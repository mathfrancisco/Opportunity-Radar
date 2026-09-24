"""Clean job descriptions and fit a prompt into the model's context window.

Pure functions, no I/O. Two jobs that belong together because the second depends on the
first: a description full of markup and boilerplate spends tokens on nothing, and the
budget only means something once the text it measures is the text that will be sent.

The Ollama server truncates an oversized prompt from the start — where the instructions
are — and reports it only in its own log. Everything here exists so the radar never sends
a prompt that would be cut without anyone knowing.
"""

from __future__ import annotations

import html
import math
import re
from dataclasses import dataclass

#: Version of the cleaning rules below. Any change to the patterns bumps it.
CLEANER_VERSION = "cleaner-v1"

#: Tokens per character before any analysis of the model has been measured. Deliberately
#: high: overestimating only cuts a description sooner, underestimating overflows.
DEFAULT_TOKENS_PER_CHAR = 0.35

#: Headings that open a section with nothing about the job itself. Matched against a
#: whole line, so a sentence that merely mentions benefits is kept.
_BOILERPLATE_HEADINGS = (
    r"about us",
    r"about the company",
    r"who we are",
    r"sobre n[óo]s",
    r"sobre a empresa",
    r"quem somos",
    r"equal (?:employment )?opportunit(?:y|ies)(?: employer)?",
    r"diversity,? (?:equity|and inclusion).*",
    r"eeo statement",
    r"benefits",
    r"perks(?: and benefits)?",
    r"benef[íi]cios",
    r"what we offer",
    r"o que oferecemos",
)

#: Headings that open the part of a posting about the job, in plain-text sources.
_JOB_HEADINGS = (
    r"(?:the )?role",
    r"about the (?:role|job|position|team)",
    r"responsibilities",
    r"what you(?:'ll| will) do",
    r"requirements",
    r"(?:minimum |preferred |basic )?qualifications",
    r"what you(?:'ll| will)? bring",
    r"who you are",
    r"nice to have",
    r"(?:sobre )?a vaga",
    r"responsabilidades",
    r"o que voc[êe] (?:vai|ir[áa]) fazer",
    r"requisitos",
    r"qualifica[çc][õo]es",
    r"diferenciais",
)


def _whole_line(alternatives: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(
        r"^\s*(?:#+\s*)?(?:" + "|".join(alternatives) + r")\s*[:.!]?\s*$", re.IGNORECASE
    )


_BOILERPLATE = _whole_line(_BOILERPLATE_HEADINGS)
_JOB_HEADING = _whole_line(_JOB_HEADINGS)
# A marked heading — from `<hN>` or Markdown — or a short line ending in a colon ends a
# boilerplate section. Anything else, bullets included, still belongs to it.
_MARKED_HEADING = re.compile(r"^\s*(?:#+\s*\S.*|[^\s\-•*][^.!?]{0,60}:)\s*$")
_HEADING_OPEN = re.compile(r"<\s*h[1-6]\b[^>]*>", re.IGNORECASE)
_BLOCK_TAGS = re.compile(
    r"<\s*/?\s*(?:br|p|div|li|ul|ol|h[1-6])\b[^>]*>", re.IGNORECASE
)
_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t ]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_SENTENCE_END = re.compile(r"[.!?](?=\s)|\n\n")


def clean_description(text: str | None) -> str:
    """Plain text with markup, entities and listed boilerplate sections removed.

    Greenhouse sends HTML that is itself escaped, so entities are decoded before tags are
    stripped and once more after, which leaves a literal `&amp;` in plain text intact.
    """
    if not text:
        return ""
    decoded = html.unescape(text)
    blocked = _BLOCK_TAGS.sub("\n", _HEADING_OPEN.sub("\n# ", decoded))
    plain = html.unescape(_TAGS.sub(" ", blocked))
    lines = [_SPACES.sub(" ", line).strip() for line in plain.replace("\r", "").split("\n")]
    kept: list[str] = []
    skipping = False
    for line in lines:
        if _BOILERPLATE.match(line):
            skipping = True
            continue
        if skipping and (_JOB_HEADING.match(line) or _MARKED_HEADING.match(line)):
            skipping = False
        if not skipping:
            kept.append(line)
    return _BLANK_LINES.sub("\n\n", "\n".join(kept)).strip()


def truncate_at_sentence(text: str, max_chars: int) -> tuple[str, bool]:
    """Cut at the last sentence or paragraph end before the limit; else at a space."""
    if len(text) <= max_chars:
        return text, False
    if max_chars <= 0:
        return "", True
    window = text[:max_chars]
    ends = [match.end() for match in _SENTENCE_END.finditer(window)]
    if ends:
        return window[: ends[-1]].rstrip(), True
    space = window.rfind(" ")
    return (window[:space] if space > 0 else window).rstrip(), True


def estimate_tokens(chars: int, tokens_per_char: float) -> int:
    return math.ceil(chars * tokens_per_char)


def prompt_budget(num_ctx: int, num_predict: int) -> int:
    """Tokens a prompt may use: the window, minus the answer, minus a 10% margin."""
    return num_ctx - num_predict - num_ctx // 10


@dataclass(frozen=True, slots=True)
class FittedText:
    text: str
    truncated: bool


def fit_description(
    description: str, *, available_tokens: int, tokens_per_char: float
) -> FittedText:
    """Give the description whatever the fixed parts left, cut at a sentence boundary."""
    max_chars = max(0, math.floor(available_tokens / tokens_per_char))
    text, truncated = truncate_at_sentence(description, max_chars)
    return FittedText(text=text, truncated=truncated)


__all__ = [
    "CLEANER_VERSION",
    "DEFAULT_TOKENS_PER_CHAR",
    "FittedText",
    "clean_description",
    "estimate_tokens",
    "fit_description",
    "prompt_budget",
    "truncate_at_sentence",
]
