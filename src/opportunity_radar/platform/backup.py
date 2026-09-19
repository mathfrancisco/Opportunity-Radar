"""Shared vocabulary for taking a backup and for checking that it restores.

Both scripts have to agree on what a good backup contains, so the manifest queries live
here rather than in either one of them.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse, urlunparse

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


__all__ = [
    "MANIFEST_QUERIES",
    "database_name",
    "database_url",
    "postgres_dsn",
    "with_database",
]
