from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.services import native_completed_outcome_source as source

NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


def fixture():
    tenant, order_id = uuid4(), uuid4()
    order = SimpleNamespace(id=order_id, tenant_id=tenant, source=None, deleted_at=None,
        is_internal=False, status='invoiced', pricing_lock_reason='invoice_finalized',
        pricing_locked_at=NOW, work_completed_at=NOW, elis_opportunity_id=None, callrail_call_id=None)
    invoice = SimpleNamespace(id=uuid4(), tenant_id=tenant, repair_order_id=order_id, source=None,
        deleted_at=None, is_internal=False, voided_at=None, status='sent', total_amount=Decimal('123.45'),
        line_items_snapshot={'labor': [{'description': 'Synthetic repair'}]}, invoice_number='TEST-123')
    return dict(tenant_id=tenant, order=order, invoices=[invoice], now=NOW)


def test_completed_unpaid_final_value_is_observed_without_financial_changes():
    args = fixture()
    before = deepcopy(args)
    snapshot = source.native_completed_snapshot(**args)
    assert snapshot['invoices'][0]['total'] == '123.45'
    assert snapshot['invoices'][0]['invoice_status'] == 'sent'
    assert snapshot['source_job_id'] == str(args['order'].id)
    assert snapshot['completed_at'] == NOW.isoformat()
    assert args == before


@pytest.mark.parametrize('target,key,value', [
    ('order','source','easy_truck_shop_import'), ('order','tenant_id',uuid4()),
    ('order','deleted_at',NOW), ('order','is_internal',True), ('order','status','in_progress'),
    ('order','pricing_lock_reason','quote_sent'), ('order','pricing_locked_at',None),
    ('invoice','source','easy_truck_shop_import'), ('invoice','tenant_id',uuid4()),
    ('invoice','repair_order_id',uuid4()), ('invoice','deleted_at',NOW),
    ('invoice','is_internal',True), ('invoice','voided_at',NOW), ('invoice','status','draft'),
    ('invoice','line_items_snapshot',None), ('invoice','invoice_number',''),
    ('invoice','total_amount',Decimal('0')), ('invoice','total_amount',Decimal('NaN')),
])
def test_ineligible_or_wrong_tenant_never_establishes_value(target,key,value):
    args = fixture()
    setattr(args['order'] if target == 'order' else args['invoices'][0],key,value)
    with pytest.raises(source.NativeCompletionHold):
        source.native_completed_snapshot(**args)


def test_approval_time_fallback_is_explicit_and_requires_finalized_status():
    args = fixture(); args['order'].work_completed_at = None
    value = source.native_completed_snapshot(**args)
    assert value['time_basis'] == 'source_completion_approved_at'
    assert value['completed_at'] == NOW.isoformat()
    args['order'].status = 'pending_review'
    with pytest.raises(source.NativeCompletionHold): source.native_completed_snapshot(**args)


@pytest.mark.parametrize('status', ['cancelled', 'draft'])
def test_cancelled_or_draft_invoice_cannot_create_completion(status):
    args = fixture(); args['invoices'][0].status = status
    with pytest.raises(source.NativeCompletionHold): source.native_completed_snapshot(**args)


def test_duplicate_active_invoices_are_held():
    args = fixture(); args['invoices'].append(deepcopy(args['invoices'][0]))
    with pytest.raises(source.NativeCompletionHold, match='manifest'): source.native_completed_snapshot(**args)


@pytest.mark.asyncio
async def test_capture_payment_transition_reuses_event_and_invalid_completion_emits_hold(monkeypatch):
    from app.services import shop_history_source
    args = fixture(); tenant = args['tenant_id']; order = args['order']; invoice = args['invoices'][0]
    monkeypatch.setattr(shop_history_source, 'history_allowed_tenants', lambda: [tenant])
    db = SimpleNamespace(scalar=AsyncMock(side_effect=[SimpleNamespace(id=tenant),order,None]),
        scalars=AsyncMock(return_value=[invoice]), add=Mock(), flush=AsyncMock())
    event = await source.capture_native_order(db,tenant,order.id)
    assert event.payload['schema_version'] == 2
    assert event.event_type == source.ETS_COMPLETED_EVENT
    assert db.add.call_count == 1
    invoice.status = 'paid'; order.status = 'paid'
    db.scalar.side_effect = [SimpleNamespace(id=tenant),order,event]
    assert await source.capture_native_order(db,tenant,order.id) is event
    assert db.add.call_count == 1
    order.status = 'in_progress'
    db.scalar.side_effect = [SimpleNamespace(id=tenant),order,event]
    hold = await source.capture_native_order(db,tenant,order.id)
    assert hold.event_type == source.ETS_HOLD_EVENT
    assert hold.payload['snapshot']['source_job_id'] == event.payload['snapshot']['source_job_id']
    assert hold.payload['source_observation'] == 2
    assert db.add.call_count == 2


@pytest.mark.asyncio
async def test_disabled_capture_does_not_query_or_write(monkeypatch):
    from app.services import shop_history_source
    monkeypatch.setattr(shop_history_source,'history_allowed_tenants',lambda: [])
    db = SimpleNamespace(scalar=AsyncMock(),add=Mock())
    assert await source.capture_native_order(db,uuid4(),uuid4()) is None
    db.scalar.assert_not_called(); db.add.assert_not_called()
