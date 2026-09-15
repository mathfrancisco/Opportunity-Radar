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

WORKER_READY_FILE = Path("/tmp/opportunity-radar-worker-ready")


def heartbeat() -> None:
    """Expose a lightweight scheduler liveness job."""


def normalize_opportunities(engine: Engine) -> None:
    with Session(engine) as session:
        OpportunityService(session).normalize_pending()


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
    scheduler = build_scheduler(get_settings())
    stopped = Event()

    def stop(*_: object) -> None:
        stopped.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    scheduler.start()
    WORKER_READY_FILE.touch()
    try:
        stopped.wait()
    finally:
        WORKER_READY_FILE.unlink(missing_ok=True)
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    run()
