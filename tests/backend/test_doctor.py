"""A scheduler that is up says nothing about a job that never ran."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from opportunity_radar.platform.config import Settings
from scripts import doctor
from scripts.doctor import Check, check_ai, classify_worker_jobs

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
GRACE = timedelta(seconds=120)


@dataclass(frozen=True)
class _State:
    last_success_at: datetime | None
    last_failure_at: datetime | None
    next_run_at: datetime | None


def _healthy() -> _State:
    return _State(
        last_success_at=NOW - timedelta(seconds=30),
        last_failure_at=None,
        next_run_at=NOW + timedelta(seconds=30),
    )


def test_each_job_lands_in_exactly_one_state() -> None:
    states = {
        "healthy_job": _healthy(),
        "late_job": _State(
            last_success_at=NOW - timedelta(hours=2),
            last_failure_at=None,
            next_run_at=NOW - timedelta(hours=1),
        ),
        "failing_job": _State(
            last_success_at=NOW - timedelta(hours=2),
            last_failure_at=NOW - timedelta(minutes=1),
            next_run_at=NOW + timedelta(seconds=30),
        ),
    }

    result = classify_worker_jobs(
        states,
        ["healthy_job", "late_job", "failing_job", "absent_job"],
        now=NOW,
        grace=GRACE,
    )

    assert result == {
        "missing": ["absent_job"],
        "failing": ["failing_job"],
        "late": ["late_job"],
        "healthy": ["healthy_job"],
    }


def test_a_job_that_failed_after_its_last_success_is_failing_not_late() -> None:
    states = {
        "job": _State(
            last_success_at=NOW - timedelta(hours=3),
            last_failure_at=NOW - timedelta(hours=2),
            next_run_at=NOW - timedelta(hours=1),
        )
    }

    result = classify_worker_jobs(states, ["job"], now=NOW, grace=GRACE)

    assert result["failing"] == ["job"]
    assert result["late"] == []


def test_a_job_inside_its_grace_is_not_late() -> None:
    states = {
        "job": _State(
            last_success_at=NOW - timedelta(minutes=2),
            last_failure_at=None,
            next_run_at=NOW - timedelta(seconds=60),
        )
    }

    result = classify_worker_jobs(states, ["job"], now=NOW, grace=GRACE)

    assert result["healthy"] == ["job"]


def test_a_first_pass_still_running_is_not_reported_as_a_failure() -> None:
    states = {
        "job": _State(
            last_success_at=None,
            last_failure_at=None,
            next_run_at=NOW + timedelta(seconds=30),
        )
    }

    result = classify_worker_jobs(states, ["job"], now=NOW, grace=GRACE)

    assert result["failing"] == []
    assert result["healthy"] == ["job"]


def test_a_first_pass_that_never_finishes_becomes_late() -> None:
    states = {
        "job": _State(
            last_success_at=None,
            last_failure_at=None,
            next_run_at=NOW - timedelta(hours=1),
        )
    }

    result = classify_worker_jobs(states, ["job"], now=NOW, grace=GRACE)

    assert result["late"] == ["job"]


def test_a_job_that_only_ever_failed_is_failing() -> None:
    states = {
        "job": _State(
            last_success_at=None,
            last_failure_at=NOW - timedelta(seconds=10),
            next_run_at=NOW + timedelta(seconds=30),
        )
    }

    result = classify_worker_jobs(states, ["job"], now=NOW, grace=GRACE)

    assert result["failing"] == ["job"]


def test_a_disabled_job_is_simply_not_expected() -> None:
    result = classify_worker_jobs({"job": _healthy()}, [], now=NOW, grace=GRACE)

    assert result == {"missing": [], "failing": [], "late": [], "healthy": []}


def test_doctor_has_no_embedding_coverage_check(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")
    monkeypatch.setattr(doctor, "Settings", lambda: object())
    monkeypatch.setattr(
        doctor,
        "check_database",
        lambda _: Check("database", doctor.OK, "stub"),
    )
    for name in (
        "check_tables",
        "check_worker_jobs",
        "check_source_incidents",
        "check_analysis",
        "check_ai",
    ):
        monkeypatch.setattr(
            doctor,
            name,
            lambda *args, _name=name, **kwargs: Check(_name, doctor.OK, "stub"),
        )

    checks = doctor.run_checks(Path(__file__).parents[2])

    assert not any("embedding" in check.name.casefold() for check in checks)


def _settings(**overrides: object) -> Settings:
    return Settings(
        database_url="postgresql+psycopg://test:test@localhost/test", **overrides
    )


def test_check_ai_never_prints_the_key() -> None:
    secret = "sk-super-secret-value"
    check = check_ai(_settings(ai_enabled=True, groq_api_key=secret))

    assert secret not in check.detail
    assert secret not in str(check.facts)
    assert secret not in (check.remedy or "")
    assert check.facts["key_present"] is True


def test_check_ai_warns_when_disabled() -> None:
    check = check_ai(_settings(ai_enabled=False))

    assert check.status == doctor.WARN
    assert "disabled" in check.detail


def test_check_ai_warns_when_key_is_missing() -> None:
    check = check_ai(_settings(ai_enabled=True, groq_api_key=""))

    assert check.status == doctor.WARN
    assert check.facts["key_present"] is False


def test_check_ai_is_ok_when_enabled_with_a_key() -> None:
    check = check_ai(_settings(ai_enabled=True, groq_api_key="sk-fake"))

    assert check.status == doctor.OK
