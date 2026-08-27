from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.security import create_access_token
from app.db.models.inventory import Inventory
from app.db.models.inventory_lifecycle import (
    CounterSale,
    CounterSaleLine,
    CounterSalePaymentAttempt,
    CounterSaleProviderEvent,
    CounterSaleRefund,
    CounterSaleReservation,
    CounterSaleReturn,
    CounterSaleReturnLine,
    PartActivityBackfillRun,
    PartActivityEvent,
)
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.notification import Notification
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.parts_operations import PartsOperationIdempotency
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.services import part_activity_backfill as backfill_module
from app.services.counter_sale_reporting_service import load_counter_sale_report_entries
from app.services import counter_sale_outbox_service as counter_sale_outbox
from app.services import quickbooks_accounting_service as qbo_accounting
from app.services import counter_sale_reconciliation_service as sale_reconciliation
from app.services.counter_sale_service import (
    create_or_replace_draft,
    create_return_claim,
    finalize_checkout_failure,
    finalize_checkout_success,
    prepare_checkout,
    price_sale,
)
from app.services.part_activity_service import (
    append_part_activity,
    safe_money_snapshot,
    safe_payment_snapshot,
    safe_source_snapshot,
    safe_stock_snapshot,
)
from app.services.parts_operations_service import apply_inventory_movement
from app.api.v1.endpoints import inventory_lifecycle as lifecycle_endpoint


PREFIX = "/api/v1/parts-operations"


def auth(user: User, tenant: Tenant) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token({'sub': str(user.id)}, tenant_id=str(tenant.id))}",
    }


async def seed_context(db_session, *, verified: bool = True):
    suffix = uuid4().hex
    tenant = Tenant(
        name="DB-045 Shop",
        slug=f"db045-{suffix}",
        is_active=True,
        parts_operations_enabled=True,
        counter_sales_enabled=True,
        sales_tax_rate=Decimal("8.000"),
        service_fee_rate=Decimal("3.000"),
    )
    db_session.add(tenant)
    await db_session.flush()
    user = User(
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
        stock_quantity=10,
        on_order_quantity=0,
        reorder_level=2,
        cost=Decimal("30.00"),
        selling_price=Decimal("50.00"),
        unit_type="each",
        is_placeholder=False,
    )
    db_session.add_all([user, item])
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
    return tenant, user, item


async def seed_draft_sale(db_session, *, quantity: int = 2):
    tenant, owner, item = await seed_context(db_session)
    sale, lines = await create_or_replace_draft(
        db_session,
        tenant=tenant,
        actor=owner,
        sale=None,
        customer_id=None,
        buyer_name="Walk-in",
        buyer_email=None,
        buyer_phone=None,
        line_inputs=[{"inventory_id": item.id, "quantity": quantity}],
    )
    await db_session.commit()
    return tenant, owner, item, sale, lines[0]


def test_counter_sale_money_allocation_is_decimal_and_cent_stable():
    sale = CounterSale(
        id=uuid4(),
        tenant_id=uuid4(),
        sale_number="CS-TEST",
        tax_rate_snapshot=Decimal("8.2500"),
        service_fee_rate_snapshot=Decimal("3.0000"),
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

    price_sale(sale, lines, fee_eligible=True)

    assert sale.charged_subtotal == Decimal("47.00")
    assert sale.discount_total == Decimal("3.00")
    assert sale.tax_total == Decimal("3.88")
    assert sale.service_fee_total == Decimal("1.53")
    assert sale.total == Decimal("52.41")
    assert sum((line.tax_allocation for line in lines), Decimal("0")) == sale.tax_total
    assert sum((line.fee_allocation for line in lines), Decimal("0")) == sale.service_fee_total
    assert sum((Decimal(unit["item"]) for line in lines for unit in line.unit_allocations), Decimal("0")) == sale.charged_subtotal


@pytest.mark.asyncio
async def test_qbo_sales_and_refund_receipts_preserve_each_allocated_cent(monkeypatch):
    tenant_id, owner_id, item_id = uuid4(), uuid4(), uuid4()
    tenant = Tenant(id=tenant_id, name="DB-045 QBO", slug=f"qbo-{uuid4().hex}")
    sale = CounterSale(
        id=uuid4(), tenant_id=tenant_id, sale_number="CS-QBO-045",
        status="completed", tax_rate_snapshot=Decimal("8.2500"),
        service_fee_rate_snapshot=Decimal("3.0000"),
        created_by_user_id=owner_id, updated_by_user_id=owner_id,
        completed_at=datetime.now(timezone.utc),
    )
    line = CounterSaleLine(
        id=uuid4(), tenant_id=tenant_id, sale_id=sale.id,
        inventory_id=item_id, quantity=3, sku_snapshot="QBO-045",
        name_snapshot="Cent allocation", unit_snapshot="each",
        unit_cost=Decimal("2.17"), list_unit_price=Decimal("10.00"),
        charged_unit_price=Decimal("9.99"),
    )
    price_sale(sale, [line], fee_eligible=True)
    connection = SimpleNamespace(walk_in_customer_id="walk-in-045")
    requests: list[tuple[str, dict]] = []

    async def fake_query(_connection, query):
        if " from Item " in f" {query} ":
            return [{"Id": "item-045"}]
        return []

    async def fake_request(_connection, method, path, *, json=None, **_kwargs):
        requests.append((path, json))
        if path == "salesreceipt":
            return {"SalesReceipt": {"Id": "qbo-sale-045"}}
        return {"RefundReceipt": {"Id": "qbo-refund-045"}}

    monkeypatch.setattr(qbo_accounting, "_query", fake_query)
    monkeypatch.setattr(qbo_accounting, "_request", fake_request)
    assert await qbo_accounting.sync_counter_sale_receipt(
        connection, tenant, sale, [line], None,
    ) == "qbo-sale-045"
    sale_payload = requests[-1][1]
    assert len(sale_payload["Line"]) == line.quantity
    assert all(
        Decimal(str(row["Amount"]))
        == Decimal(str(row["SalesItemLineDetail"]["UnitPrice"]))
        * row["SalesItemLineDetail"]["Qty"]
        for row in sale_payload["Line"]
    )
    assert sum(
        (Decimal(str(row["Amount"])) for row in sale_payload["Line"]),
        Decimal("0"),
    ) == Decimal(sale.total)

    selected = line.unit_allocations[:2]
    refund_amount = sum(
        (
            Decimal(row["item"]) + Decimal(row["tax"]) + Decimal(row["fee"])
            for row in selected
        ),
        Decimal("0"),
    )
    return_row = CounterSaleReturn(
        id=uuid4(), tenant_id=tenant_id, sale_id=sale.id, state="completed",
        item_amount=sum((Decimal(row["item"]) for row in selected), Decimal("0")),
        tax_amount=sum((Decimal(row["tax"]) for row in selected), Decimal("0")),
        fee_amount=sum((Decimal(row["fee"]) for row in selected), Decimal("0")),
        refund_amount=refund_amount, created_by_user_id=owner_id,
        reason="Bounded return", completed_at=datetime.now(timezone.utc),
    )
    return_line = CounterSaleReturnLine(
        tenant_id=tenant_id, return_id=return_row.id, sale_line_id=line.id,
        quantity=2, reason="Bounded return", disposition="restock",
        item_amount=return_row.item_amount, discount_amount=Decimal("0"),
        tax_amount=return_row.tax_amount, fee_amount=return_row.fee_amount,
        cost_amount=Decimal("4.34"),
        unit_ordinals=[int(row["ordinal"]) for row in selected],
    )
    assert await qbo_accounting.sync_counter_sale_refund_receipt(
        connection, tenant, sale, return_row, [return_line], {line.id: line}, None,
    ) == "qbo-refund-045"
    refund_payload = requests[-1][1]
    assert len(refund_payload["Line"]) == 2
    assert sum(
        (Decimal(str(row["Amount"])) for row in refund_payload["Line"]),
        Decimal("0"),
    ) == refund_amount


@pytest.mark.asyncio
async def test_counter_sale_list_uses_canonical_text_and_filter_bound_cursor(
    client, db_session, monkeypatch,
):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    monkeypatch.setattr(settings, "COUNTER_SALES_ENABLED", True)
    tenant, owner, _item = await seed_context(db_session)
    for index in range(2):
        db_session.add(CounterSale(
            tenant_id=tenant.id,
            sale_number=f"CS-FILTER-{index}",
            status="draft",
            buyer_name_snapshot="Filter Alpha",
            created_by_user_id=owner.id,
            updated_by_user_id=owner.id,
        ))
    await db_session.commit()
    headers = auth(owner, tenant)

    first = await client.get(
        f"{PREFIX}/counter-sales",
        headers=headers,
        params={"text": " Filter   Alpha ", "limit": 1},
    )
    assert first.status_code == 200
    assert len(first.json()["items"]) == 1
    cursor = first.json()["next_cursor"]
    assert cursor

    same_filter = await client.get(
        f"{PREFIX}/counter-sales",
        headers=headers,
        params={"text": "Filter Alpha", "limit": 1, "cursor": cursor},
    )
    assert same_filter.status_code == 200
    assert len(same_filter.json()["items"]) == 1

    changed_filter = await client.get(
        f"{PREFIX}/counter-sales",
        headers=headers,
        params={"text": "different", "limit": 1, "cursor": cursor},
    )
    assert changed_filter.status_code == 400

    compatibility = await client.get(
        f"{PREFIX}/counter-sales",
        headers=headers,
        params={"search": "Filter Alpha"},
    )
    assert compatibility.status_code == 200
    assert len(compatibility.json()["items"]) == 2

    conflicting = await client.get(
        f"{PREFIX}/counter-sales",
        headers=headers,
        params={"text": "Filter Alpha", "search": "different"},
    )
    assert conflicting.status_code == 422


@pytest.mark.asyncio
async def test_checkout_same_key_resumes_indeterminate_stripe_attempt_and_replays_terminal_envelope(
    client, db_session, monkeypatch,
):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    monkeypatch.setattr(settings, "COUNTER_SALES_ENABLED", True)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_db045")
    tenant, owner, _item, sale, _line = await seed_draft_sale(db_session, quantity=1)
    tenant.stripe_account_id = "acct_db045"
    tenant.stripe_onboarding_complete = True
    await db_session.commit()
    calls: list[str] = []

    def create_intent(**kwargs):
        calls.append(kwargs["idempotency_key"])
        if len(calls) == 1:
            raise lifecycle_endpoint.stripe.error.APIConnectionError("provider timeout")
        return SimpleNamespace(
            id="pi_db045_resume", status="requires_confirmation",
            client_secret="pi_secret_only_returned_once", amount_received=0,
            currency="usd",
        )

    monkeypatch.setattr(lifecycle_endpoint.stripe.PaymentIntent, "create", create_intent)
    headers = {**auth(owner, tenant), "Idempotency-Key": "checkout-resume-045"}
    body = {"expected_version": sale.version, "tender": "stripe"}
    first = await client.post(
        f"{PREFIX}/counter-sales/{sale.id}/checkout", headers=headers, json=body,
    )
    assert first.status_code == 503

    resumed = await client.post(
        f"{PREFIX}/counter-sales/{sale.id}/checkout", headers=headers, json=body,
    )
    assert resumed.status_code == 202
    assert resumed.json()["payment"]["client_secret"] == "pi_secret_only_returned_once"
    attempt_id = resumed.json()["payment"]["attempt_id"]

    replayed = await client.post(
        f"{PREFIX}/counter-sales/{sale.id}/checkout", headers=headers, json=body,
    )
    assert replayed.status_code == 202
    assert replayed.json()["payment"]["attempt_id"] == attempt_id
    assert replayed.json()["payment"]["client_secret"] is None
    assert len(calls) == 2
    assert await db_session.scalar(select(func.count(CounterSalePaymentAttempt.id))) == 1
    idempotency = await db_session.scalar(select(PartsOperationIdempotency).where(
        PartsOperationIdempotency.idempotency_key == "checkout-resume-045",
    ))
    assert idempotency.completed_at is not None
    assert "pi_secret_only_returned_once" not in (idempotency.response_body or "")


@pytest.mark.asyncio
async def test_stripe_elements_initial_requires_payment_method_keeps_hold_and_fee_inclusive_preview(
    client, db_session, monkeypatch,
):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    monkeypatch.setattr(settings, "COUNTER_SALES_ENABLED", True)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_db045")
    tenant, owner, item, sale, _line = await seed_draft_sale(db_session, quantity=1)
    tenant.stripe_account_id = "acct_elements_045"
    tenant.stripe_onboarding_complete = True
    await db_session.commit()

    monkeypatch.setattr(
        lifecycle_endpoint.stripe.PaymentIntent,
        "create",
        lambda **_kwargs: SimpleNamespace(
            id="pi_elements_045", status="requires_payment_method",
            client_secret="pi_elements_secret_045", amount_received=0,
            currency="usd",
        ),
    )
    response = await client.post(
        f"{PREFIX}/counter-sales/{sale.id}/checkout",
        headers={**auth(owner, tenant), "Idempotency-Key": "elements-create-045"},
        json={"expected_version": sale.version, "tender": "stripe"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["sale"]["status"] == "awaiting_payment"
    assert body["payment"]["state"] == "pending"
    assert body["payment"]["client_secret"] == "pi_elements_secret_045"
    assert Decimal(body["sale"]["service_fee_amount"]) > 0
    persisted_sale = await db_session.get(CounterSale, sale.id)
    reservation = await db_session.scalar(select(CounterSaleReservation).where(
        CounterSaleReservation.sale_id == sale.id,
    ))
    await db_session.refresh(persisted_sale)
    await db_session.refresh(item)
    assert persisted_sale.status == "awaiting_payment"
    assert reservation.state == "held"
    assert item.stock_quantity == 10


@pytest.mark.asyncio
async def test_counter_sale_reporting_nets_returns_and_only_reverses_restocked_cogs(db_session):
    tenant, owner, item = await seed_context(db_session)
    completed_at = datetime(2026, 8, 26, 15, 0, tzinfo=timezone.utc)
    sale = CounterSale(
        tenant_id=tenant.id,
        sale_number="CS-REPORT",
        status="returned",
        customer_id=None,
        buyer_name_snapshot="Walk-in",
        charged_subtotal=Decimal("100.00"),
        discount_total=Decimal("10.00"),
        tax_total=Decimal("8.00"),
        service_fee_total=Decimal("3.00"),
        total=Decimal("111.00"),
        created_by_user_id=owner.id,
        updated_by_user_id=owner.id,
        completed_by_user_id=owner.id,
        completed_at=completed_at,
    )
    db_session.add(sale)
    await db_session.flush()
    line = CounterSaleLine(
        tenant_id=tenant.id,
        sale_id=sale.id,
        inventory_id=item.id,
        quantity=2,
        sku_snapshot=item.sku,
        name_snapshot=item.name,
        unit_snapshot="each",
        unit_cost=Decimal("30.00"),
        list_unit_price=Decimal("55.00"),
        charged_unit_price=Decimal("50.00"),
        discount_total=Decimal("10.00"),
        item_subtotal=Decimal("100.00"),
        tax_allocation=Decimal("8.00"),
        fee_allocation=Decimal("3.00"),
        total=Decimal("111.00"),
        cost_total=Decimal("60.00"),
        unit_allocations=[],
    )
    db_session.add(line)
    await db_session.flush()
    for disposition, hour in (("restock", 16), ("damaged", 17)):
        return_row = CounterSaleReturn(
            tenant_id=tenant.id,
            sale_id=sale.id,
            state="completed",
            version=2,
            item_amount=Decimal("50.00"),
            tax_amount=Decimal("4.00"),
            fee_amount=Decimal("1.50"),
            refund_amount=Decimal("55.50"),
            created_by_user_id=owner.id,
            reason="Customer return",
            completed_at=datetime(2026, 8, 26, hour, 0, tzinfo=timezone.utc),
        )
        db_session.add(return_row)
        await db_session.flush()
        db_session.add(CounterSaleReturnLine(
            tenant_id=tenant.id,
            return_id=return_row.id,
            sale_line_id=line.id,
            quantity=1,
            reason="Customer return",
            disposition=disposition,
            item_amount=Decimal("50.00"),
            discount_amount=Decimal("5.00"),
            tax_amount=Decimal("4.00"),
            fee_amount=Decimal("1.50"),
            cost_amount=Decimal("30.00"),
            unit_ordinals=[1 if disposition == "restock" else 2],
        ))
    await db_session.commit()

    entries = await load_counter_sale_report_entries(
        db_session,
        tenant_id=tenant.id,
        start=completed_at.date(),
        end=completed_at.date(),
    )

    assert [entry.entry_type for entry in entries].count("sale") == 1
    assert [entry.entry_type for entry in entries].count("return") == 2
    assert sum((entry.item_sales for entry in entries), Decimal("0")) == Decimal("0.00")
    assert sum((entry.tax for entry in entries), Decimal("0")) == Decimal("0.00")
    assert sum((entry.fees for entry in entries), Decimal("0")) == Decimal("0.00")
    assert sum((entry.cogs for entry in entries), Decimal("0")) == Decimal("30.00")
    assert sum((entry.margin for entry in entries), Decimal("0")) == Decimal("-30.00")


@pytest.mark.asyncio
async def test_activity_backfill_resumes_keyset_batch_and_reruns_without_duplicates(
    db_session, monkeypatch,
):
    tenant, _owner, first_item = await seed_context(db_session, verified=False)
    historical_created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    first_item.created_at = historical_created_at
    second_item = Inventory(
        tenant_id=tenant.id,
        sku="FILTER-046",
        name="Second Filter",
        stock_quantity=4,
        on_order_quantity=0,
        reorder_level=1,
        cost=Decimal("12.00"),
        selling_price=Decimal("20.00"),
        unit_type="each",
        is_placeholder=False,
        created_at=historical_created_at,
    )
    db_session.add(second_item)
    await db_session.commit()
    tenant_id = tenant.id
    first_item_id = first_item.id
    second_item_id = second_item.id

    original_append = backfill_module._append_source
    calls = 0

    async def interrupt_second_batch(db, kind, row, **kwargs):
        nonlocal calls
        if kind == "baseline":
            calls += 1
            if calls == 2:
                raise RuntimeError("simulated interruption")
        return await original_append(db, kind, row, **kwargs)

    monkeypatch.setattr(backfill_module, "_append_source", interrupt_second_batch)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        await backfill_module.backfill_tenant_activity(
            db_session, tenant_id, batch_size=1,
        )
    await db_session.rollback()
    interrupted_run = (await db_session.execute(select(PartActivityBackfillRun).where(
        PartActivityBackfillRun.tenant_id == tenant_id,
    ))).scalar_one()
    assert interrupted_run.state == "running"
    assert interrupted_run.batch_cursor.startswith("baseline:")
    assert await db_session.scalar(select(func.count(PartActivityEvent.id))) == 1

    monkeypatch.setattr(backfill_module, "_append_source", original_append)
    resumed = await backfill_module.backfill_tenant_activity(
        db_session, tenant_id, batch_size=1,
    )
    assert resumed.run_id == interrupted_run.id
    assert resumed.state == "verified"
    assert await db_session.scalar(select(func.count(PartActivityEvent.id))) == 2
    baseline_events = list((await db_session.execute(
        select(PartActivityEvent).where(PartActivityEvent.origin == "baseline")
    )).scalars().all())
    resumed_run = await db_session.get(PartActivityBackfillRun, resumed.run_id)
    assert len(baseline_events) == 2
    assert all(
        event.occurred_at.replace(tzinfo=None) == resumed_run.cutoff_at.replace(tzinfo=None)
        for event in baseline_events
    )
    assert all(
        event.occurred_at.replace(tzinfo=None) > historical_created_at.replace(tzinfo=None)
        for event in baseline_events
    )

    rerun = await backfill_module.backfill_tenant_activity(
        db_session, tenant_id, batch_size=1,
    )
    assert rerun.run_id != resumed.run_id
    assert rerun.state == "verified"
    assert rerun.inserted_counts.get("baseline", 0) == 0
    assert rerun.duplicate_count == 0
    assert await db_session.scalar(select(func.count(PartActivityEvent.id))) == 2
    assert {first_item_id, second_item_id} == set((await db_session.execute(
        select(PartActivityEvent.inventory_id)
    )).scalars().all())


@pytest.mark.asyncio
async def test_activity_backfill_reconciles_movement_already_written_live(db_session):
    tenant, owner, item = await seed_context(db_session, verified=False)
    source_id = uuid4()
    movement = await apply_inventory_movement(
        db_session,
        item=item,
        quantity_delta=2,
        movement_type="manual_adjustment",
        actor=owner,
        source_type="inventory_adjustment",
        source_id=source_id,
        reason_code="cycle_count",
        note="Counted before Activity backfill",
        idempotency_key="db045-live-movement-before-backfill",
    )
    await db_session.commit()

    event_key = f"inventory_movement:{movement.id}:v1"
    live_event = (await db_session.execute(select(PartActivityEvent).where(
        PartActivityEvent.tenant_id == tenant.id,
        PartActivityEvent.idempotency_key == event_key,
    ))).scalar_one()
    assert live_event.origin == "live"
    assert live_event.inventory_id == item.id
    assert live_event.source_type == "inventory_adjustment"
    assert live_event.source_id == source_id

    result = await backfill_module.backfill_tenant_activity(
        db_session, tenant.id, batch_size=1,
    )

    assert result.state == "verified"
    assert result.source_counts["movement"] == 1
    assert result.inserted_counts.get("movement", 0) == 0
    assert await db_session.scalar(select(func.count(PartActivityEvent.id)).where(
        PartActivityEvent.tenant_id == tenant.id,
        PartActivityEvent.idempotency_key == event_key,
    )) == 1
    persisted_event = (await db_session.execute(select(PartActivityEvent).where(
        PartActivityEvent.tenant_id == tenant.id,
        PartActivityEvent.idempotency_key == event_key,
    ))).scalar_one()
    assert persisted_event.origin == "live"


def test_activity_snapshot_schemas_reject_unknown_sensitive_and_invalid_values():
    assert safe_stock_snapshot({
        "physical_on_hand": 4, "held_for_checkout": 1,
        "available_to_sell": 3, "delta": -1, "bucket": "on_hand",
        "stock_version": 2,
    })["available_to_sell"] == 3
    assert safe_money_snapshot({
        "currency": "USD", "unit_price": "10", "line_total": "20.125",
    }) == {"currency": "USD", "unit_price": "10.00", "line_total": "20.13"}
    assert safe_payment_snapshot({"tender": "stripe", "last_four": "4242"})
    assert safe_source_snapshot({"po_number": "PO-1", "stock_shortage_override": False})
    for unsafe in (
        lambda: safe_stock_snapshot({"physical_on_hand": 1, "held_for_checkout": 0, "available_to_sell": 1, "delta": 0, "bucket": "on_hand", "client_secret": "x"}),
        lambda: safe_money_snapshot({"currency": "USD", "api_token": "x"}),
        lambda: safe_payment_snapshot({"tender": "stripe", "card_number": "4242424242424242"}),
        lambda: safe_source_snapshot({"authorization": "Bearer secret"}),
    ):
        with pytest.raises(ValueError, match="Sensitive"):
            unsafe()
    with pytest.raises(ValueError, match="last-four"):
        safe_payment_snapshot({"tender": "stripe", "last_four": "424242"})


@pytest.mark.asyncio
async def test_activity_uses_event_time_part_identity_search_export_cursor_and_deep_link(
    client, db_session, monkeypatch,
):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    tenant, owner, item = await seed_context(db_session)
    sale_id = uuid4()
    event_time = datetime.now(timezone.utc)
    first = await append_part_activity(
        db_session, tenant_id=tenant.id, inventory_id=item.id,
        category="catalog", event_type="part.identity_changed",
        idempotency_key=f"identity:{item.id}:1", actor=owner,
        source_type="counter_sale", source_id=sale_id,
        source_number="CS-SNAPSHOT", reason_code="catalog_correction",
        note="Preserve original identity", before={"name": "Earlier name"},
        after={"name": item.name},
        occurred_at=event_time - timedelta(seconds=1),
    )
    await append_part_activity(
        db_session, tenant_id=tenant.id, inventory_id=item.id,
        category="catalog", event_type="part.location_changed",
        idempotency_key=f"identity:{item.id}:2", actor=owner,
        source_type="inventory", source_id=item.id,
        before={"location": None}, after={"location": "A-1"},
        occurred_at=event_time,
    )
    old_sku, old_name = item.sku, item.name
    item.sku, item.name = "RENAMED-045", "Renamed current catalog value"
    await db_session.commit()
    headers = auth(owner, tenant)

    response = await client.get(
        f"{PREFIX}/activity-events", headers=headers,
        params={"search": old_name, "limit": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["part"] == {"id": str(item.id), "sku": old_sku, "name": old_name}
    assert body["items"][0]["actor"]["name"] == "Counter Owner"
    assert body["next_cursor"]
    older = await client.get(
        f"{PREFIX}/activity-events", headers=headers,
        params={"search": old_name, "limit": 1, "cursor": body["next_cursor"]},
    )
    assert older.status_code == 200
    assert older.json()["items"][0]["id"] != body["items"][0]["id"]
    identity = await client.get(
        f"{PREFIX}/activity-events", headers=headers,
        params={"search": old_name, "event_type": "part.identity_changed"},
    )
    assert identity.status_code == 200
    identity_event = identity.json()["items"][0]
    assert identity_event["reason"] == {
        "code": "catalog_correction", "note": "Preserve original identity",
    }
    assert identity_event["source"]["href"] == (
        f"/dashboard/garage/inventory/sales?sale={sale_id}"
    )
    assert (await client.get(
        f"{PREFIX}/activity-events", headers=headers,
        params={"search": "Renamed current catalog value"},
    )).json()["items"] == []
    changed_cursor = await client.get(
        f"{PREFIX}/activity-events", headers=headers,
        params={"category": "stock", "cursor": body["next_cursor"]},
    )
    assert changed_cursor.status_code == 400
    exported = await client.get(
        f"{PREFIX}/activity-events/export.csv", headers=headers,
        params={"search": old_sku},
    )
    assert exported.status_code == 200
    assert old_sku in exported.text and old_name in exported.text
    assert "RENAMED-045" not in exported.text
    assert first.part_sku_snapshot == old_sku


@pytest.mark.asyncio
async def test_activity_noop_and_tenant_role_deleted_disabled_are_non_enumerating(
    client, db_session, monkeypatch,
):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    tenant, owner, item = await seed_context(db_session)
    with pytest.raises(ValueError, match="no-op"):
        await append_part_activity(
            db_session, tenant_id=tenant.id, inventory_id=item.id,
            category="catalog", event_type="part.location_changed",
            idempotency_key=f"noop:{item.id}", actor=owner,
            before={"location": "A-1"}, after={"location": "A-1"},
        )
    suffix = uuid4().hex
    mechanic = User(
        tenant_id=tenant.id, email=f"mechanic-{suffix}@example.test",
        hashed_password="x", first_name="Mech", last_name="User",
        role=UserRole.MECHANIC, is_active=True, is_verified=True,
    )
    foreign_tenant = Tenant(
        name="Foreign DB045", slug=f"foreign-{suffix}", is_active=True,
        parts_operations_enabled=True, counter_sales_enabled=True,
    )
    db_session.add_all([mechanic, foreign_tenant])
    await db_session.flush()
    foreign_owner = User(
        tenant_id=foreign_tenant.id, email=f"owner-{suffix}@example.test",
        hashed_password="x", first_name="Foreign", last_name="Owner",
        role=UserRole.GARAGE_OWNER, is_active=True, is_verified=True,
    )
    db_session.add(foreign_owner)
    await db_session.commit()
    missing = await client.get(
        f"{PREFIX}/parts/{uuid4()}/lifecycle-summary", headers=auth(owner, tenant),
    )
    foreign = await client.get(
        f"{PREFIX}/parts/{item.id}/lifecycle-summary",
        headers=auth(foreign_owner, foreign_tenant),
    )
    assert missing.status_code == foreign.status_code == 404
    assert missing.json()["detail"] == foreign.json()["detail"] == "Not found"
    assert (await client.get(
        f"{PREFIX}/activity-events", headers=auth(mechanic, tenant),
    )).status_code == 403
    item.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()
    deleted = await client.get(
        f"{PREFIX}/parts/{item.id}/lifecycle-summary", headers=auth(owner, tenant),
    )
    assert deleted.status_code == 404 and deleted.json()["detail"] == "Not found"
    tenant.parts_operations_enabled = False
    await db_session.commit()
    assert (await client.get(
        f"{PREFIX}/activity-events", headers=auth(owner, tenant),
    )).status_code == 404


@pytest.mark.asyncio
async def test_reservation_failure_retry_reuses_identity_and_prevents_oversell(db_session):
    tenant, owner, item, sale, _line = await seed_draft_sale(db_session, quantity=6)
    sale, _lines, first_attempt = await prepare_checkout(
        db_session, tenant=tenant, sale_id=sale.id, actor=owner,
        expected_version=sale.version, tender="stripe", idempotency_key="checkout-1",
    )
    await db_session.commit()
    reservation = await db_session.scalar(select(CounterSaleReservation).where(
        CounterSaleReservation.sale_id == sale.id,
    ))
    reservation_id = reservation.id
    await finalize_checkout_failure(
        db_session, tenant_id=tenant.id, sale_id=sale.id,
        attempt_id=first_attempt.id, failure_code="card_declined", actor=owner,
    )
    await db_session.commit()
    sale, _lines, _retry = await prepare_checkout(
        db_session, tenant=tenant, sale_id=sale.id, actor=owner,
        expected_version=sale.version, tender="stripe", idempotency_key="checkout-2",
    )
    await db_session.commit()
    rearmed = await db_session.scalar(select(CounterSaleReservation).where(
        CounterSaleReservation.sale_id == sale.id,
    ))
    assert rearmed.id == reservation_id
    assert rearmed.state == "held" and rearmed.version == 2

    other, _other_lines = await create_or_replace_draft(
        db_session, tenant=tenant, actor=owner, sale=None, customer_id=None,
        buyer_name="Other", buyer_email=None, buyer_phone=None,
        line_inputs=[{"inventory_id": item.id, "quantity": 5}],
    )
    await db_session.commit()
    with pytest.raises(HTTPException) as error:
        await prepare_checkout(
            db_session, tenant=tenant, sale_id=other.id, actor=owner,
            expected_version=other.version, tender="stripe", idempotency_key="checkout-other",
        )
    assert error.value.status_code == 409
    assert item.stock_quantity == 10


@pytest.mark.asyncio
async def test_expired_reservation_checks_provider_before_release_and_definitive_failure_releases(
    db_session, monkeypatch,
):
    tenant, owner, item, sale, _line = await seed_draft_sale(db_session, quantity=2)
    sale, _lines, attempt = await prepare_checkout(
        db_session, tenant=tenant, sale_id=sale.id, actor=owner,
        expected_version=sale.version, tender="stripe", idempotency_key="expiry-045",
    )
    attempt.provider_intent_id = "pi_expiry_045"
    reservation = await db_session.scalar(select(CounterSaleReservation).where(
        CounterSaleReservation.sale_id == sale.id,
    ))
    reservation.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()

    def pending_intent(*_args, **_kwargs):
        return SimpleNamespace(
            id="pi_expiry_045", status="processing", amount_received=0,
            metadata={
                "counter_sale_id": str(sale.id), "tenant_id": str(tenant.id),
                "attempt_id": str(attempt.id),
            },
        )

    monkeypatch.setattr(
        sale_reconciliation.stripe.PaymentIntent, "retrieve", pending_intent,
    )
    assert await sale_reconciliation._reconcile_expired_attempt(
        db_session, attempt.id,
    ) == "unknown"
    await db_session.refresh(reservation)
    await db_session.refresh(item)
    assert reservation.state == "held"
    assert reservation.expires_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)
    assert item.stock_quantity == 10

    def failed_intent(*_args, **_kwargs):
        return SimpleNamespace(
            id="pi_expiry_045", status="requires_payment_method", amount_received=0,
            metadata={
                "counter_sale_id": str(sale.id), "tenant_id": str(tenant.id),
                "attempt_id": str(attempt.id),
            },
        )

    monkeypatch.setattr(
        sale_reconciliation.stripe.PaymentIntent, "retrieve", failed_intent,
    )
    assert await sale_reconciliation._reconcile_expired_attempt(
        db_session, attempt.id,
    ) == "failed"
    await db_session.refresh(reservation)
    await db_session.refresh(sale)
    await db_session.refresh(item)
    assert reservation.state == "released"
    assert sale.status == "draft"
    assert item.stock_quantity == 10


@pytest.mark.asyncio
async def test_late_provider_success_is_idempotently_compensated_without_stock_mutation(
    db_session, monkeypatch,
):
    tenant, owner, item, sale, _line = await seed_draft_sale(db_session, quantity=2)
    tenant.stripe_account_id = f"acct_{uuid4().hex}"
    tenant.stripe_onboarding_complete = True
    sale, _lines, attempt = await prepare_checkout(
        db_session, tenant=tenant, sale_id=sale.id, actor=owner,
        expected_version=sale.version, tender="stripe", idempotency_key="late-success",
    )
    attempt.provider_intent_id = "pi_expected"
    await db_session.commit()
    await finalize_checkout_failure(
        db_session, tenant_id=tenant.id, sale_id=sale.id,
        attempt_id=attempt.id, failure_code="card_declined", actor=owner,
    )
    await db_session.commit()
    tenant_id, item_id, sale_id, attempt_id, attempt_amount = (
        tenant.id, item.id, sale.id, attempt.id, attempt.amount,
    )
    with pytest.raises(HTTPException) as mismatch:
        await finalize_checkout_success(
            db_session, tenant_id=tenant.id, sale_id=sale.id,
            attempt_id=attempt.id, provider_amount=attempt.amount,
            currency="USD", provider_status="succeeded",
            provider_object_id="pi_wrong", actor=owner,
        )
    assert mismatch.value.status_code == 409
    assert mismatch.value.detail == "Provider object identity mismatch"
    await db_session.rollback()
    item = await db_session.get(Inventory, item_id)
    sale = await db_session.get(CounterSale, sale_id)
    attempt = await db_session.get(CounterSalePaymentAttempt, attempt_id)
    for _ in range(2):
        await finalize_checkout_success(
            db_session, tenant_id=tenant_id, sale_id=sale_id,
            attempt_id=attempt_id, provider_amount=attempt_amount,
            currency="USD", provider_status="succeeded",
            provider_object_id="pi_expected", actor=owner,
        )
        await db_session.commit()
    await db_session.refresh(item)
    await db_session.refresh(sale)
    await db_session.refresh(attempt)
    assert item.stock_quantity == 10
    assert sale.status == "draft"
    assert attempt.state == "compensating_refund_pending"
    assert await db_session.scalar(select(func.count(ProviderOutboxEvent.id)).where(
        ProviderOutboxEvent.event_type == "counter_sale.compensating_refund.v1",
    )) == 1
    assert await db_session.scalar(select(func.count(PartActivityEvent.id)).where(
        PartActivityEvent.event_type == "counter_sale.late_success_refunded",
    )) == 0
    outbox = await db_session.scalar(select(ProviderOutboxEvent).where(
        ProviderOutboxEvent.event_type == "counter_sale.compensating_refund.v1",
    ))
    refund_calls: list[dict] = []

    def refund_create(**kwargs):
        refund_calls.append(kwargs)
        return SimpleNamespace(id="re_compensated_045", status="succeeded")

    monkeypatch.setattr(counter_sale_outbox.stripe.Refund, "create", refund_create)
    await counter_sale_outbox._process_compensation(db_session, outbox)
    await db_session.commit()
    await counter_sale_outbox._process_compensation(db_session, outbox)
    await db_session.commit()
    await db_session.refresh(item)
    await db_session.refresh(attempt)
    assert item.stock_quantity == 10
    assert attempt.state == "compensated"
    assert len(refund_calls) == 1
    assert refund_calls[0]["idempotency_key"] == f"db045-compensating-refund-{attempt.id}"
    assert await db_session.scalar(select(func.count(PartActivityEvent.id)).where(
        PartActivityEvent.event_type == "counter_sale.late_success_refunded",
    )) == 1


@pytest.mark.asyncio
async def test_outbox_rejects_cross_tenant_aggregates_before_all_provider_io(
    db_session, _db_engine, monkeypatch,
):
    event_tenant, _event_owner, _event_item = await seed_context(db_session)
    event_tenant.stripe_account_id = f"acct_{uuid4().hex}"
    event_tenant.stripe_onboarding_complete = True
    db_session.add(QuickBooksConnection(
        tenant_id=event_tenant.id,
        realm_id=f"realm-{uuid4().hex}",
        status="connected",
    ))
    (
        foreign_tenant, foreign_owner, _foreign_item,
        foreign_sale, _foreign_line,
    ) = await seed_draft_sale(db_session, quantity=1)
    foreign_sale.accounting_sync_status = "queued"
    foreign_sale.receipt_email_to = "walk-in@example.test"
    foreign_sale.receipt_snapshot = {"lines": [], "total": "50.00"}
    stripe_attempt = CounterSalePaymentAttempt(
        tenant_id=foreign_tenant.id,
        sale_id=foreign_sale.id,
        tender="stripe",
        state="compensating_refund_pending",
        amount=Decimal("50.00"),
        currency="USD",
        request_fingerprint="a" * 64,
        idempotency_key="foreign-stripe-compensation",
        provider_intent_id="pi_foreign_045",
        actor_user_id=foreign_owner.id,
    )
    qbp_attempt = CounterSalePaymentAttempt(
        tenant_id=foreign_tenant.id,
        sale_id=foreign_sale.id,
        tender="quickbooks_payments",
        state="compensating_refund_pending",
        amount=Decimal("50.00"),
        currency="USD",
        request_fingerprint="b" * 64,
        idempotency_key="foreign-qbp-compensation",
        provider_charge_id="charge_foreign_045",
        actor_user_id=foreign_owner.id,
    )
    return_row = CounterSaleReturn(
        tenant_id=foreign_tenant.id,
        sale_id=foreign_sale.id,
        state="completed",
        version=2,
        item_amount=Decimal("50.00"),
        tax_amount=Decimal("0.00"),
        fee_amount=Decimal("0.00"),
        refund_amount=Decimal("50.00"),
        created_by_user_id=foreign_owner.id,
        reason="Foreign tenant return",
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add_all([stripe_attempt, qbp_attempt, return_row])
    await db_session.flush()
    outbox_rows = [
        ProviderOutboxEvent(
            tenant_id=event_tenant.id,
            event_type="quickbooks.counter_sale.sync.v1",
            aggregate_type="counter_sale",
            aggregate_id=foreign_sale.id,
            payload={"sale_id": str(foreign_sale.id), "payload_version": 1},
            idempotency_key="cross-tenant-qbo-sale",
            status="pending",
            attempt_count=settings.PROVIDER_OUTBOX_MAX_ATTEMPTS - 1,
            available_at=datetime.now(timezone.utc),
        ),
        ProviderOutboxEvent(
            tenant_id=event_tenant.id,
            event_type="quickbooks.counter_sale_return.sync.v1",
            aggregate_type="counter_sale_return",
            aggregate_id=return_row.id,
            payload={
                "sale_id": str(foreign_sale.id),
                "return_id": str(return_row.id),
                "payload_version": 1,
            },
            idempotency_key="cross-tenant-qbo-return",
            status="pending",
            available_at=datetime.now(timezone.utc),
        ),
        ProviderOutboxEvent(
            tenant_id=event_tenant.id,
            event_type="counter_sale.receipt.email.v1",
            aggregate_type="counter_sale",
            aggregate_id=foreign_sale.id,
            payload={"sale_id": str(foreign_sale.id), "payload_version": 1},
            idempotency_key="cross-tenant-receipt-email",
            status="pending",
            available_at=datetime.now(timezone.utc),
        ),
        ProviderOutboxEvent(
            tenant_id=event_tenant.id,
            event_type="counter_sale.compensating_refund.v1",
            aggregate_type="counter_sale_payment_attempt",
            aggregate_id=stripe_attempt.id,
            payload={
                "sale_id": str(foreign_sale.id),
                "attempt_id": str(stripe_attempt.id),
                "amount": "50.00",
                "tender": "stripe",
            },
            idempotency_key="cross-tenant-stripe-refund",
            status="pending",
            available_at=datetime.now(timezone.utc),
        ),
        ProviderOutboxEvent(
            tenant_id=event_tenant.id,
            event_type="counter_sale.compensating_refund.v1",
            aggregate_type="counter_sale_payment_attempt",
            aggregate_id=qbp_attempt.id,
            payload={
                "sale_id": str(foreign_sale.id),
                "attempt_id": str(qbp_attempt.id),
                "amount": "50.00",
                "tender": "quickbooks_payments",
            },
            idempotency_key="cross-tenant-qbp-refund",
            status="pending",
            available_at=datetime.now(timezone.utc),
        ),
    ]
    db_session.add_all(outbox_rows)
    await db_session.commit()
    ids = [row.id for row in outbox_rows]
    foreign_sale_id = foreign_sale.id
    return_id = return_row.id
    stripe_attempt_id = stripe_attempt.id
    qbp_attempt_id = qbp_attempt.id

    calls = {"qbo_sale": 0, "qbo_return": 0, "stripe": 0, "qbp": 0, "email": 0}

    async def qbo_sale_call(*args, **kwargs):
        calls["qbo_sale"] += 1

    async def qbo_return_call(*args, **kwargs):
        calls["qbo_return"] += 1

    def stripe_call(**kwargs):
        calls["stripe"] += 1
        return SimpleNamespace(id="re_should_not_run", status="succeeded")

    async def qbp_call(**kwargs):
        calls["qbp"] += 1
        return SimpleNamespace(id="refund_should_not_run", status="SUCCEEDED")

    async def email_call(*args, **kwargs):
        calls["email"] += 1

    monkeypatch.setattr(counter_sale_outbox, "sync_counter_sale_receipt", qbo_sale_call)
    monkeypatch.setattr(counter_sale_outbox, "sync_counter_sale_refund_receipt", qbo_return_call)
    monkeypatch.setattr(counter_sale_outbox.stripe.Refund, "create", stripe_call)
    monkeypatch.setattr(counter_sale_outbox, "refund_charge", qbp_call)
    monkeypatch.setattr(counter_sale_outbox, "enqueue_email_notification", email_call)

    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    result = await counter_sale_outbox.process_counter_sale_outbox_events(
        session_factory=factory, batch_size=10,
    )

    assert result == {"claimed": 5, "succeeded": 0, "retried": 0, "dead": 5}
    assert calls == {"qbo_sale": 0, "qbo_return": 0, "stripe": 0, "qbp": 0, "email": 0}
    db_session.expire_all()
    events = list((await db_session.execute(select(ProviderOutboxEvent).where(
        ProviderOutboxEvent.id.in_(ids),
    ))).scalars().all())
    assert len(events) == 5
    assert all(row.status == "dead" and row.completed_at is not None for row in events)
    assert {
        row.last_error for row in events
    } == {
        "PermanentOutboxContextError: Provider outbox context is unavailable"
    }
    persisted_sale = await db_session.get(CounterSale, foreign_sale_id)
    persisted_stripe_attempt = await db_session.get(
        CounterSalePaymentAttempt, stripe_attempt_id,
    )
    persisted_qbp_attempt = await db_session.get(
        CounterSalePaymentAttempt, qbp_attempt_id,
    )
    persisted_return = await db_session.get(CounterSaleReturn, return_id)
    assert persisted_sale.accounting_sync_status == "queued"
    assert persisted_stripe_attempt.state == "compensating_refund_pending"
    assert persisted_stripe_attempt.provider_reference is None
    assert persisted_qbp_attempt.state == "compensating_refund_pending"
    assert persisted_qbp_attempt.provider_reference is None
    assert persisted_return.accounting_refund_receipt_id is None
    assert await db_session.scalar(select(func.count(Notification.id))) == 0


@pytest.mark.asyncio
async def test_duplicate_finalization_decrements_stock_exactly_once(db_session):
    tenant, owner, item, sale, _line = await seed_draft_sale(db_session, quantity=2)
    sale, _lines, attempt = await prepare_checkout(
        db_session, tenant=tenant, sale_id=sale.id, actor=owner,
        expected_version=sale.version, tender="cash", idempotency_key="manual-once",
    )
    await db_session.commit()
    for _ in range(2):
        await finalize_checkout_success(
            db_session, tenant_id=tenant.id, sale_id=sale.id,
            attempt_id=attempt.id, provider_amount=attempt.amount,
            currency="USD", provider_status="completed",
            provider_object_id=None, actor=owner,
        )
        await db_session.commit()
    await db_session.refresh(item)
    assert item.stock_quantity == 8
    assert await db_session.scalar(select(func.count(PartActivityEvent.id)).where(
        PartActivityEvent.event_type == "counter_sale.completed",
    )) == 1


@pytest.mark.asyncio
async def test_return_duplicate_lines_ceiling_partial_full_and_damaged_stock(db_session):
    tenant, owner, item, sale, line = await seed_draft_sale(db_session, quantity=2)
    sale.status = "completed"
    sale.completed_at = datetime.now(timezone.utc)
    attempt = CounterSalePaymentAttempt(
        tenant_id=tenant.id, sale_id=sale.id, tender="cash", state="succeeded",
        amount=sale.total, idempotency_key="settled-cash",
        request_fingerprint="settled", attempt_number=1,
        actor_user_id=owner.id,
    )
    db_session.add(attempt)
    await db_session.commit()
    tenant_id, owner_id, item_id, sale_id, line_id = (
        tenant.id, owner.id, item.id, sale.id, line.id,
    )
    duplicated = [
        {"sale_line_id": line.id, "quantity": 1, "reason": "Duplicate one", "disposition": "restock"},
        {"sale_line_id": line.id, "quantity": 1, "reason": "Duplicate two", "disposition": "damaged"},
    ]
    with pytest.raises(HTTPException) as duplicate_error:
        await create_return_claim(
            db_session, tenant=tenant, sale_id=sale.id, actor=owner,
            expected_version=sale.version, line_inputs=duplicated,
            idempotency_key="return-duplicate", manual_reference=None,
        )
    assert duplicate_error.value.status_code == 422
    await db_session.rollback()
    tenant = await db_session.get(Tenant, tenant_id)
    owner = await db_session.get(User, owner_id)
    item = await db_session.get(Inventory, item_id)
    sale = await db_session.get(CounterSale, sale_id)
    line = await db_session.get(CounterSaleLine, line_id)

    sale, first_return, _refund, _rows = await create_return_claim(
        db_session, tenant=tenant, sale_id=sale.id, actor=owner,
        expected_version=sale.version,
        line_inputs=[{"sale_line_id": line.id, "quantity": 1, "reason": "Customer return", "disposition": "restock"}],
        idempotency_key="return-first", manual_reference=None,
    )
    await db_session.commit()
    from app.services.counter_sale_service import finalize_refund_success
    await finalize_refund_success(
        db_session, tenant_id=tenant.id, return_id=first_return.id,
        provider_refund_id="cash-first", actor=owner,
    )
    await db_session.commit()
    await db_session.refresh(item)
    await db_session.refresh(sale)
    assert item.stock_quantity == 11 and sale.status == "partially_returned"

    sale, second_return, _refund, _rows = await create_return_claim(
        db_session, tenant=tenant, sale_id=sale.id, actor=owner,
        expected_version=sale.version,
        line_inputs=[{"sale_line_id": line.id, "quantity": 1, "reason": "Damaged return", "disposition": "damaged"}],
        idempotency_key="return-second", manual_reference=None,
    )
    await db_session.commit()
    await finalize_refund_success(
        db_session, tenant_id=tenant.id, return_id=second_return.id,
        provider_refund_id="cash-second", actor=owner,
    )
    await db_session.commit()
    await db_session.refresh(item)
    await db_session.refresh(sale)
    assert item.stock_quantity == 11 and sale.status == "returned"


@pytest.mark.asyncio
async def test_failed_stripe_refund_is_visible_and_same_key_retry_does_not_duplicate_stock_or_money(
    client, db_session, monkeypatch,
):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    monkeypatch.setattr(settings, "COUNTER_SALES_ENABLED", True)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_db045")
    tenant, owner, item, sale, line = await seed_draft_sale(db_session, quantity=2)
    tenant.stripe_account_id = "acct_refund_045"
    tenant.stripe_onboarding_complete = True
    sale.status = "completed"
    sale.completed_at = datetime.now(timezone.utc)
    item.stock_quantity = 8
    attempt = CounterSalePaymentAttempt(
        tenant_id=tenant.id, sale_id=sale.id, tender="stripe", state="succeeded",
        amount=sale.total, idempotency_key="stripe-settled-045",
        request_fingerprint="settled", provider_intent_id="pi_refund_045",
        provider_status="succeeded", attempt_number=1, actor_user_id=owner.id,
    )
    db_session.add(attempt)
    await db_session.commit()
    calls: list[str] = []

    def failed_refund(**kwargs):
        calls.append(kwargs["idempotency_key"])
        return SimpleNamespace(id="re_failed_045", status="failed")

    monkeypatch.setattr(lifecycle_endpoint.stripe.Refund, "create", failed_refund)
    create_headers = {**auth(owner, tenant), "Idempotency-Key": "return-create-045"}
    create_body = {
        "expected_version": sale.version,
        "lines": [{
            "sale_line_id": str(line.id), "quantity": 1,
            "reason": "Unused part", "disposition": "restock",
        }],
    }
    failed = await client.post(
        f"{PREFIX}/counter-sales/{sale.id}/returns",
        headers=create_headers, json=create_body,
    )
    assert failed.status_code == 202
    failed_body = failed.json()
    assert failed_body["state"] == "refund_failed"
    assert failed_body["refund"]["state"] == "failed"
    assert failed_body["refund"]["failure_code"] == "provider_failed"
    assert item.stock_quantity == 8
    replay_failed = await client.post(
        f"{PREFIX}/counter-sales/{sale.id}/returns",
        headers=create_headers, json=create_body,
    )
    assert replay_failed.status_code == 202
    assert len(calls) == 1

    def successful_refund(**kwargs):
        calls.append(kwargs["idempotency_key"])
        return SimpleNamespace(id="re_succeeded_045", status="succeeded")

    monkeypatch.setattr(lifecycle_endpoint.stripe.Refund, "create", successful_refund)
    retry_headers = {**auth(owner, tenant), "Idempotency-Key": "refund-retry-045"}
    retry_body = {"expected_version": failed_body["version"]}
    succeeded = await client.post(
        f"{PREFIX}/counter-sales/{sale.id}/returns/{failed_body['id']}/retry-refund",
        headers=retry_headers, json=retry_body,
    )
    assert succeeded.status_code == 200
    assert succeeded.json()["state"] == "completed"
    await db_session.refresh(item)
    assert item.stock_quantity == 9
    replay_succeeded = await client.post(
        f"{PREFIX}/counter-sales/{sale.id}/returns/{failed_body['id']}/retry-refund",
        headers=retry_headers, json=retry_body,
    )
    assert replay_succeeded.status_code == 200
    await db_session.refresh(item)
    assert item.stock_quantity == 9
    assert len(calls) == 2
    assert calls[0] != calls[1]


@pytest.mark.asyncio
async def test_price_override_requires_manager_reason_and_receptionist_cannot_override(db_session):
    tenant, owner, item = await seed_context(db_session)
    tenant_id, owner_id, item_id = tenant.id, owner.id, item.id
    with pytest.raises(HTTPException) as missing_reason:
        await create_or_replace_draft(
            db_session, tenant=tenant, actor=owner, sale=None,
            customer_id=None, buyer_name=None, buyer_email=None, buyer_phone=None,
            line_inputs=[{"inventory_id": item.id, "quantity": 1, "charged_unit_price": Decimal("45.00")}],
        )
    assert missing_reason.value.status_code == 422
    await db_session.rollback()
    tenant = await db_session.get(Tenant, tenant_id)
    owner = await db_session.get(User, owner_id)
    item = await db_session.get(Inventory, item_id)
    receptionist = User(
        tenant_id=tenant.id, email=f"reception-{uuid4().hex}@example.test",
        hashed_password="x", first_name="Front", last_name="Desk",
        role=UserRole.RECEPTIONIST, is_active=True, is_verified=True,
    )
    db_session.add(receptionist)
    await db_session.commit()
    with pytest.raises(HTTPException) as denied:
        await create_or_replace_draft(
            db_session, tenant=tenant, actor=receptionist, sale=None,
            customer_id=None, buyer_name=None, buyer_email=None, buyer_phone=None,
            line_inputs=[{
                "inventory_id": item.id, "quantity": 1,
                "charged_unit_price": Decimal("45.00"),
                "price_override_reason": "Manager-only adjustment",
            }],
        )
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_signed_stripe_webhook_is_idempotent_and_finalizes_stock_once(
    client, db_session, monkeypatch,
):
    tenant, _owner, item, sale, _line = await seed_draft_sale(db_session, quantity=2)
    tenant.stripe_account_id = "acct_webhook_045"
    tenant.stripe_onboarding_complete = True
    sale, _lines, attempt = await prepare_checkout(
        db_session,
        tenant=tenant,
        sale_id=sale.id,
        actor=_owner,
        expected_version=sale.version,
        tender="stripe",
        idempotency_key="signed-webhook-checkout-045",
    )
    attempt.provider_intent_id = "pi_signed_webhook_045"
    await db_session.commit()

    secret = "whsec_db045_signed_webhook_test"
    monkeypatch.setattr(settings, "STRIPE_CONNECT_WEBHOOK_SECRET", secret)
    payload = json.dumps(
        {
            "id": "evt_signed_webhook_045",
            "object": "event",
            "type": "payment_intent.succeeded",
            "account": tenant.stripe_account_id,
            "data": {
                "object": {
                    "id": attempt.provider_intent_id,
                    "object": "payment_intent",
                    "status": "succeeded",
                    "amount_received": int(Decimal(sale.total) * 100),
                    "currency": "usd",
                    "metadata": {
                        "counter_sale_id": str(sale.id),
                        "tenant_id": str(tenant.id),
                        "attempt_id": str(attempt.id),
                    },
                }
            },
        },
        separators=(",", ":"),
    ).encode()
    timestamp = int(time.time())
    signature = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256,
    ).hexdigest()
    headers = {"Stripe-Signature": f"t={timestamp},v1={signature}"}

    first = await client.post(
        "/api/v1/webhooks/stripe/counter-sales", content=payload, headers=headers,
    )
    duplicate = await client.post(
        "/api/v1/webhooks/stripe/counter-sales", content=payload, headers=headers,
    )

    assert first.status_code == duplicate.status_code == 200
    assert first.json() == duplicate.json() == {"received": True}
    await db_session.refresh(sale)
    await db_session.refresh(item)
    assert sale.status == "completed"
    assert item.stock_quantity == 8
    assert await db_session.scalar(select(func.count()).select_from(
        CounterSaleProviderEvent,
    ).where(
        CounterSaleProviderEvent.provider == "stripe",
        CounterSaleProviderEvent.external_event_id == "evt_signed_webhook_045",
    )) == 1


@pytest.mark.asyncio
async def test_completed_sale_pdf_and_receipt_email_queue_are_replay_safe(
    client, db_session, monkeypatch,
):
    monkeypatch.setattr(settings, "PARTS_OPERATIONS_V1_ENABLED", True)
    monkeypatch.setattr(settings, "COUNTER_SALES_ENABLED", True)
    tenant, owner, _item, sale, _line = await seed_draft_sale(db_session, quantity=1)
    sale, _lines, attempt = await prepare_checkout(
        db_session,
        tenant=tenant,
        sale_id=sale.id,
        actor=owner,
        expected_version=sale.version,
        tender="cash",
        idempotency_key="receipt-checkout-045",
    )
    await finalize_checkout_success(
        db_session,
        tenant_id=tenant.id,
        sale_id=sale.id,
        attempt_id=attempt.id,
        provider_amount=Decimal(sale.total),
        currency="USD",
        provider_status="succeeded",
        provider_object_id="cash-receipt-045",
        actor=owner,
    )
    await db_session.commit()

    receipt = await client.get(
        f"{PREFIX}/counter-sales/{sale.id}/receipt.pdf",
        headers=auth(owner, tenant),
    )
    assert receipt.status_code == 200
    assert receipt.headers["content-type"] == "application/pdf"
    assert receipt.content.startswith(b"%PDF")

    email_headers = {
        **auth(owner, tenant),
        "Idempotency-Key": "receipt-email-045",
    }
    first = await client.post(
        f"{PREFIX}/counter-sales/{sale.id}/receipt/email",
        headers=email_headers,
        json={"email": "walk-in@example.com"},
    )
    replay = await client.post(
        f"{PREFIX}/counter-sales/{sale.id}/receipt/email",
        headers=email_headers,
        json={"email": "walk-in@example.com"},
    )
    assert first.status_code == 202, first.text
    assert replay.status_code == 202, replay.text
    assert first.json() == replay.json() == {"queued": True, "sale_id": str(sale.id)}
    assert await db_session.scalar(select(func.count()).select_from(
        ProviderOutboxEvent,
    ).where(
        ProviderOutboxEvent.event_type == "counter_sale.receipt.email.v1",
        ProviderOutboxEvent.aggregate_id == sale.id,
    )) == 1
