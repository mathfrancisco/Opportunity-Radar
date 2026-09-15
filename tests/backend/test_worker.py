from opportunity_radar.platform.config import Settings
from opportunity_radar.worker import build_scheduler


def test_worker_scheduler_has_a_heartbeat_job() -> None:
    scheduler = build_scheduler(
        Settings(database_url="postgresql+psycopg://test:test@localhost/test")
    )

    assert scheduler.get_job("heartbeat") is not None
    assert scheduler.get_job("normalize-opportunities") is not None
