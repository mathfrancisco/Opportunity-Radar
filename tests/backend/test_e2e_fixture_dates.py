"""The e2e fixtures stay inside the 7-day ingestion window whenever the suite runs (R55-E1)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.e2e import fake_job_board, fake_jobposting_site

WINDOW = timedelta(days=7)


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _postings(html: str) -> list[dict]:
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert match is not None
    payload = json.loads(match.group(1))
    return payload if isinstance(payload, list) else [payload]


@pytest.mark.parametrize("board", [fake_job_board.HEALTHY_BOARD, "e2e-abc123"])
def test_the_fake_greenhouse_board_sends_recent_dates_and_first_published(board: str) -> None:
    now = datetime.now(UTC)
    [job] = fake_job_board._jobs_for(board) or []

    assert "first_published" in job
    first_published, updated_at = _parse(job["first_published"]), _parse(job["updated_at"])
    assert now - WINDOW < first_published <= updated_at <= now


def test_the_fake_greenhouse_board_still_answers_404_for_an_unknown_board() -> None:
    assert fake_job_board._jobs_for("someone-else") is None


@pytest.mark.parametrize(
    ("builder", "expect_valid_through"),
    [(fake_jobposting_site.single_object_en, True), (fake_jobposting_site.single_object_pt, False)],
)
def test_the_fake_jobposting_pages_are_dated_relative_to_now(
    builder, expect_valid_through: bool
) -> None:
    now = datetime.now(UTC)
    [posting] = _postings(builder())

    assert now - WINDOW < _parse(posting["datePosted"]) <= now
    assert ("validThrough" in posting) is expect_valid_through
    if expect_valid_through:
        assert _parse(posting["validThrough"]) > now
    assert "@" not in builder().replace("@context", "").replace("@type", "").replace(
        "@graph", ""
    ), "a date placeholder was left unreplaced"


def test_no_fixed_calendar_date_is_left_in_the_fake_jobposting_site() -> None:
    source = Path(fake_jobposting_site.__file__).read_text(encoding="utf-8")

    assert not re.search(r"\b20\d{2}-\d{2}-\d{2}", source)
