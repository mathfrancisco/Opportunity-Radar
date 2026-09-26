import logging

import pytest

from opportunity_radar.matching import adapters
from opportunity_radar.matching.adapters import build_analysis_adapter
from opportunity_radar.matching.analysis import NullAnalysisAdapter
from opportunity_radar.matching.ollama import OllamaAnalysisAdapter
from opportunity_radar.platform.config import Settings


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, database_url="postgresql+psycopg://u@h/db", **overrides)  # type: ignore[call-arg,arg-type]


def test_disabled_builds_null_adapter() -> None:
    assert isinstance(
        build_analysis_adapter(_settings(ollama_analysis_enabled=True)), NullAnalysisAdapter
    )


def test_blocked_builds_null_adapter_and_warns_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(adapters, "_missing_key_warned", False)
    settings = _settings(ai_enabled=True, ollama_analysis_enabled=True)

    with caplog.at_level(logging.WARNING):
        first = build_analysis_adapter(settings)
        build_analysis_adapter(settings)

    assert isinstance(first, NullAnalysisAdapter)
    assert [r.getMessage() for r in caplog.records].count("groq api key missing") == 1


def test_enabled_keeps_current_adapter_until_groq_adapter_exists() -> None:
    settings = _settings(ai_enabled=True, groq_api_key="k", ollama_analysis_enabled=True)

    assert isinstance(build_analysis_adapter(settings), OllamaAnalysisAdapter)
