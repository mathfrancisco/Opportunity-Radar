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
from collections.abc import Sequence
from dataclasses import dataclass, field

#: Version of the cleaning rules below. Any change to the patterns bumps it.
CLEANER_VERSION = "cleaner-v2"

#: Tokens per character before any analysis of the model has been measured. Deliberately
#: high: overestimating only cuts a description sooner, underestimating overflows.
DEFAULT_TOKENS_PER_CHAR = 0.35

#: Measured analyses a model and prompt need before their own ratio replaces the default.
MIN_CALIBRATION_SAMPLE = 20

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


#: Facts a candidate decides on. A benefits or "about us" section that states the pay,
#: the visa policy, the contract, the country or the time zone keeps those lines even
#: though the section itself is dropped.
_DECISIVE_FACT = re.compile(
    r"sal[áa]r|salary|compensa|remunera|\bpay\b|\$|€|£|\busd\b|\bbrl\b|\beur\b"
    r"|visa|visto|sponsor|patroc[íi]n|work (?:permit|authori[sz]ation)"
    r"|\bclt\b|\bpj\b|contract|contrato|full[- ]time|part[- ]time|freelanc|tempo integral"
    r"|fully remote|100% remot|remote[- ]first|trabalho remoto|work from anywhere"
    r"|h[íi]brido|hybrid|on[- ]?site|presencial|relocat|realoca"
    r"|countr|pa[íi]s|brazil|brasil|latam|latin america|europe|\beua\b"
    r"|time ?zone|fuso|\butc\b|\bgmt\b|\bbrt\b|overlap",
    re.IGNORECASE,
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


@dataclass(frozen=True, slots=True)
class CleanedText:
    """What the cleaner kept, and the headings of the sections it dropped."""

    text: str
    removed_sections: tuple[str, ...] = ()
    kept_facts: int = 0


def clean_description_report(text: str | None) -> CleanedText:
    """Plain text with markup, entities and listed boilerplate sections removed.

    Greenhouse sends HTML that is itself escaped, so entities are decoded before tags are
    stripped and once more after, which leaves a literal `&amp;` in plain text intact.
    Inside a dropped section, a line that states pay, visa, contract, country or time zone
    is kept: those are the facts a "Benefits" heading most often hides.
    """
    if not text:
        return CleanedText(text="")
    decoded = html.unescape(text)
    blocked = _BLOCK_TAGS.sub("\n", _HEADING_OPEN.sub("\n# ", decoded))
    plain = html.unescape(_TAGS.sub(" ", blocked))
    lines = [_SPACES.sub(" ", line).strip() for line in plain.replace("\r", "").split("\n")]
    kept: list[str] = []
    removed: list[str] = []
    kept_facts = 0
    skipping = False
    for line in lines:
        if _BOILERPLATE.match(line):
            skipping = True
            removed.append(line.lstrip("# ").rstrip(":.! ").strip())
            continue
        if skipping and (_JOB_HEADING.match(line) or _MARKED_HEADING.match(line)):
            skipping = False
        if not skipping:
            kept.append(line)
        elif line and _DECISIVE_FACT.search(line):
            kept.append(line)
            kept_facts += 1
    return CleanedText(
        text=_BLANK_LINES.sub("\n\n", "\n".join(kept)).strip(),
        removed_sections=tuple(removed),
        kept_facts=kept_facts,
    )


def clean_description(text: str | None) -> str:
    """The cleaned text alone; see `clean_description_report`."""
    return clean_description_report(text).text


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


def prompt_budget(num_ctx: int, num_predict: int, margin: int | None = None) -> int:
    """Tokens a prompt may use: the window, minus the answer, minus a margin.

    The margin starts at 10% of the window; a calibration whose observed prompts cost
    more than the ratio in use predicts widens it (`TokenCalibration.margin`).
    """
    return num_ctx - num_predict - (num_ctx // 10 if margin is None else margin)


def _nearest_rank(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


@dataclass(frozen=True, slots=True)
class TokenCalibration:
    """How many tokens a character costs for one model and prompt, from real calls.

    A mean says nothing about the prompt that overflows, so the ratio in use is the 95th
    percentile of the observed ratios, and the margin grows when even that ratio
    underestimated some prompt by more than the default 10%. With fewer than
    `MIN_CALIBRATION_SAMPLE` measured calls the default ratio stands and the state says
    so: an estimate is never presented as calibrated when it is not, and no estimate is
    presented as proof that nothing was truncated.
    """

    samples: int
    ratios: tuple[float, ...] = field(default=(), repr=False)
    # Relative underestimation of past estimates: (actual - estimate) / actual.
    estimate_errors: tuple[float, ...] = field(default=(), repr=False)

    @property
    def calibrated(self) -> bool:
        return self.samples >= MIN_CALIBRATION_SAMPLE

    @property
    def ratio(self) -> float:
        if not self.calibrated:
            return DEFAULT_TOKENS_PER_CHAR
        return _nearest_rank(self.ratios, 0.95)

    @property
    def mean_ratio(self) -> float | None:
        return sum(self.ratios) / len(self.ratios) if self.ratios else None

    @property
    def worst_excess(self) -> float | None:
        """How far above the ratio in use the costliest measured prompt went (fraction)."""
        if not self.ratios:
            return None
        return max(self.ratios) / self.ratio - 1

    def margin(self, num_ctx: int, num_predict: int) -> int:
        default = num_ctx // 10
        excess = self.worst_excess
        if not self.calibrated or excess is None or excess <= 0:
            return default
        return max(default, math.ceil((num_ctx - num_predict) * excess))

    def as_dict(self) -> dict[str, object]:
        errors = [abs(error) for error in self.estimate_errors]
        return {
            "state": "calibrated" if self.calibrated else "uncalibrated",
            "samples": self.samples,
            "ratio": self.ratio,
            "mean_ratio": self.mean_ratio,
            "worst_excess": self.worst_excess,
            "estimate_error_p95": _nearest_rank(errors, 0.95) if errors else None,
            "worst_underestimate": max(self.estimate_errors) if self.estimate_errors else None,
        }


def calibrate(measured: Sequence[tuple[int, int, int | None]]) -> TokenCalibration:
    """From `(prompt_tokens, prompt_chars, prompt_tokens_estimate)` of real calls."""
    usable = [(tokens, chars, estimate) for tokens, chars, estimate in measured if chars > 0]
    return TokenCalibration(
        samples=len(usable),
        ratios=tuple(tokens / chars for tokens, chars, _ in usable),
        estimate_errors=tuple(
            (tokens - estimate) / tokens
            for tokens, _, estimate in usable
            if estimate is not None and tokens > 0
        ),
    )


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
    "MIN_CALIBRATION_SAMPLE",
    "CleanedText",
    "FittedText",
    "TokenCalibration",
    "calibrate",
    "clean_description",
    "clean_description_report",
    "estimate_tokens",
    "fit_description",
    "prompt_budget",
    "truncate_at_sentence",
]
