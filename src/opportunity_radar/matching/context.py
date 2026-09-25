"""Retrieval of similar past decisions for the semantic analysis prompt.

The pgvector-backed opportunity embedding (card F16-09) has no retrieval
wiring yet, so this returns no similar decisions until that work lands.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.orm import Session

from opportunity_radar.matching.models import MatchAssessmentModel


def retrieve_similar_decisions(
    session: Session, assessment: MatchAssessmentModel
) -> Sequence[Mapping[str, Any]]:
    """Return past decisions similar to `assessment`, if any are known."""
    return ()
