"""Offline evaluation of the semantic analysis against a fixed, hand-labelled set of cases.

SPEC 36, section 8. Changing the prompt, the model or its quantisation is a decision with
numbers: every run scores the same cases on the same criteria and is compared with a
baseline. Scoring is code, never another model's opinion; the one judgement that needs a
person — whether the commentary agrees with the verdict — is left as a manual column.

Pure functions only. Running the cases against Ollama lives in scripts/eval_analysis.py.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from opportunity_radar.matching.analysis import (
    AnalysisMetrics,
    AnalysisOutcome,
    AnalysisRequest,
)
from opportunity_radar.matching.domain import EligibilityStatus, Verdict

#: The coverage every set must reach (card F16-06). A case declares one or more kinds.
CASE_KINDS = frozenset(
    {
        "strong_match",
        "weak_match",
        "ambiguous",
        "long_description",
        "english_description",
        "no_description",
        "missing_compensation",
        "missing_country",
    }
)
_REQUIRED_PAYLOAD = (
    "eligibility",
    "verdict",
    "score",
    "rules_version",
    "taxonomy_version",
    "opportunity_snapshot",
    "profile_snapshot",
)
_REQUIRED_EXPECTED = ("verdict", "must_mention_risks", "must_not_claim", "language")

# Short, high-frequency function words. A text is Portuguese when these outnumber the
# English ones; the split is crude on purpose, and good enough to catch a model that
# answers in the language of the posting.
_PORTUGUESE_WORDS = frozenset(
    "a o as os de da do das dos em no na nos nas um uma para por com não nao que se "
    "mais mas como ao à é e são sao ou sem sua seu pela pelo foi está esta há ha".split()
)
_ENGLISH_WORDS = frozenset(
    "the of and to in is are for with on not that this it be as by an or from at "
    "without has have its was".split()
)
_WORD = re.compile(r"[a-zà-ÿ]+", re.IGNORECASE)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_STOPWORDS = frozenset({"de", "da", "do", "the", "of", "a", "o", "e", "and", "em", "in"})


class EvalCaseError(ValueError):
    """A case file that cannot be scored: missing payload or incomplete answer key."""


@dataclass(frozen=True, slots=True)
class Expected:
    verdict: str
    must_mention_risks: tuple[str, ...]
    must_not_claim: tuple[str, ...]
    language: str


@dataclass(frozen=True, slots=True)
class EvalCase:
    case_id: str
    kinds: frozenset[str]
    payload: Mapping[str, Any]
    expected: Expected
    posting: Mapping[str, Any] = field(default_factory=dict)

    def request(self) -> AnalysisRequest:
        """The same request production builds; ids are placeholders, never looked up."""
        opportunity = self.payload["opportunity_snapshot"]
        return AnalysisRequest(
            opportunity_id=UUID(int=0),
            opportunity_content_version=int(opportunity.get("content_version", 1)),
            profile_version_id=UUID(int=0),
            rules_version=str(self.payload["rules_version"]),
            taxonomy_version=str(self.payload["taxonomy_version"]),
            eligibility=EligibilityStatus(self.payload["eligibility"]),
            verdict=Verdict(self.payload["verdict"]),
            score=Decimal(str(self.payload["score"])),
            opportunity_snapshot=opportunity,
            profile_snapshot=self.payload["profile_snapshot"],
        )

    def payload_text(self) -> str:
        return json.dumps(
            {"payload": self.payload, "posting": self.posting}, ensure_ascii=False
        )


def load_case(path: Path) -> EvalCase:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise EvalCaseError(f"{path.name}: unreadable case: {error}") from error
    if not isinstance(raw, dict):
        raise EvalCaseError(f"{path.name}: a case is a JSON object")
    payload, expected = raw.get("payload"), raw.get("expected")
    if not isinstance(payload, dict) or any(key not in payload for key in _REQUIRED_PAYLOAD):
        raise EvalCaseError(f"{path.name}: payload needs {', '.join(_REQUIRED_PAYLOAD)}")
    if not isinstance(expected, dict) or any(key not in expected for key in _REQUIRED_EXPECTED):
        raise EvalCaseError(f"{path.name}: expected needs {', '.join(_REQUIRED_EXPECTED)}")
    kinds = frozenset(raw.get("kinds") or ())
    if not kinds or not kinds <= CASE_KINDS:
        raise EvalCaseError(f"{path.name}: kinds must be a non-empty subset of CASE_KINDS")
    if expected["verdict"] != payload["verdict"]:
        raise EvalCaseError(f"{path.name}: expected verdict differs from the payload's")
    risks, claims = expected["must_mention_risks"], expected["must_not_claim"]
    if not _strings(risks) or not _strings(claims) or not claims:
        raise EvalCaseError(
            f"{path.name}: must_mention_risks is a list of strings and must_not_claim a "
            "non-empty one"
        )
    posting = raw.get("posting") or {}
    return EvalCase(
        case_id=path.stem,
        kinds=kinds,
        payload=payload,
        expected=Expected(
            verdict=str(expected["verdict"]),
            must_mention_risks=tuple(risks),
            must_not_claim=tuple(claims),
            language=str(expected["language"]),
        ),
        posting=posting if isinstance(posting, dict) else {},
    )


def load_cases(directory: Path) -> list[EvalCase]:
    return [load_case(path) for path in sorted(directory.glob("*.json"))]


def missing_kinds(cases: Iterable[EvalCase]) -> set[str]:
    covered: set[str] = set()
    for case in cases:
        covered |= case.kinds
    return set(CASE_KINDS - covered)


def _strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def normalize(text: str) -> str:
    """Lowercase, accents removed, punctuation collapsed to single spaces."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    ascii_only = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _NON_ALNUM.sub(" ", ascii_only).strip()


def _terms(text: str) -> set[str]:
    return {term for term in normalize(text).split() if term not in _STOPWORDS}


def coverage(risks: Sequence[str], must_mention: Sequence[str]) -> float | None:
    """Share of expected risks named by some risk: every term of the expected one appears."""
    if not must_mention:
        return None
    named = [_terms(risk) for risk in risks]
    hits = sum(1 for item in must_mention if any(_terms(item) <= risk for risk in named))
    return hits / len(must_mention)


def inventions(texts: Sequence[str], must_not_claim: Sequence[str]) -> int:
    """How many forbidden claims appear, as a normalized phrase, anywhere in the output."""
    haystack = f" {normalize(' '.join(texts))} "
    return sum(1 for claim in must_not_claim if f" {normalize(claim)} " in haystack)


def portuguese_share(texts: Sequence[str]) -> float | None:
    """Portuguese stopwords over all recognised stopwords; `None` with too little text."""
    words = [word.lower() for text in texts for word in _WORD.findall(text)]
    portuguese = sum(1 for word in words if word in _PORTUGUESE_WORDS)
    english = sum(1 for word in words if word in _ENGLISH_WORDS)
    if portuguese + english < 3:
        return None
    return portuguese / (portuguese + english)


def fidelity(evidence: Sequence[str], payload_text: str) -> float | None:
    """Share of quoted evidence found verbatim in the payload. Schema `v1` has none."""
    if not evidence:
        return None
    source = normalize(payload_text)
    return sum(1 for quote in evidence if normalize(quote) in source) / len(evidence)


@dataclass(frozen=True, slots=True)
class CaseScore:
    case_id: str
    status: str
    failure_code: str | None
    fidelity: float | None
    coverage: float | None
    inventions: int | None
    portuguese: float | None
    prompt_tokens: int | None
    output_tokens: int | None
    total_ms: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "status": self.status,
            "failure_code": self.failure_code,
            "fidelity": self.fidelity,
            "coverage": self.coverage,
            "inventions": self.inventions,
            "portuguese": self.portuguese,
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.output_tokens,
            "total_ms": self.total_ms,
        }


def score_case(case: EvalCase, outcome: AnalysisOutcome) -> CaseScore:
    metrics = outcome.metrics or AnalysisMetrics()
    analysis = outcome.analysis
    if analysis is None:
        return CaseScore(
            case_id=case.case_id,
            status=outcome.status.value,
            failure_code=outcome.failure_code.value if outcome.failure_code else None,
            fidelity=None,
            coverage=None,
            inventions=None,
            portuguese=None,
            prompt_tokens=metrics.prompt_tokens,
            output_tokens=metrics.output_tokens,
            total_ms=metrics.total_ms,
        )
    texts = [
        analysis.summary,
        *analysis.strengths,
        *analysis.risks,
        *analysis.inferences,
        *analysis.unknowns,
    ]
    evidence = [str(item) for item in getattr(analysis, "evidence", ())]
    return CaseScore(
        case_id=case.case_id,
        status=outcome.status.value,
        failure_code=None,
        fidelity=fidelity(evidence, case.payload_text()),
        coverage=coverage(analysis.risks, case.expected.must_mention_risks),
        inventions=inventions(texts, case.expected.must_not_claim),
        portuguese=portuguese_share(texts),
        prompt_tokens=metrics.prompt_tokens,
        output_tokens=metrics.output_tokens,
        total_ms=metrics.total_ms,
    )


#: Criterion -> True when a higher number is better.
CRITERIA: dict[str, bool] = {
    "completed_rate": True,
    "fidelity": True,
    "coverage": True,
    "inventions": False,
    "portuguese": True,
    "prompt_tokens": False,
    "output_tokens": False,
    "total_ms": False,
}


def summarize(scores: Sequence[CaseScore]) -> dict[str, float | None]:
    def mean(values: Iterable[float | int | None]) -> float | None:
        present = [float(value) for value in values if value is not None]
        return sum(present) / len(present) if present else None

    return {
        "completed_rate": (
            sum(1 for score in scores if score.status == "AI_COMPLETED") / len(scores)
            if scores
            else None
        ),
        "fidelity": mean(score.fidelity for score in scores),
        "coverage": mean(score.coverage for score in scores),
        # Total, not mean: one invention is one too many, however many cases ran.
        "inventions": float(sum(score.inventions or 0 for score in scores)),
        "portuguese": mean(score.portuguese for score in scores),
        "prompt_tokens": mean(score.prompt_tokens for score in scores),
        "output_tokens": mean(score.output_tokens for score in scores),
        "total_ms": mean(score.total_ms for score in scores),
    }


def compare(
    current: Mapping[str, float | None],
    baseline: Mapping[str, float | None],
    *,
    tolerance: float = 0.01,
) -> dict[str, str]:
    """`melhora`, `piora`, `empate`, or `sem dado` per criterion, in reading order."""
    verdicts: dict[str, str] = {}
    for criterion, higher_is_better in CRITERIA.items():
        now, before = current.get(criterion), baseline.get(criterion)
        if now is None or before is None:
            verdicts[criterion] = "sem dado"
            continue
        scale = max(abs(before), 1.0)
        delta = (now - before) / scale
        if abs(delta) <= tolerance:
            verdicts[criterion] = "empate"
        elif (delta > 0) == higher_is_better:
            verdicts[criterion] = "melhora"
        else:
            verdicts[criterion] = "piora"
    return verdicts


__all__ = [
    "CASE_KINDS",
    "CRITERIA",
    "CaseScore",
    "EvalCase",
    "EvalCaseError",
    "Expected",
    "compare",
    "coverage",
    "fidelity",
    "inventions",
    "load_case",
    "load_cases",
    "missing_kinds",
    "normalize",
    "portuguese_share",
    "score_case",
    "summarize",
]
