"""Scoring, pre-flight and checkpoint/resume of `scripts/eval_field_suggestions.py` (F20-23)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts.eval_field_suggestions import (
    CaseResult,
    FieldScore,
    LabelledField,
    append_checkpoint,
    estimate_case_tokens,
    load_checkpoint,
    load_labels,
    merge_scores,
    preflight,
    run_round,
    score_field,
    summarize,
)

LABELS = Path("docs/44-roadmap-fase-20/rotulagem/f20-23-amostra-unknown.json")


def _lf(field: str, expected: str | None, opp: str = "o1") -> LabelledField:
    return LabelledField(opp, field, expected)


def _result(created: dict[str, tuple[str, str]] | None = None, **kwargs: object) -> CaseResult:
    return CaseResult(created=created or {}, called=True, model="m", **kwargs)  # type: ignore[arg-type]


def test_score_field_covers_every_status() -> None:
    hit = _result({"seniority": ("senior", "5+ years")})
    assert score_field(_lf("seniority", "SENIOR"), hit).status == "correct"
    assert score_field(_lf("seniority", "MID"), hit).status == "wrong"
    assert score_field(_lf("seniority", None), hit).status == "false_positive"
    silent = _result()
    assert score_field(_lf("seniority", "SENIOR"), silent).status == "abstained"
    assert score_field(_lf("seniority", None), silent).status == "correct_abstain"
    assert score_field(_lf("seniority", "SENIOR"), None).status == "not_run"
    assert score_field(_lf("seniority", "SENIOR"), CaseResult()).status == "not_run"


def test_discarded_suggestion_counts_as_abstained_and_is_flagged() -> None:
    score = score_field(_lf("work_mode", "HYBRID"), _result(discarded=frozenset({"work_mode"})))
    assert (score.status, score.discarded) == ("abstained", True)


def test_summary_precision_counts_false_positives_and_ignores_abstentions() -> None:
    scores = [
        FieldScore("a", "seniority", "SENIOR", "SENIOR", "e", "correct"),
        FieldScore("b", "seniority", "MID", "SENIOR", "e", "wrong"),
        FieldScore("c", "seniority", None, "JUNIOR", "e", "false_positive"),
        FieldScore("d", "seniority", "SENIOR", None, None, "abstained"),
        FieldScore("e", "seniority", None, None, None, "correct_abstain"),
        FieldScore("f", "work_mode", "HYBRID", "HYBRID", "e", "correct"),
        FieldScore("g", "work_mode", "HYBRID", None, None, "not_run"),
    ]
    summary = summarize(scores)
    assert summary["seniority"]["precision"] == 1 / 3
    assert summary["seniority"]["coverage"] == 2 / 3  # 3 valued labels ran, 2 suggested
    assert summary["work_mode"]["precision"] == 1.0
    assert summary["work_mode"]["not_run"] == 1
    assert summary["role_family"]["precision"] is None
    assert summary["all"]["correct"] == 2 and summary["all"]["labelled"] == 7


def test_load_labels_groups_by_opportunity_and_maps_keep_unknown_to_none(tmp_path: Path) -> None:
    sample = {
        "casos": [
            {"opportunity_id": "a", "field": "seniority", "valor_recomendado": "senior"},
            {"opportunity_id": "a", "field": "work_mode", "valor_recomendado": "HYBRID"},
            {"opportunity_id": "b", "field": "seniority", "valor_recomendado": None},
        ]
    }
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(sample), encoding="utf-8")
    cases = load_labels(path)
    assert [(i.field, i.expected) for i in cases["a"]] == [
        ("seniority", "SENIOR"), ("work_mode", "HYBRID")
    ]
    assert cases["b"][0].expected is None


@pytest.mark.skipif(not LABELS.exists(), reason="docs/ is not part of the test image")
def test_load_labels_reads_the_real_labelled_sample() -> None:
    cases = load_labels(LABELS)
    fields = [item for items in cases.values() for item in items]
    assert len(cases) == 30 and len(fields) == 39
    assert sum(1 for item in fields if item.expected is None) == 9
    assert {item.field for item in fields} == {"role_family", "seniority", "work_mode"}


def test_preflight_requires_the_estimate_to_fit_after_the_margin() -> None:
    ok, _ = preflight(
        estimate=60_000, used_tokens=20_000, day_ceiling=170_000, margin=0.3, allow_partial=False
    )
    assert ok  # 150k remaining, 105k usable
    ok, message = preflight(
        estimate=110_000, used_tokens=20_000, day_ceiling=170_000, margin=0.3, allow_partial=False
    )
    assert not ok and "aborting" in message
    ok, _ = preflight(
        estimate=110_000, used_tokens=20_000, day_ceiling=170_000, margin=0.3, allow_partial=True
    )
    assert ok


def test_estimate_case_tokens_caps_input_and_adds_output_budget() -> None:
    assert estimate_case_tokens(3_000, 300, max_input=1500) == 1_100 + 300
    assert estimate_case_tokens(30_000, 300, max_input=1500) == 1500 + 300


class _Fake:
    def __init__(self, plan: dict[str, list[CaseResult]], cost: int = 1_000) -> None:
        self.plan = plan
        self.cost = cost
        self.calls: list[str] = []
        self.spent = 0

    async def suggest(self, opportunity_id: str, fields: Sequence[str]) -> CaseResult:
        self.calls.append(opportunity_id)
        result = self.plan[opportunity_id].pop(0)
        if result.called:
            self.spent += self.cost
        return result

    def used(self) -> int:
        return self.spent


async def _nosleep(_: float) -> None:
    return None


def _cases() -> dict[str, list[LabelledField]]:
    return {
        "o1": [_lf("seniority", "SENIOR", "o1")],
        "o2": [_lf("work_mode", "HYBRID", "o2")],
        "o3": [_lf("seniority", None, "o3")],
    }


def test_max_tokens_stops_cleanly_and_resume_skips_finished_opportunities(tmp_path: Path) -> None:
    ok = lambda f, v: _result({f: (v, "ev")})  # noqa: E731
    fake = _Fake({"o1": [ok("seniority", "SENIOR")], "o2": [ok("work_mode", "REMOTE")],
                  "o3": [_result()]})
    path = tmp_path / "cp.jsonl"
    first = asyncio.run(
        run_round(
            _cases(), fake.suggest, fake.used, lambda _: 1_000, max_tokens=2_000,
            checkpoint_writer=lambda r: append_checkpoint(path, r), sleeper=_nosleep,
        )
    )
    assert first.stopped_for_tokens and set(first.records) == {"o1", "o2"}
    assert first.tokens_spent == 2_000

    checkpoint = load_checkpoint(path)
    assert set(checkpoint) == {"o1", "o2"}
    second = asyncio.run(
        run_round(
            _cases(), fake.suggest, fake.used, lambda _: 1_000,
            skip=frozenset(checkpoint),
            checkpoint_writer=lambda r: append_checkpoint(path, r), sleeper=_nosleep,
        )
    )
    assert fake.calls == ["o1", "o2", "o3"]  # o1/o2 never repeated
    scores = merge_scores(_cases(), checkpoint, second.records)
    assert [s.status for s in scores] == ["correct", "wrong", "correct_abstain"]
    assert json.loads(path.read_text().splitlines()[0])["opportunity_id"] == "o1"


def test_call_that_never_ran_is_retried_then_recorded_not_run_and_not_checkpointed(
    tmp_path: Path,
) -> None:
    fake = _Fake({"o1": [CaseResult(), CaseResult()], "o2": [], "o3": []})
    path = tmp_path / "cp.jsonl"
    sleeps: list[float] = []

    async def sleeper(seconds: float) -> None:
        sleeps.append(seconds)

    outcome = asyncio.run(
        run_round(
            _cases(), fake.suggest, fake.used, lambda _: 1_000,
            checkpoint_writer=lambda r: append_checkpoint(path, r), sleeper=sleeper,
            retry_wait_seconds=65,
        )
    )
    assert fake.calls == ["o1", "o1"] and sleeps == [65]
    assert outcome.stopped_for_quota
    assert outcome.records["o1"]["scores"][0]["status"] == "not_run"
    assert not path.exists()  # a not-run opportunity is retried by --resume


def test_pacing_sleeps_in_proportion_to_tokens_spent() -> None:
    fake = _Fake({"o1": [_result()], "o2": [_result()], "o3": [_result()]}, cost=1_400)
    sleeps: list[float] = []

    async def sleeper(seconds: float) -> None:
        sleeps.append(seconds)

    asyncio.run(
        run_round(
            _cases(), fake.suggest, fake.used, lambda _: 1_000, sleeper=sleeper,
            pace_tokens_per_minute=7_000,
        )
    )
    assert sleeps == [12.0, 12.0, 12.0]  # 1400 tokens * 60 / 7000
