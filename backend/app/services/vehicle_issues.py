"""C3 metadata transactions: vehicle first, no order/financial side effects."""

from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import select, func, case, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.customer import Customer
from app.db.models.invoice import Invoice
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_issue import (
    VehicleIssue,
    VehicleIssueLink,
    VehicleIssueRequest,
    VehicleIssueEvent,
)
from app.services.recommended_work import _customer_link
from app.schemas.vehicle_issue import (
    Issue,
    IssueCapabilities,
    IssueLink,
    IssueOwner,
    IssueMutation,
    IssuePage,
)

STAFF = (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST)
MERGE_MESSAGE = (
    "Truck issue history is attached to one of these records. Merge is unavailable until "
    "issue-history migration is supported. Keep both records for now."
)


def fail(code, status=409):
    messages = {
        "access_denied": "Truck issues are available to shop staff only.",
        "tenant_required": "A shop context is required.",
        "issue_context_not_found": "Truck issue context was not found.",
        "issue_changed": "This issue changed. Refresh before trying again.",
        "issue_closed": "Reopen this issue before editing or linking it.",
        "invalid_state_transition": "This state change is not available.",
        "issue_already_linked": "End the current visit link before choosing another.",
        "link_changed": "This visit link changed. Refresh before trying again.",
        "target_not_linkable": "This visit cannot be linked to a truck issue.",
        "idempotency_key_reused": "This request identifier was already used for another action.",
    }
    raise HTTPException(
        status_code=status, detail={"code": code, "message": messages[code]}
    )


def authorize(user):
    if not user.is_active or user.deleted_at is not None or user.role not in STAFF:
        fail("access_denied", 403)
    if user.tenant_id is None:
        fail("tenant_required", 400)


async def vehicle_context(
    db, vehicle_id, user, *, customer_id=None, context_order_id=None, lock=False
):
    authorize(user)
    query = select(Vehicle).where(
        Vehicle.id == vehicle_id,
        Vehicle.tenant_id == user.tenant_id,
        Vehicle.deleted_at.is_(None),
    )
    if lock:
        query = query.with_for_update(of=Vehicle).execution_options(
            populate_existing=True
        )
    vehicle = await db.scalar(query)
    if vehicle is None or vehicle.deleted_at is not None:
        fail("issue_context_not_found", 404)
    if customer_id is not None:
        customer = await db.scalar(
            select(Customer.id).where(
                Customer.id == customer_id,
                Customer.tenant_id == user.tenant_id,
                Customer.deleted_at.is_(None),
            )
        )
        linked = await db.scalar(
            select(Vehicle.id).where(
                Vehicle.id == vehicle_id,
                Vehicle.tenant_id == user.tenant_id,
                _customer_link(user.tenant_id, customer_id, datetime.now(timezone.utc)),
            )
        )
        if customer is None or linked is None:
            fail("issue_context_not_found", 404)
    context = None
    if context_order_id is not None:
        context = await target_context(db, vehicle_id, context_order_id, user)
    return vehicle, context


async def target_context(db, vehicle_id, order_id, user):
    row = await db.scalar(
        select(RepairOrder).where(
            RepairOrder.id == order_id,
            RepairOrder.tenant_id == user.tenant_id,
            RepairOrder.vehicle_id == vehicle_id,
            RepairOrder.deleted_at.is_(None),
            RepairOrder.status != RepairOrderStatus.CANCELLED,
        )
    )
    if row is None:
        fail("issue_context_not_found", 404)
    return row


async def native_target(db, order):
    if order.source == "easy_truck_shop_import":
        return False
    veto = await db.scalar(
        select(Invoice.id)
        .where(
            Invoice.tenant_id == order.tenant_id,
            Invoice.repair_order_id == order.id,
            or_(
                Invoice.source == "easy_truck_shop_import",
                Invoice.accounting_policy == "historical_export_hold",
            ),
        )
        .limit(1)
    )
    return veto is None


async def load_issue(db, vehicle_id, issue_id, user, *, lock=False):
    query = select(VehicleIssue).where(
        VehicleIssue.id == issue_id,
        VehicleIssue.tenant_id == user.tenant_id,
        VehicleIssue.vehicle_id == vehicle_id,
        VehicleIssue.deleted_at.is_(None),
    )
    if lock:
        query = query.with_for_update(of=VehicleIssue).execution_options(
            populate_existing=True
        )
    issue = await db.scalar(query)
    if issue is None:
        fail("issue_context_not_found", 404)
    return issue


async def active_link(db, issue, *, lock=False):
    query = select(VehicleIssueLink).where(
        VehicleIssueLink.tenant_id == issue.tenant_id,
        VehicleIssueLink.issue_id == issue.id,
        VehicleIssueLink.ended_at.is_(None),
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return await db.scalar(query)


async def assignable_owner(db, owner_id, user):
    if owner_id is None:
        return
    valid = await db.scalar(
        select(User.id).where(
            User.id == owner_id,
            User.tenant_id == user.tenant_id,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
            User.role.in_(STAFF),
        )
    )
    if valid is None:
        fail("issue_context_not_found", 404)


async def shop_timezone(db, tenant_id):
    return await db.scalar(select(Tenant.timezone).where(Tenant.id == tenant_id))


def follow_up_state(issue, as_of, tz):
    if issue.state != "open":
        return "closed"
    if issue.follow_up_on is None:
        return "unscheduled"
    try:
        today = as_of.astimezone(ZoneInfo(tz)).date()
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        return "unknown"
    return (
        "overdue"
        if issue.follow_up_on < today
        else "today" if issue.follow_up_on == today else "upcoming"
    )


async def present(db, issue, *, as_of=None, tz=None, context=None):
    as_of = as_of or datetime.now(timezone.utc)
    if tz is None:
        tz = await shop_timezone(db, issue.tenant_id)
    owner = None
    if issue.responsible_user_id is not None:
        row = await db.scalar(
            select(User).where(
                User.id == issue.responsible_user_id, User.tenant_id == issue.tenant_id
            )
        )
        if row is not None:
            owner = IssueOwner(
                id=row.id,
                display_name=f"{row.first_name} {row.last_name}".strip(),
                active=row.is_active and row.deleted_at is None,
            )
    link = await active_link(db, issue)
    projection = None
    if link is not None:
        target = await db.scalar(
            select(RepairOrder).where(
                RepairOrder.id == link.target_order_id,
                RepairOrder.tenant_id == issue.tenant_id,
                RepairOrder.vehicle_id == issue.vehicle_id,
                RepairOrder.deleted_at.is_(None),
                RepairOrder.status != RepairOrderStatus.CANCELLED,
            )
        )
        projection = IssueLink(
            id=link.id,
            target_order_id=target.id if target else None,
            order_number=target.order_number if target else None,
            availability="available" if target else "unavailable",
            created_at=link.created_at,
        )
    can_link = (
        issue.state == "open"
        and link is None
        and context is not None
        and await native_target(db, context)
    )
    return Issue(
        id=issue.id,
        vehicle_id=issue.vehicle_id,
        description=issue.description,
        priority=issue.priority,
        state=issue.state,
        version=issue.version,
        responsible_user=owner,
        follow_up_on=issue.follow_up_on,
        follow_up_state=follow_up_state(issue, as_of, tz),
        created_at=issue.created_at,
        updated_at=issue.updated_at,
        state_changed_at=issue.state_changed_at,
        state_reason=issue.state_reason,
        current_link=projection,
        capabilities=IssueCapabilities(
            can_edit=issue.state == "open",
            can_change_state=True,
            can_link_context=can_link,
            can_end_link=link is not None,
        ),
    )


async def list_issues(
    db,
    vehicle_id,
    user,
    *,
    customer_id=None,
    context_order_id=None,
    state="open",
    skip=0,
    limit=25,
):
    _, context = await vehicle_context(
        db, vehicle_id, user, customer_id=customer_id, context_order_id=context_order_id
    )
    filters = [
        VehicleIssue.tenant_id == user.tenant_id,
        VehicleIssue.vehicle_id == vehicle_id,
        VehicleIssue.deleted_at.is_(None),
    ]
    if state != "all":
        filters.append(VehicleIssue.state == state)
    total = await db.scalar(
        select(func.count()).select_from(VehicleIssue).where(*filters)
    )
    rows = (
        await db.scalars(
            select(VehicleIssue)
            .where(*filters)
            .order_by(
                case(
                    (VehicleIssue.priority == "urgent", 0),
                    (VehicleIssue.priority == "soon", 1),
                    else_=2,
                ),
                VehicleIssue.follow_up_on.asc().nullslast(),
                VehicleIssue.created_at,
                VehicleIssue.id,
            )
            .offset(skip)
            .limit(limit)
        )
    ).all()
    as_of = datetime.now(timezone.utc)
    tz = await shop_timezone(db, user.tenant_id)
    items = [
        await present(db, row, as_of=as_of, tz=tz, context=context) for row in rows
    ]
    return IssuePage(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        has_more=skip + len(items) < total,
        as_of=as_of,
        timezone=tz,
    )


async def get_issue(
    db, vehicle_id, issue_id, user, *, customer_id=None, context_order_id=None
):
    _, context = await vehicle_context(
        db, vehicle_id, user, customer_id=customer_id, context_order_id=context_order_id
    )
    return await present(
        db, await load_issue(db, vehicle_id, issue_id, user), context=context
    )


async def list_owners(db, vehicle_id, user):
    await vehicle_context(db, vehicle_id, user)
    rows = (
        await db.scalars(
            select(User).where(
                User.tenant_id == user.tenant_id,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
                User.role.in_(STAFF),
            )
        )
    ).all()
    items = [
        {"id": row.id, "display_name": f"{row.first_name} {row.last_name}".strip()}
        for row in rows
    ]
    items.sort(key=lambda row: (row["display_name"], str(row["id"])))
    return {"items": items}


def fingerprint(vehicle_id, issue_id, link_id, body):
    payload = body.model_dump(mode="json", exclude_unset=True, exclude={"request_id"})
    # Create defaults are normalized: omission and explicitly choosing the default are identical.
    if issue_id is None:
        payload = body.model_dump(mode="json", exclude={"request_id"})
    payload.update(
        vehicle_id=str(vehicle_id),
        issue_id=str(issue_id) if issue_id else None,
        link_id=str(link_id) if link_id else None,
    )
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def receipt(db, user, body, operation, digest):
    row = await db.scalar(
        select(VehicleIssueRequest).where(
            VehicleIssueRequest.tenant_id == user.tenant_id,
            VehicleIssueRequest.request_id == body.request_id,
        )
    )
    if row and (
        row.actor_id != user.id
        or row.operation != operation
        or row.payload_hash != digest
    ):
        fail("idempotency_key_reused")
    return row


async def replay(db, row, vehicle_id, user):
    issue = await load_issue(db, vehicle_id, row.issue_id, user, lock=True)
    return IssueMutation(issue=await present(db, issue), replayed=True), False


async def mutate(
    db: AsyncSession,
    vehicle_id: UUID,
    user: User,
    body,
    *,
    operation,
    issue_id=None,
    link_id=None,
):
    # The vehicle lock is the common serialization boundary with truck merge.
    await vehicle_context(db, vehicle_id, user, lock=True)
    digest = fingerprint(vehicle_id, issue_id, link_id, body)
    prior = await receipt(db, user, body, operation, digest)
    if prior:
        return await replay(db, prior, vehicle_id, user)
    try:
        async with db.begin_nested():
            issue = (
                None
                if issue_id is None
                else await load_issue(db, vehicle_id, issue_id, user, lock=True)
            )
            # Recheck after locks; a replay never restores an earlier revision or link.
            prior = await receipt(db, user, body, operation, digest)
            if prior:
                return await replay(db, prior, vehicle_id, user)
            if issue is not None and issue.version != body.expected_version:
                fail("issue_changed")
            now = datetime.now(timezone.utc)
            changed = True
            created = False
            result_link = None
            changes = {}
            if operation == "create":
                await assignable_owner(db, body.responsible_user_id, user)
                issue = VehicleIssue(
                    tenant_id=user.tenant_id,
                    vehicle_id=vehicle_id,
                    created_by=user.id,
                    description=body.description,
                    priority=body.priority,
                    responsible_user_id=body.responsible_user_id,
                    follow_up_on=body.follow_up_on,
                    state="open",
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
                db.add(issue)
                await db.flush()
                created = True
                changes = body.model_dump(mode="json", exclude={"request_id"})
            elif operation == "edit":
                if issue.state != "open":
                    fail("issue_closed")
                values = body.model_dump(
                    exclude_unset=True, exclude={"request_id", "expected_version"}
                )
                if "responsible_user_id" in values:
                    await assignable_owner(db, values["responsible_user_id"], user)
                for field, value in values.items():
                    before = getattr(issue, field)
                    if before != value:
                        changes[field] = {
                            "before": str(before) if before is not None else None,
                            "after": str(value) if value is not None else None,
                        }
                        setattr(issue, field, value)
                changed = bool(changes)
            elif operation == "state":
                if (
                    issue.state == "open"
                    and body.state not in ("resolved", "dismissed")
                ) or (issue.state != "open" and body.state != "open"):
                    fail("invalid_state_transition")
                changes = {
                    "state": {"before": issue.state, "after": body.state},
                    "reason": body.reason,
                }
                issue.state = body.state
                issue.state_reason = body.reason
                issue.state_changed_at = now
                issue.state_changed_by = user.id
            elif operation == "link":
                if issue.state != "open":
                    fail("issue_closed")
                target = await target_context(
                    db, vehicle_id, body.target_order_id, user
                )
                if not await native_target(db, target):
                    fail("target_not_linkable")
                current = await active_link(db, issue, lock=True)
                if current is not None:
                    if current.target_order_id != target.id:
                        fail("issue_already_linked")
                    changed = False
                    result_link = current
                else:
                    result_link = VehicleIssueLink(
                        tenant_id=user.tenant_id,
                        vehicle_id=vehicle_id,
                        issue_id=issue.id,
                        target_order_id=target.id,
                        order_number=target.order_number,
                        created_by=user.id,
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(result_link)
                    await db.flush()
                    created = True
                    changes = {
                        "link_id": str(result_link.id),
                        "target_order_id": str(target.id),
                    }
            elif operation == "end_link":
                current = await active_link(db, issue, lock=True)
                if current is None or current.id != link_id:
                    fail("link_changed")
                current.ended_at = now
                current.ended_by = user.id
                current.end_reason = body.reason
                result_link = current
                changes = {"link_id": str(current.id), "reason": body.reason}
            else:
                raise ValueError("Unknown issue metadata operation")
            if changed:
                if operation != "create":
                    issue.version += 1
                    issue.updated_at = now
                db.add(
                    VehicleIssueEvent(
                        tenant_id=user.tenant_id,
                        issue_id=issue.id,
                        actor_id=user.id,
                        operation=operation,
                        version=issue.version,
                        changes=changes,
                        created_at=now,
                        updated_at=now,
                    )
                )
            db.add(
                VehicleIssueRequest(
                    tenant_id=user.tenant_id,
                    request_id=body.request_id,
                    actor_id=user.id,
                    operation=operation,
                    payload_hash=digest,
                    issue_id=issue.id,
                    link_id=result_link.id if result_link else None,
                    accepted_version=issue.version,
                    created_at=now,
                    updated_at=now,
                )
            )
            await db.flush()
        return IssueMutation(issue=await present(db, issue), replayed=False), created
    except IntegrityError:
        # A tenant request key may race across different vehicles. The savepoint
        # removes all losing metadata before reading the winning receipt.
        prior = await receipt(db, user, body, operation, digest)
        if prior:
            return await replay(db, prior, vehicle_id, user)
        fail("issue_changed")


async def guard_vehicle_merge(db, canonical, duplicate):
    found = await db.scalar(
        select(VehicleIssue.id)
        .where(
            VehicleIssue.tenant_id == canonical.tenant_id,
            VehicleIssue.vehicle_id.in_([canonical.id, duplicate.id]),
        )
        .limit(1)
    )
    if found is not None:
        from app.services.vehicle_merge import VehicleMergeError

        raise VehicleMergeError(MERGE_MESSAGE)
