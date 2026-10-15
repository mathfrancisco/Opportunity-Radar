"""Project Neon CU-h and storage budget offline without any network or DB access.

Usage::

    python scripts/project_neon_budget.py \\
        --active-hours-per-run 2 \\
        --runs-per-month 31 \\
        --cu 0.25

Output is JSON to stdout (or --output PATH).  Exit codes:

* 0 — no budget breach (compute pass AND storage pass-or-not-projected)
* 1 — at least one breach (compute fail OR storage fail)
* 2 — invalid arguments or --output write failure

744 h horizon example (31 days × 24 h/day × 0.25 CU = 186 CU-h → exit 1):

    python scripts/project_neon_budget.py \\
        --active-hours-per-run 24 \\
        --runs-per-month 31 \\
        --cu 0.25
    # total_cu_hours: 186, compute_status: "fail", exit 1

Assumptions:
* Each ``active_hours_per_run`` window already includes startup and suspend
  tails — do not add padding separately.
* The compute limit is 80 CU-h per month (well below the nominal 100 CU-h
  Neon free-tier quota; the remaining headroom is the operational reserve).
* The storage limit is 1 000 000 000 bytes (1 decimal GB, matching Neon's
  free-tier threshold).
* No rounding is applied before comparisons: Decimal arithmetic is used
  throughout to avoid floating-point drift.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from decimal import Decimal, Inexact, InvalidOperation, localcontext
from pathlib import Path
from typing import Any

_COMPUTE_LIMIT = Decimal("80")
_STORAGE_LIMIT = 1_000_000_000  # bytes (1 decimal GB)


def project_budget(
    *,
    active_hours_per_run: Decimal,
    runs_per_month: int,
    cu: Decimal,
    additional_cu_hours: Decimal = Decimal("0"),
    current_storage_bytes: int | None = None,
    monthly_growth_bytes: int | None = None,
) -> dict[str, Any]:
    """Compute offline Neon CU-h and storage projection.

    Quota comparisons use exact :mod:`decimal` arithmetic; no rounding is
    applied before any comparison.

    Parameters
    ----------
    active_hours_per_run:
        Hours the database is actively used per pipeline run.  Must be
        non-negative and finite.
    runs_per_month:
        Number of pipeline runs per month.  Must be a non-negative integer
        (zero runs is valid).
    cu:
        Compute Unit size (e.g. 0.25).  Must be strictly positive and finite.
    additional_cu_hours:
        Incremental CU-h demand outside counted windows (default 0).  Must be
        non-negative and finite.
    current_storage_bytes:
        Current database storage in bytes.  Must be provided together with
        ``monthly_growth_bytes`` (both-or-none).  Must be a non-negative
        integer.
    monthly_growth_bytes:
        Expected byte growth per month.  Must be provided together with
        ``current_storage_bytes`` (both-or-none).  Must be a non-negative
        integer.

    Returns
    -------
    dict
        Projection result.  Decimal values are serialised as strings.

    Raises
    ------
    ValueError
        On any invalid input (negative value, non-finite Decimal, CU <= 0,
        fractional runs, fractional/negative bytes, incomplete storage pair).
    """
    # ------------------------------------------------------------------ #
    # Validate Decimal inputs                                              #
    # ------------------------------------------------------------------ #
    def _check_decimal(value: Decimal, name: str, *, positive: bool = False) -> None:
        if not value.is_finite():
            raise ValueError(f"{name} must be a finite Decimal, got {value!r}")
        if positive and value <= 0:
            raise ValueError(f"{name} must be > 0, got {value}")
        if not positive and value < 0:
            raise ValueError(f"{name} must be >= 0, got {value}")

    _check_decimal(active_hours_per_run, "active_hours_per_run")
    _check_decimal(additional_cu_hours, "additional_cu_hours")
    _check_decimal(cu, "cu", positive=True)

    # runs_per_month must be a non-negative integer (fractional forbidden)
    if not isinstance(runs_per_month, int) or isinstance(runs_per_month, bool):
        raise ValueError(
            f"runs_per_month must be a non-negative integer, got {runs_per_month!r}"
        )
    if runs_per_month < 0:
        raise ValueError(f"runs_per_month must be >= 0, got {runs_per_month}")

    # Storage pair: both-or-none
    storage_pair_given = (current_storage_bytes is not None, monthly_growth_bytes is not None)
    if storage_pair_given[0] != storage_pair_given[1]:
        raise ValueError(
            "current_storage_bytes and monthly_growth_bytes must be provided together"
        )
    has_storage = storage_pair_given[0]

    if has_storage:
        for val, name in (
            (current_storage_bytes, "current_storage_bytes"),
            (monthly_growth_bytes, "monthly_growth_bytes"),
        ):
            if not isinstance(val, int) or isinstance(val, bool):
                raise ValueError(f"{name} must be a non-negative integer, got {val!r}")
            if val < 0:  # type: ignore[operator]
                raise ValueError(f"{name} must be >= 0, got {val}")

    # ------------------------------------------------------------------ #
    # Compute                                                              #
    # ------------------------------------------------------------------ #
    # Exact arithmetic: trap on any rounding instead of silently losing digits.
    try:
        with localcontext() as ctx:
            ctx.prec = 1000
            ctx.traps[Inexact] = True
            scheduled_cu_hours = active_hours_per_run * Decimal(runs_per_month) * cu
            total_cu_hours = scheduled_cu_hours + additional_cu_hours
    except ArithmeticError as exc:
        raise ValueError(f"inputs too large for exact arithmetic: {exc}") from exc

    compute_status = "pass" if total_cu_hours <= _COMPUTE_LIMIT else "fail"

    # ------------------------------------------------------------------ #
    # Storage                                                              #
    # ------------------------------------------------------------------ #
    if has_storage:
        projected_storage_bytes: int | None = current_storage_bytes + monthly_growth_bytes  # type: ignore[operator]
        storage_status = "pass" if projected_storage_bytes < _STORAGE_LIMIT else "fail"
    else:
        projected_storage_bytes = None
        storage_status = "not_projected"

    has_budget_breach = compute_status == "fail" or storage_status == "fail"

    return {
        "inputs": {
            "active_hours_per_run": str(active_hours_per_run),
            "runs_per_month": runs_per_month,
            "cu": str(cu),
            "additional_cu_hours": str(additional_cu_hours),
            "current_storage_bytes": current_storage_bytes,
            "monthly_growth_bytes": monthly_growth_bytes,
        },
        "scheduled_cu_hours": str(scheduled_cu_hours),
        "additional_cu_hours": str(additional_cu_hours),
        "total_cu_hours": str(total_cu_hours),
        "compute_limit_cu_hours": str(_COMPUTE_LIMIT),
        "compute_status": compute_status,
        "storage_projected_bytes": projected_storage_bytes,
        "storage_limit_bytes": _STORAGE_LIMIT,
        "storage_status": storage_status,
        "has_budget_breach": has_budget_breach,
    }


def _parse_decimal(value: str, name: str) -> Decimal:
    try:
        d = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(
            f"{name}: cannot parse {value!r} as a Decimal"
        ) from exc
    if not d.is_finite():
        raise argparse.ArgumentTypeError(f"{name}: value must be finite, got {value!r}")
    return d


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--active-hours-per-run",
        required=True,
        metavar="DEC",
        help="Active hours per pipeline run (Decimal).",
    )
    parser.add_argument(
        "--runs-per-month",
        required=True,
        type=int,
        metavar="INT",
        help="Number of runs per month (non-negative integer).",
    )
    parser.add_argument(
        "--cu",
        required=True,
        metavar="DEC",
        help="Compute Unit size (e.g. 0.25).",
    )
    parser.add_argument(
        "--additional-cu-hours",
        default="0",
        metavar="DEC",
        help="Extra CU-h outside scheduled windows (default 0).",
    )
    parser.add_argument(
        "--current-storage-bytes",
        default=None,
        type=int,
        metavar="INT",
        help="Current storage in bytes (must be paired with --monthly-growth-bytes).",
    )
    parser.add_argument(
        "--monthly-growth-bytes",
        default=None,
        type=int,
        metavar="INT",
        help="Expected monthly storage growth in bytes (must be paired with "
        "--current-storage-bytes).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="PATH",
        help="Write JSON output to this file instead of stdout.",
    )

    args = parser.parse_args(argv)

    # Parse Decimal arguments with descriptive errors
    try:
        active_hours_per_run = _parse_decimal(args.active_hours_per_run, "--active-hours-per-run")
        cu = _parse_decimal(args.cu, "--cu")
        additional_cu_hours = _parse_decimal(args.additional_cu_hours, "--additional-cu-hours")
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
        return 2  # unreachable; parser.error() exits

    try:
        result = project_budget(
            active_hours_per_run=active_hours_per_run,
            runs_per_month=args.runs_per_month,
            cu=cu,
            additional_cu_hours=additional_cu_hours,
            current_storage_bytes=args.current_storage_bytes,
            monthly_growth_bytes=args.monthly_growth_bytes,
        )
    except ValueError as exc:
        parser.error(str(exc))
        return 2  # unreachable

    output_text = json.dumps(result, ensure_ascii=True, indent=2) + "\n"

    if args.output is None:
        print(output_text, end="")
    else:
        try:
            args.output.write_text(output_text, encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot write to {args.output}: {exc}", file=sys.stderr)
            return 2

    return 1 if result["has_budget_breach"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
