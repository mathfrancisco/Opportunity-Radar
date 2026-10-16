"""Offline projection of Neon CU-h and storage budget.

All tests are offline-safe: no network, no database, no filesystem side-effects
beyond a temporary path created by the ``tmp_path`` fixture.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from scripts.project_neon_budget import main, project_budget

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_cli(*args: str, env: dict[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    """Run the script in a subprocess and return (exit_code, parsed_json)."""
    import os

    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    result = subprocess.run(
        [sys.executable, "-S", "scripts/project_neon_budget.py", *args],
        capture_output=True,
        text=True,
        env=run_env,
    )
    if result.stdout.strip():
        data = json.loads(result.stdout)
    else:
        data = {}
    return result.returncode, data


# ---------------------------------------------------------------------------
# TC01 — 2 × 31 × 0.25 = 15.5 CU-h → pass, exit 0
# ---------------------------------------------------------------------------


def test_tc01_low_usage_passes() -> None:
    result = project_budget(
        active_hours_per_run=Decimal("2"),
        runs_per_month=31,
        cu=Decimal("0.25"),
    )
    assert result["compute_status"] == "pass"
    assert result["has_budget_breach"] is False
    assert Decimal(result["total_cu_hours"]) == Decimal("15.5")


def test_tc01_cli_exit_0() -> None:
    code, data = _run_cli(
        "--active-hours-per-run", "2",
        "--runs-per-month", "31",
        "--cu", "0.25",
    )
    assert code == 0
    assert data["compute_status"] == "pass"


# ---------------------------------------------------------------------------
# TC02 — 744 h horizon: 24 × 31 × 0.25 = 186 CU-h → fail, exit 1
# ---------------------------------------------------------------------------


def test_tc02_744h_horizon_fails() -> None:
    result = project_budget(
        active_hours_per_run=Decimal("24"),
        runs_per_month=31,
        cu=Decimal("0.25"),
    )
    assert result["compute_status"] == "fail"
    assert result["has_budget_breach"] is True
    assert Decimal(result["total_cu_hours"]) == Decimal("186")


def test_tc02_cli_exit_1() -> None:
    code, data = _run_cli(
        "--active-hours-per-run", "24",
        "--runs-per-month", "31",
        "--cu", "0.25",
    )
    assert code == 1
    assert data["compute_status"] == "fail"


# ---------------------------------------------------------------------------
# TC03 — 320 × 1 × 0.25 = 80 CU-h → exactly at limit, pass, exit 0
# ---------------------------------------------------------------------------


def test_tc03_exactly_at_limit_passes() -> None:
    result = project_budget(
        active_hours_per_run=Decimal("320"),
        runs_per_month=1,
        cu=Decimal("0.25"),
    )
    assert Decimal(result["total_cu_hours"]) == Decimal("80")
    assert result["compute_status"] == "pass"
    assert result["has_budget_breach"] is False


def test_tc03_cli_exit_0() -> None:
    code, data = _run_cli(
        "--active-hours-per-run", "320",
        "--runs-per-month", "1",
        "--cu", "0.25",
    )
    assert code == 0


# ---------------------------------------------------------------------------
# TC04 — 320.000000004 × 1 × 0.25 = 80.000000001 → just over limit, fail
# ---------------------------------------------------------------------------


def test_tc04_just_over_limit_fails() -> None:
    result = project_budget(
        active_hours_per_run=Decimal("320.000000004"),
        runs_per_month=1,
        cu=Decimal("0.25"),
    )
    assert Decimal(result["total_cu_hours"]) > Decimal("80")
    assert result["compute_status"] == "fail"
    assert result["has_budget_breach"] is True


def test_tc04_cli_exit_1() -> None:
    code, data = _run_cli(
        "--active-hours-per-run", "320.000000004",
        "--runs-per-month", "1",
        "--cu", "0.25",
    )
    assert code == 1


# ---------------------------------------------------------------------------
# TC05 — scheduled=79 + additional=1 → total=80 → pass
# ---------------------------------------------------------------------------


def test_tc05_additional_at_limit_passes() -> None:
    # scheduled: active_hours_per_run × runs × cu = 79 / 0.25 / 1 × 0.25 = 79
    # Use 316 h × 1 run × 0.25 CU = 79 CU-h, then additional=1 → total=80
    result = project_budget(
        active_hours_per_run=Decimal("316"),
        runs_per_month=1,
        cu=Decimal("0.25"),
        additional_cu_hours=Decimal("1"),
    )
    assert Decimal(result["scheduled_cu_hours"]) == Decimal("79")
    assert Decimal(result["additional_cu_hours"]) == Decimal("1")
    assert Decimal(result["total_cu_hours"]) == Decimal("80")
    assert result["compute_status"] == "pass"


# ---------------------------------------------------------------------------
# TC06 — scheduled=79 + additional=2 → total=81 → fail
# ---------------------------------------------------------------------------


def test_tc06_additional_over_limit_fails() -> None:
    result = project_budget(
        active_hours_per_run=Decimal("316"),
        runs_per_month=1,
        cu=Decimal("0.25"),
        additional_cu_hours=Decimal("2"),
    )
    assert Decimal(result["total_cu_hours"]) == Decimal("81")
    assert result["compute_status"] == "fail"
    assert result["has_budget_breach"] is True


# ---------------------------------------------------------------------------
# TC07 — zero runs + additional_cu_hours=81 → fail
# ---------------------------------------------------------------------------


def test_tc07_zero_runs_plus_additional_fails() -> None:
    result = project_budget(
        active_hours_per_run=Decimal("0"),
        runs_per_month=0,
        cu=Decimal("0.25"),
        additional_cu_hours=Decimal("81"),
    )
    assert Decimal(result["scheduled_cu_hours"]) == Decimal("0")
    assert Decimal(result["total_cu_hours"]) == Decimal("81")
    assert result["compute_status"] == "fail"
    assert result["has_budget_breach"] is True


# ---------------------------------------------------------------------------
# TC08 — storage 900000000 + 99999999 = 999999999 < 1e9 → pass
# ---------------------------------------------------------------------------


def test_tc08_storage_just_under_limit_passes() -> None:
    result = project_budget(
        active_hours_per_run=Decimal("1"),
        runs_per_month=1,
        cu=Decimal("0.25"),
        current_storage_bytes=900_000_000,
        monthly_growth_bytes=99_999_999,
    )
    assert result["storage_projected_bytes"] == 999_999_999
    assert result["storage_status"] == "pass"
    assert result["has_budget_breach"] is False


# ---------------------------------------------------------------------------
# TC09 — storage 900000000 + 100000000 = 1000000000 >= 1e9 → fail
# ---------------------------------------------------------------------------


def test_tc09_storage_at_limit_fails() -> None:
    result = project_budget(
        active_hours_per_run=Decimal("1"),
        runs_per_month=1,
        cu=Decimal("0.25"),
        current_storage_bytes=900_000_000,
        monthly_growth_bytes=100_000_000,
    )
    assert result["storage_projected_bytes"] == 1_000_000_000
    assert result["storage_status"] == "fail"
    assert result["has_budget_breach"] is True


# ---------------------------------------------------------------------------
# TC10 — storage breach with passing compute → exit 1
# ---------------------------------------------------------------------------


def test_tc10_storage_breach_with_passing_compute_exits_1() -> None:
    result = project_budget(
        active_hours_per_run=Decimal("1"),
        runs_per_month=1,
        cu=Decimal("0.25"),
        current_storage_bytes=999_000_000,
        monthly_growth_bytes=1_000_001,
    )
    assert result["compute_status"] == "pass"
    assert result["storage_status"] == "fail"
    assert result["has_budget_breach"] is True

    code, data = _run_cli(
        "--active-hours-per-run", "1",
        "--runs-per-month", "1",
        "--cu", "0.25",
        "--current-storage-bytes", "999000000",
        "--monthly-growth-bytes", "1000001",
    )
    assert code == 1
    assert data["compute_status"] == "pass"
    assert data["storage_status"] == "fail"


# ---------------------------------------------------------------------------
# TC11 — storage omitted → storage_status="not_projected", bytes=null
# ---------------------------------------------------------------------------


def test_tc11_storage_omitted_not_projected() -> None:
    result = project_budget(
        active_hours_per_run=Decimal("2"),
        runs_per_month=10,
        cu=Decimal("0.25"),
    )
    assert result["storage_status"] == "not_projected"
    assert result["storage_projected_bytes"] is None
    # compute result preserved
    assert result["compute_status"] == "pass"
    assert Decimal(result["total_cu_hours"]) == Decimal("5")

    # Also verify JSON serialisation produces null (not a fabricated pass)
    payload = json.dumps(result)
    parsed = json.loads(payload)
    assert parsed["storage_projected_bytes"] is None
    assert parsed["storage_status"] == "not_projected"


# ---------------------------------------------------------------------------
# TC12 — invalid inputs raise ValueError (function) / exit 2 (CLI)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        # negative active_hours_per_run
        {
            "active_hours_per_run": Decimal("-1"),
            "runs_per_month": 1,
            "cu": Decimal("0.25"),
        },
        # negative additional_cu_hours
        {
            "active_hours_per_run": Decimal("1"),
            "runs_per_month": 1,
            "cu": Decimal("0.25"),
            "additional_cu_hours": Decimal("-0.01"),
        },
        # CU <= 0 (zero)
        {
            "active_hours_per_run": Decimal("1"),
            "runs_per_month": 1,
            "cu": Decimal("0"),
        },
        # CU < 0
        {
            "active_hours_per_run": Decimal("1"),
            "runs_per_month": 1,
            "cu": Decimal("-1"),
        },
        # negative runs_per_month
        {
            "active_hours_per_run": Decimal("1"),
            "runs_per_month": -1,
            "cu": Decimal("0.25"),
        },
        # non-finite (Infinity)
        {
            "active_hours_per_run": Decimal("Infinity"),
            "runs_per_month": 1,
            "cu": Decimal("0.25"),
        },
        # non-finite CU (NaN)
        {
            "active_hours_per_run": Decimal("1"),
            "runs_per_month": 1,
            "cu": Decimal("NaN"),
        },
        # negative current_storage_bytes
        {
            "active_hours_per_run": Decimal("1"),
            "runs_per_month": 1,
            "cu": Decimal("0.25"),
            "current_storage_bytes": -1,
            "monthly_growth_bytes": 0,
        },
        # negative monthly_growth_bytes
        {
            "active_hours_per_run": Decimal("1"),
            "runs_per_month": 1,
            "cu": Decimal("0.25"),
            "current_storage_bytes": 0,
            "monthly_growth_bytes": -1,
        },
    ],
)
def test_tc12_invalid_inputs_raise_value_error(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        project_budget(**kwargs)


def test_tc12_cli_negative_active_hours_exits_2() -> None:
    code, _ = _run_cli(
        "--active-hours-per-run", "-1",
        "--runs-per-month", "1",
        "--cu", "0.25",
    )
    assert code == 2


def test_tc12_cli_cu_zero_exits_2() -> None:
    code, _ = _run_cli(
        "--active-hours-per-run", "1",
        "--runs-per-month", "1",
        "--cu", "0",
    )
    assert code == 2


def test_tc12_cli_infinity_cu_exits_2() -> None:
    code, _ = _run_cli(
        "--active-hours-per-run", "1",
        "--runs-per-month", "1",
        "--cu", "Infinity",
    )
    assert code == 2


# ---------------------------------------------------------------------------
# TC13 — incomplete storage pair → ValueError / exit 2
# ---------------------------------------------------------------------------


def test_tc13_only_current_storage_raises() -> None:
    with pytest.raises(ValueError, match="together"):
        project_budget(
            active_hours_per_run=Decimal("1"),
            runs_per_month=1,
            cu=Decimal("0.25"),
            current_storage_bytes=500_000_000,
        )


def test_tc13_only_growth_raises() -> None:
    with pytest.raises(ValueError, match="together"):
        project_budget(
            active_hours_per_run=Decimal("1"),
            runs_per_month=1,
            cu=Decimal("0.25"),
            monthly_growth_bytes=100_000_000,
        )


def test_tc13_cli_incomplete_storage_pair_exits_2() -> None:
    code, _ = _run_cli(
        "--active-hours-per-run", "1",
        "--runs-per-month", "1",
        "--cu", "0.25",
        "--current-storage-bytes", "500000000",
        # missing --monthly-growth-bytes
    )
    assert code == 2


# ---------------------------------------------------------------------------
# TC14 — stdout vs --output: same JSON content, no duplicate when --output used
# ---------------------------------------------------------------------------


def test_tc14_output_file_matches_stdout(tmp_path: Path) -> None:
    import os

    out_file = tmp_path / "budget.json"

    # Run with stdout
    r_stdout = subprocess.run(
        [
            sys.executable, "-S", "scripts/project_neon_budget.py",
            "--active-hours-per-run", "2",
            "--runs-per-month", "31",
            "--cu", "0.25",
        ],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )

    # Run with --output
    r_file = subprocess.run(
        [
            sys.executable, "-S", "scripts/project_neon_budget.py",
            "--active-hours-per-run", "2",
            "--runs-per-month", "31",
            "--cu", "0.25",
            "--output", str(out_file),
        ],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )

    assert r_file.returncode == r_stdout.returncode
    # stdout should be empty when --output is used
    assert r_file.stdout == ""
    # Content must match
    assert json.loads(r_stdout.stdout) == json.loads(out_file.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# TC15 — offline isolation: patched socket + subprocess, secret not leaked
# ---------------------------------------------------------------------------


def test_tc15_offline_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that the pure function makes no network calls and leaks no secrets."""

    def _no_connect(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("network access forbidden in offline test")

    def _no_popen(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("subprocess access forbidden in offline test")

    monkeypatch.setattr(socket.socket, "connect", _no_connect)
    monkeypatch.setattr(subprocess, "Popen", _no_popen)
    monkeypatch.setenv("NEON_DB_SECRET", "supersecret")

    result = project_budget(
        active_hours_per_run=Decimal("2"),
        runs_per_month=10,
        cu=Decimal("0.25"),
    )

    serialised = json.dumps(result)
    assert "supersecret" not in serialised
    assert "NEON_DB_SECRET" not in serialised
    # Function must still return a valid result
    assert result["compute_status"] in ("pass", "fail")


# ---------------------------------------------------------------------------
# TC16 — subprocess test: verify exit code and JSON output via -S flag
# ---------------------------------------------------------------------------


def test_tc16_subprocess_verify_exit_code_and_json() -> None:
    """Run the script as a subprocess and verify exit code + JSON correctness."""
    import os

    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "scripts/project_neon_budget.py",
            "--active-hours-per-run", "24",
            "--runs-per-month", "31",
            "--cu", "0.25",
        ],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )

    assert result.returncode == 1  # compute fail → exit 1
    data = json.loads(result.stdout)
    assert data["compute_status"] == "fail"
    assert data["has_budget_breach"] is True
    assert Decimal(data["total_cu_hours"]) == Decimal("186")
    # Must not have timestamps
    assert "timestamp" not in data
    # Decimal values are strings in JSON
    assert isinstance(data["total_cu_hours"], str)
    assert isinstance(data["compute_limit_cu_hours"], str)
    # storage_projected_bytes is null (not projected)
    assert data["storage_projected_bytes"] is None
    assert data["storage_status"] == "not_projected"


# ---------------------------------------------------------------------------
# Additional: additional_cu_hours always present in output
# ---------------------------------------------------------------------------


def test_additional_cu_hours_always_in_output() -> None:
    result = project_budget(
        active_hours_per_run=Decimal("1"),
        runs_per_month=1,
        cu=Decimal("0.25"),
    )
    assert "additional_cu_hours" in result
    assert result["additional_cu_hours"] == "0"


# ---------------------------------------------------------------------------
# Additional: zero runs is valid
# ---------------------------------------------------------------------------


def test_zero_runs_is_valid() -> None:
    result = project_budget(
        active_hours_per_run=Decimal("100"),
        runs_per_month=0,
        cu=Decimal("0.25"),
    )
    assert Decimal(result["scheduled_cu_hours"]) == Decimal("0")
    assert result["compute_status"] == "pass"


# ---------------------------------------------------------------------------
# Additional: fractional runs_per_month rejected (float passed as int)
# ---------------------------------------------------------------------------


def test_fractional_runs_per_month_rejected() -> None:
    with pytest.raises((ValueError, TypeError)):
        project_budget(
            active_hours_per_run=Decimal("1"),
            runs_per_month=1.5,  # type: ignore[arg-type]
            cu=Decimal("0.25"),
        )


# ---------------------------------------------------------------------------
# Additional: has_budget_breach output key is always boolean
# ---------------------------------------------------------------------------


def test_has_budget_breach_is_boolean() -> None:
    for breach in (True, False):
        active_h = Decimal("24") if breach else Decimal("1")
        result = project_budget(
            active_hours_per_run=active_h,
            runs_per_month=31,
            cu=Decimal("0.25"),
        )
        assert isinstance(result["has_budget_breach"], bool)


# ---------------------------------------------------------------------------
# Additional: CLI argument rejection and output failure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [
        ["--runs-per-month", "1.5"],
        ["--current-storage-bytes", "1.5", "--monthly-growth-bytes", "1"],
        ["--current-storage-bytes", "1", "--monthly-growth-bytes", "-1"],
        ["--additional-cu-hours", "-1"],
        ["--additional-cu-hours", "NaN"],
        ["--monthly-growth-bytes", "1"],
    ],
)
def test_cli_rejects_invalid_arguments(extra: list[str]) -> None:
    base = {"--active-hours-per-run": "1", "--runs-per-month": "1", "--cu": "0.25"}
    for flag, value in zip(extra[::2], extra[1::2], strict=True):
        base[flag] = value
    argv = [item for pair in base.items() for item in pair]
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2


def test_cli_output_write_failure_exits_2(tmp_path: Path) -> None:
    code = main(
        [
            "--active-hours-per-run", "1",
            "--runs-per-month", "1",
            "--cu", "0.25",
            "--output", str(tmp_path / "missing-dir" / "out.json"),
        ]
    )
    assert code == 2


def test_extreme_precision_is_not_rounded() -> None:
    # 28-digit default context would round this sum down to exactly 80.
    result = project_budget(
        active_hours_per_run=Decimal("320"),
        runs_per_month=1,
        cu=Decimal("0.25"),
        additional_cu_hours=Decimal("0.0000000000000000000000000000001"),
    )
    assert result["compute_status"] == "fail"


def test_cli_main_offline_and_secret_free(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("forbidden in offline test")

    monkeypatch.setattr(socket.socket, "connect", _forbidden)
    monkeypatch.setattr(subprocess, "Popen", _forbidden)
    monkeypatch.setenv("NEON_DB_SECRET", "supersecret")
    code = main(
        ["--active-hours-per-run", "2", "--runs-per-month", "31", "--cu", "0.25"]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "supersecret" not in out
    assert Decimal(json.loads(out)["total_cu_hours"]) == Decimal("15.5")


# ---------------------------------------------------------------------------
# Lenient numeric forms are rejected (exit 2)
# ---------------------------------------------------------------------------

_BAD_INTS = ["1_0", "١٢", "+1", "-1", " 1", "1 ", "1\n", "1.0", "0x10", "1e3", ""]
_BAD_DECIMALS = [
    "1_0", "١٢", "+1", "-1", "-0", "-0.0", " 1", "1 ", "1\n", ".5", "1.", "1e3",
    "1e999999", "1E+2", "inf", "Infinity", "nan", "NaN", "",
]
_VALID_BASE = {"--active-hours-per-run": "1", "--runs-per-month": "1", "--cu": "0.25"}


def _argv(**overrides: str) -> list[str]:
    values = dict(_VALID_BASE)
    values.update({"--" + k.replace("_", "-"): v for k, v in overrides.items()})
    return [item for pair in values.items() for item in pair]


@pytest.mark.parametrize("bad", _BAD_INTS)
@pytest.mark.parametrize(
    "flag", ["runs_per_month", "current_storage_bytes", "monthly_growth_bytes"]
)
def test_cli_rejects_lenient_integer_forms(flag: str, bad: str) -> None:
    extra = {"current_storage_bytes": "1", "monthly_growth_bytes": "1"}
    extra[flag] = bad
    with pytest.raises(SystemExit) as exc:
        main(_argv(**extra))
    assert exc.value.code == 2


@pytest.mark.parametrize("bad", _BAD_DECIMALS)
@pytest.mark.parametrize("flag", ["active_hours_per_run", "cu", "additional_cu_hours"])
def test_cli_rejects_lenient_decimal_forms(flag: str, bad: str) -> None:
    with pytest.raises(SystemExit) as exc:
        main(_argv(**{flag: bad}))
    assert exc.value.code == 2


def test_cli_accepts_plain_ascii_forms(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        _argv(
            active_hours_per_run="0", runs_per_month="0", additional_cu_hours="0.5",
            current_storage_bytes="0", monthly_growth_bytes="00",
        )
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["total_cu_hours"] == "0.50"


@pytest.mark.parametrize(
    "bad", [Decimal("-0"), Decimal("1E+3"), Decimal("1E999999"), Decimal("-0.0")]
)
def test_project_budget_rejects_negative_zero_and_exponent_forms(bad: Decimal) -> None:
    with pytest.raises(ValueError):
        project_budget(active_hours_per_run=bad, runs_per_month=1, cu=Decimal("0.25"))
    with pytest.raises(ValueError):
        project_budget(
            active_hours_per_run=Decimal("1"), runs_per_month=1, cu=Decimal("0.25"),
            additional_cu_hours=bad,
        )


def test_project_budget_rejects_string_integers() -> None:
    with pytest.raises(ValueError):
        project_budget(
            active_hours_per_run=Decimal("1"),
            runs_per_month="1",  # type: ignore[arg-type]
            cu=Decimal("0.25"),
        )
    with pytest.raises(ValueError):
        project_budget(
            active_hours_per_run=Decimal("1"), runs_per_month=1, cu=Decimal("0.25"),
            current_storage_bytes="1",  # type: ignore[arg-type]
            monthly_growth_bytes=1,
        )


def test_cli_subprocess_env_isolation() -> None:
    """The real script must not echo environment secrets to stdout or stderr."""
    secret = "synthetic-secret-f53-7c1e"
    code, _ = _run_cli(
        "--active-hours-per-run", "2",
        "--runs-per-month", "31",
        "--cu", "0.25",
        env={"NEON_DB_SECRET": secret, "DATABASE_URL": f"postgresql://u:{secret}@h/db"},
    )
    assert code == 0
    import os

    for argv in (
        ["--active-hours-per-run", "2", "--runs-per-month", "31", "--cu", "0.25"],
        ["--active-hours-per-run", "x", "--runs-per-month", "31", "--cu", "0.25"],
    ):
        proc = subprocess.run(
            [sys.executable, "-S", "scripts/project_neon_budget.py", *argv],
            capture_output=True,
            text=True,
            env={**os.environ, "NEON_DB_SECRET": secret},
        )
        assert secret not in proc.stdout
        assert secret not in proc.stderr


# ---------------------------------------------------------------------------
# R55-E5 — hourly windows: 24 windows/day x 31 days = 744 runs/month
# ---------------------------------------------------------------------------

_HOURLY_RUNS = 24 * 31


def test_hourly_windows_typical_activity_stays_under_the_compute_limit() -> None:
    # About 5 min of work plus the 5 min Neon suspend tail = 10 min active per window.
    result = project_budget(
        active_hours_per_run=Decimal("0.1667"), runs_per_month=_HOURLY_RUNS, cu=Decimal("0.25")
    )
    assert result["total_cu_hours"] == "31.006200"
    assert result["compute_status"] == "pass"


def test_hourly_windows_worst_case_full_deadline_still_passes() -> None:
    # 15 min deadline fully used plus the 5 min suspend tail = 20 min active per window.
    result = project_budget(
        active_hours_per_run=Decimal("0.3334"), runs_per_month=_HOURLY_RUNS, cu=Decimal("0.25")
    )
    assert result["total_cu_hours"] == "62.012400"
    assert result["compute_status"] == "pass"


def test_hourly_windows_that_never_let_neon_suspend_breach_the_limit() -> None:
    # The negative case: always-on compute (60 min per window) is 186 CU-h and must fail.
    result = project_budget(
        active_hours_per_run=Decimal("1"), runs_per_month=_HOURLY_RUNS, cu=Decimal("0.25")
    )
    assert result["compute_status"] == "fail"
