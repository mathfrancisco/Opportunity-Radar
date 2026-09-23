"""Database-backed proof that sources, companies and jobs can be curated over HTTP."""

from __future__ import annotations

import os
from base64 import b64encode
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from opportunity_radar.platform.config import Settings
from opportunity_radar.presentation.http.app import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


def _client() -> TestClient:
    return TestClient(create_app(Settings(database_url=os.environ["DATABASE_URL"])))


def _unique(prefix: str) -> str:
    return f"{prefix} {uuid4().hex[:8]}"


def test_source_refusals_name_their_field_and_a_stale_write_is_a_conflict() -> None:
    client = _client()

    missing_board = client.post(
        "/sources",
        json={"source_type": "greenhouse", "name": _unique("CI board"), "configuration": {}},
    )
    assert missing_board.status_code == 422
    assert missing_board.json()["detail"]["field"] == "configuration.board_token"

    secret = client.post(
        "/sources",
        json={
            "source_type": "greenhouse",
            "name": _unique("CI secret"),
            "configuration": {"board_token": "ci-board", "api_key": "nope"},
        },
    )
    assert secret.status_code == 422
    assert secret.json()["detail"]["field"] == "configuration"
    assert "secret" in secret.json()["detail"]["message"]

    created = client.post(
        "/sources",
        json={
            "source_type": "greenhouse",
            "name": _unique("CI conflict"),
            "configuration": {"board_token": "ci-board"},
            "evidence_status": "confirmed",
        },
    )
    assert created.status_code == 201
    source = created.json()
    assert source["enabled"] is False

    controls = {
        "enabled": False,
        "terms_reviewed": True,
        "collector_local_tested": False,
        "expected_version": source["version"],
    }
    first = client.patch(f"/sources/{source['id']}", json=controls)
    assert first.status_code == 200
    stale = client.patch(f"/sources/{source['id']}", json=controls)
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"

    gate = client.patch(
        f"/sources/{source['id']}",
        json={**controls, "enabled": True, "expected_version": first.json()["version"]},
    )
    assert gate.status_code == 422
    assert gate.json()["detail"]["code"] == "INVALID_CONFIGURATION"


def test_manual_run_is_normalized_item_by_item() -> None:
    client = _client()
    source = client.post(
        "/sources",
        json={"source_type": "manual", "name": _unique("CI manual intake"), "enabled": True},
    ).json()
    marker = uuid4().hex[:8]
    inputs = [
        {
            "kind": "TEXT",
            "value": f"Senior Python Engineer at Example {marker}. Remote, full time.",
            "metadata": {"title": f"Senior Python Engineer {marker}", "company": "Example"},
        },
        {
            "kind": "FILE",
            "value": f"posting-{marker}.txt",
            "content_type": "text/plain",
            "content_base64": b64encode(
                f"Staff Backend Engineer {marker}. Remote.".encode()
            ).decode(),
            "metadata": {"title": f"Staff Backend Engineer {marker}", "company": "Example"},
        },
    ]

    run = client.post(f"/sources/{source['id']}/runs", json={"inputs": inputs})
    assert run.status_code == 201
    assert run.json()["items_persisted"] == 2

    normalized = client.post(f"/opportunities/normalizations/runs/{run.json()['id']}")
    assert normalized.status_code == 200
    items = normalized.json()["items"]
    assert len(items) == 2
    assert all(item["result"]["raw_item_id"] == item["raw_item_id"] for item in items)
    outcomes = {"SUCCEEDED", "REVIEW_REQUIRED", "FAILED"}
    assert all(item["result"]["status"] in outcomes for item in items)

    # Asking again answers the recorded outcome instead of normalizing twice.
    again = client.post(f"/opportunities/normalizations/runs/{run.json()['id']}")
    assert [item["result"]["id"] for item in again.json()["items"]] == [
        item["result"]["id"] for item in items
    ]

    repeated = client.post(f"/sources/{source['id']}/runs", json={"inputs": inputs})
    assert repeated.json()["items_skipped"] == 2
    assert repeated.json()["items_persisted"] == 0
    nothing_new = client.post(f"/opportunities/normalizations/runs/{repeated.json()['id']}")
    assert nothing_new.json()["items"] == []

    missing = client.post(f"/opportunities/normalizations/runs/{uuid4()}")
    assert missing.status_code == 404


def test_company_registration_reconciles_names_and_guards_identity() -> None:
    client = _client()
    total_before = client.get("/companies?page_size=1").json()["total"]
    name = _unique("Radar Labs")
    domain = f"{uuid4().hex[:10]}.example"

    created = client.post(
        "/companies",
        json={"name": name, "domain": f"https://www.{domain}/careers", "priority": "high"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["outcome"] == "created"
    company = body["company"]
    assert company["domain"] == domain
    assert company["priority"] == "high"
    assert company["version"] == 1
    assert client.get("/companies?page_size=1").json()["total"] == total_before + 1

    # The same company typed differently answers with the existing record; a suffix is a
    # different name, which is the importer's rule too.
    variant = client.post("/companies", json={"name": f"  {name.upper()}  Inc "})
    assert variant.json()["outcome"] == "created"  # "Inc" makes a different key
    same = client.post("/companies", json={"name": name.upper()})
    assert same.status_code == 201
    assert same.json()["outcome"] == "matched"
    assert same.json()["company"]["id"] == company["id"]
    assert client.get("/companies?page_size=1").json()["total"] == total_before + 2

    stranger = client.post("/companies", json={"name": _unique("Stranger"), "domain": domain})
    assert stranger.status_code == 409
    assert stranger.json()["detail"]["code"] == "identity_conflict"
    assert stranger.json()["detail"]["field"] == "domain"

    invalid = client.post("/companies", json={"name": _unique("Bad"), "domain": "not a domain"})
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["field"] == "domain"

    renamed_to = _unique("Radar Industries")
    short_name = _unique("Radar")
    updated = client.patch(
        f"/companies/{company['id']}",
        json={
            "name": renamed_to,
            "domain": domain,
            "priority": "normal",
            "radar_status": "paused",
            "aliases": [short_name],
            "expected_version": company["version"],
        },
    )
    assert updated.status_code == 200
    after = updated.json()
    assert after["name"] == renamed_to
    assert after["version"] == company["version"] + 1
    assert after["created_at"] == company["created_at"]
    assert after["status"] == "paused"
    # The old name keeps answering, so the next import still lands here.
    assert {alias["alias"] for alias in after["aliases"]} >= {name, short_name}

    stale = client.patch(
        f"/companies/{company['id']}",
        json={"name": renamed_to, "expected_version": company["version"]},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"

    taken = client.patch(
        f"/companies/{variant.json()['company']['id']}",
        json={
            "name": variant.json()["company"]["name"],
            "domain": domain,
            "expected_version": variant.json()["company"]["version"],
        },
    )
    assert taken.status_code == 409
    assert taken.json()["detail"]["field"] == "domain"


def test_company_source_is_registered_corrected_and_proposed_inertly() -> None:
    client = _client()
    company = client.post("/companies", json={"name": _unique("ATS Owner")}).json()["company"]

    nothing = client.post(f"/companies/{company['id']}/detect-source")
    assert nothing.json()["result"] == "not_detected"

    unsupported = client.post(
        f"/companies/{company['id']}/sources",
        json={
            "source_type": "workday",
            "endpoint": "https://example.wd1.myworkdayjobs.com",
            "external_key": "example",
            "evidence_note": "Seen on the careers page.",
        },
    )
    assert unsupported.status_code == 422
    assert unsupported.json()["detail"]["field"] == "source_type"
    assert "not supported" in unsupported.json()["detail"]["message"]

    no_note = client.post(
        f"/companies/{company['id']}/sources",
        json={
            "source_type": "greenhouse",
            "endpoint": "https://boards.greenhouse.io/wrongkey",
            "external_key": "wrongkey",
            "evidence_note": "   ",
        },
    )
    assert no_note.status_code == 422
    assert no_note.json()["detail"]["field"] == "evidence_note"

    registered = client.post(
        f"/companies/{company['id']}/sources",
        json={
            "source_type": "greenhouse",
            "endpoint": "https://boards.greenhouse.io/wrongkey",
            "external_key": "wrongkey",
            "evidence_note": "Linked from the careers page footer.",
        },
    )
    assert registered.status_code == 201
    source = registered.json()
    assert source["status"] == "ats_identified"
    assert source["verification_method"] == "manual"
    assert source["version"] == 1
    assert len(source["revisions"]) == 1

    corrected = client.patch(
        f"/companies/{company['id']}/sources/{source['id']}",
        json={
            "source_type": "greenhouse",
            "endpoint": "https://boards.greenhouse.io/rightkey",
            "external_key": "rightkey",
            "evidence_note": "The footer link was stale; the board moved to rightkey.",
            "expected_version": source["version"],
        },
    )
    assert corrected.status_code == 200
    after = corrected.json()
    assert after["external_key"] == "rightkey"
    assert after["version"] == 2
    assert [revision["version"] for revision in after["revisions"]] == [1, 2]
    assert after["revisions"][1]["changes"]["external_key"] == {
        "from": "wrongkey",
        "to": "rightkey",
    }

    stale = client.patch(
        f"/companies/{company['id']}/sources/{source['id']}",
        json={
            "source_type": "greenhouse",
            "endpoint": "https://boards.greenhouse.io/other",
            "external_key": "other",
            "evidence_note": "Late edit.",
            "expected_version": source["version"],
        },
    )
    assert stale.status_code == 409

    proposed = client.post(f"/companies/{company['id']}/detect-source")
    assert proposed.json()["result"] == "proposed"
    assert proposed.json()["enabled"] is False
    assert proposed.json()["evidence"] == after["evidence"]
    definition = client.get(f"/sources/{proposed.json()['source_id']}").json()
    assert definition["enabled"] is False
    assert definition["evidence_status"] == "ats_identified"
    assert definition["configuration"]["board_token"] == "rightkey"

    repeated = client.post(f"/companies/{company['id']}/detect-source")
    assert repeated.json()["result"] == "already_proposed"
    assert repeated.json()["source_id"] == proposed.json()["source_id"]
