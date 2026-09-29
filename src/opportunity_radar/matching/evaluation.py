"""Offline evaluation of the semantic analysis against a fixed, hand-labelled set of cases.

SPEC 36, section 8. Changing the prompt, the model or its quantisation is a decision with
numbers: every run scores the same cases on the same criteria and is compared with a
baseline. Scoring is code, never another model's opinion; what code cannot judge —
whether the commentary agrees with the verdict, whether a quoted passage really supports
its claim, a negation, an optional requirement — is a human rubric column in the report.

Cases are split into `tuning` and `reserved`: the prompt is adjusted on the first and a
change is decided on the second. A family of near-identical postings (`group`) lives on
one side only, so the reserved set never grades what the tuning set taught.

Pure functions only. Running the cases against the provider lives in scripts/eval_analysis.py.
"""

from __future__ import annotations

import hashlib
import json
import math
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
    claim_text,
    item_evidence,
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
        # Added by the robustness review: keyword presence alone gets these wrong.
        "negation",
        "optional_requirement",
        "contradiction",
        "prompt_injection",
    }
)
SPLITS = ("tuning", "reserved")
#: Jaccard similarity of word shingles above which two postings are the same posting.
NEAR_DUPLICATE_THRESHOLD = 0.8
_SHINGLE = 5
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
_EVIDENCE_REJECTED = "quotes evidence absent"

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
    # Requirements the posting marks as optional or negates: naming them as a hard
    # requirement is wrong, but only a person can tell how a risk mentions them.
    optional_terms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvalCase:
    case_id: str
    kinds: frozenset[str]
    payload: Mapping[str, Any]
    expected: Expected
    posting: Mapping[str, Any] = field(default_factory=dict)
    split: str = "tuning"
    # Near-identical postings share a group, and a group lives in one split only.
    group: str = ""
    # Critical cases run several times with every cache off, to measure the variation
    # a fixed seed does not remove.
    critical: bool = False
    profile_history: Mapping[str, Any] = field(default_factory=dict)

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
            posting=self.posting or None,
            profile_history=self.profile_history or None,
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
    optional = expected.get("optional_terms") or []
    if not _strings(optional):
        raise EvalCaseError(f"{path.name}: optional_terms is a list of strings")
    split = raw.get("split")
    if split not in SPLITS:
        raise EvalCaseError(f"{path.name}: split must be one of {', '.join(SPLITS)}")
    group = raw.get("group")
    if not isinstance(group, str) or not group.strip():
        raise EvalCaseError(f"{path.name}: group names the family of similar postings")
    posting = raw.get("posting") or {}
    history = raw.get("profile_history") or {}
    return EvalCase(
        case_id=path.stem,
        kinds=kinds,
        payload=payload,
        expected=Expected(
            verdict=str(expected["verdict"]),
            must_mention_risks=tuple(risks),
            must_not_claim=tuple(claims),
            language=str(expected["language"]),
            optional_terms=tuple(optional),
        ),
        posting=posting if isinstance(posting, dict) else {},
        split=split,
        group=group.strip(),
        critical=raw.get("critical") is True,
        profile_history=history if isinstance(history, dict) else {},
    )


def load_cases(directory: Path) -> list[EvalCase]:
    cases = [load_case(path) for path in sorted(directory.glob("*.json"))]
    leaks = split_leaks(cases)
    if leaks:
        raise EvalCaseError("tuning and reserved share postings: " + "; ".join(leaks))
    return cases


def _shingles(text: str) -> set[tuple[str, ...]]:
    words = normalize(text).split()
    if len(words) < _SHINGLE:
        return {tuple(words)} if words else set()
    return {tuple(words[index : index + _SHINGLE]) for index in range(len(words) - _SHINGLE + 1)}


def _posting_text(case: EvalCase) -> str:
    return " ".join(str(case.posting.get(key) or "") for key in ("title", "description"))


def split_leaks(cases: Sequence[EvalCase]) -> list[str]:
    """Pairs across the two splits that share a group or are near-identical postings."""
    tuning = [case for case in cases if case.split == "tuning"]
    reserved = [case for case in cases if case.split == "reserved"]
    leaks: list[str] = []
    for left in tuning:
        left_shingles = _shingles(_posting_text(left))
        for right in reserved:
            if left.group == right.group:
                leaks.append(f"{left.case_id} and {right.case_id} share group {left.group}")
                continue
            right_shingles = _shingles(_posting_text(right))
            union = left_shingles | right_shingles
            if union and len(left_shingles & right_shingles) / len(union) >= (
                NEAR_DUPLICATE_THRESHOLD
            ):
                leaks.append(f"{left.case_id} and {right.case_id} are near-duplicates")
    return leaks


def cases_digest(cases: Iterable[EvalCase]) -> str:
    """One hash for the set as run, so two reports say whether they graded the same cases."""
    encoded = json.dumps(
        [
            {
                "id": case.case_id,
                "split": case.split,
                "payload": case.payload,
                "posting": case.posting,
                "history": case.profile_history,
                "expected": [
                    case.expected.verdict,
                    case.expected.must_mention_risks,
                    case.expected.must_not_claim,
                    case.expected.optional_terms,
                ],
            }
            for case in cases
        ],
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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


def optional_mentions(risks: Sequence[str], optional_terms: Sequence[str]) -> int:
    """Risks naming an optional or negated requirement: flags for the human rubric.

    Not a score. "Kubernetes é diferencial" and "exige Kubernetes" share every keyword;
    only a reader can tell the first is right and the second is not.
    """
    named = [_terms(risk) for risk in risks]
    return sum(1 for term in optional_terms for risk in named if _terms(term) <= risk)


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
    """Share of quoted evidence found verbatim in the payload. Schema `v1` has none.

    Presence only: a quote can be in the payload and still not support its claim.
    """
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
    # Share of strengths and risks that quote a passage; `None` under `analysis-v1`.
    grounded: float | None = None
    # The answer quoted a passage the payload does not contain and was refused.
    evidence_rejected: bool = False
    optional_mentions: int | None = None
    split: str = "tuning"

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "split": self.split,
            "status": self.status,
            "failure_code": self.failure_code,
            "fidelity": self.fidelity,
            "grounded": self.grounded,
            "evidence_rejected": self.evidence_rejected,
            "coverage": self.coverage,
            "inventions": self.inventions,
            "optional_mentions": self.optional_mentions,
            "portuguese": self.portuguese,
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.output_tokens,
            "total_ms": self.total_ms,
        }


def score_case(
    case: EvalCase,
    outcome: AnalysisOutcome,
    *,
    evidence_sources: Mapping[str, str] | None = None,
) -> CaseScore:
    """Score one answer. `evidence_sources` are the texts actually sent (after the cut);
    without them the case's own payload stands in, which only the v1 tests rely on."""
    metrics = outcome.metrics or AnalysisMetrics()
    analysis = outcome.analysis
    if analysis is None:
        rejected = outcome.failure_code is not None and _EVIDENCE_REJECTED in (
            outcome.detail or ""
        )
        return CaseScore(
            case_id=case.case_id,
            status=outcome.status.value,
            failure_code=outcome.failure_code.value if outcome.failure_code else None,
            # An invented quote is a fidelity failure, not an absence of data.
            fidelity=0.0 if rejected else None,
            coverage=None,
            inventions=None,
            portuguese=None,
            prompt_tokens=metrics.prompt_tokens,
            output_tokens=metrics.output_tokens,
            total_ms=metrics.total_ms,
            evidence_rejected=rejected,
            split=case.split,
        )
    items = [*analysis.strengths, *analysis.risks]
    risks = [claim_text(item) for item in analysis.risks]
    texts = [
        analysis.summary,
        *(claim_text(item) for item in items),
        *analysis.inferences,
        *analysis.unknowns,
    ]
    claims_with_schema = [item for item in items if not isinstance(item, str)]
    quoted = [item_evidence(item) for item in claims_with_schema]
    sources = evidence_sources or {"posting": case.payload_text(), "profile": ""}
    return CaseScore(
        case_id=case.case_id,
        status=outcome.status.value,
        failure_code=None,
        fidelity=fidelity(
            [evidence for evidence, _ in quoted if evidence],
            "\n".join(sources.values()),
        ),
        coverage=coverage(risks, case.expected.must_mention_risks),
        inventions=inventions(texts, case.expected.must_not_claim),
        portuguese=portuguese_share(texts),
        prompt_tokens=metrics.prompt_tokens,
        output_tokens=metrics.output_tokens,
        total_ms=metrics.total_ms,
        grounded=(
            sum(1 for evidence, _ in quoted if evidence) / len(quoted) if quoted else None
        ),
        optional_mentions=optional_mentions(risks, case.expected.optional_terms),
        split=case.split,
    )


#: Criterion -> True when a higher number is better.
CRITERIA: dict[str, bool] = {
    "completed_rate": True,
    "fidelity": True,
    "grounded": True,
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
        "grounded": mean(score.grounded for score in scores),
        "coverage": mean(score.coverage for score in scores),
        # Total, not mean: one invention is one too many, however many cases ran.
        "inventions": float(sum(score.inventions or 0 for score in scores)),
        "portuguese": mean(score.portuguese for score in scores),
        "prompt_tokens": mean(score.prompt_tokens for score in scores),
        "output_tokens": mean(score.output_tokens for score in scores),
        "total_ms": mean(score.total_ms for score in scores),
    }


def summarize_by_split(scores: Sequence[CaseScore]) -> dict[str, dict[str, float | None]]:
    """The summary of each split and of the whole run; decisions read `reserved`."""
    return {
        "all": summarize(scores),
        **{
            split: summarize([score for score in scores if score.split == split])
            for split in SPLITS
        },
    }


def variation(runs: Mapping[str, Sequence[CaseScore]]) -> dict[str, dict[str, Any]]:
    """How much repeated runs of a case disagree, which a fixed seed does not rule out."""
    report: dict[str, dict[str, Any]] = {}
    for case_id, scores in runs.items():
        values = [score.coverage for score in scores if score.coverage is not None]
        mean = sum(values) / len(values) if values else None
        spread = (
            math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))
            if mean is not None
            else None
        )
        report[case_id] = {
            "runs": len(scores),
            "statuses": sorted({score.status for score in scores}),
            "coverage_mean": mean,
            "coverage_stdev": spread,
            "total_ms": [score.total_ms for score in scores],
        }
    return report


def compare(
    current: Mapping[str, float | None],
    baseline: Mapping[str, float | None],
    *,
    tolerance: float = 0.01,
) -> dict[str, str]:
    """`melhora`, `piora`, `empate`, `não comparável` or `sem dado` per criterion.

    A criterion the baseline could not measure — evidence under `analysis-v1` — is not
    comparable: the new version has to meet its answer key, not beat an absence.
    """
    verdicts: dict[str, str] = {}
    for criterion, higher_is_better in CRITERIA.items():
        now, before = current.get(criterion), baseline.get(criterion)
        if now is not None and before is None:
            verdicts[criterion] = "não comparável"
            continue
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


def switch_allowed(verdicts: Mapping[str, str]) -> bool:
    """SPEC 36 §8: no criterion worse and at least one better, on the reserved split."""
    values = set(verdicts.values())
    return "piora" not in values and "melhora" in values


__all__ = [
    "CASE_KINDS",
    "CRITERIA",
    "SPLITS",
    "CaseScore",
    "EvalCase",
    "EvalCaseError",
    "Expected",
    "cases_digest",
    "compare",
    "coverage",
    "fidelity",
    "inventions",
    "load_case",
    "load_cases",
    "missing_kinds",
    "normalize",
    "optional_mentions",
    "portuguese_share",
    "score_case",
    "split_leaks",
    "summarize",
    "summarize_by_split",
    "switch_allowed",
    "variation",
]
