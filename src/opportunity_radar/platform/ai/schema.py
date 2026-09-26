"""Strict-mode JSON Schema compatibility and response validation (card F20-14).

Groq's `strict: true` decoding (SPEC 43 section 4.2) requires every object in the
schema to close over its properties (`additionalProperties: false`) and to require
every property it declares — an optional field must be modeled as a nullable type that
stays in `required`, never as an absent key. `strict_compatible` checks a schema for
these rules without changing it; `make_validator` wraps a parser (such as
`matching.analysis.parse_analysis`) into the single-string-in, raise-or-nothing shape
the router expects when a model answers.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from opportunity_radar.platform.ai.errors import ErrorKind, ProviderError

#: Maximum length of a summary embedded in a `ProviderError` so a huge or adversarial
#: payload never blows up a log line or a persisted error message.
_MAX_ERROR_SUMMARY = 200


def strict_compatible(schema: Mapping[str, Any]) -> list[str]:
    """List of problems that keep `schema` from being valid under strict decoding.

    Walks every object in the schema — `properties`, `items` (single schema or tuple
    form), and `$defs` — and reports, per JSON Pointer-ish path, an object missing
    `additionalProperties: false` or a declared property absent from `required`. An
    empty list means the schema is strict-compatible as-is.
    """
    problems: list[str] = []
    _walk(schema, "$", problems)
    return problems


def _walk(node: Any, path: str, problems: list[str]) -> None:
    if isinstance(node, Mapping):
        if node.get("type") == "object" or "properties" in node:
            properties = node.get("properties")
            if isinstance(properties, Mapping) and properties:
                if node.get("additionalProperties") is not False:
                    problems.append(f"{path}: object missing additionalProperties: false")
                required = node.get("required")
                required_set = set(required) if isinstance(required, Sequence) else set()
                for name in properties:
                    if name not in required_set:
                        problems.append(f"{path}.properties.{name}: not in required")
                for name, subschema in properties.items():
                    _walk(subschema, f"{path}.properties.{name}", problems)
        items = node.get("items")
        if isinstance(items, Mapping):
            _walk(items, f"{path}.items", problems)
        elif isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
            for index, item in enumerate(items):
                _walk(item, f"{path}.items[{index}]", problems)
        for keyword in ("$defs", "definitions"):
            defs = node.get(keyword)
            if isinstance(defs, Mapping):
                for name, subschema in defs.items():
                    _walk(subschema, f"{path}.{keyword}.{name}", problems)
        for keyword in ("anyOf", "oneOf", "allOf"):
            variants = node.get(keyword)
            if isinstance(variants, Sequence) and not isinstance(variants, (str, bytes)):
                for index, variant in enumerate(variants):
                    _walk(variant, f"{path}.{keyword}[{index}]", problems)


def make_validator(parse: Callable[[Any], object]) -> Callable[[str], None]:
    """Wrap `parse` into a function the router calls with the raw model response text.

    `parse` receives the decoded JSON object and should raise on a mismatch (as
    `matching.analysis.parse_analysis` does); its return value is discarded here — the
    router keeps the model output for the caller to parse again with full context
    (model id, prompt version). Any failure, JSON or schema, becomes a `ProviderError`
    with kind `INVALID_OUTPUT` and a short summary, never the raw response.
    """

    def validate(content: str) -> None:
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ProviderError(
                ErrorKind.INVALID_OUTPUT,
                f"response is not valid JSON: {_short(exc)}",
            ) from exc
        try:
            parse(payload)
        except Exception as exc:  # noqa: BLE001 - any parse failure is INVALID_OUTPUT
            raise ProviderError(
                ErrorKind.INVALID_OUTPUT,
                f"response does not match the output schema: {_short(exc)}",
            ) from exc

    return validate


def _short(exc: Exception) -> str:
    text = str(exc)
    return text if len(text) <= _MAX_ERROR_SUMMARY else text[:_MAX_ERROR_SUMMARY] + "…"


__all__: Sequence[str] = ("make_validator", "strict_compatible")
