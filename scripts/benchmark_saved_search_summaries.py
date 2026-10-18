"""Reproduce the saved-search summary SQL statement budget on an isolated test DB."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from sqlalchemy import event
from sqlalchemy.orm import Session

from opportunity_radar.companies.models import Company
from opportunity_radar.dashboard.models import SavedSearchModel
from opportunity_radar.dashboard.saved_searches import (
    create_saved_search,
    list_saved_search_summaries,
    list_saved_searches,
    new_count,
)
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.domain import EmploymentPreference, ProfileSnapshot
from opportunity_radar.profile.service import ProfileService

VACANCY_COUNT = 1_000


def _require_isolated_database() -> str:
    database_url = os.environ.get("DATABASE_URL", "")
    if (
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1"
        or os.environ.get("DATABASE_INTEGRATION_ISOLATED") != "1"
        or not database_url.split("?", 1)[0].endswith("_test")
    ):
        raise SystemExit("requires RUN_DATABASE_INTEGRATION=1 and an isolated *_test DATABASE_URL")
    return database_url


def _measure(engine: object, operation: object) -> tuple[object, int, float]:
    statements: list[str] = []

    def record(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        started_at = perf_counter()
        result = operation()
        elapsed_seconds = perf_counter() - started_at
    finally:
        event.remove(engine, "before_cursor_execute", record)
    return result, len(statements), elapsed_seconds


def _seed_opportunities(session: Session, *, owner_sub: str) -> Company:
    marker = uuid4().hex
    company = Company(
        canonical_name=f"Summary benchmark {marker}",
        normalized_name=f"summary-benchmark-{marker}",
        priority="normal",
    )
    session.add(company)
    session.flush()
    session.add_all(
        OpportunityModel(
            fingerprint=f"{marker}-{index}",
            fingerprint_version="v1",
            canonical_title=f"Data Engineer {index}",
            normalized_title=f"data engineer {index}",
            canonical_company_id=company.id,
            company_name=company.canonical_name,
            work_mode="REMOTE",
            seniority="SENIOR",
            contract_type="FULL_TIME",
            lifecycle_status="ACTIVE",
            role_family="DATA",
            version=1,
        )
        for index in range(VACANCY_COUNT)
    )
    session.commit()
    return company


def _create_searches(
    session: Session, *, owner_sub: str, filters: dict[str, object], count: int
) -> None:
    for index in range(count):
        create_saved_search(
            session,
            name=f"Benchmark {index}",
            term=None,
            filters=filters,
            owner_sub=owner_sub,
        )


def main() -> None:
    engine = create_database_engine(_require_isolated_database())
    marker = uuid4().hex
    all_areas: list[dict[str, object]] = []
    fallback: list[dict[str, object]] = []
    varied: dict[str, object] | None = None
    with Session(engine) as session:
        company = _seed_opportunities(session, owner_sub=marker)
        for saved_search_count in (0, 1, 20):
            owner_sub = f"summary-benchmark-all-areas-{marker}-{saved_search_count}"
            _create_searches(
                session,
                owner_sub=owner_sub,
                filters={"company_id": str(company.id), "all_areas": True},
                count=saved_search_count,
            )
            legacy, legacy_statements, legacy_seconds = _measure(
                engine,
                lambda: tuple(
                    new_count(session, saved_search, owner_sub=owner_sub)
                    for saved_search in list_saved_searches(session, owner_sub=owner_sub)
                ),
            )
            summaries, summary_statements, summary_seconds = _measure(
                engine,
                lambda: list_saved_search_summaries(session, owner_sub=owner_sub),
            )
            assert [summary.new_count for summary in summaries] == list(legacy)
            assert summary_statements == (1 if saved_search_count == 0 else 2)
            all_areas.append(
                {
                    "saved_searches": saved_search_count,
                    "legacy_statements": legacy_statements,
                    "summary_statements": summary_statements,
                    "legacy_seconds": round(legacy_seconds, 6),
                    "summary_seconds": round(summary_seconds, 6),
                    "count_per_search": 0 if not legacy else legacy[0],
                }
            )

        for saved_search_count in (1, 20):
            owner_sub = f"summary-benchmark-fallback-{marker}-{saved_search_count}"
            ProfileService(session, owner_sub).create_active_version(
                ProfileSnapshot(
                    skills=(),
                    experiences=(),
                    projects=(),
                    preferences=EmploymentPreference(target_role_families=("DATA",)),
                ),
                expected_profile_version=0,
            )
            _create_searches(
                session,
                owner_sub=owner_sub,
                filters={"company_id": str(company.id)},
                count=saved_search_count,
            )
            summaries, statements, elapsed_seconds = _measure(
                engine,
                lambda: list_saved_search_summaries(session, owner_sub=owner_sub),
            )
            assert len(summaries) == saved_search_count
            assert statements == 4
            fallback.append(
                {
                    "saved_searches": saved_search_count,
                    "summary_statements": statements,
                    "summary_seconds": round(elapsed_seconds, 6),
                    "count_per_search": summaries[0].new_count,
                }
            )

        owner_sub = f"summary-benchmark-varied-{marker}"
        variants = tuple(
            (f"Data Engineer {index}" if index % 4 == 0 else "missing vacancy", {
                "company_id": str(company.id),
                "all_areas": True if index % 3 else False,
                **({"area": "DATA"} if index % 3 == 0 else {}),
                **({"seniority": "SENIOR"} if index % 2 else {}),
            })
            for index in range(20)
        )
        saved = tuple(
            create_saved_search(session, name=f"Varied {index}", term=term, filters=filters, owner_sub=owner_sub)
            for index, (term, filters) in enumerate(variants)
        )
        cutoff = datetime.now(UTC)
        for saved_search in saved[-4:]:
            model = session.get(SavedSearchModel, saved_search.id)
            assert model is not None
            model.last_opened_at = cutoff
        session.commit()
        legacy, legacy_statements, legacy_seconds = _measure(
            engine,
            lambda: tuple(new_count(session, item, owner_sub=owner_sub) for item in list_saved_searches(session, owner_sub=owner_sub)),
        )
        summaries, summary_statements, summary_seconds = _measure(
            engine, lambda: list_saved_search_summaries(session, owner_sub=owner_sub)
        )
        assert [summary.new_count for summary in summaries] == list(legacy)
        varied = {"saved_searches": 20, "legacy_statements": legacy_statements, "summary_statements": summary_statements, "legacy_seconds": round(legacy_seconds, 6), "summary_seconds": round(summary_seconds, 6), "cutoff_searches": 4}

    print(
        json.dumps(
            {
                "vacancies": VACANCY_COUNT,
                "all_areas": all_areas,
                "profile_fallback": fallback,
                "varied_filters": varied,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
