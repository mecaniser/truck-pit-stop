from app.core.performance_alerts import evaluate_activity_alerts


def test_alerts_require_enough_samples_to_be_actionable():
    assert evaluate_activity_alerts({
        "request_count": 9,
        "p95_latency_ms": 5_000,
        "server_error_rate_percent": 50,
        "client_error_rate_percent": 50,
    }) == []


def test_alerts_report_slow_requests_and_server_errors():
    alerts = evaluate_activity_alerts({
        "request_count": 20,
        "p95_latency_ms": 1_600,
        "server_error_rate_percent": 2.5,
        "client_error_rate_percent": 0,
    })

    assert [alert["severity"] for alert in alerts] == ["critical", "critical"]
    assert alerts[0]["title"] == "Recent request latency is critical"
    assert alerts[1]["title"] == "Server errors need attention"
