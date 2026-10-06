"""Database-backed proof of the skill retag: old-taxonomy skills are re-extracted in place."""

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

from opportunity_radar.opportunities.domain import SKILL_TAXONOMY_VERSION
from opportunity_radar.opportunities.models import OpportunityModel, OpportunitySkillModel
from opportunity_radar.platform.config import Settings, get_settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.presentation.http.app import create_app
from scripts.retag_skills import main

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

OLD = "skills-v3"


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
    """Two postings normalized today; A is then aged back to the old taxonomy."""
    client = TestClient(create_app(Settings(database_url=os.environ["DATABASE_URL"])))
    source = client.post(
        "/sources",
        json={
            "source_type": "manual",
            "name": "Retag fixture",
            "enabled": True,
            "evidence_status": "confirmed",
            "collector_local_tested": True,
        },
    ).json()
    postings = [
        ("A", "Backend Engineer", "Required: Python and PostgreSQL."),
        ("B", "Data Engineer", "Required: Python and Kafka."),
    ]
    for _, title, description in postings:
        collected = client.post(
            f"/sources/{source['id']}/runs",
            json={
                "inputs": [
                    {
                        "kind": "TEXT",
                        "value": description,
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
        a = ids["Backend Engineer"]
        # The old catalogue: same occurrence evidence, old version label, and one skill the
        # new taxonomy no longer extracts from this text.
        session.execute(
            text(
                "UPDATE opportunities.opportunity_skill SET taxonomy_version = :old"
                " WHERE opportunity_id = :id"
            ),
            {"old": OLD, "id": a},
        )
        stale = session.scalars(
            select(OpportunitySkillModel).where(OpportunitySkillModel.opportunity_id == a)
        ).first()
        assert stale is not None
        session.add(
            OpportunitySkillModel(
                opportunity_id=a,
                canonical_name="ml",
                display_name="ml",
                requirement=stale.requirement,
                evidence=list(stale.evidence),
                taxonomy_version=OLD,
                normalizer_version=stale.normalizer_version,
            )
        )
        session.commit()
    return {key: ids[title] for key, title, _ in postings}


def _state(engine: Engine, opportunity_id: UUID) -> dict[str, Any]:
    with Session(engine) as session:
        row = session.get(OpportunityModel, opportunity_id)
        assert row is not None
        return {
            "version": row.version,
            "search_skills": row.search_skills,
            "skills": sorted(
                (skill.canonical_name, skill.taxonomy_version) for skill in row.skills
            ),
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
    assert {version for _, version in before["A"]["skills"]} == {OLD}
    assert ("ml", OLD) in before["A"]["skills"]

    dry = _run(capsys)
    assert {key: _state(engine, value) for key, value in ids.items()} == before
    assert dry["mode"] == "dry-run"

    applied = _run(capsys, "--apply")
    assert applied.pop("mode") == "apply" and dry.pop("mode") == "dry-run"
    assert dry == applied
    assert applied["selected"] == 1  # B was already on the current taxonomy
    assert applied["postings_changed"] == 1 and applied["still_old"] == 0
    assert set(applied["skill_rows_before"]) == {OLD}
    assert set(applied["skill_rows_after"]) == {SKILL_TAXONOMY_VERSION}

    after = _state(engine, ids["A"])
    names = {name for name, _ in after["skills"]}
    assert {version for _, version in after["skills"]} == {SKILL_TAXONOMY_VERSION}
    assert {"python", "postgresql"} <= names and "ml" not in names
    assert after["version"] == before["A"]["version"] + 1
    assert "ml" not in (after["search_skills"] or "").split()
    assert _state(engine, ids["B"]) == before["B"]


def test_a_second_run_finds_nothing_to_do(
    engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    ids = _seed(engine)
    _run(capsys, "--apply", "--batch-size", "1")
    after_first = _state(engine, ids["A"])

    second = _run(capsys, "--apply")

    assert second["selected"] == 0 and second["postings_changed"] == 0
    assert _state(engine, ids["A"]) == after_first
