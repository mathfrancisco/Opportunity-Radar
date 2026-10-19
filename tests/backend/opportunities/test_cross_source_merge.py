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
        external_id: str | None = None,
        company_text: str | None = None,
        description: str | None = None,
        updated: datetime | None = None,
        fetched_at: datetime | None = None,
    ):
        definition = self.sources[key]
        external_id = external_id or f"job-{uuid4().hex[:10]}"
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
            fetched_at=fetched_at or NOW,
            item_metadata={
                COLLECTED_ITEM_V1_KEY: {
                    "version": 1,
                    "source_type": definition.source_type,
                    "external_id": external_id,
                    "url": url,
                    "title": title,
                    "company_name": company_text or self.company_name(company),
                    "location_text": location,
                    "published_at": published.isoformat(),
                    "updated_at": updated.isoformat() if updated else None,
                    "description": description,
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


def test_two_different_non_ascii_company_names_never_match(world: _World) -> None:
    """Every non-ASCII name folds to an empty key; an empty key is a missing name."""
    greenhouse, remotive = _greenhouse_and_remotive(world)
    first = world.post(greenhouse, company="a", company_text="株式会社甲")
    second = world.post(remotive, company="a", company_text="株式会社乙")

    assert first.opportunity is not None and first.opportunity.normalized_company_name == ""
    assert second.identity_decision != "MERGED"
    assert len(world.opportunities()) == 2


def test_conflicting_known_seniority_is_not_a_strong_match(world: _World) -> None:
    from dataclasses import replace

    from opportunity_radar.opportunities.domain import (
        NormalizationInput,
        Seniority,
        build_candidate,
    )
    from opportunity_radar.opportunities.duplicates import find_cross_source_strong_match

    greenhouse, remotive = _greenhouse_and_remotive(world)
    first = world.post(greenhouse, company="a")
    opportunity = world.session.get(OpportunityModel, first.opportunity_id)
    assert opportunity is not None
    candidate = build_candidate(
        NormalizationInput(
            raw_item_id=uuid4(),
            source_definition_id=world.sources[remotive].id,
            source_type="remotive",
            external_id="seniority-probe",
            title=opportunity.canonical_title,
            company_name=opportunity.company_name,
            location_text=opportunity.location_text,
            published_at=opportunity.published_at,
        )
    )
    source_id = world.sources[remotive].id

    opportunity.seniority = "SENIOR"
    world.session.commit()
    conflicting = replace(candidate, seniority=Seniority.JUNIOR)
    assert (
        find_cross_source_strong_match(world.session, conflicting, source_definition_id=source_id)
        is None
    )
    same = replace(candidate, seniority=Seniority.SENIOR)
    assert (
        find_cross_source_strong_match(world.session, same, source_definition_id=source_id)
        is not None
    )
    unknown = replace(candidate, seniority=Seniority.UNKNOWN)
    assert (
        find_cross_source_strong_match(world.session, unknown, source_definition_id=source_id)
        is not None
    )


def test_secondary_source_never_rewrites_the_opportunity(world: _World) -> None:
    greenhouse, remotive = _greenhouse_and_remotive(world)
    first = world.post(
        greenhouse, company="a", description="Greenhouse text", updated=NOW - timedelta(days=2),
        external_id="gh-1",
    )
    assert first.opportunity_id is not None
    world.post(
        remotive, company="a", description="Remotive text", updated=NOW - timedelta(hours=1),
        external_id="rem-1", location="SAO PAULO",
        fetched_at=NOW + timedelta(seconds=1),
    )

    def snapshot() -> tuple:
        world.session.expire_all()
        o = world.session.get(OpportunityModel, first.opportunity_id)
        assert o is not None
        return (o.version, o.description, o.location_text, o.source_updated_at, o.canonical_title)

    baseline = snapshot()
    assert baseline[1] == "Greenhouse text"
    for step in range(1, 4):
        later = NOW + timedelta(minutes=step)
        second = world.post(
            remotive, company="a", description=f"Remotive text v{step}", location="SAO PAULO",
            updated=NOW + timedelta(hours=step), external_id="rem-1", fetched_at=later,
        )
        assert second.reasons[0]["code"] == "SECONDARY_SOURCE_OCCURRENCE"
        assert snapshot() == baseline
        primary = world.post(
            greenhouse, company="a", description="Greenhouse text",
            updated=NOW - timedelta(days=2), external_id="gh-1", fetched_at=later,
        )
        assert primary.reasons[0]["code"] == "SAME_SOURCE_EXTERNAL_IDENTITY"
        assert snapshot() == baseline
    occurrences = world.session.scalars(
        select(SourceOccurrenceModel).where(
            SourceOccurrenceModel.opportunity_id == first.opportunity_id
        )
    ).all()
    assert len(occurrences) == 2


def test_measurement_ignores_closed_and_same_source_pairs(world: _World) -> None:
    greenhouse, _ = _greenhouse_and_remotive(world)
    before = measure_cross_source_duplicates(world.session)
    world.post(greenhouse, company="a", published=NOW - timedelta(days=1))
    # Same source, another publication day: two real requisitions, not a missed merge.
    world.post(greenhouse, company="a", published=NOW - timedelta(days=3))
    same_source = measure_cross_source_duplicates(world.session)
    assert same_source.residual_duplicate_rows == before.residual_duplicate_rows

    twin = world.opportunities()[0]
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
            lifecycle_status="CLOSED",
        )
    )
    world.session.commit()
    closed = measure_cross_source_duplicates(world.session)
    assert closed.residual_duplicate_rows == before.residual_duplicate_rows
    world.session.execute(
        text(
            "DELETE FROM opportunities.opportunity WHERE canonical_company_id = :c "
            "AND lifecycle_status = 'CLOSED' "
            "AND id NOT IN (SELECT opportunity_id FROM opportunities.source_occurrence)"
        ),
        {"c": twin.canonical_company_id},
    )
    world.session.commit()


def _merged_pair(world: _World) -> tuple[str, str, UUID]:
    greenhouse, remotive = _greenhouse_and_remotive(world)
    first = world.post(
        greenhouse, company="a", description="Greenhouse text", updated=NOW - timedelta(days=2),
        external_id="gh-1",
    )
    assert first.opportunity_id is not None
    world.post(
        remotive, company="a", description="Remotive text", updated=NOW - timedelta(hours=1),
        external_id="rem-1", fetched_at=NOW + timedelta(seconds=1),
    )
    return greenhouse, remotive, first.opportunity_id


def _description(world: _World, opportunity_id: UUID) -> str | None:
    world.session.expire_all()
    opportunity = world.session.get(OpportunityModel, opportunity_id)
    assert opportunity is not None
    return opportunity.description


def test_primary_is_re_elected_when_the_first_source_stops_listing_the_job(
    world: _World,
) -> None:
    """R55-E4 follow-up: content must not stay frozen on a vanished primary occurrence."""
    greenhouse, remotive, opportunity_id = _merged_pair(world)
    assert _description(world, opportunity_id) == "Greenhouse text"
    # The greenhouse board was re-read in a complete run that no longer lists the job; the
    # remotive board still does (its occurrence belongs to its latest complete run).
    world.new_run(greenhouse)
    world.session.commit()

    result = world.post(
        remotive, company="a", description="Remotive text v2", updated=NOW + timedelta(hours=1),
        external_id="rem-1", fetched_at=NOW + timedelta(minutes=1),
    )

    assert result.reasons[0]["code"] != "SECONDARY_SOURCE_OCCURRENCE"
    assert _description(world, opportunity_id) == "Remotive text v2"


def test_primary_is_kept_while_it_is_open_or_when_every_occurrence_closed(
    world: _World,
) -> None:
    greenhouse, remotive, opportunity_id = _merged_pair(world)

    # Negative 1: the first source still lists it, so the later source stays secondary.
    still_open = world.post(
        remotive, company="a", description="Remotive text v2", updated=NOW + timedelta(hours=1),
        external_id="rem-1", fetched_at=NOW + timedelta(minutes=1),
    )
    assert still_open.reasons[0]["code"] == "SECONDARY_SOURCE_OCCURRENCE"
    assert _description(world, opportunity_id) == "Greenhouse text"

    # Negative 2: both boards were re-read without the job; nothing is open, so the oldest
    # occurrence keeps the role instead of the role flipping to whichever reports first.
    world.new_run(greenhouse)
    world.new_run(remotive)
    world.session.commit()
    none_open = world.post(
        remotive, company="a", description="Remotive text v3", updated=NOW + timedelta(hours=2),
        external_id="rem-1", fetched_at=NOW + timedelta(minutes=2),
    )
    assert none_open.reasons[0]["code"] == "SECONDARY_SOURCE_OCCURRENCE"
    assert _description(world, opportunity_id) == "Greenhouse text"
