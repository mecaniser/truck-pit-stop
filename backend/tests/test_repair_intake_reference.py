from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.services import repair_intake_reference as service
from app.core.webhook_destination import ResolvedWebhookDestination
from app.schemas.repair_order import RepairOrderCreate


def tenant(**changes):
    return SimpleNamespace(**{
        "id": uuid4(), "paid_invoice_webhook_enabled": True,
        "paid_invoice_webhook_delivery_paused": False,
        "paid_invoice_webhook_url": "https://elis.example/events/shop-outcome",
        "paid_invoice_webhook_secret_encrypted": "encrypted", **changes,
    })


@pytest.mark.parametrize("url", ["http://elis.example/events/shop-outcome", "https://evil@elis.example/events/shop-outcome", "https://elis.example/other", "https://elis.example/events/shop-outcome?token=x"])
def test_url_is_derived_only_from_supported_configuration(url):
    with pytest.raises(HTTPException) as error:
        service.intake_url(tenant(paid_invoice_webhook_url=url), "candidates")
    assert error.value.status_code == 409


def test_disabled_connection_and_valid_url():
    with pytest.raises(HTTPException):
        service.intake_url(tenant(paid_invoice_webhook_enabled=False), "reserve")
    assert service.intake_url(tenant(), "reserve") == "https://elis.example/events/repair-intake/reserve"


def test_reference_bound_and_optional():
    ids = {"customer_id": uuid4(), "vehicle_id": uuid4()}
    assert RepairOrderCreate(**ids).originating_call_reference is None
    with pytest.raises(ValidationError):
        RepairOrderCreate(**ids, originating_call_reference="x" * 4097)


@pytest.mark.asyncio
async def test_signed_request_pins_address_and_exposes_only_options(monkeypatch):
    from app.services.paid_invoice_webhook_service import verify_conversion_signature
    observed = []
    def handler(request):
        observed.append(request)
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "elis.example"
        assert verify_conversion_signature(secret="test-secret", timestamp=request.headers["X-DieselBridge-Timestamp"],
                                           body=request.content, signature=request.headers["X-DieselBridge-Signature"])
        return httpx.Response(200, json={"options": [], "raw_transcript": "must not escape"})
    real_client = httpx.AsyncClient
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(service, "decrypt_paid_invoice_webhook_secret", lambda _: "test-secret")
    monkeypatch.setattr(service, "resolve_webhook_destination", AsyncMock(return_value=ResolvedWebhookDestination(
        "https://elis.example/events/repair-intake/candidates", "elis.example", "elis.example", ("93.184.216.34",))))
    result = await service.originating_call_options(tenant(), "+17045550123")
    assert result.model_dump() == {"options": []}
    assert len(observed) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [302, 401, 500, 409])
async def test_errors_are_sanitized_and_redirects_not_followed(monkeypatch, status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="secret provider detail", headers={"location": "https://private.example"})
    real_client = httpx.AsyncClient
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(service, "decrypt_paid_invoice_webhook_secret", lambda _: "secret")
    monkeypatch.setattr(service, "resolve_webhook_destination", AsyncMock(return_value=ResolvedWebhookDestination(
        "https://elis.example/events/repair-intake/candidates", "elis.example", "elis.example", ("93.184.216.34",))))
    with pytest.raises(HTTPException) as error:
        await service.originating_call_options(tenant(), None)
    assert error.value.status_code == (409 if status == 409 else 502)
    assert "secret" not in error.value.detail
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_options_customer_lookup_is_tenant_scoped(monkeypatch):
    from app.api.v1.endpoints.repair_orders import originating_call_options
    statement = []
    class DB:
        async def execute(self, query):
            statement.append(str(query))
            return SimpleNamespace(scalar_one_or_none=lambda: None)
    remote = AsyncMock()
    monkeypatch.setattr(service, "originating_call_options", remote)
    with pytest.raises(HTTPException) as error:
        await originating_call_options(service.OriginatingCallOptionsRequest(customer_id=uuid4()), DB(),
                                       SimpleNamespace(tenant_id=uuid4()))
    assert error.value.status_code == 404
    assert "customers.tenant_id" in statement[0]
    remote.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["new", "retry", "wrong_customer", "untrusted_ids", "no_selection"])
async def test_create_selection_trusted_ids_and_retry_preservation(monkeypatch, mode):
    from app.api.v1.endpoints import repair_orders as endpoint
    from app.db.models.user import UserRole
    from app.core import unique_id
    shop = tenant()
    customer_id, vehicle_id = uuid4(), uuid4()
    reservation = service.IntakeReservation(repair_order_uuid=uuid4(), elis_opportunity_id=uuid4(), callrail_call_id="CAL-synthetic")
    existing = SimpleNamespace(id=reservation.repair_order_uuid, customer_id=customer_id, vehicle_id=vehicle_id,
                               elis_opportunity_id=reservation.elis_opportunity_id, callrail_call_id=reservation.callrail_call_id)
    if mode == "wrong_customer":
        existing.customer_id = uuid4()
    customer = SimpleNamespace(id=customer_id, is_internal_fleet=False)
    vehicle = SimpleNamespace(id=vehicle_id)
    results = iter([customer, vehicle, False, shop, existing if mode in {"retry", "wrong_customer"} else None])
    class DB:
        def __init__(self):
            self.added = []
            self.queries = []
        async def execute(self, query):
            self.queries.append(str(query))
            result = next(results)
            return SimpleNamespace(scalar_one_or_none=lambda: result, scalar=lambda: result)
        async def get(self, model, key):
            return shop
        def add(self, order):
            self.added.append(order)
        async def refresh(self, order):
            pass
    db = DB()
    reserve = AsyncMock(return_value=reservation)
    monkeypatch.setattr(service, "reserve_originating_call", reserve)
    monkeypatch.setattr(endpoint, "uses_internal_fleet_pricing", lambda *_: False)
    relationship = AsyncMock()
    monkeypatch.setattr(endpoint, "ensure_vehicle_relationship", relationship)
    monkeypatch.setattr(endpoint, "RepairOrderResponse", SimpleNamespace(model_validate=lambda order: order))
    async def create_with_retry(**kw):
        return await kw["create_fn"]("SYNTHETIC-01")
    monkeypatch.setattr(unique_id, "create_with_retry", create_with_retry)
    payload = RepairOrderCreate(customer_id=customer_id, vehicle_id=vehicle_id,
        originating_call_reference=None if mode == "no_selection" else "signed-selection",
        elis_opportunity_id=uuid4() if mode == "untrusted_ids" else None)
    user = SimpleNamespace(id=uuid4(), tenant_id=shop.id, role=UserRole.GARAGE_OWNER)
    if mode in {"wrong_customer", "untrusted_ids"}:
        with pytest.raises(HTTPException) as error:
            await endpoint.create_repair_order(payload, db, user)
        assert error.value.status_code == (422 if mode == "untrusted_ids" else 409)
        assert not db.added
        relationship.assert_not_called()
        if mode == "untrusted_ids":
            reserve.assert_not_called()
    else:
        result = await endpoint.create_repair_order(payload, db, user)
        if mode == "retry":
            assert result is existing
            assert not db.added
            relationship.assert_not_called()
        elif mode == "new":
            assert result.id == reservation.repair_order_uuid
            assert result.elis_opportunity_id == reservation.elis_opportunity_id
            assert result.callrail_call_id == reservation.callrail_call_id
            assert not hasattr(result, "originating_call_reference")
        else:
            reserve.assert_not_called()
            assert result.elis_opportunity_id is None
    assert all("repair_orders.tenant_id" in query for query in db.queries if "FROM repair_orders" in query)


@pytest.mark.asyncio
@pytest.mark.parametrize("role_name", ["FLEET_MANAGER", "CUSTOMER", "DRIVER"])
async def test_options_dependency_denies_non_shop_roles(role_name):
    import inspect
    from app.api.v1.endpoints.repair_orders import originating_call_options
    from app.db.models.user import UserRole
    checker = inspect.signature(originating_call_options).parameters["current_user"].default.dependency
    with pytest.raises(HTTPException) as error:
        await checker(SimpleNamespace(role=getattr(UserRole, role_name)))
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_fleet_manager_cannot_reserve_call_before_any_database_or_provider_access(monkeypatch):
    from app.api.v1.endpoints.repair_orders import create_repair_order
    from app.db.models.user import UserRole
    remote = AsyncMock()
    monkeypatch.setattr(service, "reserve_originating_call", remote)
    with pytest.raises(HTTPException) as error:
        await create_repair_order(
            RepairOrderCreate(customer_id=uuid4(), vehicle_id=uuid4(), originating_call_reference="selected"),
            None, SimpleNamespace(role=UserRole.FLEET_MANAGER, tenant_id=uuid4()),
        )
    assert error.value.status_code == 403
    remote.assert_not_called()
