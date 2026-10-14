"""Evaluating a match writes an owner-scoped assessment, so it refuses an ownerless caller."""

from __future__ import annotations

from uuid import uuid4

import pytest

from opportunity_radar.matching.service import MatchingService
from opportunity_radar.profile.domain import ProfileOwnerRequiredError


@pytest.mark.parametrize("owner_sub", [None, "", "   "])
def test_evaluate_without_an_owner_is_refused_before_any_read(owner_sub: str | None) -> None:
    service = MatchingService(object(), owner_sub)  # type: ignore[arg-type]

    with pytest.raises(ProfileOwnerRequiredError):
        service.evaluate(uuid4())
