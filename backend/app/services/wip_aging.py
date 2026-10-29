"""Source-aware, SELECT-only WIP clocks and complete scoped queue projection.

One evidence SELECT captures every eligible job and its current evidence. The
same in-memory snapshot drives all facets, filtering and paging. No ORM source
objects are mutated, and no invoice values or quote tokens are selected.
"""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import aliased

from app.core.vehicle_display import vehicle_display_label
from app.db.models.customer import Customer
from app.db.models.labor import Labor, LaborLineType
from app.db.models.mechanic_time import MechanicTimeSession, MechanicSessionType
from app.db.models.quote import Quote
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.schemas.wip_aging import WipAgingResponse, WipAgingRow, WipClock, WipFilters, WipSummary
from app.services import operation_execution, repair_order_schedule
from app.services.internal_fleet import fleet_display_name

CATEGORIES = ('approval', 'parts', 'technician', 'review', 'other_hold', 'active', 'preparation')
STAFF = frozenset({UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST, UserRole.MECHANIC})
ACTIVE_STATUSES = (
    RepairOrderStatus.DRAFT, RepairOrderStatus.QUOTED, RepairOrderStatus.DECLINED,
    RepairOrderStatus.APPROVED, RepairOrderStatus.ASSIGNED, RepairOrderStatus.ACKNOWLEDGED,
    RepairOrderStatus.IN_PROGRESS, RepairOrderStatus.PENDING_REVIEW,
)


def utc(value):
    return operation_execution.utc(value).astimezone(UTC) if value is not None else None


def unknown(issue='missing_timestamp'):
    return WipClock(state='unknown', issue=issue)


def clock(since, now, *, created_at=None, require_creation=False, inconsistent=False):
    if inconsistent:
        return unknown('inconsistent_evidence')
    if since is None or (require_creation and created_at is None):
        return unknown()
    since, created_at = utc(since), utc(created_at)
    if since > now or (created_at is not None and created_at > now):
        return unknown('future_timestamp')
    if created_at is not None and since < created_at:
        return unknown('inconsistent_evidence')
    return WipClock(state='known', since=since, seconds=int((now - since).total_seconds()))


def _valid_assignee(row, prefix):
    return row[f'{prefix}_user_id'] is not None


def _classification(row, now):
    """Only stage-specific evidence may start the current-wait clock."""
    status = row['status'].value if hasattr(row['status'], 'value') else row['status']
    created = row['created_at']
    wait = lambda since, **kw: clock(since, now, created_at=created, require_creation=True, **kw)
    hold = (row['hold_reason'] or '').strip() if status == 'in_progress' else ''
    if hold:
        category, reason = {
            'waiting_for_parts': ('parts', 'waiting_for_parts'),
            'waiting_for_customer_approval': ('approval', 'approval_hold'),
            'need_more_info': ('other_hold', 'need_more_info'),
            'switched_to_other_ro': ('other_hold', 'technician_switched'),
        }.get(hold, ('other_hold', 'other_hold'))
        inconsistent = bool(row['live_work'] or row['work_completed_at'])
        if row['held_at'] and row['work_started_at']:
            inconsistent |= utc(row['held_at']) < utc(row['work_started_at'])
        return category, reason, wait(row['held_at'], inconsistent=inconsistent)
    if status == 'pending_review':
        inconsistent = bool(row['live_work'] or row['hold_reason'])
        if row['work_completed_at'] and row['work_started_at']:
            inconsistent |= utc(row['work_completed_at']) < utc(row['work_started_at'])
        return 'review', 'awaiting_quality_review', wait(row['work_completed_at'], inconsistent=inconsistent)
    if status == 'quoted':
        # Latest revision was selected in SQL before checking these flags.
        bad = (row['quote_id'] is None or row['quote_approved'] or row['quote_declined']
               or row['quote_decision_at'] is not None)
        if not bad and not row['quote_sent']:
            if row['quote_sent_at'] is None:
                return 'preparation', 'quote_not_sent', unknown()
            bad = True
        published = wait(row['quote_sent_at'])
        if bad or published.state != 'known':
            return 'preparation', 'quote_evidence_unknown', unknown('inconsistent_evidence') if bad else published
        expiry = published.since + timedelta(days=7)
        if row['quote_expires_at'] is not None:
            explicit_expiry = utc(row['quote_expires_at'])
            if explicit_expiry < published.since:
                return 'preparation', 'quote_evidence_unknown', unknown('inconsistent_evidence')
            expiry = min(expiry, explicit_expiry)
        if now > expiry:
            return 'preparation', 'quote_expired', unknown()
        return 'approval', 'awaiting_customer_decision', published
    if status in {'approved', 'assigned', 'acknowledged'}:
        if status == 'approved':
            return 'technician', 'ready_to_start', unknown()
        inconsistent = (not _valid_assignee(row, 'order') or bool(row['work_started_at'])
                        or bool(row['work_completed_at']) or bool(row['live_work']))
        if status == 'acknowledged' and row['assigned_at'] and row['acknowledged_at']:
            inconsistent |= utc(row['acknowledged_at']) < utc(row['assigned_at'])
        if status == 'assigned' and row['acknowledged_at']:
            inconsistent = True
        if inconsistent:
            return 'technician', 'technician_timing_unknown', unknown('inconsistent_evidence')
        since = row['assigned_at'] if status == 'assigned' else row['acknowledged_at']
        reason = 'awaiting_acknowledgment' if status == 'assigned' else 'ready_to_start'
        return 'technician', reason, wait(since)
    if status == 'in_progress':
        return 'active', 'work_in_progress', WipClock(state='not_applicable')
    return 'preparation', 'revise_estimate' if status == 'declined' else 'prepare_estimate', unknown()


def evidence_statement(tenant_id, actor, native_predicate):
    """A single statement is the data snapshot for rows AND all aggregate facets."""
    order_tech, operation_tech = aliased(User), aliased(User)
    operation = aliased(Labor)
    latest_id = (select(Quote.id).where(
        Quote.tenant_id == RepairOrder.tenant_id, Quote.repair_order_id == RepairOrder.id,
        Quote.deleted_at.is_(None),
    ).order_by(Quote.revision.desc(), Quote.created_at.desc(), Quote.id.desc())
        .limit(1).correlate(RepairOrder).scalar_subquery())
    quote = aliased(Quote)
    live_work = select(MechanicTimeSession.id).where(
        MechanicTimeSession.tenant_id == RepairOrder.tenant_id,
        MechanicTimeSession.repair_order_id == RepairOrder.id,
        MechanicTimeSession.session_type == MechanicSessionType.REPAIR_ORDER,
        MechanicTimeSession.deleted_at.is_(None), MechanicTimeSession.ended_at.is_(None),
    ).correlate(RepairOrder).exists()
    ro_fields = ('id', 'order_number', 'status', 'created_at', 'hold_reason', 'held_at',
                 'assigned_at', 'acknowledged_at', 'work_started_at', 'work_completed_at',
                 'assigned_mechanic_id', 'scheduled_start_at', 'promised_finish_at')
    valid_user = lambda user: and_(user.tenant_id == tenant_id, user.role == UserRole.MECHANIC,
                                  user.is_active.is_(True), user.deleted_at.is_(None))
    query = (select(
        *(getattr(RepairOrder, key).label(key) for key in ro_fields),
        Customer.first_name.label('customer_first_name'), Customer.last_name.label('customer_last_name'),
        Customer.company_name.label('customer_company_name'), Customer.is_internal_fleet.label('is_internal_fleet'),
        Vehicle.year.label('vehicle_year'), Vehicle.make.label('vehicle_make'),
        Vehicle.model.label('vehicle_model'), Vehicle.unit_number.label('vehicle_unit_number'),
        quote.id.label('quote_id'), quote.sent_to_customer.label('quote_sent'),
        quote.sent_at.label('quote_sent_at'), quote.is_approved.label('quote_approved'),
        quote.is_declined.label('quote_declined'), quote.decision_at.label('quote_decision_at'),
        quote.expires_at.label('quote_expires_at'),
        order_tech.id.label('order_user_id'), order_tech.first_name.label('order_first_name'),
        order_tech.last_name.label('order_last_name'), operation.mechanic_id.label('operation_mechanic_id'),
        operation_tech.id.label('operation_user_id'), operation_tech.first_name.label('operation_first_name'),
        operation_tech.last_name.label('operation_last_name'), live_work.label('live_work'),
    ).select_from(RepairOrder)
        .join(Customer, and_(Customer.id == RepairOrder.customer_id, Customer.tenant_id == tenant_id,
                             Customer.deleted_at.is_(None)))
        .join(Vehicle, and_(Vehicle.id == RepairOrder.vehicle_id, Vehicle.tenant_id == tenant_id,
                            Vehicle.deleted_at.is_(None)))
        .join(Tenant, and_(Tenant.id == RepairOrder.tenant_id, Tenant.is_active.is_(True), Tenant.deleted_at.is_(None)))
        .outerjoin(quote, and_(quote.id == latest_id, quote.tenant_id == tenant_id))
        .outerjoin(order_tech, and_(order_tech.id == RepairOrder.assigned_mechanic_id, valid_user(order_tech)))
        .outerjoin(operation, and_(operation.repair_order_id == RepairOrder.id, operation.tenant_id == tenant_id,
                              operation.deleted_at.is_(None), operation.line_type != LaborLineType.SUBLET,
                              or_(operation.execution_status.is_(None), operation.execution_status == 'pending')))
        .outerjoin(operation_tech, and_(operation_tech.id == operation.mechanic_id, valid_user(operation_tech)))
        .where(RepairOrder.tenant_id == tenant_id, RepairOrder.deleted_at.is_(None),
               RepairOrder.vehicle_released_at.is_(None), RepairOrder.status.in_(ACTIVE_STATUSES), native_predicate))
    if actor.role == UserRole.MECHANIC:
        query = query.where(operation_execution.job_scope(tenant_id, actor.id))
    return query


def project_rows(evidence, *, now, fleet_name):
    grouped = {}
    for raw in evidence:
        raw = dict(raw)
        item = grouped.setdefault(raw['id'], {'raw': raw, 'names': set(), 'invalid': False, 'assigned': False})
        for prefix, foreign_key in [('order', 'assigned_mechanic_id'), ('operation', 'operation_mechanic_id')]:
            if raw[foreign_key] is not None:
                if not _valid_assignee(raw, prefix):
                    item['invalid'] = True
                else:
                    name = ' '.join(filter(None, [raw[f'{prefix}_first_name'], raw[f'{prefix}_last_name']])).strip()
                    item['assigned'] = True
                    if name:
                        item['names'].add(name)
    result = []
    for item in grouped.values():
        row, names = item['raw'], sorted(item['names'])
        category, reason, current_wait = _classification(row, now)
        status = row['status'].value if hasattr(row['status'], 'value') else row['status']
        customer = SimpleNamespace(first_name=row['customer_first_name'], last_name=row['customer_last_name'],
                                   company_name=row['customer_company_name'], is_internal_fleet=row['is_internal_fleet'])
        created, promise, scheduled = utc(row['created_at']), utc(row['promised_finish_at']), utc(row['scheduled_start_at'])
        valid_promise = (promise is not None and created is not None and created <= now and promise >= created
                         and (scheduled is None or promise > scheduled))
        promise = promise if valid_promise else None
        overdue = repair_order_schedule.is_overdue(SimpleNamespace(status=status, promised_finish_at=promise), now)
        result.append(WipAgingRow(
            id=str(row['id']), order_number=row['order_number'], status=status,
            customer_name=fleet_display_name(customer, fleet_name),
            vehicle_info=vehicle_display_label(row['vehicle_year'], row['vehicle_make'], row['vehicle_model'], row['vehicle_unit_number']),
            vehicle_unit_number=row['vehicle_unit_number'], category=category, reason=reason,
            hold_reason=(row['hold_reason'] or None) if status == 'in_progress' else None,
            assignment='unknown' if item['invalid'] else ('assigned' if item['assigned'] else 'unassigned'),
            technician_names=names, order_age=clock(row['created_at'], now), current_wait=current_wait,
            promised_finish_at=promise, overdue_seconds=int((now - promise).total_seconds()) if overdue else None,
            is_overdue=overdue, action_lane='needs_action' if status in {'draft', 'quoted', 'declined', 'pending_review'} else 'on_floor',
        ))
    return result


def _sort_key(row, sort):
    age = (-(row.order_age.seconds or 0) if row.order_age.state == 'known' else float('inf'), row.id)
    wait = ({'known': 0, 'unknown': 1, 'not_applicable': 2}[row.current_wait.state], -(row.current_wait.seconds or 0))
    if sort == 'oldest_order':
        return age
    if sort == 'oldest_wait':
        return (*wait, *age)
    priority = 0 if row.hold_reason else {'review': 1, 'approval': 2, 'technician': 3, 'preparation': 4, 'active': 5}.get(row.category, 0)
    return (not row.is_overdue, priority, *wait, *age)


def build_response(rows, *, now, zone, scope, filters, offset, limit, search_index=None):
    needle = filters.search.strip().casefold()
    searched = [row for row in rows if not needle or needle in ' '.join([
        row.order_number, row.customer_name, row.vehicle_info, row.vehicle_unit_number or '', *row.technician_names,
        (search_index or {}).get(row.id, ''),
    ]).casefold()]
    counts = {key: 0 for key in CATEGORIES}
    for row in searched:
        counts[row.category] += 1
    filtered = [row for row in searched
                if (filters.category == 'all' or row.category == filters.category)
                and (not filters.overdue_only or row.is_overdue)
                and (filters.timing == 'all' or row.current_wait.state == filters.timing)]
    filtered.sort(key=lambda row: _sort_key(row, filters.sort))
    items = filtered[offset:offset + limit]
    return WipAgingResponse(
        as_of=now, timezone=zone, scope=scope, filters=filters,
        summary=WipSummary(total_jobs=len(searched), category_counts=counts,
                           overdue_jobs=sum(row.is_overdue for row in searched),
                           unknown_wait_jobs=sum(row.current_wait.state == 'unknown' for row in searched)),
        filtered_total=len(filtered), offset=offset, limit=limit,
        has_more=offset + len(items) < len(filtered), items=items,
    )


async def read_wip_aging(db, actor, *, native_predicate, filters, offset=0, limit=50, now=None):
    if (actor.role not in STAFF or not actor.tenant_id or not actor.is_active or actor.deleted_at is not None):
        raise HTTPException(403, 'Access denied')
    # no_autoflush prevents a caller's pending ORM changes from becoming side
    # effects of this read path. Authentication has no authority to repair rows.
    with db.no_autoflush:
        tenant = (await db.execute(select(Tenant.timezone, Tenant.fleet_company_name).where(
            Tenant.id == actor.tenant_id, Tenant.is_active.is_(True), Tenant.deleted_at.is_(None),
        ))).first()
        if tenant is None:
            raise HTTPException(403, 'Access denied')
        instant = utc(now or datetime.now(UTC))
        evidence = (await db.execute(evidence_statement(actor.tenant_id, actor, native_predicate))).mappings().all()
    rows = project_rows(evidence, now=instant, fleet_name=tenant.fleet_company_name)
    search_index = {str(row['id']): ' '.join(filter(None, [row['customer_first_name'],
        row['customer_last_name'], row['customer_company_name']])) for row in evidence}
    return build_response(rows, now=instant, zone=repair_order_schedule.valid_timezone(tenant.timezone),
                          scope='assigned' if actor.role == UserRole.MECHANIC else 'shop',
                          filters=filters, offset=offset, limit=limit, search_index=search_index)
