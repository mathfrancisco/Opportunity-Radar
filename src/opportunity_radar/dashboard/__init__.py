"""Read models for the dashboard.

Section 9.4 of docs/06-estrutura-projeto-mvp.md: dashboard screens read through query
services built on optimised SQL, not by loading aggregates. Nothing here writes, and no
other context depends on this module — it is the join point the screens need, kept out
of the domain repositories so those stay about one aggregate each.
"""

from opportunity_radar.dashboard.queries import (
    InboxItem,
    InboxOrder,
    InboxPage,
    InboxQuery,
    OverviewSummary,
    SourceHealth,
    list_opportunity_inbox,
    list_source_health,
    summarize_overview,
)

__all__ = [
    "InboxItem",
    "InboxOrder",
    "InboxPage",
    "InboxQuery",
    "OverviewSummary",
    "SourceHealth",
    "list_opportunity_inbox",
    "list_source_health",
    "summarize_overview",
]
