"""AI tasks and their model routes (SPEC 43, section 6).

Model names live only in `Settings`: changing the model for a task is configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from opportunity_radar.platform.config import Settings


class AITask(StrEnum):
    JOB_MATCH = "job_match"
    JOB_CLASSIFICATION = "job_classification"
    JOB_EXTRACTION = "job_extraction"


class ModelRole(StrEnum):
    REASONING = "reasoning"
    FAST = "fast"
    ALT = "alt"


@dataclass(frozen=True)
class TaskBudget:
    max_input_tokens: int
    max_output_tokens: int
    reasoning_effort: str


@dataclass(frozen=True)
class ModelRoute:
    task: AITask
    chain: tuple[str, ...]  # resolved model names, in order of preference
    budget: TaskBudget


def _model_for(settings: Settings, role: ModelRole) -> str:
    return {
        ModelRole.REASONING: settings.groq_reasoning_model,
        ModelRole.FAST: settings.groq_fast_model,
        ModelRole.ALT: settings.groq_alt_model,
    }[role]


def _effort_for(settings: Settings, task: AITask) -> str:
    """The task's `reasoning_effort`: its own override (card F20-22) or the shared default.

    Every override defaults to `None`, so this returns `settings.ai_reasoning_effort` for
    every task until a benchmark decision sets one explicitly — a no-op by construction.
    """
    override = {
        AITask.JOB_MATCH: settings.ai_reasoning_effort_job_match,
        AITask.JOB_CLASSIFICATION: settings.ai_reasoning_effort_job_classification,
        AITask.JOB_EXTRACTION: settings.ai_reasoning_effort_job_extraction,
    }[task]
    return override or settings.ai_reasoning_effort


#: Output ceiling of `job_match` under the analysis prompts whose schema caps each list
#: (card F50-09); every other prompt keeps the default below.
_JOB_MATCH_OUTPUT_BY_PROMPT = {"v3": 600}


def default_routes(settings: Settings) -> dict[AITask, ModelRoute]:
    job_match_output = _JOB_MATCH_OUTPUT_BY_PROMPT.get(settings.ai_analysis_prompt, 900)
    table = {
        AITask.JOB_MATCH: ((ModelRole.REASONING, ModelRole.ALT), 5000, job_match_output),
        AITask.JOB_CLASSIFICATION: ((ModelRole.FAST, ModelRole.ALT), 1500, 300),
        AITask.JOB_EXTRACTION: ((ModelRole.FAST, ModelRole.REASONING), 3000, 600),
    }
    return {
        task: ModelRoute(
            task=task,
            chain=tuple(_model_for(settings, role) for role in roles),
            budget=TaskBudget(max_input, max_output, _effort_for(settings, task)),
        )
        for task, (roles, max_input, max_output) in table.items()
    }
