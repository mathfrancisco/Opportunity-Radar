"""F48-19: the central list of platforms the project never collects from."""

from __future__ import annotations

import pytest

from opportunity_radar.acquisition.forbidden import (
    FORBIDDEN_PLATFORMS,
    forbidden_platform_for_url,
    forbidden_platform_in,
    is_forbidden_url,
)
from opportunity_radar.acquisition.startup_discovery import is_allowed_ats_url
from opportunity_radar.dashboard.funnel import FORBIDDEN_HOSTS


def test_list_names_every_forbidden_platform() -> None:
    assert {platform.name for platform in FORBIDDEN_PLATFORMS} == {
        "Gupy",
        "Wellfound",
        "YC / Work at a Startup",
        "Careerflow",
        "Crossover",
        "Braintrust",
        "Landing.jobs",
    }
    assert all(platform.hosts and platform.reason for platform in FORBIDDEN_PLATFORMS)


def test_braintrust_is_excluded_for_lack_of_an_endpoint_not_for_terms() -> None:
    braintrust = forbidden_platform_for_url("https://app.usebraintrust.com/jobs/")
    assert braintrust is not None
    assert braintrust.reason == "sem endpoint estruturado (F20-56)"
    assert "termos" not in braintrust.reason


@pytest.mark.parametrize(
    "url",
    [
        "https://acme.gupy.io/",
        "https://GUPY.io/vagas",
        "https://wellfound.com/company/acme",
        "https://www.workatastartup.com/jobs/1",
        "https://www.ycombinator.com/jobs/acme",
        "https://careerflow.ai/x",
        "https://app.crossover.com/",
        "https://landing.jobs/at/acme",
        "acme.gupy.io/vagas",
    ],
)
def test_forbidden_urls_are_detected(url: str) -> None:
    assert is_forbidden_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://news.ycombinator.com/item?id=1",
        "https://www.ycombinator.com/companies",
        "https://jobs.ashbyhq.com/acme",
        "https://notgupy.io.example.com/",
        "",
    ],
)
def test_other_urls_are_not_forbidden(url: str) -> None:
    assert not is_forbidden_url(url)


def test_configuration_scan_finds_nested_hosts_only() -> None:
    assert forbidden_platform_in({"a": {"b": ["see https://acme.gupy.io/x"]}}) is not None
    assert forbidden_platform_in({"company_name": "Gupy Labs", "note": "Node.js"}) is None


def test_funnel_guard_and_startup_discovery_use_the_central_list() -> None:
    assert "gupy.io" in FORBIDDEN_HOSTS
    assert "www.ycombinator.com/jobs" in FORBIDDEN_HOSTS
    assert not is_allowed_ats_url("https://wellfound.com/company/acme")
