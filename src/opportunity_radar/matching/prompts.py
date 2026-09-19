"""Loader for the versioned prompt artifacts under `prompts/`.

Section 42 of docs/29-roadmap-mvp.md keeps the prompt outside the code so a change of
wording is a reviewable, versioned artifact instead of an edited string literal.

The loader is deliberately strict. A prompt that silently loses a variable, or an
`output.schema.json` that drifts from `matching.analysis.OUTPUT_SCHEMA`, would change
model behaviour without changing any validator, so both are load-time failures.

`user.md.j2` keeps the Jinja extension for the documented layout, but only `{{ name }}`
substitution is supported: the payload is a single JSON document, so loops and
conditionals would add a dependency and a source of non-determinism for nothing. Every
value is substituted already JSON-encoded, which is what makes the rendered template a
valid JSON document.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from opportunity_radar.matching.analysis import ANALYSIS_SCHEMA_VERSION, OUTPUT_SCHEMA

PROMPT_FAMILY = "opportunity_analysis"
DEFAULT_PROMPT_NAME = "v1"

_SYSTEM_FILE = "system.md"
_USER_FILE = "user.md.j2"
_SCHEMA_FILE = "output.schema.json"
_EXAMPLES_FILE = "examples.json"
_METADATA_FILE = "metadata.yaml"

_PLACEHOLDER = re.compile(r"{{\s*([a-z_][a-z0-9_]*)\s*}}")


class PromptArtifactError(RuntimeError):
    """The prompt on disk is missing, unreadable or inconsistent with the code."""


@dataclass(frozen=True)
class PromptArtifacts:
    """One immutable, versioned prompt as loaded from disk."""

    version: str
    system: str
    user_template: str
    output_schema: dict[str, Any]
    metadata: dict[str, Any]
    directory: Path

    @property
    def variables(self) -> tuple[str, ...]:
        return tuple(sorted(set(_PLACEHOLDER.findall(self.user_template))))

    def render_user(self, values: Mapping[str, str]) -> str:
        """Substitute every placeholder. Unused or unknown names are errors, not silence."""
        declared = set(self.variables)
        provided = set(values)
        missing = sorted(declared - provided)
        if missing:
            raise PromptArtifactError(
                f"{self.version} user template needs values for: {', '.join(missing)}"
            )
        unused = sorted(provided - declared)
        if unused:
            raise PromptArtifactError(
                f"{self.version} user template does not use: {', '.join(unused)}"
            )
        return _PLACEHOLDER.sub(lambda match: values[match.group(1)], self.user_template)


def prompts_root() -> Path:
    """Repository `prompts/` directory, whether running from source or from the image."""
    candidates = (
        Path.cwd() / "prompts",
        Path(__file__).resolve().parents[3] / "prompts",
    )
    return next((path for path in candidates if path.is_dir()), candidates[0])


@lru_cache(maxsize=8)
def load_prompt(
    name: str = DEFAULT_PROMPT_NAME,
    *,
    root: Path | None = None,
) -> PromptArtifacts:
    directory = (root or prompts_root()) / PROMPT_FAMILY / name
    if not directory.is_dir():
        raise PromptArtifactError(f"prompt directory not found: {directory}")

    version = f"{PROMPT_FAMILY}/{name}"
    system = _read_text(directory / _SYSTEM_FILE)
    user_template = _read_text(directory / _USER_FILE)
    output_schema = _read_json(directory / _SCHEMA_FILE)
    metadata = _read_metadata(directory / _METADATA_FILE)

    if output_schema != OUTPUT_SCHEMA:
        raise PromptArtifactError(
            f"{version} output.schema.json drifted from matching.analysis.OUTPUT_SCHEMA; "
            "regenerate it with scripts/export_prompt_schema.py"
        )
    if metadata.get("prompt_version") != version:
        raise PromptArtifactError(
            f"{version} metadata declares prompt_version "
            f"{metadata.get('prompt_version')!r}"
        )
    if metadata.get("schema_version") != ANALYSIS_SCHEMA_VERSION:
        raise PromptArtifactError(
            f"{version} metadata declares schema_version "
            f"{metadata.get('schema_version')!r}, expected {ANALYSIS_SCHEMA_VERSION!r}"
        )

    artifacts = PromptArtifacts(
        version=version,
        system=system,
        user_template=user_template,
        output_schema=output_schema,
        metadata=metadata,
        directory=directory,
    )
    declared = tuple(metadata.get("variables") or ())
    if tuple(sorted(declared)) != artifacts.variables:
        raise PromptArtifactError(
            f"{version} metadata lists variables {sorted(declared)} but the template uses "
            f"{list(artifacts.variables)}"
        )
    return artifacts


def load_examples(
    name: str = DEFAULT_PROMPT_NAME,
    *,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Reference outputs. Read by tests, not by the adapter."""
    directory = (root or prompts_root()) / PROMPT_FAMILY / name
    examples = _read_json(directory / _EXAMPLES_FILE, expect=list)
    if not isinstance(examples, list):  # pragma: no cover - guarded by _read_json
        raise PromptArtifactError(f"{directory / _EXAMPLES_FILE} must hold a JSON array")
    return examples


def _read_text(path: Path) -> str:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise PromptArtifactError(f"cannot read prompt artifact: {path}") from error
    if not content.strip():
        raise PromptArtifactError(f"prompt artifact is empty: {path}")
    return content.strip()


def _read_json(path: Path, *, expect: type = dict) -> Any:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise PromptArtifactError(f"cannot read prompt artifact: {path}") from error
    except ValueError as error:
        raise PromptArtifactError(f"prompt artifact is not valid JSON: {path}") from error
    if not isinstance(payload, expect):
        raise PromptArtifactError(f"prompt artifact has the wrong JSON type: {path}")
    return payload


def _read_metadata(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise PromptArtifactError(f"cannot read prompt artifact: {path}") from error
    except yaml.YAMLError as error:
        raise PromptArtifactError(f"prompt artifact is not valid YAML: {path}") from error
    if not isinstance(payload, dict):
        raise PromptArtifactError(f"prompt metadata must be a mapping: {path}")
    return payload


__all__ = [
    "DEFAULT_PROMPT_NAME",
    "PROMPT_FAMILY",
    "PromptArtifactError",
    "PromptArtifacts",
    "load_examples",
    "load_prompt",
    "prompts_root",
]
