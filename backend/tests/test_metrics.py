from app.core.metrics import normalize_endpoint_label


def test_normalize_endpoint_label_replaces_uuid_path_segments():
    endpoint = "/api/v1/repair-orders/414dd91f-00da-4faa-9a3e-f3968188e691/parts?limit=10"

    assert normalize_endpoint_label(endpoint) == "/api/v1/repair-orders/:id/parts"


def test_normalize_endpoint_label_keeps_static_path():
    assert normalize_endpoint_label("/api/v1/dashboard/stats") == "/api/v1/dashboard/stats"
