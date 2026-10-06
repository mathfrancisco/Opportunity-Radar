"""Selection logic of the F51-11 support sample, no database needed."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.measure_content_classification import load_gold
from scripts.sample_rule_support import (
    build_entries,
    find_emissions,
    load_excluded_ids,
    select_per_rule,
    summarize,
)

RULE = "seniority:description_years_min"
OTHER_RULE = "work_mode:description_phrase"


def _item(index: int) -> tuple[dict[str, object], str]:
    return {"opportunity_id": f"job-{index:03d}", "description": f"text {index}"}, "MID"


def _emissions(count: int) -> dict[str, list[tuple[dict[str, object], str]]]:
    return {RULE: [_item(i) for i in range(count)], OTHER_RULE: [_item(i) for i in range(5)]}


def _ids(chosen: dict[str, list[tuple[dict[str, object], str]]], rule: str) -> list[str]:
    return [str(row["opportunity_id"]) for row, _ in chosen[rule]]


def test_a_fixed_seed_draws_the_same_jobs_whatever_the_input_order() -> None:
    emissions = _emissions(100)
    reversed_input = {rule: list(reversed(items)) for rule, items in emissions.items()}

    first = select_per_rule(emissions, per_rule=40, seed=7)
    again = select_per_rule(reversed_input, per_rule=40, seed=7)
    other_seed = select_per_rule(emissions, per_rule=40, seed=8)

    assert _ids(first, RULE) == _ids(again, RULE)
    assert _ids(first, RULE) != _ids(other_seed, RULE)


def test_jobs_in_the_existing_gold_are_never_drawn() -> None:
    excluded = {f"job-{i:03d}" for i in range(0, 100, 2)}

    chosen = select_per_rule(_emissions(100), exclude_ids=excluded, per_rule=40, seed=1)

    assert len(chosen[RULE]) == 40
    assert not excluded & set(_ids(chosen, RULE))
    assert not excluded & set(_ids(chosen, OTHER_RULE))


def test_the_cap_per_rule_holds_and_a_small_rule_takes_every_job() -> None:
    chosen = select_per_rule(_emissions(100), per_rule=40, seed=1)

    assert len(chosen[RULE]) == 40
    assert len(set(_ids(chosen, RULE))) == 40
    assert sorted(_ids(chosen, OTHER_RULE)) == [f"job-{i:03d}" for i in range(5)]


def test_the_summary_reports_support_and_thin_source_types() -> None:
    rows = [
        {"opportunity_id": f"a-{i}", "description": "d", "source_type": "greenhouse"}
        for i in range(25)
    ] + [{"opportunity_id": "r-1", "description": "d", "source_type": "remotive"}]
    emissions = {RULE: [(row, "MID") for row in rows], OTHER_RULE: [(rows[0], "REMOTE")]}
    chosen = select_per_rule(emissions, exclude_ids={"a-0"}, per_rule=40, seed=1)

    summary = summarize(emissions, chosen, exclude_ids={"a-0"}, min_support=20)

    assert summary["per_rule"][RULE]["emissions_in_catalogue"] == 26
    assert summary["per_rule"][RULE]["emissions_in_existing_gold"] == 1
    assert summary["per_rule"][RULE]["sampled"] == 25
    assert summary["per_rule"][OTHER_RULE]["can_reach_gate_minimum"] is False
    assert summary["by_source_type"] == {"greenhouse": 24, "remotive": 1}
    assert summary["source_types_under_minimum"] == ["remotive"]


def test_entries_carry_the_whole_description_and_no_label(tmp_path: Path) -> None:
    long_text = "x" * 5000
    row = {
        "opportunity_id": "job-1",
        "title": "Engineer",
        "company": "Acme",
        "location_text": "Remote",
        "source_type": "greenhouse",
        "description": long_text,
        "seniority": "UNKNOWN",
    }

    entries = build_entries({RULE: [(row, "MID")]})
    path = tmp_path / "sample.json"
    path.write_text(json.dumps({"casos": entries}), encoding="utf-8")

    assert entries[0]["trecho_descricao"] == long_text
    assert entries[0]["regra_selecao"] == RULE
    assert entries[0]["regra_valor"] == "MID"
    assert entries[0]["revisado_por"] is None
    assert entries[0]["judgment"] is None
    assert entries[0]["valor_recomendado"] is None
    assert load_gold(path) == []
    assert load_excluded_ids([path]) == {"job-1"}


def test_find_emissions_picks_the_jobs_where_a_description_rule_emits() -> None:
    emitting = {
        "opportunity_id": "e",
        "title": "Engineer",
        "description": "You bring 5+ years of experience building services.",
        "location_text": "Berlin",
    }
    silent = {
        "opportunity_id": "s",
        "title": "Engineer",
        "description": "We build things.",
        "location_text": "Berlin",
    }

    found = find_emissions([emitting, silent])

    assert [row["opportunity_id"] for row, _ in found[RULE]] == ["e"]
    assert all(row["opportunity_id"] != "s" for items in found.values() for row, _ in items)
