"""Database-backed proof that an existing source can be linked to its company source."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import (
    SourceCheckpointModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.presentation.http.app import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

_HOSTS = {"ashby": "jobs.ashbyhq.com", "greenhouse": "boards.greenhouse.io"}
_IDENTIFIERS = {"ashby": "board_identifier", "greenhouse": "board_token"}


def _client() -> TestClient:
    return TestClient(create_app(Settings(database_url=os.environ["DATABASE_URL"])))


def _unique(prefix: str) -> str:
    return f"{prefix} {uuid4().hex[:8]}"


def _company_source(client: TestClient, key: str, source_type: str = "ashby") -> dict:
    company = client.post("/companies", json={"name": _unique("Link Owner")}).json()["company"]
    created = client.post(
        f"/companies/{company['id']}/sources",
        json={
            "source_type": source_type,
            "endpoint": f"https://{_HOSTS[source_type]}/{key}",
            "external_key": key,
            "evidence_note": "Linked from the careers page.",
        },
    )
    assert created.status_code == 201
    return created.json()


def _source(client: TestClient, key: str, source_type: str = "ashby", **extra: object) -> dict:
    created = client.post(
        "/sources",
        json={
            "source_type": source_type,
            "name": _unique("Proposed link"),
            "configuration": {_IDENTIFIERS[source_type]: key, "company_name": "Whoever"},
            **extra,
        },
    )
    assert created.status_code == 201
    assert created.json()["company_source_id"] is None
    return created.json()


def _link(client: TestClient, source: dict, record: dict, version: int | None = None):
    return client.patch(
        f"/sources/{source['id']}/company-source",
        json={
            "company_source_id": record["id"],
            "expected_version": version or source["version"],
        },
    )


def _linked_to(client: TestClient, source: dict) -> str | None:
    return client.get(f"/sources/{source['id']}").json()["company_source_id"]


def test_link_sets_company_source_id_and_bumps_the_version_only() -> None:
    client = _client()
    key = f"Link{uuid4().hex[:8]}"
    record = _company_source(client, key)
    source = _source(client, key)

    linked = _link(client, source, record)

    assert linked.status_code == 200
    body = linked.json()
    assert body["company_source_id"] == record["id"]
    assert body["version"] == source["version"] + 1
    for field in ("configuration", "schedule", "enabled", "priority", "evidence_status"):
        assert body[field] == source[field]


def test_an_enabled_source_keeps_enabled_schedule_checkpoint_and_runs() -> None:
    client = _client()
    key = f"Live{uuid4().hex[:8]}"
    record = _company_source(client, key)
    source = _source(client, key, schedule="0 */4 * * *", evidence_status="confirmed")
    enabled = client.patch(
        f"/sources/{source['id']}",
        json={
            "enabled": True,
            "terms_reviewed": True,
            "collector_local_tested": True,
            "reviewed_at": "2026-10-05T12:00:00Z",
            "expected_version": source["version"],
        },
    )
    assert enabled.status_code == 200
    source = enabled.json()
    source_id = UUID(source["id"])
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        run = SourceRunModel(
            source_definition_id=source_id,
            status="SUCCEEDED",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            items_seen=3,
        )
        session.add(run)
        session.flush()
        session.add(
            SourceCheckpointModel(
                source_definition_id=source_id, cursor="cursor-1", promoted_by_run_id=run.id
            )
        )
        session.commit()

    linked = _link(client, source, record)

    assert linked.status_code == 200
    body = linked.json()
    assert body["enabled"] is True
    assert body["schedule"] == "0 */4 * * *"
    assert body["terms_reviewed"] is True and body["collector_local_tested"] is True
    assert body["reviewed_at"] == source["reviewed_at"]
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        runs = session.scalars(
            select(SourceRunModel).where(SourceRunModel.source_definition_id == source_id)
        ).all()
        checkpoint = session.get(SourceCheckpointModel, source_id)
        assert [(r.status, r.items_seen) for r in runs] == [("SUCCEEDED", 3)]
        assert checkpoint is not None and checkpoint.cursor == "cursor-1"


def test_stale_expected_version_is_a_conflict_and_nothing_changes() -> None:
    client = _client()
    key = f"Stale{uuid4().hex[:8]}"
    record = _company_source(client, key)
    source = _source(client, key)

    stale = _link(client, source, record, version=source["version"] + 5)

    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"
    assert _linked_to(client, source) is None


def test_unknown_source_is_404_and_unknown_company_source_is_422() -> None:
    client = _client()
    key = f"Miss{uuid4().hex[:8]}"
    record = _company_source(client, key)
    source = _source(client, key)

    missing_source = client.patch(
        f"/sources/{uuid4()}/company-source",
        json={"company_source_id": record["id"], "expected_version": 1},
    )
    missing_record = client.patch(
        f"/sources/{source['id']}/company-source",
        json={"company_source_id": str(uuid4()), "expected_version": source["version"]},
    )

    assert missing_source.status_code == 404
    assert missing_record.status_code == 422
    assert missing_record.json()["detail"]["field"] == "company_source_id"


def test_company_source_of_another_type_is_refused() -> None:
    client = _client()
    key = f"Type{uuid4().hex[:8]}"
    record = _company_source(client, key, source_type="greenhouse")
    source = _source(client, key, source_type="ashby")

    refused = _link(client, source, record)

    assert refused.status_code == 422
    assert refused.json()["detail"]["field"] == "company_source_id"
    assert _linked_to(client, source) is None


def test_company_source_with_a_different_key_is_refused_including_case() -> None:
    client = _client()
    key = f"Case{uuid4().hex[:8]}"
    different = _company_source(client, f"other{uuid4().hex[:8]}")
    lowercase = _company_source(client, key.lower())
    source = _source(client, key)

    assert _link(client, source, different).status_code == 422
    assert _link(client, source, lowercase).status_code == 422
    assert _linked_to(client, source) is None


def test_a_source_already_linked_elsewhere_is_a_409() -> None:
    client = _client()
    key = f"Twice{uuid4().hex[:8]}"
    record = _company_source(client, key)
    source = _source(client, key)
    first = _link(client, source, record)
    assert first.status_code == 200
    current = first.json()

    again = _link(client, current, record)
    elsewhere = _link(client, current, _company_source(client, key + "x"))

    assert again.status_code == 200  # the same link again is a no-op
    assert again.json()["version"] == current["version"]
    assert elsewhere.status_code == 409
    assert elsewhere.json()["detail"]["code"] == "source_already_linked"
    assert _linked_to(client, source) == record["id"]


def test_a_company_source_already_read_by_another_source_is_a_409() -> None:
    client = _client()
    key = f"Dup{uuid4().hex[:8]}"
    record = _company_source(client, key)
    first = _source(client, key)
    second = _source(client, key)
    assert _link(client, first, record).status_code == 200

    refused = _link(client, second, record)

    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "company_source_already_linked"
    assert _linked_to(client, second) is None


def test_the_link_is_persisted_on_the_source_row() -> None:
    client = _client()
    key = f"Rows{uuid4().hex[:8]}"
    record = _company_source(client, key)
    source = _source(client, key)
    assert _link(client, source, record).status_code == 200
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        row = session.get(SourceDefinitionModel, UUID(source["id"]))
        assert row is not None
        assert str(row.company_source_id) == record["id"]
        assert row.version == source["version"] + 1
