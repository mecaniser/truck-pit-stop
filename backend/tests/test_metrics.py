from app.core.metrics import normalize_endpoint_label
from app.core.metrics_parser import _parse_http_metrics


def test_normalize_endpoint_label_replaces_uuid_path_segments():
    endpoint = "/api/v1/repair-orders/414dd91f-00da-4faa-9a3e-f3968188e691/parts?limit=10"

    assert normalize_endpoint_label(endpoint) == "/api/v1/repair-orders/:id/parts"


def test_normalize_endpoint_label_keeps_static_path():
    assert normalize_endpoint_label("/api/v1/dashboard/stats") == "/api/v1/dashboard/stats"


def test_http_metrics_aggregate_histograms_and_keep_endpoint_latency_separate():
    metrics = {
        "dieselbridge_http_request_duration_seconds": {
            "type": "histogram",
            "samples": [
                {"name": "dieselbridge_http_request_duration_seconds_bucket", "labels": {"handler": "/customers", "le": "0.1"}, "value": 8},
                {"name": "dieselbridge_http_request_duration_seconds_bucket", "labels": {"handler": "/customers", "le": "1.0"}, "value": 10},
                {"name": "dieselbridge_http_request_duration_seconds_count", "labels": {"handler": "/customers"}, "value": 10},
                {"name": "dieselbridge_http_request_duration_seconds_sum", "labels": {"handler": "/customers"}, "value": 1.4},
                {"name": "dieselbridge_http_request_duration_seconds_bucket", "labels": {"handler": "/repair-orders", "le": "0.1"}, "value": 1},
                {"name": "dieselbridge_http_request_duration_seconds_bucket", "labels": {"handler": "/repair-orders", "le": "1.0"}, "value": 10},
                {"name": "dieselbridge_http_request_duration_seconds_count", "labels": {"handler": "/repair-orders"}, "value": 10},
                {"name": "dieselbridge_http_request_duration_seconds_sum", "labels": {"handler": "/repair-orders"}, "value": 5.0},
            ],
        }
    }

    result = _parse_http_metrics(metrics)

    assert result["avg_latency_ms"] == 320.0
    assert result["p95_latency_ms"] == 918.18
    assert result["slowest_endpoints"][0] == {
        "path": "/repair-orders",
        "requests": 10,
        "avg_latency_ms": 500.0,
        "p95_latency_ms": 950.0,
    }


def test_http_metrics_prefer_the_route_labeled_histogram():
    metrics = {
        "dieselbridge_http_endpoint_duration_seconds": {
            "type": "histogram",
            "samples": [
                {"name": "dieselbridge_http_endpoint_duration_seconds_bucket", "labels": {"endpoint": "/customers", "le": "0.1"}, "value": 9},
                {"name": "dieselbridge_http_endpoint_duration_seconds_bucket", "labels": {"endpoint": "/customers", "le": "1.0"}, "value": 10},
                {"name": "dieselbridge_http_endpoint_duration_seconds_count", "labels": {"endpoint": "/customers"}, "value": 10},
                {"name": "dieselbridge_http_endpoint_duration_seconds_sum", "labels": {"endpoint": "/customers"}, "value": 1.0},
            ],
        },
        "dieselbridge_http_http_request_duration_seconds": {
            "type": "histogram",
            "samples": [],
        },
    }

    result = _parse_http_metrics(metrics)

    assert result["slowest_endpoints"] == [{
        "path": "/customers",
        "requests": 10,
        "avg_latency_ms": 100.0,
        "p95_latency_ms": 550.0,
    }]
