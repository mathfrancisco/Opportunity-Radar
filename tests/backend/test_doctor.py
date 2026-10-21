"""A scheduler that is up says nothing about a job that never ran."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.platform.config import Settings
from opportunity_radar.profile.domain import EmploymentPreference, ProfileSnapshot
from opportunity_radar.profile.models import CareerProfileModel
from opportunity_radar.profile.service import ProfileService
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
        "check_ai_usage",
        "check_funnel",
    ):
        monkeypatch.setattr(
            doctor,
            name,
            lambda *args, _name=name, **kwargs: Check(_name, doctor.OK, "stub"),
        )

    checks = doctor.run_checks(Path(__file__).parents[2])

    assert not any("embedding" in check.name.casefold() for check in checks)


def _settings(**overrides: object) -> Settings:
    return Settings(database_url="postgresql+psycopg://test:test@localhost/test", **overrides)


_requires_database = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)


def _seed_active_profile(session: Session, owner_sub: str) -> None:
    ProfileService(session, owner_sub).create_active_version(
        ProfileSnapshot(
            skills=(),
            experiences=(),
            projects=(),
            preferences=EmploymentPreference(target_role_families=("DATA",)),
        ),
        expected_profile_version=0,
    )


def _cleanup_profile(session: Session, owner_sub: str) -> None:
    profile = session.scalar(
        select(CareerProfileModel).where(CareerProfileModel.owner_sub == owner_sub)
    )
    if profile is not None:
        session.delete(profile)
        session.commit()


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


def test_check_ai_is_ok_with_only_a_reserve_key_and_lists_it() -> None:
    check = check_ai(_settings(ai_enabled=True, groq_api_key="", gemini_api_key="gk-secret"))

    assert check.status == doctor.OK
    assert "gk-secret" not in str(check.facts) + check.detail
    assert check.facts["providers"]["gemini"]["models"] == 1
    assert check.facts["providers"]["gemini"]["may_retain_prompts"] is True


def test_check_ai_explains_why_workersai_is_left_out() -> None:
    check = check_ai(_settings(ai_enabled=True, groq_api_key="g", workersai_api_key="w-secret"))

    assert check.status == doctor.OK
    assert "w-secret" not in str(check.facts) + check.detail
    assert "CLOUDFLARE_ACCOUNT_ID" in check.facts["excluded"]["workersai"]


def test_check_ai_warns_with_no_key_at_all() -> None:
    check = check_ai(_settings(ai_enabled=True, groq_api_key=""))

    assert check.status == doctor.WARN


def test_check_ai_is_ok_when_enabled_with_a_key() -> None:
    check = check_ai(_settings(ai_enabled=True, groq_api_key="sk-fake"))

    assert check.status == doctor.OK


def test_check_analysis_warns_when_worker_owner_is_missing() -> None:
    check = doctor.check_analysis(_settings(worker_owner_sub="  "))

    assert check.status == doctor.WARN
    assert "WORKER_OWNER_SUB" in check.detail


def test_check_analysis_passes_operational_owner_to_matching_service(monkeypatch) -> None:
    seen: dict[str, str | None] = {}

    class _Matching:
        def __init__(self, session, owner_sub=None) -> None:
            del session
            seen["owner_sub"] = owner_sub

        def count_pending_analysis(self, **kwargs) -> int:
            del kwargs
            return 0

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            del args

    monkeypatch.setattr(doctor, "create_database_engine", lambda _: object())
    monkeypatch.setattr(doctor, "Session", lambda _: _Session())
    monkeypatch.setattr(doctor, "MatchingService", _Matching)
    monkeypatch.setattr(
        doctor,
        "analysis_metrics",
        lambda *args, **kwargs: SimpleNamespace(
            windows=[SimpleNamespace(for_model=lambda _model: None)]
        ),
    )

    check = doctor.check_analysis(_settings(worker_owner_sub="doctor-test-owner"))

    assert check.status == doctor.OK
    assert seen["owner_sub"] == "doctor-test-owner"


def test_check_funnel_warns_when_worker_owner_is_missing() -> None:
    check = doctor.check_funnel(_settings(worker_owner_sub="  "))

    assert check.status == doctor.WARN
    assert "WORKER_OWNER_SUB" in check.detail


def test_check_funnel_uses_operational_owner(monkeypatch) -> None:
    seen: dict[str, object] = {}

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            del args

    class _Profile:
        def __init__(self, session, owner_sub) -> None:
            del session
            seen["owner_sub"] = owner_sub

        def get_active(self):
            return SimpleNamespace(
                snapshot=SimpleNamespace(
                    preferences=SimpleNamespace(target_role_families=("DATA",))
                )
            )

    monkeypatch.setattr(doctor, "create_database_engine", lambda _: object())
    monkeypatch.setattr(doctor, "Session", lambda _: _Session())
    monkeypatch.setattr(doctor, "ProfileService", _Profile)
    monkeypatch.setattr(
        doctor,
        "funnel_report",
        lambda session, *, target_role_families: seen.update(
            {"families": target_role_families}
        ) or object(),
    )
    monkeypatch.setattr(
        doctor,
        "describe_funnel",
        lambda report: Check("funnel", doctor.OK, "stub"),
    )

    check = doctor.check_funnel(_settings(worker_owner_sub="doctor-test-owner"))

    assert check.status == doctor.OK
    assert seen == {"owner_sub": "doctor-test-owner", "families": ("DATA",)}


@pytest.mark.integration
@_requires_database
def test_check_analysis_reads_an_owned_active_profile() -> None:
    owner_sub = f"doctor-test-owner-{os.urandom(8).hex()}"
    settings = Settings(database_url=os.environ["DATABASE_URL"], worker_owner_sub=owner_sub)
    with Session(doctor.create_database_engine(settings.database_url)) as session:
        try:
            _seed_active_profile(session, owner_sub)
            check = doctor.check_analysis(settings)
            assert check.status != doctor.WARN
            assert "WORKER_OWNER_SUB" not in check.detail
        finally:
            _cleanup_profile(session, owner_sub)


@pytest.mark.integration
@_requires_database
def test_check_funnel_reads_an_owned_active_profile() -> None:
    owner_sub = f"doctor-test-owner-{os.urandom(8).hex()}"
    settings = Settings(database_url=os.environ["DATABASE_URL"], worker_owner_sub=owner_sub)
    with Session(doctor.create_database_engine(settings.database_url)) as session:
        try:
            _seed_active_profile(session, owner_sub)
            check = doctor.check_funnel(settings)
            assert check.status != doctor.WARN
            assert "WORKER_OWNER_SUB" not in check.detail
        finally:
            _cleanup_profile(session, owner_sub)


@dataclass(frozen=True)
class _AISettings:
    ai_enabled: bool = True
    groq_api_key_value: str = "gsk_test"
    database_url: str = "postgresql+psycopg://test:test@localhost/test"
    ai_minute_requests_soft_limit: int = 25
    ai_minute_tokens_soft_limit: int = 7_000
    ai_daily_requests_soft_limit: int = 850
    ai_daily_tokens_soft_limit: int = 170_000
    ai_breaker_failures: int = 5
    groq_reasoning_model: str = "openai/gpt-oss-120b"
    groq_fast_model: str = "openai/gpt-oss-20b"
    groq_alt_model: str = "qwen/qwen3.8-27b"
    ai_provider_limits: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def groq_api_key(self) -> object:
        class _Secret:
            def __init__(self, value: str) -> None:
                self._value = value

            def get_secret_value(self) -> str:
                return self._value

        return _Secret(self.groq_api_key_value)


def test_check_ai_skips_everything_when_ai_is_disabled() -> None:
    check = doctor.check_ai_usage(_AISettings(ai_enabled=False))

    assert check.status == doctor.OK
    assert "disabled" in check.detail


def test_check_ai_alerts_when_daily_balance_and_breaker_are_bad(monkeypatch) -> None:
    settings = _AISettings()
    monkeypatch.setattr(doctor, "create_database_engine", lambda _url: object())

    class _StubGuard:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def snapshot(self) -> list[dict]:
            return [
                {
                    "model": settings.groq_reasoning_model,
                    "window_kind": "day",
                    "window_start": doctor.day_window(doctor.datetime.now(doctor.UTC)),
                    "requests": 800,  # 94% of the 850 soft limit
                    "tokens": 1000,
                }
            ]

    monkeypatch.setattr(doctor, "QuotaGuard", _StubGuard)
    monkeypatch.setattr(
        doctor, "_models_with_a_recent_failure_streak", lambda *_a, **_k: {settings.groq_fast_model}
    )
    monkeypatch.setattr(doctor, "Session", lambda _engine: _NullSessionContext())

    check = doctor.check_ai_usage(settings)

    assert check.status == doctor.WARN
    assert settings.groq_reasoning_model in check.detail
    assert settings.groq_fast_model in check.detail
    assert check.remedy is not None


class _NullSessionContext:
    def __enter__(self) -> "_NullSessionContext":
        return self

    def __exit__(self, *args: object) -> None:
        return None
