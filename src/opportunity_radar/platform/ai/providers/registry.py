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

PROVIDERS: tuple[ProviderSpec, ...] = (TOKENHARBOR,)


def spec_for_model(model: str) -> ProviderSpec | None:
    """The spec whose prefix starts `model`, or `None` for a Groq model."""
    return next((spec for spec in PROVIDERS if model.startswith(spec.prefix)), None)


def provider_name_for(model: str) -> str:
    spec = spec_for_model(model)
    return spec.name if spec is not None else "groq"
