from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.security import create_access_token
from app.db.models.inventory import Inventory
from app.db.models.parts_operations import InventoryMovement, InventorySupplierSource, PurchaseOrder
from app.db.models.supplier import Supplier
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole


PREFIX = "/api/v1/parts-operations"
SUPPLIERS_PREFIX = "/api/v1/suppliers"
KEY = "db038-receipt-key-0001"


def auth(user: User, tenant: Tenant) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)}, tenant_id=str(tenant.id))}"}


async def seed(db_session, role: UserRole = UserRole.GARAGE_OWNER):
    suffix = uuid4().hex
    tenant = Tenant(name="Parts Shop", slug=f"parts-{suffix}", is_active=True, parts_operations_enabled=True)
    db_session.add(tenant)
    await db_session.flush()
    user = User(tenant_id=tenant.id, email=f"parts-{suffix}@example.test", hashed_password="x", first_name="Parts", last_name="Owner", role=role, is_active=True, is_verified=True)
    supplier = Supplier(tenant_id=tenant.id, name="Reliable Parts", normalized_name="reliable parts", is_active=True)
    item = Inventory(tenant_id=tenant.id, sku="FILTER-1", name="Oil filter", stock_quantity=2, on_order_quantity=0, reorder_level=3, cost=Decimal("10.00"), selling_price=Decimal("20.00"), unit_type="each", is_placeholder=False)
    db_session.add_all([user, supplier, item])
    await db_session.commit()
    return tenant, user, supplier, item


@pytest.mark.asyncio
async def test_parts_operations_receipt_wac_ledger_and_durable_replay(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    tenant, owner, supplier, item = await seed(db_session)
    headers = auth(owner, tenant)
    source_response = await client.post(
        f"{PREFIX}/parts/{item.id}/supplier-sources",
        headers={**headers, "Idempotency-Key": "db038-source-create-key"},
        json={"supplier_id": str(supplier.id), "is_preferred": True},
    )
    assert source_response.status_code == 201
    created = await client.post(f"{PREFIX}/purchase-orders", headers={**headers, "Idempotency-Key": "db038-create-po-key"}, json={
        "po_number": "PO-100", "supplier_id": str(supplier.id),
        "lines": [{"inventory_id": str(item.id), "ordered_quantity": 4, "unit_cost": "16.00"}],
    })
    assert created.status_code == 201
    po = created.json()
    submitted = await client.post(f"{PREFIX}/purchase-orders/{po['id']}/submit", headers={**headers, "Idempotency-Key": "db038-submit-po-key"}, json={"expected_version": 1})
    assert submitted.status_code == 200
    line = submitted.json()["lines"][0]
    received = await client.post(f"{PREFIX}/purchase-orders/{po['id']}/receipts", headers={**headers, "Idempotency-Key": KEY}, json={
        "expected_version": 2, "received_at": "2026-08-23T14:00:00Z",
        "lines": [{"purchase_order_line_id": line["id"], "quantity": 2, "unit_cost": "16.00"}],
    })
    assert received.status_code == 201
    assert "Idempotency-Replayed" not in received.headers
    assert received.json()["purchase_order_status"] == "partially_received"
    assert received.json()["lines"][0]["balance_before"] == 2
    assert received.json()["lines"][0]["balance_after"] == 4
    assert received.json()["lines"][0]["wac_after"] == "13.00"
    replay = await client.post(f"{PREFIX}/purchase-orders/{po['id']}/receipts", headers={**headers, "Idempotency-Key": KEY}, json={
        "expected_version": 2, "received_at": "2026-08-23T14:00:00Z",
        "lines": [{"purchase_order_line_id": line["id"], "quantity": 2, "unit_cost": "16.00"}],
    })
    assert replay.status_code == 201
    assert replay.headers["Idempotency-Replayed"] == "true"
    await db_session.refresh(item)
    assert item.stock_quantity == 4
    assert item.cost == Decimal("13.00")
    source = await db_session.get(InventorySupplierSource, UUID(source_response.json()["source_id"]))
    assert source.last_unit_cost == Decimal("16.00")
    movements = (await db_session.execute(__import__('sqlalchemy').select(InventoryMovement).where(InventoryMovement.inventory_id == item.id))).scalars().all()
    assert len(movements) == 1
    assert movements[0].movement_type == "po_receipt"


@pytest.mark.asyncio
async def test_parts_redesign_projection_sources_and_atomic_grouped_drafts(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    tenant, owner, supplier, item = await seed(db_session)
    headers = auth(owner, tenant)
    source_response = await client.post(
        f"{PREFIX}/parts/{item.id}/supplier-sources",
        headers={**headers, "Idempotency-Key": "db038-source-create-0002"},
        json={
            "supplier_id": str(supplier.id),
            "supplier_part_number": "RP-FILTER-1",
            "is_preferred": True,
            "minimum_order_quantity": 2,
            "pack_quantity": 2,
            "lead_time_days": 2,
        },
    )
    assert source_response.status_code == 201
    source = source_response.json()

    parts = await client.get(f"{PREFIX}/parts?paginated=true", headers=headers)
    assert parts.status_code == 200
    assert parts.json()["total"] == 1
    projection = parts.json()["items"][0]
    assert projection["available_packages"] == 2
    assert projection["needed_for_open_repairs"] == 0
    assert projection["reorder_level"] == 3
    assert projection["recommended_order_packages"] == 1
    assert projection["preferred_source"]["supplier_part_number"] == "RP-FILTER-1"
    search = await client.get(f"{PREFIX}/parts?search=rp-filter", headers=headers)
    assert search.status_code == 200 and search.json()["total"] == 1

    payload = {
        "groups": [{
            "supplier_id": str(supplier.id),
            "lines": [{
                "inventory_id": str(item.id),
                "source_id": source["source_id"],
                "ordered_quantity": 4,
                "unit_cost": "11.25",
            }],
        }],
        "notes": "Prepared from Needs reorder",
    }
    batch_headers = {**headers, "Idempotency-Key": "db038-batch-create-0001"}
    created = await client.post(f"{PREFIX}/purchase-orders/batch", headers=batch_headers, json=payload)
    assert created.status_code == 201
    body = created.json()
    assert body["count"] == 1
    assert body["unassigned"] == []
    assert body["purchase_orders"][0]["status"] == "draft"
    assert body["purchase_orders"][0]["po_number"].startswith("PO-")
    assert body["purchase_orders"][0]["supplier"]["name"] == supplier.name
    assert body["purchase_orders"][0]["line_count"] == 1
    assert body["purchase_orders"][0]["ordered_quantity"] == 4
    assert body["purchase_orders"][0]["lines"][0]["supplier_source_id"] == source["source_id"]
    assert body["purchase_orders"][0]["lines"][0]["supplier_part_number"] == "RP-FILTER-1"
    updated = await client.patch(
        f"{PREFIX}/purchase-orders/{body['purchase_orders'][0]['id']}",
        headers=headers,
        json={
            "expected_version": 1,
            "lines": [{
                "inventory_id": str(item.id),
                "ordered_quantity": 6,
                "unit_cost": "11.50",
            }],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["lines"][0]["supplier_source_id"] == source["source_id"]
    assert updated.json()["lines"][0]["supplier_part_number"] == "RP-FILTER-1"
    detail = await client.get(f"{PREFIX}/parts/{item.id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["open_purchase_order_lines"][0]["supplier_source_id"] == source["source_id"]
    assert detail.json()["open_purchase_order_lines"][0]["remaining_quantity"] == 6
    replay = await client.post(f"{PREFIX}/purchase-orders/batch", headers=batch_headers, json=payload)
    assert replay.status_code == 201
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json() == body
    assert await db_session.scalar(select(func.count(PurchaseOrder.id))) == 1

    changed = {**payload, "notes": "Changed request"}
    conflict = await client.post(f"{PREFIX}/purchase-orders/batch", headers=batch_headers, json=changed)
    assert conflict.status_code == 409


@pytest.mark.asyncio
async def test_parts_redesign_batch_rejects_invalid_source_without_partial_draft(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    tenant, owner, supplier, item = await seed(db_session)
    headers = auth(owner, tenant)
    valid_source = await client.post(
        f"{PREFIX}/parts/{item.id}/supplier-sources",
        headers={**headers, "Idempotency-Key": "db038-batch-valid-source"},
        json={"supplier_id": str(supplier.id)},
    )
    assert valid_source.status_code == 201
    second_supplier = Supplier(
        tenant_id=tenant.id,
        name="Alternate Parts",
        normalized_name="alternate parts",
        is_active=True,
    )
    second_item = Inventory(
        tenant_id=tenant.id,
        sku="BELT-2",
        name="Serpentine belt",
        stock_quantity=0,
        on_order_quantity=0,
        reorder_level=1,
        cost=Decimal("20.00"),
        selling_price=Decimal("40.00"),
        unit_type="each",
        is_placeholder=False,
    )
    db_session.add_all([second_supplier, second_item])
    await db_session.commit()
    response = await client.post(
        f"{PREFIX}/purchase-orders/batch",
        headers={**headers, "Idempotency-Key": "db038-batch-invalid-01"},
        json={"groups": [
            {
                "supplier_id": str(supplier.id),
                "lines": [{
                    "inventory_id": str(item.id),
                    "source_id": valid_source.json()["source_id"],
                    "ordered_quantity": 1,
                    "unit_cost": "10.00",
                }],
            },
            {
                "supplier_id": str(second_supplier.id),
                "lines": [{
                    "inventory_id": str(second_item.id),
                    "source_id": str(uuid4()),
                    "ordered_quantity": 1,
                    "unit_cost": "20.00",
                }],
            },
        ]},
    )
    assert response.status_code == 404
    assert await db_session.scalar(select(func.count(PurchaseOrder.id))) == 0


@pytest.mark.asyncio
async def test_parts_collection_server_pagination_search_attention_and_archived_view(
    client,
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    tenant, owner, supplier, item = await seed(db_session)
    headers = auth(owner, tenant)
    source = await client.post(
        f"{PREFIX}/parts/{item.id}/supplier-sources",
        headers={**headers, "Idempotency-Key": "db038-pagination-source"},
        json={
            "supplier_id": str(supplier.id),
            "supplier_part_number": "SOURCE-LOOKUP-01",
            "is_preferred": True,
        },
    )
    assert source.status_code == 201
    for index in range(3):
        db_session.add(Inventory(
            tenant_id=tenant.id,
            sku=f"STOCK-{index}",
            name=f"Stocked part {index}",
            stock_quantity=10 + index,
            on_order_quantity=0,
            reorder_level=0,
            cost=Decimal("5.00"),
            selling_price=Decimal("10.00"),
            unit_type="each",
            is_placeholder=False,
        ))
    archived = Inventory(
        tenant_id=tenant.id,
        sku="ARCHIVED-1",
        name="Archived part",
        stock_quantity=0,
        on_order_quantity=0,
        reorder_level=0,
        cost=Decimal("1.00"),
        selling_price=Decimal("2.00"),
        unit_type="each",
        is_placeholder=False,
        ets_retired_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
    )
    db_session.add(archived)
    await db_session.commit()

    first = await client.get(f"{PREFIX}/parts?paginated=true&skip=0&limit=2", headers=headers)
    second = await client.get(f"{PREFIX}/parts?paginated=true&skip=2&limit=2", headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["total"] == second.json()["total"] == 4
    assert len(first.json()["items"]) == len(second.json()["items"]) == 2
    assert first.json()["has_more"] is True
    assert second.json()["has_more"] is False
    assert {row["id"] for row in first.json()["items"]}.isdisjoint(
        {row["id"] for row in second.json()["items"]}
    )

    unpaged = await client.get(f"{PREFIX}/parts?paginated=false&limit=1", headers=headers)
    assert unpaged.status_code == 200 and len(unpaged.json()) == 4
    archived_page = await client.get(f"{PREFIX}/parts?view=archived&paginated=true", headers=headers)
    assert archived_page.status_code == 200
    assert archived_page.json()["total"] == 1
    assert archived_page.json()["items"][0]["id"] == str(archived.id)
    attention = await client.get(f"{PREFIX}/parts?attention=needs_reorder&paginated=true", headers=headers)
    assert attention.status_code == 200
    assert [row["id"] for row in attention.json()["items"]] == [str(item.id)]
    by_supplier = await client.get(
        f"{PREFIX}/parts?supplier_id={supplier.id}&paginated=true",
        headers=headers,
    )
    assert by_supplier.status_code == 200
    assert [row["id"] for row in by_supplier.json()["items"]] == [str(item.id)]
    by_source_number = await client.get(
        f"{PREFIX}/parts?search=source-lookup&paginated=true",
        headers=headers,
    )
    assert by_source_number.status_code == 200
    assert [row["id"] for row in by_source_number.json()["items"]] == [str(item.id)]


@pytest.mark.asyncio
async def test_supplier_sources_preference_roles_tenant_and_archived_delete_safety(
    client,
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    tenant, owner, supplier, item = await seed(db_session)
    headers = auth(owner, tenant)
    alternate_supplier = Supplier(
        tenant_id=tenant.id,
        name="Second Source",
        normalized_name="second source",
        is_active=True,
    )
    receptionist = User(
        tenant_id=tenant.id,
        email=f"source-desk-{uuid4().hex}@example.test",
        hashed_password="x",
        first_name="R",
        last_name="Desk",
        role=UserRole.RECEPTIONIST,
        is_active=True,
    )
    db_session.add_all([alternate_supplier, receptionist])
    await db_session.commit()

    primary = await client.post(
        f"{PREFIX}/parts/{item.id}/supplier-sources",
        headers={**headers, "Idempotency-Key": "db038-primary-source"},
        json={"supplier_id": str(supplier.id), "is_preferred": True},
    )
    alternate = await client.post(
        f"{PREFIX}/parts/{item.id}/supplier-sources",
        headers={**headers, "Idempotency-Key": "db038-alternate-source"},
        json={"supplier_id": str(alternate_supplier.id), "supplier_part_number": "ALT-01"},
    )
    assert primary.status_code == alternate.status_code == 201

    duplicate = await client.post(
        f"{PREFIX}/parts/{item.id}/supplier-sources",
        headers={**headers, "Idempotency-Key": "db038-duplicate-source"},
        json={"supplier_id": str(supplier.id)},
    )
    assert duplicate.status_code == 409
    read_only = await client.post(
        f"{PREFIX}/parts/{item.id}/supplier-sources",
        headers={**auth(receptionist, tenant), "Idempotency-Key": "db038-read-only-source"},
        json={"supplier_id": str(alternate_supplier.id)},
    )
    assert read_only.status_code == 403

    foreign_tenant, _, foreign_supplier, _ = await seed(db_session)
    foreign = await client.post(
        f"{PREFIX}/parts/{item.id}/supplier-sources",
        headers={**headers, "Idempotency-Key": "db038-foreign-source"},
        json={"supplier_id": str(foreign_supplier.id)},
    )
    missing = await client.post(
        f"{PREFIX}/parts/{item.id}/supplier-sources",
        headers={**headers, "Idempotency-Key": "db038-missing-source"},
        json={"supplier_id": str(uuid4())},
    )
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["detail"] == missing.json()["detail"] == "Not found"
    assert foreign_tenant.id != tenant.id

    server_owned_cost = await client.patch(
        f"{PREFIX}/parts/{item.id}/supplier-sources/{alternate.json()['source_id']}",
        headers=headers,
        json={
            "expected_updated_at": alternate.json()["updated_at"],
            "last_unit_cost": "7.50",
        },
    )
    assert server_owned_cost.status_code == 422
    stale = await client.patch(
        f"{PREFIX}/parts/{item.id}/supplier-sources/{alternate.json()['source_id']}",
        headers=headers,
        json={"expected_updated_at": "2000-01-01T00:00:00Z", "is_preferred": True},
    )
    assert stale.status_code == 409
    preferred = await client.patch(
        f"{PREFIX}/parts/{item.id}/supplier-sources/{alternate.json()['source_id']}",
        headers=headers,
        json={"expected_updated_at": alternate.json()["updated_at"], "is_preferred": True},
    )
    assert preferred.status_code == 200
    await db_session.refresh(item)
    assert item.preferred_supplier_id == alternate_supplier.id
    primary_row = await db_session.get(InventorySupplierSource, UUID(primary.json()["source_id"]))
    await db_session.refresh(primary_row)
    assert primary_row.is_preferred is False

    archived = Inventory(
        tenant_id=tenant.id,
        sku="ARCH-SOURCE",
        name="Archived source part",
        stock_quantity=0,
        on_order_quantity=0,
        reorder_level=0,
        cost=Decimal("1.00"),
        selling_price=Decimal("2.00"),
        unit_type="each",
        is_placeholder=False,
        ets_retired_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
    )
    db_session.add(archived)
    await db_session.flush()
    archived_source = InventorySupplierSource(
        tenant_id=tenant.id,
        inventory_id=archived.id,
        supplier_id=supplier.id,
        minimum_order_quantity=1,
        pack_quantity=1,
        is_active=True,
    )
    db_session.add(archived_source)
    await db_session.commit()
    await db_session.refresh(archived_source)
    archived_delete = await client.request(
        "DELETE",
        f"{PREFIX}/parts/{archived.id}/supplier-sources/{archived_source.id}",
        headers=headers,
        json={"expected_updated_at": archived_source.updated_at.isoformat()},
    )
    assert archived_delete.status_code == 409


@pytest.mark.asyncio
async def test_supplier_purchasing_profile_round_trip_validation_roles_and_tenant_isolation(
    client,
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    tenant, owner, supplier, _ = await seed(db_session)
    owner_headers = auth(owner, tenant)

    updated = await client.put(
        f"{SUPPLIERS_PREFIX}/{supplier.id}",
        headers=owner_headers,
        json={
            "payment_terms": "Net 30",
            "default_lead_time_days": 5,
            "minimum_order_amount": "250.00",
            "purchasing_notes": "Order filters by the case.",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["payment_terms"] == "Net 30"
    assert updated.json()["default_lead_time_days"] == 5
    assert updated.json()["minimum_order_amount"] == "250.00"
    assert updated.json()["purchasing_notes"] == "Order filters by the case."

    listed = await client.get(f"{SUPPLIERS_PREFIX}?paginated=true", headers=owner_headers)
    assert listed.status_code == 200
    listed_supplier = next(row for row in listed.json()["items"] if row["id"] == str(supplier.id))
    commercial_fields = {
        "payment_terms", "default_lead_time_days",
        "minimum_order_amount", "purchasing_notes",
    }
    assert commercial_fields.isdisjoint(listed_supplier)

    purchasing = await client.get(
        f"{PREFIX}/suppliers/{supplier.id}/purchasing",
        headers=owner_headers,
    )
    assert purchasing.status_code == 200
    assert purchasing.json()["payment_terms"] == "Net 30"
    assert purchasing.json()["default_lead_time_days"] == 5
    assert purchasing.json()["minimum_order_amount"] == "250.00"
    assert purchasing.json()["on_time_rate"] is None

    invalid_lead_time = await client.put(
        f"{SUPPLIERS_PREFIX}/{supplier.id}",
        headers=owner_headers,
        json={"default_lead_time_days": 366},
    )
    assert invalid_lead_time.status_code == 422
    invalid_minimum = await client.put(
        f"{SUPPLIERS_PREFIX}/{supplier.id}",
        headers=owner_headers,
        json={"minimum_order_amount": "-0.01"},
    )
    assert invalid_minimum.status_code == 422

    receptionist = User(
        tenant_id=tenant.id,
        email=f"desk-{uuid4().hex}@example.test",
        hashed_password="x",
        first_name="R",
        last_name="Desk",
        role=UserRole.RECEPTIONIST,
        is_active=True,
    )
    mechanic = User(
        tenant_id=tenant.id,
        email=f"mechanic-supplier-{uuid4().hex}@example.test",
        hashed_password="x",
        first_name="M",
        last_name="Tech",
        role=UserRole.MECHANIC,
        is_active=True,
    )
    tenantless_owner = User(
        tenant_id=None,
        email=f"tenantless-supplier-{uuid4().hex}@example.test",
        hashed_password="x",
        first_name="No",
        last_name="Tenant",
        role=UserRole.GARAGE_OWNER,
        is_active=True,
    )
    db_session.add_all((receptionist, mechanic, tenantless_owner))
    await db_session.commit()
    mechanic_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(mechanic.id)})}",
    }
    mechanic_list = await client.get(f"{SUPPLIERS_PREFIX}?paginated=true", headers=mechanic_headers)
    assert mechanic_list.status_code == 200 and mechanic_list.json()["total"] == 1
    assert commercial_fields.isdisjoint(mechanic_list.json()["items"][0])
    mechanic_purchasing = await client.get(
        f"{PREFIX}/suppliers/{supplier.id}/purchasing",
        headers=mechanic_headers,
    )
    assert mechanic_purchasing.status_code == 403
    read_only = await client.put(
        f"{SUPPLIERS_PREFIX}/{supplier.id}",
        headers=auth(receptionist, tenant),
        json={"payment_terms": "Due now"},
    )
    assert read_only.status_code == 403

    foreign_tenant, foreign_owner, _, _ = await seed(db_session)
    foreign = await client.put(
        f"{SUPPLIERS_PREFIX}/{supplier.id}",
        headers=auth(foreign_owner, foreign_tenant),
        json={"payment_terms": "Due now"},
    )
    assert foreign.status_code == 404
    missing = await client.put(
        f"{SUPPLIERS_PREFIX}/{uuid4()}",
        headers=auth(foreign_owner, foreign_tenant),
        json={"payment_terms": "Due now"},
    )
    assert foreign.json()["detail"] == missing.json()["detail"] == "Not found"
    foreign_list = await client.get(
        f"{SUPPLIERS_PREFIX}?paginated=true",
        headers=auth(foreign_owner, foreign_tenant),
    )
    assert foreign_list.status_code == 200 and foreign_list.json()["total"] == 1
    assert foreign_list.json()["items"][0]["tenant_id"] == str(foreign_tenant.id)
    assert commercial_fields.isdisjoint(foreign_list.json()["items"][0])

    tenantless_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(tenantless_owner.id)})}",
    }
    for method, url, payload in (
        ("GET", SUPPLIERS_PREFIX, None),
        ("POST", SUPPLIERS_PREFIX, {"name": "Unscoped supplier"}),
        ("PUT", f"{SUPPLIERS_PREFIX}/{supplier.id}", {"payment_terms": "Leaked"}),
        ("DELETE", f"{SUPPLIERS_PREFIX}/{supplier.id}", None),
    ):
        response = await client.request(method, url, headers=tenantless_headers, json=payload)
        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"
    await db_session.refresh(supplier)
    assert supplier.payment_terms == "Net 30" and supplier.deleted_at is None


@pytest.mark.asyncio
async def test_parts_operations_gate_roles_and_foreign_po_are_non_enumerating(client, db_session, monkeypatch):
    tenant, owner, supplier, item = await seed(db_session)
    headers = auth(owner, tenant)
    denied_gate = await client.get(f"{PREFIX}/summary", headers=headers)
    assert denied_gate.status_code == 404
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    mechanic = User(tenant_id=tenant.id, email=f"mechanic-{uuid4().hex}@example.test", hashed_password="x", first_name="M", last_name="Tech", role=UserRole.MECHANIC, is_active=True)
    receptionist = User(tenant_id=tenant.id, email=f"desk-{uuid4().hex}@example.test", hashed_password="x", first_name="R", last_name="Desk", role=UserRole.RECEPTIONIST, is_active=True)
    other = Tenant(name="Other Shop", slug=f"other-{uuid4().hex}", is_active=True, parts_operations_enabled=True)
    db_session.add_all([mechanic, receptionist, other]); await db_session.commit()
    assert (await client.get(f"{PREFIX}/summary", headers=auth(mechanic, tenant))).status_code == 403
    assert (await client.get(f"{PREFIX}/summary", headers=auth(receptionist, tenant))).status_code == 200
    po = await client.post(f"{PREFIX}/purchase-orders", headers={**headers, "Idempotency-Key": "db038-foreign-create"}, json={"po_number": "PO-FOREIGN", "supplier_id": str(supplier.id), "lines": [{"inventory_id": str(item.id), "ordered_quantity": 1, "unit_cost": "10.00"}]})
    assert po.status_code == 201
    foreign_user = User(tenant_id=other.id, email=f"foreign-{uuid4().hex}@example.test", hashed_password="x", first_name="F", last_name="User", role=UserRole.GARAGE_OWNER, is_active=True)
    db_session.add(foreign_user); await db_session.commit()
    foreign = await client.get(f"{PREFIX}/purchase-orders/{po.json()['id']}", headers=auth(foreign_user, other))
    missing = await client.get(f"{PREFIX}/purchase-orders/{uuid4()}", headers=auth(foreign_user, other))
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["detail"] == missing.json()["detail"] == "Not found"
    # Correlation IDs are intentionally per request, but cannot contain any
    # protected object data and must be present for both generic 404s.
    assert foreign.json().get("correlation_id")
    assert missing.json().get("correlation_id")
    assert foreign.json()["correlation_id"] != missing.json()["correlation_id"]

def test_parts_operations_migration_supplier_backfill_uses_exact_windowed_match():
    """PostgreSQL has no min(uuid); only a single exact normalized match links it."""
    migration = (Path(__file__).resolve().parents[1] / "alembic" / "versions" / "124_parts_operations_v1.py").read_text()
    assert "min(s.id)" not in migration
    assert "count(s.id) OVER (PARTITION BY i.id) AS supplier_count" in migration
    assert "c.supplier_count = 1" in migration

def test_parts_operations_migration_downgrade_drops_inventory_fks_before_category_table():
    migration = (Path(__file__).resolve().parents[1] / "alembic" / "versions" / "124_parts_operations_v1.py").read_text()
    downgrade = migration.split("def downgrade() -> None:", 1)[1]
    assert downgrade.index('op.drop_column("inventory", "category_id")') < downgrade.index('op.drop_table("inventory_categories")')
    assert '"inventory_categories"' not in downgrade.split('for table in (', 1)[1].split('):', 1)[0]


def test_parts_redesign_migration_is_additive_exact_and_linear_after_db038():
    migration = (Path(__file__).resolve().parents[1] / "alembic" / "versions" / "125_inventory_supplier_sources.py").read_text()
    assert 'down_revision = "124_parts_operations_v1"' in migration
    assert "inventory_supplier_sources" in migration
    assert "i.preferred_supplier_id" in migration
    assert "s.id = i.preferred_supplier_id" in migration
    assert "s.tenant_id = i.tenant_id" in migration
    assert "s.is_active IS TRUE" in migration
    assert 'sa.Column("supplier_source_id", UUID, nullable=True)' in migration
    assert 'sa.Column("supplier_part_number_snapshot", sa.String(150), nullable=True)' in migration
    assert '"uq_inventory_supplier_sources_tenant_id_id_db038"' in migration
    assert '"uq_inventory_supplier_sources_tenant_id_id_inventory_db038"' in migration
    assert '"fk_po_lines_tenant_supplier_source"' in migration
    assert '["tenant_id", "supplier_source_id"]' in migration
    assert '["tenant_id", "id"]' in migration
    assert '"fk_po_lines_supplier_source_inventory"' in migration
    assert '["tenant_id", "supplier_source_id", "inventory_id"]' in migration
    assert '["tenant_id", "id", "inventory_id"]' in migration
    assert '"fk_inventory_supplier_sources_tenant_inventory"' in migration
    assert '"fk_inventory_supplier_sources_tenant_supplier"' in migration
    assert '"uq_inventory_tenant_id_id_db038"' in migration
    assert '"uq_suppliers_tenant_id_id_db038"' in migration
    assert 'sqlite_where=sa.text("deleted_at IS NULL")' in migration
    assert 'sqlite_where=sa.text("deleted_at IS NULL AND is_preferred = 1")' in migration
    assert "src.tenant_id = pol.tenant_id" in migration
    assert "src.inventory_id = pol.inventory_id" in migration
    assert "src.supplier_id = po.supplier_id" in migration
    assert "fuzzy" in migration
    downgrade = migration.split("def downgrade() -> None:", 1)[1]
    assert downgrade.index('"fk_po_lines_supplier_source_inventory"') < downgrade.index(
        'op.drop_table("inventory_supplier_sources")'
    )
    assert downgrade.index('"fk_po_lines_tenant_supplier_source"') < downgrade.index(
        'op.drop_table("inventory_supplier_sources")'
    )

def test_parts_operations_uses_durable_not_ephemeral_idempotency_replay():
    from app.middleware.idempotency import IdempotencyMiddleware

    assert not IdempotencyMiddleware._should_apply({
        "type": "http", "method": "POST", "path": "/api/v1/parts-operations/purchase-orders/x/receipts",
    })
