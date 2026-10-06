"""Token Harbor chat-completion client: a second, free provider beside Groq.

Its `/v1/chat/completions` is OpenAI-compatible, so the request and the response are the
ones `GroqProvider` already builds and reads. What differs, checked against the live API on
2026-10-05 with `deepseek-v4.1-flash:free` and `mimo-v2.6-flash:free`:

* A route names its models with the `tokenharbor:` prefix, which is how the routed provider
  tells the two backends apart. The prefix never reaches the API, and the response is
  labelled with the prefixed name, so quota, breaker and telemetry all see one identity.
* `response_format` with a JSON schema is accepted but not enforced (an enum came back in
  another case). The router's validator and its repair turn cover that.
* No `x-ratelimit-*` headers: the quota guard runs on the project's own soft limits alone.
  A 429 carries `Retry-After`.

Free models are opt-in on the account, and the vendor may retain their prompts and
responses; the payload is already stripped by `sanitize_for_llm` before it gets here.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from opportunity_radar.platform.ai.providers.base import LLMRequest, LLMResponse
from opportunity_radar.platform.ai.providers.groq import GroqProvider

#: Marks a model name in a route as served by Token Harbor.
MODEL_PREFIX = "tokenharbor:"


class TokenHarborProvider(GroqProvider):
    """`LLMProvider` for Token Harbor's OpenAI-compatible endpoint."""

    name = "tokenharbor"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        response = await super().complete(request)
        return replace(response, model=request.model)

    def _body(self, request: LLMRequest) -> dict[str, Any]:
        return super()._body(replace(request, model=request.model.removeprefix(MODEL_PREFIX)))
