"""F51-04 AC02: two workers never both take the last unit of a host budget."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import HostBudgetStateModel
from opportunity_radar.acquisition.repository import AcquisitionRepository
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
HOST = "tenant.wd5.myworkdayjobs.com"
CEILING = 5


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE acquisition.host_budget_state"))
    yield engine
    engine.dispose()


def _race(engine: Engine, workers: int) -> list[str | None]:
    """Each worker has its own session and reserves at the same instant."""
    barrier = threading.Barrier(workers)
    outcomes: list[str | None] = []
    http_calls: list[int] = []
    lock = threading.Lock()

    def worker(index: int) -> None:
        with Session(engine) as session:
            barrier.wait(timeout=10)
            outcome = AcquisitionRepository(session).reserve_host_request(
                HOST, now=NOW, default_ceiling=CEILING, run_id=uuid4(), detail=True
            )
            with lock:
                outcomes.append(outcome)
                if outcome is None:
                    # The transport only starts after an accepted, committed reservation.
                    http_calls.append(index)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not any(thread.is_alive() for thread in threads)
    assert len(http_calls) == outcomes.count(None)
    return outcomes


def _used(engine: Engine) -> int:
    with Session(engine) as session:
        row = session.get(HostBudgetStateModel, HOST)
        assert row is not None
        return row.requests_used


def test_workday_budget_reservation_is_atomic_across_workers(engine: Engine) -> None:
    with Session(engine) as session:
        session.add(
            HostBudgetStateModel(
                host=HOST,
                window_start=NOW,
                requests_used=CEILING - 1,
                requests_ceiling=CEILING,
            )
        )
        session.commit()

    outcomes = _race(engine, workers=2)

    assert sorted(outcomes, key=str) == sorted([None, "quota"], key=str)
    assert _used(engine) == CEILING


def test_many_workers_on_a_new_host_never_exceed_the_ceiling(engine: Engine) -> None:
    # No row yet: the first reservation creates it, and the race includes that insert.
    outcomes = _race(engine, workers=CEILING + 4)

    assert outcomes.count(None) == CEILING
    assert outcomes.count("quota") == 4
    assert _used(engine) == CEILING
