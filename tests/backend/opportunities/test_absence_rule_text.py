"""R55-D5: the job screen reads the window from the API; the API reads the setting."""

from __future__ import annotations

from pathlib import Path

import pytest

from opportunity_radar.platform.config import Settings

_DETAIL_PAGE = (
    Path(__file__).resolve().parents[3]
    / "apps/web/src/routes/OpportunityDetailPage.tsx"
)


@pytest.mark.skipif(not _DETAIL_PAGE.exists(), reason="the web app is not part of this checkout")
def test_the_documented_absence_window_is_the_settings_default() -> None:
    assert Settings.model_fields["absence_after_hours"].default == 24
    page = _DETAIL_PAGE.read_text(encoding="utf-8")
    assert "mais de 24 h" not in page  # no hard-coded window
    assert "absence_after_hours" in page
