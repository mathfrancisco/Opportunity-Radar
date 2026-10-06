"""F52-09: the search evaluation carries level cases and its runner executes them.

A level case pairs a query with the seniorities that must not show up in the top results
("júnior remoto" must not return a `SENIOR` or higher posting). The cases live in
`scripts/eval_search.py` (`LEVEL_CASES`); the frozen manifest of `search_benchmark.py` and
its signed gold are not touched.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from opportunity_radar.platform.database import create_database_engine
from scripts import eval_search

from .test_queries import _company, _opportunity

NOW = datetime.now(UTC)

requires_database = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)


def test_level_cases_include_junior_remote_and_forbid_senior_or_higher() -> None:
    by_query = {case.query: case for case in eval_search.LEVEL_CASES}

    assert len(eval_search.LEVEL_CASES) >= 3
    assert set(by_query["júnior remoto"].forbidden_seniorities) == {
        "SENIOR",
        "STAFF",
        "LEAD",
        "MANAGER",
        "DIRECTOR",
    }
    assert all("UNKNOWN" not in case.forbidden_seniorities for case in eval_search.LEVEL_CASES)


def test_reference_file_may_add_level_cases(tmp_path) -> None:
    path = tmp_path / "queries.json"
    path.write_text(
        '{"queries": ['
        '{"query": "react remoto", "relevant_urls": []},'
        '{"query": "estágio", "forbidden_seniorities": ["MID", "SENIOR"]}'
        "]}",
        encoding="utf-8",
    )

    assert eval_search.reference_level_cases(path) == (
        eval_search.LevelCase("estágio", ("MID", "SENIOR")),
    )
    assert eval_search.reference_level_cases(tmp_path / "missing.json") == ()


@pytest.mark.integration
@requires_database
def test_level_cases_run_against_a_corpus_and_flag_a_senior_in_the_top() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        session.execute(text("TRUNCATE opportunities.opportunity CASCADE"))
        company = _company(session, "normal")
        for title, seniority, description in (
            ("Desenvolvedor Júnior Backend", "JUNIOR", "Vaga remota para início de carreira."),
            ("Desenvolvedor Pleno Backend", "MID", "Atuação remota em produto."),
            ("Desenvolvedor Sênior Backend", "SENIOR", "Atuação remota, liderança técnica."),
            ("Staff Engineer Platform", "STAFF", "Remote, plataforma interna."),
        ):
            _opportunity(
                session,
                company,
                title=title,
                published_at=NOW,
                seniority=seniority,
                description=description,
            )
        session.commit()

        clean = eval_search.evaluate_level_cases(session, "fulltext", eval_search.LEVEL_CASES)

        assert [case["query"] for case in clean] == [
            case.query for case in eval_search.LEVEL_CASES
        ]
        assert all(case["returned"] >= 1 for case in clean)
        assert all(case["passed"] for case in clean), clean

        _opportunity(
            session,
            company,
            title="Desenvolvedor Júnior Remoto Liderança",
            published_at=NOW,
            seniority="SENIOR",
            description="Júnior remoto no nome, mas nível sênior.",
        )
        session.commit()

        flagged = eval_search.evaluate_level_cases(
            session, "fulltext", (eval_search.LevelCase("júnior remoto"),)
        )

        assert flagged[0]["passed"] is False
        assert [row["seniority"] for row in flagged[0]["violations"]] == ["SENIOR"]  # type: ignore[index]
