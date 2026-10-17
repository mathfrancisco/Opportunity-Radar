"""Measure the analysis prompt size on the R55-C2 fixture postings (read-only, no network).

    python scripts/measure_prompt_tokens.py [fixture.json]

Card R55-C2. Builds the real adapter with a router that has no provider and calls
`prepare` only, so nothing is sent. Prints, per posting, the characters and the estimated
prompt tokens, and whether the requirements section reached the prompt.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from opportunity_radar.matching.analysis import AnalysisRequest
from opportunity_radar.matching.domain import EligibilityStatus, Verdict
from opportunity_radar.matching.groq import GroqAnalysisAdapter
from opportunity_radar.matching.prompts import load_prompt
from opportunity_radar.platform.ai.router import AIRouter
from opportunity_radar.platform.ai.tasks import default_routes
from opportunity_radar.platform.config import Settings

DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[1] / "tests/backend/fixtures/r55_c2_postings.json"
)


def build_adapter(prompt_name: str = "v2") -> GroqAnalysisAdapter:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, database_url="postgresql+psycopg://u@h/db", ai_analysis_prompt=prompt_name
    )
    router = AIRouter(provider=None, routes=default_routes(settings))  # type: ignore[arg-type]
    return GroqAnalysisAdapter(router=router, prompt=load_prompt(prompt_name))


def measure(path: Path = DEFAULT_FIXTURE, prompt_name: str = "v2") -> list[dict[str, object]]:
    adapter = build_adapter(prompt_name)
    rows: list[dict[str, object]] = []
    for index, posting in enumerate(json.loads(path.read_text(encoding="utf-8"))):
        request = AnalysisRequest(
            opportunity_id=UUID(int=index + 1),
            opportunity_content_version=1,
            profile_version_id=UUID(int=99),
            rules_version="matching-v1",
            taxonomy_version="skills-v1",
            eligibility=EligibilityStatus.ELIGIBLE,
            verdict=Verdict.RECOMMENDED,
            score=Decimal("70"),
            opportunity_snapshot={"work_mode": "REMOTE", "seniority": "MID"},
            profile_snapshot={"skills": ["python", "sql"]},
            posting=posting,
        )
        prepared = adapter.prepare(request)
        sent = json.dumps(prepared.payload, ensure_ascii=False)
        rows.append(
            {
                "title": posting["title"],
                "prompt_chars": prepared.size.prompt_chars,
                "prompt_tokens_estimate": prepared.size.prompt_tokens_estimate,
                "has_requirements": "Requirements" in sent,
                "has_company_boilerplate": "Our Mission" in sent or "Why join us" in sent,
                "description_truncated": prepared.inference["cut"]["description_truncated"],
            }
        )
    return rows


if __name__ == "__main__":
    fixture = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FIXTURE
    rows = measure(fixture)
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))
    total = sum(int(row["prompt_tokens_estimate"] or 0) for row in rows)  # type: ignore[call-overload]
    print(json.dumps({"total_prompt_tokens_estimate": total, "postings": len(rows)}))
