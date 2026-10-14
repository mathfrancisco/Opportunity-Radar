from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from opportunity_radar.operations.assessment_retention import AssessmentPruneReport
from scripts import retention_report


class _Connection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.read_only = False

    def exec_driver_sql(self, statement: str) -> None:
        self.statements.append(statement)
        if statement == "SET TRANSACTION READ ONLY":
            self.read_only = True

    def execute(self, statement: str, parameters: Any = None) -> _Connection:
        self.statements.append(str(statement))
        return self

    def fetchall(self) -> list[tuple[str, str, int]]:
        return [("matching", "match_assessment", 1234)]

    def fetchone(self) -> tuple[int]:
        return (4,)

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None


class _Engine:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def connect(self) -> _Connection:
        return self.connection


def test_report_is_read_only_aggregate_and_counts_protected_references(monkeypatch: Any) -> None:
    connection = _Connection()
    retention = AssessmentPruneReport(
        dry_run=True,
        retention_days=7,
        cutoff=datetime(2026, 1, 1, tzinfo=UTC),
        candidates=5,
        kept_with_analysis=1,
        kept_with_claim=1,
        kept_with_application=1,
        kept_as_current=1,
        deletable=1,
        deleted=1,
        rows_before=10,
        rows_remaining=10,
        avg_per_open_posting_before=2.0,
        avg_per_open_posting_after=None,
    )
    monkeypatch.setattr(
        retention_report,
        "prune_superseded_assessments",
        lambda *_args, **_kwargs: retention,
    )

    report = retention_report.build_report(_Engine(connection), retention_days=7)

    assert connection.read_only is True
    assert report["candidates"] == 5
    assert report["protected_references"] == {
        "analysis": 1,
        "claim": 1,
        "application": 1,
        "current": 1,
    }
    assert report["relation_sizes"] == [
        {"schema": "matching", "relation": "match_assessment", "bytes": 1234}
    ]
    assert all("DELETE" not in statement.upper() for statement in connection.statements)
    assert all("UPDATE" not in statement.upper() for statement in connection.statements)
    assert all("INSERT" not in statement.upper() for statement in connection.statements)

    serialized = json.dumps(report)
    assert "query" not in serialized.lower()
    assert "personal" not in serialized.lower()
