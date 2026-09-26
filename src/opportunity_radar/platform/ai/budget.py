"""Token Guard per task (SPEC 43, section 7.2).

`TaskBudget.max_input_tokens` replaces a local model's context window as the ceiling a
prompt must fit under before it is ever sent; `estimate_tokens` is the cheap character
count the router and the Quota Guard use before a real tokenizer count exists.
"""

from __future__ import annotations

import math

from opportunity_radar.platform.ai.tasks import TaskBudget

#: Deliberately high per character: overestimating only rejects a prompt sooner,
#: underestimating would send one that overflows without anyone knowing.
DEFAULT_CHARS_PER_TOKEN = 3.0

#: Above the raw estimate, in case the calibration in use still underestimates.
DEFAULT_MARGIN = 0.15


def estimate_tokens(
    text: str,
    *,
    chars_per_token: float = DEFAULT_CHARS_PER_TOKEN,
    margin: float = DEFAULT_MARGIN,
) -> int:
    """`ceil(len(text) / chars_per_token * (1 + margin))`."""
    return math.ceil(len(text) / chars_per_token * (1 + margin))


def fits(
    system: str,
    user: str,
    budget: TaskBudget,
    *,
    chars_per_token: float = DEFAULT_CHARS_PER_TOKEN,
    margin: float = DEFAULT_MARGIN,
) -> bool:
    """Whether `system` + `user`, estimated, stays at or under the task's input budget."""
    estimated = estimate_tokens(system + user, chars_per_token=chars_per_token, margin=margin)
    return estimated <= budget.max_input_tokens


__all__ = ["DEFAULT_CHARS_PER_TOKEN", "DEFAULT_MARGIN", "estimate_tokens", "fits"]
