"""DB-151 bounded task projection, with isolated rollback-only source reads.

A candidate is a pointer to the owning workflow, never a mutation or a verified
account balance. Source failures cannot poison a later source's transaction.
"""
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import logging

from fastapi import HTTPException
from sqlalchemy import and_, case, or_, select, text
from sqlalchemy.orm import aliased

from app.core.config import settings
from app.db.models.customer import Customer
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import InvoicePaymentLedgerEvent, InvoiceSettlement
from app.db.models.parts_operations import CoreObligation, PurchaseOrder, PurchaseOrderLine, VendorReturn, VendorReturnLine
from app.db.models.payment import Payment
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.db.models.vehicle import Vehicle
from app.db.session import AsyncSessionLocal
from app.schemas.shop_work_overview import ShopWorkDestination, ShopWorkItem, ShopWorkOverview, ShopWorkSource
from app.services import operation_execution, repair_order_schedule, wip_aging
from app.services.customer_receivables import BAD_BASELINE_EVENTS, trusted_settlement
from app.services.native_record_classification import load_native_record_policy
from app.services.parts_operations_service import PARTS_READ_ROLES

logger = logging.getLogger(__name__)
SOURCE_CAP = 5000
SOURCES = ('repairs', 'schedule', 'inventory', 'purchasing', 'returns', 'cores', 'receivables')
ACTIVE_RETURNS = ('draft', 'submitted', 'shipped')


@asynccontextmanager
async def source_session(factory):
    async with factory() as db:
        try:
            with db.no_autoflush:
                # SQLite is used only by isolated tests. PostgreSQL enforces the
                # same SELECT-only boundary for every source, including finance.
                if db.bind.dialect.name == 'postgresql':
                    await db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
                yield db
        finally:
            await db.rollback()


def item(source, kind, identity, title, reason, action_label, status, **extra):
    view = extra.pop('view', None)
    return ShopWorkItem(id=f'{kind}:{identity}', source=source,
                        destination=ShopWorkDestination(kind=kind, id=str(identity), view=view),
                        title=title, reason=reason, action_label=action_label, status=status, **extra)


def stamp(value):
    return wip_aging.utc(value)


async def read_repairs(db, tenant_id, actor, native_predicate, now, fleet_name, finance_allowed):
    # WIP deliberately has no page cap: one evidence snapshot supplies its full
    # population and all facets. Reuse that exact snapshot, not its public page.
    evidence = (await db.execute(wip_aging.evidence_statement(tenant_id, actor, native_predicate))).mappings().all()
    rows = wip_aging.project_rows(evidence, now=now, fleet_name=fleet_name)
    raw = {str(row['id']): row for row in evidence}
    actions, upcoming = [], []
    for row in rows:
        origin = raw[row.id]
        created = stamp(origin['created_at'])
        common = dict(view=row.action_lane, created_at=created, related_repair_order_ids=[row.id])
        if row.category != 'active' or row.is_overdue:
            actions.append(item('repairs', 'repair_order', row.id, row.order_number,
                                'repair_promise_overdue' if row.is_overdue else row.reason,
                                'Review order', row.status,
                                due_at=row.promised_finish_at if row.is_overdue else None,
                                due_kind='repair_promise' if row.is_overdue else None,
                                evidence='review_required' if row.current_wait.state == 'unknown' else 'verified',
                                **common))
            continue
        commitments = []
        start = stamp(origin['scheduled_start_at'])
        # Match WIP's invalid-creation safeguard for both commitment clocks.
        if created and created <= now and start and start >= created and start > now:
            commitments.append((start, 'repair_start', 'scheduled_repair_start'))
        if row.promised_finish_at and row.promised_finish_at > now:
            commitments.append((row.promised_finish_at, 'repair_promise', 'repair_promise'))
        if commitments:
            due, kind, reason = min(commitments)
            upcoming.append(item('schedule', 'repair_order', row.id, row.order_number,
                                 reason, 'Review order', row.status, due_at=due, due_kind=kind, **common))
    closeout = await read_closeout(db, tenant_id, actor, native_predicate, finance_allowed)
    closeout_ids = {row.destination.id for row in closeout}
    actions = [row for row in actions if row.destination.id not in closeout_ids] + closeout
    upcoming = [row for row in upcoming if row.destination.id not in closeout_ids]
    return actions, upcoming, len(rows)


async def read_closeout(db, tenant_id, actor, native_predicate, finance_allowed):
    # Existing native completed/pending-Zelle membership, with all join sides
    # tenant/deletion scoped. Issued invoices belong to account review instead.
    invoice_link = and_(Invoice.tenant_id == tenant_id, Invoice.repair_order_id == RepairOrder.id,
                        Invoice.deleted_at.is_(None))
    has_invoice = select(Invoice.id).where(invoice_link).correlate(RepairOrder).exists()
    unbilled = and_(RepairOrder.status == RepairOrderStatus.COMPLETED, ~has_invoice)
    pending = select(Invoice.id).where(invoice_link, Invoice.zelle_pending_submitted_at.is_not(None),
        Invoice.status.not_in((InvoiceStatus.PAID, InvoiceStatus.CANCELLED)),
    ).correlate(RepairOrder).exists()
    condition = or_(unbilled, pending) if finance_allowed else unbilled
    fields = [RepairOrder.id, RepairOrder.order_number, RepairOrder.status, RepairOrder.created_at]
    if finance_allowed:
        fields.append(pending.label('pending'))
    statement = select(*fields).join(Customer, and_(Customer.id == RepairOrder.customer_id,
        Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None))).join(Vehicle, and_(
        Vehicle.id == RepairOrder.vehicle_id, Vehicle.tenant_id == tenant_id, Vehicle.deleted_at.is_(None)))
    statement = statement.where(RepairOrder.tenant_id == tenant_id, RepairOrder.deleted_at.is_(None),
        RepairOrder.vehicle_released_at.is_(None), native_predicate, condition)
    if actor.role == UserRole.MECHANIC:
        statement = statement.where(operation_execution.job_scope(tenant_id, actor.id))
    result = []
    for row in (await db.execute(statement)).all():
        payment = finance_allowed and row.pending
        result.append(item('repairs', 'repair_order', row.id, row.order_number,
            'review_payment' if payment else 'review_closeout',
            'Review payment' if payment else 'Review closeout',
            row.status.value, view='needs_action' if payment else 'ready_to_close',
            created_at=stamp(row.created_at), related_repair_order_ids=[str(row.id)], evidence='review_required'))
    return result


async def read_inventory(db, tenant_id, now):
    from app.api.v1.endpoints.parts_operations import _part_metric_expressions, _part_projection_rows
    _, _, recommendation = _part_metric_expressions(tenant_id)
    records = list((await db.scalars(select(Inventory).where(
        Inventory.tenant_id == tenant_id, Inventory.deleted_at.is_(None),
        Inventory.ets_retired_at.is_(None), Inventory.is_placeholder.is_(False), recommendation > 0,
    ).order_by(Inventory.id).limit(SOURCE_CAP + 1))).all())
    capped = len(records) > SOURCE_CAP
    records = records[:SOURCE_CAP]
    by_id = {str(record.id): record for record in records}
    projected = await _part_projection_rows(db, tenant_id, items=records)
    rows = [item('inventory', 'inventory', row['id'], row['name'], 'stock_preparation', 'Review stock',
                 'needs_review', created_at=stamp(by_id[row['id']].created_at),
                 quantity=row['recommended_order_packages'],
                 related_repair_order_ids=sorted({source['repair_order_id'] for source in row['repair_sources']}))
            for row in projected if row['recommended_order_packages'] > 0]
    return rows, [], capped


async def read_purchasing(db, tenant_id, now):
    from app.api.v1.endpoints.parts_operations import _purchase_order_quantities
    records = list((await db.scalars(select(PurchaseOrder).where(
        PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.deleted_at.is_(None),
        PurchaseOrder.status.in_(('draft', 'submitted', 'partially_received')),
    ).order_by(PurchaseOrder.id).limit(SOURCE_CAP + 1))).all())
    capped = len(records) > SOURCE_CAP
    records = records[:SOURCE_CAP]
    lines = {row.id: [] for row in records}
    if lines:
        for line in (await db.scalars(select(PurchaseOrderLine).where(
            PurchaseOrderLine.tenant_id == tenant_id, PurchaseOrderLine.deleted_at.is_(None),
            PurchaseOrderLine.purchase_order_id.in_(lines),
        ))).all():
            lines[line.purchase_order_id].append(line)
    actions, upcoming = [], []
    for row in records:
        remaining = _purchase_order_quantities(lines[row.id])['remaining_quantity']
        draft = row.status == 'draft'
        if not draft and remaining <= 0:
            continue
        due = stamp(row.expected_at) if not draft else None
        task = item('purchasing', 'purchase_order', row.id, row.po_number,
                    'purchase_draft' if draft else 'delivery_review',
                    'Review purchase draft' if draft else 'Review delivery', row.status,
                    view='orders' if draft else 'receiving', created_at=stamp(row.created_at),
                    due_at=due, due_kind='expected_delivery' if due else None, quantity=remaining)
        (upcoming if due and due > now else actions).append(task)
    return actions, upcoming, capped


async def read_returns(db, tenant_id, now):
    records = list((await db.scalars(select(VendorReturn).where(
        VendorReturn.tenant_id == tenant_id, VendorReturn.deleted_at.is_(None),
        VendorReturn.status.in_(ACTIVE_RETURNS),
    ).order_by(VendorReturn.id).limit(SOURCE_CAP + 1))).all())
    capped = len(records) > SOURCE_CAP
    labels = {'draft': ('return_review', 'Review return'), 'submitted': ('shipment_review', 'Review shipment'),
              'shipped': ('supplier_credit_review', 'Review supplier credit')}
    return [item('returns', 'vendor_return', row.id, row.return_number, *labels[row.status], row.status,
                 created_at=stamp(row.created_at)) for row in records[:SOURCE_CAP]], [], capped


async def read_cores(db, tenant_id, now):
    owned_by_return = select(VendorReturnLine.id).join(VendorReturn, and_(
        VendorReturn.id == VendorReturnLine.vendor_return_id, VendorReturn.tenant_id == tenant_id,
        VendorReturn.deleted_at.is_(None), VendorReturn.status.in_(ACTIVE_RETURNS),
    )).where(VendorReturnLine.tenant_id == tenant_id, VendorReturnLine.deleted_at.is_(None),
             VendorReturnLine.core_obligation_id == CoreObligation.id).correlate(CoreObligation).exists()
    records = (await db.execute(select(CoreObligation, Inventory.name, RepairOrder.id).outerjoin(Inventory, and_(
        Inventory.id == CoreObligation.inventory_id, Inventory.tenant_id == tenant_id, Inventory.deleted_at.is_(None),
    )).outerjoin(PartsUsage, and_(
        PartsUsage.id == CoreObligation.parts_usage_id, PartsUsage.tenant_id == tenant_id, PartsUsage.deleted_at.is_(None),
    )).outerjoin(RepairOrder, and_(
        RepairOrder.id == PartsUsage.repair_order_id, RepairOrder.tenant_id == tenant_id, RepairOrder.deleted_at.is_(None),
    )).where(CoreObligation.tenant_id == tenant_id, CoreObligation.deleted_at.is_(None),
             CoreObligation.status.in_(('expected', 'on_hand')), ~owned_by_return)
        .order_by(CoreObligation.id).limit(SOURCE_CAP + 1))).all()
    return [item('cores', 'core', row.id, name or 'Core obligation',
                 'core_recovery' if row.status == 'expected' else 'core_return',
                 'Review core recovery' if row.status == 'expected' else 'Review core return', row.status,
                 created_at=stamp(row.created_at), quantity=row.quantity,
                 related_repair_order_ids=[str(order_id)] if order_id else [])
            for row, name, order_id in records[:SOURCE_CAP]], [], len(records) > SOURCE_CAP


class IncompleteSource(Exception):
    """Bounded evidence could not establish the source population."""


async def read_receivables(db, tenant_id, now):
    policy = load_native_record_policy()
    if not policy.available:
        raise IncompleteSource('classification_unavailable')
    successor = aliased(Invoice)
    superseded = select(successor.id).where(
        successor.tenant_id == tenant_id, successor.deleted_at.is_(None),
        successor.supersedes_invoice_id == Invoice.id,
    ).correlate(Invoice).exists()
    # A non-null bill-to is authoritative, even if missing/deleted/foreign.
    customer_identity = case((Invoice.billed_customer_id.is_not(None), Invoice.billed_customer_id),
                             else_=RepairOrder.customer_id)
    records = (await db.execute(select(Invoice, RepairOrder, Customer).join(RepairOrder, and_(
        RepairOrder.id == Invoice.repair_order_id, RepairOrder.tenant_id == tenant_id,
        RepairOrder.deleted_at.is_(None), RepairOrder.is_internal.is_(False),
    )).join(Customer, and_(Customer.id == customer_identity, Customer.tenant_id == tenant_id,
                         Customer.deleted_at.is_(None), Customer.is_internal_fleet.is_(False)))
        .where(Invoice.tenant_id == tenant_id, Invoice.deleted_at.is_(None), Invoice.is_internal.is_(False),
               Invoice.status.in_((InvoiceStatus.SENT, InvoiceStatus.PAID, InvoiceStatus.OVERDUE)),
               Invoice.voided_at.is_(None), ~superseded,
               or_(Invoice.source.is_(None), Invoice.source != 'easy_truck_shop_import'),
               or_(RepairOrder.source.is_(None), RepairOrder.source != 'easy_truck_shop_import'),
               or_(Invoice.accounting_policy.is_(None), Invoice.accounting_policy != 'historical_export_hold'))
        .order_by(Invoice.id).limit(SOURCE_CAP + 1))).all()
    capped = len(records) > SOURCE_CAP
    records = records[:SOURCE_CAP]
    ids = [invoice.id for invoice, _, _ in records]
    settlements = {}
    bad, imported = set(), set()
    if ids:
        linked = list((await db.scalars(select(InvoiceSettlement).where(
            InvoiceSettlement.tenant_id == tenant_id, InvoiceSettlement.invoice_id.in_(ids),
        ).limit(SOURCE_CAP + 1))).all())
        if len(linked) > SOURCE_CAP:
            raise IncompleteSource('source_limit')
        for row in linked:
            settlements.setdefault(row.invoice_id, []).append(row)
        bad = set((await db.scalars(select(InvoicePaymentLedgerEvent.invoice_id).where(
            InvoicePaymentLedgerEvent.tenant_id == tenant_id, InvoicePaymentLedgerEvent.invoice_id.in_(ids),
            InvoicePaymentLedgerEvent.event_type.in_(BAD_BASELINE_EVENTS),
        ).distinct())).all())
        imported = set((await db.scalars(select(Payment.invoice_id).where(
            Payment.tenant_id == tenant_id, Payment.invoice_id.in_(ids), Payment.deleted_at.is_(None),
            Payment.source == 'easy_truck_shop_import',
        ).distinct())).all())
    candidates = {}
    for invoice, order, customer in records:
        classification = policy.classify(invoice, order, customer.id, tenant_id=tenant_id)
        if classification == 'test':
            continue
        linked = settlements.get(invoice.id, [])
        trusted = (len(linked) == 1 and trusted_settlement(invoice, linked[0], customer_id=customer.id,
                                                          bad_baseline=invoice.id in bad))
        if (invoice.id in imported or not trusted
                or linked[0].principal_total > linked[0].confirmed_principal):
            if customer.id not in candidates:
                name = customer.company_name or ' '.join(filter(None, [customer.first_name, customer.last_name])) or 'Customer account'
                candidates[customer.id] = item('receivables', 'customer_account', customer.id, name,
                    'account_verification_required', 'Review account', 'review_required', evidence='review_required')
    return list(candidates.values()), [], capped


def action_sort(row):
    if row.reason == 'repair_promise_overdue':
        band = 0
    elif row.source == 'repairs':
        band = 2 if row.reason in {'prepare_estimate', 'revise_estimate', 'quote_not_sent', 'quote_expired', 'quote_evidence_unknown'} else 1
    else:
        band = 4 if row.source == 'inventory' else 3
    latest = datetime.max.replace(tzinfo=UTC)
    return band, row.due_at or latest, row.created_at or latest, row.id


async def read_shop_work_overview(actor, *, native_predicate, limit=50, upcoming_limit=20, now=None, session_factory=None):
    if actor.role not in wip_aging.STAFF or not actor.tenant_id or not actor.is_active or actor.deleted_at is not None:
        raise HTTPException(403, 'Access denied')
    # This exact existing authorization runs before any financial source read.
    from app.api.v1.endpoints.customer_receivables import _authorize
    try:
        _authorize(actor)
        finance_allowed = True
    except HTTPException:
        finance_allowed = False
    factory = session_factory or AsyncSessionLocal
    tenant_id = actor.tenant_id
    now = stamp(now or datetime.now(UTC))
    async with source_session(factory) as db:
        tenant = (await db.execute(select(Tenant.timezone, Tenant.fleet_company_name, Tenant.parts_operations_enabled).where(
            Tenant.id == tenant_id, Tenant.is_active.is_(True), Tenant.deleted_at.is_(None),
        ))).first()
        if tenant is None:
            raise HTTPException(403, 'Access denied')
    statuses = {}
    actions, upcoming = [], []
    active_jobs = None
    try:
        async with source_session(factory) as db:
            repair_actions, scheduled, active_jobs = await read_repairs(db, tenant_id, actor, native_predicate, now, tenant.fleet_company_name, finance_allowed)
        actions.extend(repair_actions)
        upcoming.extend(scheduled)
        for source, rows in [('repairs', repair_actions), ('schedule', scheduled)]:
            statuses[source] = ShopWorkSource(id=source, state='ready', checked_at=now, total=len(rows))
    except Exception:
        logger.warning('Shop work repairs source unavailable')
        for source in ('repairs', 'schedule'):
            statuses[source] = ShopWorkSource(id=source, state='unavailable', reason='source_unavailable')
    readers = {'inventory': read_inventory, 'purchasing': read_purchasing, 'returns': read_returns,
               'cores': read_cores, 'receivables': read_receivables}
    for source, reader in readers.items():
        if (source == 'receivables' and not finance_allowed) or (source != 'receivables' and actor.role not in PARTS_READ_ROLES):
            statuses[source] = ShopWorkSource(id=source, state='restricted', reason='permission_required')
            continue
        if source != 'receivables' and not (settings.PARTS_OPERATIONS_V1_ENABLED and tenant.parts_operations_enabled):
            statuses[source] = ShopWorkSource(id=source, state='disabled', reason='parts_disabled')
            continue
        try:
            async with source_session(factory) as db:
                current, future, capped = await reader(db, tenant_id, now)
            actions.extend(current)
            upcoming.extend(future)
            partial = capped or source == 'receivables'
            statuses[source] = ShopWorkSource(id=source, state='partial' if partial else 'ready', checked_at=now,
                reason='account_review_only' if source == 'receivables' else ('source_limit' if capped else None),
                total=None if capped else len(current) + len(future), has_more=capped)
        except IncompleteSource as exc:
            statuses[source] = ShopWorkSource(id=source, state='partial', checked_at=now, reason=str(exc), has_more=True)
        except Exception:
            logger.warning('Shop work %s source unavailable', source)
            statuses[source] = ShopWorkSource(id=source, state='unavailable', reason='source_unavailable')
    # Only actual projected PartsUsage associations can transfer a parts hold
    # to procurement. Approval/review and overdue promise work remain independent.
    procurement_orders = {identity for row in actions if row.source == 'inventory' for identity in row.related_repair_order_ids}
    actions = [row for row in actions if not (row.source == 'repairs' and row.reason == 'waiting_for_parts'
                                             and row.destination.id in procurement_orders)]
    if statuses['repairs'].state == 'ready':
        statuses['repairs'].total = sum(row.source == 'repairs' for row in actions)
    actions.sort(key=action_sort)
    upcoming.sort(key=lambda row: (row.due_at, row.created_at or datetime.max.replace(tzinfo=UTC), row.id))
    action_unknown = any(statuses[source].state in {'partial', 'unavailable'} for source in SOURCES if source != 'schedule')
    upcoming_unknown = any(statuses[source].state in {'partial', 'unavailable'} for source in ('schedule', 'purchasing'))
    action_page, upcoming_page = actions[:limit], upcoming[:upcoming_limit]
    for source, status in statuses.items():
        status.shown = sum(row.source == source for row in [*action_page, *upcoming_page])
        status.has_more |= status.total is not None and status.shown < status.total
    return ShopWorkOverview(as_of=now, timezone=repair_order_schedule.valid_timezone(tenant.timezone),
        scope='assigned' if actor.role == UserRole.MECHANIC else 'shop', active_jobs=active_jobs,
        sources=[statuses[source] for source in SOURCES], actions=action_page, upcoming=upcoming_page,
        actions_total=None if action_unknown else len(actions), upcoming_total=None if upcoming_unknown else len(upcoming),
        has_more_actions=len(actions) > limit or any(statuses[source].has_more and statuses[source].total is None for source in SOURCES if source != 'schedule'),
        has_more_upcoming=len(upcoming) > upcoming_limit or any(statuses[source].has_more and statuses[source].total is None for source in ('schedule', 'purchasing')))
