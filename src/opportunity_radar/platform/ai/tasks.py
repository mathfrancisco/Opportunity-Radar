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


def default_routes(settings: Settings) -> dict[AITask, ModelRoute]:
    effort = settings.ai_reasoning_effort
    table = {
        AITask.JOB_MATCH: ((ModelRole.REASONING, ModelRole.ALT), 5000, 900),
        AITask.JOB_CLASSIFICATION: ((ModelRole.FAST, ModelRole.ALT), 1500, 300),
        AITask.JOB_EXTRACTION: ((ModelRole.FAST, ModelRole.REASONING), 3000, 600),
    }
    return {
        task: ModelRoute(
            task=task,
            chain=tuple(_model_for(settings, role) for role in roles),
            budget=TaskBudget(max_input, max_output, effort),
        )
        for task, (roles, max_input, max_output) in table.items()
    }
