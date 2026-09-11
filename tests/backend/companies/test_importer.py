from pathlib import Path

from scripts.import_notion_export import candidate_from_row, read_rows


def test_accepts_common_notion_csv_columns(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    source.write_text(
        "Company Name,Website,Aliases\n"
        "Ácme,https://www.acme.test,Acme Inc; ACME\n",
        encoding="utf-8",
    )

    candidate = candidate_from_row(next(read_rows(source)))

    assert candidate is not None
    assert candidate.name == "Ácme"
    assert candidate.normalized_domain == "acme.test"
    assert candidate.normalized_aliases == ("acme inc",)
