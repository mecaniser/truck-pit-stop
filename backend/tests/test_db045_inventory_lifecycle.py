from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.config import settings
from app.core.security import create_access_token
from app.db.models.inventory import Inventory
from app.db.models.inventory_lifecycle import (
    CounterSale,
    CounterSaleLine,
    CounterSalePaymentAttempt,
    CounterSaleReturn,
    PartActivityBackfillRun,
    PartActivityEvent,
)
from app.db.models.parts_operations import InventoryMovement
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.services.counter_sale_service import create_or_replace_draft, price_sale
from app.services.part_activity_backfill import backfill_tenant_activity
from app.services.part_activity_service import (
    append_part_activity,
    safe_money_snapshot,
    safe_payment_snapshot,
    safe_source_snapshot,
    safe_stock_snapshot,
)
from app.services.parts_operations_service import apply_inventory_movement


PREFIX = "/api/v1/parts-operations"


def auth(user: User, tenant: Tenant) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token({'sub': str(user.id)}, tenant_id=str(tenant.id))}",
    }


async def seed_context(db_session, *, verified: bool = True, stock: int = 10):
    suffix = uuid4().hex
    tenant = Tenant(
        name="DB-045 Shop",
        slug=f"db045-{suffix}",
        is_active=True,
        parts_operations_enabled=True,
        counter_sales_enabled=True,
        sales_tax_rate=Decimal("8.000"),
    )
    db_session.add(tenant)
    await db_session.flush()
    owner = User(
        tenant_id=tenant.id,
        email=f"db045-{suffix}@example.test",
        hashed_password="x",
        first_name="Counter",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        is_active=True,
        is_verified=True,
    )
    item = Inventory(
        tenant_id=tenant.id,
        sku="FILTER-045",
        name="Lifecycle Filter",
        stock_quantity=stock,
        on_order_quantity=0,
        reorder_level=2,
        cost=Decimal("30.00"),
        selling_price=Decimal("50.00"),
        unit_type="each",
        is_placeholder=False,
    )
    db_session.add_all([owner, item])
    await db_session.flush()
    if verified:
        now = datetime.now(timezone.utc)
        db_session.add(PartActivityBackfillRun(
            tenant_id=tenant.id,
            payload_version=1,
            cutoff_at=now,
            state="verified",
            source_counts={},
            inserted_counts={},
            replayed_counts={},
            source_checksums={},
            duplicate_count=0,
            reconciled_at=now,
            verified_at=now,
        ))
    await db_session.commit()
    return tenant, owner, item


async def create_sale(client, tenant, owner, item, *, quantity: int = 2, key: str = "db045-create-sale-001"):
    response = await client.post(
        f"{PREFIX}/counter-sales",
        headers={**auth(owner, tenant), "Idempotency-Key": key},
        json={
            "buyer_name": "Walk-in",
            "lines": [{"inventory_id": str(item.id), "quantity": quantity}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_counter_sale_money_allocation_is_cent_stable_without_provider_fee():
    sale = CounterSale(
        id=uuid4(),
        tenant_id=uuid4(),
        sale_number="CS-TEST",
        tax_rate_snapshot=Decimal("8.2500"),
        created_by_user_id=uuid4(),
        updated_by_user_id=uuid4(),
    )
    lines = [
        CounterSaleLine(
            id=uuid4(), tenant_id=sale.tenant_id, sale_id=sale.id,
            inventory_id=uuid4(), quantity=3, sku_snapshot="A", name_snapshot="A",
            unit_snapshot="each", unit_cost=Decimal("2.17"),
            list_unit_price=Decimal("10.00"), charged_unit_price=Decimal("9.99"),
        ),
        CounterSaleLine(
            id=uuid4(), tenant_id=sale.tenant_id, sale_id=sale.id,
            inventory_id=uuid4(), quantity=1, sku_snapshot="B", name_snapshot="B",
            unit_snapshot="each", unit_cost=Decimal("5.00"),
            list_unit_price=Decimal("20.00"), charged_unit_price=Decimal("17.03"),
        ),
    ]

    price_sale(sale, lines)

    assert sale.charged_subtotal == Decimal("47.00")
    assert sale.discount_total == Decimal("3.00")
    assert sale.tax_total == Decimal("3.88")
    assert sale.total == Decimal("50.88")
    assert sum((line.tax_allocation for line in lines), Decimal("0")) == sale.tax_total
    assert sum((Decimal(unit["item"]) for line in lines for unit in line.unit_allocations), Decimal("0")) == sale.charged_subtotal
    assert all("fee" not in unit for line in lines for unit in line.unit_allocations)


@pytest.mark.asyncio
async def test_counter_sale_list_uses_filter_bound_stable_cursor(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    monkeypatch.setattr(settings, "COUNTER_SALES_ENABLED", True)
    tenant, owner, item = await seed_context(db_session)
    await create_sale(client, tenant, owner, item, quantity=1, key="db045-list-sale-a")
    await create_sale(client, tenant, owner, item, quantity=1, key="db045-list-sale-b")

    first = await client.get(
        f"{PREFIX}/counter-sales",
        headers=auth(owner, tenant),
        params={"text": " Walk-in ", "limit": 1},
    )
    assert first.status_code == 200
    assert len(first.json()["items"]) == 1
    cursor = first.json()["next_cursor"]
    assert cursor

    second = await client.get(
        f"{PREFIX}/counter-sales",
        headers=auth(owner, tenant),
        params={"text": "Walk-in", "limit": 1, "cursor": cursor},
    )
    assert second.status_code == 200
    assert len(second.json()["items"]) == 1

    changed = await client.get(
        f"{PREFIX}/counter-sales",
        headers=auth(owner, tenant),
        params={"text": "different", "limit": 1, "cursor": cursor},
    )
    assert changed.status_code == 400


@pytest.mark.asyncio
async def test_counter_sales_require_both_gates_verified_backfill_and_allowed_role(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    monkeypatch.setattr(settings, "COUNTER_SALES_ENABLED", True)
    tenant, owner, _item = await seed_context(db_session, verified=False)

    assert (await client.get(f"{PREFIX}/counter-sales", headers=auth(owner, tenant))).status_code == 404

    now = datetime.now(timezone.utc)
    db_session.add(PartActivityBackfillRun(
        tenant_id=tenant.id, payload_version=1, cutoff_at=now, state="verified",
        source_counts={}, inserted_counts={}, replayed_counts={}, source_checksums={},
        duplicate_count=0, reconciled_at=now, verified_at=now,
    ))
    mechanic = User(
        tenant_id=tenant.id,
        email=f"mechanic-{uuid4().hex}@example.test",
        hashed_password="x",
        first_name="No",
        last_name="Counter",
        role=UserRole.MECHANIC,
        is_active=True,
        is_verified=True,
    )
    db_session.add(mechanic)
    await db_session.commit()

    assert (await client.get(f"{PREFIX}/counter-sales", headers=auth(mechanic, tenant))).status_code == 403
    monkeypatch.setattr(settings, "COUNTER_SALES_ENABLED", False)
    assert (await client.get(f"{PREFIX}/counter-sales", headers=auth(owner, tenant))).status_code == 404


@pytest.mark.asyncio
async def test_manual_checkout_is_atomic_idempotent_and_has_no_provider_state(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    monkeypatch.setattr(settings, "COUNTER_SALES_ENABLED", True)
    tenant, owner, item = await seed_context(db_session)
    sale = await create_sale(client, tenant, owner, item)
    body = {"expected_version": sale["version"], "tender": "external_terminal", "manual_reference": "TERM-44"}
    headers = {**auth(owner, tenant), "Idempotency-Key": "checkout-manual-045"}

    first = await client.post(f"{PREFIX}/counter-sales/{sale['id']}/checkout", headers=headers, json=body)
    replay = await client.post(f"{PREFIX}/counter-sales/{sale['id']}/checkout", headers=headers, json=body)

    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert first.json()["status"] == "completed"
    assert first.json()["payment_attempts"] == [{
        "id": first.json()["payment_attempts"][0]["id"],
        "tender": "external_terminal",
        "state": "succeeded",
        "amount": "108.00",
        "reference": "TERM-44",
        "created_at": first.json()["payment_attempts"][0]["created_at"],
    }]
    assert "client_secret" not in first.text
    assert "reconcile" not in first.text

    await db_session.refresh(item)
    assert item.stock_quantity == 8
    assert await db_session.scalar(select(func.count(InventoryMovement.id)).where(
        InventoryMovement.tenant_id == tenant.id,
        InventoryMovement.inventory_id == item.id,
        InventoryMovement.movement_type == "counter_sale",
    )) == 1
    assert await db_session.scalar(select(func.count(CounterSalePaymentAttempt.id)).where(
        CounterSalePaymentAttempt.tenant_id == tenant.id,
    )) == 1
    assert await db_session.scalar(select(func.count(PartActivityEvent.id)).where(
        PartActivityEvent.tenant_id == tenant.id,
        PartActivityEvent.event_type == "counter_sale.completed",
    )) == 1


@pytest.mark.asyncio
async def test_checkout_rejects_oversell_without_changing_stock(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    monkeypatch.setattr(settings, "COUNTER_SALES_ENABLED", True)
    tenant, owner, item = await seed_context(db_session, stock=1)
    sale = await create_sale(client, tenant, owner, item, quantity=2)
    response = await client.post(
        f"{PREFIX}/counter-sales/{sale['id']}/checkout",
        headers={**auth(owner, tenant), "Idempotency-Key": "db045-oversell-checkout"},
        json={"expected_version": sale["version"], "tender": "cash"},
    )
    assert response.status_code == 409
    await db_session.refresh(item)
    assert item.stock_quantity == 1
    assert await db_session.scalar(select(func.count(CounterSalePaymentAttempt.id)).where(
        CounterSalePaymentAttempt.tenant_id == tenant.id,
    )) == 0


@pytest.mark.asyncio
async def test_price_override_requires_manager_reason_and_receptionist_uses_catalog(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    monkeypatch.setattr(settings, "COUNTER_SALES_ENABLED", True)
    tenant, owner, item = await seed_context(db_session)
    receptionist = User(
        tenant_id=tenant.id,
        email=f"reception-{uuid4().hex}@example.test",
        hashed_password="x",
        first_name="Front",
        last_name="Desk",
        role=UserRole.RECEPTIONIST,
        is_active=True,
        is_verified=True,
    )
    db_session.add(receptionist)
    await db_session.commit()
    override = {
        "buyer_name": "Walk-in",
        "lines": [{"inventory_id": str(item.id), "quantity": 1, "charged_unit_price": "45.00"}],
    }

    receptionist_response = await client.post(
        f"{PREFIX}/counter-sales",
        headers={**auth(receptionist, tenant), "Idempotency-Key": "reception-override"},
        json={**override, "lines": [{**override["lines"][0], "price_override_reason": "Manager approved"}]},
    )
    missing_reason = await client.post(
        f"{PREFIX}/counter-sales",
        headers={**auth(owner, tenant), "Idempotency-Key": "db045-owner-no-reason"},
        json=override,
    )
    accepted = await client.post(
        f"{PREFIX}/counter-sales",
        headers={**auth(owner, tenant), "Idempotency-Key": "db045-owner-with-reason"},
        json={**override, "lines": [{**override["lines"][0], "price_override_reason": "Damaged packaging"}]},
    )

    assert receptionist_response.status_code == 403
    assert missing_reason.status_code == 422
    assert accepted.status_code == 201
    assert accepted.json()["lines"][0]["charged_unit_price"] == "45.00"
    assert accepted.json()["lines"][0]["price_override_reason"] == "Damaged packaging"


@pytest.mark.asyncio
async def test_manual_partial_returns_are_bounded_idempotent_and_disposition_safe(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    monkeypatch.setattr(settings, "COUNTER_SALES_ENABLED", True)
    tenant, owner, item = await seed_context(db_session)
    sale = await create_sale(client, tenant, owner, item)
    completed = (await client.post(
        f"{PREFIX}/counter-sales/{sale['id']}/checkout",
        headers={**auth(owner, tenant), "Idempotency-Key": "db045-return-checkout"},
        json={"expected_version": sale["version"], "tender": "cash"},
    )).json()
    line_id = completed["lines"][0]["id"]

    damaged_body = {
        "expected_version": completed["version"],
        "manual_refund_reference": "REV-1",
        "lines": [{"sale_line_id": line_id, "quantity": 1, "reason": "Damaged package", "disposition": "damaged"}],
    }
    damaged_headers = {**auth(owner, tenant), "Idempotency-Key": "db045-return-damaged"}
    first = await client.post(f"{PREFIX}/counter-sales/{sale['id']}/returns", headers=damaged_headers, json=damaged_body)
    replay = await client.post(f"{PREFIX}/counter-sales/{sale['id']}/returns", headers=damaged_headers, json=damaged_body)
    assert first.status_code == replay.status_code == 201
    assert first.json() == replay.json()
    await db_session.refresh(item)
    assert item.stock_quantity == 8

    current = (await client.get(f"{PREFIX}/counter-sales/{sale['id']}", headers=auth(owner, tenant))).json()
    restock = await client.post(
        f"{PREFIX}/counter-sales/{sale['id']}/returns",
        headers={**auth(owner, tenant), "Idempotency-Key": "db045-return-restock"},
        json={
            "expected_version": current["version"],
            "lines": [{"sale_line_id": line_id, "quantity": 1, "reason": "Customer return", "disposition": "restock"}],
        },
    )
    assert restock.status_code == 201
    await db_session.refresh(item)
    assert item.stock_quantity == 9
    final = (await client.get(f"{PREFIX}/counter-sales/{sale['id']}", headers=auth(owner, tenant))).json()
    assert final["status"] == "returned"

    excessive = await client.post(
        f"{PREFIX}/counter-sales/{sale['id']}/returns",
        headers={**auth(owner, tenant), "Idempotency-Key": "db045-return-excess"},
        json={
            "expected_version": final["version"],
            "lines": [{"sale_line_id": line_id, "quantity": 1, "reason": "Too many", "disposition": "restock"}],
        },
    )
    assert excessive.status_code in {409, 422}
    assert await db_session.scalar(select(func.count(CounterSaleReturn.id)).where(
        CounterSaleReturn.tenant_id == tenant.id,
    )) == 2


@pytest.mark.asyncio
async def test_foreign_sale_is_not_enumerable(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    monkeypatch.setattr(settings, "COUNTER_SALES_ENABLED", True)
    tenant, owner, item = await seed_context(db_session)
    sale = await create_sale(client, tenant, owner, item)
    other_tenant, other_owner, _other_item = await seed_context(db_session)

    response = await client.get(
        f"{PREFIX}/counter-sales/{sale['id']}",
        headers=auth(other_owner, other_tenant),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_counter_sale_draft_rejects_retired_and_foreign_parts_identically(
    client, db_session, monkeypatch,
):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    monkeypatch.setattr(settings, "COUNTER_SALES_ENABLED", True)
    tenant, owner, retired_item = await seed_context(db_session)
    retired_item.ets_retired_at = datetime.now(timezone.utc)
    _foreign_tenant, _foreign_owner, foreign_item = await seed_context(db_session)
    await db_session.commit()

    async def create_with_part(inventory_id, key):
        return await client.post(
            f"{PREFIX}/counter-sales",
            headers={**auth(owner, tenant), "Idempotency-Key": key},
            json={
                "buyer_name": "Walk-in",
                "lines": [{"inventory_id": str(inventory_id), "quantity": 1}],
            },
        )

    retired = await create_with_part(
        retired_item.id, "db045-retired-part-boundary",
    )
    foreign = await create_with_part(
        foreign_item.id, "db045-foreign-part-boundary",
    )

    assert retired.status_code == foreign.status_code == 404
    assert retired.json()["detail"] == foreign.json()["detail"] == "Not found"
    assert retired.json().keys() == foreign.json().keys()
    assert await db_session.scalar(select(func.count(CounterSale.id)).where(
        CounterSale.tenant_id == tenant.id,
    )) == 0
    assert await db_session.scalar(select(func.count(CounterSaleLine.id)).where(
        CounterSaleLine.tenant_id == tenant.id,
    )) == 0


@pytest.mark.asyncio
async def test_activity_backfill_reruns_and_export_uses_identical_filters(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    tenant, owner, item = await seed_context(db_session, verified=False)
    item.name = "=Dangerous lifecycle filter"
    await apply_inventory_movement(
        db_session,
        item=item,
        quantity_delta=1,
        movement_type="adjustment",
        actor=owner,
        reason_code="backfill_proof",
        idempotency_key="db045-movement-v1",
    )
    await db_session.commit()

    first = await backfill_tenant_activity(db_session, tenant.id, batch_size=1)
    second = await backfill_tenant_activity(db_session, tenant.id, batch_size=1)
    assert first.state == second.state == "verified"
    assert first.source_counts == second.source_counts
    assert first.checksum == second.checksum

    params = {"inventory_id": str(item.id), "category": "stock"}
    listed = await client.get(f"{PREFIX}/activity-events", headers=auth(owner, tenant), params=params)
    exported = await client.get(f"{PREFIX}/activity-events/export.csv", headers=auth(owner, tenant), params=params)
    assert listed.status_code == exported.status_code == 200
    assert all(row["category"] == "stock" for row in listed.json()["items"])
    assert "backfill_proof" in exported.text
    assert "'=Dangerous lifecycle filter" in exported.text


@pytest.mark.asyncio
async def test_activity_snapshots_reject_unknown_or_sensitive_values():
    with pytest.raises(ValueError):
        safe_payment_snapshot({"card_number": "4111111111111111"})
    with pytest.raises(ValueError):
        safe_source_snapshot({"type": "counter_sale", "unknown": "value"})
    with pytest.raises(ValueError):
        safe_stock_snapshot({"physical_on_hand": "ten"})
    with pytest.raises(ValueError):
        safe_money_snapshot({"currency": "EUR"})


@pytest.mark.asyncio
async def test_completed_sale_receipt_is_printable_and_no_email_endpoint_exists(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    monkeypatch.setattr(settings, "COUNTER_SALES_ENABLED", True)
    tenant, owner, item = await seed_context(db_session)
    sale = await create_sale(client, tenant, owner, item, quantity=1)
    completed = await client.post(
        f"{PREFIX}/counter-sales/{sale['id']}/checkout",
        headers={**auth(owner, tenant), "Idempotency-Key": "db045-receipt-checkout"},
        json={"expected_version": sale["version"], "tender": "cash"},
    )
    assert completed.status_code == 200

    receipt = await client.get(f"{PREFIX}/counter-sales/{sale['id']}/receipt.pdf", headers=auth(owner, tenant))
    removed_email = await client.post(
        f"{PREFIX}/counter-sales/{sale['id']}/receipt/email",
        headers={**auth(owner, tenant), "Idempotency-Key": "db045-removed-email-endpoint"},
        json={"email": "buyer@example.test"},
    )
    assert receipt.status_code == 200
    assert receipt.headers["content-type"].startswith("application/pdf")
    assert removed_email.status_code in {404, 405}
