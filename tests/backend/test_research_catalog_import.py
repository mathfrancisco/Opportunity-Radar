from pathlib import Path

from scripts.import_research_catalog import (
    DEFAULT_INPUTS,
    ResearchRow,
    read_research_rows,
)


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
