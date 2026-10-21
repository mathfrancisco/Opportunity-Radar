"""The provider probe: its table, the json_object retry and that it never prints a key."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from opportunity_radar.platform.config import Settings
from scripts import probe_ai_providers as probe

_KEY = "csk-super-secret-key-123"
_GOOD = {
    "model": "gpt-oss-120b",
    "choices": [{"message": {"content": '{"work_mode": "remote"}'}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 20, "completion_tokens": 5},
}


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {"database_url": "postgresql+psycopg://u:p@localhost/db"}
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[call-arg]


def _factory(handler: Callable[[httpx.Request], httpx.Response]) -> Any:
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_probe_marks_json_object_only_on_schema_400(capsys: pytest.CaptureFixture[str]) -> None:
    formats: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        formats.append(body["response_format"]["type"])
        if body["response_format"]["type"] == "json_schema":
            return httpx.Response(400, json={"error": "response_format unsupported"})
        return httpx.Response(200, json=_GOOD, headers={"x-ratelimit-limit-requests": "50"})

    settings = _settings(cerebras_api_key=_KEY, cerebras_models="gpt-oss-120b")
    code = probe.main(
        ["--provider", "cerebras"], settings=settings, client_factory=_factory(handler)
    )

    out = capsys.readouterr().out
    assert code == 0
    assert formats == ["json_schema", "json_object"]
    line = next(line for line in out.splitlines() if "cerebras:gpt-oss-120b" in line)
    assert "json_object_only" in line
    assert "200" in line and "stop" in line


def test_probe_never_prints_key(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=f"bad key {_KEY}", headers={"x-echo": _KEY})

    out_path = tmp_path / "probe.json"
    settings = _settings(cerebras_api_key=_KEY, cerebras_models="gpt-oss-120b")
    code = probe.main(
        ["--json", str(out_path)], settings=settings, client_factory=_factory(handler)
    )

    captured = capsys.readouterr()
    assert code == 0
    assert _KEY not in captured.out + captured.err
    assert _KEY not in out_path.read_text(encoding="utf-8")
    assert "401" in captured.out
    rows = json.loads(out_path.read_text(encoding="utf-8"))
    assert rows[0]["provider"] == "cerebras"
    assert rows[0]["schema_ok"] is False


def test_probe_skips_unconfigured_providers(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_GOOD)

    settings = _settings(cerebras_api_key=_KEY, cerebras_models="gpt-oss-120b")
    probe.main([], settings=settings, client_factory=_factory(handler))

    out = capsys.readouterr().out
    assert "cerebras" in out
    assert "openrouter" not in out


def test_probe_probes_groq_models_deduplicated_and_flags_schema_mismatch(
    capsys: pytest.CaptureFixture[str],
) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content)["model"])
        content = '{"work_mode": "moon"}'
        return httpx.Response(
            200, json={"model": "x", "choices": [{"message": {"content": content}}]}
        )

    settings = _settings(
        groq_api_key="gsk-key",
        groq_reasoning_model="a",
        groq_fast_model="b",
        groq_alt_model="a",
    )
    probe.main([], settings=settings, client_factory=_factory(handler))

    out = capsys.readouterr().out
    assert seen == ["a", "b"]
    lines = [line for line in out.splitlines() if line.startswith("groq")]
    assert len(lines) == 2
    assert all(" no " in line for line in lines)  # schema_ok and rate_headers both "no"


def test_probe_without_any_key_prints_a_hint_and_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = probe.main([], settings=_settings())

    assert code == 0
    assert "no provider to probe" in capsys.readouterr().out


def test_target_repr_hides_the_api_key() -> None:
    settings = _settings(cerebras_api_key=_KEY, cerebras_models="gpt-oss-120b")

    target = probe.targets(settings)[0]

    assert _KEY not in repr(target)
    assert target.api_key == _KEY


def test_probe_records_an_unexpected_exception_by_class_and_finishes(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        calls.append(model)
        if model == "gpt-oss-120b":
            raise RuntimeError(f"boom {_KEY}")
        return httpx.Response(200, json=_GOOD)

    out_path = tmp_path / "probe.json"
    settings = _settings(cerebras_api_key=_KEY, cerebras_models="gpt-oss-120b,qwen-3.8-27b")
    code = probe.main(
        ["--json", str(out_path)], settings=settings, client_factory=_factory(handler)
    )

    captured = capsys.readouterr()
    rows = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert [row["status"] for row in rows] == ["error:RuntimeError", "200"]
    assert calls == ["gpt-oss-120b", "qwen-3.8-27b"]
    assert "boom" not in captured.out + captured.err + out_path.read_text(encoding="utf-8")
    assert _KEY not in captured.out + captured.err + out_path.read_text(encoding="utf-8")
