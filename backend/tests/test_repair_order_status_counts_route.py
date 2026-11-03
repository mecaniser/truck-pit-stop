"""The status-counts route must not be shadowed by the id routes.

`/repair-orders/status-counts` is a literal path on a router that also declares
`/repair-orders/{order_id}/...`. FastAPI matches in declaration order, so if the
literal ever moves below a path-parameter route, "status-counts" is parsed as an
order id and the filters lose their counts with a 422 rather than an error that
points at the cause.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.main import app
from app.api.v1.endpoints.repair_orders import repair_order_status_counts
from app.db.models.user import UserRole


def test_status_counts_route_is_registered():
    paths = app.openapi()["paths"]
    assert "get" in paths["/api/v1/repair-orders/status-counts"]
    assert any("/repair-orders/{" in path for path in paths), "expected id-parameterised routes to exist"


@pytest.mark.asyncio
async def test_status_counts_dispatches_before_any_order_id_route():
    """A literal request must reach counts, not UUID validation on an ID route."""
    import httpx
    from app.core.dependencies import get_current_active_user
    from app.db.session import get_db

    class Result:
        def one(self):
            return (5, 5)

        def all(self):
            return [("invoiced", 3), ("paid", 2)]

    class DB:
        async def execute(self, _statement):
            return Result()

    async def database():
        yield DB()

    current_user = SimpleNamespace(role=UserRole.GARAGE_OWNER, tenant_id=uuid4())
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_active_user] = lambda: current_user
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/repair-orders/status-counts")
        assert response.status_code == 200
        assert response.json() == {"invoiced": 3, "paid": 2, "all": 5}
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.mark.asyncio
async def test_status_counts_uses_the_projection_primary_key():
    class Result:
        def one(self):
            return (5, 5)

        def all(self):
            return [("invoiced", 3), ("paid", 2)]

    class DB:
        async def execute(self, _statement):
            return Result()

    counts = await repair_order_status_counts(
        customer_id=None,
        vehicle_id=None,
        search=None,
        deleted=False,
        db=DB(),
        current_user=SimpleNamespace(
            role=UserRole.GARAGE_OWNER,
            tenant_id=uuid4(),
        ),
    )
    assert counts == {"invoiced": 3, "paid": 2, "all": 5}
