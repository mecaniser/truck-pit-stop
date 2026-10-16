"""Native completed/finalized invoice observations, independent of payment.

This adapter only reads shop financial facts and writes the signed source outbox.
The stable RO UUID is shared with the existing paid bridge, never a second job.
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from uuid import uuid4

from sqlalchemy import select

from app.db.models.invoice import Invoice
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.repair_order import RepairOrder
from app.db.models.tenant import Tenant
from app.services.ets_completed_outcome_source import ETS_COMPLETED_EVENT, ETS_HOLD_EVENT, ETS_EVENTS


class NativeCompletionHold(ValueError):
    pass


def _status(value):
    return value.value if hasattr(value, 'value') else value


def _time(value, now):
    if value is None or value.utcoffset() is None or value > now:
        raise NativeCompletionHold('source_fields_missing')
    return value.astimezone(timezone.utc).isoformat()


def native_completed_snapshot(*, tenant_id, order, invoices, now):
    if order.tenant_id != tenant_id or order.source is not None:
        raise NativeCompletionHold('source_identity_conflict')
    if (order.deleted_at is not None or order.is_internal
            or _status(order.status) not in {'completed', 'invoiced', 'paid'}):
        raise NativeCompletionHold('source_status_unsupported')
    if order.pricing_lock_reason != 'invoice_finalized' or not order.pricing_locked_at:
        raise NativeCompletionHold('source_fields_missing')
    active = [invoice for invoice in invoices if _status(invoice.status) != 'cancelled']
    if len(active) != 1:
        raise NativeCompletionHold('invoice_manifest_incomplete')
    invoice = active[0]
    if invoice.tenant_id != tenant_id or invoice.repair_order_id != order.id or invoice.source is not None:
        raise NativeCompletionHold('source_identity_conflict')
    if (invoice.deleted_at is not None or invoice.is_internal or invoice.voided_at is not None
            or _status(invoice.status) not in {'sent', 'overdue', 'paid'}):
        raise NativeCompletionHold('source_status_unsupported')
    if invoice.line_items_snapshot is None or not invoice.invoice_number:
        raise NativeCompletionHold('source_fields_missing')
    try:
        total = Decimal(invoice.total_amount)
        if not total.is_finite() or total <= 0 or total != total.quantize(Decimal('.01')):
            raise ValueError()
    except (ValueError, TypeError, InvalidOperation):
        raise NativeCompletionHold('source_fields_missing') from None
    # A manager-approved completed order can lack a mechanic completion instant.
    # Its explicit finalization lock is the approval timestamp, not a guess at
    # the date that work physically ended.
    physical = order.work_completed_at is not None
    completed_at = _time(order.work_completed_at if physical else order.pricing_locked_at, now)
    return {'source': 'dieselbridge', 'source_job_id': str(order.id), 'repair_order_uuid': str(order.id),
        'completed': True, 'completed_at': completed_at,
        'time_basis': 'source_work_completed_at' if physical else 'source_completion_approved_at',
        'value_basis': 'completed_invoice_total',
        'invoice_manifest': {'complete': True, 'invoice_ids': [str(invoice.id)],
                             'evidence_kind': 'native_finalized_invoice_manifest'},
        'invoices': [{'invoice_id': str(invoice.id), 'invoice_number': invoice.invoice_number,
                      'invoice_status': _status(invoice.status), 'currency': 'USD',
                      'total': format(total, '.2f'), 'finalized': True}],
        'attribution': {'elis_opportunity_id': str(order.elis_opportunity_id) if order.elis_opportunity_id else None,
                        'callrail_call_id': order.callrail_call_id}}


def _economic_snapshot(snapshot):
    value = deepcopy(snapshot)
    for invoice in value.get('invoices', []):
        invoice.pop('invoice_status', None)
    return value


async def capture_native_order(db, tenant_id, order_id):
    from app.services.shop_history_source import history_allowed_tenants
    if tenant_id not in history_allowed_tenants():
        return None
    # Same tenant lock as the history sweep serializes source observations.
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    if tenant is None:
        return None
    order = await db.scalar(select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.tenant_id == tenant_id))
    if order is None:
        return None
    prefix = f'native-completed:{order_id}:'
    previous = await db.scalar(select(ProviderOutboxEvent).where(
        ProviderOutboxEvent.tenant_id == tenant_id, ProviderOutboxEvent.event_type.in_(ETS_EVENTS),
        ProviderOutboxEvent.idempotency_key.like(prefix + '%'),
    ).order_by(ProviderOutboxEvent.payload['source_observation'].as_integer().desc()).limit(1))
    if order.source is not None and previous is None:
        return None
    if previous and not previous.payload.get('snapshot'):
        return None  # never reconstruct erased source evidence
    invoices = list(await db.scalars(select(Invoice).where(
        Invoice.tenant_id == tenant_id, Invoice.repair_order_id == order_id).limit(201)))
    now = datetime.now(timezone.utc)
    event_type = ETS_COMPLETED_EVENT
    try:
        if len(invoices) > 200:
            raise NativeCompletionHold('invoice_manifest_incomplete')
        snapshot = native_completed_snapshot(tenant_id=tenant_id, order=order, invoices=invoices, now=now)
    except NativeCompletionHold as exc:
        if previous is None:
            return None  # drafts are not revenue candidates
        event_type = ETS_HOLD_EVENT
        snapshot = {'source': 'dieselbridge', 'source_job_id': str(order_id),
                    'repair_order_uuid': str(order_id), 'hold_reason': str(exc)}
    if previous and _economic_snapshot(previous.payload['snapshot']) == _economic_snapshot(snapshot):
        return previous  # payment-only state changes are not new completion events
    revision = hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    sequence = previous.payload['source_observation'] + 1 if previous else 1
    event_id = uuid4()
    event = ProviderOutboxEvent(id=event_id, tenant_id=tenant_id, event_type=event_type,
        aggregate_type='repair_order', aggregate_id=order_id,
        idempotency_key=f'{prefix}{sequence}:{revision}', status=ProviderOutboxStatus.PENDING.value,
        available_at=now, created_at=now,
        payload={'schema_version': 2, 'source_system': 'dieselbridge', 'event_type': event_type,
                 'event_id': str(event_id), 'shop_id': str(tenant_id),
                 'occurred_at': snapshot.get('completed_at', now.isoformat()), 'observed_at': now.isoformat(),
                 'source_observation': sequence, 'source_revision': revision, 'snapshot': snapshot})
    db.add(event)
    await db.flush()
    return event
