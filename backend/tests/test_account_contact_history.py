"""Real source freshness, source provenance and immutable daily history delivery."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle
from app.services.account_contact_history import capture_account_contacts_batch
from app.services.account_contact_snapshot import normalize
from app.services.shop_history_source import ETS, history_snapshot, capture_tenant_history


async def account(db, monkeypatch, *, observed=None):
    tenant = Tenant(name='Daily shop', slug=uuid4().hex, paid_invoice_webhook_enabled=True,
        paid_invoice_webhook_url='https://example.test/hook', paid_invoice_webhook_secret_encrypted='synthetic')
    customer = Customer(tenant=tenant, first_name='Fleet', last_name='Example', source=ETS,
                        ets_external_id='123', email='fleet@example.test', phone='+17045550123')
    vehicle = Vehicle(tenant=tenant, customer=customer, make='Truck', model='Example', unit_number='42')
    service_id = str(uuid4().int % 10**12)
    order = RepairOrder(tenant=tenant, customer=customer, vehicle=vehicle, source=ETS,
                        order_number=f'ETS-{service_id}-123', status=RepairOrderStatus.COMPLETED)
    invoice = Invoice(tenant=tenant, repair_order=order, source=ETS, invoice_number=f'ETSINV-{service_id}',
                      status=InvoiceStatus.SENT, subtotal=Decimal('12'), total_amount=Decimal('12'))
    db.add_all([tenant, customer, vehicle, order, invoice]); await db.flush()
    customer.ets_contact_phone_snapshot = normalize(dict(source_shop_id='shop_test', source_customer_id='123',
        observed_at=(observed or datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
        complete=True, reason=None, phones=['7045550123']), customer_id='123', dbn_customer_id=customer.id)
    await db.commit()
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_ENABLED', True)
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_TENANT_IDS', str(tenant.id))
    monkeypatch.setattr('app.services.ets_completed_outcome_source.configured_shops', lambda: {tenant.id: 'shop_test'})
    return tenant, customer, vehicle, order, invoice


@pytest.mark.asyncio
async def test_daily_rerun_same_read_is_one_event_and_same_day_corrections_propagate(_db_engine, monkeypatch):
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, vehicle, order, invoice = await account(db, monkeypatch)
        profile = customer.phone; original = deepcopy(customer.ets_contact_phone_snapshot)
        # Two supported invoices still produce one account event.
        second = RepairOrder(tenant=tenant, customer=customer, vehicle=vehicle, source=ETS,
                             order_number='ETS-43-123', status=RepairOrderStatus.COMPLETED)
        db.add(Invoice(tenant=tenant, repair_order=second, source=ETS, invoice_number='ETSINV-43',
                       status=InvoiceStatus.SENT, subtotal=Decimal('30'), total_amount=Decimal('30')))
        await db.commit()
    first = await capture_account_contacts_batch(session_factory=factory)
    assert first['captured'] == 1
    assert (await capture_account_contacts_batch(session_factory=factory))['captured'] == 0
    async with factory() as db:
        event = await db.scalar(select(ProviderOutboxEvent))
        assert event.payload['schema_version'] == 2
        assert event.payload['snapshot']['customer']['contact_phone_snapshot'] == original
        assert event.payload['source_observation'] == 1
        first_id, first_body = event.id, deepcopy(event.payload)
    # Invalidation, recovery and complete empty sets are distinct even on one day.
    for i, (complete, phones) in enumerate([(False, []), (True, ['7045550199']), (True, [])], 1):
        async with factory() as db:
            current = await db.get(Customer, customer.id)
            current.ets_contact_phone_snapshot = normalize(dict(source_shop_id='shop_test', source_customer_id='123',
                observed_at=(datetime.now(timezone.utc)-timedelta(minutes=10-i)).isoformat(),
                complete=complete, reason=None if complete else 'read_unavailable', phones=phones),
                customer_id='123', dbn_customer_id=current.id)
            await db.commit()
        assert (await capture_account_contacts_batch(session_factory=factory))['captured'] == 1
        assert (await capture_account_contacts_batch(session_factory=factory))['captured'] == 0
    async with factory() as db:
        events = list((await db.scalars(select(ProviderOutboxEvent).order_by(ProviderOutboxEvent.created_at))).all())
        assert len(events) == 4
        assert [e.payload['source_observation'] for e in events] == [1,2,3,4]
        assert len({e.idempotency_key for e in events}) == 4
        assert all(len(e.idempotency_key) <= 255 for e in events)
        assert (await db.get(ProviderOutboxEvent, first_id)).payload == first_body
        assert events[1].payload['snapshot']['customer']['contact_phone_snapshot']['complete'] is False
        assert events[-1].payload['snapshot']['customer']['contact_phone_snapshot']['contacts'] == []
        assert (await db.get(Customer, customer.id)).phone == profile
        assert (await db.get(Invoice, invoice.id)).total_amount == Decimal('12')


@pytest.mark.asyncio
@pytest.mark.parametrize('restriction', ['stale', 'future', 'wrong_shop', 'wrong_customer', 'wrong_tenant',
    'native_invoice', 'native_order', 'internal', 'deleted_invoice', 'deleted_order', 'deleted_customer',
    'disabled', 'not_allowed', 'capture_disabled', 'no_evidence'])
async def test_untrusted_or_ineligible_accounts_do_not_emit(_db_engine, monkeypatch, restriction):
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, vehicle, order, invoice = await account(db, monkeypatch)
        evidence = deepcopy(customer.ets_contact_phone_snapshot)
        if restriction == 'stale': evidence['observed_at'] = (datetime.now(timezone.utc)-timedelta(hours=21)).isoformat()
        if restriction == 'future': evidence['observed_at'] = (datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat()
        if restriction == 'wrong_shop': evidence['source_shop_id'] = 'another_shop'
        if restriction == 'wrong_customer': evidence['source_customer_id'] = '456'
        if restriction == 'wrong_tenant': order.tenant_id = uuid4()
        if restriction == 'native_invoice': invoice.source = None
        if restriction == 'native_order': order.source = None
        if restriction == 'internal': invoice.is_internal = True
        if restriction == 'deleted_invoice': invoice.deleted_at = datetime.now(timezone.utc)
        if restriction == 'deleted_order': order.deleted_at = datetime.now(timezone.utc)
        if restriction == 'deleted_customer': customer.deleted_at = datetime.now(timezone.utc)
        if restriction == 'disabled': tenant.paid_invoice_webhook_enabled = False
        if restriction == 'not_allowed': monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_TENANT_IDS', str(uuid4()))
        if restriction == 'capture_disabled': monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_ENABLED', False)
        customer.ets_contact_phone_snapshot = None if restriction == 'no_evidence' else evidence
        await db.commit()
    assert (await capture_account_contacts_batch(session_factory=factory))['captured'] == 0
    async with factory() as db:
        assert await db.scalar(select(ProviderOutboxEvent)) is None


@pytest.mark.asyncio
async def test_native_job_on_imported_account_keeps_v2_without_contact_or_source_change(_db_engine, monkeypatch):
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, vehicle, order, invoice = await account(db, monkeypatch)
        evidence = deepcopy(customer.ets_contact_phone_snapshot)
        imported = history_snapshot(tenant=tenant, invoice=invoice, order=order, customer=customer,
                                    vehicle=vehicle, operations=[order])
        assert imported['customer']['contact_phone_snapshot']['complete'] is True
        order.source = invoice.source = None
        native = history_snapshot(tenant=tenant, invoice=invoice, order=order, customer=customer,
                                  vehicle=vehicle, operations=[order])
        assert native['source'] == 'dieselbridge'
        assert native['customer']['source_customer_id'] == '123'
        assert 'contact_phone_snapshot' not in native['customer']
        assert customer.ets_contact_phone_snapshot == evidence
        await db.commit()
        # Capture uses v2, avoiding the receiver's v1 downgrade rule.
        await capture_tenant_history(db, tenant, batch_size=50)
        event = await db.scalar(select(ProviderOutboxEvent).where(ProviderOutboxEvent.event_type == 'job.history_snapshot'))
        assert event.payload['schema_version'] == 2
        assert 'contact_phone_snapshot' not in event.payload['snapshot']['customer']


@pytest.mark.asyncio
async def test_priority_does_not_bypass_pause_and_captures_continue(_db_engine, monkeypatch):
    from app.services.paid_invoice_webhook_service import process_due_paid_invoice_webhooks
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, *_ = await account(db, monkeypatch)
        tenant.paid_invoice_webhook_delivery_paused = True
        bulk_id = uuid4()
        db.add(ProviderOutboxEvent(id=bulk_id, tenant=tenant, event_type='job.history_snapshot', aggregate_type='invoice',
            aggregate_id=uuid4(), payload={}, idempotency_key='bulk-history',
            available_at=datetime.now(timezone.utc)-timedelta(hours=2)))
        await db.commit()
    assert (await capture_account_contacts_batch(session_factory=factory))['captured'] == 1
    assert (await process_due_paid_invoice_webhooks(session_factory=factory, history_only=True))['claimed'] == 0
    async with factory() as db:
        current = await db.get(Tenant, tenant.id); current.paid_invoice_webhook_delivery_paused = False
        await db.commit()
    sent = []
    async def accept(_tenant, event):
        sent.append(event.id); return 'synthetic-receipt', 202
    monkeypatch.setattr('app.services.paid_invoice_webhook_service._deliver', accept)
    assert (await process_due_paid_invoice_webhooks(session_factory=factory, history_only=True))['succeeded'] == 1
    assert sent[0] != bulk_id
    assert (await process_due_paid_invoice_webhooks(session_factory=factory, history_only=True))['succeeded'] == 1
    assert sent[1] == bulk_id


@pytest.mark.asyncio
async def test_postgres_concurrent_capture_preserves_one_account_event_and_invoice_sequence(monkeypatch):
    import asyncio
    import os
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.db.base import Base
    from app.db.models.shop_history_cursor import ShopHistoryObservation
    from app.services.shop_history_source import capture_shop_history_batch
    url = os.environ.get('CONTACT_HISTORY_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set CONTACT_HISTORY_TEST_DATABASE_URL to an isolated local PostgreSQL test database')
    parsed = make_url(url)
    if parsed.host not in {'127.0.0.1', 'localhost'} or not parsed.database.endswith('_test'):
        pytest.fail('Contact concurrency test requires a local database ending _test')
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            tenant, *_ = await account(db, monkeypatch)
        results = await asyncio.wait_for(asyncio.gather(*[
            capture_account_contacts_batch(session_factory=factory) for _ in range(2)
        ]), timeout=15)
        assert sum(r['captured'] for r in results) == 1
        # Rotate and daily capture concurrently against the same invoice lock.
        await asyncio.wait_for(asyncio.gather(
            capture_account_contacts_batch(session_factory=factory),
            capture_shop_history_batch(session_factory=factory)), timeout=15)
        async with factory() as db:
            events = list((await db.scalars(select(ProviderOutboxEvent).where(
                ProviderOutboxEvent.tenant_id == tenant.id))).all())
            assert len(events) == 1
            observation = await db.scalar(select(ShopHistoryObservation).where(
                ShopHistoryObservation.tenant_id == tenant.id))
            assert observation.sequence == 1
            assert events[0].payload['source_observation'] == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_invalid_account_read_cannot_starve_later_accounts(_db_engine, monkeypatch):
    from app.services.account_contact_history import CONTACT_CAPTURE_FAILED
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, vehicle, order, invoice = await account(db, monkeypatch)
        other = Customer(id=uuid4(), tenant=tenant, first_name='Second', last_name='Account', email='second@example.test',
                         source=ETS, ets_external_id='456', phone='+17045550199')
        db.add(other); await db.flush()
        other.ets_contact_phone_snapshot = normalize(dict(source_shop_id='shop_test', source_customer_id='456',
            observed_at=datetime.now(timezone.utc).isoformat(), complete=True, reason=None, phones=['7045550199']),
            customer_id='456', dbn_customer_id=other.id)
        other_order = RepairOrder(tenant=tenant, customer=other, vehicle=vehicle, source=ETS,
                                 order_number='ETS-44-456', status=RepairOrderStatus.COMPLETED)
        db.add(Invoice(tenant=tenant, repair_order=other_order, source=ETS, invoice_number='ETSINV-44',
                       status=InvoiceStatus.SENT, subtotal=Decimal('12'), total_amount=Decimal('12')))
        first = min([customer, other], key=lambda c: str(c.id))
        bad = deepcopy(first.ets_contact_phone_snapshot); bad['semantic_hash'] = '0'*64
        first.ets_contact_phone_snapshot = bad
        await db.commit()
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_BATCH_SIZE', 1)
    assert (await capture_account_contacts_batch(session_factory=factory))['invalid'] == 1
    assert (await capture_account_contacts_batch(session_factory=factory))['captured'] == 1
    assert (await capture_account_contacts_batch(session_factory=factory))['captured'] == 0
    async with factory() as db:
        failure = await db.scalar(select(ProviderOutboxEvent).where(ProviderOutboxEvent.event_type == CONTACT_CAPTURE_FAILED))
        assert failure.status == 'dead'
        assert 'contacts' not in failure.payload and 'snapshot' not in failure.payload


@pytest.mark.asyncio
async def test_erased_account_read_is_not_reconstructed_through_another_invoice(_db_engine, monkeypatch):
    from app.services.conversion_pii_retention_service import erase_customer_conversion_event_pii
    from app.services.shop_history_source import enqueue_history_snapshot
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, vehicle, order, invoice = await account(db, monkeypatch)
        snapshot = history_snapshot(tenant=tenant, invoice=invoice, order=order, customer=customer,
                                    vehicle=vehicle, operations=[order])
        await enqueue_history_snapshot(db, tenant=tenant, invoice=invoice, snapshot=snapshot)
        await db.commit()
        assert await erase_customer_conversion_event_pii(db, tenant_id=tenant.id, customer_id=customer.id, apply=True) == 1
        # Removing this invoice from eligible selection cannot bypass account erasure.
        current = await db.get(Invoice, invoice.id); current.is_internal = True
        sibling = RepairOrder(tenant=tenant, customer=customer, vehicle=vehicle, source=ETS,
                              order_number='ETS-45-123', status=RepairOrderStatus.COMPLETED)
        db.add(Invoice(tenant=tenant, repair_order=sibling, source=ETS, invoice_number='ETSINV-45',
                       status=InvoiceStatus.SENT, subtotal=Decimal('12'), total_amount=Decimal('12')))
        await db.commit()
    assert (await capture_account_contacts_batch(session_factory=factory))['captured'] == 0
    async with factory() as db:
        old = await db.scalar(select(ProviderOutboxEvent))
        assert old.status == 'expired' and 'snapshot' not in old.payload
        current = await db.get(Customer, customer.id)
        source_read = deepcopy(current.ets_contact_phone_snapshot)
        source_read['observed_at'] = datetime.now(timezone.utc).isoformat()
        current.ets_contact_phone_snapshot = source_read
        await db.commit()
    assert (await capture_account_contacts_batch(session_factory=factory))['captured'] == 1


@pytest.mark.asyncio
async def test_legacy_native_fallback_cannot_reintroduce_complete_ets_contacts(_db_engine, monkeypatch):
    from app.services.shop_history_source import enqueue_history_snapshot
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, vehicle, order, invoice = await account(db, monkeypatch)
        old = history_snapshot(tenant=tenant, invoice=invoice, order=order, customer=customer,
                               vehicle=vehicle, operations=[order])
        old['source'] = 'dieselbridge'
        saved = deepcopy(old)
        event = await enqueue_history_snapshot(db, tenant=tenant, invoice=invoice, snapshot=old)
        assert old == saved
        assert event.payload['schema_version'] == 2
        assert event.payload['snapshot']['source'] == 'dieselbridge'
        assert 'contact_phone_snapshot' not in event.payload['snapshot']['customer']


@pytest.mark.asyncio
async def test_newest_contact_invalidation_precedes_older_complete_read(_db_engine, monkeypatch):
    from app.services.paid_invoice_webhook_service import process_due_paid_invoice_webhooks
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, *_ = await account(db, monkeypatch)
    assert (await capture_account_contacts_batch(session_factory=factory))['captured'] == 1
    async with factory() as db:
        current = await db.get(Customer, customer.id)
        current.ets_contact_phone_snapshot = normalize(dict(source_shop_id='shop_test', source_customer_id='123',
            observed_at=datetime.now(timezone.utc).isoformat(), complete=False, reason='read_unavailable', phones=[]),
            customer_id='123', dbn_customer_id=current.id)
        await db.commit()
    assert (await capture_account_contacts_batch(session_factory=factory))['captured'] == 1
    delivered = []
    async def accept(_tenant, event):
        delivered.append(event.payload['snapshot']['customer']['contact_phone_snapshot']['complete'])
        return 'synthetic-receipt', 202
    monkeypatch.setattr('app.services.paid_invoice_webhook_service._deliver', accept)
    for _ in range(2):
        assert (await process_due_paid_invoice_webhooks(session_factory=factory, history_only=True))['succeeded'] == 1
    assert delivered == [False, True]


@pytest.mark.asyncio
async def test_postgres_customer_erasure_serializes_with_uncommitted_daily_capture(monkeypatch):
    import asyncio
    import os
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.db.base import Base
    from app.services import account_contact_history as daily
    from app.services.conversion_pii_retention_service import erase_customer_conversion_event_pii
    url = os.environ.get('CONTACT_HISTORY_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set CONTACT_HISTORY_TEST_DATABASE_URL to an isolated local PostgreSQL test database')
    parsed = make_url(url)
    if parsed.host not in {'127.0.0.1', 'localhost'} or not parsed.database.endswith('_test'):
        pytest.fail('Contact concurrency test requires a local database ending _test')
    engine = create_async_engine(url)
    entered, release = asyncio.Event(), asyncio.Event()
    real_enqueue = daily.enqueue_history_snapshot
    async def gated(*args, **kwargs):
        entered.set()
        await release.wait()
        return await real_enqueue(*args, **kwargs)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            tenant, customer, *_ = await account(db, monkeypatch)
        monkeypatch.setattr(daily, 'enqueue_history_snapshot', gated)
        capture = asyncio.create_task(daily.capture_account_contacts_batch(session_factory=factory))
        await asyncio.wait_for(entered.wait(), timeout=10)
        async def erase():
            async with factory() as db:
                return await erase_customer_conversion_event_pii(db, tenant_id=tenant.id,
                                                                customer_id=customer.id, apply=True)
        erasure = asyncio.create_task(erase())
        await asyncio.sleep(0.05)
        assert not erasure.done()
        release.set()
        assert (await asyncio.wait_for(capture, timeout=10))['captured'] == 1
        assert await asyncio.wait_for(erasure, timeout=10) == 1
        async with factory() as db:
            events = list((await db.scalars(select(ProviderOutboxEvent).where(
                ProviderOutboxEvent.tenant_id == tenant.id))).all())
            assert len(events) == 1
            assert events[0].status == 'expired' and 'snapshot' not in events[0].payload
    finally:
        release.set()
        await engine.dispose()
