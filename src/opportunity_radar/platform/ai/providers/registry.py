"""Declarative registry of the OpenAI-compatible providers beside Groq.

Each `ProviderSpec` names one backend and the model-name prefix that routes to it; this is
the single place that knows prefixes. A model without a registered prefix belongs to Groq.
The facts below hold for every spec and are carried by `OpenAICompatibleProvider`:

* The prefix never reaches the API, and the response is labelled with the prefixed name, so
  quota, breaker and telemetry all see one identity.
* A backend may not send `x-ratelimit-*` headers: the quota guard then runs on the
  project's own soft limits alone.
* A free backend may retain prompts and responses (`may_retain_prompts`); the payload is
  already stripped by `sanitize_for_llm` before it gets here.

Token Harbor, checked against the live API on 2026-10-05 with `deepseek-v4.1-flash:free`
and `mimo-v2.6-flash:free`: `response_format` with a JSON schema is accepted but not
enforced (the router's validator and its repair turn cover that), and a 429 carries
`Retry-After`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from opportunity_radar.platform.ai.quota import QuotaLimits


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    #: Marks a model name in a route as served by this provider.
    prefix: str
    default_base_url: str
    #: Whether the backend accepts `reasoning_effort`.
    reasoning_effort: bool
    response_format: Literal["json_schema", "json_object"]
    #: Soft per-model limits when the backend sends no `x-ratelimit-*` headers.
    default_limits: QuotaLimits | None
    #: The vendor's own daily request cap, when known.
    provider_day_requests: int | None
    may_retain_prompts: bool


TOKENHARBOR = ProviderSpec(
    name="tokenharbor",
    prefix="tokenharbor:",
    default_base_url="https://tokenharbor.ai/v1",
    reasoning_effort=True,
    response_format="json_schema",
    default_limits=None,
    provider_day_requests=None,
    may_retain_prompts=True,
)

# Defaults below follow docs/research/2026-10-20-llm-gratuitos.md. `response_format` and
# `reasoning_effort` are first guesses that the probe script confirms per model.
CEREBRAS = ProviderSpec(
    name="cerebras",
    prefix="cerebras:",
    default_base_url="https://api.cerebras.ai/v1",
    reasoning_effort=True,
    response_format="json_schema",
    default_limits=QuotaLimits(4, 80_000, 900, 950_000),
    provider_day_requests=None,
    may_retain_prompts=False,
)

ZEN = ProviderSpec(
    name="zen",
    prefix="zen:",
    default_base_url="https://opencode.ai/inference/openai/v1",
    reasoning_effort=False,
    response_format="json_schema",
    default_limits=QuotaLimits(20, 60_000, 300, 1_500_000),
    provider_day_requests=None,
    may_retain_prompts=False,
)

GEMINI = ProviderSpec(
    name="gemini",
    prefix="gemini:",
    default_base_url="https://generativelanguage.googleapis.com/v1beta/openai",
    reasoning_effort=False,
    response_format="json_schema",
    default_limits=QuotaLimits(10, 60_000, 500, 1_000_000),
    provider_day_requests=None,
    may_retain_prompts=True,
)

OPENROUTER = ProviderSpec(
    name="openrouter",
    prefix="openrouter:",
    default_base_url="https://openrouter.ai/api/v1",
    reasoning_effort=False,
    response_format="json_schema",
    default_limits=QuotaLimits(15, 60_000, 45, 300_000),
    provider_day_requests=50,
    may_retain_prompts=True,
)

MISTRAL = ProviderSpec(
    name="mistral",
    prefix="mistral:",
    default_base_url="https://api.mistral.ai/v1",
    reasoning_effort=False,
    response_format="json_schema",
    default_limits=QuotaLimits(20, 60_000, 500, 1_000_000),
    provider_day_requests=None,
    may_retain_prompts=True,
)

NIM = ProviderSpec(
    name="nim",
    prefix="nim:",
    default_base_url="https://integrate.api.nvidia.com/v1",
    reasoning_effort=True,
    response_format="json_schema",
    default_limits=QuotaLimits(30, 60_000, 1_000, 1_000_000),
    provider_day_requests=None,
    may_retain_prompts=True,
)

WORKERSAI = ProviderSpec(
    name="workersai",
    prefix="workersai:",
    default_base_url="https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
    reasoning_effort=False,
    response_format="json_schema",
    default_limits=QuotaLimits(20, 60_000, 40, 250_000),
    provider_day_requests=None,
    may_retain_prompts=False,
)

PROVIDERS: tuple[ProviderSpec, ...] = (
    TOKENHARBOR,
    CEREBRAS,
    ZEN,
    GEMINI,
    OPENROUTER,
    MISTRAL,
    NIM,
    WORKERSAI,
)


def spec_for_model(model: str) -> ProviderSpec | None:
    """The spec whose prefix starts `model`, or `None` for a Groq model."""
    return next((spec for spec in PROVIDERS if model.startswith(spec.prefix)), None)


def provider_name_for(model: str) -> str:
    spec = spec_for_model(model)
    return spec.name if spec is not None else "groq"
