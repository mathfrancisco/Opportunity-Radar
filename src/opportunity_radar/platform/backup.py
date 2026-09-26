"""Shared vocabulary for taking a backup and for checking that it restores.

Both scripts have to agree on what a good backup contains, so the manifest queries live
here rather than in either one of them.

Card F20-41 (old F18-08): the tables a future Groq call log, quota guard (`ai_quota_usage`,
F20-12/F20-19) and cache-identity change (F20-16) add are not in `MANIFEST_QUERIES` yet —
those cards have not landed, so the tables do not exist. Add them here once they do; this
module is the single place both scripts read the list from.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse

#: Bumped whenever the manifest's shape changes in a way `restore_check.py` must not read
#: as if it were the previous shape. A manifest with a different value is incompatible.
FORMAT_VERSION = 1

#: One count per table the vertical flow depends on. The restore check compares these, so
#: a dump that silently lost a context fails instead of passing quietly.
MANIFEST_QUERIES: dict[str, str] = {
    "companies": "SELECT count(*) FROM company_radar.company",
    "company_sources": "SELECT count(*) FROM company_radar.company_source",
    "profile_versions": "SELECT count(*) FROM profile.profile_version",
    "source_definitions": "SELECT count(*) FROM acquisition.source_definition",
    "source_runs": "SELECT count(*) FROM acquisition.source_run",
    "raw_items": "SELECT count(*) FROM acquisition.raw_item",
    "opportunities": "SELECT count(*) FROM opportunities.opportunity",
    "source_occurrences": "SELECT count(*) FROM opportunities.source_occurrence",
    "match_assessments": "SELECT count(*) FROM matching.match_assessment",
    "match_analyses": "SELECT count(*) FROM matching.match_analysis",
    "applications": "SELECT count(*) FROM crm.application_process",
    "stage_history": "SELECT count(*) FROM crm.stage_history",
}

#: Never allowed to appear in a manifest's serialized JSON. The Groq API key never enters
#: `pg_dump`'s output (it only ever dumps the Postgres database, never the filesystem or
#: environment), but the manifest is built from plain Python values this process also
#: has `GROQ_API_KEY` in its environment for, so this is defense in depth, not the only
#: guard: a future field (an AI call record's request/response body, once F20-19 lands)
#: must never carry the key by accident either.
FORBIDDEN_MANIFEST_STRINGS: tuple[str, ...] = ("GROQ_API_KEY",)

#: A count alone can agree by coincidence; these must always be zero, in the manifest and
#: after a restore, or a relationship a table count cannot see (a dangling foreign key
#: the schema itself no longer enforces, a row a migration was supposed to backfill) broke.
RELATIONSHIP_QUERIES: dict[str, str] = {
    "assessments_without_opportunity": (
        "SELECT count(*) FROM matching.match_assessment a "
        "LEFT JOIN opportunities.opportunity o ON o.id = a.opportunity_id "
        "WHERE o.id IS NULL"
    ),
    "occurrences_without_opportunity": (
        "SELECT count(*) FROM opportunities.source_occurrence oc "
        "LEFT JOIN opportunities.opportunity o ON o.id = oc.opportunity_id "
        "WHERE o.id IS NULL"
    ),
    "stage_history_without_application": (
        "SELECT count(*) FROM crm.stage_history h "
        "LEFT JOIN crm.application_process a ON a.id = h.application_id "
        "WHERE a.id IS NULL"
    ),
}

#: What a restore into a scratch database, or one built from a different image, must also
#: have: an extension present in the source and missing afterwards is a silent capability
#: loss (pgvector-backed similarity search returning empty instead of failing loudly).
EXTENSIONS_QUERY = "SELECT extname FROM pg_extension ORDER BY extname"

ALEMBIC_REVISION_QUERY = "SELECT version_num FROM alembic_version"


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set")
    return url


def postgres_dsn(url: str) -> str:
    """`pg_dump` speaks postgresql://, not SQLAlchemy's postgresql+psycopg://."""
    parsed = urlparse(url)
    return urlunparse(parsed._replace(scheme=parsed.scheme.split("+", 1)[0]))


def with_database(url: str, name: str) -> str:
    return urlunparse(urlparse(url)._replace(path=f"/{name}"))


def database_name(url: str) -> str:
    from urllib.parse import unquote

    return unquote(urlparse(url).path.lstrip("/"))


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """The dump's checksum, so a restore can refuse a file that changed after backup wrote it."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "ALEMBIC_REVISION_QUERY",
    "EXTENSIONS_QUERY",
    "FORBIDDEN_MANIFEST_STRINGS",
    "FORMAT_VERSION",
    "MANIFEST_QUERIES",
    "RELATIONSHIP_QUERIES",
    "database_name",
    "database_url",
    "postgres_dsn",
    "sha256_file",
    "with_database",
]
