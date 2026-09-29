"""Backfill startup evidence for companies discovered by F20-53 (card F20-54).

Reads only what the F20-53 proposals already recorded in their configuration
(`discovery_excerpt`, `startup_signal_strength`, `startup_signal_terms`, `startup_boards`)
and derives the evidence from that literal text, the same way live discovery does
(`derive_startup_evidence`). A proposal without an excerpt gets nothing: no signal is
invented. `--weak-company NAME` (repeatable) forces weak/`other` for companies that look
like recruiting agencies rather than startups, whatever their text says.

Idempotent: `record_startup_evidence` returns the existing row for an identical sighting.
"""

from __future__ import annotations

import argparse
import json
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import SourceDefinitionModel
from opportunity_radar.acquisition.startup_discovery import DISCOVERY_VIA
from opportunity_radar.companies.domain import normalize_name
from opportunity_radar.companies.models import Company
from opportunity_radar.companies.startup import derive_startup_evidence, record_startup_evidence
from opportunity_radar.platform.database import create_database_engine


def backfill(
    session: Session, *, weak_companies: frozenset[str], dry_run: bool
) -> list[dict[str, object]]:
    # The proposal is not linked to a `CompanySource`; `propose_startups` created the
    # company from `company_name`, so that is the join key (by normalized name).
    proposals = session.scalars(
        select(SourceDefinitionModel).where(
            SourceDefinitionModel.configuration["discovery_via"].as_string() == DISCOVERY_VIA
        )
    ).all()
    report: list[dict[str, object]] = []
    for proposal in proposals:
        config = proposal.configuration
        name = str(config.get("company_name", ""))
        company_id = session.scalar(
            select(Company.id).where(Company.normalized_name == normalize_name(name))
        )
        if company_id is None:
            report.append({"company": name, "result": "skipped: company not found"})
            continue
        excerpt = config.get("discovery_excerpt")
        terms = config.get("startup_signal_terms") or []
        boards = [b for b in config.get("startup_boards") or [] if isinstance(b, str)]
        if not isinstance(excerpt, str) or not excerpt.strip() or not boards:
            report.append({"company": name, "result": "skipped: no recorded text/url"})
            continue
        board_key = config.get("board_identifier") or config.get("company_identifier") or ""
        url = next((b for b in boards if board_key and str(board_key) in b), boards[0])
        term = str(terms[0]) if terms else str(config.get("discovery_query", ""))
        if name.casefold() in weak_companies:
            signal, strength, text, batch = (
                "other",
                "weak",
                f"busca por {term}; possível agência de recrutamento, não confirmada como startup",
                None,
            )
        else:
            derived = derive_startup_evidence(
                strong_term=config.get("startup_signal_strength") == "forte",
                term=term,
                excerpt=excerpt,
            )
            signal, strength, text, batch = (
                derived.signal,
                derived.strength,
                derived.source_text,
                derived.batch,
            )
        if not dry_run:
            record_startup_evidence(
                session,
                company_id,
                signal=signal,
                strength=strength,
                source_text=text,
                source_url=url,
                batch=batch,
            )
        report.append(
            {"company": name, "signal": signal, "strength": strength, "batch": batch, "url": url}
        )
    if not dry_run:
        session.commit()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weak-company", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required.")
    with Session(create_database_engine(database_url)) as session:
        report = backfill(
            session,
            weak_companies=frozenset(name.casefold() for name in args.weak_company),
            dry_run=args.dry_run,
        )
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
