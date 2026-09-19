from __future__ import annotations

import signal
from pathlib import Path
from threading import Event

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.service import OpportunityService
from opportunity_radar.platform.config import Settings, get_settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.platform.logging import (
    configure_logging,
    correlation_scope,
    get_logger,
)

WORKER_READY_FILE = Path("/tmp/opportunity-radar-worker-ready")

logger = get_logger("opportunity_radar.worker")


def heartbeat() -> None:
    """Expose a lightweight scheduler liveness job."""
    logger.debug("worker heartbeat")


def normalize_opportunities(engine: Engine) -> None:
    """Each pass gets its own correlation id, so one batch is greppable end to end."""
    with correlation_scope():
        with Session(engine) as session:
            try:
                batch = OpportunityService(session).normalize_pending()
            except Exception:
                logger.exception("normalization batch failed", extra={"job": "normalize"})
                raise
        if batch.processed:
            logger.info(
                "normalization batch finished",
                extra={
                    "job": "normalize",
                    "processed": batch.processed,
                    "succeeded": batch.succeeded,
                    "review_required": batch.review_required,
                    "failed": batch.failed,
                },
            )


def build_scheduler(settings: Settings) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=settings.collection_timezone)
    engine = create_database_engine(settings.database_url)
    scheduler.add_job(heartbeat, "interval", minutes=5, id="heartbeat", replace_existing=True)
    scheduler.add_job(
        normalize_opportunities,
        "interval",
        seconds=60,
        args=(engine,),
        id="normalize-opportunities",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    return scheduler


def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    scheduler = build_scheduler(settings)
    stopped = Event()

    def stop(*_: object) -> None:
        stopped.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    scheduler.start()
    WORKER_READY_FILE.touch()
    logger.info("worker started", extra={"timezone": settings.collection_timezone})
    try:
        stopped.wait()
    finally:
        WORKER_READY_FILE.unlink(missing_ok=True)
        scheduler.shutdown(wait=False)
        logger.info("worker stopped")


if __name__ == "__main__":
    run()
