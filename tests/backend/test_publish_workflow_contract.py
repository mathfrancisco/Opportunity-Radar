from pathlib import Path

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
