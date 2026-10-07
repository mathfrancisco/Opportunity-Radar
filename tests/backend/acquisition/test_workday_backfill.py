"""F51-05 AC01 to AC05 (AC06 needs the real pilot): the Workday detail backfill script.

Runs `scripts/workday_detail_backfill.py` against a real `_test` database; HTTP is
`httpx.MockTransport`, no network. The postings are collected and normalized by the real
service first, so the backfill sees real occurrences, raw items and opportunities.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import CollectionMode, CollectionRequest
from opportunity_radar.acquisition.models import (
    HostBudgetStateModel,
    RawItemModel,
    SourceCheckpointModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.acquisition.workday import WorkdayCollector
from opportunity_radar.opportunities.models import (
    NormalizationResultModel,
    OpportunityModel,
    SourceOccurrenceModel,
    SourceOccurrenceObservationModel,
)
from opportunity_radar.opportunities.service import OpportunityService
from opportunity_radar.platform.database import create_database_engine
from scripts import workday_detail_backfill as backfill
from scripts.workday_detail_backfill import BackfillRefused, rollback, run_backfill


def integration(test: Callable[..., None]) -> Callable[..., None]:
    return pytest.mark.integration(
        pytest.mark.skipif(
            os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
            reason="database integration is enabled only in the isolated CI database",
        )(test)
    )

HOST = "acme.wd5.myworkdayjobs.com"
_TARGETS = ("SOFTWARE_ENGINEERING",)
_ENG = "Senior Backend Engineer"


def _path(number: int) -> str:
    return f"/job/Remote/Job-{number}_R{number}"


def _board(engineers: int, *, marketing: int = 0) -> list[dict[str, object]]:
    titles = [_ENG] * engineers + ["Marketing Manager"] * marketing
    return [
        {
            "title": title,
            "externalPath": _path(number),
            "locationsText": "Remote",
            "bulletFields": [f"R{number}"],
        }
        for number, title in enumerate(titles)
    ]


def _approved_configuration(source_id: UUID) -> dict[str, object]:
    return {
        "tenant_identifier": "acme/site",
        "api_region": "wd5",
        "fetch_detail": True,
        "detail_approval": {
            "source_id": str(source_id),
            "owner": "test fixture",
            "hostname": HOST,
            "reviewed_at": datetime.now(UTC).date().isoformat(),
            "terms_reference": "synthetic fixture policy",
            "decision": "approved",
        },
    }


class _Env:
    """One approved Workday source with `postings` collected and normalized, detail off."""

    def __init__(self, engine: Engine, session: Session, postings: list[dict[str, object]]):
        self.engine = engine
        self.session = session
        self.postings = postings
        self.detail_log: list[str] = []
        self.on_detail: Callable[[str], httpx.Response | None] = lambda path: None
        self.source = SourceDefinitionModel(
            id=uuid4(),
            source_type="workday",
            name=f"workday backfill probe {uuid4().hex[:8]}",
            enabled=True,
            configuration={"tenant_identifier": "acme/site", "api_region": "wd5"},
            rate_limit_policy={"max_retries": 0, "minimum_interval_seconds": 0},
        )
        session.add(self.source)
        session.commit()
        self._collect()
        for raw_item in self.raw_items():
            OpportunityService(session).normalize(raw_item.id)
        self.source.configuration = _approved_configuration(self.source.id)
        session.commit()

    def _handler(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = json.loads(request.content)
            offset, limit = body["offset"], body["limit"]
            return httpx.Response(
                200,
                json={
                    "total": len(self.postings) if offset == 0 else 0,
                    "jobPostings": self.postings[offset : offset + limit],
                },
            )
        path = request.url.path.rsplit("/cxs/acme/site", 1)[1]
        self.detail_log.append(path)
        override = self.on_detail(path)
        if override is not None:
            return override
        return httpx.Response(200, json={"jobPostingInfo": {"jobDescription": f"<p>{path}</p>"}})

    def _collect(self) -> None:
        async def no_sleep(delay: float) -> None:
            del delay

        client = httpx.AsyncClient(transport=httpx.MockTransport(self._handler))
        service = AcquisitionService(
            self.session,
            registry=CollectorRegistry((WorkdayCollector(client=client, sleeper=no_sleep),)),
            sleeper=no_sleep,
            target_role_families=lambda: _TARGETS,
        )
        try:
            asyncio.run(
                service.execute(self.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
            )
        finally:
            asyncio.run(client.aclose())

    def run(self, manifest: Path | None = None, **options: Any) -> dict[str, Any]:
        async def no_sleep(delay: float) -> None:
            del delay

        client = httpx.AsyncClient(transport=httpx.MockTransport(self._handler))
        try:
            return run_backfill(
                self.session,
                source_id=self.source.id,
                role_families=_TARGETS,
                manifest_path=manifest,
                collector=WorkdayCollector(client=client, sleeper=no_sleep),
                **options,
            )
        finally:
            asyncio.run(client.aclose())

    def raw_items(self) -> list[RawItemModel]:
        return list(
            self.session.scalars(
                select(RawItemModel)
                .where(RawItemModel.source_definition_id == self.source.id)
                .order_by(RawItemModel.external_id)
            )
        )

    def opportunity(self, number: int) -> OpportunityModel:
        occurrence = self.session.scalar(
            select(SourceOccurrenceModel).where(
                SourceOccurrenceModel.source_definition_id == self.source.id,
                SourceOccurrenceModel.external_id == _path(number),
            )
        )
        assert occurrence is not None
        self.session.refresh(occurrence.opportunity)
        return occurrence.opportunity

    def snapshot(self) -> dict[str, Any]:
        """Everything the card says a backfill must leave alone, plus the description."""
        self.session.expire_all()
        occurrences = self.session.scalars(
            select(SourceOccurrenceModel)
            .where(SourceOccurrenceModel.source_definition_id == self.source.id)
            .order_by(SourceOccurrenceModel.external_id)
        ).all()
        return {
            "occurrences": [
                (
                    o.id,
                    o.external_id,
                    o.opportunity_id,
                    o.raw_item_id,
                    o.first_seen_at,
                    o.last_seen_at,
                    o.last_seen_run_id,
                )
                for o in occurrences
            ],
            "opportunities": [
                (
                    o.opportunity.id,
                    o.opportunity.description,
                    o.opportunity.version,
                    o.opportunity.lifecycle_status,
                    o.opportunity.closure_evidence,
                    o.opportunity.published_at,
                    o.opportunity.source_updated_at,
                    o.opportunity.first_seen_at,
                    o.opportunity.updated_at,
                )
                for o in occurrences
            ],
            "raw_items": [
                (r.id, r.payload_hash, r.item_metadata, r.canonical_url) for r in self.raw_items()
            ],
            "runs": self.session.scalar(
                select(func.count())
                .select_from(SourceRunModel)
                .where(SourceRunModel.source_definition_id == self.source.id)
            ),
        }

    def budget(self) -> HostBudgetStateModel:
        with Session(self.engine) as session:
            row = session.get(HostBudgetStateModel, HOST)
            assert row is not None
            session.expunge(row)
            return row

    def cleanup(self) -> None:
        session = self.session
        session.rollback()
        run_ids = list(
            session.scalars(
                select(SourceRunModel.id).where(
                    SourceRunModel.source_definition_id == self.source.id
                )
            )
        )
        raw_item_ids = [item.id for item in self.raw_items()]
        occurrence_ids = list(
            session.scalars(
                select(SourceOccurrenceModel.id).where(
                    SourceOccurrenceModel.raw_item_id.in_(raw_item_ids)
                )
            )
        )
        opportunity_ids = list(
            session.scalars(
                select(SourceOccurrenceModel.opportunity_id).where(
                    SourceOccurrenceModel.id.in_(occurrence_ids)
                )
            )
        )
        session.execute(
            delete(SourceOccurrenceObservationModel).where(
                SourceOccurrenceObservationModel.raw_item_id.in_(raw_item_ids)
                | SourceOccurrenceObservationModel.source_occurrence_id.in_(occurrence_ids)
            )
        )
        session.execute(
            delete(NormalizationResultModel).where(
                NormalizationResultModel.raw_item_id.in_(raw_item_ids)
            )
        )
        session.execute(
            delete(SourceOccurrenceModel).where(SourceOccurrenceModel.id.in_(occurrence_ids))
        )
        session.execute(delete(OpportunityModel).where(OpportunityModel.id.in_(opportunity_ids)))
        session.execute(
            delete(SourceCheckpointModel).where(
                SourceCheckpointModel.source_definition_id == self.source.id
            )
        )
        session.execute(delete(RawItemModel).where(RawItemModel.id.in_(raw_item_ids)))
        session.execute(delete(SourceRunModel).where(SourceRunModel.id.in_(run_ids)))
        session.execute(
            delete(SourceDefinitionModel).where(SourceDefinitionModel.id == self.source.id)
        )
        session.commit()


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE acquisition.host_budget_state"))
    yield engine
    engine.dispose()


@pytest.fixture
def make_env(engine: Engine) -> Iterator[Callable[[list[dict[str, object]]], _Env]]:
    created: list[_Env] = []
    sessions: list[Session] = []

    def make(postings: list[dict[str, object]]) -> _Env:
        session = Session(engine)
        sessions.append(session)
        env = _Env(engine, session, postings)
        created.append(env)
        return env

    yield make
    for env in created:
        env.cleanup()
    for session in sessions:
        session.close()


def test_workday_backfill_refuses_a_source_not_explicitly_allowed() -> None:
    with pytest.raises(BackfillRefused, match="not found"):
        backfill._require_allowed(None)
    source_id = uuid4()
    approved = _approved_configuration(source_id)

    def source(
        configuration: dict[str, object], source_type: str = "workday"
    ) -> SourceDefinitionModel:
        return SourceDefinitionModel(
            id=source_id, source_type=source_type, name="x", configuration=configuration
        )

    assert backfill._require_allowed(source(approved)) == ("acme", "site", "wd5", 200)
    with pytest.raises(BackfillRefused, match="not workday"):
        backfill._require_allowed(source(approved, "greenhouse"))
    with pytest.raises(BackfillRefused, match="fetch_detail"):
        backfill._require_allowed(source({**approved, "fetch_detail": False}))
    no_approval = {k: v for k, v in approved.items() if k != "detail_approval"}
    with pytest.raises(BackfillRefused, match="approval_missing"):
        backfill._require_allowed(source(no_approval))
    approval = dict(approved["detail_approval"])  # type: ignore[call-overload]
    other_host = {**approved, "detail_approval": {**approval, "hostname": "x.com"}}
    with pytest.raises(BackfillRefused, match="approval_missing"):
        backfill._require_allowed(source(other_host))


@pytest.mark.parametrize("approval", [False, True])
@integration
def test_workday_backfill_does_no_request_for_an_unapproved_source(
    make_env: Callable[[list[dict[str, object]]], _Env], approval: bool
) -> None:
    env = make_env(_board(1))
    if not approval:
        env.source.configuration = {"tenant_identifier": "acme/site", "api_region": "wd5"}
        env.session.commit()
    env.detail_log.clear()
    if approval:
        assert env.run()["mode"] == "dry-run"
    else:
        with pytest.raises(BackfillRefused):
            env.run()
    assert env.detail_log == []


@integration
def test_workday_backfill_dry_run_is_read_only_and_explains_targets(
    make_env: Callable[[list[dict[str, object]]], _Env],
) -> None:
    env = make_env(_board(3, marketing=1))
    env.session.execute(
        update(OpportunityModel)
        .where(OpportunityModel.id == env.opportunity(1).id)
        .values(description="Human written text")
    )
    env.session.commit()
    env.detail_log.clear()
    before, budget_before = env.snapshot(), env.budget()

    report = env.run()

    assert report["mode"] == "dry-run"
    assert env.detail_log == []
    assert env.snapshot() == before
    budget_after = env.budget()
    assert (budget_after.requests_used, budget_after.cooldown_until) == (
        budget_before.requests_used,
        budget_before.cooldown_until,
    )
    reasons = {row["key"]: (row["included"], row["reason"]) for row in report["decisions"]}
    assert reasons == {
        _path(0): (True, "description_missing"),
        _path(1): (False, "description_present"),
        _path(2): (True, "description_missing"),
        _path(3): (False, "role_family_off_target"),
    }
    assert report["postings_seen"] == 4
    assert report["eligible"] == 2
    assert report["excluded"] == {"description_present": 1, "role_family_off_target": 1}


@integration
def test_workday_backfill_resume_is_idempotent(
    make_env: Callable[[list[dict[str, object]]], _Env], tmp_path: Path
) -> None:
    env = make_env(_board(5))
    manifest = tmp_path / "manifest.json"
    env.detail_log.clear()
    versions = [env.opportunity(n).version for n in range(5)]
    occurrences = env.snapshot()["occurrences"]

    first = env.run(manifest, apply=True, max_requests=2)  # interrupted by the run cap

    assert (first["applied"], first["stopped_by"], first["not_attempted"]) == (2, "cap", 2)
    assert env.detail_log == [_path(0), _path(1)]

    second = env.run(manifest, apply=True, max_requests=10)  # resumed from the same manifest
    assert (second["applied"], second["stopped_by"]) == (3, None)
    assert second["excluded"] == {"already_applied": 2}
    assert env.detail_log == [_path(n) for n in range(5)]  # each key fetched exactly once

    third = env.run(manifest, apply=True, max_requests=10)  # a repeat changes nothing
    assert (third["eligible"], third["applied"], third["details_fetched"]) == (0, 0, 0)
    assert env.detail_log == [_path(n) for n in range(5)]

    for number in range(5):
        opportunity = env.opportunity(number)
        assert opportunity.description == f"<p>{_path(number)}</p>"
        assert opportunity.version == versions[number] + 1  # one write per key
    assert env.snapshot()["occurrences"] == occurrences  # nothing duplicated
    entries = json.loads(manifest.read_text(encoding="utf-8"))["entries"]
    assert {key: entry["status"] for key, entry in entries.items()} == {
        _path(n): "applied" for n in range(5)
    }


@integration
def test_workday_backfill_preserves_human_text_and_raw_payload(
    make_env: Callable[[list[dict[str, object]]], _Env], tmp_path: Path
) -> None:
    env = make_env(_board(3))
    human = "Edited by a person after the dry-run\n"
    target = env.opportunity(1)

    def edit_before_fetch(path: str) -> httpx.Response | None:
        if path == _path(1):
            with Session(env.engine) as other:
                other.execute(
                    update(OpportunityModel)
                    .where(OpportunityModel.id == target.id)
                    .values(description=human)
                )
                other.commit()
        return None

    env.on_detail = edit_before_fetch
    raw_before = env.snapshot()["raw_items"]
    manifest = tmp_path / "manifest.json"

    report = env.run(manifest, apply=True)

    assert (report["applied"], report["conflicts"]) == (2, 1)
    assert env.opportunity(1).description == human  # same bytes
    assert env.snapshot()["raw_items"] == raw_before
    entries = json.loads(manifest.read_text(encoding="utf-8"))["entries"]
    assert entries[_path(1)]["status"] == "conflict"
    assert entries[_path(0)]["status"] == entries[_path(2)]["status"] == "applied"


@integration
def test_workday_backfill_backup_restore_round_trip(
    make_env: Callable[[list[dict[str, object]]], _Env], tmp_path: Path
) -> None:
    env = make_env(_board(3))
    manifest = tmp_path / "manifest.json"
    snapshot = env.snapshot()
    env.run(manifest, apply=True)

    # The backup holds the values from before the first write.
    entries = json.loads(manifest.read_text(encoding="utf-8"))["entries"]
    for number in range(3):
        backup = entries[_path(number)]["backup"]
        assert backup["description"] is None
        assert backup["version"] == snapshot["opportunities"][number][2]
        assert backup["raw_payload_hash"] == snapshot["raw_items"][number][1]

    # A person edits one description after the backfill: it is a conflict, never undone.
    edited = env.opportunity(2)
    env.session.execute(
        update(OpportunityModel).where(OpportunityModel.id == edited.id).values(description="Mine")
    )
    env.session.commit()

    preview = rollback(env.session, source_id=env.source.id, manifest_path=manifest)
    assert (preview["restorable"], preview["conflicts"]) == (2, 1)
    assert env.opportunity(0).description is not None  # the preview wrote nothing

    done = rollback(env.session, source_id=env.source.id, manifest_path=manifest, apply=True)
    assert done["restorable"] == 2
    after = env.snapshot()
    assert [row[1] for row in after["opportunities"]] == [None, None, "Mine"]
    assert after["raw_items"] == snapshot["raw_items"]
    assert [row[:4] for row in after["occurrences"]] == [row[:4] for row in snapshot["occurrences"]]
    again = rollback(env.session, source_id=env.source.id, manifest_path=manifest, apply=True)
    assert again["restorable"] == 0


@integration
def test_partial_workday_backfill_never_closes_absences(
    make_env: Callable[[list[dict[str, object]]], _Env], tmp_path: Path
) -> None:
    env = make_env(_board(4))
    manifest = tmp_path / "manifest.json"
    before = env.snapshot()

    # A backfill cut short by a 429 on its second request.
    env.on_detail = lambda path: (
        httpx.Response(429, headers={"Retry-After": "300"}) if path == _path(1) else None
    )
    report = env.run(manifest, apply=True)

    assert report["stopped_by"] == "cooldown"
    assert (report["applied"], report["failed"], report["not_attempted"]) == (1, 1, 2)
    after = env.snapshot()
    # Description and `version` of the written posting aside, nothing else moved: occurrence
    # presence, lifecycle, closure evidence, timestamps (`updated_at` included), the raw items
    # and the number of runs (a backfill is never an inventory).
    assert after["occurrences"] == before["occurrences"]
    assert after["raw_items"] == before["raw_items"]
    assert after["runs"] == before["runs"]
    for old, new in zip(before["opportunities"], after["opportunities"], strict=True):
        assert (old[0], *old[3:]) == (new[0], *new[3:])
    assert [row[1] for row in after["opportunities"]] == [f"<p>{_path(0)}</p>", None, None, None]
    assert env.budget().cooldown_until is not None


@integration
def test_workday_backfill_never_bypasses_host_budget_or_cooldown(
    make_env: Callable[[list[dict[str, object]]], _Env], tmp_path: Path
) -> None:
    env = make_env(_board(3))
    env.detail_log.clear()
    used = env.budget().requests_used
    with Session(env.engine) as session:
        session.execute(
            update(HostBudgetStateModel)
            .where(HostBudgetStateModel.host == HOST)
            .values(requests_ceiling=used + 1)
        )
        session.commit()

    quota = env.run(tmp_path / "quota.json", apply=True)

    assert (quota["applied"], quota["stopped_by"]) == (1, "quota")
    assert env.detail_log == [_path(0)]  # the second request was denied before any transport
    assert env.budget().requests_used == used + 1

    with Session(env.engine) as session:
        session.execute(
            update(HostBudgetStateModel)
            .where(HostBudgetStateModel.host == HOST)
            .values(requests_ceiling=500, cooldown_until=datetime(2999, 1, 1, tzinfo=UTC))
        )
        session.commit()
    cooldown = env.run(tmp_path / "cooldown.json", apply=True)

    assert (cooldown["applied"], cooldown["stopped_by"]) == (0, "cooldown")
    assert env.detail_log == [_path(0)]
