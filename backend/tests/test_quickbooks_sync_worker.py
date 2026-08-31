from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle
from app.services import quickbooks_sync_service as sync_service


@pytest.mark.asyncio
async def test_quickbooks_sync_enqueue_is_conflict_safe(db_session):
    tenant = Tenant(name="Outbox Tenant", slug=f"outbox-{uuid4().hex[:8]}")
    db_session.add(tenant)
    await db_session.commit()
    invoice = Invoice(
        id=uuid4(),
        tenant_id=tenant.id,
        repair_order_id=uuid4(),
        invoice_number=f"INV-{uuid4().hex[:8]}",
        status=InvoiceStatus.SENT,
        subtotal=Decimal("10.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("10.00"),
    )

    first = await sync_service.enqueue_quickbooks_invoice_sync(
        db_session,
        invoice=invoice,
    )
    second = await sync_service.enqueue_quickbooks_invoice_sync(
        db_session,
        invoice=invoice,
    )
    await db_session.commit()

    count = (await db_session.execute(
        select(func.count(ProviderOutboxEvent.id)).where(
            ProviderOutboxEvent.tenant_id == tenant.id,
            ProviderOutboxEvent.event_type
            == sync_service.QUICKBOOKS_INVOICE_SYNC_EVENT,
        )
    )).scalar_one()
    assert count == 1
    assert first.id == second.id


@pytest.mark.asyncio
async def test_quickbooks_sync_enqueue_handles_two_transaction_race(
    _db_engine,
    tmp_path,
):
    database_path = tmp_path / "quickbooks-outbox-race.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        tenant = Tenant(
            name="Concurrent Outbox Tenant",
            slug=f"concurrent-{uuid4().hex[:8]}",
        )
        db.add(tenant)
        await db.commit()
        tenant_id = tenant.id

    invoice_id = uuid4()
    release = asyncio.Event()

    async def contender():
        invoice = Invoice(
            id=invoice_id,
            tenant_id=tenant_id,
            repair_order_id=uuid4(),
            invoice_number=f"INV-{invoice_id.hex[:8]}",
            status=InvoiceStatus.SENT,
            subtotal=Decimal("10.00"),
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("10.00"),
        )
        await release.wait()
        async with factory() as db:
            event = await sync_service.enqueue_quickbooks_invoice_sync(
                db,
                invoice=invoice,
            )
            await db.commit()
            return event.id

    first_task = asyncio.create_task(contender())
    second_task = asyncio.create_task(contender())
    release.set()
    first_id, second_id = await asyncio.gather(first_task, second_task)

    async with factory() as db:
        count = (await db.execute(
            select(func.count(ProviderOutboxEvent.id)).where(
                ProviderOutboxEvent.tenant_id == tenant_id,
                ProviderOutboxEvent.event_type
                == sync_service.QUICKBOOKS_INVOICE_SYNC_EVENT,
            )
        )).scalar_one()
    await engine.dispose()

    assert count == 1
    assert first_id == second_id


@pytest.mark.asyncio
async def test_quickbooks_worker_claims_one_event_with_bounded_provider_lease(
    db_session,
):
    tenant = Tenant(name="Lease Tenant", slug=f"lease-{uuid4().hex[:8]}")
    db_session.add(tenant)
    await db_session.flush()
    events = [
        ProviderOutboxEvent(
            tenant_id=tenant.id,
            event_type=sync_service.QUICKBOOKS_INVOICE_SYNC_EVENT,
            aggregate_type="quickbooks_invoice",
            aggregate_id=uuid4(),
            payload={"invoice_id": str(uuid4()), "operation": "sync"},
            idempotency_key=f"lease-{index}-{uuid4().hex}",
            status=ProviderOutboxStatus.PENDING.value,
            available_at=sync_service._now(),
        )
        for index in range(2)
    ]
    db_session.add_all(events)
    await db_session.commit()
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async with factory() as db:
        claim = await sync_service._claim_next_quickbooks_sync_event(db)
    assert claim is not None

    for event in events:
        await db_session.refresh(event)
    processing = [
        event
        for event in events
        if event.status == ProviderOutboxStatus.PROCESSING.value
    ]
    pending = [
        event
        for event in events
        if event.status == ProviderOutboxStatus.PENDING.value
    ]
    assert len(processing) == 1
    assert len(pending) == 1
    lease_seconds = (
        processing[0].locked_until - processing[0].locked_at
    ).total_seconds()
    assert lease_seconds >= (
        sync_service.settings.QUICKBOOKS_HTTP_TIMEOUT_SECONDS * 12 + 60
    )


@pytest.mark.asyncio
async def test_quickbooks_sync_rejects_foreign_tenant_aggregate(
    db_session,
    monkeypatch,
):
    event_tenant = Tenant(
        name="Event Tenant",
        slug=f"event-{uuid4().hex[:8]}",
    )
    invoice_tenant = Tenant(
        name="Invoice Tenant",
        slug=f"invoice-{uuid4().hex[:8]}",
    )
    db_session.add_all([event_tenant, invoice_tenant])
    await db_session.flush()
    customer = Customer(
        id=uuid4(),
        tenant_id=invoice_tenant.id,
        first_name="Foreign",
        last_name="Customer",
        email="foreign@example.test",
    )
    vehicle = Vehicle(
        id=uuid4(),
        tenant_id=invoice_tenant.id,
        customer_id=customer.id,
        year=2024,
        make="Kenworth",
        model="T680",
    )
    repair_order = RepairOrder(
        id=uuid4(),
        tenant_id=invoice_tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        order_number=f"RO-{uuid4().hex[:8]}",
        status=RepairOrderStatus.INVOICED,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("10.00"),
        total_cost=Decimal("10.00"),
    )
    invoice = Invoice(
        id=uuid4(),
        tenant_id=invoice_tenant.id,
        repair_order_id=repair_order.id,
        invoice_number=f"INV-{uuid4().hex[:8]}",
        status=InvoiceStatus.SENT,
        subtotal=Decimal("10.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("10.00"),
    )
    event = ProviderOutboxEvent(
        tenant_id=event_tenant.id,
        event_type=sync_service.QUICKBOOKS_INVOICE_SYNC_EVENT,
        aggregate_type="quickbooks_invoice",
        aggregate_id=invoice.id,
        payload={"invoice_id": str(invoice.id), "operation": "sync"},
        idempotency_key=f"quickbooks-invoice:{invoice.id}:sync:v1",
        status=ProviderOutboxStatus.PENDING.value,
        available_at=sync_service._now(),
    )
    connection = QuickBooksConnection(
        tenant_id=event_tenant.id,
        realm_id=f"realm-{uuid4().hex[:8]}",
        status="connected",
        encrypted_access_token="not-used",
        encrypted_refresh_token="not-used",
    )
    db_session.add_all([
        customer,
        vehicle,
        repair_order,
        invoice,
        event,
        connection,
    ])
    await db_session.commit()

    provider_calls = 0

    async def fail_if_called(*_args, **_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("foreign tenant invoice reached QuickBooks")

    monkeypatch.setattr(sync_service, "sync_invoice", fail_if_called)
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    result = await sync_service.process_quickbooks_invoice_sync_events(
        session_factory=factory,
        batch_size=10,
    )

    await db_session.refresh(event)
    assert provider_calls == 0
    assert result == {
        "processed": 1,
        "succeeded": 0,
        "retried": 0,
        "dead": 1,
        "skipped": 0,
    }
    assert event.status == ProviderOutboxStatus.DEAD.value
    assert event.lock_token is None
    assert event.locked_until is None
