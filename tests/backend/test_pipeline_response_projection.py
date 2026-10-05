"""The applications endpoint projects card labels in one bounded lookup."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from opportunity_radar.presentation.http.pipeline import _application_responses


def test_application_responses_project_title_and_company_in_one_query() -> None:
    opportunity_id = uuid4()
    application = SimpleNamespace(
        id=uuid4(),
        opportunity_id=opportunity_id,
        profile_version_id=uuid4(),
        current_stage="INTERESTED",
        status="ACTIVE",
        outcome=None,
        next_action=None,
        next_action_at=None,
        notes=None,
        applied_at=None,
        started_at=datetime.now(UTC),
        closed_at=None,
        version=1,
        history=[],
    )
    session = Mock()
    session.execute.return_value = [(opportunity_id, "Senior Engineer", "Example Ltd")]

    responses = _application_responses([application], session)

    assert len(responses) == 1
    assert responses[0].opportunity_title == "Senior Engineer"
    assert responses[0].company_name == "Example Ltd"
    session.execute.assert_called_once()
