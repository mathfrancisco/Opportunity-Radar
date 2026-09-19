"""The versioned prompt on disk must stay consistent with the validator that enforces it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opportunity_radar.matching.analysis import (
    ANALYSIS_SCHEMA_VERSION,
    OUTPUT_SCHEMA,
    parse_analysis,
)
from opportunity_radar.matching.prompts import (
    DEFAULT_PROMPT_NAME,
    PROMPT_FAMILY,
    PromptArtifactError,
    load_examples,
    load_prompt,
    prompts_root,
)

_VARIABLES = {
    "schema_version": '"analysis-v1"',
    "deterministic_result": '{"authoritative": true, "verdict": "RECOMMENDED"}',
    "opportunity": '{"work_mode": "REMOTE"}',
    "profile": '{"skills": ["python"]}',
}


def test_default_prompt_loads_with_its_declared_version() -> None:
    prompt = load_prompt()

    assert prompt.version == f"{PROMPT_FAMILY}/{DEFAULT_PROMPT_NAME}"
    assert prompt.metadata["schema_version"] == ANALYSIS_SCHEMA_VERSION
    assert "do not decide eligibility" in prompt.system


def test_output_schema_artifact_matches_the_validator() -> None:
    """A schema that drifts would change model behaviour without changing any check."""
    prompt = load_prompt()
    on_disk = json.loads(
        (prompt.directory / "output.schema.json").read_text(encoding="utf-8")
    )

    assert prompt.output_schema == OUTPUT_SCHEMA
    assert on_disk == OUTPUT_SCHEMA


def test_rendered_user_message_is_a_json_document() -> None:
    rendered = load_prompt().render_user(_VARIABLES)
    payload = json.loads(rendered)

    assert payload["schema_version"] == ANALYSIS_SCHEMA_VERSION
    assert payload["deterministic_result"]["authoritative"] is True
    assert payload["opportunity"] == {"work_mode": "REMOTE"}
    assert payload["profile"] == {"skills": ["python"]}


def test_missing_variable_is_a_load_error_not_a_silent_placeholder() -> None:
    prompt = load_prompt()
    incomplete = {key: value for key, value in _VARIABLES.items() if key != "profile"}

    with pytest.raises(PromptArtifactError, match="profile"):
        prompt.render_user(incomplete)


def test_unused_variable_is_rejected() -> None:
    prompt = load_prompt()

    with pytest.raises(PromptArtifactError, match="unexpected_field"):
        prompt.render_user({**_VARIABLES, "unexpected_field": '"x"'})


def test_unknown_prompt_version_fails_loudly() -> None:
    with pytest.raises(PromptArtifactError, match="prompt directory not found"):
        load_prompt("v99")


def test_metadata_declares_exactly_the_template_variables() -> None:
    prompt = load_prompt()

    assert prompt.variables == tuple(sorted(_VARIABLES))
    assert tuple(sorted(prompt.metadata["variables"])) == prompt.variables


def test_every_example_satisfies_the_output_contract() -> None:
    examples = load_examples()

    assert examples
    for example in examples:
        analysis = parse_analysis(
            example["output"],
            model_id="llama3.2:3b",
            prompt_version=f"{PROMPT_FAMILY}/{DEFAULT_PROMPT_NAME}",
        )
        assert analysis.summary
        assert analysis.schema_version == ANALYSIS_SCHEMA_VERSION


def test_every_declared_artifact_exists() -> None:
    prompt = load_prompt()
    directory: Path = prompt.directory

    for artifact in prompt.metadata["artifacts"]:
        assert (directory / artifact).is_file(), artifact


def test_prompts_root_resolves_to_the_repository_directory() -> None:
    assert (prompts_root() / PROMPT_FAMILY / DEFAULT_PROMPT_NAME).is_dir()
