"""Export anonymised drafts of evaluation cases from the collection.

    python scripts/export_eval_cases.py --per-verdict 8

Card F16-06. Writes `prompts/opportunity_analysis/eval/drafts/NN-<verdict>.json` from
current assessments, spread across verdicts. A draft is not a case: its answer key is
empty. The operator reviews the anonymisation, fills `must_mention_risks` and
`must_not_claim`, and moves it to `eval/cases/`. Drafts are git-ignored because they
have not been reviewed yet, and the repository is public.

Anonymisation removes what code can find — ids, company names, URLs, e-mails, the
profile's compensation. Names of people inside a description are left to the review.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from opportunity_radar.companies.models import Company
from opportunity_radar.matching.evaluation import portuguese_share
from opportunity_radar.matching.models import MatchAssessmentModel
from opportunity_radar.matching.prompts import prompts_root
from opportunity_radar.matching.text import clean_description
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine

DRAFTS_DIR = prompts_root() / "opportunity_analysis" / "eval" / "drafts"
_VERDICTS = ("HIGH_PRIORITY", "RECOMMENDED", "REVIEW_REQUIRED", "WATCHLIST", "LOW_MATCH")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_URL = re.compile(r"https?://\S+|www\.\S+", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PLACEHOLDER_ID = "00000000-0000-0000-0000-000000000000"
_LONG_DESCRIPTION_CHARS = 4000


def _scrub(value: Any) -> Any:
    """Every id in a snapshot becomes the same placeholder, recursively."""
    if isinstance(value, dict):
        return {key: _scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, str):
        return _UUID.sub(_PLACEHOLDER_ID, value)
    return value


def _anonymise_text(text: str, company: str | None) -> str:
    result = _EMAIL.sub("[e-mail]", _URL.sub("[link]", text))
    if company:
        result = re.sub(re.escape(company), "Empresa X", result, flags=re.IGNORECASE)
    return result


def _kinds(verdict: str, snapshot: dict[str, Any], description: str) -> list[str]:
    kinds = {
        "HIGH_PRIORITY": "strong_match",
        "RECOMMENDED": "strong_match",
        "REVIEW_REQUIRED": "ambiguous",
        "WATCHLIST": "weak_match",
        "LOW_MATCH": "weak_match",
    }
    found = {kinds[verdict]}
    if not description:
        found.add("no_description")
    elif len(description) > _LONG_DESCRIPTION_CHARS:
        found.add("long_description")
    share = portuguese_share([description]) if description else None
    if share is not None and share < 0.5:
        found.add("english_description")
    if not snapshot.get("compensation"):
        found.add("missing_compensation")
    if not snapshot.get("allowed_countries"):
        found.add("missing_country")
    return sorted(found)


def _draft(
    assessment: MatchAssessmentModel, opportunity: OpportunityModel, company: str | None
) -> dict[str, Any]:
    description = _anonymise_text(clean_description(opportunity.description), company)
    profile = _scrub(dict(assessment.profile_snapshot))
    profile.pop("compensation", None)  # the operator's own expectation, never published
    snapshot = _scrub(dict(assessment.opportunity_snapshot))
    return {
        "kinds": _kinds(assessment.verdict, snapshot, description),
        "payload": {
            "eligibility": assessment.eligibility,
            "verdict": assessment.verdict,
            "score": str(assessment.score),
            "rules_version": assessment.rules_version,
            "taxonomy_version": assessment.taxonomy_version,
            "opportunity_snapshot": snapshot,
            "profile_snapshot": profile,
        },
        "posting": {
            "title": _anonymise_text(opportunity.canonical_title, company),
            "description": description,
        },
        "expected": {
            "verdict": assessment.verdict,
            "must_mention_risks": [],
            "must_not_claim": [],
            "language": "pt-BR",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-verdict", type=int, default=8)
    parser.add_argument("--output", type=Path, default=DRAFTS_DIR)
    args = parser.parse_args(argv)

    settings = Settings()  # type: ignore[call-arg]  # values come from the environment
    engine = create_database_engine(settings.database_url)
    newer = aliased(MatchAssessmentModel)
    args.output.mkdir(parents=True, exist_ok=True)
    written = 0
    with Session(engine) as session:
        for verdict in _VERDICTS:
            rows = session.execute(
                select(MatchAssessmentModel, OpportunityModel, Company.canonical_name)
                .join(OpportunityModel, OpportunityModel.id == MatchAssessmentModel.opportunity_id)
                .outerjoin(Company, Company.id == OpportunityModel.canonical_company_id)
                .where(
                    MatchAssessmentModel.verdict == verdict,
                    ~select(newer.id)
                    .where(
                        newer.opportunity_id == MatchAssessmentModel.opportunity_id,
                        newer.assessed_at > MatchAssessmentModel.assessed_at,
                    )
                    .exists(),
                )
                .order_by(MatchAssessmentModel.assessed_at.desc())
                .limit(args.per_verdict)
            ).all()
            for assessment, opportunity, company in rows:
                written += 1
                path = args.output / f"{written:02d}-{verdict.lower()}.json"
                path.write_text(
                    json.dumps(
                        _draft(assessment, opportunity, company), ensure_ascii=False, indent=2
                    )
                    + "\n",
                    encoding="utf-8",
                )
    print(f"wrote {written} drafts to {args.output}; review, fill the answer key, then move")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
