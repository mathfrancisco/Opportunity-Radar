"""Database-backed proof of the seniority retag (F52-02): old levels are recomputed in place."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.domain import SENIORITY_MAPPING_VERSION
from opportunity_radar.opportunities.models import (
    NormalizationResultModel,
    OpportunityModel,
    SourceOccurrenceModel,
)
from opportunity_radar.platform.config import Settings, get_settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.presentation.http.app import create_development_app as create_app
from scripts.retag_seniority import main

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

OLD = "seniority-v3"
# key, title, the level `seniority-v3` had stored, the level the current mapping gives
POSTINGS = [
    ("A", "Desenvolvedor(a) Backend Sênior - Node.js", "UNKNOWN", "SENIOR"),
    ("B", "Entry Level Developer", "INTERN", "JUNIOR"),
    ("C", "Desenvolvedor Pl/Sr", "UNKNOWN", "MID"),
    # same level under both mappings: only the evidence is brought up to date
    ("D", "Senior Data Engineer", "SENIOR", "SENIOR"),
    ("E", "Data Engineer", "UNKNOWN", "UNKNOWN"),
]


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with engine.begin() as connection:
        connection.execute(
            text("TRUNCATE acquisition.source_definition, opportunities.opportunity CASCADE")
        )
    yield engine
    get_settings.cache_clear()


def _seed(engine: Engine) -> dict[str, UUID]:
    """Five postings normalized today, then aged back to what `seniority-v3` had stored."""
    client = TestClient(create_app(Settings(database_url=os.environ["DATABASE_URL"])))
    source = client.post(
        "/sources",
        json={
            "source_type": "manual",
            "name": "Seniority retag fixture",
            "enabled": True,
            "evidence_status": "confirmed",
            "collector_local_tested": True,
        },
    ).json()
    for _, title, _, _ in POSTINGS:
        collected = client.post(
            f"/sources/{source['id']}/runs",
            json={
                "inputs": [
                    {
                        "kind": "TEXT",
                        "value": f"We build payment systems. Opening: {title}.",
                        "metadata": {
                            "title": title,
                            "company_name": "Example Corp",
                            "location_text": "Remote",
                        },
                    }
                ]
            },
        )
        assert collected.status_code == 201
    assert client.post("/opportunities/normalizations/pending?limit=10").status_code == 200
    with Session(engine) as session:
        ids = {row.canonical_title: row.id for row in session.scalars(select(OpportunityModel))}
        for _, title, old_level, new_level in POSTINGS:
            opportunity = session.get(OpportunityModel, ids[title])
            assert opportunity is not None and opportunity.seniority == new_level
            opportunity.seniority = old_level
            result = _result(session, opportunity.id)
            result.reasons = [
                {
                    "code": "SENIORITY_CLASSIFICATION",
                    "source": "title",
                    "external_value": None,
                    "mapping_version": OLD,
                    "collector": "manual",
                    "value": old_level,
                }
                if reason.get("code") == "SENIORITY_CLASSIFICATION"
                else reason
                for reason in result.reasons
            ]
        session.commit()
    return {key: ids[title] for key, title, _, _ in POSTINGS}


def _result(session: Session, opportunity_id: UUID) -> NormalizationResultModel:
    result = session.scalar(
        select(NormalizationResultModel)
        .join(
            SourceOccurrenceModel,
            SourceOccurrenceModel.raw_item_id == NormalizationResultModel.raw_item_id,
        )
        .where(SourceOccurrenceModel.opportunity_id == opportunity_id)
    )
    assert result is not None
    return result


def _state(engine: Engine, opportunity_id: UUID) -> dict[str, Any]:
    with Session(engine) as session:
        row = session.get(OpportunityModel, opportunity_id)
        assert row is not None
        reasons = _result(session, opportunity_id).reasons
        return {
            "version": row.version,
            "seniority": row.seniority,
            "evidence": [
                reason for reason in reasons if reason.get("code") == "SENIORITY_CLASSIFICATION"
            ],
            "other_reasons": [
                reason for reason in reasons if reason.get("code") != "SENIORITY_CLASSIFICATION"
            ],
        }


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> dict[str, Any]:
    capsys.readouterr()
    assert main(list(argv)) == 0
    report: dict[str, Any] = json.loads(capsys.readouterr().out)
    return report


def test_dry_run_writes_nothing_and_reports_what_apply_then_does(
    engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    ids = _seed(engine)
    before = {key: _state(engine, value) for key, value in ids.items()}

    dry = _run(capsys)
    assert {key: _state(engine, value) for key, value in ids.items()} == before
    assert dry["mode"] == "dry-run"

    applied = _run(capsys, "--apply")
    assert applied.pop("mode") == "apply" and dry.pop("mode") == "dry-run"
    assert dry == applied
    assert applied["mapping_version"] == SENIORITY_MAPPING_VERSION
    assert applied["selected"] == 5
    assert applied["postings_changed"] == applied["version_bumps"] == 3
    assert applied["evidence_rewritten"] == 5
    assert applied["transitions"] == {
        "INTERN->JUNIOR": 1,
        "UNKNOWN->MID": 1,
        "UNKNOWN->SENIOR": 1,
    }
    assert applied["distribution_before"] == {"INTERN": 1, "SENIOR": 1, "UNKNOWN": 3}
    assert applied["distribution_after"] == {"JUNIOR": 1, "MID": 1, "SENIOR": 2, "UNKNOWN": 1}

    after = {key: _state(engine, value) for key, value in ids.items()}
    for key, _, old_level, new_level in POSTINGS:
        bump = 1 if old_level != new_level else 0
        assert after[key]["seniority"] == new_level
        assert after[key]["version"] == before[key]["version"] + bump
        (evidence,) = after[key]["evidence"]
        assert evidence["mapping_version"] == SENIORITY_MAPPING_VERSION
        assert evidence["value"] == new_level
        assert after[key]["other_reasons"] == before[key]["other_reasons"]
    # A range keeps its lowest level; the evidence carries the whole range (SPEC 52, Q1).
    assert after["C"]["evidence"][0]["range"] == "MID,SENIOR"


def test_a_second_run_finds_nothing_to_do(
    engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    ids = _seed(engine)
    _run(capsys, "--apply", "--batch-size", "2")
    after_first = {key: _state(engine, value) for key, value in ids.items()}

    second = _run(capsys, "--apply")

    assert second["postings_changed"] == 0 and second["evidence_rewritten"] == 0
    assert second["transitions"] == {}
    assert {key: _state(engine, value) for key, value in ids.items()} == after_first


def test_limit_bounds_the_postings_read(
    engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed(engine)

    assert _run(capsys, "--limit", "2")["selected"] == 2
