import math

from opportunity_radar.platform.ai.budget import (
    DEFAULT_CHARS_PER_TOKEN,
    DEFAULT_MARGIN,
    estimate_tokens,
    fits,
)
from opportunity_radar.platform.ai.tasks import TaskBudget

_BUDGET = TaskBudget(max_input_tokens=100, max_output_tokens=20, reasoning_effort="low")


def test_estimate_tokens_applies_the_default_margin() -> None:
    text = "a" * 300

    assert estimate_tokens(text) == math.ceil(300 / DEFAULT_CHARS_PER_TOKEN * (1 + DEFAULT_MARGIN))


def test_estimate_tokens_with_custom_chars_per_token_and_margin() -> None:
    text = "a" * 100

    assert estimate_tokens(text, chars_per_token=2.0, margin=0.5) == math.ceil(
        100 / 2.0 * 1.5
    )


def test_estimate_tokens_of_empty_text_is_zero() -> None:
    assert estimate_tokens("") == 0


def test_fits_exactly_at_the_limit() -> None:
    # chars_per_token=1, margin=0 => estimate_tokens == len(system + user) exactly.
    text = "x" * _BUDGET.max_input_tokens

    assert fits("", text, _BUDGET, chars_per_token=1.0, margin=0.0) is True


def test_fits_one_token_over_the_limit() -> None:
    text = "x" * (_BUDGET.max_input_tokens + 1)

    assert fits("", text, _BUDGET, chars_per_token=1.0, margin=0.0) is False


def test_fits_combines_system_and_user() -> None:
    system = "x" * (_BUDGET.max_input_tokens // 2)
    user = "x" * (_BUDGET.max_input_tokens // 2)

    assert fits(system, user, _BUDGET, chars_per_token=1.0, margin=0.0) is True

    assert fits(system, user + "x", _BUDGET, chars_per_token=1.0, margin=0.0) is False


def test_fits_with_default_margin_rejects_a_prompt_the_raw_length_would_allow() -> None:
    # At the default margin, an input whose raw length equals the budget divided by
    # chars_per_token no longer fits once the 15% margin is added.
    raw_chars = math.floor(_BUDGET.max_input_tokens * DEFAULT_CHARS_PER_TOKEN)

    assert fits("", "x" * raw_chars, _BUDGET) is False
