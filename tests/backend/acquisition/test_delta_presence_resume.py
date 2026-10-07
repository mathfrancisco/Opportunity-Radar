"""F20-39: revisiting confirms presence without duplicating content or inference, and a
partial collection (a bare 304, a crash, an out-of-order replay) never proves an
opportunity closed.

Runs `AcquisitionService.execute` against a real database (like
`tests/backend/opportunities/test_run_closures.py`), because the acceptance criteria are
about what the same source's *successive* runs commit together — evidence, presence
observation and checkpoint — not about one call's return value in isolation.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectedItem,
    CollectionMode,
    CollectionRequest,
    CollectorCapabilities,
    HealthResult,
)
from opportunity_radar.acquisition.inventory_contract import inventory_scope_hash
from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceCheckpointModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.acquisition.repository import AcquisitionRepository
from opportunity_radar.acquisition.scheduling import ConditionalRequestHeaders
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.opportunities.models import (
    NormalizationResultModel,
    OpportunityModel,
    SourceOccurrenceModel,
    SourceOccurrenceObservationModel,
)
from opportunity_radar.opportunities.service import OpportunityService
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


class _StaticCollector:
    """Yields a fixed, precomputed sequence of items, once per `discover` call."""

    capabilities = CollectorCapabilities(incremental_cursor=True, etag=True, last_modified=True)

    def __init__(self, source_type: str, batches: list[list[CollectedItem]]) -> None:
        self.source_type = source_type
        self._batches = list(batches)
        self.calls = 0

    async def healthcheck(self, context: object = None) -> HealthResult:
        del context
        return HealthResult(healthy=True)

    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        del request
        batch = self._batches[min(self.calls, len(self._batches) - 1)]
        self.calls += 1
        for item in batch:
            yield item


class _ConditionalCollector:
    """Revalidates against a fake board via `httpx.MockTransport`, like a real ATS
    collector honouring `conditional_headers` (F20-38)."""

    capabilities = CollectorCapabilities(incremental_cursor=True, etag=True, last_modified=True)

    def __init__(self, source_type: str, transport: httpx.MockTransport) -> None:
        self.source_type = source_type
        self._transport = transport

    async def healthcheck(self, context: object = None) -> HealthResult:
        del context
        return HealthResult(healthy=True)

    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        headers = (
            request.conditional_headers.as_headers()
            if request.conditional_headers is not None
            else {}
        )
        async with httpx.AsyncClient(transport=self._transport) as client:
            response = await client.get("https://example.test/jobs", headers=headers)
        request.telemetry.record_http_attempt()
        if response.status_code == 304:
            request.telemetry.record_conditional_response(not_modified=True)
            return
        request.telemetry.record_conditional_response(
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
        )
        for job in response.json()["jobs"]:
            yield CollectedItem(
                source_type=self.source_type,
                external_id=job["id"],
                title=job["title"],
                raw_payload=job,
                cursor=job["id"],
            )


class _ManifestConditionalCollector:
    """Revalidates a fixed number of declared representations (F20-39 manifest).

    Each entry of `pages` is `True` for a representation that comes back 304, `False`
    for one that comes back with a new item. `manifest_size` lets a test declare more
    representations than actually get revalidated in the run, to model a manifest whose
    pagination stopped early.
    """

    capabilities = CollectorCapabilities(incremental_cursor=True, etag=True, last_modified=True)

    def __init__(
        self, source_type: str, pages: list[bool], *, manifest_size: int | None = None
    ) -> None:
        self.source_type = source_type
        self._pages = pages
        self._manifest_size = manifest_size if manifest_size is not None else len(pages)

    async def healthcheck(self, context: object = None) -> HealthResult:
        del context
        return HealthResult(healthy=True)

    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        request.telemetry.record_manifest(self._manifest_size)
        for index, revalidated in enumerate(self._pages):
            request.telemetry.record_http_attempt()
            if revalidated:
                request.telemetry.record_conditional_response(not_modified=True)
                continue
            request.telemetry.record_conditional_response(etag=f'"page-{index}"')
            yield CollectedItem(
                source_type=self.source_type,
                external_id=f"job-new-{index}",
                title="New Role",
                raw_payload={"id": f"job-new-{index}"},
                cursor=f"job-new-{index}",
            )


class _FailingAfterOneItemCollector:
    """Yields one item, then raises — a run that persists a real prefix before stopping
    short (`PARTIAL`), leaving something F20-39's explicit resume can point back at."""

    capabilities = CollectorCapabilities(incremental_cursor=True, etag=True, last_modified=True)

    def __init__(self, source_type: str, item: CollectedItem) -> None:
        self.source_type = source_type
        self._item = item

    async def healthcheck(self, context: object = None) -> HealthResult:
        del context
        return HealthResult(healthy=True)

    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        del request
        yield self._item
        raise AcquisitionError(AcquisitionErrorCode.INVALID_ITEM, "boom")


class _CrashingSession:
    """Wraps a real `Session` and raises once on `commit`, to simulate a crash between
    the last write and the durable commit — the transaction rolls back exactly as it
    would if the process had died at that point."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self.crash_on_next_commit = False

    def commit(self) -> None:
        if self.crash_on_next_commit:
            self.crash_on_next_commit = False
            self._session.rollback()
            raise RuntimeError("simulated crash before commit")
        self._session.commit()

    def __getattr__(self, name: str) -> object:
        return getattr(self._session, name)


def _engine():
    return create_database_engine(os.environ["DATABASE_URL"])


class _Fixture:
    def __init__(self, session: Session, source_type: str | None = None) -> None:
        self.session = session
        self.source_type = source_type or f"delta_probe_{uuid4().hex[:8]}"
        self.source = SourceDefinitionModel(
            id=uuid4(),
            source_type=self.source_type,
            name=f"delta probe {uuid4().hex[:8]}",
            enabled=True,
            configuration={},
            rate_limit_policy={},
        )
        session.add(self.source)
        session.commit()

    def service(self, collector: object, *, session: object | None = None) -> AcquisitionService:
        use_session = session or self.session
        return AcquisitionService(
            use_session,  # type: ignore[arg-type]
            registry=CollectorRegistry((collector,)),  # type: ignore[arg-type]
            repository=AcquisitionRepository(use_session),  # type: ignore[arg-type]
        )

    def raw_items(self) -> list[RawItemModel]:
        return list(
            self.session.scalars(
                select(RawItemModel)
                .where(RawItemModel.source_definition_id == self.source.id)
                .order_by(RawItemModel.fetched_at)
            )
        )

    def occurrence_for(self, raw_item_id: UUID) -> SourceOccurrenceModel | None:
        return self.session.scalar(
            select(SourceOccurrenceModel).where(SourceOccurrenceModel.raw_item_id == raw_item_id)
        )

    def cleanup(self) -> None:
        self.session.rollback()
        run_ids = list(
            self.session.scalars(
                select(SourceRunModel.id).where(
                    SourceRunModel.source_definition_id == self.source.id
                )
            )
        )
        raw_item_ids = list(
            self.session.scalars(
                select(RawItemModel.id).where(RawItemModel.source_definition_id == self.source.id)
            )
        )
        occurrence_ids = list(
            self.session.scalars(
                select(SourceOccurrenceModel.id).where(
                    SourceOccurrenceModel.raw_item_id.in_(raw_item_ids)
                )
            )
        )
        opportunity_ids = list(
            self.session.scalars(
                select(SourceOccurrenceModel.opportunity_id).where(
                    SourceOccurrenceModel.id.in_(occurrence_ids)
                )
            )
        )
        self.session.execute(
            delete(SourceOccurrenceObservationModel).where(
                # `source_occurrence_id` alone misses observations recorded before an
                # occurrence exists (F20-39's before-normalization revisit) — those still
                # point at one of this fixture's raw items and must not leak into another
                # test's unfiltered query of the same table.
                SourceOccurrenceObservationModel.raw_item_id.in_(raw_item_ids)
                | SourceOccurrenceObservationModel.source_occurrence_id.in_(occurrence_ids)
            )
        )
        self.session.execute(
            delete(NormalizationResultModel).where(
                NormalizationResultModel.raw_item_id.in_(raw_item_ids)
            )
        )
        self.session.execute(
            delete(SourceOccurrenceModel).where(SourceOccurrenceModel.id.in_(occurrence_ids))
        )
        self.session.execute(
            delete(OpportunityModel).where(OpportunityModel.id.in_(opportunity_ids))
        )
        self.session.execute(
            delete(SourceCheckpointModel).where(
                SourceCheckpointModel.source_definition_id == self.source.id
            )
        )
        self.session.execute(delete(RawItemModel).where(RawItemModel.id.in_(raw_item_ids)))
        self.session.execute(delete(SourceRunModel).where(SourceRunModel.id.in_(run_ids)))
        self.session.execute(
            delete(SourceDefinitionModel).where(SourceDefinitionModel.id == self.source.id)
        )
        self.session.commit()


def _item(source_type: str, *, external_id: str, title: str, **extra: object) -> CollectedItem:
    payload = {"id": external_id, "title": title, **extra}
    return CollectedItem(
        source_type=source_type,
        external_id=external_id,
        title=title,
        raw_payload=payload,
        cursor=external_id,
    )


def test_two_identical_visits_update_presence_without_duplicate_content_or_ai() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        item = _item(fixture.source_type, external_id="job-1", title="Backend Engineer")
        collector = _StaticCollector(fixture.source_type, [[item], [item]])
        service = fixture.service(collector)
        opp_service = OpportunityService(session)
        try:
            first_run = __import__("asyncio").run(
                service.execute(fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
            )
            assert first_run.items_persisted == 1
            [raw_item] = fixture.raw_items()
            opp_service.normalize(raw_item.id)

            occurrence = fixture.occurrence_for(raw_item.id)
            assert occurrence is not None
            first_last_seen = occurrence.last_seen_at

            second_run = __import__("asyncio").run(
                service.execute(fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
            )

            # Presence updated, no new evidence and no re-inference triggered.
            assert second_run.items_persisted == 0
            assert second_run.items_skipped == 1
            assert len(fixture.raw_items()) == 1

            session.refresh(occurrence)
            assert occurrence.last_seen_at > first_last_seen
            assert occurrence.last_seen_run_id == second_run.id

            observations = list(
                session.scalars(
                    select(SourceOccurrenceObservationModel).where(
                        SourceOccurrenceObservationModel.source_occurrence_id == occurrence.id
                    )
                )
            )
            assert len(observations) == 2
            assert {observation.source_run_id for observation in observations} == {
                first_run.id,
                second_run.id,
            }
            assert {observation.raw_item_id for observation in observations} == {raw_item.id}
            assert {observation.content_hash_matched for observation in observations} == {
                False,
                True,
            }
        finally:
            fixture.cleanup()


def test_304_does_not_close_job_or_mask_incomplete_inventory() -> None:
    import asyncio

    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)

        def handler_factory(etag: str):
            def handler(request: httpx.Request) -> httpx.Response:
                if request.headers.get("If-None-Match") == f'"{etag}"':
                    return httpx.Response(304, headers={"ETag": f'"{etag}"'})
                return httpx.Response(
                    200,
                    headers={"ETag": f'"{etag}"'},
                    json={"jobs": [{"id": "job-1", "title": "Backend Engineer"}]},
                )

            return handler

        try:
            # First run: full, unconditional read of a single-page board.
            collector = _ConditionalCollector(
                fixture.source_type, httpx.MockTransport(handler_factory("v1"))
            )
            first_run = asyncio.run(
                fixture.service(collector).execute(
                    fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
                )
            )
            assert first_run.status == "SUCCEEDED"
            assert first_run.complete is True

            # A bare 304 has no manifest proving every representation in this run was
            # revalidated. It must remain incomplete even after a prior complete read.
            collector = _ConditionalCollector(
                fixture.source_type, httpx.MockTransport(handler_factory("v1"))
            )
            second_run = asyncio.run(
                fixture.service(collector).execute(
                    fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
                )
            )
            assert second_run.items_persisted == 0
            assert second_run.complete is False

            # A job later reappearing must not look impossible: the occurrence itself was
            # never touched by the 304 alone, only the run's own completeness flag was.
            session.commit()
        finally:
            fixture.cleanup()


def test_304_without_a_prior_complete_run_stays_incomplete() -> None:
    """A source whose board has never been read in full cannot have a 304 manufacture
    that completeness — it stays parcial/desconhecido (SPEC 39 §7)."""
    import asyncio

    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        source = SourceDefinitionModel(
            id=uuid4(),
            source_type=fixture.source_type,
            name=f"never-complete {uuid4().hex[:8]}",
            enabled=True,
            configuration={},
            rate_limit_policy={},
        )
        session.add(
            SourceCheckpointModel(
                source_definition_id=source.id,
                checkpoint_type="cursor",
                etag='"v1"',
            )
        )
        session.add(source)
        session.commit()

        def handler(request: httpx.Request) -> httpx.Response:
            del request
            return httpx.Response(304, headers={"ETag": '"v1"'})

        try:
            collector = _ConditionalCollector(fixture.source_type, httpx.MockTransport(handler))
            run = asyncio.run(
                AcquisitionService(
                    session,
                    registry=CollectorRegistry((collector,)),
                    repository=AcquisitionRepository(session),
                ).execute(source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
            )
            assert run.complete is False
        finally:
            session.execute(
                delete(SourceRunModel).where(SourceRunModel.source_definition_id == source.id)
            )
            session.execute(
                delete(SourceCheckpointModel).where(
                    SourceCheckpointModel.source_definition_id == source.id
                )
            )
            session.execute(
                delete(SourceDefinitionModel).where(SourceDefinitionModel.id == source.id)
            )
            session.commit()
            fixture.cleanup()


def test_crash_before_commit_leaves_no_partial_state_and_retry_succeeds() -> None:
    import asyncio

    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        crashing = _CrashingSession(session)
        item = _item(fixture.source_type, external_id="job-1", title="Backend Engineer")
        try:
            collector = _StaticCollector(fixture.source_type, [[item]])
            service = fixture.service(collector, session=crashing)
            crashing.crash_on_next_commit = True
            with pytest.raises(RuntimeError):
                asyncio.run(
                    service.execute(
                        fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
                    )
                )

            # Nothing from the crashed attempt survived: evidence, run and checkpoint are
            # one transaction (acceptance criterion 3).
            assert fixture.raw_items() == []
            assert (
                session.scalar(
                    select(func.count(SourceRunModel.id)).where(
                        SourceRunModel.source_definition_id == fixture.source.id
                    )
                )
                == 0
            )

            # A fresh attempt behaves exactly like a first attempt, not a resumed one.
            retry_collector = _StaticCollector(fixture.source_type, [[item]])
            retry_run = asyncio.run(
                fixture.service(retry_collector).execute(
                    fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
                )
            )
            assert retry_run.status == "SUCCEEDED"
            assert retry_run.items_persisted == 1
            assert len(fixture.raw_items()) == 1
        finally:
            fixture.cleanup()


def test_crash_after_commit_then_retry_is_idempotent() -> None:
    import asyncio

    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        item = _item(fixture.source_type, external_id="job-1", title="Backend Engineer")
        try:
            first_run = asyncio.run(
                fixture.service(_StaticCollector(fixture.source_type, [[item]])).execute(
                    fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
                )
            )
            assert first_run.items_persisted == 1

            # The worker "crashed" right after this commit and got retried: the next
            # attempt sees the same content again, exactly like an ordinary revisit.
            retry_run = asyncio.run(
                fixture.service(_StaticCollector(fixture.source_type, [[item]])).execute(
                    fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
                )
            )
            assert retry_run.items_persisted == 0
            assert retry_run.items_skipped == 1
            assert len(fixture.raw_items()) == 1
        finally:
            fixture.cleanup()


def test_material_change_reprocesses_cosmetic_does_not() -> None:
    import asyncio

    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        opp_service = OpportunityService(session)
        try:
            original = _item(
                fixture.source_type,
                external_id="job-1",
                title="Backend Engineer",
                description="Build things.  Ship things.",
            )
            asyncio.run(
                fixture.service(_StaticCollector(fixture.source_type, [[original]])).execute(
                    fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
                )
            )
            [raw_item_1] = fixture.raw_items()
            result1 = opp_service.normalize(raw_item_1.id)
            assert result1.identity_decision == "NEW"
            opportunity_id = result1.opportunity_id

            # Cosmetic-only republish: whitespace differs, semantic content does not.
            cosmetic = _item(
                fixture.source_type,
                external_id="job-1",
                title="Backend Engineer",
                description="Build things. Ship things.",
            )
            asyncio.run(
                fixture.service(_StaticCollector(fixture.source_type, [[cosmetic]])).execute(
                    fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
                )
            )
            raw_items = fixture.raw_items()
            assert len(raw_items) == 2
            raw_item_2 = raw_items[1]
            assert raw_item_1.semantic_hash == raw_item_2.semantic_hash
            assert raw_item_1.payload_hash != raw_item_2.payload_hash

            result2 = opp_service.normalize(raw_item_2.id)
            assert result2.identity_decision == "REFRESHED"
            assert result2.opportunity_id == opportunity_id
            assert any(
                reason.get("code") == "COSMETIC_CHANGE_SEMANTIC_HASH_UNCHANGED"
                for reason in result2.reasons
            )
            opportunity_count_after_cosmetic = session.scalar(
                select(func.count(OpportunityModel.id)).where(OpportunityModel.id == opportunity_id)
            )
            assert opportunity_count_after_cosmetic == 1

            # Material change: the title itself changes.
            material = _item(
                fixture.source_type,
                external_id="job-1",
                title="Senior Backend Engineer",
                description="Build things. Ship things.",
            )
            asyncio.run(
                fixture.service(_StaticCollector(fixture.source_type, [[material]])).execute(
                    fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
                )
            )
            raw_item_3 = fixture.raw_items()[2]
            assert raw_item_3.semantic_hash != raw_item_2.semantic_hash

            result3 = opp_service.normalize(raw_item_3.id)
            assert not any(
                reason.get("code") == "COSMETIC_CHANGE_SEMANTIC_HASH_UNCHANGED"
                for reason in result3.reasons
            )
        finally:
            fixture.cleanup()


def test_out_of_order_replay_does_not_regress_last_seen() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        repository = AcquisitionRepository(session)
        try:
            item = _item(fixture.source_type, external_id="job-1", title="Backend Engineer")
            run_early = SourceRunModel(
                id=uuid4(),
                source_definition_id=fixture.source.id,
                execution_trigger="SCHEDULED",
                status="SUCCEEDED",
                started_at=datetime.now(UTC) - timedelta(hours=2),
                finished_at=datetime.now(UTC) - timedelta(hours=2),
            )
            run_late = SourceRunModel(
                id=uuid4(),
                source_definition_id=fixture.source.id,
                execution_trigger="SCHEDULED",
                status="SUCCEEDED",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            )
            session.add_all([run_early, run_late])
            session.commit()

            raw_item = RawItemModel(
                id=uuid4(),
                source_run_id=run_late.id,
                source_definition_id=fixture.source.id,
                external_id=item.external_id,
                identity_key=f"external:{item.external_id}",
                payload_hash=uuid4().hex + uuid4().hex,
                semantic_hash=uuid4().hex,
                semantic_hash_version="semantic-hash-v1",
                item_metadata={},
            )
            session.add(raw_item)
            session.flush()

            opportunity = OpportunityModel(
                id=uuid4(),
                fingerprint=uuid4().hex + uuid4().hex,
                fingerprint_version="v1",
                canonical_title="Backend Engineer",
                normalized_title="backend engineer",
                work_mode="UNKNOWN",
                seniority="UNKNOWN",
                contract_type="UNKNOWN",
                lifecycle_status="ACTIVE",
                version=1,
            )
            session.add(opportunity)
            session.flush()

            occurrence = SourceOccurrenceModel(
                id=uuid4(),
                opportunity_id=opportunity.id,
                raw_item_id=raw_item.id,
                source_definition_id=fixture.source.id,
                external_id=raw_item.external_id,
                first_seen_at=run_late.started_at,
                last_seen_at=run_late.started_at,
                last_seen_run_id=run_late.id,
            )
            session.add(occurrence)
            session.commit()

            # A replay of the *older* run confirming the same evidence must not move
            # presence backwards, even though it is a legitimate observation.
            repository.record_presence_observation(
                raw_item=raw_item,
                source_run_id=run_early.id,
                observed_at=run_early.started_at,
                content_hash_matched=True,
            )
            session.commit()
            session.refresh(occurrence)

            assert occurrence.last_seen_at == run_late.started_at
            assert occurrence.last_seen_run_id == run_late.id

            observations = list(
                session.scalars(
                    select(SourceOccurrenceObservationModel).where(
                        SourceOccurrenceObservationModel.source_occurrence_id == occurrence.id
                    )
                )
            )
            assert len(observations) == 1
            assert observations[0].source_run_id == run_early.id
        finally:
            fixture.cleanup()


def test_explicit_cursor_suffix_never_claims_a_complete_inventory() -> None:
    import asyncio

    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            item = _item(fixture.source_type, external_id="job-1", title="Backend Engineer")
            run = asyncio.run(
                fixture.service(_StaticCollector(fixture.source_type, [[item]])).execute(
                    fixture.source.id,
                    CollectionRequest(mode=CollectionMode.DISCOVERY, cursor="page-2"),
                )
            )
            assert run.status == "SUCCEEDED"
            assert run.complete is False
        finally:
            fixture.cleanup()


def test_revisits_before_normalization_keep_per_run_observations() -> None:
    import asyncio

    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            item = _item(fixture.source_type, external_id="job-1", title="Backend Engineer")
            service = fixture.service(_StaticCollector(fixture.source_type, [[item], [item]]))
            first_run = asyncio.run(
                service.execute(fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
            )
            second_run = asyncio.run(
                service.execute(fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
            )
            # Scoped to this fixture's two runs: the table is shared with every other test
            # in the suite, so an unfiltered select here would fail on whatever another
            # test (in whatever order it happened to run) left behind or added concurrently.
            observations = list(
                session.scalars(
                    select(SourceOccurrenceObservationModel).where(
                        SourceOccurrenceObservationModel.source_run_id.in_(
                            (first_run.id, second_run.id)
                        )
                    )
                )
            )
            assert {observation.source_run_id for observation in observations} == {
                first_run.id,
                second_run.id,
            }
            assert all(observation.source_occurrence_id is None for observation in observations)
        finally:
            fixture.cleanup()


def test_source_deadline_commits_positive_prefix_without_closing_absent_occurrence() -> None:
    """A timed-out DB-backed run keeps its positive observation but cannot prove absence."""
    import asyncio

    class _StalledAfterPrefixCollector(_StaticCollector):
        async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
            del request
            yield _item(
                fixture.source_type,
                external_id="deadline-present",
                title="Still listed",
            )
            await asyncio.Event().wait()

    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        opportunities = OpportunityService(session)
        try:
            present = _item(
                fixture.source_type, external_id="deadline-present", title="Still listed"
            )
            absent = _item(
                fixture.source_type, external_id="deadline-absent", title="Not listed"
            )
            first = asyncio.run(
                fixture.service(_StaticCollector(fixture.source_type, [[present, absent]])).execute(
                    fixture.source.id,
                    CollectionRequest(mode=CollectionMode.DISCOVERY),
                )
            )
            assert first.complete is True
            for raw_item in fixture.raw_items():
                opportunities.normalize(raw_item.id)
            absent_raw = next(
                item for item in fixture.raw_items() if item.external_id == "deadline-absent"
            )
            absent_occurrence = fixture.occurrence_for(absent_raw.id)
            assert absent_occurrence is not None

            second = asyncio.run(
                fixture.service(_StaticCollector(fixture.source_type, [[present]])).execute(
                    fixture.source.id,
                    CollectionRequest(mode=CollectionMode.DISCOVERY),
                )
            )
            assert second.complete is True
            opportunities.reconcile_run_closures(second.id)

            partial = asyncio.run(
                fixture.service(_StalledAfterPrefixCollector(fixture.source_type, [])).execute(
                    fixture.source.id,
                    CollectionRequest(mode=CollectionMode.DISCOVERY),
                    deadline_seconds=0.05,
                )
            )
            assert partial.status == "PARTIAL"
            assert partial.complete is False
            refreshed_present = fixture.occurrence_for(
                next(
                    item.id
                    for item in fixture.raw_items()
                    if item.external_id == "deadline-present"
                )
            )
            assert refreshed_present is not None
            assert refreshed_present.last_seen_run_id == partial.id

            opportunities.reconcile_run_closures(partial.id)
            session.refresh(absent_occurrence)
            assert absent_occurrence.opportunity.lifecycle_status != "CLOSED"
            assert absent_occurrence.opportunity.closure_evidence is None
        finally:
            fixture.cleanup()


def test_manifest_fully_revalidated_304_reuses_prior_complete_inventory() -> None:
    """Every declared representation revalidating 304, after a prior complete read,
    is the one thing SPEC 39 §7 lets a 304 reuse (F20-39 manifest check)."""
    import asyncio

    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            item = _item(fixture.source_type, external_id="job-1", title="Backend Engineer")
            first_run = asyncio.run(
                fixture.service(_StaticCollector(fixture.source_type, [[item]])).execute(
                    fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
                )
            )
            assert first_run.complete is True

            collector = _ManifestConditionalCollector(fixture.source_type, [True, True])
            second_run = asyncio.run(
                fixture.service(collector).execute(
                    fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
                )
            )
            assert second_run.items_persisted == 0
            assert second_run.status == "SUCCEEDED"
            assert second_run.complete is True
        finally:
            fixture.cleanup()


def test_manifest_partially_revalidated_304_stays_incomplete() -> None:
    """A manifest that declares more representations than this run actually revalidated
    must not be read as coverage of the whole board (F20-39 manifest check)."""
    import asyncio

    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            item = _item(fixture.source_type, external_id="job-1", title="Backend Engineer")
            first_run = asyncio.run(
                fixture.service(_StaticCollector(fixture.source_type, [[item]])).execute(
                    fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
                )
            )
            assert first_run.complete is True

            # Declares 2 representations but this run only revalidated 1 before stopping.
            collector = _ManifestConditionalCollector(
                fixture.source_type, [True], manifest_size=2
            )
            second_run = asyncio.run(
                fixture.service(collector).execute(
                    fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
                )
            )
            assert second_run.complete is False
        finally:
            fixture.cleanup()


def test_manifest_revalidation_without_a_prior_complete_run_stays_incomplete() -> None:
    """A fully-revalidated manifest still cannot manufacture completeness the board
    never had (F20-39 manifest check requires a prior complete run to reuse)."""
    import asyncio

    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            collector = _ManifestConditionalCollector(fixture.source_type, [True, True])
            run = asyncio.run(
                fixture.service(collector).execute(
                    fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
                )
            )
            assert run.complete is False
        finally:
            fixture.cleanup()


def test_resume_of_run_links_the_new_run_to_its_persisted_prefix() -> None:
    """An explicit resume names the interrupted run it continues; the prefix it already
    persisted is not duplicated (F20-39 "retomada da mesma execução")."""
    import asyncio

    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            first_item = _item(fixture.source_type, external_id="job-1", title="Backend Engineer")
            interrupted = asyncio.run(
                fixture.service(_FailingAfterOneItemCollector(fixture.source_type, first_item))
                .execute(fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
            )
            assert interrupted.status == "PARTIAL"
            assert interrupted.items_persisted == 1

            second_item = _item(fixture.source_type, external_id="job-2", title="Data Engineer")
            resumed = asyncio.run(
                fixture.service(_StaticCollector(fixture.source_type, [[first_item, second_item]]))
                .execute(
                    fixture.source.id,
                    CollectionRequest(
                        mode=CollectionMode.DISCOVERY,
                        cursor="job-1",
                        resume_of_run_id=interrupted.id,
                    ),
                )
            )
            assert resumed.resumed_from_run_id == interrupted.id
            # The prefix already committed by `interrupted` dedupes; only the genuinely new
            # item from this attempt is persisted.
            assert resumed.items_persisted == 1
            assert resumed.items_skipped == 1
            assert len(fixture.raw_items()) == 2
        finally:
            fixture.cleanup()


def test_resume_of_run_rejects_a_run_that_is_not_a_resumable_prefix() -> None:
    import asyncio

    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            item = _item(fixture.source_type, external_id="job-1", title="Backend Engineer")
            succeeded = asyncio.run(
                fixture.service(_StaticCollector(fixture.source_type, [[item]])).execute(
                    fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
                )
            )
            assert succeeded.status == "SUCCEEDED"

            with pytest.raises(AcquisitionError) as excinfo:
                asyncio.run(
                    fixture.service(_StaticCollector(fixture.source_type, [[item]])).execute(
                        fixture.source.id,
                        CollectionRequest(
                            mode=CollectionMode.DISCOVERY,
                            cursor="job-1",
                            resume_of_run_id=succeeded.id,
                        ),
                    )
                )
            assert excinfo.value.code == AcquisitionErrorCode.INVALID_CONFIGURATION
        finally:
            fixture.cleanup()


def _normalize_all(fixture: _Fixture, opportunities: OpportunityService) -> None:
    for raw_item in fixture.raw_items():
        opportunities.normalize(raw_item.id)


def _opportunity_states(fixture: _Fixture) -> dict[str, str]:
    states: dict[str, str] = {}
    for raw_item in fixture.raw_items():
        occurrence = fixture.occurrence_for(raw_item.id)
        assert occurrence is not None
        fixture.session.refresh(occurrence.opportunity)
        states[str(raw_item.external_id)] = occurrence.opportunity.lifecycle_status
    return states


def test_304_requires_matching_inventory_scope() -> None:
    """A 304 reuses the stored inventory only for the board, filters and contract version
    the cache was stored under; otherwise the run is partial and closes nothing (F51-13)."""
    import asyncio

    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        opportunities = OpportunityService(session)
        seen_headers: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_headers.append(request.headers.get("If-None-Match"))
            if request.headers.get("If-None-Match") == '"v1"':
                return httpx.Response(304, headers={"ETag": '"v1"'})
            return httpx.Response(
                200,
                headers={"ETag": '"v1"'},
                json={"jobs": [{"id": "job-1", "title": "Backend Engineer"}]},
            )

        def execute(collector: object, **request: object):
            return asyncio.run(
                fixture.service(collector).execute(
                    fixture.source.id,
                    CollectionRequest(mode=CollectionMode.DISCOVERY, **request),  # type: ignore[arg-type]
                )
            )

        try:
            # A complete read, under the unfiltered scope, stores a validator for it.
            first = execute(
                _ConditionalCollector(fixture.source_type, httpx.MockTransport(handler)),
                company_reference="acme",
            )
            assert first.complete is True
            _normalize_all(fixture, opportunities)
            checkpoint = fixture.source.checkpoint
            assert checkpoint is not None and checkpoint.scope_hash is not None
            stored_scope = checkpoint.scope_hash

            # Same scope: every declared representation revalidates, the inventory is reused.
            same = execute(
                _ManifestConditionalCollector(fixture.source_type, [True, True]),
                company_reference="acme",
            )
            assert same.complete is True

            # Different board: the same fully revalidated manifest proves nothing.
            other = execute(
                _ManifestConditionalCollector(fixture.source_type, [True, True]),
                company_reference="other-board",
            )
            assert other.status == "SUCCEEDED"
            assert other.complete is False
            opportunities.reconcile_run_closures(other.id)
            assert "CLOSED" not in _opportunity_states(fixture).values()

            # The stored validator is not sent for the other filter: the request is
            # unconditional and the board is read in full.
            seen_headers.clear()
            unconditional = execute(
                _ConditionalCollector(fixture.source_type, httpx.MockTransport(handler)),
                company_reference="other-board",
            )
            assert seen_headers == [None]
            assert unconditional.items_seen == 1

            # A 304 that answers a validator of another scope (here supplied by the caller)
            # confirms nothing: partial, no closure, and the stored cache is left alone.
            session.refresh(checkpoint)
            scope_before = checkpoint.scope_hash
            assert scope_before != stored_scope
            foreign = execute(
                _ConditionalCollector(fixture.source_type, httpx.MockTransport(handler)),
                company_reference="third-board",
                conditional_headers=ConditionalRequestHeaders(if_none_match='"v1"'),
            )
            assert foreign.items_persisted == 0 and foreign.items_seen == 0
            assert foreign.complete is False
            opportunities.reconcile_run_closures(foreign.id)
            assert "CLOSED" not in _opportunity_states(fixture).values()
            session.refresh(checkpoint)
            assert checkpoint.scope_hash == scope_before
        finally:
            fixture.cleanup()


def test_inventory_scope_hash_changes_with_every_dimension_of_the_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F51-13 AC03: the fingerprint a validator is stored under covers the board, the
    filters, the region and the contract version, and ignores filter order and case."""
    from opportunity_radar.acquisition import inventory_contract

    base = {
        "source_type": "greenhouse",
        "company_reference": "acme",
        "api_region": None,
        "keywords": ("python", "backend"),
        "locations": ("Recife",),
    }
    baseline = inventory_scope_hash(**base)  # type: ignore[arg-type]

    # Filter order and case do not make another scope.
    assert baseline == inventory_scope_hash(
        **{**base, "keywords": ("Backend", "PYTHON"), "locations": ("recife",)}  # type: ignore[arg-type]
    )
    variants = {
        "source_type": {"source_type": "lever"},
        "company_reference": {"company_reference": "other-board"},
        "api_region": {"api_region": "eu"},
        "keywords": {"keywords": ("python",)},
        "locations": {"locations": ("Recife", "Lisbon")},
    }
    hashes = {
        name: inventory_scope_hash(**{**base, **change})  # type: ignore[arg-type]
        for name, change in variants.items()
    }
    assert baseline not in hashes.values()
    assert len(set(hashes.values())) == len(variants)

    monkeypatch.setattr(inventory_contract, "INVENTORY_CONTRACT_VERSION", "inventory-contract-next")
    assert inventory_scope_hash(**base) not in {baseline, *hashes.values()}  # type: ignore[arg-type]


_SEARCHABLE = CollectorCapabilities(
    incremental_cursor=True,
    etag=True,
    last_modified=True,
    keyword_search=True,
    location_search=True,
)


class _SearchableConditionalCollector(_ConditionalCollector):
    capabilities = _SEARCHABLE


class _SearchableManifestCollector(_ManifestConditionalCollector):
    capabilities = _SEARCHABLE


@pytest.mark.parametrize(
    "change",
    ["keywords", "locations", "api_region", "contract_version"],
)
def test_304_validator_and_inventory_reuse_are_scoped_to_filters_region_and_contract(
    change: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F51-13 AC03: a validator stored under one scope is sent, and lets a fully revalidated
    manifest reuse the inventory, only under that same scope. Under a changed keyword,
    location, region or contract version nothing is sent, nothing is reused, and no
    previously seen posting is closed."""
    import asyncio

    from opportunity_radar.acquisition import inventory_contract

    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        opportunities = OpportunityService(session)
        seen_headers: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_headers.append(request.headers.get("If-None-Match"))
            if request.headers.get("If-None-Match") == '"v1"':
                return httpx.Response(304, headers={"ETag": '"v1"'})
            return httpx.Response(
                200,
                headers={"ETag": '"v1"'},
                json={
                    "jobs": [
                        {"id": "job-1", "title": "Backend Engineer"},
                        {"id": "job-2", "title": "Data Engineer"},
                    ]
                },
            )

        def execute(collector: object, **request: object):
            return asyncio.run(
                fixture.service(collector).execute(
                    fixture.source.id,
                    CollectionRequest(
                        mode=CollectionMode.DISCOVERY,
                        company_reference="acme",
                        **request,  # type: ignore[arg-type]
                    ),
                )
            )

        def conditional() -> _SearchableConditionalCollector:
            return _SearchableConditionalCollector(
                fixture.source_type, httpx.MockTransport(handler)
            )

        changed: dict[str, object] = {
            "keywords": {"keywords": ("python",)},
            "locations": {"locations": ("Recife",)},
            "api_region": {"api_region": "eu"},
            "contract_version": {},
        }[change]  # type: ignore[assignment]
        try:
            first = execute(conditional())
            assert first.complete is True and first.items_seen == 2
            _normalize_all(fixture, opportunities)
            checkpoint = fixture.source.checkpoint
            assert checkpoint is not None and checkpoint.scope_hash is not None
            stored_scope = checkpoint.scope_hash
            seen_ids = set(_opportunity_states(fixture))
            assert seen_ids == {"job-1", "job-2"}

            # Same scope: the validator is sent, and a fully revalidated manifest reuses the
            # inventory (complete run, zero items re-read) without closing what it knew.
            seen_headers.clear()
            execute(conditional())
            assert seen_headers == ['"v1"']
            same = execute(_SearchableManifestCollector(fixture.source_type, [True, True]))
            assert same.complete is True and same.items_seen == 0
            assert opportunities.reconcile_run_closures(same.id) is True
            assert set(_opportunity_states(fixture)) == seen_ids
            assert "CLOSED" not in _opportunity_states(fixture).values()

            # Another scope: the same fully revalidated manifest proves nothing about it.
            if change == "contract_version":
                monkeypatch.setattr(
                    inventory_contract, "INVENTORY_CONTRACT_VERSION", "inventory-contract-next"
                )
            foreign = execute(
                _SearchableManifestCollector(fixture.source_type, [True, True]), **changed
            )
            assert foreign.status == "SUCCEEDED" and foreign.complete is False
            opportunities.reconcile_run_closures(foreign.id)
            assert "CLOSED" not in _opportunity_states(fixture).values()
            session.refresh(checkpoint)
            assert checkpoint.scope_hash == stored_scope  # the cache was left alone

            # The validator stored under the old scope is not sent: the request is
            # unconditional and the whole board is read again.
            seen_headers.clear()
            unconditional = execute(conditional(), **changed)
            assert seen_headers == [None]
            assert unconditional.items_seen == 2
            session.refresh(checkpoint)
            assert checkpoint.scope_hash != stored_scope  # now stored under the new scope
        finally:
            fixture.cleanup()


class _TimeoutAfterPrefixCollector(_StaticCollector):
    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        del request
        yield self._batches[0][0]
        raise AcquisitionError(AcquisitionErrorCode.SOURCE_TIMEOUT, "next page timed out")


def test_timeout_after_valid_page_keeps_presence_and_closes_nothing() -> None:
    import asyncio

    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        opportunities = OpportunityService(session)
        try:
            present = _item(fixture.source_type, external_id="page-1", title="On page one")
            absent = _item(fixture.source_type, external_id="page-2", title="On page two")
            first = asyncio.run(
                fixture.service(_StaticCollector(fixture.source_type, [[present, absent]])).execute(
                    fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
                )
            )
            assert first.complete is True
            _normalize_all(fixture, opportunities)

            partial = asyncio.run(
                fixture.service(
                    _TimeoutAfterPrefixCollector(fixture.source_type, [[present]])
                ).execute(fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
            )

            assert partial.status == "PARTIAL"
            assert partial.error_code == AcquisitionErrorCode.SOURCE_TIMEOUT.value
            assert partial.complete is False
            observed = fixture.occurrence_for(
                next(i.id for i in fixture.raw_items() if i.external_id == "page-1")
            )
            assert observed is not None
            session.refresh(observed)
            assert observed.last_seen_run_id == partial.id
            opportunities.reconcile_run_closures(partial.id)
            assert _opportunity_states(fixture)["page-2"] != "CLOSED"
        finally:
            fixture.cleanup()
