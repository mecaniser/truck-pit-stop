"""Transactional conversion and reduced, role-gated recommendation provenance."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import and_, select
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.recommended_service import RecommendedService
from app.db.models.recommendation_conversion import RecommendationConversion
from app.db.models.labor import Labor, LaborLineType
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.schemas.recommendation_conversion import RecommendationConversionResponse, RecommendationSourceResponse
from app.services.financial_transaction_lock import lock_tenant_financials
from app.services.internal_fleet import fleet_labor_uses_customer_rate
from app.services.repair_order_status_sets import EDITABLE_RO_STATUSES, INTERNAL_FROZEN_RO_STATUSES

STAFF_ROLES = (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST)
COMPLETED = (RepairOrderStatus.COMPLETED, RepairOrderStatus.INVOICED, RepairOrderStatus.PAID)


def fail(code, message, *, status=409, conversion=None):
    detail = {"code": code, "message": message}
    if conversion is not None:
        detail['conversion'] = conversion.model_dump(mode='json')
    raise HTTPException(status_code=status, detail=detail)


def can_convert(order):
    return bool(order.deleted_at is None and order.source != 'easy_truck_shop_import'
                and not (order.pricing_locked_at and order.pricing_lock_reason != 'quote_sent')
                and (order.status not in INTERNAL_FROZEN_RO_STATUSES if order.is_internal else order.status in EDITABLE_RO_STATUSES))


def policy_rate(order, tenant):
    return Decimal(tenant.labor_rate if not order.is_internal or fleet_labor_uses_customer_rate(order) else tenant.internal_labor_rate)


def scoped_order(order_id, tenant_id, *, include_deleted=False):
    query = select(RepairOrder).join(Customer, and_(Customer.id == RepairOrder.customer_id, Customer.tenant_id == tenant_id)).join(Vehicle, and_(Vehicle.id == RepairOrder.vehicle_id, Vehicle.tenant_id == tenant_id)).where(
        RepairOrder.id == order_id, RepairOrder.tenant_id == tenant_id,
        Customer.deleted_at.is_(None), Vehicle.deleted_at.is_(None))
    if not include_deleted:
        query = query.where(RepairOrder.deleted_at.is_(None))
    return query


async def current_conversion(db, tenant_id, recommendation_id):
    return await db.scalar(select(RecommendationConversion).where(
        RecommendationConversion.tenant_id == tenant_id,
        RecommendationConversion.recommendation_id == recommendation_id,
        RecommendationConversion.superseded_at.is_(None)))


async def projection_context(db, conversions):
    """Bound list projection to three reads, regardless of recommendation count."""
    if not conversions:
        return {}, set(), {}
    tenant_id = conversions[0].tenant_id
    order_ids = {value for c in conversions for value in (c.source_order_id, c.target_order_id)}
    orders = (await db.scalars(select(RepairOrder).join(Customer, and_(
        Customer.id == RepairOrder.customer_id, Customer.tenant_id == tenant_id)).join(Vehicle, and_(
        Vehicle.id == RepairOrder.vehicle_id, Vehicle.tenant_id == tenant_id)).where(
        RepairOrder.id.in_(order_ids), RepairOrder.tenant_id == tenant_id,
        Customer.deleted_at.is_(None), Vehicle.deleted_at.is_(None)))).all()
    lines = (await db.execute(select(Labor.id, Labor.repair_order_id).where(
        Labor.id.in_([c.target_labor_id for c in conversions]), Labor.tenant_id == tenant_id,
        Labor.deleted_at.is_(None)))).all()
    recs = (await db.scalars(select(RecommendedService).where(
        RecommendedService.id.in_([c.recommendation_id for c in conversions]),
        RecommendedService.tenant_id == tenant_id))).all()
    return {o.id: o for o in orders}, set(lines), {r.id: r for r in recs}


async def project(db, conversion, context=None):
    orders, lines, recs = context or await projection_context(db, [conversion])
    source = orders.get(conversion.source_order_id)
    if source is not None and source.deleted_at is not None:
        source = None
    target = orders.get(conversion.target_order_id)
    line = (conversion.target_labor_id, conversion.target_order_id) in lines
    rec = recs.get(conversion.recommendation_id)
    state = _conversion_state(
        conversion, target.status if target else None,
        target is not None and target.deleted_at is None, line)
    unresolved = rec is not None and rec.deleted_at is None and not rec.is_resolved and rec.resolved_by_repair_order_id is None
    return RecommendationConversionResponse(
        id=conversion.id, recommendation_id=conversion.recommendation_id,
        source_order=dict(id=conversion.source_order_id, order_number=conversion.source_order_number, available=source is not None),
        source_description=conversion.source_description,
        target_order=dict(id=conversion.target_order_id, order_number=conversion.target_order_number,
                          status=target.status if target else RepairOrderStatus.CANCELLED,
                          available=target is not None and target.deleted_at is None),
        labor_id=conversion.target_labor_id, state=state, created_at=conversion.created_at,
        can_replace=bool(unresolved and state in ('operation_removed','target_cancelled','target_deleted') and source is not None and source.status != RepairOrderStatus.CANCELLED),
        can_resolve=bool(unresolved and state == 'active' and target.status in COMPLETED))


async def projections(db, tenant_id, recommendation_ids):
    if not recommendation_ids:
        return {}
    rows = (await db.scalars(select(RecommendationConversion).where(
        RecommendationConversion.tenant_id == tenant_id,
        RecommendationConversion.recommendation_id.in_(recommendation_ids),
        RecommendationConversion.superseded_at.is_(None)))).all()
    context = await projection_context(db, rows)
    return {row.recommendation_id: await project(db, row, context) for row in rows}


async def line_sources(db, tenant_id, order_id, labor_ids):
    """Read the reduced labor provenance in one query, including lifecycle state."""
    if not labor_ids:
        return {}
    target = scoped_order(order_id, tenant_id, include_deleted=True).with_only_columns(
        RepairOrder.id, RepairOrder.status, RepairOrder.deleted_at).subquery()
    source_available = scoped_order(
        RecommendationConversion.source_order_id, tenant_id,
    ).with_only_columns(RepairOrder.id).correlate(RecommendationConversion).exists()
    rows = (await db.execute(select(
        RecommendationConversion, target.c.id, target.c.status, target.c.deleted_at,
        Labor.id, source_available,
    ).outerjoin(target, target.c.id == RecommendationConversion.target_order_id).outerjoin(
        Labor, and_(Labor.id == RecommendationConversion.target_labor_id,
                    Labor.tenant_id == tenant_id,
                    Labor.repair_order_id == RecommendationConversion.target_order_id,
                    Labor.deleted_at.is_(None)),
    ).where(
        RecommendationConversion.tenant_id == tenant_id,
        RecommendationConversion.target_order_id == order_id,
        RecommendationConversion.target_labor_id.in_(labor_ids)))).all()
    result = {}
    for row, target_id, target_status, target_deleted_at, labor_id, source_exists in rows:
        result[row.target_labor_id] = RecommendationSourceResponse(
            conversion_id=row.id, recommendation_id=row.recommendation_id,
            source_order=dict(id=row.source_order_id, order_number=row.source_order_number,
                              available=source_exists),
            description=row.source_description,
            state=_conversion_state(row, target_status,
                                    target_id is not None and target_deleted_at is None,
                                    labor_id is not None))
    return result


def _conversion_state(conversion, target_status, target_available, line_available):
    if conversion.superseded_at is not None:
        return 'superseded'
    if not target_available:
        return 'target_deleted'
    if target_status == RepairOrderStatus.CANCELLED:
        return 'target_cancelled'
    if not line_available:
        return 'operation_removed'
    return 'active'


def request_hash(target_id, recommendation_id, body):
    value = dict(target_id=str(target_id), recommendation_id=str(recommendation_id),
                 hours=format(body.hours.quantize(Decimal('.01')), 'f'),
                 hourly_rate=format(body.hourly_rate.quantize(Decimal('.01')), 'f'),
                 replaces_conversion_id=str(body.replaces_conversion_id) if body.replaces_conversion_id else None)
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


async def convert(db, *, target_id, recommendation_id, body, user):
    if user.role not in STAFF_ROLES:
        fail('access_denied', 'Access denied', status=403)
    if not user.tenant_id:
        fail('tenant_required', 'User must be associated with a tenant', status=400)
    tenant_id = user.tenant_id
    digest = request_hash(target_id, recommendation_id, body)
    await lock_tenant_financials(db, tenant_id)
    replay = await db.scalar(select(RecommendationConversion).where(
        RecommendationConversion.tenant_id == tenant_id, RecommendationConversion.request_id == body.request_id))
    if replay is not None:
        if replay.request_hash != digest:
            fail('idempotency_key_reused', 'This request was already used with different values. Refresh before adding work.')
        return await project(db, replay), True
    target = await db.scalar(scoped_order(target_id, tenant_id).with_for_update(of=RepairOrder).execution_options(populate_existing=True))
    if target is None:
        fail('target_not_found', 'Repair order not found', status=404)
    rec = await db.scalar(select(RecommendedService).where(
        RecommendedService.id == recommendation_id, RecommendedService.tenant_id == tenant_id,
        RecommendedService.deleted_at.is_(None)).with_for_update().execution_options(populate_existing=True))
    source = await db.scalar(scoped_order(rec.repair_order_id, tenant_id)) if rec else None
    if rec is None or source is None or source.status == RepairOrderStatus.CANCELLED:
        fail('recommendation_not_found', 'Recommendation not found', status=404)
    # A different target may have waited on the recommendation row. Recheck the
    # request and current conversion after obtaining the serialization boundary.
    replay = await db.scalar(select(RecommendationConversion).where(
        RecommendationConversion.tenant_id == tenant_id, RecommendationConversion.request_id == body.request_id))
    if replay is not None:
        if replay.request_hash != digest:
            fail('idempotency_key_reused', 'This request was already used with different values.')
        return await project(db, replay), True
    if target.vehicle_id != source.vehicle_id:
        fail('vehicle_mismatch', 'The recommendation belongs to a different truck.')
    existing = await current_conversion(db, tenant_id, recommendation_id)
    previous = await project(db, existing) if existing else None
    if existing is not None and previous.state == 'active':
        if (existing.target_order_id == target_id and existing.hours == body.hours
                and existing.hourly_rate == body.hourly_rate and body.replaces_conversion_id is None):
            return previous, True
        fail('already_converted', 'This recommendation already has an operation.', conversion=previous)
    if rec.is_resolved or rec.resolved_by_repair_order_id:
        fail('recommendation_resolved', 'This recommendation is already resolved.')
    if target.source == 'easy_truck_shop_import':
        fail('target_ets_managed', 'Imported ETS orders cannot receive converted work.')
    if not can_convert(target):
        fail('target_not_editable', 'This repair order no longer accepts work.')
    if existing is not None:
        if body.replaces_conversion_id is None:
            fail('replacement_confirmation_required', 'The previous operation is unavailable. Confirm adding it again.', conversion=previous)
        if body.replaces_conversion_id != existing.id or not previous.can_replace:
            fail('conversion_changed', 'The recommendation changed. Refresh before adding work.', conversion=previous)
    elif body.replaces_conversion_id is not None:
        fail('conversion_changed', 'The recommendation changed. Refresh before adding work.')
    tenant = await db.get(Tenant, tenant_id)
    if target.is_internal and body.hourly_rate != policy_rate(target, tenant):
        fail('pricing_changed', 'The work order labor rate changed. Refresh and review the new amount.')
    total = (body.hours * body.hourly_rate).quantize(Decimal('.01'))
    if total > Decimal('99999999.99'):
        fail('amount_too_large', 'The labor total exceeds the supported amount.', status=422)
    conversion_id, line_id = uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    if existing is not None:
        existing.superseded_at = now
        # Flush the partial unique index release before inserting its successor.
        await db.flush()
    line = Labor(execution_status="pending", id=line_id, tenant_id=tenant_id, repair_order_id=target.id,
                 description=rec.description, hours=body.hours, hourly_rate=body.hourly_rate,
                 total_cost=total, line_type=LaborLineType.MANUAL, auto_recalc_enabled=False)
    conversion = RecommendationConversion(
        id=conversion_id, tenant_id=tenant_id, recommendation_id=rec.id,
        source_order_id=source.id, source_order_number=source.order_number,
        source_description=rec.description, source_priority=rec.priority.value,
        vehicle_id=source.vehicle_id, target_order_id=target.id, target_order_number=target.order_number,
        target_labor_id=line_id, request_id=body.request_id, request_hash=digest,
        hours=body.hours, hourly_rate=body.hourly_rate, created_by_user_id=user.id, created_at=now)
    from app.services.operation_execution import enroll_new_scope
    enroll_new_scope(target)
    db.add_all([line, conversion])
    await db.flush()
    if existing is not None:
        existing.superseded_by_conversion_id = conversion_id
    db.add(RepairOrderHistoryEvent(
        tenant_id=tenant_id, repair_order_id=target.id, event_type='recommendation_converted',
        label='Recommended work added', detail=rec.description,
        entity_id=line_id, actor_user_id=user.id,
        actor_name=f'{user.first_name} {user.last_name}'.strip()))
    # Import lazily to reuse the canonical totals validation without an endpoint
    # import cycle. The endpoint owns the one transaction commit.
    from app.api.v1.endpoints.repair_orders import _refresh_repair_order_totals
    refreshed = await _refresh_repair_order_totals(db, target.id)
    if any(abs(Decimal(value or 0)) > Decimal('99999999.99') for value in
           (refreshed.total_labor_cost, refreshed.total_parts_cost, refreshed.total_cost)):
        fail('amount_too_large', 'The order total exceeds the supported amount.', status=422)
    await db.flush()
    return await project(db, conversion), False


async def guard_reactivation(db, order, user=None):
    rows = (await db.scalars(select(RecommendationConversion).join(Labor, and_(
        Labor.id == RecommendationConversion.target_labor_id,
        Labor.tenant_id == RecommendationConversion.tenant_id,
        Labor.repair_order_id == RecommendationConversion.target_order_id,
        Labor.deleted_at.is_(None))).where(
        RecommendationConversion.tenant_id == order.tenant_id,
        RecommendationConversion.target_order_id == order.id,
        RecommendationConversion.superseded_at.is_not(None)))).all()
    if rows:
        current = await current_conversion(db, order.tenant_id, rows[0].recommendation_id)
        fail('superseded_recommendation_work', 'This order contains recommended work that was moved to another operation. Use the current work record.',
             conversion=await project(db, current) if current and user and user.role in STAFF_ROLES else None)


async def guard_resolution(db, rec, changes, user):
    current = await current_conversion(db, rec.tenant_id, rec.id)
    if current is None:
        return
    resolution_fields = {'is_resolved', 'resolved_by_repair_order_id'} & changes.keys()
    if not resolution_fields:
        return
    # Existing source-assigned mechanic access does not grant visibility or
    # control over work created on another order through staff-only conversion.
    if user.role not in STAFF_ROLES:
        fail('access_denied', 'Staff must review resolution of linked recommended work.', status=403)
    if changes.get('is_resolved') is False:
        changes['resolved_by_repair_order_id'] = None
        return
    value = await project(db, current)
    resolved = changes.get('is_resolved', rec.is_resolved)
    resolved_by = changes.get('resolved_by_repair_order_id', rec.resolved_by_repair_order_id)
    if (not resolved or resolved_by != current.target_order_id or value.state != 'active'
            or value.target_order.status not in COMPLETED):
        fail('converted_work_not_completed', 'Resolve completed linked work with its order reference, or explicitly reopen the recommendation.', conversion=value)


async def guard_source_delete(db, rec):
    any_conversion = await db.scalar(select(RecommendationConversion.id).where(
        RecommendationConversion.tenant_id == rec.tenant_id, RecommendationConversion.recommendation_id == rec.id).limit(1))
    if any_conversion:
        fail('recommendation_has_conversion', 'This recommendation is linked to work and must be kept. Resolve it after the work is completed.')
