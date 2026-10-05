"""`robots_allows`: the product's own User-Agent, RFC 9309 outcomes; fetch stubbed, no network."""

from __future__ import annotations

import httpx
import pytest

from opportunity_radar.companies import discovery
from opportunity_radar.companies.discovery import DEFAULT_USER_AGENT, robots_allows

_URL = "https://example.com/careers"


def _stub(
    monkeypatch: pytest.MonkeyPatch, handler: httpx.Response | Exception
) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    def fake(robots_url: str, user_agent: str) -> httpx.Response:
        calls.append((robots_url, user_agent))
        if isinstance(handler, Exception):
            raise handler
        return handler

    monkeypatch.setattr(discovery, "_fetch_robots", fake)
    return calls


def test_robots_request_carries_the_product_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")

    def get_via_mock(url: str, **kwargs: object) -> httpx.Response:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return client.get(url, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "get", get_via_mock)
    assert robots_allows(_URL) is True
    assert str(sent[0].url) == "https://example.com/robots.txt"
    assert sent[0].headers["User-Agent"] == DEFAULT_USER_AGENT


def test_site_blocking_the_default_agent_is_evaluated_from_its_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake(robots_url: str, user_agent: str) -> httpx.Response:
        if user_agent == DEFAULT_USER_AGENT:
            return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
        return httpx.Response(403)

    monkeypatch.setattr(discovery, "_fetch_robots", fake)
    assert robots_allows(_URL) is True
    assert robots_allows("https://example.com/private/x") is False


def test_disallow_for_star_blocks_that_path_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(monkeypatch, httpx.Response(200, text="User-agent: *\nDisallow: /careers\n"))
    assert robots_allows("https://example.com/careers") is False
    assert robots_allows("https://example.com/jobs") is True


def test_group_for_the_product_token_overrides_star(monkeypatch: pytest.MonkeyPatch) -> None:
    text = (
        "User-agent: *\nDisallow: /\n\n"
        "User-agent: OpportunityRadarDiscoveryBot\nDisallow: /admin\n"
    )
    _stub(monkeypatch, httpx.Response(200, text=text))
    assert robots_allows("https://example.com/careers") is True
    assert robots_allows("https://example.com/admin") is False


@pytest.mark.parametrize("status", [404, 410, 400])
def test_missing_robots_means_no_restrictions(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    _stub(monkeypatch, httpx.Response(status))
    assert robots_allows(_URL) is True


@pytest.mark.parametrize("status", [500, 502, 503])
def test_server_errors_mean_disallowed(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    _stub(monkeypatch, httpx.Response(status))
    assert robots_allows(_URL) is False


def test_timeout_and_network_errors_mean_disallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(monkeypatch, httpx.ReadTimeout("slow"))
    assert robots_allows(_URL) is False
    _stub(monkeypatch, httpx.ConnectError("down"))
    assert robots_allows(_URL) is False


@pytest.mark.parametrize("status", [401, 403])
def test_unauthorized_or_forbidden_robots_stays_disallowed(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    _stub(monkeypatch, httpx.Response(status))
    assert robots_allows(_URL) is False
