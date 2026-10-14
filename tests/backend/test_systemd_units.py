from __future__ import annotations

import configparser
import os
import re
import shutil
import subprocess
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SYSTEMD = ROOT / "infra" / "systemd"
SERVICE = SYSTEMD / "opportunity-radar-pipeline.service"
TIMER = SYSTEMD / "opportunity-radar-pipeline.timer"
WRAPPER = SYSTEMD / "run-opportunity-radar-window"


def _unit(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read(path, encoding="utf-8")
    return parser


def _seconds(value: str) -> int:
    units = {"s": 1, "min": 60, "h": 3600, "d": 86400}
    for suffix, multiplier in units.items():
        if value.endswith(suffix):
            return int(value[: -len(suffix)]) * multiplier
    return int(value)


def test_service_has_finite_oneshot_contract() -> None:
    service = _unit(SERVICE)

    assert service["Service"]["Type"] == "oneshot"
    assert service["Service"]["Restart"] == "no"
    assert service["Service"]["KillSignal"] == "SIGTERM"
    assert service["Unit"]["Requires"] == "docker.service"
    assert service["Unit"]["After"] == "docker.service network-online.target"
    assert service["Service"]["User"] == "opportunity-radar"
    assert service["Service"]["WorkingDirectory"] == "/opt/opportunity-radar"
    assert service["Service"]["EnvironmentFile"] == "/etc/opportunity-radar/pipeline.env"
    assert service["Service"]["ExecStart"] == "/usr/local/sbin/run-opportunity-radar-window"

    for key, value in service["Service"].items():
        if key == "Environment" or key.startswith("Environment"):
            assert not any(
                secret in value.upper() for secret in ("DATABASE_URL", "CLERK", "TOKEN", "KEY")
            )


def test_timer_is_explicit_utc_non_catchup_and_installed() -> None:
    timer = _unit(TIMER)

    assert timer["Timer"]["OnCalendar"].endswith(" UTC")
    assert timer["Timer"]["RandomizedDelaySec"]
    assert timer["Timer"]["Unit"] == "opportunity-radar-pipeline.service"
    assert timer["Timer"]["Persistent"].lower() == "false"
    assert timer["Install"]["WantedBy"] == "timers.target"


def test_timing_contract_is_runner_less_than_service_less_than_schedule_window() -> None:
    service = _unit(SERVICE)["Service"]
    timer = _unit(TIMER)["Timer"]
    wrapper = WRAPPER.read_text(encoding="utf-8")
    default_window = int(
        next(
            line.split("=", 1)[1]
            for line in wrapper.splitlines()
            if line.startswith("DEFAULT_WINDOW_SECONDS=")
        )
    )
    runner_deadline = default_window
    service_timeout = _seconds(service["TimeoutStartSec"])
    randomized_delay = _seconds(timer["RandomizedDelaySec"])
    calendar = timer["OnCalendar"]
    match = re.fullmatch(r"\*-\*-\* (\d{2}):(\d{2}):(\d{2}) UTC", calendar)
    assert match, f"unsupported OnCalendar form: {calendar!r}"
    scheduled_time = time(*(int(value) for value in match.groups()))
    first = datetime.combine(datetime(2026, 1, 1), scheduled_time, tzinfo=timezone.utc)
    second = first + timedelta(days=1)
    schedule_window = int((second - first).total_seconds()) - randomized_delay

    assert runner_deadline < service_timeout < schedule_window


@pytest.mark.skipif(shutil.which("sh") is None, reason="POSIX sh is required")
def test_wrapper_runs_runner_once_with_run_id_and_future_deadline(tmp_path: Path) -> None:
    log = tmp_path / "runner.log"
    stub = tmp_path / "runner.sh"
    stub.write_text(
        "#!/bin/sh\n"
        "printf 'RUN_ID=%s\\nDEADLINE_UTC=%s\\n' \"$RUN_ID\" \"$DEADLINE_UTC\" >> \"$RUN_LOG\"\n"
        "printf 'PIPELINE_DEADLINE_SECONDS=%s\\n' \"$PIPELINE_DEADLINE_SECONDS\" >> \"$RUN_LOG\"\n"
        "for argument in \"$@\"; do printf 'ARG=%s\\n' \"$argument\" >> \"$RUN_LOG\"; done\n",
        encoding="utf-8",
    )
    stub.chmod(0o700)

    env = os.environ.copy()
    env.update(
        {
            "PIPELINE_WINDOW_SECONDS": "60",
            "PIPELINE_COMPOSE_BIN": str(stub),
            "RUN_LOG": str(log),
        }
    )
    result = subprocess.run(
        ["sh", str(WRAPPER)], env=env, text=True, capture_output=True, check=False
    )

    assert result.returncode == 0, result.stderr
    lines = log.read_text(encoding="utf-8").splitlines()
    values = dict(
        line.split("=", 1) for line in lines if "=" in line and not line.startswith("ARG=")
    )
    arguments = [line.removeprefix("ARG=") for line in lines if line.startswith("ARG=")]
    assert values["RUN_ID"]
    deadline = datetime.fromisoformat(values["DEADLINE_UTC"].replace("Z", "+00:00"))
    assert deadline > datetime.now(timezone.utc)
    assert values["PIPELINE_DEADLINE_SECONDS"] == "60"
    assert arguments == [
        "compose",
        "--project-name",
        "opportunity-radar",
        "-f",
        "/opt/opportunity-radar/compose.cloud.yaml",
        "run",
        "--rm",
        "-e",
        "RUN_ID",
        "-e",
        "DEADLINE_UTC",
        "worker",
    ]


@pytest.mark.skipif(shutil.which("sh") is None, reason="POSIX sh is required")
@pytest.mark.parametrize("window", ["abc", "1.5", "-1"])
def test_wrapper_rejects_non_positive_or_non_integer_window(window: str, tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PIPELINE_WINDOW_SECONDS"] = window

    result = subprocess.run(
        ["sh", str(WRAPPER)], env=env, text=True, capture_output=True, check=False
    )

    assert result.returncode == 2


@pytest.mark.skipif(shutil.which("sh") is None, reason="POSIX sh is required")
def test_wrapper_returns_runner_exit_code(tmp_path: Path) -> None:
    stub = tmp_path / "compose.sh"
    stub.write_text("#!/bin/sh\nexit 17\n", encoding="utf-8")
    stub.chmod(0o700)
    env = os.environ.copy()
    env["PIPELINE_COMPOSE_BIN"] = str(stub)

    result = subprocess.run(
        ["sh", str(WRAPPER)], env=env, text=True, capture_output=True, check=False
    )

    assert result.returncode == 17


def test_systemd_analyze_verify_when_available(tmp_path: Path) -> None:
    if shutil.which("systemd-analyze") is None:
        pytest.skip("systemd-analyze is not installed")
    service_copy = tmp_path / SERVICE.name
    timer_copy = service_copy.with_name(TIMER.name)
    service_copy.write_text(
        SERVICE.read_text(encoding="utf-8").replace(
            "ExecStart=/usr/local/sbin/run-opportunity-radar-window",
            f"ExecStart={WRAPPER}",
        ),
        encoding="utf-8",
    )
    timer_copy.write_text(TIMER.read_text(encoding="utf-8"), encoding="utf-8")
    service_copy.chmod(0o644)
    timer_copy.chmod(0o644)
    result = subprocess.run(
        ["systemd-analyze", "verify", "--man=no", str(service_copy), str(timer_copy)],
        text=True,
        capture_output=True,
        check=False,
    )
    # A CI container may lack Docker, the dedicated service user, or the root-only env file.
    known_host_diagnostics = (
        "Unit docker.service not found",
        "Failed to determine user credentials",
        "Failed at step USER",
        "EnvironmentFile=/etc/opportunity-radar/pipeline.env not found",
        "Failed to load environment files",
    )
    diagnostics = [line for line in result.stderr.splitlines() if line.strip()]
    unexpected = [
        line
        for line in diagnostics
        if not any(fragment in line for fragment in known_host_diagnostics)
    ]
    assert not unexpected, "\n".join(unexpected)
    assert "run-opportunity-radar-window is not executable" not in result.stderr
