from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_cloud_runtime_images_are_validated_before_tags_are_published() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "pipeline.yml").read_text())
    publish = workflow["jobs"]["publish"]
    entries = publish["strategy"]["matrix"]["include"]
    cloud_entries = [entry for entry in entries if entry["cloud_runtime"]]

    assert {entry["image"] for entry in cloud_entries} == {"api", "worker", "proxy"}
    assert all(entry["dockerfile"] for entry in cloud_entries)

    steps = publish["steps"]
    first_run = next(step for step in steps if "run" in step)
    assert first_run["name"] == "Block image publication until owner-scoped API is proven"
    assert first_run["run"] == "python scripts/check_tenancy_release_gate.py"

    qemu = next(
        step for step in steps if step["name"] == "Set up QEMU for cloud runtime images"
    )
    assert qemu["uses"].startswith("docker/setup-qemu-action@")
    assert len(qemu["uses"].partition("@")[2]) == 40

    build_index = next(
        index
        for index, step in enumerate(steps)
        if step["name"] == "Build and push cloud image by digest"
    )
    inspect_index = next(
        index for index, step in enumerate(steps) if step["name"] == "Inspect cloud image manifest"
    )
    validate_index = next(
        index
        for index, step in enumerate(steps)
        if step["name"] == "Validate cloud image digest and arm64 manifest"
    )
    tag_index = next(
        index for index, step in enumerate(steps) if step["name"] == "Tag validated cloud image"
    )
    assert build_index < inspect_index < validate_index < tag_index

    build = steps[build_index]
    assert "tags" not in build["with"]
    assert build["with"]["platforms"] == "linux/amd64,linux/arm64"
    assert "push-by-digest=true" in build["with"]["outputs"]
    assert "name-canonical=true" in build["with"]["outputs"]
    assert "validate_cloud_images.py" in steps[validate_index]["run"]
    assert "imagetools create" in steps[tag_index]["run"]


def test_backend_quality_validates_offline_cloud_manifest_contracts_without_gate() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "pipeline.yml").read_text(encoding="utf-8")
    )
    backend_quality = workflow["jobs"]["backend-quality"]

    needs = backend_quality.get("needs", [])
    needs = [needs] if isinstance(needs, str) else needs
    assert "publish" not in needs
    assert not backend_quality.get("if")

    steps = backend_quality["steps"]
    step = next(
        (s for s in steps if s.get("name") == "Validate offline cloud manifest contracts"),
        None,
    )
    assert (
        step is not None
    ), "Validate offline cloud manifest contracts step not found in backend-quality job"

    run_cmd = step.get("run", "")
    assert "tests/backend/test_cloud_image_preflight_cli.py" in run_cmd
    assert "if" not in step
    assert "continue-on-error" not in step

    step_names = [s.get("name") for s in steps]
    install_index = step_names.index("Install backend tooling")
    validate_index = step_names.index("Validate offline cloud manifest contracts")
    assert install_index < validate_index


def test_e2e_is_independent_and_publish_requires_every_validation_gate() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "pipeline.yml").read_text(encoding="utf-8")
    )
    e2e = workflow["jobs"]["e2e"]
    publish = workflow["jobs"]["publish"]

    assert "needs" not in e2e
    assert set(publish["needs"]) == {
        "backend-quality",
        "backend-tests",
        "frontend",
        "terraform-static",
        "e2e",
    }
    publish_gate = str(publish["if"])
    for job in publish["needs"]:
        assert f"needs.{job}.result == 'success'" in publish_gate

    assert _publication_gate_allows(
        publish_gate,
        {job: "success" for job in publish["needs"]},
        event_name="push",
        ref="refs/heads/main",
        publish_input=False,
    )
    assert not _publication_gate_allows(
        publish_gate,
        {job: "success" for job in publish["needs"]},
        event_name="pull_request",
        ref="refs/pull/123/merge",
        publish_input=False,
    )


@pytest.mark.parametrize("failed_result", ["failure", "skipped"])
@pytest.mark.parametrize(
    "job", ["backend-quality", "backend-tests", "frontend", "terraform-static", "e2e"]
)
def test_publish_gate_refuses_each_failed_or_skipped_validation(
    failed_result: str, job: str
) -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "pipeline.yml").read_text(encoding="utf-8")
    )
    publish = workflow["jobs"]["publish"]
    results = {required_job: "success" for required_job in publish["needs"]}
    results[job] = failed_result

    assert not _publication_gate_allows(
        str(publish["if"]),
        results,
        event_name="push",
        ref="refs/heads/main",
        publish_input=False,
    )


def _publication_gate_allows(
    condition: str,
    results: dict[str, str],
    *,
    event_name: str,
    ref: str,
    publish_input: bool,
) -> bool:
    expression = condition
    for job, result in results.items():
        expression = expression.replace(
            f"needs.{job}.result == 'success'", str(result == "success")
        )
    expression = expression.replace(
        "startsWith(github.ref, 'refs/tags/v')", str(ref.startswith("refs/tags/v"))
    )
    expression = expression.replace(
        "github.event_name == 'push'", str(event_name == "push")
    ).replace(
        "github.event_name == 'workflow_dispatch'", str(event_name == "workflow_dispatch")
    )
    expression = expression.replace(
        "github.ref == 'refs/heads/main'", str(ref == "refs/heads/main")
    )
    expression = expression.replace("inputs.publish", str(publish_input))
    expression = expression.replace("&&", " and ").replace("||", " or ")
    return bool(eval(expression, {"__builtins__": {}}, {}))


def test_backend_test_cache_tracks_both_requirement_files_and_reports_slowest_tests() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "pipeline.yml").read_text(encoding="utf-8")
    )
    backend_tests = workflow["jobs"]["backend-tests"]
    setup_python = next(
        step for step in backend_tests["steps"] if step.get("name") == "Set up Python"
    )
    assert setup_python["with"]["cache-dependency-path"].splitlines() == [
        "requirements.txt",
        "requirements-dev.txt",
    ]
    run_tests = next(
        step for step in backend_tests["steps"] if step.get("name") == "Run backend tests"
    )
    assert run_tests["run"] == "pytest -q --durations=15"
    assert all(
        step.get("name") != "Smoke the fail-closed production factory offline"
        for step in backend_tests["steps"]
    )


def test_e2e_restart_proves_new_completed_worker_passes_before_idempotency_assertions() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "pipeline.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["e2e"]["steps"]
    restart = next(
        step
        for step in steps
        if step.get("name") == "Verify the autonomous cycle without a terminal"
    )
    run = restart["run"]

    assert "$compose stop worker" in run
    assert "$compose start worker" in run
    assert 'restart_after="$(count_rows "SELECT extract(epoch FROM clock_timestamp())")"' in run
    assert "platform.worker_pass_history" in run
    assert "finished_at IS NOT NULL AND success" in run
    assert "sleep 150" not in run
