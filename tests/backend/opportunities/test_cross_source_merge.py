"""R55-E4: the same job posted in two sources becomes one opportunity with two occurrences.

Drives `OpportunityService.normalize` end to end on real raw items (a company-linked ATS
board and a broad aggregator without a company id), because the acceptance is about the
rows the normalizer leaves behind, not about one query in isolation.
"""

from __future__ import annotations

import os
import string
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.acquisition.service import COLLECTED_ITEM_V1_KEY
from opportunity_radar.companies.models import Company, CompanySource
from opportunity_radar.operations.cross_source_duplicates import (
    measure_cross_source_duplicates,
)
from opportunity_radar.opportunities.models import (
    DuplicateCandidateModel,
    OpportunityModel,
    RelevanceMarkModel,
    SourceOccurrenceModel,
)
from opportunity_radar.opportunities.service import OpportunityService
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

NOW = datetime.now(UTC)


def _letters() -> str:
    """A name fragment with no digits, unique per call, safe as a company name."""
    return "".join(string.ascii_lowercase[int(c, 16) % 26] for c in uuid4().hex[:10])


class _World:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.suffix = _letters()
        self.sources: dict[str, SourceDefinitionModel] = {}
        self.runs: dict[str, SourceRunModel] = {}
        self.companies: dict[str, Company] = {}
        self.raw_ids: list[UUID] = []
        self.service = OpportunityService(session)

    def company(self, label: str) -> str:
        name = f"Acme {label} {self.suffix}"
        if label not in self.companies:
            company = Company(canonical_name=name, normalized_name=name.casefold())
            self.session.add(company)
            self.session.flush()
            self.companies[label] = company
        return name

    def source(self, source_type: str, *, company_label: str | None = None) -> str:
        key = f"{source_type}:{company_label}"
        if key in self.sources:
            return key
        company_source_id = None
        if company_label is not None:
            self.company(company_label)
            company_source = CompanySource(
                company_id=self.companies[company_label].id,
                source_type=source_type,
                endpoint=f"https://example.invalid/{self.suffix}/{company_label}",
            )
            self.session.add(company_source)
            self.session.flush()
            company_source_id = company_source.id
        definition = SourceDefinitionModel(
            id=uuid4(),
            source_type=source_type,
            name=f"cross source probe {self.suffix} {len(self.sources)}",
            enabled=True,
            configuration={},
            rate_limit_policy={},
            company_source_id=company_source_id,
        )
        self.session.add(definition)
        self.session.flush()
        self.sources[key] = definition
        self.new_run(key)
        return key

    def new_run(self, key: str, *, complete: bool = True) -> SourceRunModel:
        started = NOW + timedelta(seconds=len(self.runs))
        run = SourceRunModel(
            id=uuid4(),
            source_definition_id=self.sources[key].id,
            execution_trigger="SCHEDULED",
            status="SUCCEEDED",
            started_at=started,
            finished_at=started + timedelta(seconds=1),
            complete=complete,
        )
        self.session.add(run)
        self.session.flush()
        self.runs[f"{key}:{len([k for k in self.runs if k.startswith(key)])}"] = run
        return run

    def latest_run(self, key: str) -> SourceRunModel:
        matching = [r for k, r in self.runs.items() if k.startswith(f"{key}:")]
        return matching[-1]

    def post(
        self,
        key: str,
        *,
        title: str = "Senior Backend Engineer",
        company: str,
        location: str | None = "Sao Paulo",
        published: datetime | None = None,
        url: str | None = None,
    ):
        definition = self.sources[key]
        external_id = f"job-{uuid4().hex[:10]}"
        url = url or f"https://example.invalid/{definition.source_type}/{external_id}"
        published = published or NOW - timedelta(days=1)
        run = self.latest_run(key)
        raw = RawItemModel(
            id=uuid4(),
            source_run_id=run.id,
            source_definition_id=definition.id,
            external_id=external_id,
            canonical_url=url,
            identity_key=f"external:{external_id}",
            payload_hash=uuid4().hex + uuid4().hex,
            fetched_at=NOW,
            item_metadata={
                COLLECTED_ITEM_V1_KEY: {
                    "version": 1,
                    "source_type": definition.source_type,
                    "external_id": external_id,
                    "url": url,
                    "title": title,
                    "company_name": self.company_name(company),
                    "location_text": location,
                    "published_at": published.isoformat(),
                    "metadata": {},
                }
            },
        )
        self.session.add(raw)
        self.session.commit()
        self.raw_ids.append(raw.id)
        return self.service.normalize(raw.id)

    def company_name(self, label: str) -> str:
        return f"Acme {label} {self.suffix}"

    def opportunities(self) -> list[OpportunityModel]:
        self.session.expire_all()
        ids = self.session.scalars(
            select(SourceOccurrenceModel.opportunity_id).where(
                SourceOccurrenceModel.raw_item_id.in_(self.raw_ids)
            )
        ).all()
        return list(
            self.session.scalars(select(OpportunityModel).where(OpportunityModel.id.in_(ids)))
        )

    def occurrence_count(self, opportunity: OpportunityModel) -> int:
        return (
            self.session.scalar(
                select(func.count())
                .select_from(SourceOccurrenceModel)
                .where(SourceOccurrenceModel.opportunity_id == opportunity.id)
            )
            or 0
        )

    def cleanup(self) -> None:
        s = self.session
        s.rollback()
        source_ids = [d.id for d in self.sources.values()]
        opportunity_ids = list(
            s.scalars(
                select(SourceOccurrenceModel.opportunity_id).where(
                    SourceOccurrenceModel.source_definition_id.in_(source_ids)
                )
            )
        )
        s.execute(
            text("DELETE FROM opportunities.normalization_result WHERE raw_item_id = ANY(:r)"),
            {"r": self.raw_ids},
        )
        s.execute(
            text("DELETE FROM opportunities.opportunity WHERE id = ANY(:o)"),
            {"o": opportunity_ids},
        )
        s.execute(
            text("DELETE FROM acquisition.raw_item WHERE source_definition_id = ANY(:s)"),
            {"s": source_ids},
        )
        s.execute(
            text("DELETE FROM acquisition.source_run WHERE source_definition_id = ANY(:s)"),
            {"s": source_ids},
        )
        s.execute(
            text("DELETE FROM acquisition.source_definition WHERE id = ANY(:s)"),
            {"s": source_ids},
        )
        s.execute(
            text("DELETE FROM company_radar.company WHERE id = ANY(:c)"),
            {"c": [c.id for c in self.companies.values()]},
        )
        s.commit()


@pytest.fixture()
def world() -> Iterator[_World]:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        fixture = _World(session)
        try:
            yield fixture
        finally:
            fixture.cleanup()
    engine.dispose()


def _greenhouse_and_remotive(w: _World) -> tuple[str, str]:
    return w.source("greenhouse", company_label="a"), w.source("remotive")


def test_same_job_in_greenhouse_and_remotive_is_one_opportunity_with_two_occurrences(
    world: _World,
) -> None:
    greenhouse, remotive = _greenhouse_and_remotive(world)
    first = world.post(greenhouse, company="a")
    second = world.post(remotive, company="a")

    assert first.identity_decision == "NEW"
    assert second.identity_decision == "MERGED"
    assert second.reasons[0]["code"] == "CROSS_SOURCE_STRONG_MATCH"
    assert second.opportunity_id == first.opportunity_id
    [opportunity] = world.opportunities()
    assert world.occurrence_count(opportunity) == 2
    sources = set(
        world.session.scalars(
            select(SourceOccurrenceModel.source_definition_id).where(
                SourceOccurrenceModel.opportunity_id == opportunity.id
            )
        )
    )
    assert sources == {world.sources[greenhouse].id, world.sources[remotive].id}
    assert world.session.scalar(
        select(func.count()).select_from(DuplicateCandidateModel).where(
            DuplicateCandidateModel.opportunity_id == opportunity.id
        )
    ) == 0


def test_same_job_on_two_ats_boards_of_one_company_merges(world: _World) -> None:
    greenhouse = world.source("greenhouse", company_label="a")
    lever = world.source("lever", company_label="a")
    world.post(greenhouse, company="a")
    second = world.post(lever, company="a")

    assert second.identity_decision == "MERGED"
    assert len(world.opportunities()) == 1


def test_same_canonical_apply_url_merges_across_sources(world: _World) -> None:
    greenhouse, remotive = _greenhouse_and_remotive(world)
    shared = f"https://example.invalid/apply/{world.suffix}?utm_source=feed"
    world.post(greenhouse, company="a", url=shared)
    # Different location: only the URL ties them together.
    second = world.post(
        remotive, company="a", location="Lisbon", url=shared.replace("?utm_source=feed", "/")
    )

    assert second.identity_decision == "MERGED"
    assert second.reasons[0]["code"] == "SAME_NORMALIZED_URL"
    assert len(world.opportunities()) == 1


def test_different_location_stays_two_opportunities(world: _World) -> None:
    greenhouse, remotive = _greenhouse_and_remotive(world)
    world.post(greenhouse, company="a", location="Sao Paulo")
    second = world.post(remotive, company="a", location="Lisbon")

    assert second.identity_decision != "MERGED"
    assert len(world.opportunities()) == 2


def test_different_company_same_title_stays_two_opportunities(world: _World) -> None:
    greenhouse, remotive = _greenhouse_and_remotive(world)
    world.company("b")
    world.post(greenhouse, company="a")
    second = world.post(remotive, company="b")

    assert second.identity_decision == "NEW"
    assert len(world.opportunities()) == 2


def test_title_listed_twice_by_one_source_is_two_jobs(world: _World) -> None:
    greenhouse = world.source("greenhouse", company_label="a")
    world.post(greenhouse, company="a", published=NOW - timedelta(days=1))
    # Another publication day, so the pre-existing exact fingerprint does not apply.
    second = world.post(greenhouse, company="a", published=NOW - timedelta(days=3))

    assert second.identity_decision != "MERGED"
    assert len(world.opportunities()) == 2


def test_weak_match_outside_the_window_becomes_a_duplicate_candidate(world: _World) -> None:
    greenhouse, remotive = _greenhouse_and_remotive(world)
    world.post(greenhouse, company="a", published=NOW - timedelta(days=12))
    second = world.post(remotive, company="a", published=NOW - timedelta(days=2))

    assert second.identity_decision != "MERGED"
    first_opportunity, second_opportunity = world.opportunities()
    candidates = world.session.scalars(
        select(DuplicateCandidateModel).where(
            DuplicateCandidateModel.opportunity_id.in_(
                [first_opportunity.id, second_opportunity.id]
            )
        )
    ).all()
    assert [(c.status, c.rule) for c in candidates] == [("PENDING", "title_location_window")]


def test_window_boundary_is_seven_days(world: _World) -> None:
    greenhouse, remotive = _greenhouse_and_remotive(world)
    anchor = NOW - timedelta(days=9)
    world.post(greenhouse, company="a", published=anchor)
    inside = world.post(remotive, company="a", published=anchor + timedelta(days=6, hours=23))
    assert inside.identity_decision == "MERGED"

    other = world.source("ashby", company_label="a")
    outside = world.post(other, company="a", published=anchor + timedelta(days=7, hours=2))
    assert outside.identity_decision != "MERGED"


def test_missing_location_or_date_is_never_a_strong_match(world: _World) -> None:
    greenhouse, remotive = _greenhouse_and_remotive(world)
    world.post(greenhouse, company="a", location=None)
    second = world.post(remotive, company="a", location=None)
    assert second.identity_decision != "MERGED"
    assert len(world.opportunities()) == 2


def test_closed_opportunity_is_not_a_merge_target(world: _World) -> None:
    greenhouse, remotive = _greenhouse_and_remotive(world)
    first = world.post(greenhouse, company="a")
    opportunity = world.session.get(OpportunityModel, first.opportunity_id)
    assert opportunity is not None
    opportunity.lifecycle_status = "CLOSED"
    world.session.commit()

    second = world.post(remotive, company="a")
    assert second.identity_decision != "MERGED"
    assert len(world.opportunities()) == 2


def test_owner_scoped_rows_are_left_alone_by_the_merge(world: _World) -> None:
    """The catalogue is shared; marks (per owner) must survive an attach untouched."""
    greenhouse, remotive = _greenhouse_and_remotive(world)
    first = world.post(greenhouse, company="a")
    assert first.opportunity_id is not None
    for owner, relevant in (("owner-one-xsource", True), ("owner-two-xsource", False)):
        world.session.add(
            RelevanceMarkModel(
                owner_sub=owner, opportunity_id=first.opportunity_id, relevant=relevant
            )
        )
    world.session.commit()
    version_before = world.session.get(OpportunityModel, first.opportunity_id).version  # type: ignore[union-attr]

    second = world.post(remotive, company="a")

    assert second.identity_decision == "MERGED"
    marks = {
        (m.owner_sub, m.relevant)
        for m in world.session.scalars(
            select(RelevanceMarkModel).where(
                RelevanceMarkModel.opportunity_id == first.opportunity_id
            )
        )
    }
    assert marks == {("owner-one-xsource", True), ("owner-two-xsource", False)}
    world.session.expire_all()
    assert world.session.get(OpportunityModel, first.opportunity_id).version >= version_before  # type: ignore[union-attr]
    world.session.execute(
        text("DELETE FROM opportunities.relevance_mark WHERE owner_sub LIKE '%-xsource'")
    )
    world.session.commit()


def test_closing_one_source_keeps_the_opportunity_open(world: _World) -> None:
    greenhouse, remotive = _greenhouse_and_remotive(world)
    first = world.post(greenhouse, company="a")
    world.post(remotive, company="a")
    opportunity = world.session.get(OpportunityModel, first.opportunity_id)
    assert opportunity is not None
    opportunity.lifecycle_status = "ACTIVE"
    greenhouse_occurrence = world.session.scalar(
        select(SourceOccurrenceModel).where(
            SourceOccurrenceModel.opportunity_id == opportunity.id,
            SourceOccurrenceModel.source_definition_id == world.sources[greenhouse].id,
        )
    )
    assert greenhouse_occurrence is not None
    # The greenhouse board stopped listing it 30 h ago and was re-read since.
    greenhouse_occurrence.last_seen_at = datetime.now(UTC) - timedelta(hours=30)
    world.session.commit()
    greenhouse_run = world.new_run(greenhouse)
    world.session.commit()

    world.service.reconcile_run_closures(greenhouse_run.id)
    world.session.expire_all()
    assert world.session.get(OpportunityModel, opportunity.id).lifecycle_status == "ACTIVE"  # type: ignore[union-attr]

    # Control: once the other source stops listing it too, the same pass closes it.
    world.new_run(remotive)
    world.session.commit()
    world.service.reconcile_run_closures(greenhouse_run.id)
    world.session.expire_all()
    assert world.session.get(OpportunityModel, opportunity.id).lifecycle_status == "CLOSED"  # type: ignore[union-attr]


def test_measurement_counts_merged_and_residual_duplicates(world: _World) -> None:
    greenhouse, remotive = _greenhouse_and_remotive(world)
    before = measure_cross_source_duplicates(world.session)
    world.post(greenhouse, company="a")
    world.post(remotive, company="a")
    after_merge = measure_cross_source_duplicates(world.session)
    assert after_merge.root_opportunities == before.root_opportunities + 1
    assert after_merge.multi_source_opportunities == before.multi_source_opportunities + 1
    assert after_merge.residual_duplicate_rows == before.residual_duplicate_rows

    # A legacy pair the rule never merged (inserted without going through normalization).
    twin = world.session.scalars(select(OpportunityModel).where(
        OpportunityModel.id.in_([o.id for o in world.opportunities()])
    )).one()
    world.session.add(
        OpportunityModel(
            fingerprint=uuid4().hex + uuid4().hex,
            fingerprint_version="v1",
            canonical_title=twin.canonical_title,
            normalized_title=twin.normalized_title,
            canonical_company_id=twin.canonical_company_id,
            normalized_company_name=twin.normalized_company_name,
            normalized_location=twin.normalized_location,
            published_at=twin.published_at,
            lifecycle_status="ACTIVE",
        )
    )
    world.session.commit()
    residual = measure_cross_source_duplicates(world.session)
    assert residual.residual_duplicate_rows == before.residual_duplicate_rows + 1
    assert residual.residual_rate > 0
    world.session.execute(
        text(
            "DELETE FROM opportunities.opportunity WHERE canonical_company_id = :c "
            "AND id NOT IN (SELECT opportunity_id FROM opportunities.source_occurrence)"
        ),
        {"c": twin.canonical_company_id},
    )
    world.session.commit()
