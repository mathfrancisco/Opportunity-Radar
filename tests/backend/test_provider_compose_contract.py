from pathlib import Path

import yaml

from opportunity_radar.platform.ai.providers.registry import PROVIDERS
from opportunity_radar.platform.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def _provider_variables() -> list[str]:
    names = [
        f"{spec.name}_{suffix}" for spec in PROVIDERS for suffix in ("api_key", "base_url", "models")
    ]
    return [*names, "cloudflare_account_id", "ai_reserve_order", "ai_provider_limits"]


def _compose_environments() -> dict[str, dict[str, str]]:
    cloud = yaml.safe_load((ROOT / "compose.cloud.yaml").read_text(encoding="utf-8"))
    local = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    return {
        "compose.cloud.yaml": cloud["x-runtime-environment"],
        "compose.yaml": local["x-app-environment"],
    }


def test_every_provider_registry_setting_exists_on_settings() -> None:
    for name in _provider_variables():
        assert name in Settings.model_fields, name


def test_provider_variables_reach_both_compose_environments() -> None:
    for file_name, environment in _compose_environments().items():
        for name in _provider_variables():
            assert name.upper() in environment, f"{name.upper()} missing in {file_name}"


def test_provider_variable_defaults_match_settings() -> None:
    for environment in _compose_environments().values():
        for name in _provider_variables():
            default = "{}" if name == "ai_provider_limits" else Settings.model_fields[name].default
            if name.endswith("_api_key"):
                default = ""
            assert environment[name.upper()] == "${" + f"{name.upper()}:-{default}" + "}", name
