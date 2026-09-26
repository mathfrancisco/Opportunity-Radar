"""Strict-mode schema compatibility and the response validator built on it (F20-14)."""

from __future__ import annotations

import pytest

from opportunity_radar.matching.analysis import (
    ANALYSIS_SCHEMA_V2,
    ANALYSIS_SCHEMA_VERSION,
    OUTPUT_SCHEMAS,
    parse_analysis,
)
from opportunity_radar.platform.ai.errors import ErrorKind, ProviderError
from opportunity_radar.platform.ai.schema import make_validator, strict_compatible


@pytest.mark.parametrize("version", [ANALYSIS_SCHEMA_VERSION, ANALYSIS_SCHEMA_V2])
def test_output_schemas_are_strict_compatible(version: str) -> None:
    assert strict_compatible(OUTPUT_SCHEMAS[version]) == []


def test_object_without_additional_properties_false_is_reported() -> None:
    schema = {
        "type": "object",
        "properties": {"a": {"type": "string"}},
        "required": ["a"],
    }
    problems = strict_compatible(schema)
    assert any("additionalProperties" in p for p in problems)


def test_property_missing_from_required_is_reported() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
        "required": ["a"],
    }
    problems = strict_compatible(schema)
    assert any("properties.b" in p and "not in required" in p for p in problems)


def test_walks_nested_objects_in_items_and_defs() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["items"],
        "properties": {
            "items": {
                "type": "array",
                "items": {"$ref": "#/$defs/Item"},
            }
        },
        "$defs": {
            "Item": {
                "type": "object",
                "properties": {"claim": {"type": "string"}},
                # Missing additionalProperties: false and missing from required.
            }
        },
    }
    problems = strict_compatible(schema)
    assert any("$defs.Item" in p and "additionalProperties" in p for p in problems)
    assert any("$defs.Item.properties.claim" in p and "not in required" in p for p in problems)


def test_fully_compatible_schema_has_no_problems() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["a"],
        "properties": {"a": {"type": "string"}},
    }
    assert strict_compatible(schema) == []


def _parse(model_id: str = "test-model", prompt_version: str = "v2"):
    def parse(payload: object) -> object:
        return parse_analysis(
            payload,
            model_id=model_id,
            prompt_version=prompt_version,
            schema_version=ANALYSIS_SCHEMA_VERSION,
        )

    return parse


def test_make_validator_accepts_valid_json_matching_schema() -> None:
    validator = make_validator(_parse())
    validator(
        '{"summary": "ok", "strengths": [], "risks": [], "inferences": [], '
        '"unknowns": [], "recommended_review": false}'
    )


def test_make_validator_rejects_broken_json() -> None:
    validator = make_validator(_parse())
    with pytest.raises(ProviderError) as excinfo:
        validator("{not json")
    assert excinfo.value.kind is ErrorKind.INVALID_OUTPUT


def test_make_validator_rejects_missing_field() -> None:
    validator = make_validator(_parse())
    with pytest.raises(ProviderError) as excinfo:
        validator('{"summary": "ok"}')
    assert excinfo.value.kind is ErrorKind.INVALID_OUTPUT


def test_make_validator_rejects_wrong_type() -> None:
    validator = make_validator(_parse())
    with pytest.raises(ProviderError) as excinfo:
        validator(
            '{"summary": 123, "strengths": [], "risks": [], "inferences": [], '
            '"unknowns": [], "recommended_review": false}'
        )
    assert excinfo.value.kind is ErrorKind.INVALID_OUTPUT


def test_make_validator_error_summary_never_contains_raw_response() -> None:
    validator = make_validator(_parse())
    secret_marker = "SECRET_TOKEN_MARKER_ABC123"
    with pytest.raises(ProviderError) as excinfo:
        validator(f'{{"summary": "{secret_marker}"')  # broken JSON containing the marker
    assert secret_marker not in excinfo.value.summary
