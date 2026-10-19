"""Clean job descriptions and fit a prompt into its task's token budget.

Pure functions, no I/O. Two jobs that belong together because the second depends on the
first: a description full of markup and boilerplate spends tokens on nothing, and the
budget only means something once the text it measures is the text that will be sent.

An oversized prompt is truncated from the start — where the instructions are — by a
server that reports it, if at all, only in its own log. Everything here exists so the
radar never sends a prompt that would be cut without anyone knowing.

`platform.ai.budget` (F20-13) is the same idea for the cloud router: `TaskBudget.
max_input_tokens` is the ceiling here `num_ctx` used to be, now set by the task
(SPEC 43, section 6) instead of a local model's context window.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from opportunity_radar.platform.html_text import html_to_text

#: Version of the cleaning rules below. Any change to the patterns bumps it.
CLEANER_VERSION = "cleaner-v4"

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
    # Repeated institutional blocks (card R55-C2): the same mission, values and "why join"
    # text is pasted into every posting of a company and says nothing about this job.
    r"our (?:mission|values|culture|story|vision)",
    r"company (?:overview|culture|values)",
    r"why (?:join|work (?:with|at|for)) (?:us|.{1,40})",
    r"life at .{1,40}",
    r"nossa (?:miss[ãa]o|cultura|hist[óo]ria|vis[ãa]o)",
    r"nossos valores",
    r"por que (?:trabalhar|fazer parte) .{1,40}",
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


#: Headings of the sections a candidate screens a posting by. Under a token ceiling these
#: go into the prompt first (card R55-C2); everything else follows in its original order.
_PRIORITY_HEADINGS = (
    r"responsibilities",
    r"(?:key )?responsibilities and requirements",
    r"what you(?:'ll| will) do",
    r"requirements",
    r"(?:minimum |preferred |basic )?qualifications",
    r"what you(?:'ll| will)? bring",
    r"who you are",
    r"responsabilidades",
    r"o que voc[êe] (?:vai|ir[áa]) fazer",
    r"requisitos",
    r"qualifica[çc][õo]es",
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

#: Plain-text headings that only end a dropped institutional block (R55-C review); kept out
#: of `split_sections` so a bare "Skills" inside "Requirements" does not split it.
_SKIP_EXIT_HEADINGS = (
    r"what we(?:'re| are) looking for",
    r"your profile",
    r"(?:technical |key |core )?skills(?: and experience)?",
    r"must[- ]haves?",
    r"(?:required )?experience",
    r"job description",
    r"(?:the )?position",
    r"perfil(?: da vaga| desejado)?",
    r"compet[êe]ncias",
    r"habilidades",
    r"experi[êe]ncia",
    r"descri[çc][ãa]o da vaga",
    r"o que buscamos",
)

_BOILERPLATE = _whole_line(_BOILERPLATE_HEADINGS)
_PRIORITY_HEADING = _whole_line(_PRIORITY_HEADINGS)
_JOB_HEADING = _whole_line(_JOB_HEADINGS)
_SKIP_EXIT_HEADING = _whole_line(_SKIP_EXIT_HEADINGS)
# A marked heading — from `<hN>` or Markdown — or a short line ending in a colon ends a
# boilerplate section. Anything else, bullets included, still belongs to it.
_MARKED_HEADING = re.compile(r"^\s*(?:#+\s*\S.*|[^\s\-•*][^.!?]{0,60}:)\s*$")
# A short unpunctuated line that opens a bullet list or a paragraph is a heading even when
# no listed heading matches it and it carries no colon (conservative: ending the skip early
# keeps text, it never loses a requirement).
_HEADING_LIKE = re.compile(r"^[^\s\-•*][^.!?,;:]{0,50}$")
_BULLET_OR_SENTENCE = re.compile(r"^(?:[\-•*]\s*\S|.*[.!?]$|(?:\S+\s+){8,}\S+)")
_SPACES = re.compile(r"[ \t ]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_SENTENCE_END = re.compile(r"[.!?](?=\s)|\n\n")


@dataclass(frozen=True, slots=True)
class CleanedText:
    """What the cleaner kept, and the headings of the sections it dropped."""

    text: str
    removed_sections: tuple[str, ...] = ()
    kept_facts: int = 0


def _opens_block(line: str, following: Sequence[str]) -> bool:
    """A short heading-like line whose next non-blank line is a bullet or a paragraph."""
    if not line or not _HEADING_LIKE.match(line) or len(line.split()) > 6:
        return False
    next_line = next((candidate for candidate in following if candidate), "")
    return bool(next_line) and bool(_BULLET_OR_SENTENCE.match(next_line))


def clean_description_report(text: str | None) -> CleanedText:
    """Plain text with markup, entities and listed boilerplate sections removed.

    Greenhouse sends HTML that is itself escaped; `platform.html_text.html_to_text` decodes
    it, strips the tags and keeps paragraph and list line breaks (card R55-B3).
    Inside a dropped section, a line that states pay, visa, contract, country or time zone
    is kept: those are the facts a "Benefits" heading most often hides.
    """
    if not text:
        return CleanedText(text="")
    plain = html_to_text(text, heading_marker="# ", bullet="") or ""
    lines = [_SPACES.sub(" ", line).strip() for line in plain.replace("\r", "").split("\n")]
    kept: list[str] = []
    removed: list[str] = []
    kept_facts = 0
    skipping = False
    for index, line in enumerate(lines):
        if _BOILERPLATE.match(line):
            skipping = True
            removed.append(line.lstrip("# ").rstrip(":.! ").strip())
            continue
        if skipping and (
            _JOB_HEADING.match(line)
            or _SKIP_EXIT_HEADING.match(line)
            or _MARKED_HEADING.match(line)
            or _opens_block(line, lines[index + 1 :])
        ):
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


def trim_stored_description(text: str | None, max_chars: int) -> str | None:
    """The form of a description kept in the database (card R55-E6).

    Up to `max_chars` (or with `max_chars <= 0`) the text is returned untouched. Longer
    text loses its boilerplate sections (`clean_description`) and, if still too long, is
    cut with the requirements and responsibilities sections first
    (`fit_description_by_section`). Idempotent: a trimmed text is within the cap, so a
    second pass returns it as is. Skills, seniority and country rules read the full
    text before this runs; they never see the trimmed one.
    """
    if not text or max_chars <= 0 or len(text) <= max_chars:
        return text
    cleaned = clean_description(text)
    trimmed = fit_description_by_section(
        cleaned, available_tokens=max_chars, tokens_per_char=1.0
    ).text
    if trimmed.strip():
        return trimmed
    # Everything was boilerplate (or nothing fit): never store an empty description.
    return truncate_at_sentence(text.strip(), max_chars)[0] or text.strip()[:max_chars]


def estimate_tokens(chars: int, tokens_per_char: float) -> int:
    return math.ceil(chars * tokens_per_char)


def prompt_budget(max_input_tokens: int, max_output_tokens: int, margin: int | None = None) -> int:
    """Tokens a prompt may use: the task's input budget, minus the answer, minus a margin.

    `max_input_tokens` and `max_output_tokens` come from the task's `TaskBudget`
    (`platform.ai.tasks`, SPEC 43 section 6) rather than a model's own context window.
    The margin starts at 10% of `max_input_tokens`; a calibration whose observed prompts
    cost more than the ratio in use predicts widens it (`TokenCalibration.margin`).
    """
    return (
        max_input_tokens
        - max_output_tokens
        - (max_input_tokens // 10 if margin is None else margin)
    )


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

    def margin(self, max_input_tokens: int, max_output_tokens: int) -> int:
        default = max_input_tokens // 10
        excess = self.worst_excess
        if not self.calibrated or excess is None or excess <= 0:
            return default
        return max(default, math.ceil((max_input_tokens - max_output_tokens) * excess))

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


def split_sections(text: str) -> list[tuple[bool, str]]:
    """`(is_priority, block)` pairs of a cleaned description, in the original order.

    A block starts at a heading line (job heading or marked heading) and runs to the next
    one; text before the first heading is its own block. `is_priority` is true for the
    requirements and responsibilities blocks (card R55-C2).
    """
    blocks: list[tuple[bool, list[str]]] = []
    for line in text.split(chr(10)):
        if _JOB_HEADING.match(line) or _PRIORITY_HEADING.match(line) or _MARKED_HEADING.match(line):
            blocks.append((bool(_PRIORITY_HEADING.match(line)), [line]))
        elif blocks:
            blocks[-1][1].append(line)
        else:
            blocks.append((False, [line]))
    return [(priority, chr(10).join(lines).strip()) for priority, lines in blocks if any(lines)]


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


def fit_description_by_section(
    description: str, *, available_tokens: int, tokens_per_char: float
) -> FittedText:
    """Like `fit_description`, but a cut keeps requirements and responsibilities first.

    A description that fits is returned untouched. Otherwise its sections go in whole, the
    requirements and responsibilities ones first and the rest in their original order,
    until the budget is spent; the section that crosses it is cut at a sentence boundary.
    Without any section heading the result is the plain cut of `fit_description`.
    """
    max_chars = max(0, math.floor(available_tokens / tokens_per_char))
    if len(description) <= max_chars:
        return FittedText(text=description, truncated=False)
    sections = split_sections(description)
    if not any(priority for priority, _ in sections):
        return fit_description(
            description, available_tokens=available_tokens, tokens_per_char=tokens_per_char
        )
    ordered = [block for priority, block in sections if priority] + [
        block for priority, block in sections if not priority
    ]
    kept: list[str] = []
    used = 0
    for block in ordered:
        cost = len(block) + (2 if kept else 0)
        if used + cost <= max_chars:
            kept.append(block)
            used += cost
            continue
        room = max_chars - used - (2 if kept else 0)
        if room > 0:
            cut, _ = truncate_at_sentence(block, room)
            if cut:
                kept.append(cut)
                used += len(cut) + (2 if len(kept) > 1 else 0)
    return FittedText(text=(chr(10) * 2).join(kept), truncated=True)


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
    "trim_stored_description",
    "fit_description",
    "fit_description_by_section",
    "split_sections",
    "prompt_budget",
    "truncate_at_sentence",
]
