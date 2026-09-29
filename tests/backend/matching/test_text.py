"""Description cleaner and prompt budget. Fixtures are anonymised postings from each ATS."""

from __future__ import annotations

import pytest

from opportunity_radar.matching.text import (
    clean_description,
    estimate_tokens,
    fit_description,
    prompt_budget,
    truncate_at_sentence,
)

# Greenhouse `content`: HTML that is itself entity-escaped.
_GREENHOUSE = (
    "&lt;h2&gt;About Us&lt;/h2&gt;&lt;p&gt;Acme is a fast-growing company on a mission."
    "&lt;/p&gt;&lt;h2&gt;What You&amp;#39;ll Do&lt;/h2&gt;&lt;ul&gt;&lt;li&gt;Build APIs "
    "in Python &amp;amp; Go&lt;/li&gt;&lt;li&gt;Own the data pipeline&lt;/li&gt;&lt;/ul&gt;"
    "&lt;h2&gt;Benefits&lt;/h2&gt;&lt;ul&gt;&lt;li&gt;Health insurance&lt;/li&gt;&lt;/ul&gt;"
    "&lt;h2&gt;Requirements&lt;/h2&gt;&lt;p&gt;5+ years with Python.&lt;/p&gt;"
    "&lt;p&gt;Acme is an Equal Opportunity Employer.&lt;/p&gt;"
)

# Ashby `descriptionPlain`: plain text, headings on their own line.
_ASHBY = """About the role
You will design the ingestion platform.

Benefits:
- Remote stipend
- Unlimited PTO

Qualifications
- Strong SQL
"""

# Lever `descriptionPlain`: Portuguese, boilerplate first.
_LEVER = """Sobre nós
Somos uma fintech que cresce rápido.
Nossa cultura valoriza autonomia.

Responsabilidades
Manter serviços em Python.

Benefícios
Vale refeição.
Plano de saúde."""


def test_greenhouse_html_is_decoded_stripped_and_its_boilerplate_dropped() -> None:
    cleaned = clean_description(_GREENHOUSE)

    assert "<" not in cleaned and "&lt;" not in cleaned and "&amp;" not in cleaned
    assert "Build APIs in Python & Go" in cleaned
    assert "What You'll Do" in cleaned
    assert "5+ years with Python." in cleaned
    assert "mission" not in cleaned
    assert "Health insurance" not in cleaned


def test_ashby_plain_text_keeps_the_job_and_drops_the_benefits_list() -> None:
    cleaned = clean_description(_ASHBY)

    assert "design the ingestion platform" in cleaned
    assert "Strong SQL" in cleaned
    assert "Remote stipend" not in cleaned
    assert "Unlimited PTO" not in cleaned


def test_lever_portuguese_boilerplate_is_dropped_on_both_ends() -> None:
    cleaned = clean_description(_LEVER)

    assert cleaned == "Responsabilidades\nManter serviços em Python."


def test_whitespace_is_collapsed_and_a_sentence_about_benefits_survives() -> None:
    cleaned = clean_description("Line   one\t here\n\n\n\nWe explain benefits of Go.")

    assert cleaned == "Line one here\n\nWe explain benefits of Go."


@pytest.mark.parametrize("empty", [None, ""])
def test_nothing_to_clean_is_an_empty_string(empty: str | None) -> None:
    assert clean_description(empty) == ""


def test_truncation_stops_at_the_last_sentence_that_fits() -> None:
    text = "First sentence. Second sentence! Third one runs long"

    assert truncate_at_sentence(text, 40) == ("First sentence. Second sentence!", True)
    assert truncate_at_sentence(text, 1000) == (text, False)


def test_truncation_without_a_sentence_end_cuts_at_a_space() -> None:
    assert truncate_at_sentence("alpha beta gamma delta", 13) == ("alpha beta", True)


def test_the_budget_leaves_room_for_the_answer_and_a_margin() -> None:
    assert prompt_budget(8192, 1024) == 8192 - 1024 - 819
    assert estimate_tokens(1000, 0.35) == 350


def test_the_budget_tracks_a_task_budget_not_a_model_window() -> None:
    # F20-13: `max_input_tokens`/`max_output_tokens` come from `TaskBudget` (SPEC 43
    # section 6), e.g. `job_match`'s 5000/900, not a local model's `num_ctx`/`num_predict`.
    assert prompt_budget(5000, 900) == 5000 - 900 - 500


def test_the_description_cut_respects_the_task_budget() -> None:
    description = "Uma frase curta. " * 800
    task_input_budget = 5000
    task_output_budget = 900
    available = prompt_budget(task_input_budget, task_output_budget)

    fitted = fit_description(description, available_tokens=available, tokens_per_char=0.35)

    assert fitted.truncated
    assert estimate_tokens(len(fitted.text), 0.35) <= available


def test_the_description_gets_only_what_the_fixed_parts_left() -> None:
    description = "Uma frase curta. " * 100

    fitted = fit_description(description, available_tokens=35, tokens_per_char=0.35)

    assert fitted.truncated
    assert len(fitted.text) <= 100
    assert fitted.text.endswith(".")
    untouched = fit_description("Curta.", available_tokens=35, tokens_per_char=0.35)
    assert untouched.text == "Curta." and not untouched.truncated
