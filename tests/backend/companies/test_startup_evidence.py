"""Card F20-54: startup evidence on a company, its precedence, and the Inbox filter.

The pure/source-level checks always run; the database ones run under
`RUN_DATABASE_INTEGRATION=1` like the rest of the integration suite.
"""

from __future__ import annotations

import dataclasses
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import opportunity_radar
from opportunity_radar.companies.models import Company, CompanyStartupEvidence
from opportunity_radar.companies.startup import (
    InvalidStartupEvidenceError,
    StartupSummary,
    record_startup_evidence,
    startup_evidence,
    summarize,
)
from opportunity_radar.matching.domain import OpportunitySnapshot
from opportunity_radar.matching.service import MatchingService
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.presentation.http.app import create_development_app as create_app
from opportunity_radar.profile.domain import EmploymentPreference, ProfileSnapshot, Skill
from opportunity_radar.profile.models import CareerProfileModel
from opportunity_radar.profile.service import ProfileService

NOW = datetime(2026, 9, 29, 12, tzinfo=UTC)
PACKAGE = Path(opportunity_radar.__file__).parent

integration = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)


def _row(**changes: object) -> CompanyStartupEvidence:
    values: dict[str, object] = {
        "company_id": uuid4(),
        "signal": "yc_batch",
        "strength": "strong",
        "source_text": "Y Combinator (S24)",
        "source_url": None,
        "batch": "S24",
        "captured_at": NOW,
    }
    values.update(changes)
    return CompanyStartupEvidence(**values)


# --- pure: precedence and accumulation -----------------------------------------------


def test_summary_of_no_evidence_is_not_a_startup() -> None:
    assert summarize([]) == StartupSummary(strength=None, batch=None, evidence_count=0)


def test_strong_evidence_is_not_overridden_by_a_newer_weak_one() -> None:
    strong = _row(captured_at=NOW)
    weak = _row(
        signal="seed_stage",
        strength="weak",
        source_text="seed stage",
        batch=None,
        captured_at=NOW + timedelta(days=30),
    )
    summary = summarize([strong, weak])
    assert summary.strength == "strong"
    assert summary.batch == "S24"
    assert summary.evidence_count == 2
    assert summarize([weak, strong]) == summary


def test_weak_only_evidence_reads_weak_and_has_no_batch() -> None:
    weak = _row(signal="series_a", strength="weak", source_text="Series A", batch=None)
    assert summarize([weak]) == StartupSummary(strength="weak", batch=None, evidence_count=1)


def test_latest_strong_batch_wins_among_strong_evidence() -> None:
    older = _row(batch="W23", source_text="YC W23", captured_at=NOW)
    newer = _row(batch="S24", captured_at=NOW + timedelta(days=1))
    assert summarize([newer, older]).batch == "S24"


# --- guard: the mark is display/filter metadata only ---------------------------------


def test_matching_snapshot_has_no_startup_field() -> None:
    names = {field.name for field in dataclasses.fields(OpportunitySnapshot)}
    assert not {name for name in names if "startup" in name}


@pytest.mark.parametrize("package", ["matching", "opportunities"])
def test_matching_and_opportunities_never_read_startup_evidence(package: str) -> None:
    pattern = re.compile(r"startup_evidence|StartupEvidence|companies\.startup|is_startup", re.I)
    offenders = [
        str(path.relative_to(PACKAGE))
        for path in (PACKAGE / package).rglob("*.py")
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


# --- database ------------------------------------------------------------------------


def _engine():
    return create_database_engine(os.environ["DATABASE_URL"])


def _company(session: Session, marker: str) -> Company:
    company = Company(
        canonical_name=f"Startup Co {marker}",
        normalized_name=f"startup co {marker}",
        priority="normal",
    )
    session.add(company)
    session.flush()
    return company


def _opportunity(session: Session, company: Company, marker: str) -> OpportunityModel:
    opportunity = OpportunityModel(
        fingerprint=uuid4().hex + uuid4().hex,
        fingerprint_version="v1",
        canonical_title=f"Backend {marker}",
        normalized_title=f"backend {marker}",
        normalized_company_name=company.normalized_name,
        company_name=company.canonical_name,
        canonical_company_id=company.id,
        work_mode="REMOTE",
        seniority="SENIOR",
        contract_type="FULL_TIME",
        lifecycle_status="ACTIVE",
        published_at=datetime.now(UTC) - timedelta(days=1),
        version=1,
    )
    session.add(opportunity)
    session.flush()
    return opportunity


def _cleanup(session: Session, company_ids: list[UUID], opportunity_ids: list[UUID]) -> None:
    session.rollback()
    session.execute(delete(OpportunityModel).where(OpportunityModel.id.in_(opportunity_ids)))
    session.execute(delete(Company).where(Company.id.in_(company_ids)))
    session.commit()


@integration
def test_evidence_is_stored_with_type_strength_origin_and_date() -> None:
    with Session(_engine()) as session:
        company = _company(session, uuid4().hex[:8])
        try:
            record_startup_evidence(
                session,
                company.id,
                signal="yc_batch",
                strength="strong",
                source_text="Y Combinator (S24)",
                source_url="https://boards.greenhouse.io/x/jobs/1",
                batch="S24",
                captured_at=NOW,
            )
            session.commit()
            (stored,) = startup_evidence(session, company.id)
            assert stored.signal == "yc_batch"
            assert stored.strength == "strong"
            assert stored.source_text == "Y Combinator (S24)"
            assert stored.source_url == "https://boards.greenhouse.io/x/jobs/1"
            assert stored.batch == "S24"
            assert stored.captured_at == NOW
        finally:
            _cleanup(session, [company.id], [])


@integration
def test_evidence_accumulates_and_a_weak_sighting_never_replaces_a_strong_one() -> None:
    with Session(_engine()) as session:
        company = _company(session, uuid4().hex[:8])
        try:
            record_startup_evidence(
                session, company.id, signal="yc_batch", strength="strong",
                source_text="Y Combinator (S24)", batch="S24", captured_at=NOW,
            )
            record_startup_evidence(
                session, company.id, signal="seed_stage", strength="weak",
                source_text="seed stage", captured_at=NOW + timedelta(days=5),
            )
            # Same sighting again: idempotent, not a duplicate row.
            record_startup_evidence(
                session, company.id, signal="seed_stage", strength="weak",
                source_text="seed stage", captured_at=NOW + timedelta(days=9),
            )
            session.commit()
            rows = startup_evidence(session, company.id)
            assert [(row.signal, row.strength) for row in rows] == [
                ("yc_batch", "strong"),
                ("seed_stage", "weak"),
            ]
            assert summarize(rows).strength == "strong"
        finally:
            _cleanup(session, [company.id], [])


@integration
def test_invalid_evidence_is_rejected() -> None:
    with Session(_engine()) as session:
        company_id = uuid4()
        with pytest.raises(InvalidStartupEvidenceError):
            record_startup_evidence(
                session, company_id, signal="unicorn", strength="strong", source_text="x"
            )
        with pytest.raises(InvalidStartupEvidenceError):
            record_startup_evidence(
                session, company_id, signal="other", strength="medium", source_text="x"
            )
        with pytest.raises(InvalidStartupEvidenceError):
            record_startup_evidence(
                session, company_id, signal="other", strength="weak", source_text="  "
            )


@integration
def test_inbox_only_startups_filter_and_fields() -> None:
    database_url = os.environ["DATABASE_URL"]
    client = TestClient(create_app(Settings(database_url=database_url)))
    marker = uuid4().hex[:10]
    with Session(_engine()) as session:
        strong_co = _company(session, f"a{marker}")
        weak_co = _company(session, f"b{marker}")
        plain_co = _company(session, f"c{marker}")
        strong_opp = _opportunity(session, strong_co, marker)
        weak_opp = _opportunity(session, weak_co, marker)
        plain_opp = _opportunity(session, plain_co, marker)
        record_startup_evidence(
            session, strong_co.id, signal="yc_batch", strength="strong",
            source_text="Y Combinator (S24)", batch="S24",
        )
        record_startup_evidence(
            session, strong_co.id, signal="seed_stage", strength="weak",
            source_text="seed stage", captured_at=datetime.now(UTC) + timedelta(seconds=5),
        )
        record_startup_evidence(
            session, weak_co.id, signal="series_a", strength="weak", source_text="Series A"
        )
        session.commit()
        company_ids = [strong_co.id, weak_co.id, plain_co.id]
        opportunity_ids = [strong_opp.id, weak_opp.id, plain_opp.id]
        try:
            params = {"all_areas": "true", "search": marker}
            everything = client.get("/inbox", params=params).json()["items"]
            assert {item["opportunity_id"] for item in everything} == {
                str(value) for value in opportunity_ids
            }

            filtered = client.get("/inbox", params={**params, "only_startups": "true"})
            assert filtered.status_code == 200
            items = {item["opportunity_id"]: item for item in filtered.json()["items"]}
            assert set(items) == {str(strong_opp.id), str(weak_opp.id)}
            assert items[str(strong_opp.id)]["startup_strength"] == "strong"
            assert items[str(strong_opp.id)]["startup_batch"] == "S24"
            assert items[str(weak_opp.id)]["startup_strength"] == "weak"
            assert items[str(weak_opp.id)]["startup_batch"] is None

            unfiltered = {item["opportunity_id"]: item for item in everything}
            assert unfiltered[str(plain_opp.id)]["startup_strength"] is None
        finally:
            _cleanup(session, company_ids, opportunity_ids)


def _activate_profile(session: Session) -> None:
    service = ProfileService(session)
    profile = session.scalar(select(CareerProfileModel).limit(1))
    expected = profile.version if profile is not None else 0
    snapshot = ProfileSnapshot(
        skills=(Skill(canonical_name="python"),),
        experiences=(),
        projects=(),
        preferences=EmploymentPreference(work_modes=("REMOTE",), countries=("BR",)),
    )
    version = service.create_version(snapshot, expected)
    profile = session.scalar(select(CareerProfileModel).limit(1))
    assert profile is not None
    service.publish(version.id, profile.version)
    session.refresh(profile)
    service.activate(version.id, profile.version)


@integration
def test_startup_evidence_does_not_change_the_assessment() -> None:
    """Regression against the existing matching: same inputs, same assessment."""
    with Session(_engine()) as session:
        _activate_profile(session)
        company = _company(session, uuid4().hex[:8])
        opportunity = _opportunity(session, company, uuid4().hex[:8])
        session.commit()
        # No cleanup: assessments are immutable by trigger (as in the other matching
        # integration tests, the rows stay in the isolated CI database).
        before = MatchingService(session).evaluate(opportunity.id)
        snapshot = (before.verdict, before.eligibility, before.score, before.input_hash)

        record_startup_evidence(
            session, company.id, signal="yc_batch", strength="strong",
            source_text="Y Combinator (S24)", batch="S24",
        )
        session.commit()
        after = MatchingService(session).evaluate(opportunity.id)

        # An unchanged input hash makes `evaluate` return the very same assessment.
        assert after.id == before.id
        assert (after.verdict, after.eligibility, after.score, after.input_hash) == snapshot


@integration
def test_company_endpoint_exposes_the_evidence_with_its_origin() -> None:
    database_url = os.environ["DATABASE_URL"]
    client = TestClient(create_app(Settings(database_url=database_url)))
    with Session(_engine()) as session:
        company = _company(session, uuid4().hex[:8])
        record_startup_evidence(
            session, company.id, signal="yc_batch", strength="strong",
            source_text="Y Combinator (S24)", source_url="https://example.com/job", batch="S24",
        )
        session.commit()
        try:
            body = client.get(f"/companies/{company.id}").json()
            assert body["startup_strength"] == "strong"
            assert body["startup_batch"] == "S24"
            (evidence,) = body["startup_evidence"]
            assert evidence["signal"] == "yc_batch"
            assert evidence["source_text"] == "Y Combinator (S24)"
            assert evidence["source_url"] == "https://example.com/job"
        finally:
            _cleanup(session, [company.id], [])
