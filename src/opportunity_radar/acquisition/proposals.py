"""How a source proposed from a researched ATS record follows corrections to that record.

A proposal is a `SourceDefinition` born from a `CompanySource`. While it is inert — never
homologated, never tested, never enabled — it asserts nothing about the board, and a
correction to the record can simply reach it. Once anyone has reviewed, tested or enabled
it, those facts were about the old board: the proposal is left alone and reported as
outdated, and bringing it up to date is an explicit reopening of its homologation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import SourceDefinitionModel
from opportunity_radar.companies.models import CompanySource

# Where each ATS keeps the board key in a source's configuration.
IDENTIFIER_KEYS = {
    "ashby": "board_identifier",
    "lever": "site_identifier",
    "greenhouse": "board_token",
}

ProposalOutcome = Literal["none", "updated", "outdated"]


@dataclass(frozen=True, slots=True)
class ProposalFollowUp:
    outcome: ProposalOutcome
    proposal: SourceDefinitionModel | None = None


class ProposalChangedError(Exception):
    """The proposal changed while a correction was trying to reach it."""


def proposal_for(session: Session, company_source_id: object) -> SourceDefinitionModel | None:
    return session.scalar(
        select(SourceDefinitionModel)
        .where(SourceDefinitionModel.company_source_id == company_source_id)
        .order_by(SourceDefinitionModel.created_at)
    )


def proposal_key(proposal: SourceDefinitionModel) -> str | None:
    key = IDENTIFIER_KEYS.get(proposal.source_type)
    value = (proposal.configuration or {}).get(key) if key else None
    return value if isinstance(value, str) else None


def is_inert(proposal: SourceDefinitionModel) -> bool:
    """Nothing about the board has been asserted yet: no test, no terms, no run allowed."""
    return (
        not proposal.enabled
        and not proposal.terms_reviewed
        and not proposal.collector_local_tested
        and proposal.evidence_status in {"ats_identified", "unverified"}
    )


def is_outdated(proposal: SourceDefinitionModel, record: CompanySource) -> bool:
    return (
        proposal.source_type != record.source_type
        or proposal_key(proposal) != record.external_key
    )


def follow_correction(session: Session, record: CompanySource) -> ProposalFollowUp:
    """Bring an inert proposal in line with a corrected record, in the caller's transaction.

    The caller commits; if the proposal moved under this write, `ProposalChangedError` asks
    it to roll back the correction too, so the record and the proposal never disagree
    because half of a correction landed.
    """
    proposal = proposal_for(session, record.id)
    if proposal is None:
        return ProposalFollowUp("none")
    return follow_inert_correction(
        session,
        proposal,
        source_type=record.source_type,
        board_key=record.external_key,
        discovery_evidence=record.evidence_note or record.endpoint,
    )


def follow_inert_correction(
    session: Session,
    proposal: SourceDefinitionModel,
    *,
    source_type: str,
    board_key: str | None,
    discovery_evidence: str,
    configuration_updates: dict[str, Any] | None = None,
) -> ProposalFollowUp:
    """Apply a corrected board to an inert proposal in the caller's transaction.

    Both researched CompanySource records and Tavily evidence use this guarded path.  A
    proposal that has crossed the review/test gate remains untouched because those facts
    describe its previous board.
    """
    identifier_key = IDENTIFIER_KEYS.get(source_type)
    if identifier_key is None:
        return ProposalFollowUp("outdated", proposal)
    if (
        proposal.source_type == source_type
        and proposal_key(proposal) == board_key
        and not configuration_updates
    ):
        return ProposalFollowUp("none", proposal)
    if not is_inert(proposal) or proposal.source_type != source_type:
        # A different ATS is a different collector: a source never changes type, so the
        # proposal stays as it is and the screen says why.
        return ProposalFollowUp("outdated", proposal)
    configuration = dict(proposal.configuration or {})
    configuration[identifier_key] = board_key
    configuration["discovery_evidence"] = discovery_evidence
    configuration.update(configuration_updates or {})
    updated = session.scalar(
        update(SourceDefinitionModel)
        .where(
            SourceDefinitionModel.id == proposal.id,
            SourceDefinitionModel.version == proposal.version,
        )
        .values(configuration=configuration, version=SourceDefinitionModel.version + 1)
        .returning(SourceDefinitionModel.id)
    )
    if updated is None:
        raise ProposalChangedError(proposal.id)
    session.refresh(proposal)
    return ProposalFollowUp("updated", proposal)
