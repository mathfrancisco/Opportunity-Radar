"""Database-backed proof of the first MVP product slice."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from opportunity_radar.companies.models import Company, CompanyAlias, CompanyImportBatch
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.presentation.http.app import create_app
from scripts.import_notion_export import import_companies, input_hash

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


def test_profile_and_company_catalog_flow(tmp_path: Path) -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_database_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE profile.career_profile, "
                "company_radar.company_import_batch, "
                "company_radar.company CASCADE"
            )
        )

    client = TestClient(create_app(Settings(database_url=database_url)))
    created = client.post(
        "/profile/versions",
        json={
            "expected_profile_version": 0,
            "skills": [
                {
                    "canonical_name": "Python",
                    "level": "advanced",
                    "experience_months": 60,
                }
            ],
            "experiences": [
                {
                    "company_name": "Acme",
                    "title": "Backend Engineer",
                    "started_on": "2022-01-01",
                }
            ],
            "projects": [],
            "preferences": {
                "work_modes": ["remote"],
                "contracts": ["full-time"],
                "countries": ["BR"],
            },
        },
    )
    assert created.status_code == 201
    draft = created.json()
    assert draft["status"] == "DRAFT"
    assert draft["profile_lock_version"] == 1

    published = client.post(
        f"/profile/versions/{draft['id']}/publish",
        json={"expected_profile_version": 1},
    )
    assert published.status_code == 200
    assert published.json()["status"] == "PUBLISHED"
    assert published.json()["profile_lock_version"] == 2

    activated = client.post(
        f"/profile/versions/{draft['id']}/activate",
        json={"expected_profile_version": 2},
    )
    assert activated.status_code == 200
    assert activated.json()["status"] == "ACTIVE"
    assert activated.json()["profile_lock_version"] == 3
    assert client.get("/profile").json()["skills"][0]["canonical_name"] == "python"

    fixture = Path(__file__).parents[1] / "fixtures" / "notion_companies.csv"
    with Session(engine) as session:
        first_import = import_companies(session, fixture, dry_run=False, resume=False)
        repeated_import = import_companies(session, fixture, dry_run=False, resume=False)
    assert first_import["created"] == 2
    assert repeated_import["status"] == "already_completed"

    alias_file = tmp_path / "alias.csv"
    alias_file.write_text(
        "Company Name,Website,Aliases\nAcme Global,acme.test,Acme\n",
        encoding="utf-8",
    )
    with Session(engine) as session:
        alias_reconciliation = import_companies(
            session,
            alias_file,
            dry_run=False,
            resume=False,
        )
    assert alias_reconciliation["created"] == 0
    assert alias_reconciliation["reconciled"] == 1
    assert alias_reconciliation["aliases_added"] == 1

    with Session(engine) as session:
        imported_companies = list(session.scalars(select(Company)))
        for company in imported_companies:
            company.aliases.append(
                CompanyAlias(alias="Shared Alias", normalized_alias="shared alias")
            )
        session.commit()

    ambiguous_file = tmp_path / "ambiguous.csv"
    ambiguous_file.write_text(
        "Company Name,Website\nShared Alias,shared.test\n",
        encoding="utf-8",
    )
    with Session(engine) as session:
        ambiguity = import_companies(
            session,
            ambiguous_file,
            dry_run=False,
            resume=False,
        )
    assert ambiguity["created"] == 0
    assert ambiguity["issues"][0]["code"] == "manual_review_required"

    resume_file = tmp_path / "resume.csv"
    resume_file.write_text(
        "Company Name,Website\nResume Co,resume.test\n",
        encoding="utf-8",
    )
    with Session(engine) as session:
        session.add(
            CompanyImportBatch(
                file_hash=input_hash(resume_file),
                source_filename=resume_file.name,
                status="running",
            )
        )
        session.commit()
        with pytest.raises(ValueError, match="--resume"):
            import_companies(session, resume_file, dry_run=False, resume=False)
        resumed = import_companies(session, resume_file, dry_run=False, resume=True)
    assert resumed["status"] == "completed"
    assert resumed["created"] == 1

    dry_run_file = tmp_path / "dry-run.csv"
    dry_run_file.write_text("Company Name,Website\nPreview,preview.test\n", encoding="utf-8")
    with Session(engine) as session:
        preview = import_companies(session, dry_run_file, dry_run=True, resume=False)
        total = session.scalar(select(func.count(Company.id)))
    assert preview["status"] == "dry_run"
    assert preview["created"] == 1
    assert total == 3

    companies = client.get("/companies?q=acme")
    assert companies.status_code == 200
    assert companies.json()["total"] == 1
    assert companies.json()["items"][0]["name"] == "Acme"
    assert len(companies.json()["items"][0]["aliases"]) == 4
