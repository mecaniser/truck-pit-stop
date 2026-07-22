"""Rule evaluation for the in-app local performance dashboard."""
from __future__ import annotations

from typing import Any


MIN_REQUEST_SAMPLES = 10
P95_WARNING_MS = 750
P95_CRITICAL_MS = 1_500
SERVER_ERROR_RATE_CRITICAL = 1.0
CLIENT_ERROR_RATE_WARNING = 15.0


def evaluate_activity_alerts(activity: dict[str, Any]) -> list[dict[str, str]]:
    """Return bounded, operator-facing alerts for a rolling request window."""
    if activity["request_count"] < MIN_REQUEST_SAMPLES:
        return []

    alerts: list[dict[str, str]] = []
    p95_latency = activity["p95_latency_ms"]
    if p95_latency >= P95_CRITICAL_MS:
        alerts.append(_alert(
            "critical",
            "Recent request latency is critical",
            f"P95 is {p95_latency:.0f}ms; investigate routes, database time, and pool pressure.",
        ))
    elif p95_latency >= P95_WARNING_MS:
        alerts.append(_alert(
            "warning",
            "Recent request latency is elevated",
            f"P95 is {p95_latency:.0f}ms; target is below {P95_WARNING_MS}ms.",
        ))

    if activity["server_error_rate_percent"] >= SERVER_ERROR_RATE_CRITICAL:
        alerts.append(_alert(
            "critical",
            "Server errors need attention",
            f"{activity['server_error_rate_percent']:.2f}% of recent requests returned 5xx responses.",
        ))

    if activity["client_error_rate_percent"] >= CLIENT_ERROR_RATE_WARNING:
        alerts.append(_alert(
            "warning",
            "Client errors are elevated",
            f"{activity['client_error_rate_percent']:.2f}% of recent requests returned 4xx responses.",
        ))

    return alerts


def _alert(severity: str, title: str, detail: str) -> dict[str, str]:
    return {"severity": severity, "title": title, "detail": detail}
