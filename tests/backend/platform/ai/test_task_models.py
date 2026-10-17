"""Card R55-C4: the model per task. Names live in `Settings`, the table only picks roles."""

from __future__ import annotations

from opportunity_radar.platform.ai.tasks import AITask, default_routes
from opportunity_radar.platform.config import Settings


def _settings(**overrides: object) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None, database_url="postgresql+psycopg://u@h/db", **overrides
    )


def test_fit_analysis_uses_the_120b_and_the_cheap_tasks_use_the_20b() -> None:
    routes = default_routes(_settings())

    assert routes[AITask.JOB_MATCH].chain[0] == "openai/gpt-oss-120b"
    assert routes[AITask.JOB_CLASSIFICATION].chain[0] == "openai/gpt-oss-20b"
    assert routes[AITask.JOB_EXTRACTION].chain[0] == "openai/gpt-oss-20b"


def test_only_fit_analysis_may_be_the_first_choice_of_the_120b() -> None:
    routes = default_routes(_settings())
    big = _settings().groq_reasoning_model

    first_choice = [task for task, route in routes.items() if route.chain[0] == big]

    assert first_choice == [AITask.JOB_MATCH]


def test_every_task_keeps_a_fallback_behind_its_first_choice() -> None:
    for route in default_routes(_settings()).values():
        assert len(route.chain) >= 2
        assert len(set(route.chain)) == len(route.chain)
