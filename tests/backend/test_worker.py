import logging

import pytest

from opportunity_radar.platform.config import Settings
from opportunity_radar.worker import FUNCTIONAL_JOB_IDS, build_scheduler

_DATABASE_URL = "postgresql+psycopg://test:test@localhost/test"


def test_worker_scheduler_has_a_heartbeat_job() -> None:
    scheduler = build_scheduler(Settings(database_url=_DATABASE_URL))

    assert scheduler.get_job("heartbeat") is not None
    assert scheduler.get_job("collect-enabled-sources") is not None
    assert scheduler.get_job("normalize-opportunities") is not None
    assert scheduler.get_job("evaluate-pending") is not None
    assert scheduler.get_job("analyze-pending") is not None
    assert scheduler.get_job("expire-raw-payloads") is not None


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
    }
    for switch, disabled_job in switches.items():
        scheduler = build_scheduler(
            Settings(database_url=_DATABASE_URL, **{switch: False})
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


def test_the_model_is_warmed_up_once_at_startup_when_analysis_is_on() -> None:
    scheduler = build_scheduler(Settings(database_url=_DATABASE_URL))
    warm_up = scheduler.get_job("warm-up-models")
    analyze = scheduler.get_job("analyze-pending")

    assert warm_up is not None and analyze is not None
    assert warm_up.args[0] is analyze.args[1]
    assert "warm-up-models" not in FUNCTIONAL_JOB_IDS.values()


@pytest.mark.parametrize("switch", ["worker_analyze_enabled", "ollama_analysis_enabled"])
def test_no_warm_up_without_analysis(switch: str) -> None:
    scheduler = build_scheduler(Settings(database_url=_DATABASE_URL, **{switch: False}))

    assert scheduler.get_job("warm-up-models") is None
