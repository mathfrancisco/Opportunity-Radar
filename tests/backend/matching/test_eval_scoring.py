"""Scorers of the evaluation set, and the set itself: every case must load with its key."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.engine import Engine

from opportunity_radar.matching.analysis import (
    AnalysisFailureCode,
    AnalysisMetrics,
    AnalysisOutcome,
    AnalysisStatus,
    SemanticAnalysis,
)
from opportunity_radar.matching.evaluation import (
    EvalCase,
    EvalCaseError,
    Expected,
    compare,
    coverage,
    fidelity,
    inventions,
    load_case,
    load_cases,
    missing_kinds,
    portuguese_share,
    score_case,
    summarize,
)
from opportunity_radar.matching.prompts import prompts_root
from opportunity_radar.platform.ai.tasks import AITask, default_routes
from opportunity_radar.platform.config import Settings
from scripts import eval_analysis
from scripts.eval_analysis import _adapter, _run, resolve_routes

_CASE = {
    "kinds": ["strong_match", "missing_compensation"],
    "payload": {
        "eligibility": "ELIGIBLE",
        "verdict": "RECOMMENDED",
        "score": "78.5",
        "rules_version": "matching-v1",
        "taxonomy_version": "skills-v1",
        "opportunity_snapshot": {"content_version": 2, "required_skills": ["python"]},
        "profile_snapshot": {"skills": ["python"]},
    },
    "posting": {"title": "Backend Engineer", "description": "Kubernetes in production."},
    "split": "tuning",
    "group": "backend-engineer",
    "expected": {
        "verdict": "RECOMMENDED",
        "must_mention_risks": ["Kubernetes em produção"],
        "must_not_claim": ["salário competitivo"],
        "language": "pt-BR",
    },
}


def _write(tmp_path: Path, case: dict[str, object], name: str = "01-case.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(case), encoding="utf-8")
    return path


def _analysis(**overrides: object) -> SemanticAnalysis:
    values: dict[str, object] = {
        "summary": "Vaga de backend com a stack do perfil.",
        "strengths": ("Python está no perfil",),
        "risks": ("Exige Kubernetes em produção, que não está no perfil",),
        "inferences": (),
        "unknowns": ("A remuneração não é informada",),
        "recommended_review": False,
        "model_id": "qwen3:8b-q4_K_M",
        "prompt_version": "opportunity_analysis/v1",
    }
    values.update(overrides)
    return SemanticAnalysis(**values)  # type: ignore[arg-type]


def test_every_case_in_the_set_loads_with_a_complete_answer_key() -> None:
    directory = prompts_root() / "opportunity_analysis" / "eval" / "cases"

    cases = load_cases(directory)

    assert len({case.case_id for case in cases}) == len(cases)
    for case in cases:
        assert case.expected.must_not_claim
        assert case.request().verdict.value == case.expected.verdict


def test_a_case_loads_into_a_production_request(tmp_path: Path) -> None:
    case = load_case(_write(tmp_path, _CASE))

    request = case.request()
    assert case.case_id == "01-case"
    assert request.opportunity_content_version == 2
    assert str(request.score) == "78.5"
    assert case.expected.must_mention_risks == ("Kubernetes em produção",)


@pytest.mark.parametrize(
    "broken",
    [
        {**_CASE, "expected": {**_CASE["expected"], "must_not_claim": []}},
        {**_CASE, "expected": {**_CASE["expected"], "verdict": "WATCHLIST"}},
        {**_CASE, "kinds": ["made_up"]},
        {**_CASE, "payload": {"verdict": "RECOMMENDED"}},
    ],
)
def test_an_incomplete_case_is_refused(tmp_path: Path, broken: dict[str, object]) -> None:
    with pytest.raises(EvalCaseError):
        load_case(_write(tmp_path, broken))


def test_the_missing_kinds_are_reported(tmp_path: Path) -> None:
    case = load_case(_write(tmp_path, _CASE))

    assert "no_description" in missing_kinds([case])
    assert "strong_match" not in missing_kinds([case])


def test_coverage_matches_every_term_of_an_expected_risk_in_one_item() -> None:
    risks = ["Exige Kubernetes em produção", "Inglês fluente"]

    assert coverage(risks, ["kubernetes em producao"]) == 1.0
    assert coverage(risks, ["Kubernetes em produção", "AWS"]) == 0.5
    # Terms spread over two items do not count as naming the risk.
    assert coverage(["Kubernetes", "em produção"], ["Kubernetes em produção"]) == 0.0
    assert coverage(risks, []) is None


def test_an_invented_claim_is_counted_as_a_phrase_not_as_loose_words() -> None:
    texts = ["Oferece salário competitivo e plano de saúde."]

    assert inventions(texts, ["salário competitivo"]) == 1
    assert inventions(["O salário não é competitivo"], ["salário competitivo"]) == 0
    assert inventions(texts, ["salario competitivo", "vale refeição"]) == 1


def test_the_language_share_tells_portuguese_from_english() -> None:
    portuguese = portuguese_share(["A vaga não informa a remuneração e exige inglês."])
    english = portuguese_share(["The posting does not state the salary and is remote."])

    assert portuguese is not None and portuguese > 0.8
    assert english is not None and english < 0.2
    assert portuguese_share(["Python"]) is None


def test_fidelity_counts_quotes_found_verbatim_and_is_absent_without_evidence() -> None:
    payload = '{"description": "Kubernetes in production, five years of Python."}'

    assert fidelity(["Kubernetes in production"], payload) == 1.0
    assert fidelity(["Kubernetes in production", "ten years of Go"], payload) == 0.5
    assert fidelity([], payload) is None


def _case() -> EvalCase:
    return EvalCase(
        case_id="01-case",
        kinds=frozenset({"strong_match"}),
        payload=_CASE["payload"],  # type: ignore[arg-type]
        expected=Expected(
            verdict="RECOMMENDED",
            must_mention_risks=("Kubernetes em produção",),
            must_not_claim=("salário competitivo",),
            language="pt-BR",
        ),
    )


def test_a_completed_answer_is_scored_on_every_criterion() -> None:
    outcome = AnalysisOutcome(
        status=AnalysisStatus.AI_COMPLETED,
        analysis=_analysis(),
        metrics=AnalysisMetrics(total_ms=4200, prompt_tokens=1800, output_tokens=200),
    )

    score = score_case(_case(), outcome)

    assert score.coverage == 1.0
    assert score.inventions == 0
    assert score.portuguese is not None and score.portuguese > 0.8
    assert score.fidelity is None  # schema v1 carries no evidence
    assert (score.prompt_tokens, score.output_tokens, score.total_ms) == (1800, 200, 4200)


def test_an_answer_in_english_that_invents_pay_scores_badly() -> None:
    outcome = AnalysisOutcome(
        status=AnalysisStatus.AI_COMPLETED,
        analysis=_analysis(
            summary="The role offers a salário competitivo and is a great fit for the team.",
            risks=("No risks were found in the posting",),
            unknowns=(),
        ),
    )

    score = score_case(_case(), outcome)

    assert score.inventions == 1
    assert score.coverage == 0.0
    assert score.portuguese is not None and score.portuguese < 0.5


def test_a_failed_case_keeps_its_failure_and_no_quality_score() -> None:
    outcome = AnalysisOutcome(
        status=AnalysisStatus.AI_FAILED,
        failure_code=AnalysisFailureCode.SCHEMA_MISMATCH,
        metrics=AnalysisMetrics(total_ms=9000),
    )

    score = score_case(_case(), outcome)

    assert score.failure_code == "SCHEMA_MISMATCH"
    assert score.coverage is None and score.inventions is None
    assert score.total_ms == 9000
    assert summarize([score])["completed_rate"] == 0.0


def test_the_model_flag_overrides_only_the_job_match_chain_and_drops_fallback() -> None:
    settings = Settings(database_url="postgresql+psycopg://u:p@localhost/db")

    default = resolve_routes(settings, None)
    overridden = resolve_routes(settings, "openai/gpt-oss-120b")

    assert default == default_routes(settings)
    assert default[AITask.JOB_MATCH].chain[0] == settings.groq_reasoning_model
    assert overridden[AITask.JOB_MATCH].chain == ("openai/gpt-oss-120b",)
    # Every other route is untouched by the override.
    assert overridden[AITask.JOB_CLASSIFICATION] == default[AITask.JOB_CLASSIFICATION]
    assert overridden[AITask.JOB_EXTRACTION] == default[AITask.JOB_EXTRACTION]


@pytest.mark.parametrize(("model", "fallback"), [(None, True), ("configured/model", False)])
def test_adapter_keeps_quota_guard_and_sets_fallback_for_the_model_flag(
    monkeypatch: pytest.MonkeyPatch, model: str | None, fallback: bool
) -> None:
    settings = Settings(
        database_url="postgresql+psycopg://u:p@localhost/db", ai_fallback_enabled=True
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(eval_analysis, "GroqProvider", lambda **kwargs: object())
    monkeypatch.setattr(eval_analysis, "QuotaGuard", lambda engine, limits: "quota-guard")
    monkeypatch.setattr(eval_analysis, "CircuitBreaker", lambda **kwargs: object())

    def build_router(provider: object, routes: object, **kwargs: object) -> object:
        captured.update(kwargs)
        captured["routes"] = routes
        return object()

    monkeypatch.setattr(eval_analysis, "AIRouter", build_router)
    monkeypatch.setattr(eval_analysis, "load_prompt", lambda prompt: object())
    monkeypatch.setattr(
        eval_analysis, "GroqAnalysisAdapter", lambda **kwargs: kwargs
    )

    _adapter(
        settings,
        SimpleNamespace(prompt="v1", model=model),
        cast(Engine, object()),
    )

    assert captured["fallback_enabled"] is fallback
    assert captured["quota_guard"] == "quota-guard"
    routes = captured["routes"]
    assert routes == resolve_routes(settings, model)  # type: ignore[comparison-overlap]


def test_quota_refusal_marks_case_blocked_and_stops_without_retrying() -> None:
    quota_exhausted = AnalysisOutcome(
        status=AnalysisStatus.AI_FAILED, failure_code=AnalysisFailureCode.QUOTA_EXHAUSTED
    )

    class _FakeAdapter:
        calls = 0

        async def warm_up(self) -> None:
            return None

        async def describe(self) -> dict[str, object]:
            return {}

        def prepare(self, request: object) -> SimpleNamespace:
            return SimpleNamespace(inference={}, evidence_sources={})

        async def analyze(
            self, request: object, *, prepared: object, use_cache: bool
        ) -> AnalysisOutcome:
            del request, prepared, use_cache
            self.calls += 1
            return quota_exhausted

    adapter = _FakeAdapter()
    scores, repeats, identity, blocked_case = asyncio.run(_run(adapter, [_case(), _case()], 1))

    assert adapter.calls == 1
    assert blocked_case == "01-case"
    assert len(scores) == 1
    assert scores[0].status == "QUOTA_BLOCKED"
    assert scores[0].failure_code == "QUOTA_EXHAUSTED"
    assert repeats == {}
    assert identity == {"server": {}, "inference": {}}


def test_main_writes_the_quota_blocked_case_and_returns_nonzero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    class _QuotaBlockedAdapter:
        async def warm_up(self) -> None:
            return None

        async def describe(self) -> dict[str, object]:
            return {}

        def prepare(self, request: object) -> SimpleNamespace:
            return SimpleNamespace(inference={}, evidence_sources={})

        async def analyze(
            self, request: object, *, prepared: object, use_cache: bool
        ) -> AnalysisOutcome:
            del request, prepared, use_cache
            return AnalysisOutcome(
                status=AnalysisStatus.AI_FAILED,
                failure_code=AnalysisFailureCode.QUOTA_EXHAUSTED,
            )

    settings = Settings(database_url="postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setattr(eval_analysis, "Settings", lambda: settings)
    monkeypatch.setattr(eval_analysis, "load_cases", lambda path: [_case()])
    monkeypatch.setattr(eval_analysis, "create_database_engine", lambda url: object())

    def build_adapter(settings: Settings, args: object, engine: object) -> _QuotaBlockedAdapter:
        return _QuotaBlockedAdapter()

    monkeypatch.setattr(eval_analysis, "_adapter", build_adapter)

    exit_code = eval_analysis.main(["--output", str(tmp_path)])

    reports = list(tmp_path.glob("*.json"))
    assert exit_code == 1
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert report["quota_blocked_case"] == "01-case"
    assert report["cases"][0]["status"] == "QUOTA_BLOCKED"
    assert report["cases"][0]["failure_code"] == "QUOTA_EXHAUSTED"
    assert "quota guard blocked case 01-case" in capsys.readouterr().out


def test_the_comparison_reads_each_criterion_in_its_own_direction() -> None:
    baseline = {"coverage": 0.5, "inventions": 3.0, "total_ms": 5000.0, "fidelity": None}
    current = {"coverage": 0.8, "inventions": 3.0, "total_ms": 6000.0, "fidelity": 0.9}

    verdicts = compare(current, baseline)

    assert verdicts["coverage"] == "melhora"
    assert verdicts["inventions"] == "empate"
    assert verdicts["total_ms"] == "piora"
    assert verdicts["fidelity"] == "não comparável"
