from __future__ import annotations

import signal
from pathlib import Path
from threading import Event

from apscheduler.schedulers.background import BackgroundScheduler

from opportunity_radar.platform.config import Settings, get_settings

WORKER_READY_FILE = Path("/tmp/opportunity-radar-worker-ready")


def heartbeat() -> None:
    """Keep the Phase 0 scheduler active until domain jobs are added."""


def build_scheduler(settings: Settings) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=settings.collection_timezone)
    scheduler.add_job(heartbeat, "interval", minutes=5, id="heartbeat", replace_existing=True)
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
