"""R55 review follow-ups (PR #115 yellows) that need no database."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from opportunity_radar.opportunities.service import OpportunityService
from opportunity_radar.opportunities.suggestions import (
    existing_suggestion_fields,
    existing_suggestion_fields_many,
)
from tests.e2e import fake_job_board


class _Recorder:
    """A session whose `execute` answers one scripted row list per call."""

    def __init__(self, *answers: list[tuple]) -> None:
        self.answers = list(answers)
        self.calls = 0

    def execute(self, _statement):
        self.calls += 1
        return self.answers.pop(0)


def _opportunity(version: int = 1):
    return SimpleNamespace(id=uuid4(), version=version)


# --- C5: batch loading -------------------------------------------------------------------


def test_the_batch_costs_two_queries_for_the_whole_page_and_keeps_each_opportunity_apart() -> None:
    first, second, untouched = _opportunity(), _opportunity(version=2), _opportunity()
    session = _Recorder(
        [(first.id, 1, "seniority"), (second.id, 2, "work_mode")],
        [(first.id, 1, "role_family"), (second.id, 2, "seniority")],
    )

    found = existing_suggestion_fields_many(session, [first, second, untouched], "p1")

    assert session.calls == 2
    assert found[first.id] == {"seniority", "role_family"}
    assert found[second.id] == {"work_mode", "seniority"}
    assert found[untouched.id] == set()


def test_a_row_from_another_opportunity_version_does_not_count() -> None:
    current = _opportunity(version=3)
    session = _Recorder(
        [(current.id, 2, "seniority")],  # an older version's suggestion
        [(current.id, 2, "work_mode")],  # an older version's marker
    )

    assert existing_suggestion_fields_many(session, [current], "p1")[current.id] == set()


def test_without_a_prompt_version_markers_are_not_read() -> None:
    item = _opportunity()
    session = _Recorder([(item.id, 1, "seniority")])

    assert existing_suggestion_fields_many(session, [item])[item.id] == {"seniority"}
    assert session.calls == 1


def test_an_empty_page_runs_no_query_and_the_single_form_agrees_with_the_batch() -> None:
    session = _Recorder()
    assert existing_suggestion_fields_many(session, []) == {}
    assert session.calls == 0

    item = _opportunity()
    assert existing_suggestion_fields(_Recorder([(item.id, 1, "seniority")], []), item, "p1") == {
        "seniority"
    }


# --- B1: the race winner ------------------------------------------------------------------


class _Repository:
    def __init__(self, *answers) -> None:
        self.answers = list(answers)
        self.reads = 0

    def normalization_result(self, _raw_item_id, _version):
        self.reads += 1
        return self.answers.pop(0)


class _Session:
    def __init__(self, commit_error: Exception | None = None) -> None:
        self.rollbacks = 0
        self.commit_error = commit_error

    def rollback(self) -> None:
        self.rollbacks += 1

    def add(self, _row) -> None:
        pass

    def commit(self) -> None:
        if self.commit_error is not None:
            raise self.commit_error

    def refresh(self, _row) -> None:
        pass


def _integrity_error() -> IntegrityError:
    return IntegrityError("insert", {}, Exception("duplicate"))


def test_a_winner_that_is_missed_on_the_first_read_is_found_on_the_retry() -> None:
    winner = object()
    repository = _Repository(None, winner)
    service = OpportunityService(_Session(commit_error=_integrity_error()), repository)

    assert service._record_unexpected_failure(uuid4(), RuntimeError("boom")) is winner
    assert repository.reads == 2


def test_an_unreadable_winner_is_logged_and_leaves_the_item_pending(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = _Repository(None, None)
    service = OpportunityService(_Session(commit_error=_integrity_error()), repository)

    with caplog.at_level(logging.WARNING):
        assert service._record_unexpected_failure(uuid4(), RuntimeError("boom")) is None

    assert repository.reads == 2
    assert "race winner could not be read" in caplog.text


# --- e2e fake: FIRST_PUBLISHED is computed once -------------------------------------------


def test_the_fake_board_dates_are_computed_once_and_identical_across_requests() -> None:
    first = fake_job_board._jobs_for(fake_job_board.HEALTHY_BOARD)
    second = fake_job_board._jobs_for(fake_job_board.HEALTHY_BOARD)
    dynamic = [fake_job_board._jobs_for("e2e-one"), fake_job_board._jobs_for("e2e-two")]

    assert first[0]["first_published"] == second[0]["first_published"]
    assert first[0]["first_published"] == fake_job_board.FIRST_PUBLISHED
    assert first[0]["updated_at"] == fake_job_board.UPDATED_AT
    assert all(jobs[0]["first_published"] == fake_job_board.FIRST_PUBLISHED for jobs in dynamic)


def test_a_posting_never_claims_to_be_published_after_it_was_updated() -> None:
    assert fake_job_board.FIRST_PUBLISHED < fake_job_board.UPDATED_AT
