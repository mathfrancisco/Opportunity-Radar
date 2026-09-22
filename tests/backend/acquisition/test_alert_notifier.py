"""The alert channel is optional, and the absence of one is configuration, not an error."""

from __future__ import annotations

import pytest

from opportunity_radar.acquisition.alerts import (
    WebhookNotifier,
    build_source_alert_notifier,
)


@pytest.mark.parametrize("value", ["", "   ", None])
def test_an_empty_webhook_builds_no_notifier(value: str | None) -> None:
    assert build_source_alert_notifier(value) is None


def test_a_configured_webhook_builds_a_notifier() -> None:
    notifier = build_source_alert_notifier(" https://example.com/hook ", timeout_seconds=2)

    assert notifier == WebhookNotifier("https://example.com/hook", timeout_seconds=2)


def test_an_unreachable_webhook_reports_a_rejection_instead_of_raising() -> None:
    # Port 0 cannot be connected to, which is the shape of every channel outage: the
    # notifier answers "not delivered" so the caller can record it and move on.
    notifier = WebhookNotifier("http://127.0.0.1:0/hook", timeout_seconds=0.1)

    assert notifier.send({"event": "source_alert"}) is False
