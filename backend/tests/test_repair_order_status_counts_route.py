"""The status-counts route must not be shadowed by the id routes.

`/repair-orders/status-counts` is a literal path on a router that also declares
`/repair-orders/{order_id}/...`. FastAPI matches in declaration order, so if the
literal ever moves below a path-parameter route, "status-counts" is parsed as an
order id and the filters lose their counts with a 422 rather than an error that
points at the cause.
"""
from app.main import app


def _repair_order_paths() -> list[str]:
    return [
        route.path
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/v1/repair-orders")
    ]


def test_status_counts_route_is_registered():
    assert any(path.endswith("/repair-orders/status-counts") for path in _repair_order_paths())


def test_status_counts_is_declared_before_any_order_id_route():
    paths = _repair_order_paths()
    literal = next(i for i, p in enumerate(paths) if p.endswith("/repair-orders/status-counts"))
    parameterised = [i for i, p in enumerate(paths) if "/repair-orders/{" in p]
    assert parameterised, "expected id-parameterised repair-order routes to exist"
    assert literal < min(parameterised), (
        "status-counts must be declared before the {order_id} routes or it will be shadowed"
    )
