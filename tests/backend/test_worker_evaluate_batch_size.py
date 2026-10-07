from opportunity_radar.platform.config import Settings
from opportunity_radar.worker import build_scheduler, evaluate_pending

_DATABASE_URL = "postgresql+psycopg://test:test@localhost/test"


def test_evaluate_batch_size_defaults_to_500() -> None:
    assert Settings(database_url=_DATABASE_URL).worker_evaluate_batch_size == 500


def test_worker_passes_the_batch_size_to_evaluate_pending() -> None:
    scheduler = build_scheduler(Settings(database_url=_DATABASE_URL))

    job = scheduler.get_job("evaluate-pending")

    assert job is not None
    assert job.func is evaluate_pending
    assert job.kwargs == {"batch_size": 500}
