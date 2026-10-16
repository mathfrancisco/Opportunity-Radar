"""R55-B3: every ATS description reaches normalization and the AI as plain text.

The fixtures are anonymised shapes of what each ATS returns: Greenhouse sends HTML that is
itself entity-escaped (`content=true`), Teamtailor/Workable/Inhire/Workday/JobPosting/Remotive
send HTML, Lever and Ashby send plain text.
"""

from __future__ import annotations

import pytest

from opportunity_radar.matching.text import clean_description
from opportunity_radar.platform.html_text import html_to_text

_GREENHOUSE = (
    "&lt;div class=&quot;content-intro&quot;&gt;&lt;p&gt;Acme builds payments for "
    "marketplaces.&lt;/p&gt;&lt;/div&gt;&lt;h3&gt;Requirements&lt;/h3&gt;&lt;ul&gt;"
    "&lt;li&gt;3+ years with Ruby on Rails&lt;/li&gt;&lt;li&gt;Experience with GraphQL "
    "&amp;amp; REST&lt;/li&gt;&lt;/ul&gt;&lt;p&gt;Don&amp;#39;t apply without a CV.&lt;/p&gt;"
    "&lt;style&gt;.x{color:red}&lt;/style&gt;"
)
_GREENHOUSE_DOUBLE = (
    "&amp;lt;p&amp;gt;Build GraphQL APIs&amp;lt;/p&amp;gt;"
    "&amp;lt;p&amp;gt;Use Python&amp;lt;/p&amp;gt;"
)
_TEAMTAILOR = (
    "<h2>About the role</h2><p>You will own the <strong>Python</strong> data platform.</p>"
    "<ul><li>Design pipelines</li><li>Review code</li></ul><script>track()</script>"
)
_WORKABLE = "<p>Descri&ccedil;&atilde;o da vaga</p><p>Requisitos:<br/>Python<br>SQL</p>"
_INHIRE = "<div><p>Vaga <b>Pleno</b> em Python</p></div><div><p>Remoto no Brasil</p></div>"
_WORKDAY = "<p><b>Job&nbsp;Description</b></p><p>Maintain&nbsp;Linux&nbsp;services.</p>"
_JOBPOSTING = (
    "<section><h1>Data Engineer</h1><p>Build ETL jobs.</p><!-- internal note --></section>"
)
_REMOTIVE = (
    '<p><span style="x">Remote</span> role &amp; great team</p>'
    "<table><tr><td>Go</td><td>Rust</td></tr></table>"
)
_LEVER = "About the role\nYou will design APIs.\n\nRequirements\n- Strong SQL\n- Python"
_ASHBY = "Responsibilities\nOwn the ingestion platform.\n\nR&D budget is shared across teams."


@pytest.mark.parametrize(
    ("source", "raw", "present", "absent"),
    [
        (
            "greenhouse",
            _GREENHOUSE,
            [
                "Requirements",
                "- 3+ years with Ruby on Rails",
                "- Experience with GraphQL & REST",
                "Don't apply",
            ],
            ["&lt;", "<", "&amp;", "color:red", "content-intro"],
        ),
        (
            "greenhouse-double-escaped",
            _GREENHOUSE_DOUBLE,
            ["Build GraphQL APIs", "Use Python"],
            ["&lt;", "&gt;", "<p>", "&amp;"],
        ),
        (
            "teamtailor",
            _TEAMTAILOR,
            ["About the role", "You will own the Python data platform.", "- Design pipelines"],
            ["<", "track()"],
        ),
        (
            "workable",
            _WORKABLE,
            ["Descrição da vaga", "Requisitos:\nPython\nSQL"],
            ["<", "&ccedil;"],
        ),
        ("inhire", _INHIRE, ["Vaga Pleno em Python", "Remoto no Brasil"], ["<", "</"]),
        ("workday", _WORKDAY, ["Job Description", "Maintain Linux services."], ["&nbsp;", "\xa0"]),
        ("jobposting", _JOBPOSTING, ["Data Engineer", "Build ETL jobs."], ["<", "internal note"]),
        ("remotive", _REMOTIVE, ["Remote role & great team", "Go Rust"], ["<", "style="]),
    ],
)
def test_each_ats_description_becomes_plain_text(
    source: str, raw: str, present: list[str], absent: list[str]
) -> None:
    text = html_to_text(raw)

    assert text is not None
    for expected in present:
        assert expected in text, (source, expected)
    for forbidden in absent:
        assert forbidden not in text, (source, forbidden)


def test_paragraphs_and_list_items_keep_their_line_breaks() -> None:
    text = html_to_text(_GREENHOUSE)

    assert text is not None
    lines = text.split("\n")
    assert "Requirements" in lines
    assert "- 3+ years with Ruby on Rails" in lines
    assert "- Experience with GraphQL & REST" in lines


def test_inline_tags_do_not_split_words() -> None:
    assert html_to_text("<p>Py<b>thon</b> and Ru<i>by</i></p>") == "Python and Ruby"


@pytest.mark.parametrize(
    "plain", [_LEVER, _ASHBY, "Python, SQL e Go.\n\nSem markup.", "a < b and c > d"]
)
def test_plain_text_is_returned_unchanged(plain: str) -> None:
    assert html_to_text(plain) == plain


@pytest.mark.parametrize("empty", [None, ""])
def test_empty_values_pass_through(empty: str | None) -> None:
    assert html_to_text(empty) == empty


def test_whitespace_only_markup_collapses_to_empty() -> None:
    assert html_to_text("<p>&nbsp;</p><div> </div>") == ""


def test_is_idempotent() -> None:
    once = html_to_text(_GREENHOUSE)
    assert html_to_text(once) == once


def test_ai_prompt_cleaner_reads_the_same_text_and_keeps_the_requirements() -> None:
    cleaned = clean_description(_GREENHOUSE)

    assert "<" not in cleaned and "&lt;" not in cleaned
    assert "3+ years with Ruby on Rails" in cleaned
    assert "GraphQL & REST" in cleaned


def test_ai_prompt_cleaner_reads_a_double_escaped_description() -> None:
    cleaned = clean_description(_GREENHOUSE_DOUBLE)

    assert "Build GraphQL APIs" in cleaned
    assert "&lt;" not in cleaned and "<p>" not in cleaned


def test_real_html_is_never_unescaped_twice() -> None:
    assert html_to_text("<p>R&amp;lt;D</p>") == "R&lt;D"
    assert html_to_text("<p>Tom &amp;amp; Jerry</p>") == "Tom &amp; Jerry"


def test_clean_text_is_stable_when_its_decoded_form_has_no_entity() -> None:
    once = html_to_text("<p>Tom &amp; Jerry</p>")
    assert once == "Tom & Jerry"
    assert html_to_text(once) == once


def test_decoded_entity_text_is_decoded_once_more_by_a_second_pass() -> None:
    # Documented limit of idempotence: `R&lt;D` is still an entity after one decode.
    once = html_to_text("<p>R&amp;lt;D</p>")
    assert once == "R&lt;D"
    assert html_to_text(once) == "R<D"


def test_plain_text_with_entities_but_no_tags_is_decoded_once() -> None:
    assert html_to_text("Tom &amp; Jerry &nbsp;x") == "Tom & Jerry  x"
    assert html_to_text("Use &lt;D for the delta") == "Use <D for the delta"
    assert html_to_text("&amp;lt;") == "&lt;"


@pytest.mark.parametrize("tag", ["script", "style", "noscript", "template"])
def test_unclosed_dropped_element_keeps_the_text_after_it(tag: str) -> None:
    text = html_to_text(f"<p>Hi</p><{tag}>x{{}}<p>Job at Acme, R&amp;D")

    assert text is not None
    assert "Hi" in text and "Job at Acme, R&D" in text


@pytest.mark.parametrize("tag", ["script", "style", "noscript", "template"])
def test_closed_dropped_element_is_removed_with_its_content(tag: str) -> None:
    text = html_to_text(f"<p>Hi</p><{tag}>secret()</{tag}><p>Job</p>")

    assert text == "Hi\n\nJob"


def test_one_closed_and_one_unclosed_element_of_the_same_tag() -> None:
    text = html_to_text("<style>a{}</style><p>One</p><style>b{}<p>Two")

    assert text is not None
    assert "a{}" not in text and "One" in text and "Two" in text


def test_input_is_capped_and_hostile_markup_is_fast() -> None:
    import time

    hostile = "<a" * 40_000
    started = time.perf_counter()
    html_to_text(hostile)
    html_to_text("&lt;a" * 40_000)
    html_to_text("<p>" + "word " * 100_000)
    assert time.perf_counter() - started < 0.5


def test_input_past_the_cap_is_cut() -> None:
    from opportunity_radar.platform.html_text import MAX_INPUT_CHARS

    text = html_to_text("<p>" + "x" * (MAX_INPUT_CHARS * 2) + "</p>")
    assert text is not None and len(text) < MAX_INPUT_CHARS
