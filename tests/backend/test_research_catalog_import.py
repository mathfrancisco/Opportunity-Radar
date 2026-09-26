import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from opportunity_radar.companies.models import Company, CompanySource
from opportunity_radar.platform.database import create_database_engine
from scripts.import_research_catalog import (
    DEFAULT_INPUTS,
    ResearchRow,
    _record_source_metadata,
    _resolve_source_key,
    extract_ats_key,
    import_research_file,
    read_research_rows,
)


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)
def test_import_research_file_is_idempotent_for_completed_file(tmp_path: Path) -> None:
    company_name = f"F20 Idempotence {uuid4().hex}"
    research = tmp_path / "research.md"
    research.write_text(
        "\n".join(
            (
                "| Empresa | Situação | ATS | Fonte consultada | Evidência / observação |",
                "| --- | --- | --- | --- | --- |",
                f"| {company_name} | ATS identificado | Ashby | "
                "[Carreiras](https://example.com/careers) | "
                "[Board](https://jobs.ashbyhq.com/idempotence-board) |",
            )
        ),
        encoding="utf-8",
    )
    engine = create_database_engine(os.environ["DATABASE_URL"])

    with Session(engine) as session:
        first = import_research_file(
            session, research, dry_run=False, resume=False
        )
        session.commit()
        second = import_research_file(
            session, research, dry_run=False, resume=False
        )

        company_count = session.scalar(
            select(func.count()).select_from(Company).where(
                Company.canonical_name == company_name
            )
        )
        source_count = session.scalar(
            select(func.count())
            .select_from(CompanySource)
            .join(CompanySource.company)
            .where(Company.canonical_name == company_name)
        )

    assert first["status"] == "completed"
    assert second["status"] == "already_completed"
    assert company_count == 1
    assert source_count == 2  # Ashby board plus the careers page.


def test_reads_only_company_rows_and_preserves_consulted_url(tmp_path: Path) -> None:
    research = tmp_path / "research.md"
    research.write_text(
        "\n".join(
            (
                "# Research",
                "| Empresa | Situação | ATS | Fonte consultada | "
                "Evidência / observação |",
                "| --- | --- | --- | --- | --- |",
                "| Example | API JSON confirmada | Ashby | "
                "[Carreiras](https://example.com/careers) | "
                "[JSON](https://api.example.com/jobs). Confirmed. |",
                "A paragraph with | pipes | is ignored.",
            )
        ),
        encoding="utf-8",
    )

    rows = list(read_research_rows(research))

    assert len(rows) == 1
    assert rows[0].name == "Example"
    assert rows[0].consulted_url == "https://example.com/careers"
    assert rows[0].links[-1] == ("JSON", "https://api.example.com/jobs")


def test_maps_confirmed_json_before_ats_and_careers() -> None:
    row = ResearchRow(
        name="Example",
        situation="API JSON confirmada",
        ats="Ashby",
        consulted_url="https://example.com/careers",
        evidence="[JSON](https://api.example.com/jobs). Confirmed.",
        links=(
            ("Carreiras", "https://example.com/careers"),
            ("JSON", "https://api.example.com/jobs"),
        ),
    )

    sources = row.source_candidates()

    assert [(source.source_type, source.endpoint) for source in sources] == [
        ("ashby", "https://api.example.com/jobs"),
        ("careers", "https://example.com/careers"),
    ]
    assert row.source_priority == "high"
    assert row.source_status == "api_json_confirmed"


def test_maps_dynamic_and_redirected_companies_to_backlog() -> None:
    row = ResearchRow(
        name="Example",
        situation="Redirecionamento; revisar",
        ats=None,
        consulted_url="https://example.com/careers",
        evidence="Redirected to a product page.",
        links=(("Carreiras", "https://example.com/careers"),),
    )

    assert row.is_backlog is True
    assert row.source_status == "backlog"
    assert row.source_priority == "low"
    identities = [
        (source.source_type, source.endpoint)
        for source in row.source_candidates()
    ]
    assert identities == [
        ("careers", "https://example.com/careers"),
    ]


def test_known_brand_transitions_are_reconciled_as_aliases() -> None:
    neon = ResearchRow(
        name="Neon",
        situation="Redirecionamento; revisar",
        ats=None,
        consulted_url="https://neon.com/careers",
        evidence="Redirected to Databricks.",
        links=(("Carreiras", "https://neon.com/careers"),),
    )

    assert neon.as_candidate().aliases == ("Databricks",)


def test_default_studies_contain_the_researched_catalog() -> None:
    counts = [len(list(read_research_rows(path))) for path in DEFAULT_INPUTS]

    assert counts == [186, 36]


def test_extract_ats_key_validates_each_ats_board_link_shape() -> None:
    assert extract_ats_key("ashby", "https://jobs.ashbyhq.com/cartesia").key == "cartesia"
    assert extract_ats_key(
        "ashby", "https://jobs.ashbyhq.com/cartesia/opening/123"
    ).key == "cartesia"
    assert extract_ats_key(
        "greenhouse", "https://job-boards.greenhouse.io/assemblyai"
    ).key == "assemblyai"
    assert extract_ats_key(
        "greenhouse", "https://boards.greenhouse.io/assemblyai"
    ).key == "assemblyai"
    global_lever = extract_ats_key("lever", "https://jobs.lever.co/ciandt")
    assert global_lever.key == "ciandt"
    assert global_lever.api_region == "global"
    eu_lever = extract_ats_key("lever", "https://jobs.eu.lever.co/ciandt")
    assert eu_lever.api_region == "eu"


def test_extract_ats_key_rejects_links_outside_the_ats_domain_or_pattern() -> None:
    assert extract_ats_key("ashby", "https://jobs.ashbyhq.com/") is None
    assert extract_ats_key("greenhouse", "https://boards.greenhouse.io/") is None
    assert extract_ats_key("ashby", "https://cartesia.ai/careers") is None
    assert extract_ats_key("lever", "https://example.com/jobs/ciandt") is None


def _company_source(*, source_type: str, endpoint: str) -> CompanySource:
    return CompanySource(source_type=source_type, endpoint=endpoint)


def test_resolve_source_key_extracts_and_validates_board_link() -> None:
    row = ResearchRow(
        name="Cartesia",
        situation="ATS identificado",
        ats="Ashby",
        consulted_url="https://cartesia.ai/careers",
        evidence="[Board](https://jobs.ashbyhq.com/cartesia). Evidence.",
        links=(
            ("Carreiras", "https://cartesia.ai/careers"),
            ("Board", "https://jobs.ashbyhq.com/cartesia"),
        ),
    )
    source = _company_source(
        source_type="ashby", endpoint="https://jobs.ashbyhq.com/cartesia"
    )

    resolution = _resolve_source_key(row, source)

    assert resolution.key == "cartesia"
    assert resolution.verification_method == "research_link"
    assert resolution.unresolved_reason is None


def test_resolve_source_key_reports_unresolved_when_no_link_matches() -> None:
    row = ResearchRow(
        name="Cognition",
        situation="ATS identificado",
        ats="Ashby",
        consulted_url="https://cognition.ai/careers",
        evidence="No board link available.",
        links=(("Carreiras", "https://cognition.ai/careers"),),
    )
    source = _company_source(
        source_type="ashby", endpoint="https://cognition.ai/careers"
    )

    resolution = _resolve_source_key(row, source)

    assert resolution.key is None
    assert resolution.unresolved_reason is not None


def test_record_source_metadata_surfaces_unresolved_ats_keys() -> None:
    row = ResearchRow(
        name="Cognition",
        situation="ATS identificado",
        ats="Ashby",
        consulted_url="https://cognition.ai/careers",
        evidence="No board link available.",
        links=(("Carreiras", "https://cognition.ai/careers"),),
    )
    source = _company_source(
        source_type="ashby", endpoint="https://cognition.ai/careers"
    )

    unresolved = _record_source_metadata([source], row)

    assert source.external_key is None
    assert source.verification_status == "ats_identified"
    assert unresolved == [
        (
            "ashby",
            "ashby identified with no board or JSON link to extract a key from.",
        )
    ]
