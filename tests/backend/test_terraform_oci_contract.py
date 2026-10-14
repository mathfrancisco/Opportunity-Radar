import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TF_DIR = Path(os.environ.get("OCI_TF_DIR", ROOT / "infra" / "terraform" / "oci"))


def _read(name: str) -> str:
    return (TF_DIR / name).read_text(encoding="utf-8")


def _all_tf() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(TF_DIR.glob("*.tf")))


def _variable_block(name: str) -> str:
    match = re.search(rf'variable "{name}" \{{(.*?)\n\}}', _read("variables.tf"), re.S)
    assert match, f"variable {name} not found"
    return match.group(1)


def _default(name: str) -> str:
    match = re.search(r"^\s*default\s*=\s*(.+?)\s*$", _variable_block(name), re.M)
    assert match, f"variable {name} has no default"
    return match.group(1).strip('"')


def _ingress_rules() -> dict[str, str]:
    text = _all_tf()
    rules: dict[str, str] = {}
    pattern = r'resource "oci_core_network_security_group_security_rule" "(\w+)" \{(.*?)\n\}'
    for name, body in re.findall(pattern, text, re.S):
        if re.search(r'direction\s*=\s*"INGRESS"', body):
            rules[name] = body
    return rules


def test_instance_shape_is_a1_flex_within_always_free_limits() -> None:
    compute = _read("compute.tf")

    assert re.search(r"shape\s*=\s*var\.instance_shape\b", compute)
    assert _default("instance_shape") == "VM.Standard.A1.Flex"
    assert 'var.instance_shape == "VM.Standard.A1.Flex"' in _variable_block("instance_shape")
    assert float(_default("shape_ocpus")) <= 2
    assert float(_default("shape_memory_in_gbs")) <= 12
    assert "var.shape_ocpus <= 2" in _variable_block("shape_ocpus")
    assert "var.shape_memory_in_gbs <= 12" in _variable_block("shape_memory_in_gbs")
    assert "var.shape_ocpus <= 2 && var.shape_memory_in_gbs <= 12" in compute


def test_boot_volume_is_fixed_at_50_gb() -> None:
    assert _default("boot_volume_size_gbs") == "50"
    assert "var.boot_volume_size_gbs == 50" in _variable_block("boot_volume_size_gbs")
    assert re.search(
        r"boot_volume_size_in_gbs\s*=\s*var\.boot_volume_size_gbs\b", _read("compute.tf")
    )


def test_public_ingress_is_only_web_ports_and_admin_scoped_ssh() -> None:
    rules = _ingress_rules()

    assert set(rules) == {"http", "https", "ssh_admin"}
    ports: dict[str, tuple[str, str]] = {}
    for name, body in rules.items():
        assert re.search(r'protocol\s*=\s*"6"', body), name
        match = re.search(r"min\s*=\s*(\d+)\s*\n\s*max\s*=\s*(\d+)", body)
        assert match, name
        ports[name] = (match.group(1), match.group(2))
    assert ports == {"http": ("80", "80"), "https": ("443", "443"), "ssh_admin": ("22", "22")}

    assert re.search(r'source\s*=\s*"0\.0\.0\.0/0"', rules["http"])
    assert re.search(r'source\s*=\s*"0\.0\.0\.0/0"', rules["https"])
    ssh = rules["ssh_admin"]
    assert re.search(r"source\s*=\s*var\.admin_cidr\b", ssh)
    assert "0.0.0.0/0" not in ssh
    assert "::/0" not in ssh


def test_no_other_ingress_path_or_database_ports_are_opened() -> None:
    text = _all_tf()

    assert "ingress_security_rules" not in text
    for body in _ingress_rules().values():
        assert not re.search(r"\b(5432|6379)\b", body)
    assert "::/0" not in text
    assert "admin_cidr" in _read("variables.tf")


def test_no_remote_backend_nat_load_balancer_or_database_resources() -> None:
    text = _all_tf()

    assert not re.search(r"^\s*backend\s+\"", text, re.M)
    forbidden = (
        "oci_core_nat_gateway",
        "oci_core_service_gateway",
        "oci_load_balancer",
        "oci_network_load_balancer",
        "oci_database_",
        "oci_mysql_",
        "oci_psql_",
        "oci_redis_",
        "oci_nosql_",
    )
    resources = set(re.findall(r'^\s*resource\s+"(\w+)"', text, re.M))
    for prefix in forbidden:
        assert not [name for name in resources if name.startswith(prefix)], prefix
