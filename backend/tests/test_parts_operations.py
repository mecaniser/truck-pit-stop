from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import settings
from app.core.security import create_access_token
from app.db.models.inventory import Inventory
from app.db.models.parts_operations import InventoryMovement
from app.db.models.supplier import Supplier
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole


PREFIX = "/api/v1/parts-operations"
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
    movements = (await db_session.execute(__import__('sqlalchemy').select(InventoryMovement).where(InventoryMovement.inventory_id == item.id))).scalars().all()
    assert len(movements) == 1
    assert movements[0].movement_type == "po_receipt"


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

def test_parts_operations_uses_durable_not_ephemeral_idempotency_replay():
    from app.middleware.idempotency import IdempotencyMiddleware

    assert not IdempotencyMiddleware._should_apply({
        "type": "http", "method": "POST", "path": "/api/v1/parts-operations/purchase-orders/x/receipts",
    })
