import logging
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from functools import partial
from types import SimpleNamespace
from uuid import uuid4

import pytest

from opportunity_radar import worker
from opportunity_radar.platform.config import Settings
from opportunity_radar.worker import (
    FUNCTIONAL_JOB_IDS,
    build_scheduler,
    collection_service_factory,
)

_DATABASE_URL = "postgresql+psycopg://test:test@localhost/test"


@pytest.mark.parametrize("budget", [0, 7])
def test_scheduled_collection_uses_configured_tavily_credit_budget(budget: int) -> None:
    service = collection_service_factory(
        Settings(
            database_url=_DATABASE_URL,
            tavily_credit_budget_per_run=budget,
            worker_owner_sub="worker-owner-synthetic",
        )
    )(None)  # type: ignore[arg-type]

    collector = service.registry.resolve("tavily_search")

    assert collector._credit_budget_per_run == budget  # type: ignore[attr-defined]


def test_worker_scheduler_has_a_heartbeat_job() -> None:
    scheduler = build_scheduler(Settings(database_url=_DATABASE_URL))

    assert scheduler.get_job("heartbeat") is not None
    assert scheduler.get_job("collect-enabled-sources") is not None
    assert scheduler.get_job("normalize-opportunities") is not None
    assert scheduler.get_job("evaluate-pending") is not None
    assert scheduler.get_job("analyze-pending") is not None
    assert scheduler.get_job("expire-raw-payloads") is not None


def test_worker_jobs_receive_an_explicit_operational_owner() -> None:
    scheduler = build_scheduler(
        Settings(database_url=_DATABASE_URL, worker_owner_sub="worker-owner-synthetic")
    )

    assert scheduler.get_job("evaluate-pending").kwargs["owner_sub"] == "worker-owner-synthetic"
    assert scheduler.get_job("analyze-pending").kwargs["owner_sub"] == "worker-owner-synthetic"
    assert (
        scheduler.get_job("collect-enabled-sources").kwargs["owner_sub"]
        == "worker-owner-synthetic"
    )


def test_collection_factory_scopes_profile_reads_to_configured_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def target_roles(session: object, owner_sub: str | None = None):
        captured["session"] = session
        captured["owner_sub"] = owner_sub
        return lambda: ()

    monkeypatch.setattr(worker, "active_profile_target_role_families", target_roles)
    session = object()
    service = collection_service_factory(
        Settings(database_url=_DATABASE_URL, worker_owner_sub="worker-owner-synthetic")
    )(session)  # type: ignore[arg-type]

    assert captured == {"session": session, "owner_sub": "worker-owner-synthetic"}
    assert service.profile_owner_sub == "worker-owner-synthetic"


def test_collection_factory_rejects_blank_owner_without_global_profile_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str | None] = []

    def target_roles(_session: object, owner_sub: str | None = None):
        captured.append(owner_sub)
        return lambda: ()

    monkeypatch.setattr(worker, "active_profile_target_role_families", target_roles)
    factory = collection_service_factory(
        Settings(database_url=_DATABASE_URL, worker_owner_sub="  ")
    )

    with pytest.raises(ValueError, match="explicit operational owner"):
        factory(object())  # type: ignore[arg-type]

    assert captured == []


def test_remotive_does_not_read_a_global_profile_without_owner() -> None:
    collector = SimpleNamespace(
        capabilities=SimpleNamespace(keyword_search=True, incremental_cursor=False)
    )
    service = SimpleNamespace(
        registry=SimpleNamespace(resolve=lambda _source_type: collector),
        profile_owner_sub=None,
        session=object(),
    )
    source = SimpleNamespace(
        source_type="remotive",
        configuration={"keywords": ["custom term"]},
        id=uuid4(),
        checkpoint=None,
    )

    request, rotation, term_count = worker._scheduled_request_with_rotation(
        service, source, "correlation"  # type: ignore[arg-type]
    )

    assert request.keywords == ("custom term",)
    assert rotation is not None
    assert term_count == 1


def test_suggestion_candidate_query_fails_closed_without_owner() -> None:
    assert worker.candidates_needing_suggestion(object(), limit=1) == []  # type: ignore[arg-type]


def test_evaluation_skips_without_operational_owner(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        worker,
        "Session",
        lambda _engine: pytest.fail("an ownerless worker must not open a database session"),
    )

    with caplog.at_level(logging.WARNING, logger="opportunity_radar.worker"):
        worker.evaluate_pending(object())

    assert any(
        record.message == "worker job skipped: no operational owner configured"
        and getattr(record, "reason") == "missing_worker_owner"
        for record in caplog.records
    )


@pytest.mark.parametrize("owner_sub", [None, "   "])
@pytest.mark.parametrize("job", ["collect", "evaluate", "analyze", "suggest"])
def test_ownerless_worker_jobs_skip_before_observation_or_session(
    owner_sub: str | None,
    job: str,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> object:
        pytest.fail("an ownerless worker job must stop before clock, observation, or session")

    monkeypatch.setattr(worker, "Session", fail)
    monkeypatch.setattr(worker, "observe_job", fail)
    kwargs: dict[str, object] = {"owner_sub": owner_sub}
    if job == "collect":
        kwargs.update(monotonic_clock=fail, service_factory=fail)
        call = partial(worker.collect_enabled_sources, object(), **kwargs)  # type: ignore[arg-type]
    elif job == "evaluate":
        call = partial(worker.evaluate_pending, object(), **kwargs)  # type: ignore[arg-type]
    elif job == "analyze":
        call = partial(worker.analyze_pending, object(), object(), **kwargs)  # type: ignore[arg-type]
    else:
        call = partial(
            worker.suggest_fields_pending, object(), object(), **kwargs
        )  # type: ignore[arg-type]

    with caplog.at_level(logging.WARNING, logger="opportunity_radar.worker"):
        call()

    assert any(
        record.message == "worker job skipped: no operational owner configured"
        and getattr(record, "reason") == "missing_worker_owner"
        for record in caplog.records
    )


def test_evaluation_uses_the_configured_operational_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owners: list[str | None] = []

    class Service:
        def __init__(self, _session: object, owner_sub: str | None) -> None:
            owners.append(owner_sub)

        def pending_evaluation_ids(self, *, limit: int) -> list[object]:
            assert limit == 3
            return []

    monkeypatch.setattr(worker, "observe_job", lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(worker, "Session", lambda _engine: nullcontext(object()))
    monkeypatch.setattr(worker, "MatchingService", Service)

    worker.evaluate_pending(object(), batch_size=3, owner_sub="worker-owner-synthetic")

    assert owners == ["worker-owner-synthetic"]


def test_worker_scheduler_has_no_embedding_job() -> None:
    scheduler = build_scheduler(Settings(database_url=_DATABASE_URL))

    assert scheduler.get_job("embed-opportunities") is None
    assert "embed_opportunities" not in FUNCTIONAL_JOB_IDS


def test_worker_kill_switches_only_remove_functional_jobs() -> None:
    scheduler = build_scheduler(
        Settings(
            database_url=_DATABASE_URL,
            worker_collect_enabled=False,
            worker_normalize_enabled=False,
            worker_match_enabled=False,
            worker_analyze_enabled=False,
            worker_retention_enabled=False,
            worker_suggest_enabled=False,
        )
    )

    assert scheduler.get_job("heartbeat") is not None
    for job_id in FUNCTIONAL_JOB_IDS.values():
        assert scheduler.get_job(job_id) is None


def test_each_kill_switch_removes_only_its_own_job() -> None:
    switches = {
        "worker_collect_enabled": "collect-enabled-sources",
        "worker_normalize_enabled": "normalize-opportunities",
        "worker_match_enabled": "evaluate-pending",
        "worker_analyze_enabled": "analyze-pending",
        "worker_retention_enabled": "expire-raw-payloads",
        "worker_suggest_enabled": "suggest-fields-pending",
    }
    for switch, disabled_job in switches.items():
        enabled_switches = {name: True for name in switches}
        enabled_switches[switch] = False
        scheduler = build_scheduler(
            Settings(database_url=_DATABASE_URL, **enabled_switches)
        )

        assert scheduler.get_job(disabled_job) is None
        for other in switches.values():
            if other != disabled_job:
                assert scheduler.get_job(other) is not None
        assert scheduler.get_job("heartbeat") is not None


def test_the_startup_log_reports_what_the_scheduler_actually_holds(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The log is evidence of what is running, so it is read off the scheduler itself.

    Reporting the kill switches instead would let the log claim a job is active when no
    such job was ever registered — an automation that looks on while it is off.
    """
    settings = Settings(database_url=_DATABASE_URL, worker_analyze_enabled=False)
    with caplog.at_level(logging.INFO, logger="opportunity_radar.worker"):
        scheduler = build_scheduler(settings)

    record = next(
        item for item in caplog.records if item.message == "worker jobs configured"
    )
    reported = getattr(record, "jobs")

    assert set(reported) == set(FUNCTIONAL_JOB_IDS)
    for name, job_id in FUNCTIONAL_JOB_IDS.items():
        assert reported[name] is (scheduler.get_job(job_id) is not None)
    assert reported["analyze_pending"] is False


def test_no_warm_up_job_is_scheduled_for_a_cloud_adapter() -> None:
    """The Groq adapter has nothing to warm up, so no separate startup job exists."""
    scheduler = build_scheduler(Settings(database_url=_DATABASE_URL))

    assert scheduler.get_job("warm-up-models") is None
    assert scheduler.get_job("analyze-pending") is not None


def test_no_analyze_job_without_analysis_enabled() -> None:
    scheduler = build_scheduler(
        Settings(database_url=_DATABASE_URL, worker_analyze_enabled=False)
    )

    assert scheduler.get_job("analyze-pending") is None


def test_suggest_fields_batch_summary_uses_non_reserved_log_fields(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    opportunity = SimpleNamespace(id="opportunity-1")

    async def suggest_fields(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            created=(), discarded_fields=(), state="success", quota_exhausted=False
        )

    monkeypatch.setattr(worker, "observe_job", lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(worker, "Session", lambda _engine: nullcontext(object()))
    monkeypatch.setattr(
        worker,
        "candidates_needing_suggestion",
        lambda _session, *, limit, **_kwargs: [opportunity],
    )
    monkeypatch.setattr(worker, "suggest_fields", suggest_fields)
    router = SimpleNamespace(
        quota_guard=None,
        route=lambda _task: SimpleNamespace(chain=("model",)),
    )

    with caplog.at_level(logging.INFO, logger="opportunity_radar.worker"):
        worker.suggest_fields_pending(
            object(), router, owner_sub="worker-owner-synthetic"
        )

    record = next(
        item
        for item in caplog.records
        if item.message == "suggest fields batch finished"
    )
    summary_fields = {
        "job",
        "processed",
        "suggestions_created",
        "discarded",
        "skipped_budget",
        "failed",
    }

    assert summary_fields.isdisjoint(logging.makeLogRecord({}).__dict__)
    assert getattr(record, "suggestions_created") == 0
    assert getattr(record, "discarded") == 0


def test_the_assessment_prune_job_is_off_unless_its_flag_is_on() -> None:
    off = build_scheduler(Settings(database_url=_DATABASE_URL))
    on = build_scheduler(
        Settings(database_url=_DATABASE_URL, worker_assessment_retention_enabled=True)
    )

    assert off.get_job("prune-match-assessments") is None
    assert on.get_job("prune-match-assessments") is not None
    assert on.get_job("expire-raw-payloads") is not None


def test_assessment_retention_settings_must_be_positive() -> None:
    with pytest.raises(ValueError, match="ASSESSMENT_RETENTION_DAYS"):
        Settings(database_url=_DATABASE_URL, assessment_retention_days=0)
    with pytest.raises(ValueError, match="ASSESSMENT_RETENTION_BATCH_SIZE"):
        Settings(database_url=_DATABASE_URL, assessment_retention_batch_size=0)


def test_worker_rechecks_due_time_after_each_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = [SimpleNamespace(id="slow"), SimpleNamespace(id="newly-due")]
    current = [datetime(2026, 1, 1, tzinfo=UTC)]
    executed: list[str] = []
    judged_at: list[datetime] = []

    class Service:
        def list_collectable_sources(self) -> list[object]:
            return sources

        def scheduling_state(self, source: object, *, timezone: str) -> object:
            del timezone
            return source

        async def execute(self, source_id: str, _request: object, **_kwargs: object):
            executed.append(source_id)
            current[0] += timedelta(seconds=90)
            return SimpleNamespace(
                complete=False,
                status="SUCCEEDED",
                id=f"run-{source_id}",
                items_persisted=1,
            )

    monkeypatch.setattr(worker, "observe_job", lambda *_args, **_kwargs: nullcontext("pass"))
    monkeypatch.setattr(worker, "Session", lambda _engine: nullcontext(object()))
    def evaluate(_state: object, *, now: datetime, **_kwargs: object):
        judged_at.append(now)
        return worker.CollectionGate.DUE

    monkeypatch.setattr(worker, "evaluate_gate", evaluate)
    monkeypatch.setattr(
        worker,
        "_scheduled_request_with_rotation",
        lambda _service, source, _correlation: (SimpleNamespace(keywords=()), None, 0),
    )
    monkeypatch.setattr(worker, "annotate_pass", lambda *_args, **_kwargs: None)

    worker.collect_enabled_sources(
        object(),
        owner_sub="worker-owner-synthetic",
        service_factory=lambda _session: Service(),  # type: ignore[arg-type]
        utc_clock=lambda: current[0],
    )

    assert executed == ["slow", "newly-due"]
    assert judged_at == [
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 1, 0, 1, 30, tzinfo=UTC),
    ]


def test_pass_deadline_skips_next_source_after_prior_cleanup_finishes(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    sources = [SimpleNamespace(id="slow"), SimpleNamespace(id="not-started")]
    current = [datetime(2026, 1, 1, tzinfo=UTC)]
    monotonic = [0.0]
    executed: list[str] = []
    cleanup_finished = [False]
    skips: list[str] = []

    class Service:
        def list_collectable_sources(self) -> list[object]:
            return sources

        def scheduling_state(self, source: object, *, timezone: str) -> object:
            del timezone
            return source

        async def execute(self, source_id: str, _request: object, **_kwargs: object):
            executed.append(source_id)
            monotonic[0] = 2.0
            cleanup_finished[0] = True
            return SimpleNamespace(
                complete=False,
                status="PARTIAL",
                id=f"run-{source_id}",
                items_persisted=1,
            )

    monkeypatch.setattr(worker, "observe_job", lambda *_args, **_kwargs: nullcontext("pass"))
    monkeypatch.setattr(worker, "Session", lambda _engine: nullcontext(object()))
    monkeypatch.setattr(
        worker,
        "evaluate_gate",
        lambda *_args, **_kwargs: worker.CollectionGate.DUE,
    )
    monkeypatch.setattr(
        worker,
        "_scheduled_request_with_rotation",
        lambda _service, _source, _correlation: (SimpleNamespace(keywords=()), None, 0),
    )
    monkeypatch.setattr(worker, "annotate_pass", lambda *_args, **_kwargs: None)

    with caplog.at_level(logging.INFO, logger="opportunity_radar.worker"):
        worker.collect_enabled_sources(
            object(),
            owner_sub="worker-owner-synthetic",
            service_factory=lambda _session: Service(),  # type: ignore[arg-type]
            source_deadline_seconds=0.0,
            pass_deadline_seconds=1.0,
            monotonic_clock=lambda: monotonic[0],
            utc_clock=lambda: current[0],
        )
    skips = [
        record.reason
        for record in caplog.records
        if record.message == "scheduled collection skipped"
    ]

    assert cleanup_finished[0] is True
    assert executed == ["slow"]
    assert skips == ["pass_deadline"]


def test_claimed_elsewhere_source_is_skipped_without_costing_the_rest_of_the_pass(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    sources = [SimpleNamespace(id="held-by-cli"), SimpleNamespace(id="free")]
    executed: list[str] = []
    summaries: list[dict[str, int]] = []

    class Service:
        def list_collectable_sources(self) -> list[object]:
            return sources

        def scheduling_state(self, source: object, *, timezone: str) -> object:
            del timezone
            return source

        async def execute(self, source_id: str, _request: object, **_kwargs: object):
            executed.append(source_id)
            if source_id == "held-by-cli":
                raise worker.SourceClaimedElsewhereError(source_id)  # type: ignore[arg-type]
            return SimpleNamespace(
                complete=False, status="SUCCEEDED", id="run-free", items_persisted=1
            )

    monkeypatch.setattr(worker, "observe_job", lambda *_args, **_kwargs: nullcontext("pass"))
    monkeypatch.setattr(
        worker, "Session", lambda _engine: nullcontext(SimpleNamespace(rollback=lambda: None))
    )
    monkeypatch.setattr(
        worker, "evaluate_gate", lambda *_args, **_kwargs: worker.CollectionGate.DUE
    )
    monkeypatch.setattr(
        worker,
        "_scheduled_request_with_rotation",
        lambda _service, _source, _correlation: (SimpleNamespace(keywords=()), None, 0),
    )
    monkeypatch.setattr(
        worker, "annotate_pass", lambda *_a, **summary: summaries.append(summary)
    )

    with caplog.at_level(logging.INFO, logger="opportunity_radar.worker"):
        worker.collect_enabled_sources(
            object(),
            owner_sub="worker-owner-synthetic",
            service_factory=lambda _session: Service(),  # type: ignore[arg-type]
        )

    assert executed == ["held-by-cli", "free"]
    assert [
        record.reason
        for record in caplog.records
        if record.message == "scheduled collection skipped"
    ] == ["claimed_elsewhere"]
    assert summaries[0]["skipped"] == 1 and summaries[0]["completed"] == 1
    assert summaries[0]["failed"] == 0


def test_collection_claims_follow_the_setting_and_default_on() -> None:
    on = collection_service_factory(
        Settings(database_url=_DATABASE_URL, worker_owner_sub="worker-owner-synthetic")
    )(None)  # type: ignore[arg-type]
    off = collection_service_factory(
        Settings(
            database_url=_DATABASE_URL,
            collection_claim_enabled=False,
            worker_owner_sub="worker-owner-synthetic",
        )
    )(None)  # type: ignore[arg-type]

    assert on._claims_enabled is True  # type: ignore[attr-defined]
    assert off._claims_enabled is False  # type: ignore[attr-defined]
