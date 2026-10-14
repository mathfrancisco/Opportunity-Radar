"""Collect redacted host, Docker, and PostgreSQL resource measurements."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from opportunity_radar.platform.backup import postgres_dsn

Runner = Callable[..., subprocess.CompletedProcess[str]]


def _run(runner: Runner, command: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return runner(command, capture_output=True, text=True, check=False)
    except OSError:
        return None


def _git_commit(runner: Runner) -> str | None:
    result = _run(runner, ["git", "rev-parse", "HEAD"])
    if result is None or result.returncode != 0:
        return None
    commit = result.stdout.strip()
    return commit or None


def _docker_stats(runner: Runner) -> list[dict[str, str]]:
    result = _run(runner, ["docker", "stats", "--no-stream", "--format", "{{json .}}"])
    if result is None or result.returncode != 0:
        return []
    metrics: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        metrics.append(
            {
                "name": str(row.get("Name", "")),
                "cpu_percent": str(row.get("CPUPerc", "")),
                "memory": str(row.get("MemUsage", "")),
                "memory_percent": str(row.get("MemPerc", "")),
            }
        )
    return metrics


def _host_totals(runner: Runner) -> dict[str, Any]:
    if os.name == "nt":
        return {}
    totals: dict[str, Any] = {}
    free = _run(runner, ["free", "-b"])
    if free is not None and free.returncode == 0:
        for line in free.stdout.splitlines():
            fields = line.split()
            if fields and fields[0] == "Mem:" and len(fields) >= 3:
                totals["memory_total_bytes"] = int(fields[1])
                totals["memory_available_bytes"] = int(fields[6]) if len(fields) >= 7 else None
                break
    disk = _run(runner, ["df", "-B1", "/"])
    if disk is not None and disk.returncode == 0:
        rows = disk.stdout.splitlines()
        if len(rows) > 1:
            fields = rows[-1].split()
            if len(fields) >= 5:
                totals["disk_total_bytes"] = int(fields[1])
                totals["disk_used_bytes"] = int(fields[2])
                totals["disk_available_bytes"] = int(fields[3])
    return totals


def _postgres_connections(database_url: str, connect: Callable[..., Any]) -> list[dict[str, Any]]:
    connection = connect(
        postgres_dsn(database_url),
        connect_timeout=3,
        options="-c statement_timeout=3000 -c default_transaction_read_only=on",
    )
    try:
        connection.read_only = True
        cursor = connection.cursor()
        try:
            cursor.execute(
                "SELECT state, count(*) FROM pg_stat_activity GROUP BY state ORDER BY state"
            )
            return [
                {"state": row[0] or "unknown", "count": int(row[1])}
                for row in cursor.fetchall()
            ]
        finally:
            cursor.close()
    finally:
        connection.rollback()
        connection.close()


def collect_measurement(
    *,
    phase: str,
    database_url: str | None = None,
    runner: Runner = subprocess.run,
    connect: Callable[..., Any] | None = psycopg.connect,
) -> dict[str, Any]:
    """Collect one comparable measurement window without reading user data."""
    record: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "phase": phase,
        "git_commit": _git_commit(runner),
        "docker": _docker_stats(runner),
        "host": _host_totals(runner),
    }
    if database_url and connect is not None:
        record["postgres_connections"] = _postgres_connections(database_url, connect)
    return record


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("before", "peak", "after", "idle"), required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    record = collect_measurement(phase=args.phase, database_url=os.environ.get("DATABASE_URL"))
    line = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
    if args.output is None:
        print(line)
    else:
        args.output.write_text(line + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
