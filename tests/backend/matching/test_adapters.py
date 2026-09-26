import logging
from unittest.mock import MagicMock

import pytest

from opportunity_radar.matching import adapters
from opportunity_radar.matching.adapters import build_analysis_adapter
from opportunity_radar.matching.analysis import NullAnalysisAdapter
from opportunity_radar.matching.groq import GroqAnalysisAdapter
from opportunity_radar.platform.config import Settings


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, database_url="postgresql+psycopg://u@h/db", **overrides)  # type: ignore[call-arg,arg-type]


def _engine() -> MagicMock:
    """A stand-in `Engine`: `build_analysis_adapter` only stores it in the Quota Guard,
    it never opens a connection at construction time."""
    return MagicMock()


def test_disabled_builds_null_adapter() -> None:
    assert isinstance(build_analysis_adapter(_settings(), _engine()), NullAnalysisAdapter)


def test_blocked_builds_null_adapter_and_warns_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(adapters, "_missing_key_warned", False)
    settings = _settings(ai_enabled=True)

    with caplog.at_level(logging.WARNING):
        first = build_analysis_adapter(settings, _engine())
        build_analysis_adapter(settings, _engine())

    assert isinstance(first, NullAnalysisAdapter)
    assert [r.getMessage() for r in caplog.records].count("groq api key missing") == 1


def test_enabled_builds_groq_adapter() -> None:
    settings = _settings(ai_enabled=True, groq_api_key="k")

    adapter = build_analysis_adapter(settings, _engine())

    assert isinstance(adapter, GroqAnalysisAdapter)
    assert adapter.model == settings.groq_reasoning_model
    assert adapter.prompt_version.endswith(settings.ai_analysis_prompt)
