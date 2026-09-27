"""The versioned prompt on disk must stay consistent with the validator that enforces it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opportunity_radar.matching.analysis import (
    ANALYSIS_SCHEMA_V2,
    ANALYSIS_SCHEMA_VERSION,
    OUTPUT_SCHEMA,
    OUTPUT_SCHEMAS,
    AnalysisError,
    item_evidence,
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

_VARIABLES_V2 = {
    "schema_version": '"analysis-v2"',
    "deterministic_result": '{"authoritative": true, "verdict": "RECOMMENDED"}',
    "opportunity": '{"work_mode": "REMOTE"}',
    "posting": '{"title": "Backend Sr"}',
    "profile": '{"skills": ["python"]}',
    "profile_history": '{"experiences": []}',
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


# --- F20-18: prompt v2 reads the posting and the profile history, pt-BR with evidence --


def test_v2_loads_and_declares_posting_and_profile_history() -> None:
    prompt = load_prompt("v2")

    assert prompt.version == f"{PROMPT_FAMILY}/v2"
    assert prompt.metadata["schema_version"] == ANALYSIS_SCHEMA_V2
    assert "posting" in prompt.variables
    assert "profile_history" in prompt.variables
    assert prompt.reads_profile_history is True


def test_v2_output_schema_matches_the_v2_validator() -> None:
    prompt = load_prompt("v2")
    on_disk = json.loads(
        (prompt.directory / "output.schema.json").read_text(encoding="utf-8")
    )

    assert prompt.output_schema == OUTPUT_SCHEMAS[ANALYSIS_SCHEMA_V2]
    assert on_disk == OUTPUT_SCHEMAS[ANALYSIS_SCHEMA_V2]


def test_v2_rendered_user_message_carries_posting_and_profile_history() -> None:
    rendered = load_prompt("v2").render_user(_VARIABLES_V2)
    payload = json.loads(rendered)

    assert payload["schema_version"] == ANALYSIS_SCHEMA_V2
    assert payload["posting"] == {"title": "Backend Sr"}
    assert payload["profile_history"] == {"experiences": []}
    assert payload["profile"] == {"skills": ["python"]}


def test_v2_metadata_declares_exactly_the_template_variables() -> None:
    prompt = load_prompt("v2")

    assert prompt.variables == tuple(sorted(_VARIABLES_V2))
    assert tuple(sorted(prompt.metadata["variables"])) == prompt.variables


def test_v2_every_declared_artifact_exists() -> None:
    prompt = load_prompt("v2")
    directory: Path = prompt.directory

    for artifact in prompt.metadata["artifacts"]:
        assert (directory / artifact).is_file(), artifact


def test_v2_every_example_satisfies_the_output_contract_with_its_own_evidence() -> None:
    """Each example's claimed evidence must literally appear in the block its own
    `posting`/`profile` payload would have sent (card F20-18's acceptance rule)."""
    examples = load_examples("v2")

    assert examples
    sources = {
        "posting": "Não informamos a faixa salarial nesta etapa",
        "profile": "3 anos como desenvolvedor Python e PostgreSQL",
    }
    for example in examples:
        analysis = parse_analysis(
            example["output"],
            model_id="openai/gpt-oss-120b",
            prompt_version=f"{PROMPT_FAMILY}/v2",
            schema_version=ANALYSIS_SCHEMA_V2,
            evidence_sources=sources,
        )
        assert analysis.summary
        assert analysis.schema_version == ANALYSIS_SCHEMA_V2
        for item in (*analysis.strengths, *analysis.risks):
            evidence, source = item_evidence(item)
            assert (evidence is None) == (source is None)


def test_v2_claim_with_evidence_absent_from_the_source_is_rejected() -> None:
    """Acceptance criterion: a claim quoting a passage that is not in the payload sent
    is discarded and counted as a schema mismatch (current `parse_analysis` behaviour,
    unchanged by this card)."""
    payload = {
        "summary": "Resumo.",
        "strengths": [
            {
                "claim": "Experiência compatível",
                "evidence": "trecho que não existe em nenhum bloco enviado",
                "source": "profile",
            }
        ],
        "risks": [],
        "inferences": [],
        "unknowns": [],
        "recommended_review": False,
    }

    with pytest.raises(AnalysisError, match="quotes evidence absent"):
        parse_analysis(
            payload,
            model_id="openai/gpt-oss-120b",
            prompt_version=f"{PROMPT_FAMILY}/v2",
            schema_version=ANALYSIS_SCHEMA_V2,
            evidence_sources={"profile": "experiência real e diferente do trecho citado"},
        )
