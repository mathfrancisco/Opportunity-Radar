"""One-off, real-Groq measurement of the token-estimate error (card F20-13).

Not a pytest: it spends real Groq quota against `GROQ_API_KEY` and must never run in CI.
Run it manually, with a real key, from the repository root:

    docker compose --env-file /path/to/.env -f compose.yaml -f compose.dev.yaml \\
        run --rm api python scripts/measure_token_estimate_error.py

Compares `platform.ai.budget.estimate_tokens` -- the character-based estimate the Quota
Guard reserves against before a call -- with the real `usage.prompt_tokens` Groq reports
for the same request, over 20+ real job postings. Prefers the collection's own postings
(`opportunities.opportunity.description`); when the database has fewer than 20 (true of
a fresh dev database), falls back to real, live postings from a public Greenhouse job
board -- real content, not synthetic filler, so the characters-per-token ratio is
measured against a real distribution of descriptions, the same kind `GroqAnalysisAdapter`
will see in production.

The `GroqAnalysisAdapter.prepare()` call under measurement is exactly the one production
uses (same sanitizer, same cleaner, same budget math); the network call bypasses the
router (no fallback, no persistent quota reservation) and calls the real `GroqProvider`
directly, on the same model `AITask.JOB_MATCH` would route to, waiting out the account's
own rate limit on a 429 rather than treating it as a measurement failure.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.matching.analysis import OUTPUT_SCHEMAS, AnalysisRequest
from opportunity_radar.matching.domain import EligibilityStatus, Verdict
from opportunity_radar.matching.groq import GroqAnalysisAdapter
from opportunity_radar.matching.prompts import load_prompt
from opportunity_radar.matching.text import clean_description_report
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.platform.ai.errors import ErrorKind, ProviderError
from opportunity_radar.platform.ai.providers.base import LLMRequest, LLMResponse
from opportunity_radar.platform.ai.providers.groq import GroqProvider
from opportunity_radar.platform.ai.router import AIRouter
from opportunity_radar.platform.ai.tasks import AITask, ModelRoute, default_routes
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine

_MIN_POSTINGS = 20
_GREENHOUSE_BOARDS = ("gitlab", "elastic", "airbnb", "stripe", "asana")
_GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
_MAX_DESCRIPTION_CHARS = 6000  # keeps each real call's cost small and comparable
#: The output itself is discarded -- only `usage.prompt_tokens` matters -- but the real
#: analysis schema and the production output budget are used anyway: a 400 from Groq
#: (a model that cannot fill the schema at all) never reports `usage`, so a schema this
#: script does not exercise for real would silently measure nothing.
_MAX_COMPLETION_TOKENS = 900
_MAX_QUOTA_RETRIES = 6

_PROFILE_SNAPSHOT = {
    "headline": "Senior Backend Engineer",
    "skills": ["Python", "PostgreSQL", "Distributed systems", "REST APIs"],
    "years_experience": 8,
    "seniority": "SENIOR",
    "accepted_work_modes": ["REMOTE", "HYBRID"],
}


@dataclass(frozen=True)
class _Posting:
    title: str
    description: str


class _UnusedProvider:
    """Satisfies `AIRouter`'s constructor; `prepare()` never calls it."""

    name = "unused"

    async def complete(self, request: LLMRequest) -> LLMResponse:  # pragma: no cover
        raise AssertionError("measurement calls the provider directly, never through the router")


def _postings_from_db(session: Session, limit: int) -> list[_Posting]:
    rows = session.execute(
        select(OpportunityModel.canonical_title, OpportunityModel.description)
        .where(OpportunityModel.description.is_not(None))
        .limit(limit)
    ).all()
    return [
        _Posting(title=title or "Untitled role", description=description)
        for title, description in rows
        if description and len(description.strip()) > 200
    ]


def _postings_from_greenhouse(limit: int) -> list[_Posting]:
    postings: list[_Posting] = []
    with httpx.Client(timeout=15.0) as client:
        for board in _GREENHOUSE_BOARDS:
            if len(postings) >= limit:
                break
            response = client.get(_GREENHOUSE_URL.format(board=board))
            if response.status_code != 200:
                continue
            for job in response.json().get("jobs", []):
                content = job.get("content")
                if not content or len(content) < 400:
                    continue
                postings.append(
                    _Posting(title=str(job.get("title") or "Untitled role"), description=content)
                )
                if len(postings) >= limit:
                    break
    return postings


def _gather_postings(settings: Settings, limit: int) -> tuple[list[_Posting], str]:
    engine = create_database_engine(settings.database_url)
    with Session(engine) as session:
        from_db = _postings_from_db(session, limit)
    if len(from_db) >= _MIN_POSTINGS:
        return from_db[:limit], "database"
    from_web = _postings_from_greenhouse(limit)
    return from_web[:limit], "greenhouse (public boards; database had too few)"


def _request_for(posting: _Posting) -> AnalysisRequest:
    cleaned = clean_description_report(posting.description).text[:_MAX_DESCRIPTION_CHARS]
    return AnalysisRequest(
        opportunity_id=UUID("00000000-0000-0000-0000-000000000001"),
        opportunity_content_version=1,
        profile_version_id=UUID("00000000-0000-0000-0000-000000000002"),
        rules_version="measurement",
        taxonomy_version="measurement",
        eligibility=EligibilityStatus.ELIGIBLE,
        verdict=Verdict.RECOMMENDED,
        score=Decimal("80"),
        # `analysis_prompt.v1` only reads `opportunity` and `profile`; the real posting
        # text goes in `opportunity_snapshot` so the prompt's length genuinely varies
        # with real content, which is what this measurement is calibrating against.
        opportunity_snapshot={"title": posting.title, "description": cleaned},
        profile_snapshot=_PROFILE_SNAPSHOT,
    )


async def _measure_one(
    adapter: GroqAnalysisAdapter, provider: GroqProvider, route: ModelRoute, posting: _Posting
) -> dict[str, object]:
    prepared = adapter.prepare(_request_for(posting))
    estimate = prepared.size.prompt_tokens_estimate or 0
    request = LLMRequest(
        model=route.chain[0],
        system=prepared.system,
        user=prepared.user_content,
        schema_name="measurement",
        json_schema=OUTPUT_SCHEMAS[prepared.schema_version],
        max_completion_tokens=_MAX_COMPLETION_TOKENS,
        temperature=0,
        reasoning_effort=route.budget.reasoning_effort,
    )
    # This script has no router, so it has no fallback and no circuit breaker; it does
    # need the router's patience with a soft-tier TPM limit, one request at a time.
    for attempt in range(_MAX_QUOTA_RETRIES + 1):
        try:
            response = await provider.complete(request)
            break
        except ProviderError as error:
            if error.kind is not ErrorKind.QUOTA or attempt == _MAX_QUOTA_RETRIES:
                raise
            wait_seconds = (error.retry_after_seconds or 60.0) + 1.0
            print(f"    (rate limited, waiting {wait_seconds:.0f}s)")
            await asyncio.sleep(wait_seconds)
    actual = response.usage.prompt_tokens
    return {
        "title": posting.title,
        "prompt_chars": prepared.size.prompt_chars,
        "estimate": estimate,
        "actual": actual,
        "error": None if not actual else (actual - estimate) / actual,
        "underestimated": actual is not None and actual > estimate,
    }


def _report(rows: list[dict[str, object]]) -> dict[str, object]:
    errors = [row["error"] for row in rows if row["error"] is not None]
    underestimates = [row for row in rows if row["underestimated"]]
    return {
        "postings_measured": len(rows),
        "mean_error": statistics.mean(errors) if errors else None,
        "median_error": statistics.median(errors) if errors else None,
        "max_error": max(errors, key=abs) if errors else None,
        "underestimated_count": len(underestimates),
        "worst_underestimate": (
            max((row["error"] for row in underestimates), default=None)
        ),
        "rows": rows,
    }


async def _run(limit: int) -> dict[str, object]:
    settings = Settings()  # type: ignore[call-arg]  # values come from the environment
    if not settings.groq_api_key.get_secret_value():
        raise SystemExit("GROQ_API_KEY is not set; pass --env-file to docker compose")

    postings, source = _gather_postings(settings, limit)
    if len(postings) < _MIN_POSTINGS:
        raise SystemExit(
            f"only found {len(postings)} usable postings (need {_MIN_POSTINGS}); "
            "the database is empty and the public Greenhouse boards did not answer"
        )

    prompt = load_prompt(settings.ai_analysis_prompt)
    route = default_routes(settings)[AITask.JOB_MATCH]
    router = AIRouter(_UnusedProvider(), default_routes(settings))
    adapter = GroqAnalysisAdapter(router=router, prompt=prompt)
    provider = GroqProvider(
        api_key=settings.groq_api_key.get_secret_value(),
        base_url=settings.groq_base_url,
        timeout_seconds=settings.ai_timeout_seconds,
        connect_timeout_seconds=settings.ai_connect_timeout_seconds,
    )

    rows = []
    for index, posting in enumerate(postings, start=1):
        print(f"[{index}/{len(postings)}] {posting.title[:60]!r}")
        rows.append(await _measure_one(adapter, provider, route, posting))

    report = _report(rows)
    report["source"] = source
    report["model"] = route.chain[0]
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=25, help="postings to measure (>=20)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args(argv)

    report = asyncio.run(_run(args.limit))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0

    def _pct(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.3%}"

    print(f"Source: {report['source']}")
    print(f"Model: {report['model']}")
    print(f"Postings measured: {report['postings_measured']}")
    print(f"Mean error (actual-estimate)/actual: {_pct(report['mean_error'])}")
    print(f"Median error: {_pct(report['median_error'])}")
    print(f"Max |error|: {_pct(report['max_error'])}")
    print(f"Underestimated (actual > estimate): {report['underestimated_count']}")
    print(f"Worst underestimate: {_pct(report['worst_underestimate'])}")
    for row in report["rows"]:
        error = row["error"]
        error_text = "n/a" if error is None else f"{error:.3%}"
        title = str(row["title"])[:60]
        print(
            f"  - {title!r}: chars={row['prompt_chars']} "
            f"estimate={row['estimate']} actual={row['actual']} error={error_text}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
