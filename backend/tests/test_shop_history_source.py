from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.vehicle import Vehicle
from app.db.models.tenant import Tenant
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.services.shop_history_source import capture_shop_history_batch, snapshot_revision, history_snapshot
from app.services.conversion_pii_retention_service import redact_conversion_payload


def test_contract_hash_and_retention():
    fixture = json.loads((Path(__file__).parent / 'fixtures/job-history-snapshot.json').read_text())
    assert snapshot_revision(fixture['snapshot']) == fixture['source_revision']
    event = ProviderOutboxEvent(payload=fixture)
    redact_conversion_payload(event)
    assert 'snapshot' not in event.payload
    assert event.payload['source_revision'] == fixture['source_revision']


async def seed(db, *, imported=True):
    tenant = Tenant(name='History shop', slug=uuid4().hex, paid_invoice_webhook_enabled=True,
                    paid_invoice_webhook_url='https://example.test/hook', paid_invoice_webhook_secret_encrypted='synthetic-not-used')
    customer = Customer(tenant=tenant, first_name='A', last_name='Fleet', company_name='Example fleet', email='fleet@example.test', phone='+15555550123')
    vehicle = Vehicle(tenant=tenant, customer=customer, make='Truck', model='Example', unit_number='1824')
    source = 'easy_truck_shop_import' if imported else None
    order = RepairOrder(tenant=tenant, customer=customer, vehicle=vehicle, source=source,
                        order_number='ETS-1763-101976', description='Inspection', status=RepairOrderStatus.COMPLETED)
    invoice = Invoice(tenant=tenant, repair_order=order, source=source, invoice_number='ETSINV-1639',
                      status=InvoiceStatus.PAID, subtotal=Decimal('1992.62'), total_amount=Decimal('1992.62'),
                      paid_at=datetime(2026, 10, 13, tzinfo=timezone.utc))
    db.add_all([tenant, customer, vehicle, order, invoice])
    await db.flush()
    return tenant, customer, vehicle, order, invoice


@pytest.mark.asyncio
async def test_current_account_contact_evidence_replaces_and_invalidates_without_profile_edits(_db_engine, monkeypatch):
    from scripts.easytruck_sync.contact_snapshot import normalize
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, vehicle, order, invoice = await seed(db)
        customer.source = 'easy_truck_shop_import'
        customer.ets_external_id = '123'
        primary_before = customer.phone
        customer.ets_contact_phone_snapshot = normalize(dict(source_shop_id='shop_test', source_customer_id='123',
            observed_at='2026-10-16T00:00:00Z', complete=True, reason=None, phones=['7045551234']),
            customer_id='123', dbn_customer_id=customer.id)
        monkeypatch.setattr('app.services.ets_completed_outcome_source.configured_shops', lambda: {tenant.id: 'shop_test'})
        snapshot = history_snapshot(tenant=tenant, invoice=invoice, order=order, customer=customer, vehicle=vehicle, operations=[order])
        assert snapshot['customer']['source_customer_id'] == '123'
        assert snapshot['customer']['contact_phone_snapshot']['complete']
        customer.source = None
        customer.ets_external_id = None
        invalidated = history_snapshot(tenant=tenant, invoice=invoice, order=order, customer=customer, vehicle=vehicle, operations=[order])
        assert invalidated['customer']['contact_phone_snapshot']['complete'] is False
        assert invalidated['customer']['contact_phone_snapshot']['contacts'] == []
        customer.ets_external_id = 'invalid-source-id'
        malformed = history_snapshot(tenant=tenant, invoice=invoice, order=order, customer=customer, vehicle=vehicle, operations=[order])
        assert malformed['customer']['source_customer_id'] is None
        assert malformed['customer']['contact_phone_snapshot']['source_customer_id'] is None
        assert customer.phone == primary_before
        assert invoice.total_amount == Decimal('1992.62')


@pytest.mark.asyncio
async def test_replay_changed_snapshot_split_operations_and_tenant_scope(_db_engine, monkeypatch):
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, vehicle, order, invoice = await seed(db)
        sibling = RepairOrder(tenant=tenant, customer=customer, vehicle=vehicle, source=order.source,
                              order_number=order.order_number+'-2', description='ABS sensor', status=RepairOrderStatus.COMPLETED)
        other = Tenant(name='Other tenant', slug=uuid4().hex, paid_invoice_webhook_enabled=True,
                       paid_invoice_webhook_url='https://example.test/hook', paid_invoice_webhook_secret_encrypted='synthetic')
        db.add_all([sibling, other]); await db.commit()
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_ENABLED', True)
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_TENANT_IDS', str(tenant.id))
    assert (await capture_shop_history_batch(session_factory=factory)) == {'scanned': 1, 'captured': 1, 'tenants': 1}
    assert (await capture_shop_history_batch(session_factory=factory))['captured'] == 0
    async with factory() as db:
        events = (await db.execute(select(ProviderOutboxEvent))).scalars().all()
        assert len(events) == 1
        snapshot = events[0].payload['snapshot']
        assert snapshot['invoice_total'] == '1992.62'
        assert len(snapshot['operations']) == 2
        assert snapshot['paid_at'] is None
        assert snapshot['paid_date'] == '2026-10-13'
        assert snapshot['paid_time_precision'] == 'day'
        assert not snapshot['grouping_uncertain']
        current = await db.get(RepairOrder, sibling.id)
        current.description = 'Revised ABS sensor'
        await db.commit()
    assert (await capture_shop_history_batch(session_factory=factory))['captured'] == 1
    async with factory() as db:
        events = (await db.execute(select(ProviderOutboxEvent))).scalars().all()
        assert len(events) == 2
        assert len({e.payload['source_revision'] for e in events}) == 2
        assert {e.event_type for e in events} == {'job.history_snapshot'}
        assert {e.tenant_id for e in events} == {tenant.id}
        assert (await db.get(Invoice, invoice.id)).total_amount == Decimal('1992.62')
        current = await db.get(RepairOrder, sibling.id)
        current.description = 'ABS sensor'
        await db.commit()
    assert (await capture_shop_history_batch(session_factory=factory))['captured'] == 1
    assert (await capture_shop_history_batch(session_factory=factory))['captured'] == 0
    async with factory() as db:
        events = (await db.execute(select(ProviderOutboxEvent).order_by(ProviderOutboxEvent.created_at))).scalars().all()
        assert len(events) == 3
        assert [event.payload['source_observation'] for event in events] == [1, 2, 3]
        assert events[0].payload['source_revision'] == events[2].payload['source_revision']
        assert events[0].idempotency_key != events[2].idempotency_key


@pytest.mark.asyncio
async def test_disabled_or_empty_allowlist_captures_nothing(_db_engine, monkeypatch):
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_ENABLED', False)
    assert (await capture_shop_history_batch(session_factory=factory))['tenants'] == 0
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_ENABLED', True)
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_TENANT_IDS', '')
    assert (await capture_shop_history_batch(session_factory=factory))['tenants'] == 0


@pytest.mark.asyncio
async def test_conflicting_equipment_is_held_and_foreign_tenant_rejected(_db_engine):
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, vehicle, order, invoice = await seed(db, imported=False)
        sibling = RepairOrder(tenant_id=tenant.id, customer_id=customer.id, vehicle_id=uuid4(), id=uuid4(),
                              order_number='OTHER', description='Other work')
        snapshot = history_snapshot(tenant=tenant, invoice=invoice, order=order, customer=customer,
                                    vehicle=vehicle, operations=[order, sibling])
        assert snapshot['grouping_uncertain']
        assert snapshot['paid_at'] is None
        assert snapshot['paid_time_precision'] == 'unknown'
        sibling.tenant_id = uuid4()
        with pytest.raises(ValueError, match='same tenant'):
            history_snapshot(tenant=tenant, invoice=invoice, order=order, customer=customer,
                             vehicle=vehicle, operations=[order, sibling])


@pytest.mark.asyncio
async def test_bounded_cursor_advances_and_atomic_rollback(_db_engine, monkeypatch):
    from app.db.models.shop_history_cursor import ShopHistoryCursor
    from app.services.shop_history_source import capture_tenant_history
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, vehicle, order, invoice = await seed(db)
        second_order = RepairOrder(tenant=tenant, customer=customer, vehicle=vehicle, source=order.source,
                                   order_number='ETS-9999-101976', status=RepairOrderStatus.COMPLETED)
        db.add(Invoice(tenant=tenant, repair_order=second_order, source=invoice.source, invoice_number='ETSINV-9999',
                       status=InvoiceStatus.SENT, subtotal=Decimal('50'), total_amount=Decimal('50')))
        await db.commit()
        tenant_id = tenant.id
        await capture_tenant_history(db, tenant, batch_size=1)
        await db.rollback()
        assert (await db.execute(select(ProviderOutboxEvent))).scalars().all() == []
        assert (await db.execute(select(ShopHistoryCursor))).scalars().all() == []
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_ENABLED', True)
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_TENANT_IDS', str(tenant_id))
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_BATCH_SIZE', 1)
    assert (await capture_shop_history_batch(session_factory=factory))['captured'] == 1
    assert (await capture_shop_history_batch(session_factory=factory))['captured'] == 1
    assert (await capture_shop_history_batch(session_factory=factory))['scanned'] == 0
    assert (await capture_shop_history_batch(session_factory=factory))['captured'] == 0


@pytest.mark.asyncio
async def test_history_delivery_gate_is_separate_from_native(monkeypatch):
    from app.services.paid_invoice_webhook_service import _deliver_within_budget, ConversionDeliveryPaused
    tenant = Tenant(id=uuid4())
    event = ProviderOutboxEvent(event_type='job.history_snapshot')
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_ENABLED', False)
    with pytest.raises(ConversionDeliveryPaused):
        await _deliver_within_budget(tenant, event)


@pytest.mark.asyncio
async def test_history_failure_does_not_pause_native_and_disabled_does_not_claim(_db_engine, monkeypatch):
    from app.services.paid_invoice_webhook_service import process_due_paid_invoice_webhooks
    from app.services.provider_outbox_service import ProviderDeliveryError
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, vehicle, order, invoice = await seed(db)
        await db.commit()
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_ENABLED', True)
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_TENANT_IDS', str(tenant.id))
    await capture_shop_history_batch(session_factory=factory)
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_ENABLED', False)
    assert (await process_due_paid_invoice_webhooks(session_factory=factory))['dead'] == 0
    async with factory() as db:
        event = await db.scalar(select(ProviderOutboxEvent))
        assert event.attempt_count == 0
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_ENABLED', True)
    async def reject(*args):
        raise ProviderDeliveryError('Unsupported history schema', retryable=False, response_code=422)
    monkeypatch.setattr('app.services.paid_invoice_webhook_service._deliver', reject)
    assert (await process_due_paid_invoice_webhooks(session_factory=factory))['dead'] == 1
    async with factory() as db:
        assert not (await db.get(Tenant, tenant.id)).paid_invoice_webhook_delivery_paused
        event = await db.scalar(select(ProviderOutboxEvent))
        assert event.status == 'dead'


@pytest.mark.asyncio
async def test_invalid_history_allowlist_does_not_break_native_worker(_db_engine, monkeypatch):
    from app.services.paid_invoice_webhook_service import process_due_paid_invoice_webhooks
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_ENABLED', True)
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_TENANT_IDS', 'invalid-uuid')
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    assert (await capture_shop_history_batch(session_factory=factory))['captured'] == 0
    assert (await process_due_paid_invoice_webhooks(session_factory=factory))['dead'] == 0


@pytest.mark.asyncio
async def test_oversized_source_context_is_explicitly_truncated_and_held(_db_engine):
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, vehicle, order, invoice = await seed(db)
        order.description = 'x' * 20000
        snapshot = history_snapshot(tenant=tenant, invoice=invoice, order=order, customer=customer,
                                    vehicle=vehicle, operations=[order])
        assert snapshot['grouping_uncertain']
        assert len(snapshot['operations'][0]['description']) < 500
        assert 'truncated; review required' in snapshot['operations'][0]['description']


@pytest.mark.asyncio
async def test_invalid_invoice_is_audited_without_blocking_other_history(_db_engine, monkeypatch):
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, vehicle, order, invoice = await seed(db)
        invoice.total_amount = Decimal('-1')
        other_order = RepairOrder(tenant=tenant, customer=customer, vehicle=vehicle, source=order.source,
                                 order_number='ETS-9999-101976', status=RepairOrderStatus.COMPLETED)
        db.add(Invoice(tenant=tenant, repair_order=other_order, source=invoice.source, invoice_number='ETSINV-9999',
                       status=InvoiceStatus.SENT, subtotal=Decimal('50'), total_amount=Decimal('50')))
        await db.commit()
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_ENABLED', True)
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_TENANT_IDS', str(tenant.id))
    assert (await capture_shop_history_batch(session_factory=factory))['captured'] == 1
    assert (await capture_shop_history_batch(session_factory=factory))['captured'] == 0
    async with factory() as db:
        events = (await db.execute(select(ProviderOutboxEvent))).scalars().all()
        assert len(events) == 2
        failure = next(event for event in events if event.event_type == 'job.history_capture_failed')
        assert failure.status == 'dead'
        assert failure.payload == {'invoice_id': str(invoice.id), 'reason': 'invalid_source_history'}


@pytest.mark.asyncio
async def test_invalid_correction_quarantines_previous_valid_context(_db_engine, monkeypatch):
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, vehicle, order, invoice = await seed(db)
        await db.commit()
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_ENABLED', True)
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_TENANT_IDS', str(tenant.id))
    await capture_shop_history_batch(session_factory=factory)
    async with factory() as db:
        current = await db.get(Invoice, invoice.id)
        current.total_amount = Decimal('-1')
        await db.commit()
    assert (await capture_shop_history_batch(session_factory=factory))['captured'] == 1
    assert (await capture_shop_history_batch(session_factory=factory))['captured'] == 0
    async with factory() as db:
        events = (await db.execute(select(ProviderOutboxEvent).where(
            ProviderOutboxEvent.event_type == 'job.history_snapshot').order_by(ProviderOutboxEvent.created_at))).scalars().all()
        assert len(events) == 2
        assert events[-1].payload['source_observation'] == 2
        assert events[-1].payload['snapshot']['grouping_uncertain']
        assert events[-1].payload['snapshot']['invoice_total'] == '1992.62'


@pytest.mark.asyncio
async def test_native_history_preserves_invoice_value_independent_of_settlement(db_session):
    tenant, customer, vehicle, order, invoice = await seed(db_session, imported=False)
    invoice.total_amount = Decimal("103"); invoice.service_fee_amount = Decimal("3")
    no_evidence = history_snapshot(tenant=tenant, invoice=invoice, order=order, customer=customer, vehicle=vehicle, operations=[order])
    assert not no_evidence["grouping_uncertain"]
    assert no_evidence["invoice_total"] == "103.00"
    assert no_evidence["paid_time_precision"] == "unknown"
    paid = history_snapshot(tenant=tenant, invoice=invoice, order=order, customer=customer, vehicle=vehicle, operations=[order], settled_amount=Decimal("100"))
    assert paid["invoice_total"] == "103.00"
    assert paid["paid_time_precision"] == "instant"
    assert not paid["grouping_uncertain"]
    assert invoice.total_amount == Decimal("103")


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_case", ["internal", "invalid_history_amount", "unsupported_source", "unsupported_order_source"])
async def test_prior_native_completion_invalidates_outside_public_history(_db_engine, monkeypatch, invalid_case):
    from app.services.native_completed_outcome_source import ETS_HOLD_EVENT
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, vehicle, order, invoice = await seed(db, imported=False)
        if invalid_case == "internal":
            invoice.is_internal = True
        elif invalid_case == "unsupported_source":
            invoice.source = "unsupported"
        elif invalid_case == "unsupported_order_source":
            order.source = "unsupported"
        else:
            invoice.total_amount = Decimal("-1.00")
        previous = ProviderOutboxEvent(tenant_id=tenant.id, event_type='repair.completed_invoice_snapshot',
            aggregate_type='repair_order', aggregate_id=order.id,
            idempotency_key=f'native-completed:{order.id}:1:prior', status='succeeded', available_at=datetime.now(timezone.utc),
            payload={'schema_version':2,'source_observation':1,'snapshot':{'source':'dieselbridge',
                'source_job_id':str(order.id),'repair_order_uuid':str(order.id),'completed':True}})
        db.add(previous); await db.commit()
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_ENABLED',True)
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_TENANT_IDS',str(tenant.id))
    result = await capture_shop_history_batch(session_factory=factory)
    assert result['scanned'] == 1
    assert result['captured'] == 0  # internal record is not exported as public history
    async with factory() as db:
        events = list(await db.scalars(select(ProviderOutboxEvent).where(ProviderOutboxEvent.tenant_id == tenant.id)))
        holds = [event for event in events if event.event_type == ETS_HOLD_EVENT]
        assert len(holds) == 1
        assert holds[0].payload['source_observation'] == 2
        assert holds[0].payload['snapshot']['source_job_id'] == str(order.id)


@pytest.mark.asyncio
async def test_delivery_pause_keeps_current_history_durable_without_dispatch(_db_engine, monkeypatch):
    """A receiver outage must not stop current source evidence being captured."""
    from app.services.paid_invoice_webhook_service import process_due_paid_invoice_webhooks

    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, vehicle, order, invoice = await seed(db)
        tenant.paid_invoice_webhook_delivery_paused = True
        foreign = Tenant(name='Unselected shop', slug=uuid4().hex,
                         paid_invoice_webhook_enabled=True,
                         paid_invoice_webhook_delivery_paused=True,
                         paid_invoice_webhook_url='https://example.test/hook',
                         paid_invoice_webhook_secret_encrypted='synthetic-not-used')
        db.add(foreign)
        await db.commit()
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_ENABLED', True)
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_TENANT_IDS', str(tenant.id))

    assert await capture_shop_history_batch(session_factory=factory) == {'scanned': 1, 'captured': 1, 'tenants': 1}
    assert (await process_due_paid_invoice_webhooks(session_factory=factory))['claimed'] == 0
    async with factory() as db:
        events = (await db.execute(select(ProviderOutboxEvent))).scalars().all()
        assert len(events) == 1
        assert events[0].tenant_id == tenant.id
        assert events[0].status == 'pending'
        assert events[0].attempt_count == 0
        assert (await db.get(Tenant, tenant.id)).paid_invoice_webhook_delivery_paused is True
        assert (await db.get(Invoice, invoice.id)).total_amount == Decimal('1992.62')
        current = await db.get(RepairOrder, order.id)
        current.description = 'Current changed work context'
        await db.commit()
    assert (await capture_shop_history_batch(session_factory=factory))['captured'] == 1
    assert (await capture_shop_history_batch(session_factory=factory))['captured'] == 0
    assert (await process_due_paid_invoice_webhooks(session_factory=factory))['claimed'] == 0


@pytest.mark.asyncio
async def test_reserved_history_slot_progresses_despite_continuous_completion_traffic(_db_engine, monkeypatch):
    from app.services.paid_invoice_webhook_service import process_due_paid_invoice_webhooks
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, *_ = await seed(db)
        await db.commit()
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_ENABLED', True)
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_TENANT_IDS', str(tenant.id))
    monkeypatch.setattr('app.core.config.settings.PROVIDER_OUTBOX_BATCH_SIZE', 1)
    await capture_shop_history_batch(session_factory=factory)
    delivered = []
    async def accept(_tenant, event):
        delivered.append(event.event_type)
        return 'synthetic-receipt', 202
    monkeypatch.setattr('app.services.paid_invoice_webhook_service._deliver', accept)
    for _ in range(3):
        async with factory() as db:
            db.add(ProviderOutboxEvent(tenant_id=tenant.id, event_type='repair_order.paid', aggregate_type='invoice', aggregate_id=uuid4(), payload={}, idempotency_key=uuid4().hex, available_at=datetime.now(timezone.utc)))
            await db.commit()
        assert (await process_due_paid_invoice_webhooks(session_factory=factory))['succeeded'] == 1
    assert delivered == ['repair_order.paid'] * 3
    async with factory() as db:
        db.add(ProviderOutboxEvent(tenant_id=tenant.id, event_type='repair_order.paid', aggregate_type='invoice', aggregate_id=uuid4(), payload={}, idempotency_key=uuid4().hex, available_at=datetime.now(timezone.utc)))
        await db.commit()
    # Even an oversized caller override cannot enlarge the reserved task budget.
    assert (await process_due_paid_invoice_webhooks(session_factory=factory, history_only=True, batch_size=100))['succeeded'] == 1
    assert delivered[-1] == 'job.history_snapshot'
    async with factory() as db:
        assert len((await db.scalars(select(ProviderOutboxEvent).where(ProviderOutboxEvent.status == 'pending'))).all()) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('restriction', ['paused', 'disabled', 'not_allowed', 'capture_disabled', 'dead', 'leased', 'future'])
async def test_reserved_history_slot_preserves_claim_guards(_db_engine, monkeypatch, restriction):
    from datetime import timedelta
    from app.services.paid_invoice_webhook_service import process_due_paid_invoice_webhooks
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, *_ = await seed(db)
        await db.commit()
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_ENABLED', True)
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_TENANT_IDS', str(tenant.id))
    await capture_shop_history_batch(session_factory=factory)
    async with factory() as db:
        event = await db.scalar(select(ProviderOutboxEvent))
        tenant = await db.get(Tenant, tenant.id)
        if restriction == 'paused': tenant.paid_invoice_webhook_delivery_paused = True
        if restriction == 'disabled': tenant.paid_invoice_webhook_enabled = False
        if restriction == 'not_allowed': monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_TENANT_IDS', str(uuid4()))
        if restriction == 'capture_disabled': monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_ENABLED', False)
        if restriction == 'dead': event.status = 'dead'
        if restriction == 'leased':
            event.status = 'processing'
            event.locked_until = datetime.now(timezone.utc) + timedelta(minutes=5)
        if restriction == 'future': event.available_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        await db.commit()
        before = event.attempt_count
    result = await process_due_paid_invoice_webhooks(session_factory=factory, history_only=True)
    assert result['claimed'] == 0
    async with factory() as db:
        assert (await db.scalar(select(ProviderOutboxEvent))).attempt_count == before


@pytest.mark.asyncio
async def test_reserved_history_failure_keeps_native_retry_rules(_db_engine, monkeypatch):
    from app.services.paid_invoice_webhook_service import process_due_paid_invoice_webhooks
    from app.services.provider_outbox_service import ProviderDeliveryError
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, *_ = await seed(db)
        await db.commit()
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_ENABLED', True)
    monkeypatch.setattr('app.core.config.settings.SHOP_HISTORY_CAPTURE_TENANT_IDS', str(tenant.id))
    monkeypatch.setattr('app.core.config.settings.PROVIDER_OUTBOX_MAX_ATTEMPTS', 3)
    await capture_shop_history_batch(session_factory=factory)
    async def fail(*args):
        raise ProviderDeliveryError('synthetic timeout', retryable=True)
    monkeypatch.setattr('app.services.paid_invoice_webhook_service._deliver', fail)
    assert (await process_due_paid_invoice_webhooks(session_factory=factory, history_only=True))['retried'] == 1
    async with factory() as db:
        event = await db.scalar(select(ProviderOutboxEvent))
        assert event.status == 'pending' and event.attempt_count == 1
        assert event.available_at > event.last_attempt_at
    assert (await process_due_paid_invoice_webhooks(session_factory=factory, history_only=True))['claimed'] == 0


def test_reserved_history_task_has_independent_schedule_and_bounded_budget():
    from app.tasks import celery_app
    from app.tasks.provider_outbox import process_shop_history_webhooks
    from app.core.config import settings
    schedule = celery_app.conf.beat_schedule
    assert schedule['process-shop-history-webhooks']['task'] == 'process_shop_history_webhooks'
    assert schedule['process-shop-history-webhooks']['schedule'].total_seconds() == 10
    assert schedule['process-shop-history-webhooks']['options']['expires'] == 10
    assert schedule['process-paid-invoice-webhooks']['schedule'].total_seconds() == 10
    assert process_shop_history_webhooks.soft_time_limit == 45
    assert process_shop_history_webhooks.time_limit == 60
    assert settings.PAID_INVOICE_WEBHOOK_TOTAL_TIMEOUT_SECONDS == 35


@pytest.mark.asyncio
async def test_reserved_history_delivery_retains_total_timeout(monkeypatch):
    import anyio
    from app.services.paid_invoice_webhook_service import _deliver
    from app.services.provider_outbox_service import ProviderDeliveryError
    monkeypatch.setattr('app.core.config.settings.PAID_INVOICE_WEBHOOK_TOTAL_TIMEOUT_SECONDS', .01)
    async def stalled(*args):
        await anyio.sleep(1)
    monkeypatch.setattr('app.services.paid_invoice_webhook_service._deliver_within_budget', stalled)
    event = ProviderOutboxEvent(event_type='job.history_snapshot', payload={}, created_at=datetime.now(timezone.utc))
    with pytest.raises(ProviderDeliveryError, match='total time budget') as error:
        await _deliver(Tenant(id=uuid4()), event)
    assert error.value.retryable
