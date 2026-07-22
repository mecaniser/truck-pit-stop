from app.core.request_activity import RequestActivityWindow


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_request_activity_reports_a_rolling_window_and_ignores_monitoring_routes():
    clock = Clock()
    activity = RequestActivityWindow(window_seconds=300, clock=clock)

    activity.record("/health/ready", 5, 200)
    activity.record("/api/v1/admin/performance/stats", 5, 200)
    activity.record("/api/v1/customers", 100, 200)
    clock.now = 60
    activity.record("/api/v1/repair-orders", 400, 404)

    assert activity.snapshot() == {
        "window_seconds": 300,
        "observed_seconds": 60,
        "request_count": 2,
        "requests_per_minute": 2.0,
        "p95_latency_ms": 400,
        "error_rate_percent": 50.0,
        "error_count": 1,
        "client_error_rate_percent": 50.0,
        "server_error_rate_percent": 0.0,
    }


def test_request_activity_discards_samples_outside_the_window():
    clock = Clock()
    activity = RequestActivityWindow(window_seconds=300, clock=clock)
    activity.record("/api/v1/customers", 100, 200)
    clock.now = 301

    assert activity.snapshot()["request_count"] == 0
