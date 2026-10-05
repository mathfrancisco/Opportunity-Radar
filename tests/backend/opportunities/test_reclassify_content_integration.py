"""Database-backed proof of F50-02: batch reclassification by the enabled content rules."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import RawItemModel
from opportunity_radar.acquisition.service import COLLECTED_ITEM_V1_KEY
from opportunity_radar.opportunities.domain import ContractType, WorkMode, opportunity_fingerprint
from opportunity_radar.opportunities.models import (
    DuplicateCandidateModel,
    NormalizationResultModel,
    OpportunityModel,
    SourceOccurrenceModel,
)
from opportunity_radar.opportunities.service import OpportunityService
from opportunity_radar.platform.config import Settings, get_settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.presentation.http.app import create_app
from scripts.reclassify_content import main

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

ALL_THREE = "5+ years of experience. Regime híbrido, 3 dias. Must be located in Brazil."
ALL_RULES = (
    "seniority:description_years_min,work_mode:description_phrase,allowed_countries:description"
)
IN_FAMILIES = "SOFTWARE_ENGINEERING,DATA"


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with engine.begin() as connection:
        connection.execute(
            text("TRUNCATE acquisition.source_definition, opportunities.opportunity CASCADE")
        )
    yield engine
    get_settings.cache_clear()


def _enable(monkeypatch: pytest.MonkeyPatch, rules: str) -> None:
    monkeypatch.setenv("CONTENT_CLASSIFICATION_ENABLED_RULES", rules)
    get_settings.cache_clear()


def _seed(engine: Engine) -> dict[str, UUID]:
    """Normalize four postings with every content rule off (the state in production today)."""
    client = TestClient(create_app(Settings(database_url=os.environ["DATABASE_URL"])))
    source = client.post(
        "/sources",
        json={
            "source_type": "manual",
            "name": "Reclassify fixture",
            "enabled": True,
            "evidence_status": "confirmed",
            "collector_local_tested": True,
        },
    ).json()
    postings = [
        # three fields change once the rules are on
        ("A", "Backend Engineer", "São Paulo, SP", ALL_THREE),
        # nothing to find: title and location already decided everything they can
        ("B", "Data Engineer", "Remote — Brazil", "A friendly team and a nice office."),
        # outside the selected role families, same signals as A
        ("C", "Account Executive", "São Paulo, SP", ALL_THREE + " Join our sales team."),
        # a remote title with an on-site description: the v7 rule turns it back to UNKNOWN
        ("D", "Data Analyst", "Remote", "Regime presencial integral."),
    ]
    for key, title, location, description in postings:
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
                            "location_text": location,
                        },
                    }
                ]
            },
        )
        assert collected.status_code == 201
    assert client.post("/opportunities/normalizations/pending?limit=10").status_code == 200
    with Session(engine) as session:
        by_title = {
            row.canonical_title: row.id for row in session.scalars(select(OpportunityModel))
        }
    return {key: by_title[title] for key, title, _, _ in postings}


def _state(engine: Engine, opportunity_id: UUID) -> dict[str, Any]:
    with Session(engine) as session:
        row = session.get(OpportunityModel, opportunity_id)
        assert row is not None
        return {
            "version": row.version,
            "fingerprint": row.fingerprint,
            "seniority": row.seniority,
            "work_mode": row.work_mode,
            "allowed_countries": row.allowed_countries,
            "allowed_countries_version": row.allowed_countries_version,
            "role_family": row.role_family,
        }


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> dict[str, Any]:
    capsys.readouterr()
    assert main(list(argv)) == 0
    report: dict[str, Any] = json.loads(capsys.readouterr().out)
    return report


def test_seeded_postings_start_unclassified(engine: Engine) -> None:
    ids = _seed(engine)
    assert _state(engine, ids["A"])["seniority"] == "UNKNOWN"
    assert _state(engine, ids["A"])["allowed_countries"] is None
    assert _state(engine, ids["B"])["work_mode"] == "REMOTE"
    assert _state(engine, ids["B"])["allowed_countries"] == ["BR"]
    assert _state(engine, ids["C"])["role_family"] not in IN_FAMILIES.split(",")
    assert _state(engine, ids["D"])["work_mode"] == "REMOTE"


def test_dry_run_writes_nothing_and_reports_what_apply_then_does(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ids = _seed(engine)
    _enable(monkeypatch, ALL_RULES)
    before = {key: _state(engine, value) for key, value in ids.items()}

    dry = _run(capsys, "--role-families", IN_FAMILIES)
    assert {key: _state(engine, value) for key, value in ids.items()} == before
    assert dry["mode"] == "dry-run"
    assert dry["postings_changed"] == 2  # A and D

    applied = _run(capsys, "--role-families", IN_FAMILIES, "--apply")
    assert applied["mode"] == "apply"
    for report in (dry, applied):
        report.pop("mode"), report.pop("evidence_rewritten")
    assert dry == applied

    fields = applied["fields"]
    assert fields["seniority"]["unknown_to_value"] == 1
    assert applied["selected"] == 3  # A, B and D; C is outside the areas
    assert fields["seniority"]["unchanged"] == 2
    assert fields["seniority"]["distribution_before"] == {"UNKNOWN": 3}
    assert fields["seniority"]["distribution_after"] == {"SENIOR": 1, "UNKNOWN": 2}
    assert fields["allowed_countries"]["distribution_after"] == {"BR": 2, "UNKNOWN": 1}
    # The risky bucket: a value that goes away, with id, old, new and the rule that did it.
    assert fields["work_mode"]["value_to_unknown"] == 1
    assert {k: v for k, v in fields["work_mode"]["examples"][0].items() if k != "id"} == {
        "kind": "value_to_unknown",
        "old": "REMOTE",
        "new": "UNKNOWN",
        "rule": "title_vs_description",
    }
    assert fields["work_mode"]["examples"][0]["id"] == str(ids["D"])


def test_apply_bumps_the_version_once_per_posting_and_a_second_run_changes_nothing(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ids = _seed(engine)
    _enable(monkeypatch, ALL_RULES)
    before = {key: _state(engine, value) for key, value in ids.items()}

    first = _run(capsys, "--role-families", IN_FAMILIES, "--apply", "--batch-size", "1")
    assert first["version_bumps"] == 2

    # A: three fields changed, one version bump.
    a = _state(engine, ids["A"])
    assert (a["seniority"], a["work_mode"], a["allowed_countries"]) == ("SENIOR", "HYBRID", ["BR"])
    assert a["allowed_countries_version"] == "allowed-countries-v2"
    assert a["version"] == before["A"]["version"] + 1
    # D: one field changed, one version bump.
    d = _state(engine, ids["D"])
    assert (d["work_mode"], d["version"]) == ("UNKNOWN", before["D"]["version"] + 1)
    # B: nothing changed, no bump. C: outside the selected role families, untouched.
    assert _state(engine, ids["B"]) == before["B"]
    assert _state(engine, ids["C"]) == before["C"]

    # Evidence follows the value, with the version of the rule set that decided it.
    with Session(engine) as session:
        reasons = session.scalars(
            select(NormalizationResultModel.reasons).where(
                NormalizationResultModel.opportunity_id == ids["A"]
            )
        ).one()
    by_code = {reason["code"]: reason for reason in reasons if "mapping_version" in reason}
    assert by_code["SENIORITY_CLASSIFICATION"]["rule"] == "description_years_min"
    assert by_code["SENIORITY_CLASSIFICATION"]["mapping_version"] == "seniority-v4"
    assert by_code["WORK_MODE_CLASSIFICATION"]["mapping_version"] == "work-mode-v7"
    assert by_code["ALLOWED_COUNTRIES_CLASSIFICATION"]["source"] == "description"
    assert sum(1 for reason in reasons if reason["code"] == "SENIORITY_CLASSIFICATION") == 1

    second = _run(capsys, "--role-families", IN_FAMILIES, "--apply")
    assert second["postings_changed"] == 0
    assert second["version_bumps"] == 0
    for key in ids:  # the second run bumped nothing: A and D stay at one bump, the rest at none
        expected = before[key]["version"] + (1 if key in ("A", "D") else 0)
        assert _state(engine, ids[key])["version"] == expected


def test_only_the_enabled_rule_changes_its_field(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ids = _seed(engine)
    _enable(monkeypatch, "seniority:description_years_min")
    report = _run(capsys, "--all", "--apply")
    assert report["postings_changed"] == 2  # A and C: same description, same single rule

    for key in ("A", "C"):
        state = _state(engine, ids[key])
        assert state["seniority"] == "SENIOR"
        assert state["work_mode"] == "UNKNOWN"
        assert state["allowed_countries"] is None
        assert state["allowed_countries_version"] is None
    # `--all` reaches the posting outside the target areas.
    assert report["role_families"] is None


def test_without_an_enabled_rule_the_script_refuses_to_run(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = _seed(engine)
    monkeypatch.delenv("CONTENT_CLASSIFICATION_ENABLED_RULES", raising=False)
    get_settings.cache_clear()
    before = _state(engine, ids["A"])
    with pytest.raises(SystemExit):
        main(["--all", "--apply"])
    assert _state(engine, ids["A"]) == before


def test_default_scope_needs_an_active_profile_with_target_areas(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(engine)
    _enable(monkeypatch, ALL_RULES)
    with pytest.raises(SystemExit):
        main(["--apply"])


def _expected_fingerprint(row: OpportunityModel, work_mode: str) -> str:
    """The key normalization builds, from the stored identity inputs and a given work mode."""
    return opportunity_fingerprint(
        company_id=row.canonical_company_id,
        normalized_company_name=row.normalized_company_name,
        normalized_title=row.normalized_title,
        normalized_location=row.normalized_location,
        work_mode=WorkMode(work_mode),
        contract_type=ContractType(row.contract_type),
        published_at=row.published_at,
    )


def _renormalize(engine: Engine, opportunity_id: UUID) -> NormalizationResultModel:
    """Normalize the posting's raw item again under the same rules, as a normalizer bump would."""
    with Session(engine) as session:
        raw_item_id = session.scalars(
            select(SourceOccurrenceModel.raw_item_id).where(
                SourceOccurrenceModel.opportunity_id == opportunity_id
            )
        ).one()
        session.execute(
            delete(NormalizationResultModel).where(
                NormalizationResultModel.raw_item_id == raw_item_id
            )
        )
        session.commit()
        return OpportunityService(session).normalize(raw_item_id)


def _review_rows(engine: Engine) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(DuplicateCandidateModel)) or 0


def test_work_mode_change_moves_the_fingerprint_and_bumps_the_version_once(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ids = _seed(engine)
    _enable(monkeypatch, ALL_RULES)
    before = {key: _state(engine, value) for key, value in ids.items()}

    _run(capsys, "--all", "--apply")

    after = _state(engine, ids["A"])
    assert (after["seniority"], after["work_mode"], after["allowed_countries"]) == (
        "SENIOR",
        "HYBRID",
        ["BR"],
    )
    assert after["version"] == before["A"]["version"] + 1  # three fields moved, one bump
    with Session(engine) as session:
        row = session.get(OpportunityModel, ids["A"])
        assert row is not None
        assert before["A"]["fingerprint"] == _expected_fingerprint(row, "UNKNOWN")
        assert after["fingerprint"] == _expected_fingerprint(row, "HYBRID")
    # B kept its work mode, so its fingerprint is not touched.
    assert _state(engine, ids["B"])["fingerprint"] == before["B"]["fingerprint"]


def test_normalizing_again_after_a_reclassification_changes_nothing(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ids = _seed(engine)
    _enable(monkeypatch, ALL_RULES)
    _run(capsys, "--all", "--apply")
    reviews = _review_rows(engine)

    for key in ("A", "D"):  # A: UNKNOWN -> HYBRID, D: REMOTE -> UNKNOWN
        settled = _state(engine, ids[key])
        result = _renormalize(engine, ids[key])
        assert result.status == "SUCCEEDED"
        assert result.identity_decision == "REFRESHED"
        assert "IDENTITY_REFRESHED_SAME_EXTERNAL_ID" not in [r["code"] for r in result.reasons]
        assert _state(engine, ids[key]) == settled  # same version, same fingerprint
    assert _review_rows(engine) == reviews


# The world below holds postings that each hit a different path of the collision check.
#   X  owns the HYBRID identity of "Collide Engineer" (normalized with the rules on).
#   Y  is "Collide Engineer" normalized with the rules off (UNKNOWN): reclassified it wants
#      X's fingerprint, while its seniority and countries change too.
#   P, Q  end up with one identity of their own: Q's evidence is rewritten to P's title, as
#      if their stored fingerprints predated it.
#   A  is a bystander that changes freely.
HYBRID_DESCRIPTION = "Regime híbrido, 3 dias."
COLLIDING_DESCRIPTION = HYBRID_DESCRIPTION + " 5+ years of experience. Must be located in Brazil."


def _collect(client: TestClient, source_id: str, title: str, description: str) -> None:
    collected = client.post(
        f"/sources/{source_id}/runs",
        json={
            "inputs": [
                {
                    "kind": "TEXT",
                    "value": description,
                    "metadata": {
                        "title": title,
                        "company_name": "Example Corp",
                        "location_text": "São Paulo, SP",
                    },
                }
            ]
        },
    )
    assert collected.status_code == 201


def _collision_world(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> dict[str, UUID]:
    client = TestClient(create_app(Settings(database_url=os.environ["DATABASE_URL"])))
    source = client.post(
        "/sources",
        json={
            "source_type": "manual",
            "name": "Collision fixture",
            "enabled": True,
            "evidence_status": "confirmed",
            "collector_local_tested": True,
        },
    ).json()
    monkeypatch.delenv("CONTENT_CLASSIFICATION_ENABLED_RULES", raising=False)
    get_settings.cache_clear()
    for title, description in (
        ("Collide Engineer", COLLIDING_DESCRIPTION),
        ("Twin Engineer Alpha", HYBRID_DESCRIPTION),
        ("Twin Engineer Beta", HYBRID_DESCRIPTION + " Beta team."),
        ("Backend Engineer", ALL_THREE),
    ):
        _collect(client, source["id"], title, description)
    assert client.post("/opportunities/normalizations/pending?limit=10").status_code == 200
    # X is normalized afterwards, with the rules on, so it takes the HYBRID identity first.
    _enable(monkeypatch, ALL_RULES)
    _collect(client, source["id"], "Collide Engineer", HYBRID_DESCRIPTION + " Owner team.")
    assert client.post("/opportunities/normalizations/pending?limit=10").status_code == 200

    with Session(engine) as session:
        rows = list(session.scalars(select(OpportunityModel)))
        unknown = {row.canonical_title: row for row in rows if row.work_mode == "UNKNOWN"}
        ids = {
            "X": next(row.id for row in rows if row.work_mode == "HYBRID"),
            "Y": unknown["Collide Engineer"].id,
            "P": unknown["Twin Engineer Alpha"].id,
            "Q": unknown["Twin Engineer Beta"].id,
            "A": unknown["Backend Engineer"].id,
        }
        raw_item_id = session.scalars(
            select(SourceOccurrenceModel.raw_item_id).where(
                SourceOccurrenceModel.opportunity_id == ids["Q"]
            )
        ).one()
        metadata = session.scalars(
            select(RawItemModel.item_metadata).where(RawItemModel.id == raw_item_id)
        ).one()
        snapshot = {**metadata[COLLECTED_ITEM_V1_KEY], "title": "Twin Engineer Alpha"}
        # RawItem is immutable through the ORM; a bulk update is the fixture's way around it.
        session.execute(
            update(RawItemModel)
            .where(RawItemModel.id == raw_item_id)
            .values(item_metadata={**metadata, COLLECTED_ITEM_V1_KEY: snapshot})
        )
        session.commit()
    return ids


def test_a_taken_fingerprint_keeps_the_work_mode_and_reports_the_collision(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ids = _collision_world(engine, monkeypatch)
    before = {key: _state(engine, value) for key, value in ids.items()}

    report = _run(capsys, "--all", "--apply", "--batch-size", "10")  # one batch, no IntegrityError

    y = _state(engine, ids["Y"])
    assert (y["work_mode"], y["fingerprint"]) == ("UNKNOWN", before["Y"]["fingerprint"])
    assert (y["seniority"], y["allowed_countries"]) == ("SENIOR", ["BR"])  # the rest applies
    assert y["version"] == before["Y"]["version"] + 1
    assert _state(engine, ids["X"]) == before["X"]
    a = _state(engine, ids["A"])  # the rest of the batch still goes through
    assert (a["work_mode"], a["version"]) == ("HYBRID", before["A"]["version"] + 1)

    collisions = report["fingerprint_collisions"]
    example = next(item for item in collisions["examples"] if item["id"] == str(ids["Y"]))
    assert example == {
        "id": str(ids["Y"]),
        "competing_opportunity_id": str(ids["X"]),
        "old": "UNKNOWN",
        "new": "HYBRID",
    }
    assert collisions["count"] == len(collisions["examples"]) == 2  # Y, plus one of P and Q


def test_two_postings_of_one_batch_collide_with_each_other(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ids = _collision_world(engine, monkeypatch)
    before = {key: _state(engine, value) for key, value in ids.items()}

    report = _run(capsys, "--all", "--apply", "--batch-size", "10")

    moved = [key for key in ("P", "Q") if _state(engine, ids[key])["work_mode"] == "HYBRID"]
    assert len(moved) == 1  # the first one moves; the second is the collision
    kept = "Q" if moved[0] == "P" else "P"
    winner, loser = ids[moved[0]], ids[kept]
    assert _state(engine, winner)["version"] == before[moved[0]]["version"] + 1
    assert _state(engine, loser) == before[kept]  # nothing else to apply: untouched
    example = next(
        item for item in report["fingerprint_collisions"]["examples"] if item["id"] == str(loser)
    )
    assert example["competing_opportunity_id"] == str(winner)


def test_dry_run_reports_the_same_collisions_and_writes_nothing(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ids = _collision_world(engine, monkeypatch)
    before = {key: _state(engine, value) for key, value in ids.items()}

    dry = _run(capsys, "--all", "--batch-size", "1")
    assert {key: _state(engine, value) for key, value in ids.items()} == before
    assert dry["fingerprint_collisions"]["count"] == 2

    applied = _run(capsys, "--all", "--apply", "--batch-size", "1")
    for report in (dry, applied):
        report.pop("mode"), report.pop("evidence_rewritten")
    assert dry == applied  # collisions, examples and every count alike


def test_a_second_run_changes_nothing_but_still_reports_the_collisions(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ids = _collision_world(engine, monkeypatch)
    _run(capsys, "--all", "--apply")
    settled = {key: _state(engine, value) for key, value in ids.items()}

    second = _run(capsys, "--all", "--apply")

    assert second["postings_changed"] == 0
    assert second["version_bumps"] == 0
    assert {key: _state(engine, value) for key, value in ids.items()} == settled
    # Stated on purpose: the postings that could not take their work mode are still refused,
    # so they are reported as collisions again; that is a report line, not a change.
    assert second["fingerprint_collisions"]["count"] == 2
