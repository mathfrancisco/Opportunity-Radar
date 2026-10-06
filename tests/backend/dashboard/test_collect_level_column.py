"""F52-09: `scripts/collect.py` reports, per run and per source, how many postings of the
accepted level it brought (the active profile's `accepted_seniorities`, without `UNKNOWN`).

The unit tests stub the profile and the counting query. The integration test exercises the
counting query itself and is gated like the rest of the database suite.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.domain import ProfileNotFoundError
from scripts import collect

from .test_queries import _company, _occurrence, _opportunity, _source_with_run

NOW = datetime.now(UTC)


class _Profiles:
    def __init__(self, accepted: tuple[str, ...] | None) -> None:
        self._accepted = accepted

    def get_active(self) -> SimpleNamespace:
        if self._accepted is None:
            raise ProfileNotFoundError("no active profile")
        preferences = SimpleNamespace(accepted_seniorities=self._accepted)
        return SimpleNamespace(snapshot=SimpleNamespace(preferences=preferences))


def _use_profile(monkeypatch: pytest.MonkeyPatch, accepted: tuple[str, ...] | None) -> None:
    monkeypatch.setattr(collect, "ProfileService", lambda session: _Profiles(accepted))


def test_accepted_levels_drop_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_profile(monkeypatch, ("INTERN", "JUNIOR", "MID", "UNKNOWN"))

    assert collect.active_profile_accepted_seniorities(object()) == (  # type: ignore[arg-type]
        "INTERN",
        "JUNIOR",
        "MID",
    )


@pytest.mark.parametrize("accepted", [None, (), ("UNKNOWN",)])
def test_no_active_profile_or_no_level_reads_as_unknown(
    monkeypatch: pytest.MonkeyPatch, accepted: tuple[str, ...] | None
) -> None:
    _use_profile(monkeypatch, accepted)

    assert collect.active_profile_accepted_seniorities(object()) is None  # type: ignore[arg-type]


def test_column_says_no_active_profile_and_does_not_fail() -> None:
    runs = [
        {"source_name": "A", "status": "SUCCEEDED", "run_id": str(uuid4())},
        {"source_name": "B", "status": "ERROR", "error_code": "UNKNOWN_ERROR"},
    ]

    summary = collect.add_level_column(object(), runs, None)  # type: ignore[arg-type]

    assert summary == {"status": collect.NO_ACTIVE_PROFILE}
    assert [item["accepted_level"] for item in runs] == [
        {"status": collect.NO_ACTIVE_PROFILE}
    ] * 2


def test_column_is_added_per_source_and_summed(monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = uuid4(), uuid4()
    monkeypatch.setattr(
        collect,
        "level_counts_by_run",
        lambda session, run_ids, accepted: {
            first: {"postings": 10, "accepted_level": 4},
            second: {"postings": 3, "accepted_level": 0},
        },
    )
    runs = [
        {"source_name": "A", "run_id": str(first)},
        {"source_name": "B", "run_id": str(second)},
        {"source_name": "C", "status": "ERROR"},
    ]

    summary = collect.add_level_column(object(), runs, ("JUNIOR", "MID"))  # type: ignore[arg-type]

    assert runs[0]["accepted_level"] == {"status": "ok", "postings": 10, "accepted_level": 4}
    assert runs[1]["accepted_level"] == {"status": "ok", "postings": 3, "accepted_level": 0}
    assert runs[2]["accepted_level"] == {"status": "no_run"}
    assert summary == {
        "status": "ok",
        "accepted_seniorities": ["JUNIOR", "MID"],
        "postings": 13,
        "accepted_level": 4,
    }


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)
def test_level_counts_by_run_counts_each_posting_once_per_source_run() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        company = _company(session, "normal")
        source_a, run_a = _source_with_run(session)
        source_b, run_b = _source_with_run(session)
        for source_id, run_id, seniority in (
            (source_a, run_a, "JUNIOR"),
            (source_a, run_a, "MID"),
            (source_a, run_a, "SENIOR"),
            (source_a, run_a, "UNKNOWN"),
            (source_b, run_b, "SENIOR"),
            (source_b, run_b, "STAFF"),
        ):
            opportunity = _opportunity(
                session,
                company,
                title=f"{seniority} {uuid4().hex[:6]}",
                published_at=NOW,
                seniority=seniority,
            )
            _occurrence(session, opportunity, source_id, run_id)
        session.commit()

        counts = collect.level_counts_by_run(session, [run_a, run_b], ("JUNIOR", "MID"))

        assert counts[run_a] == {"postings": 4, "accepted_level": 2}
        assert counts[run_b] == {"postings": 2, "accepted_level": 0}
        assert collect.level_counts_by_run(session, [], ("JUNIOR",)) == {}
