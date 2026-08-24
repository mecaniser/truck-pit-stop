from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.api.v1.endpoints import parts_operations
from app.core.config import settings
from app.core.security import create_access_token
from app.db.models.customer import Customer
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.parts_operations import (
    CoreObligation,
    InventoryCategory,
    InventoryMovement,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceipt,
    PurchaseReceiptLine,
    VendorReturn,
    VendorReturnLine,
)
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.supplier import Supplier
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle

PREFIX = "/api/v1/parts-operations"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "db038_parts_operations.json"
FROZEN = datetime(2026, 8, 23, 14, tzinfo=timezone.utc)


def _headers(user: User, tenant: Tenant) -> dict[str, str]:
    token = create_access_token({"sub": str(user.id)}, tenant_id=str(tenant.id))
    return {"Authorization": f"Bearer {token}"}


async def _seed_read_contract(db):
    fixture = json.loads(FIXTURE_PATH.read_text())
    ids = {name: UUID(value) for name, value in fixture["ids"].items()}
    tenant = Tenant(id=UUID(fixture["tenant_ids"]["primary"]), name="Truck Pit Stop", slug=f"db038-read-{uuid4().hex}", is_active=True, parts_operations_enabled=True)
    foreign = Tenant(id=UUID(fixture["tenant_ids"]["foreign"]), name="Foreign Shop", slug=f"db038-foreign-{uuid4().hex}", is_active=True, parts_operations_enabled=True)
    db.add_all((tenant, foreign)); await db.flush()
    owner = User(tenant_id=tenant.id, email=f"db038-read-owner-{uuid4().hex}@example.test", hashed_password="x", first_name="Parts", last_name="Owner", role=UserRole.GARAGE_OWNER, is_active=True, is_verified=True)
    receptionist = User(tenant_id=tenant.id, email=f"db038-read-desk-{uuid4().hex}@example.test", hashed_password="x", first_name="Parts", last_name="Desk", role=UserRole.RECEPTIONIST, is_active=True, is_verified=True)
    mechanic = User(tenant_id=tenant.id, email=f"db038-read-tech-{uuid4().hex}@example.test", hashed_password="x", first_name="Parts", last_name="Tech", role=UserRole.MECHANIC, is_active=True, is_verified=True)
    supplier = Supplier(id=ids["supplier"], tenant_id=tenant.id, name="Fleet Parts Co", normalized_name="fleet parts co", is_active=True)
    foreign_supplier = Supplier(tenant_id=foreign.id, name="Foreign Parts", normalized_name="foreign parts", is_active=True)
    deleted_supplier = Supplier(tenant_id=tenant.id, name="Deleted Parts", normalized_name="deleted parts", is_active=True, deleted_at=FROZEN)
    category = InventoryCategory(id=ids["category"], tenant_id=tenant.id, name="Filters", normalized_name="filters", description="Engine filters", is_active=True)
    inactive_category = InventoryCategory(tenant_id=tenant.id, name="Archived", normalized_name="archived", is_active=False)
    inventory_rows = {}
    for record in fixture["inventory"][:4]:
        inventory_rows[record["id"]] = Inventory(
            id=UUID(record["id"]), tenant_id=tenant.id, sku=record["sku"], name=record["name"],
            stock_quantity=record["stock_quantity"], on_order_quantity=record.get("on_order_quantity", 0),
            reorder_level=record["reorder_level"], cost=Decimal(record["cost"]),
            selling_price=Decimal("20.00"), core_charge=Decimal(record.get("core_charge", "0.00")),
            unit_type="each", is_placeholder=record.get("is_placeholder", False),
            preferred_supplier_id=UUID(record["preferred_supplier_id"]) if record.get("preferred_supplier_id") else None,
            category_id=category.id,
        )
    foreign_item = Inventory(id=ids["foreign_lookalike"], tenant_id=foreign.id, sku="DB-OIL-FILTER-01", name="Foreign oil filter", stock_quantity=99, on_order_quantity=0, reorder_level=0, cost=Decimal("1.00"), selling_price=Decimal("2.00"), unit_type="each", is_placeholder=False)
    deleted_item = Inventory(tenant_id=tenant.id, sku="DELETED-ITEM", name="Deleted item", stock_quantity=0, on_order_quantity=0, reorder_level=0, cost=Decimal("1.00"), selling_price=Decimal("2.00"), unit_type="each", is_placeholder=False, deleted_at=FROZEN)
    db.add_all((owner, receptionist, mechanic, supplier, foreign_supplier, deleted_supplier, category, inactive_category, *inventory_rows.values(), foreign_item, deleted_item)); await db.flush()
    customer = Customer(tenant_id=tenant.id, first_name="Read", last_name="Fixture", email=f"db038-read-customer-{uuid4().hex}@example.test")
    db.add(customer); await db.flush()
    vehicle = Vehicle(tenant_id=tenant.id, customer_id=customer.id, make="Freightliner", model="Cascadia", year=2024)
    db.add(vehicle); await db.flush()
    active_order = RepairOrder(id=ids["repair_order"], tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id, order_number="TPS-000301", status=RepairOrderStatus.IN_PROGRESS)
    terminal_orders = [RepairOrder(
        tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id,
        order_number=f"TPS-{terminal.value.upper()}-{uuid4().hex[:8]}", status=terminal,
    ) for terminal in (RepairOrderStatus.COMPLETED, RepairOrderStatus.INVOICED, RepairOrderStatus.PAID, RepairOrderStatus.CANCELLED)]
    locked_order = RepairOrder(tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id, order_number=f"TPS-LOCKED-{uuid4().hex[:8]}", status=RepairOrderStatus.IN_PROGRESS, pricing_locked_at=FROZEN)
    deleted_order = RepairOrder(tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id, order_number=f"TPS-DELETED-{uuid4().hex[:8]}", status=RepairOrderStatus.IN_PROGRESS, deleted_at=FROZEN)
    db.add_all((active_order, *terminal_orders, locked_order, deleted_order)); await db.flush()
    oil = inventory_rows[str(ids["oil_filter"])]
    coolant = inventory_rows[str(ids["coolant"])]
    starter = inventory_rows[str(ids["reman_starter"])]
    placeholder = inventory_rows[str(ids["placeholder_part"])]
    usages = [
        PartsUsage(id=ids["parts_usage"], tenant_id=tenant.id, repair_order_id=active_order.id, inventory_id=oil.id, quantity=Decimal("3.00"), unit_cost=oil.cost, unit_price=Decimal("20.00"), total_price=Decimal("60.00"), stock_reserved_packages=1, stock_shortage_override=True),
        PartsUsage(tenant_id=tenant.id, repair_order_id=active_order.id, inventory_id=coolant.id, quantity=Decimal("1.00"), unit_cost=coolant.cost, unit_price=Decimal("20.00"), total_price=Decimal("20.00"), stock_reserved_packages=0, stock_shortage_override=True),
        PartsUsage(tenant_id=tenant.id, repair_order_id=active_order.id, inventory_id=placeholder.id, quantity=Decimal("1.00"), unit_cost=Decimal("0.00"), unit_price=Decimal("0.00"), total_price=Decimal("0.00"), stock_reserved_packages=0, stock_shortage_override=True),
        PartsUsage(tenant_id=tenant.id, repair_order_id=active_order.id, inventory_id=starter.id, quantity=Decimal("1.00"), unit_cost=starter.cost, unit_price=Decimal("150.00"), total_price=Decimal("150.00"), stock_reserved_packages=1, stock_shortage_override=False),
        *[PartsUsage(tenant_id=tenant.id, repair_order_id=order.id, inventory_id=oil.id, quantity=Decimal("50.00"), unit_cost=oil.cost, unit_price=Decimal("20.00"), total_price=Decimal("1000.00"), stock_reserved_packages=0, stock_shortage_override=True) for order in terminal_orders],
        PartsUsage(tenant_id=tenant.id, repair_order_id=locked_order.id, inventory_id=oil.id, quantity=Decimal("50.00"), unit_cost=oil.cost, unit_price=Decimal("20.00"), total_price=Decimal("1000.00"), stock_reserved_packages=0, stock_shortage_override=True),
        PartsUsage(tenant_id=tenant.id, repair_order_id=deleted_order.id, inventory_id=oil.id, quantity=Decimal("50.00"), unit_cost=oil.cost, unit_price=Decimal("20.00"), total_price=Decimal("1000.00"), stock_reserved_packages=0, stock_shortage_override=True),
        PartsUsage(tenant_id=tenant.id, repair_order_id=active_order.id, inventory_id=oil.id, quantity=Decimal("50.00"), unit_cost=oil.cost, unit_price=Decimal("20.00"), total_price=Decimal("1000.00"), stock_reserved_packages=0, stock_shortage_override=True, deleted_at=FROZEN),
    ]
    db.add_all(usages); await db.flush()
    po = PurchaseOrder(id=ids["purchase_order"], tenant_id=tenant.id, po_number="PO-000201", supplier_id=supplier.id, status="partially_received", version=3, created_by_user_id=owner.id)
    oil_line = PurchaseOrderLine(id=ids["purchase_order_line"], tenant_id=tenant.id, purchase_order_id=po.id, inventory_id=oil.id, sku_snapshot=oil.sku, description_snapshot=oil.name, unit_type_snapshot="each", unit_cost_snapshot=Decimal("18.25"), core_charge_snapshot=Decimal("0.00"), ordered_quantity=2, received_quantity=1)
    coolant_line = PurchaseOrderLine(tenant_id=tenant.id, purchase_order_id=po.id, inventory_id=coolant.id, sku_snapshot=coolant.sku, description_snapshot=coolant.name, unit_type_snapshot="each", unit_cost_snapshot=Decimal("18.00"), core_charge_snapshot=Decimal("0.00"), ordered_quantity=1, received_quantity=0)
    db.add_all((po, oil_line, coolant_line)); await db.flush()
    receipt = PurchaseReceipt(id=ids["purchase_receipt"], tenant_id=tenant.id, purchase_order_id=po.id, receipt_number="RCV-000221", received_at=FROZEN, received_by_user_id=owner.id, idempotency_key="db038-read-receipt-key", request_fingerprint="fixture")
    receipt_line = PurchaseReceiptLine(id=ids["purchase_receipt_line"], tenant_id=tenant.id, purchase_receipt_id=receipt.id, purchase_order_line_id=oil_line.id, inventory_id=oil.id, quantity=1, unit_cost=Decimal("18.25"), wac_before=Decimal("10.00"), wac_after=Decimal("14.13"), balance_before=0, balance_after=1)
    db.add_all((receipt, receipt_line)); await db.flush()
    core = CoreObligation(id=ids["core_obligation"], tenant_id=tenant.id, parts_usage_id=usages[3].id, inventory_id=starter.id, supplier_id=supplier.id, quantity=1, unit_core_value_snapshot=Decimal("50.00"), status="on_hand")
    vendor_return = VendorReturn(id=ids["vendor_return"], tenant_id=tenant.id, return_number="RET-000601", supplier_id=supplier.id, kind="stock", status="shipped", version=3, reason="damaged_in_box", shipped_at=FROZEN)
    return_line = VendorReturnLine(id=ids["vendor_return_line"], tenant_id=tenant.id, vendor_return_id=vendor_return.id, purchase_receipt_line_id=receipt_line.id, inventory_id=oil.id, quantity=1, expected_credit=Decimal("18.25"), stock_value_snapshot=Decimal("10.00"))
    movement = InventoryMovement(id=ids["movement"], tenant_id=tenant.id, inventory_id=oil.id, bucket="on_hand", movement_type="repair_reservation", quantity_delta=-1, balance_before=2, balance_after=1, unit_cost_snapshot=Decimal("10.00"), wac_before=Decimal("10.00"), wac_after=Decimal("10.00"), source_type="repair_order", source_id=active_order.id, occurred_at=FROZEN)
    db.add_all((core, vendor_return, return_line, movement)); await db.commit()
    return {"fixture": fixture, "tenant": tenant, "foreign": foreign, "owner": owner, "receptionist": receptionist, "mechanic": mechanic, "supplier": supplier, "foreign_supplier": foreign_supplier, "deleted_supplier": deleted_supplier,
            "foreign_item": foreign_item, "deleted_item": deleted_item}


@pytest.mark.asyncio
async def test_db038_read_contract_demand_exact_fixture_filters_and_stable_pagination(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    monkeypatch.setattr(parts_operations, "_utc_now", lambda: FROZEN)
    context = await _seed_read_contract(db_session)
    headers = _headers(context["owner"], context["tenant"])
    response = await client.get(f"{PREFIX}/demand?paginated=true", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert {key: body[key] for key in ("total", "skip", "limit", "has_more")} == {"total": 3, "skip": 0, "limit": 50, "has_more": False}
    expected = context["fixture"]["read_contract"]["expected_oil_filter_demand"]
    assert next(item for item in body["items"] if item["inventory_id"] == expected["inventory_id"]) == expected
    assert [item["state"] for item in body["items"]] == ["open", "unlinked", "covered"]
    for state in ("open", "covered", "unlinked"):
        filtered = await client.get(f"{PREFIX}/demand?state={state}", headers=headers)
        assert filtered.status_code == 200 and all(item["state"] == state for item in filtered.json())
    supplier = await client.get(f"{PREFIX}/demand?supplier_id={context['supplier'].id}&search=oil", headers=headers)
    assert supplier.status_code == 200 and [item["sku"] for item in supplier.json()] == ["DB-OIL-FILTER-01"]
    first = await client.get(f"{PREFIX}/demand?paginated=true&limit=1", headers=headers)
    second = await client.get(f"{PREFIX}/demand?paginated=true&limit=1&skip=1", headers=headers)
    assert first.json()["has_more"] is True
    assert first.json()["items"][0]["inventory_id"] != second.json()["items"][0]["inventory_id"]
    assert isinstance((await client.get(f"{PREFIX}/demand", headers=headers)).json(), list)


@pytest.mark.asyncio
async def test_db038_read_contract_collections_filters_sources_and_security(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    context = await _seed_read_contract(db_session)
    headers = _headers(context["owner"], context["tenant"])
    supplier_id = context["supplier"].id
    fixture_ids = context["fixture"]["ids"]
    activity = await client.get(f"{PREFIX}/activity?source_type=repair_order&movement_type=repair_reservation&from=2026-08-23T13:00:00Z&to=2026-08-23T15:00:00Z&paginated=true", headers=headers)
    assert activity.status_code == 200 and activity.json()["total"] == 1
    assert activity.json()["items"][0]["source"] == {"type": "repair_order", "id": fixture_ids["repair_order"], "order_number": "TPS-000301"}
    po = await client.get(f"{PREFIX}/purchase-orders?status=partially_received&supplier_id={supplier_id}&search=000201&paginated=true", headers=headers)
    assert po.status_code == 200 and po.json()["total"] == 1
    assert po.json()["items"][0]["remaining_quantity"] == 2 and po.json()["items"][0]["supplier"]["name"] == "Fleet Parts Co"
    returns = await client.get(f"{PREFIX}/returns?kind=stock&status=shipped&supplier_id={supplier_id}&paginated=true", headers=headers)
    assert returns.status_code == 200 and returns.json()["items"][0]["total_quantity"] == 1
    detail = await client.get(f"{PREFIX}/returns/{fixture_ids['vendor_return']}", headers=headers)
    assert detail.status_code == 200
    return_line = detail.json()["lines"][0]
    assert {**return_line["source"], "quantity": return_line["quantity"], "vendor_return_id": detail.json()["id"]} == context["fixture"]["read_contract"]["expected_return_source"]
    cores = await client.get(f"{PREFIX}/cores?status=on_hand&supplier_id={supplier_id}&inventory_id={fixture_ids['reman_starter']}&paginated=true", headers=headers)
    assert cores.status_code == 200 and cores.json()["total"] == 1
    assert cores.json()["items"][0]["source"]["order_number"] == "TPS-000301"
    categories = await client.get(f"{PREFIX}/categories?active=true&search=filter&paginated=true", headers=headers)
    assert categories.status_code == 200 and [item["name"] for item in categories.json()["items"]] == ["Filters"]
    for route in ("activity", "purchase-orders", "returns", "cores", "categories"):
        compatible = await client.get(f"{PREFIX}/{route}", headers=headers)
        assert compatible.status_code == 200 and isinstance(compatible.json(), list)
    for url in (
        f"{PREFIX}/demand?state=invalid", f"{PREFIX}/purchase-orders?status=invalid",
        f"{PREFIX}/returns?kind=invalid", f"{PREFIX}/cores?status=invalid",
        f"{PREFIX}/activity?limit=0", f"{PREFIX}/activity?source_type=invalid",
        f"{PREFIX}/activity?movement_type=invalid",
        f"{PREFIX}/activity?from=2026-08-24T00:00:00Z&to=2026-08-23T00:00:00Z",
    ):
        assert (await client.get(url, headers=headers)).status_code == 422
    for foreign_id, route in (
        (context["foreign_supplier"].id, "demand?supplier_id="),
        (context["foreign_supplier"].id, "purchase-orders?supplier_id="),
        (context["foreign_supplier"].id, "returns?supplier_id="),
        (context["foreign_item"].id, "activity?inventory_id="),
        (context["foreign_item"].id, "cores?inventory_id="),
        (context["deleted_supplier"].id, "demand?supplier_id="),
        (context["deleted_supplier"].id, "returns?supplier_id="),
        (context["deleted_item"].id, "activity?inventory_id="),
        (context["deleted_item"].id, "cores?inventory_id="),
    ):
        foreign = await client.get(f"{PREFIX}/{route}{foreign_id}", headers=headers)
        missing = await client.get(f"{PREFIX}/{route}{uuid4()}", headers=headers)
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json()["detail"] == missing.json()["detail"] == "Not found"
    assert (await client.get(f"{PREFIX}/demand", headers=_headers(context["receptionist"], context["tenant"]))).status_code == 200
    assert (await client.get(f"{PREFIX}/demand", headers=_headers(context["mechanic"], context["tenant"]))).status_code == 403
    before = await db_session.scalar(select(func.count(InventoryMovement.id)))
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", False)
    assert (await client.get(f"{PREFIX}/demand", headers=headers)).status_code == 404
    assert await db_session.scalar(select(func.count(InventoryMovement.id))) == before
