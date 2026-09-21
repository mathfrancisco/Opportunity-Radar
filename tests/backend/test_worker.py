from opportunity_radar.platform.config import Settings
from opportunity_radar.worker import build_scheduler


def test_worker_scheduler_has_a_heartbeat_job() -> None:
    scheduler = build_scheduler(
        Settings(database_url="postgresql+psycopg://test:test@localhost/test")
    )

    assert scheduler.get_job("heartbeat") is not None
    assert scheduler.get_job("collect-enabled-sources") is not None
    assert scheduler.get_job("normalize-opportunities") is not None


def test_worker_kill_switches_only_remove_functional_jobs() -> None:
    scheduler = build_scheduler(
        Settings(
            database_url="postgresql+psycopg://test:test@localhost/test",
            worker_collect_enabled=False,
            worker_normalize_enabled=False,
            worker_match_enabled=False,
            worker_analyze_enabled=False,
        )
    )

    assert scheduler.get_job("heartbeat") is not None
    assert scheduler.get_job("collect-enabled-sources") is None
    assert scheduler.get_job("normalize-opportunities") is None
    assert scheduler.get_job("evaluate-pending") is None
