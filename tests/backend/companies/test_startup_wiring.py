"""F20-54 wiring: startup discovery (F20-53) records startup evidence for the company."""

from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import SourceDefinitionModel
from opportunity_radar.acquisition.registry import build_collector_registry
from opportunity_radar.acquisition.startup_discovery import (
    StartupBoard,
    StartupCandidate,
    ValidatedStartup,
    propose_startups,
)
from opportunity_radar.companies.models import Company, CompanyStartupEvidence
from opportunity_radar.companies.startup import derive_startup_evidence
from opportunity_radar.platform.database import create_database_engine

_PREFIX = "f20-54w:"
_db = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)


# --- pure derivation ----------------------------------------------------------------


def test_brand_in_text_is_strong_yc_batch_with_batch() -> None:
    derived = derive_startup_evidence(
        strong_term=True,
        term='"Y Combinator" startup remote',
        excerpt="We are a startup backed by Y Combinator (S24) hiring engineers.",
    )
    assert (derived.signal, derived.strength, derived.batch) == ("yc_batch", "strong", "S24")
    assert "Y Combinator" in derived.source_text


def test_brand_in_text_without_batch_is_strong_with_no_batch() -> None:
    derived = derive_startup_evidence(
        strong_term=True, term="YC", excerpt="Backed by Y Combinator and others."
    )
    assert (derived.signal, derived.strength, derived.batch) == ("yc_batch", "strong", None)


def test_brand_term_without_brand_in_text_is_only_weak() -> None:
    derived = derive_startup_evidence(
        strong_term=True, term='"Y Combinator" startup remote', excerpt="Hiring a recruiter."
    )
    assert (derived.signal, derived.strength, derived.batch) == ("other", "weak", None)


def test_stage_term_maps_to_series_a_or_seed_and_is_weak() -> None:
    series = derive_startup_evidence(
        strong_term=False, term="stage", excerpt="We just raised our Series A."
    )
    seed = derive_startup_evidence(
        strong_term=False, term="stage", excerpt="A seed stage company."
    )
    assert (series.signal, series.strength) == ("series_a", "weak")
    assert (seed.signal, seed.strength) == ("seed_stage", "weak")
    unknown = derive_startup_evidence(strong_term=False, term="stage", excerpt=None)
    assert (unknown.signal, unknown.strength) == ("other", "weak")


# --- proposal wiring (database, no network) -----------------------------------------


@pytest.fixture
def session() -> Iterator[Session]:
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as db:
        _purge(db)
        yield db
        db.rollback()
        _purge(db)


def _purge(db: Session) -> None:
    db.execute(
        delete(SourceDefinitionModel).where(
            SourceDefinitionModel.configuration["company_name"].as_string().startswith(_PREFIX)
        )
    )
    db.execute(delete(Company).where(Company.canonical_name.startswith(_PREFIX)))
    db.commit()


def _validated(name: str, key: str, *, strength: str, excerpt: str) -> ValidatedStartup:
    board = StartupBoard("lever", key, f"https://jobs.lever.co/{key}/1")
    candidate = StartupCandidate(
        name=name,
        key=uuid4().hex,
        boards=(board,),
        strength=strength,  # type: ignore[arg-type]
        terms=('"Y Combinator" remote',) if strength == "forte" else ('"seed stage"',),
        excerpt=excerpt,
        score=0.9,
    )
    return ValidatedStartup(candidate, board, 1)


def _evidence(db: Session, name: str) -> list[CompanyStartupEvidence]:
    return list(
        db.scalars(
            select(CompanyStartupEvidence)
            .join(Company, Company.id == CompanyStartupEvidence.company_id)
            .where(Company.canonical_name == name)
        )
    )


def _registry():
    return build_collector_registry(greenhouse_base_url="https://boards-api.greenhouse.io")


@_db
def test_strong_proposal_records_strong_evidence_with_result_url(session: Session) -> None:
    name = f"{_PREFIX}Acme {uuid4().hex[:6]}"
    key = f"w{uuid4().hex[:8]}"
    validated = _validated(name, key, strength="forte", excerpt="Backed by YC S24, remote first.")

    propose_startups(session, [validated], registry=_registry())
    session.commit()

    (row,) = _evidence(session, name)
    assert (row.signal, row.strength, row.batch) == ("yc_batch", "strong", "S24")
    assert row.source_url == f"https://jobs.lever.co/{key}/1"


@_db
def test_weak_proposal_records_weak_stage_evidence(session: Session) -> None:
    name = f"{_PREFIX}Seedco {uuid4().hex[:6]}"
    validated = _validated(
        name, f"w{uuid4().hex[:8]}", strength="fraco", excerpt="An early seed stage team."
    )

    propose_startups(session, [validated], registry=_registry())
    session.commit()

    (row,) = _evidence(session, name)
    assert (row.signal, row.strength) == ("seed_stage", "weak")


@_db
def test_rerun_does_not_duplicate_evidence_and_weak_never_downgrades_strong(
    session: Session,
) -> None:
    name = f"{_PREFIX}Rerun {uuid4().hex[:6]}"
    key = f"w{uuid4().hex[:8]}"
    strong = _validated(name, key, strength="forte", excerpt="Backed by Y Combinator.")
    weak = _validated(name, key, strength="fraco", excerpt="seed stage")

    propose_startups(session, [strong], registry=_registry())
    propose_startups(session, [strong], registry=_registry())
    propose_startups(session, [weak], registry=_registry())
    session.commit()

    rows = _evidence(session, name)
    assert sorted(row.strength for row in rows) == ["strong", "weak"]
    assert len([row for row in rows if row.strength == "strong"]) == 1


@_db
def test_failed_probe_records_no_evidence(session: Session) -> None:
    name = f"{_PREFIX}Ghost {uuid4().hex[:6]}"
    validated = _validated(name, "ghost", strength="forte", excerpt="Y Combinator")

    propose_startups(
        session, [ValidatedStartup(validated.candidate, None, 2)], registry=_registry()
    )

    assert _evidence(session, name) == []
