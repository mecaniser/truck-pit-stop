"""Opt-in DB-067 PostgreSQL checks against an explicitly isolated migrated DB."""
import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle
from app.services.paid_invoice_webhook_service import _claim, enqueue_paid_invoice_webhook


@pytest_asyncio.fixture
async def pg_source():
    url = os.getenv("ELIS_OUTCOME_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set ELIS_OUTCOME_TEST_DATABASE_URL to an isolated migrated test database")
    from sqlalchemy.engine import make_url
    parsed = make_url(url)
    if not parsed.database or not (parsed.database.endswith("_test") or parsed.database.endswith("_local")):
        pytest.fail("DB-067 PostgreSQL checks require a database ending _test or _local")
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        assert (await db.execute(text("select version_num from alembic_version"))).scalar_one() == "148_elis_outcome_source"
        tenant = Tenant(name="DB067 synthetic", slug=f"db067-{uuid4().hex}", paid_invoice_webhook_enabled=True, paid_invoice_webhook_url="https://receiver.example/hook", paid_invoice_webhook_secret_encrypted="synthetic")
        customer = Customer(tenant=tenant, first_name="Synthetic", last_name="Test", email=f"synthetic-{uuid4().hex}@example.test")
        vehicle = Vehicle(tenant=tenant, customer=customer, make="Synthetic", model="Test")
        order = RepairOrder(tenant=tenant, customer=customer, vehicle=vehicle, order_number=f"SYN-{uuid4().hex}", status=RepairOrderStatus.PAID)
        invoice = Invoice(tenant=tenant, repair_order=order, invoice_number=f"SYN-{uuid4().hex}", status=InvoiceStatus.PAID, subtotal=Decimal(100), tax_amount=Decimal(0), discount_amount=Decimal(0), total_amount=Decimal(100), paid_at=datetime.now(timezone.utc))
        db.add_all([tenant, customer, vehicle, order, invoice]); await db.commit()
        ids = tenant.id, customer.id, order.id, invoice.id
    try:
        yield factory, ids
    finally:
        async with factory() as db:
            for model in (ProviderOutboxEvent, Invoice, RepairOrder, Vehicle, Customer):
                await db.execute(delete(model).where(model.tenant_id == ids[0]))
            await db.execute(delete(Tenant).where(Tenant.id == ids[0])); await db.commit()
        await engine.dispose()


async def _enqueue(db, ids):
    tenant_id, customer_id, order_id, invoice_id = ids
    tenant = await db.get(Tenant, tenant_id)
    customer = await db.get(Customer, customer_id)
    order = await db.get(RepairOrder, order_id)
    invoice = await db.get(Invoice, invoice_id)
    return await enqueue_paid_invoice_webhook(db, tenant=tenant, invoice=invoice, order=order, customer=customer)


@pytest.mark.asyncio
async def test_postgres_concurrent_source_notifications_accept_one_event(pg_source):
    factory, ids = pg_source
    barrier = asyncio.Barrier(2)
    async def notify():
        async with factory() as db:
            await barrier.wait()
            event = await _enqueue(db, ids)
            await db.commit()
            return event.id
    accepted = await asyncio.wait_for(asyncio.gather(notify(), notify()), timeout=15)
    assert accepted[0] == accepted[1]
    async with factory() as db:
        rows = (await db.execute(select(ProviderOutboxEvent).where(ProviderOutboxEvent.tenant_id == ids[0]))).scalars().all()
        assert len(rows) == 1
        tenant = await db.get(Tenant, ids[0])
        assert tenant.paid_invoice_webhook_payload_version == 1
        assert tenant.paid_invoice_webhook_delivery_paused is False


@pytest.mark.asyncio
async def test_postgres_concurrent_workers_do_not_claim_same_event(pg_source):
    factory, ids = pg_source
    async with factory() as db:
        event = await _enqueue(db, ids); await db.commit()
    async def claim():
        async with factory() as db:
            return await _claim(db, 1)
    results = await asyncio.wait_for(asyncio.gather(claim(), claim()), timeout=15)
    claims = [item for result, _expired in results for item in result]
    assert [item[0] for item in claims] == [event.id]
