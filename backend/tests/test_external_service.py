"""DB119 staff privacy, historical invariants, replay and retained corrections."""
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import HTTPException, Response
from pydantic import ValidationError
import pytest
from sqlalchemy import func, select

from app.api.v1.endpoints import external_services as routes
from app.db.models.external_service import ExternalServiceEvent as Event, ExternalServiceRecord as Record
from app.db.models.invoice import Invoice
from app.db.models.payment import Payment
from app.db.models.repair_order import RepairOrder
from app.db.models.user import UserRole
from app.db.models.vehicle import Vehicle
from app.schemas.external_service import ExternalServiceCreate as Create, ExternalServiceRestore as Restore, ExternalServiceUpdate as Update, ExternalServiceVoid as Void
from app.services import external_service as service
from app.services.vehicle_merge import merge_vehicles, vehicle_merge_summary
from test_operation_execution import assert_error
from test_service_checklists import seed


def create(**overrides):
    return Create(**dict(request_id=uuid4(), provider_name="QA Outside Shop", service_date="2026-01-10", description="Changed air dryer", odometer=425000, reference="EXT-1", reported_cost="240.50") | overrides)


def update(record, **overrides):
    values = create().model_dump()
    values.update(expected_version=record.version)
    values.update(overrides)
    return Update(**values)


async def add_vehicle(db, a):
    vehicle = Vehicle(id=uuid4(), tenant_id=a.tenant.id, customer_id=a.customer.id, make="QA", model="Truck", vin="1HTMMAAL17H123456")
    db.add(vehicle)
    await db.commit()
    return vehicle


@pytest.mark.parametrize("field,value", [
    ("provider_name", " "), ("provider_name", "x" * 161), ("description", "x" * 4001), ("description", 123),
    ("reference", "x" * 101), ("odometer", True), ("odometer", 1.5), ("odometer", "123"), ("odometer", -1), ("odometer", 100000000),
    ("reported_cost", "NaN"), ("reported_cost", "Infinity"), ("reported_cost", "-1"), ("reported_cost", "1.001"), ("reported_cost", True), ("reported_cost", "10000000000"),
    ("service_date", "1899-12-31"), ("service_date", "2026-02-30"), ("service_date", "2026-01-10T00:00:00Z"), ("service_date", 1768003200),
    ("tenant_id", str(uuid4())), ("actor_user_id", str(uuid4())), ("vehicle_id", str(uuid4())), ("voided_at", None),
])
def test_validation(field, value):
    with pytest.raises(ValidationError):
        create(**{field: value})


def test_trim_bounds_and_exact_decimal():
    body = create(provider_name="  " + "x" * 160 + " ", description=" \n  Work\n  details  ", reference=" ", reported_cost="1.0")
    assert body.provider_name == "x" * 160 and body.description == "Work\n  details"
    assert body.reference is None and body.model_dump(mode="json")["reported_cost"] == "1.00"
    for model, values in [(Void, dict(reason=" ")), (Restore, dict(expected_version=True))]:
        with pytest.raises(ValidationError):
            model(**(dict(request_id=uuid4(), expected_version=1) | values))


@pytest.mark.asyncio
async def test_full_lifecycle_replays_audit_and_no_native_side_effects(db_session):
    a = await seed(db_session)
    a.vehicle.mileage = 500000
    a.vehicle.next_pm_miles = 510000
    a.vehicle.pm_due_date = date(2026, 11, 1)
    await db_session.commit()
    native_before = (a.order.total_cost, a.order.status, a.order.customer_id)
    request = create(description=" <script>literal, never HTML</script> ")
    first = await service.mutate(db_session, a.vehicle.id, a.owner, request)
    assert first.record.version == 1 and first.record.original_vehicle_id == a.vehicle.id
    assert first.record.created_by_name == "Casey Owner" and not first.replayed
    await db_session.commit()
    change = update(first.record, description="Correction", reported_cost=None)
    corrected = await service.mutate(db_session, a.vehicle.id, a.owner, change, action="update", record_id=first.record.id)
    assert corrected.record.version == 2 and corrected.record.reported_cost is None
    replay = await service.mutate(db_session, a.vehicle.id, a.owner, request)
    assert replay.replayed and replay.record == corrected.record
    reason = Void(request_id=uuid4(), expected_version=2, reason="  Wrong truck  ")
    voided = await service.mutate(db_session, a.vehicle.id, a.owner, reason, action="void", record_id=first.record.id)
    assert voided.record.version == 3 and voided.record.voided_at is not None
    assert (await service.page(db_session, a.vehicle.id, a.owner)).total == 0
    assert (await service.page(db_session, a.vehicle.id, a.owner, include_voided=True)).total == 1
    await assert_error(409, service.mutate(db_session, a.vehicle.id, a.owner, update(voided.record), action="update", record_id=first.record.id), "Restore")
    restore = Restore(request_id=uuid4(), expected_version=3)
    restored = await service.mutate(db_session, a.vehicle.id, a.owner, restore, action="restore", record_id=first.record.id)
    assert restored.record.version == 4 and restored.record.voided_at is None
    for action, body in [("update", change), ("void", reason), ("restore", restore)]:
        result = await service.mutate(db_session, a.vehicle.id, a.owner, body, action=action, record_id=first.record.id)
        assert result.replayed and result.record == restored.record
    history = await service.history(db_session, a.vehicle.id, first.record.id, a.owner)
    assert [row.action for row in history.items] == ["restore", "void", "update", "create"]
    assert history.items[-1].snapshot.description == "<script>literal, never HTML</script>"
    assert history.items[-1].snapshot.reported_cost == Decimal("240.50")
    assert history.items[1].reason == "Wrong truck"
    await db_session.commit()
    await db_session.refresh(a.vehicle)
    await db_session.refresh(a.order)
    assert (a.vehicle.mileage, a.vehicle.next_pm_miles, a.vehicle.pm_due_date) == (500000, 510000, date(2026, 11, 1))
    assert (a.order.total_cost, a.order.status, a.order.customer_id) == native_before
    assert await db_session.scalar(select(func.count(RepairOrder.id))) == 1
    for model in (Invoice, Payment):
        assert await db_session.scalar(select(func.count(model.id))) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("role", list(UserRole))
async def test_role_boundary_before_data_queries(db_session, role):
    actor = SimpleNamespace(id=uuid4(), tenant_id=uuid4(), role=role)
    if role not in service.STAFF_ROLES:
        db = AsyncMock()
        for call in [service.page(db, uuid4(), actor), service.history(db, uuid4(), uuid4(), actor), service.mutate(db, uuid4(), actor, create())]:
            await assert_error(403, call)
        db.execute.assert_not_called()
    else:
        a = await seed(db_session)
        a.owner.role = role
        result = await service.mutate(db_session, a.vehicle.id, a.owner, create())
        assert result.record.created_by_user_id == a.owner.id


@pytest.mark.asyncio
async def test_tenant_vehicle_record_and_archived_boundaries(db_session):
    a, b = await seed(db_session), await seed(db_session)
    other_vehicle = await add_vehicle(db_session, a)
    record = (await service.mutate(db_session, a.vehicle.id, a.owner, create())).record
    for actor, vehicle in [(b.owner, a.vehicle), (a.owner, b.vehicle)]:
        await assert_error(404, service.page(db_session, vehicle.id, actor), service.NOT_FOUND)
        await assert_error(404, service.mutate(db_session, vehicle.id, actor, create()), service.NOT_FOUND)
    await assert_error(404, service.history(db_session, other_vehicle.id, record.id, a.owner), service.NOT_FOUND)
    await assert_error(404, service.mutate(db_session, other_vehicle.id, a.owner, update(record), action="update", record_id=record.id), service.NOT_FOUND)
    await assert_error(404, service.history(db_session, a.vehicle.id, uuid4(), a.owner))
    a.vehicle.deleted_at = datetime.now(UTC)
    await db_session.flush()
    await assert_error(404, service.page(db_session, a.vehicle.id, a.owner))
    await assert_error(404, service.mutate(db_session, a.vehicle.id, a.owner, create()))
    a.owner.tenant_id = None
    await assert_error(400, service.page(db_session, a.vehicle.id, a.owner))


@pytest.mark.asyncio
async def test_collisions_stale_versions_and_invalid_lifecycle(db_session):
    a = await seed(db_session)
    other_vehicle = await add_vehicle(db_session, a)
    request = create()
    record = (await service.mutate(db_session, a.vehicle.id, a.owner, request)).record
    alternate = SimpleNamespace(id=uuid4(), tenant_id=a.tenant.id, role=UserRole.GARAGE_ADMIN, first_name="Other", last_name="Staff")
    for vehicle, actor, payload in [(a.vehicle, a.owner, create(request_id=request.request_id, description="different")), (other_vehicle, a.owner, request), (a.vehicle, alternate, request)]:
        await assert_error(409, service.mutate(db_session, vehicle.id, actor, payload), service.COLLISION)
    await assert_error(409, service.mutate(db_session, a.vehicle.id, a.owner, update(record, request_id=request.request_id), action="update", record_id=record.id), service.COLLISION)
    await service.mutate(db_session, a.vehicle.id, a.owner, update(record), action="update", record_id=record.id)
    await assert_error(409, service.mutate(db_session, a.vehicle.id, a.owner, update(record, description="stale"), action="update", record_id=record.id), service.STALE)
    await assert_error(409, service.mutate(db_session, a.vehicle.id, a.owner, Restore(request_id=uuid4(), expected_version=2), action="restore", record_id=record.id), "already active")
    void = Void(request_id=uuid4(), expected_version=2, reason="QA cleanup")
    await service.mutate(db_session, a.vehicle.id, a.owner, void, action="void", record_id=record.id)
    await assert_error(409, service.mutate(db_session, a.vehicle.id, a.owner, Void(request_id=uuid4(), expected_version=3, reason="again"), action="void", record_id=record.id), "Restore")
    assert await db_session.scalar(select(func.count(Record.id))) == 1
    assert await db_session.scalar(select(func.count(Event.id))) == 3


@pytest.mark.asyncio
async def test_date_order_pagination_zero_unknown_and_tenant_scoped_request_id(db_session):
    a, b = await seed(db_session), await seed(db_session)
    request = create(service_date="2025-01-01", reported_cost="0")
    first = await service.mutate(db_session, a.vehicle.id, a.owner, request)
    await service.mutate(db_session, b.vehicle.id, b.owner, request)
    newest = await service.mutate(db_session, a.vehicle.id, a.owner, create(reported_cost=None))
    page = await service.page(db_session, a.vehicle.id, a.owner, limit=1)
    assert page.items[0].id == newest.record.id and page.has_more and page.total == 2
    page = await service.page(db_session, a.vehicle.id, a.owner, skip=1, limit=1)
    assert page.items[0].id == first.record.id and page.items[0].reported_cost == 0 and not page.has_more
    await assert_error(422, service.mutate(db_session, a.vehicle.id, a.owner, create(service_date=(date.today() + timedelta(days=2)).isoformat())), "future")


@pytest.mark.asyncio
async def test_merge_moves_active_and_voided_history_and_retains_original_provenance(db_session):
    a = await seed(db_session)
    canonical = await add_vehicle(db_session, a)
    a.vehicle.vin = canonical.vin
    await db_session.commit()
    original = create()
    first = (await service.mutate(db_session, a.vehicle.id, a.owner, original)).record
    second = (await service.mutate(db_session, a.vehicle.id, a.owner, create())).record
    await service.mutate(db_session, a.vehicle.id, a.owner, Void(request_id=uuid4(), expected_version=1, reason="QA void"), action="void", record_id=second.id)
    await db_session.commit()
    before = (await service.history(db_session, a.vehicle.id, first.id, a.owner)).model_dump(mode="json")
    assert (await vehicle_merge_summary(db_session, a.vehicle))["external_service_count"] == 2
    _, _, moved = await merge_vehicles(db_session, tenant_id=a.tenant.id, canonical_id=canonical.id, duplicate_id=a.vehicle.id, merged_by_user_id=a.owner.id, confirm_vin=canonical.vin)
    await db_session.commit()
    assert moved["external_services"] == 2
    result = await service.page(db_session, canonical.id, a.owner, include_voided=True)
    assert result.total == 2 and {item.original_vehicle_id for item in result.items} == {a.vehicle.id}
    assert (await service.history(db_session, canonical.id, first.id, a.owner)).model_dump(mode="json") == before
    await assert_error(404, service.mutate(db_session, a.vehicle.id, a.owner, original))
    await assert_error(409, service.mutate(db_session, canonical.id, a.owner, original), service.COLLISION)
    await service.mutate(db_session, canonical.id, a.owner, update(first, description="Correct canonical record"), action="update", record_id=first.id)
    assert (await service.history(db_session, canonical.id, first.id, a.owner)).items[0].snapshot.original_vehicle_id == a.vehicle.id


@pytest.mark.asyncio
async def test_http_status_and_mounted_contract(db_session):
    a = await seed(db_session)
    response = Response(status_code=201)
    body = create()
    first = await routes.create_external_service(a.vehicle.id, body, response, db_session, a.owner)
    assert response.status_code == 201 and not first.replayed
    response = Response(status_code=201)
    second = await routes.create_external_service(a.vehicle.id, body, response, db_session, a.owner)
    assert response.status_code == 200 and second.replayed
    from app.api.v1.router import api_router
    paths = {(route.path, method) for route in api_router.routes for method in getattr(route, "methods", [])}
    base = "/vehicles/{vehicle_id}/external-services"
    assert {(base, "GET"), (base, "POST"), (base + "/{record_id}", "PUT"), (base + "/{record_id}/void", "POST"), (base + "/{record_id}/restore", "POST"), (base + "/{record_id}/history", "GET")} <= paths


@pytest.mark.asyncio
async def test_actual_http_auth_validation_replay_cache_and_stale(client, db_session):
    from app.main import app
    from app.core.dependencies import get_current_active_user
    a = await seed(db_session)
    path = f"/api/v1/vehicles/{a.vehicle.id}/external-services"
    assert (await client.get(path)).status_code == 401
    app.dependency_overrides[get_current_active_user] = lambda: a.owner
    try:
        body = create().model_dump(mode="json")
        invalid = await client.post(path, json=body | {"tenant_id": str(uuid4())})
        assert invalid.status_code == 422
        saved = await client.post(path, json=body)
        assert saved.status_code == 201 and "no-store" in saved.headers["cache-control"]
        record = saved.json()["record"]
        replay = await client.post(path, json=body)
        assert replay.status_code == 200 and replay.json()["replayed"]
        response = await client.get(path)
        assert "no-store" in response.headers["cache-control"]
        assert response.json()["items"] == [record]
        for query in ["limit=0", "limit=101", "skip=-1"]:
            assert (await client.get(f"{path}?{query}")).status_code == 422
        changed = body | {"request_id": str(uuid4()), "expected_version": 1, "description": "Corrected"}
        assert (await client.put(f"{path}/{record['id']}", json=changed)).status_code == 200
        changed["request_id"] = str(uuid4())
        stale = await client.put(f"{path}/{record['id']}", json=changed)
        assert stale.status_code == 409 and stale.json()["detail"] == service.STALE
        history = await client.get(f"{path}/{record['id']}/history")
        assert history.status_code == 200 and history.json()["total"] == 2 and "no-store" in history.headers["cache-control"]
        a.owner.role = UserRole.CUSTOMER
        denied = await client.get(path)
        assert denied.status_code == 403 and body["description"] not in denied.text
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)


@pytest.mark.asyncio
async def test_private_records_not_in_existing_customer_order_invoice_quote_or_fleet_serializers(db_session):
    from app.api.v1.endpoints import customers, fleet, invoices, quotes, repair_orders, vehicles
    from app.db.models.quote import Quote
    from app.db.models.vehicle_relationship import FleetMembership
    a = await seed(db_session)
    marker = "DB119 PRIVATE OUTSIDE WORK"
    saved = (await service.mutate(db_session, a.vehicle.id, a.owner, create(description=marker))).record
    a.customer.is_internal_fleet = True
    a.customer.fleet_enabled = True
    db_session.add(FleetMembership(tenant_id=a.tenant.id, vehicle_id=a.vehicle.id, fleet_customer_id=a.customer.id))
    quote = Quote(id=uuid4(), tenant_id=a.tenant.id, repair_order_id=a.order.id, quote_number=f"Q-{uuid4()}", total_amount=100)
    invoice = Invoice(id=uuid4(), tenant_id=a.tenant.id, repair_order_id=a.order.id, invoice_number=f"I-{uuid4()}", subtotal=100, total_amount=100)
    db_session.add_all([quote, invoice])
    await db_session.commit()
    customer = SimpleNamespace(role=UserRole.CUSTOMER, customer_id=a.customer.id, tenant_id=a.tenant.id)
    values = [
        (await vehicles.get_vehicle(a.vehicle.id, db_session, customer)).model_dump(mode="json"),
        (await customers.get_customer_with_vehicles(a.customer.id, db_session, customer)).model_dump(mode="json"),
        await customers.get_customer_history(a.customer.id, db_session, customer),
        await customers.get_customer_history_detail(a.customer.id, a.order.id, db_session, customer),
        (await invoices.get_invoice(invoice.id, db_session, customer)).model_dump(mode="json"),
        (await quotes.get_quote_by_repair_order(a.order.id, db_session, a.owner)).model_dump(mode="json"),
        (await repair_orders.get_repair_order_workspace(a.order.id, db_session, a.owner)).model_dump(mode="json"),
        [entry.model_dump(mode="json") for entry in await fleet.truck_history(a.vehicle.id, 50, db_session, a.owner)],
    ]
    serialized = json.dumps(values, default=str)
    assert marker not in serialized and str(saved.id) not in serialized and "external_services" not in serialized


@pytest.mark.asyncio
async def test_customer_relink_and_merge_preserve_private_truck_record(db_session):
    from app.api.v1.endpoints import customers, vehicles
    from app.db.models.customer import Customer
    from app.schemas.customer import CustomerMergeRequest
    from app.schemas.vehicle import VehicleRelationshipSync
    a = await seed(db_session)
    second = Customer(id=uuid4(), tenant_id=a.tenant.id, first_name="Second", last_name="Account", email=f"{uuid4()}@example.invalid")
    third = Customer(id=uuid4(), tenant_id=a.tenant.id, first_name="Third", last_name="Account", email=f"{uuid4()}@example.invalid")
    db_session.add_all([second, third])
    await db_session.commit()
    record = (await service.mutate(db_session, a.vehicle.id, a.owner, create())).record
    await db_session.commit()
    before = (await service.history(db_session, a.vehicle.id, record.id, a.owner)).model_dump(mode="json")
    await vehicles.sync_vehicle_relationships(a.vehicle.id, VehicleRelationshipSync(customer_id=second.id, relationship_types=["owner"]), db_session, a.owner)
    assert (await service.page(db_session, a.vehicle.id, a.owner)).items == [record]
    await customers.merge_customers(CustomerMergeRequest(winner_id=third.id, loser_id=second.id), db_session, a.owner)
    assert (await service.page(db_session, a.vehicle.id, a.owner)).items == [record]
    assert (await service.history(db_session, a.vehicle.id, record.id, a.owner)).model_dump(mode="json") == before
    for customer in [a.customer, third]:
        actor = SimpleNamespace(role=UserRole.CUSTOMER, customer_id=customer.id, tenant_id=a.tenant.id)
        await assert_error(403, service.page(db_session, a.vehicle.id, actor))


@pytest.mark.asyncio
async def test_event_failure_rolls_back_create_and_correction_atomically(db_session):
    from sqlalchemy import event
    a = await seed(db_session)
    record = (await service.mutate(db_session, a.vehicle.id, a.owner, create())).record
    await db_session.commit()
    def fail_event(mapper, connection, target):
        raise RuntimeError("Injected audit write failure")
    event.listen(Event, "before_insert", fail_event)
    try:
        with pytest.raises(RuntimeError, match="audit write"):
            await service.mutate(db_session, a.vehicle.id, a.owner, create())
        with pytest.raises(RuntimeError, match="audit write"):
            await service.mutate(db_session, a.vehicle.id, a.owner, update(record, description="Must not persist"), action="update", record_id=record.id)
    finally:
        event.remove(Event, "before_insert", fail_event)
    result = await service.page(db_session, a.vehicle.id, a.owner)
    assert result.total == 1 and result.items == [record]
    assert (await service.history(db_session, a.vehicle.id, record.id, a.owner)).total == 1


@pytest.mark.asyncio
async def test_service_date_uses_shop_timezone_at_midnight(db_session, monkeypatch):
    a = await seed(db_session)
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 1, 10, 1, tzinfo=UTC).astimezone(tz)
    monkeypatch.setattr(service, "datetime", FixedDateTime)
    a.tenant.timezone = "America/New_York"
    await db_session.flush()
    await assert_error(422, service.mutate(db_session, a.vehicle.id, a.owner, create(service_date="2026-01-10")), "future")
    a.tenant.timezone = "Asia/Tokyo"
    await db_session.flush()
    result = await service.mutate(db_session, a.vehicle.id, a.owner, create(service_date="2026-01-10"))
    assert result.record.service_date == date(2026, 1, 10)


@pytest.mark.asyncio
async def test_search_complete_history_literal_scope_and_pagination(db_session):
    a, b = await seed(db_session), await seed(db_session)
    other_vehicle = await add_vehicle(db_session, a)
    for i in range(12):
        await service.mutate(db_session, a.vehicle.id, a.owner, create(provider_name=f"Recent shop {i}", description="Recent work", reference=None))
    matches = []
    for values in [dict(provider_name="Needle Shop"), dict(description="Repaired NEEDLE valve"), dict(reference="needle-001")]:
        matches.append((await service.mutate(db_session, a.vehicle.id, a.owner, create(service_date="2024-01-01", **values))).record)
    # All matches are beyond the first unfiltered page.
    assert not ({r.id for r in matches} & {r.id for r in (await service.page(db_session, a.vehicle.id, a.owner, limit=10)).items})
    for vehicle, actor in [(other_vehicle, a.owner), (b.vehicle, b.owner)]:
        await service.mutate(db_session, vehicle.id, actor, create(description="needle"))
    hidden = (await service.mutate(db_session, a.vehicle.id, a.owner, create(description="needle voided"))).record
    await service.mutate(db_session, a.vehicle.id, a.owner, Void(request_id=uuid4(), expected_version=1, reason="QA"), action="void", record_id=hidden.id)
    deleted = (await service.mutate(db_session, a.vehicle.id, a.owner, create(description="needle deleted"))).record
    (await db_session.get(Record, deleted.id)).deleted_at = datetime.now(UTC)
    stamp = datetime(2024, 1, 1, tzinfo=UTC)
    for record in matches:
        (await db_session.get(Record, record.id)).created_at = stamp
    await db_session.flush()
    before = [await db_session.scalar(select(func.count(model.id))) for model in (Event, RepairOrder, Invoice, Payment)]
    first = await service.page(db_session, a.vehicle.id, a.owner, search="  NeEdLe  ", limit=2)
    second = await service.page(db_session, a.vehicle.id, a.owner, search="needle", skip=2, limit=2)
    assert first.total == second.total == 3 and first.has_more and not second.has_more
    assert [r.id for r in first.items + second.items] == sorted([r.id for r in matches], reverse=True)
    assert (await service.page(db_session, a.vehicle.id, a.owner, search="needle", include_voided=True)).total == 4
    assert (await service.page(db_session, a.vehicle.id, a.owner, search="not found")).model_dump() == dict(items=[], total=0, has_more=False)
    assert (await service.page(db_session, a.vehicle.id, a.owner, search=" \t ")).total == (await service.page(db_session, a.vehicle.id, a.owner)).total
    special = (await service.mutate(db_session, a.vehicle.id, a.owner, create(description=r"Literal 50% A_B C\D ' OR 1=1 --"))).record
    for term in ["50%", "A_B", "C\\D", "' OR 1=1 --"]:
        result = await service.page(db_session, a.vehicle.id, a.owner, search=term)
        assert result.total == 1 and result.items[0].id == special.id
    for term in ["50_", "A%B", "C_D"]:
        assert (await service.page(db_session, a.vehicle.id, a.owner, search=term)).total == 0
    assert [await db_session.scalar(select(func.count(model.id))) for model in (Event, RepairOrder, Invoice, Payment)] == [before[0] + 1, *before[1:]]
    await assert_error(404, service.page(db_session, b.vehicle.id, a.owner, search="needle"))
    a.vehicle.deleted_at = datetime.now(UTC)
    await db_session.flush()
    await assert_error(404, service.page(db_session, a.vehicle.id, a.owner, search="needle"))


@pytest.mark.asyncio
async def test_search_http_bounds_cache_and_role_denial(client, db_session):
    from app.main import app
    from app.core.dependencies import get_current_active_user
    a = await seed(db_session)
    path = f"/api/v1/vehicles/{a.vehicle.id}/external-services"
    assert (await client.get(path, params={"search": "needle"})).status_code == 401
    app.dependency_overrides[get_current_active_user] = lambda: a.owner
    try:
        saved = (await service.mutate(db_session, a.vehicle.id, a.owner, create(description="Needle work"))).record
        response = await client.get(path, params={"search": "  NEEDLE "})
        assert response.status_code == 200 and "no-store" in response.headers["cache-control"]
        assert response.json() == dict(items=[saved.model_dump(mode="json")], total=1, has_more=False)
        assert (await client.get(path, params={"search": "x" * 200})).status_code == 200
        assert (await client.get(path, params={"search": "x" * 201})).status_code == 422
        a.owner.role = UserRole.MECHANIC
        assert (await client.get(path, params={"search": "needle"})).status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)
