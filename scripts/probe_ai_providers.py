"""Probe each configured AI provider model with one tiny, fixed request.

    python scripts/probe_ai_providers.py
    python scripts/probe_ai_providers.py --provider cerebras --json data/probe.json

It spends one small request (at most 200 completion tokens) per configured model, against
the provider's real quota, and prints one line per model:

    provider model status latency_ms schema_ok rate_headers finish_reason note

`schema_ok` runs the answer through the router's own validator (`make_validator`).
`rate_headers` says whether the response carried any `x-ratelimit-*` header. When a
`json_schema` request is rejected with HTTP 400, the same request is retried with the
provider forced to `json_object`; a success is marked `json_object_only`.

The request is synthetic: no user, profile or job data. Nothing here touches the
database or `QuotaGuard`, and the output carries only the status code or error kind,
never a response body, header or key. This is a diagnostic, so it ignores `AI_ENABLED`;
it needs at least one provider key (`GROQ_API_KEY` or a reserve provider). The exit code
is 0 whenever the script ran: the result is data, not a test.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import httpx

from opportunity_radar.platform.ai.config import (
    configured_providers,
    excluded_providers,
    provider_models,
)
from opportunity_radar.platform.ai.errors import ProviderError
from opportunity_radar.platform.ai.providers.base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    RateLimit,
)
from opportunity_radar.platform.ai.providers.groq import GroqProvider
from opportunity_radar.platform.ai.providers.openai_compat import OpenAICompatibleProvider
from opportunity_radar.platform.ai.providers.registry import ProviderSpec
from opportunity_radar.platform.ai.schema import make_validator
from opportunity_radar.platform.config import Settings

SYSTEM = "Responda só JSON."
USER = "Classifique: 'Vaga de engenheira de dados, remoto, Brasil.'"
WORK_MODES = ("remote", "hybrid", "onsite")
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"work_mode": {"type": "string", "enum": list(WORK_MODES)}},
    "required": ["work_mode"],
    "additionalProperties": False,
}
MAX_COMPLETION_TOKENS = 200
GROQ = "groq"

ClientFactory = Callable[[], AbstractAsyncContextManager[httpx.AsyncClient]]


def _parse(payload: object) -> None:
    if not isinstance(payload, dict) or payload.get("work_mode") not in WORK_MODES:
        raise ValueError("work_mode is missing or outside the enum")


_validate = make_validator(_parse)


@dataclass(frozen=True)
class Target:
    """One model to probe and how to reach it. `spec` is None for Groq."""

    provider: str
    model: str  # as routed: prefixed for reserve providers, bare for Groq
    spec: ProviderSpec | None
    api_key: str
    base_url: str


@dataclass(frozen=True)
class Row:
    provider: str
    model: str
    status: str  # HTTP status, or the error kind when there was none
    latency_ms: int | None
    schema_ok: bool
    rate_headers: bool
    finish_reason: str | None
    note: str


def targets(settings: Settings, only: str | None = None) -> list[Target]:
    """Groq's role models (when keyed) then each usable reserve provider's models."""
    found: list[Target] = []
    groq_key = settings.groq_api_key.get_secret_value()
    if groq_key:
        roles = (
            settings.groq_reasoning_model,
            settings.groq_fast_model,
            settings.groq_alt_model,
        )
        for model in dict.fromkeys(name for name in roles if name):
            found.append(Target(GROQ, model, None, groq_key, settings.groq_base_url))
    for spec, key, base_url in configured_providers(settings):
        for name in provider_models(settings, spec):
            found.append(Target(spec.name, f"{spec.prefix}{name}", spec, key, base_url))
    if only:
        found = [target for target in found if target.provider == only.strip().lower()]
    return found


def _provider(
    target: Target, settings: Settings, client_factory: ClientFactory | None, *, json_object: bool
) -> LLMProvider:
    common: dict[str, Any] = {
        "api_key": target.api_key,
        "base_url": target.base_url,
        "timeout_seconds": settings.ai_timeout_seconds,
        "connect_timeout_seconds": settings.ai_connect_timeout_seconds,
        "client_factory": client_factory,
    }
    if target.spec is None:
        return GroqProvider(**common)
    spec = replace(target.spec, response_format="json_object") if json_object else target.spec
    return OpenAICompatibleProvider(spec, **common)


def _request(model: str) -> LLMRequest:
    return LLMRequest(
        model=model,
        system=SYSTEM,
        user=USER,
        schema_name="probe",
        json_schema=SCHEMA,
        max_completion_tokens=MAX_COMPLETION_TOKENS,
    )


def _has_rate_headers(rate_limit: object) -> bool:
    return isinstance(rate_limit, RateLimit) and any(
        value is not None for value in asdict(rate_limit).values()
    )


def _schema_ok(content: str) -> bool:
    try:
        _validate(content)
    except ProviderError:
        return False
    return True


async def _call(
    provider: LLMProvider, model: str
) -> tuple[LLMResponse | None, ProviderError | None]:
    try:
        return await provider.complete(_request(model)), None
    except ProviderError as error:
        return None, error


def _row(
    target: Target, response: LLMResponse | None, error: ProviderError | None, note: str
) -> Row:
    if response is not None:
        return Row(
            target.provider, target.model, "200", response.latency_ms,
            _schema_ok(response.content), _has_rate_headers(response.rate_limit),
            response.finish_reason, note,
        )
    assert error is not None
    status = str(error.status) if error.status is not None else error.kind.value
    return Row(
        target.provider, target.model, status, error.latency_ms, False,
        _has_rate_headers(error.rate_limit), None, note,
    )


async def probe_target(
    target: Target, settings: Settings, client_factory: ClientFactory | None = None
) -> Row:
    response, error = await _call(
        _provider(target, settings, client_factory, json_object=False), target.model
    )
    note = ""
    if (
        error is not None
        and error.status == 400
        and target.spec is not None
        and target.spec.response_format == "json_schema"
    ):
        retry, _retry_error = await _call(
            _provider(target, settings, client_factory, json_object=True), target.model
        )
        if retry is not None:
            return _row(target, retry, None, "json_object_only")
        note = "json_object_failed"
    return _row(target, response, error, note)


async def probe_all(
    settings: Settings, only: str | None = None, client_factory: ClientFactory | None = None
) -> list[Row]:
    """Probe sequentially, so a provider's per-minute limit sees one request at a time."""
    return [await probe_target(t, settings, client_factory) for t in targets(settings, only)]


_COLUMNS = (
    "provider", "model", "status", "latency_ms", "schema_ok", "rate_headers",
    "finish_reason", "note",
)


def format_table(rows: Sequence[Row]) -> str:
    cells = [list(_COLUMNS)]
    for row in rows:
        cells.append([
            row.provider, row.model, row.status,
            "-" if row.latency_ms is None else str(row.latency_ms),
            "yes" if row.schema_ok else "no", "yes" if row.rate_headers else "no",
            row.finish_reason or "-", row.note or "-",
        ])
    widths = [max(len(line[i]) for line in cells) for i in range(len(_COLUMNS))]
    return "\n".join(
        "  ".join(cell.ljust(width) for cell, width in zip(line, widths, strict=True)).rstrip()
        for line in cells
    )


def main(
    argv: list[str] | None = None,
    *,
    settings: Settings | None = None,
    client_factory: ClientFactory | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", help="probe only this provider name, e.g. cerebras or groq")
    parser.add_argument("--json", type=Path, dest="json_path", help="also write the rows here")
    args = parser.parse_args(argv)
    settings = settings or Settings()  # type: ignore[call-arg]  # values come from the environment

    for name, reason in excluded_providers(settings).items():
        print(f"skipped {name}: {reason}")
    rows: list[Row] = []
    if not targets(settings, args.provider):
        print("no provider to probe: set GROQ_API_KEY or a reserve provider key")
    else:
        rows = asyncio.run(probe_all(settings, args.provider, client_factory))
        print(format_table(rows))
    if args.json_path is not None:
        args.json_path.write_text(
            json.dumps([asdict(row) for row in rows], indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
