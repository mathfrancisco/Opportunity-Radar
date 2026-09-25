"""Maintain the search reference set at `data/search-reference/queries.json`.

    python scripts/search_reference.py init
    python scripts/search_reference.py add --query "python remoto" --opportunity-id <uuid>
    python scripts/search_reference.py resolve
    python scripts/search_reference.py resolve --json

Card F17-01. The reference set backs the recall@10 metric F17-03 and F16-10 read, and is
kept out of git (`data/search-reference/`): opportunity ids are local-database ids, so the
file stores the vaga's canonical URL instead, resolved back to whatever id it has in the
current database. That is what survives a backup restore.

40 queries is the SPEC's target (§10); `init` only scaffolds empty ones, it never invents
relevant vagas.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.models import OpportunityModel, SourceOccurrenceModel
from opportunity_radar.platform.database import create_database_engine

DEFAULT_PATH = Path("data/search-reference/queries.json")
REFERENCE_QUERY_COUNT = 40


def _load(path: Path) -> dict[str, list[dict[str, Any]]]:
    if not path.exists():
        return {"queries": []}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("queries"), list):
        raise ValueError(f"{path} is not a valid search reference file.")
    return data


def _save(path: Path, data: dict[str, list[dict[str, Any]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def init_reference(path: Path = DEFAULT_PATH) -> dict[str, list[dict[str, Any]]]:
    """Create the file with 40 empty query slots, unless it already exists."""
    if path.exists():
        return _load(path)
    data = {"queries": [{"query": "", "relevant_urls": []} for _ in range(REFERENCE_QUERY_COUNT)]}
    _save(path, data)
    return data


def canonical_url(session: Session, opportunity_id: UUID) -> str | None:
    """The URL an opportunity is found by, stable across a backup restore."""
    return session.scalar(
        select(
            func.coalesce(
                SourceOccurrenceModel.normalized_source_url,
                SourceOccurrenceModel.source_url,
            )
        )
        .where(SourceOccurrenceModel.opportunity_id == opportunity_id)
        .order_by(SourceOccurrenceModel.first_seen_at)
        .limit(1)
    )


def add_relevant(
    session: Session,
    *,
    query: str,
    opportunity_id: UUID,
    path: Path = DEFAULT_PATH,
) -> dict[str, list[dict[str, Any]]]:
    data = _load(path)
    url = canonical_url(session, opportunity_id)
    if url is None:
        raise ValueError(f"opportunity {opportunity_id} has no source occurrence with a URL")
    entry = next((item for item in data["queries"] if item.get("query") == query), None)
    if entry is None:
        entry = {"query": query, "relevant_urls": []}
        data["queries"].append(entry)
    urls = entry.setdefault("relevant_urls", [])
    if url not in urls:
        urls.append(url)
    _save(path, data)
    return data


def resolve(session: Session, path: Path = DEFAULT_PATH) -> list[dict[str, Any]]:
    """Resolve every stored URL back to the opportunity it names in this database.

    A URL with no match is reported, not dropped silently: the reference set is only as
    good as what the operator can see is missing.
    """
    data = _load(path)
    resolved: list[dict[str, Any]] = []
    for entry in data["queries"]:
        query = str(entry.get("query", ""))
        urls = list(entry.get("relevant_urls", []))
        matched: list[dict[str, str]] = []
        unresolved: list[str] = []
        for url in urls:
            opportunity_id = session.scalar(
                select(OpportunityModel.id)
                .join(
                    SourceOccurrenceModel,
                    SourceOccurrenceModel.opportunity_id == OpportunityModel.id,
                )
                .where(
                    (SourceOccurrenceModel.normalized_source_url == url)
                    | (SourceOccurrenceModel.source_url == url)
                )
                .limit(1)
            )
            if opportunity_id is None:
                unresolved.append(url)
            else:
                matched.append({"url": url, "opportunity_id": str(opportunity_id)})
        resolved.append({"query": query, "relevant": matched, "unresolved": unresolved})
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init")
    add_parser = subparsers.add_parser("add")
    add_parser.add_argument("--query", required=True)
    add_parser.add_argument("--opportunity-id", required=True, type=UUID)
    resolve_parser = subparsers.add_parser("resolve")
    resolve_parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.command == "init":
        init_reference(args.path)
        print(f"Initialized {args.path} with {REFERENCE_QUERY_COUNT} query slots.")
        return 0

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required.")
    with Session(create_database_engine(database_url)) as session:
        if args.command == "add":
            add_relevant(
                session,
                query=args.query,
                opportunity_id=args.opportunity_id,
                path=args.path,
            )
            print(f"Recorded a relevant vaga for query '{args.query}'.")
            return 0
        if args.command == "resolve":
            result = resolve(session, args.path)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                for entry in result:
                    print(
                        f"{entry['query'] or '(sem texto)'}: "
                        f"{len(entry['relevant'])} resolvidas, "
                        f"{len(entry['unresolved'])} não encontradas"
                    )
            return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
