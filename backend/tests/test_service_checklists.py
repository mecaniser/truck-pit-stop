"""DB102 lifecycle, isolation, completion-side-effect and compatibility proofs."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.api.v1.endpoints import fleet, repair_orders, services
from app.db.models.customer import Customer
from app.db.models.labor import Labor
from app.db.models.repair_order import RepairOrder
from app.db.models.repair_order import RepairOrderStatus as Status
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.db.models.service import Service
from app.db.models.service_checklist import RepairOrderChecklistItem as Task
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.schemas.repair_order import LaborCreate, LaborUpdate, RepairOrderUpdate
from app.schemas.service_checklist import ChecklistTaskUpdate, ChecklistTemplateUpdate
from app.services import service_checklist as checks
from app.services.price_build_service import PriceBuildService
from fastapi import HTTPException, Response
from pydantic import ValidationError
from sqlalchemy import select


async def seed(db):
    tenant = Tenant(
        id=uuid4(),
        name="Checklist QA",
        slug=f"checklist-{uuid4().hex}",
        labor_rate=Decimal(100),
    )
    owner = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email=f"{uuid4().hex}@example.invalid",
        hashed_password="unused",
        first_name="Casey",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
    )
    customer = Customer(
        id=uuid4(),
        tenant_id=tenant.id,
        first_name="Synthetic",
        last_name="Account",
        email=f"{uuid4().hex}@example.invalid",
    )
    vehicle = Vehicle(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        make="Synthetic",
        model="Truck",
        year=2020,
    )
    order = RepairOrder(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        order_number=f"QA-{uuid4().hex[:12]}",
        status=Status.IN_PROGRESS,
        assigned_mechanic_id=owner.id,
    )
    service = Service(
        id=uuid4(),
        tenant_id=tenant.id,
        name="QA oil service",
        duration_minutes=60,
        checklist_version=1,
        checklist_template=[
            {"id": str(uuid4()), "label": "Secure plug", "required": True},
            {"id": str(uuid4()), "label": "Check leaks", "required": True},
            {"id": str(uuid4()), "label": "Record brand", "required": False},
        ],
    )
    db.add(tenant)
    await db.flush()
    db.add_all([owner, customer])
    await db.flush()
    db.add_all([vehicle, service])
    await db.flush()
    db.add(order)
    await db.commit()
    return SimpleNamespace(
        tenant=tenant,
        owner=owner,
        customer=customer,
        vehicle=vehicle,
        order=order,
        service=service,
    )


async def apply(db, data):
    builder = PriceBuildService()
    order = await builder.load_order(db, data.order.id, tenant_id=data.tenant.id)
    await builder.add_flat_service_line(db, order, data.service.id, actor=data.owner)
    await db.commit()
    return await checks.read_checklist(db, data.order.id, data.owner)


@pytest.mark.asyncio
async def test_template_version_ids_reorder_remove_noop_and_isolation(db_session):
    a = await seed(db_session)
    b = await seed(db_session)
    initial = checks.template_response(a.service)
    body = ChecklistTemplateUpdate(
        expected_version=1,
        items=[
            initial.items[2].model_dump(),
            initial.items[0].model_dump(),
            {"label": "  New check  "},
        ],
    )
    changed = await services.put_service_checklist(
        a.service.id, body, db_session, a.owner
    )
    assert (
        changed.version == 2
        and changed.items[0].id == initial.items[2].id
        and changed.items[2].label == "New check"
    )
    assert (
        await services.put_service_checklist(
            a.service.id,
            ChecklistTemplateUpdate(
                expected_version=2, items=[x.model_dump() for x in changed.items]
            ),
            db_session,
            a.owner,
        )
    ).version == 2
    for data, code in [
        (body, 409),
        (
            ChecklistTemplateUpdate(
                expected_version=2, items=[{"id": uuid4(), "label": "foreign"}]
            ),
            422,
        ),
    ]:
        with pytest.raises(HTTPException) as exc:
            await services.put_service_checklist(
                a.service.id, data, db_session, a.owner
            )
        assert exc.value.status_code == code
    with pytest.raises(HTTPException) as exc:
        await services.get_service_checklist(b.service.id, db_session, a.owner)
    assert exc.value.status_code == 404
    cleared = await services.put_service_checklist(
        a.service.id,
        ChecklistTemplateUpdate(expected_version=2, items=[]),
        db_session,
        a.owner,
    )
    assert cleared.version == 3 and cleared.items == []


@pytest.mark.parametrize(
    "body",
    [
        {"expected_version": -1, "items": []},
        {"expected_version": True, "items": []},
        {"expected_version": 0, "items": [{"label": " "}]},
        {"expected_version": 0, "items": [{"label": "x" * 301}]},
        {"expected_version": 0, "items": [{"label": "x"}] * 51},
        {"expected_version": 0, "items": [{"label": "x", "required": "false"}]},
        {"expected_version": 0, "items": [{"label": 5}]},
        {"expected_version": 0, "items": [], "tenant_id": "spoof"},
    ],
)
def test_template_validation(body):
    with pytest.raises(ValidationError):
        ChecklistTemplateUpdate(**body)


def test_valid_limits_and_duplicate_ids():
    assert (
        len(
            ChecklistTemplateUpdate(
                expected_version=0, items=[{"label": "x" * 300}] * 50
            ).items
        )
        == 50
    )
    duplicate = uuid4()
    with pytest.raises(ValidationError):
        ChecklistTemplateUpdate(
            expected_version=0,
            items=[{"id": duplicate, "label": "a"}, {"id": duplicate, "label": "b"}],
        )
    for body in [
        {"is_completed": True, "expected_version": 1, "completed_by": "spoof"},
        {"is_completed": 1, "expected_version": 1},
        {"is_completed": True, "expected_version": 0},
    ]:
        with pytest.raises(ValidationError):
            ChecklistTaskUpdate(**body)


@pytest.mark.asyncio
async def test_snapshot_immutable_reapply_and_independent_jobs(db_session):
    a = await seed(db_session)
    page = await apply(db_session, a)
    first = page.items[0]
    checked = await checks.update_task(
        db_session,
        a.order.id,
        first.id,
        a.owner,
        ChecklistTaskUpdate(is_completed=True, expected_version=1),
    )
    await db_session.commit()
    await services.put_service_checklist(
        a.service.id,
        ChecklistTemplateUpdate(expected_version=1, items=[{"label": "Replacement"}]),
        db_session,
        a.owner,
    )
    await apply(db_session, a)
    repeated = await checks.read_checklist(db_session, a.order.id, a.owner)
    assert [(x.id, x.label, x.is_completed) for x in repeated.items] == [
        (x.id, x.label, x.id == first.id) for x in page.items
    ]
    a.service.is_active = False
    await db_session.commit()
    assert (
        await checks.read_checklist(db_session, a.order.id, a.owner)
    ).summary.total == 3
    assert checked.completed_by.name == "Casey Owner"
    a.service.is_active = True
    second = RepairOrder(
        id=uuid4(),
        tenant_id=a.tenant.id,
        customer_id=a.customer.id,
        vehicle_id=a.vehicle.id,
        order_number=f"QA-{uuid4().hex}",
        status=Status.IN_PROGRESS,
    )
    db_session.add(second)
    await db_session.commit()
    a.order = second
    assert [x.label for x in (await apply(db_session, a)).items] == ["Replacement"]


@pytest.mark.asyncio
@pytest.mark.parametrize("historical", [True, False])
async def test_empty_or_historical_application_never_retrofits(db_session, historical):
    a = await seed(db_session)
    if historical:
        db_session.add(
            Labor(
                id=uuid4(),
                tenant_id=a.tenant.id,
                repair_order_id=a.order.id,
                description="Old line",
                source_service_id=a.service.id,
                hours=1,
                hourly_rate=100,
                total_cost=100,
            )
        )
        await db_session.commit()
    else:
        a.service.checklist_template = []
        await db_session.commit()
        await apply(db_session, a)
        a.service.checklist_template = [
            {"id": str(uuid4()), "label": "New definition", "required": True}
        ]
        await db_session.commit()
    assert (await apply(db_session, a)).total == 0


@pytest.mark.asyncio
async def test_assignment_actor_version_noop_reopen_history(db_session):
    a = await seed(db_session)
    page = await apply(db_session, a)
    task = page.items[0]
    a.owner.role = UserRole.MECHANIC
    await db_session.commit()
    changed = await checks.update_task(
        db_session,
        a.order.id,
        task.id,
        a.owner,
        ChecklistTaskUpdate(is_completed=True, expected_version=1),
    )
    await db_session.commit()
    assert changed.version == 2 and changed.completed_by.id == a.owner.id
    repeated = await checks.update_task(
        db_session,
        a.order.id,
        task.id,
        a.owner,
        ChecklistTaskUpdate(is_completed=True, expected_version=2),
    )
    assert repeated.completed_at == changed.completed_at
    with pytest.raises(HTTPException) as exc:
        await checks.update_task(
            db_session,
            a.order.id,
            task.id,
            a.owner,
            ChecklistTaskUpdate(is_completed=False, expected_version=1),
        )
    assert exc.value.status_code == 409
    reopened = await checks.update_task(
        db_session,
        a.order.id,
        task.id,
        a.owner,
        ChecklistTaskUpdate(is_completed=False, expected_version=2),
    )
    await db_session.commit()
    assert (
        reopened.version == 3
        and reopened.completed_by is None
        and reopened.completed_at is None
    )
    events = (
        (
            await db_session.execute(
                select(RepairOrderHistoryEvent).where(
                    RepairOrderHistoryEvent.entity_id == task.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 3 and any(
        "Casey Owner" in x.detail
        for x in events
        if x.event_type == "checklist_reopened"
    )
    a.order.assigned_mechanic_id = None
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await checks.read_checklist(db_session, a.order.id, a.owner)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role", [UserRole.CUSTOMER, UserRole.DRIVER, UserRole.SUPER_ADMIN]
)
async def test_disallowed_roles_read_write_and_template(db_session, role):
    a = await seed(db_session)
    page = await apply(db_session, a)
    a.owner.role = role
    await db_session.commit()
    for call in [
        checks.read_checklist(db_session, a.order.id, a.owner),
        checks.update_task(
            db_session,
            a.order.id,
            page.items[0].id,
            a.owner,
            ChecklistTaskUpdate(is_completed=True, expected_version=1),
        ),
        checks.load_template(db_session, a.service.id, a.owner),
    ]:
        with pytest.raises(HTTPException) as exc:
            await call
        assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    [
        Status.DRAFT,
        Status.QUOTED,
        Status.APPROVED,
        Status.ASSIGNED,
        Status.ACKNOWLEDGED,
        Status.COMPLETED,
        Status.INVOICED,
        Status.PAID,
        Status.CANCELLED,
    ],
)
async def test_frozen_states(db_session, state):
    a = await seed(db_session)
    page = await apply(db_session, a)
    a.order.status = state
    await db_session.commit()
    assert not (await checks.read_checklist(db_session, a.order.id, a.owner)).can_update
    with pytest.raises(HTTPException) as exc:
        await checks.update_task(
            db_session,
            a.order.id,
            page.items[0].id,
            a.owner,
            ChecklistTaskUpdate(is_completed=True, expected_version=1),
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_pricing_lock_deleted_foreign_and_corrupt_joins(db_session):
    a = await seed(db_session)
    b = await seed(db_session)
    page = await apply(db_session, a)
    a.order.pricing_locked_at = datetime.now(UTC)
    a.order.pricing_lock_reason = "invoice"
    await db_session.commit()
    assert not (await checks.read_checklist(db_session, a.order.id, a.owner)).can_update
    with pytest.raises(HTTPException) as exc:
        await checks.read_checklist(db_session, b.order.id, a.owner)
    assert exc.value.status_code == 404
    a.order.pricing_locked_at = None
    await db_session.commit()
    task = await db_session.get(Task, page.items[0].id)
    line = await db_session.get(Labor, task.labor_id)
    for attr, value in [
        ("tenant_id", b.tenant.id),
        ("repair_order_id", b.order.id),
        ("deleted_at", datetime.now(UTC)),
    ]:
        old = getattr(line, attr)
        setattr(line, attr, value)
        await db_session.commit()
        assert (await checks.read_checklist(db_session, a.order.id, a.owner)).total == 0
        with pytest.raises(HTTPException) as exc:
            await checks.update_task(
                db_session,
                a.order.id,
                task.id,
                a.owner,
                ChecklistTaskUpdate(is_completed=True, expected_version=1),
            )
        assert exc.value.status_code == 404
        setattr(line, attr, old)
        await db_session.commit()
    a.order.deleted_at = datetime.now(UTC)
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await checks.read_checklist(db_session, a.order.id, a.owner)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route",
    [
        "mechanic",
        "admin",
        "approve",
        "fleet",
        "pending_review",
        "completed",
        "invoiced",
        "paid",
    ],
)
async def test_all_completion_routes_block_before_side_effects(
    db_session, monkeypatch, route
):
    a = await seed(db_session)
    await apply(db_session, a)
    if route == "mechanic":
        a.owner.role = UserRole.MECHANIC
    if route == "admin":
        a.order.assigned_mechanic_id = None
    if route == "approve":
        a.order.status = Status.PENDING_REVIEW
    await db_session.commit()
    calls = []

    async def forbidden(*args, **kwargs):
        calls.append(1)
        raise AssertionError("side effect before checklist gate")

    monkeypatch.setattr(repair_orders, "broadcast_repair_order_update", forbidden)
    monkeypatch.setattr(repair_orders, "stop_active_session", forbidden)
    monkeypatch.setattr(repair_orders, "send_email", forbidden)
    monkeypatch.setattr(repair_orders, "send_sms", forbidden)
    monkeypatch.setattr(repair_orders, "_refresh_repair_order_totals", forbidden)
    monkeypatch.setattr(fleet, "_load_fleet_ro_or_404", AsyncMock(return_value=a.order))
    if route == "mechanic":
        action = repair_orders.complete_work(a.order.id, db_session, a.owner)
    elif route == "admin":
        action = repair_orders.admin_complete_unassigned_work(
            a.order.id, db_session, a.owner
        )
    elif route == "approve":
        action = repair_orders.approve_completion(
            a.order.id, db=db_session, current_user=a.owner
        )
    elif route == "fleet":
        action = fleet.complete_work_order(
            a.order.id, db=db_session, current_user=a.owner
        )
    else:
        action = repair_orders.update_repair_order(
            a.order.id, RepairOrderUpdate(status=Status(route)), db_session, a.owner
        )
    original = a.order.status
    with pytest.raises(HTTPException) as exc:
        await action
    assert (
        exc.value.status_code == 409
        and "2 required checklist tasks" in exc.value.detail
    )
    assert (
        a.order.status == original and a.order.work_completed_at is None and calls == []
    )


@pytest.mark.asyncio
async def test_optional_does_not_gate_and_paging_is_full_scope(db_session):
    a = await seed(db_session)
    await apply(db_session, a)
    tasks = (await db_session.execute(select(Task))).scalars().all()
    for task in tasks:
        if task.required:
            await checks.update_task(
                db_session,
                a.order.id,
                task.id,
                a.owner,
                ChecklistTaskUpdate(is_completed=True, expected_version=1),
            )
    from app.services import operation_execution
    from app.schemas.operation_execution import OperationCompletion
    for line in (await db_session.execute(select(Labor).where(Labor.repair_order_id == a.order.id))).scalars():
        if line.execution_status == 'pending':
            await operation_execution.complete(db_session, a.order.id, line.id, a.owner, OperationCompletion(is_completed=True, expected_version=line.execution_version))
    await checks.guard_completion(db_session, a.order)
    for _ in range(35):
        line = Labor(
            id=uuid4(),
            tenant_id=a.tenant.id,
            repair_order_id=a.order.id,
            description="Independent",
            hours=1,
            hourly_rate=100,
            total_cost=100,
        )
        db_session.add(line)
        await checks.snapshot_service(db_session, a.order, line, a.service, a.owner)
    page = await checks.read_checklist(db_session, a.order.id, a.owner, 100, 100)
    assert (
        len(page.items) == 8
        and page.total == 108
        and page.summary.required_remaining == 70
    )
    with pytest.raises(HTTPException):
        await checks.guard_completion(db_session, a.order)


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [True, False])
async def test_line_removal_archives_readd_and_source_edit(db_session, legacy):
    a = await seed(db_session)
    page = await apply(db_session, a)
    line_id = page.items[0].labor_id
    with pytest.raises(HTTPException) as exc:
        await repair_orders.update_repair_order_labor(
            a.order.id,
            line_id,
            LaborUpdate(source_service_id=None),
            db_session,
            a.owner,
        )
    assert exc.value.status_code == 409
    if legacy:
        await repair_orders.remove_labor_from_repair_order(
            a.order.id, line_id, db_session, a.owner
        )
    else:
        await PriceBuildService().remove_line(
            db_session, a.order, line_id=line_id, actor=a.owner
        )
        await db_session.commit()
    assert (await checks.read_checklist(db_session, a.order.id, a.owner)).total == 0
    old = (await db_session.execute(select(Task))).scalars().all()
    assert len(old) == 3 and all(x.removed_at and x.labor_id is None for x in old)
    new = await apply(db_session, a)
    assert {x.id for x in new.items}.isdisjoint({x.id for x in page.items})
    assert not any(x.is_completed for x in new.items)


@pytest.mark.asyncio
async def test_legacy_and_operation_service_application(db_session):
    a = await seed(db_session)
    line = await repair_orders.add_labor_to_repair_order(
        a.order.id,
        LaborCreate(
            description="Service",
            hours=1,
            hourly_rate=100,
            source_service_id=a.service.id,
        ),
        db_session,
        a.owner,
    )
    assert (await checks.read_checklist(db_session, a.order.id, a.owner)).items[
        0
    ].labor_id == line.id
    await repair_orders.remove_labor_from_repair_order(
        a.order.id, line.id, db_session, a.owner
    )
    builder = PriceBuildService()
    order = await builder.load_order(db_session, a.order.id)
    await builder.add_repair_operation_line(
        db_session, order, operation_id=f"service:{a.service.id}", actor=a.owner
    )
    await db_session.commit()
    assert (await checks.read_checklist(db_session, a.order.id, a.owner)).total == 3


@pytest.mark.asyncio
async def test_pm_reseed_preserves_removes_and_rejects_ambiguous(db_session):
    a = await seed(db_session)
    a.order.status = Status.DRAFT
    await db_session.commit()
    loaded = await fleet._load_pm_services(db_session, a.tenant.id, [a.service.id])
    await fleet._apply_pm_services_to_ro(
        db_session, a.tenant.id, a.order, loaded, actor=a.owner
    )
    await db_session.commit()
    first = await checks.read_checklist(db_session, a.order.id, a.owner)
    a.service.checklist_template = [
        {"id": str(uuid4()), "label": "Changed later", "required": True}
    ]
    await db_session.commit()
    await fleet._apply_pm_services_to_ro(
        db_session, a.tenant.id, a.order, loaded, actor=a.owner
    )
    await db_session.commit()
    second = await checks.read_checklist(db_session, a.order.id, a.owner)
    assert [x.id for x in first.items] == [x.id for x in second.items] and first.items[
        0
    ].labor_id == second.items[0].labor_id
    duplicate = Labor(
        id=uuid4(),
        tenant_id=a.tenant.id,
        repair_order_id=a.order.id,
        source_service_id=a.service.id,
        description="dup",
        hours=1,
        hourly_rate=100,
        total_cost=100,
    )
    db_session.add(duplicate)
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await fleet._apply_pm_services_to_ro(
            db_session, a.tenant.id, a.order, loaded, actor=a.owner
        )
    assert exc.value.status_code == 409
    assert [
        x.id
        for x in (await checks.read_checklist(db_session, a.order.id, a.owner)).items
    ] == [x.id for x in second.items]
    await db_session.delete(duplicate)
    await db_session.commit()
    await fleet._apply_pm_services_to_ro(
        db_session, a.tenant.id, a.order, [], actor=a.owner
    )
    await db_session.commit()
    assert (await checks.read_checklist(db_session, a.order.id, a.owner)).total == 0
    assert all(
        task.removed_at
        for task in (await db_session.execute(select(Task))).scalars().all()
    )


@pytest.mark.asyncio
async def test_staff_scope_template_permissions_and_missing_tenant(db_session):
    a = await seed(db_session)
    await apply(db_session, a)
    for role in [UserRole.RECEPTIONIST, UserRole.MECHANIC, UserRole.FLEET_MANAGER]:
        a.owner.role = role
        await db_session.commit()
        assert (
            await checks.load_template(db_session, a.service.id, a.owner)
        ).id == a.service.id
        with pytest.raises(HTTPException) as exc:
            await checks.save_template(
                db_session,
                a.service.id,
                a.owner,
                ChecklistTemplateUpdate(expected_version=1, items=[]),
            )
        assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        await checks.read_checklist(db_session, a.order.id, a.owner)
    assert exc.value.status_code == 403
    a.order.is_fleet_work = True
    await db_session.commit()
    assert (await checks.read_checklist(db_session, a.order.id, a.owner)).total == 3
    a.owner.tenant_id = None
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await checks.read_checklist(db_session, a.order.id, a.owner)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_internal_history_hidden_from_customer_and_cache_header(db_session):
    a = await seed(db_session)
    await apply(db_session, a)
    for event_type in checks.INTERNAL_EVENT_TYPES:
        db_session.add(
            RepairOrderHistoryEvent(
                tenant_id=a.tenant.id,
                repair_order_id=a.order.id,
                event_type=event_type,
                label="Internal task",
                detail="Private instruction",
                actor_name="Internal staff",
            )
        )
    db_session.add(
        RepairOrderHistoryEvent(
            tenant_id=a.tenant.id,
            repair_order_id=a.order.id,
            event_type="work_added",
            label="Public work",
            detail="Service",
        )
    )
    await db_session.commit()
    staff = await repair_orders.get_repair_order_detail(a.order.id, db_session, a.owner)
    assert any(
        x.event_type in checks.INTERNAL_EVENT_TYPES for x in staff.history_events
    )
    a.owner.role = UserRole.CUSTOMER
    a.owner.customer_id = a.customer.id
    await db_session.commit()
    customer = await repair_orders.get_repair_order_detail(
        a.order.id, db_session, a.owner
    )
    assert customer.history_events and not any(
        x.event_type in checks.INTERNAL_EVENT_TYPES for x in customer.history_events
    )
    a.owner.role = UserRole.GARAGE_OWNER
    await db_session.commit()
    response = Response()
    await repair_orders.get_order_checklist(
        a.order.id, response, 0, 100, db_session, a.owner
    )
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_cancel_soft_delete_restore_and_reopen_preserve_evidence(
    db_session, monkeypatch
):
    a = await seed(db_session)
    page = await apply(db_session, a)
    item = page.items[0]
    await checks.update_task(
        db_session,
        a.order.id,
        item.id,
        a.owner,
        ChecklistTaskUpdate(is_completed=True, expected_version=1),
    )
    await db_session.commit()
    monkeypatch.setattr(repair_orders, "broadcast_repair_order_update", AsyncMock())
    await repair_orders.update_repair_order(
        a.order.id, RepairOrderUpdate(status=Status.CANCELLED), db_session, a.owner
    )
    assert not (await checks.read_checklist(db_session, a.order.id, a.owner)).can_update
    await repair_orders.delete_repair_order(a.order.id, db_session, a.owner)
    await repair_orders.restore_repair_order(a.order.id, db_session, a.owner)
    retained = await checks.read_checklist(db_session, a.order.id, a.owner)
    assert (
        retained.items[0].id == item.id
        and retained.items[0].is_completed
        and retained.items[0].version == 2
    )
    a.order.is_internal = True
    a.order.status = Status.COMPLETED
    await db_session.commit()
    await repair_orders.reopen_repair_order(a.order.id, db_session, a.owner)
    retained = await checks.read_checklist(db_session, a.order.id, a.owner)
    assert (
        retained.can_update
        and retained.items[0].is_completed
        and retained.items[0].version == 2
    )


@pytest.mark.asyncio
async def test_pm_empty_prior_snapshot_retained_and_new_service_gets_tasks(db_session):
    a = await seed(db_session)
    a.order.status = Status.DRAFT
    original = a.service.checklist_template
    a.service.checklist_template = []
    await db_session.commit()
    loaded = await fleet._load_pm_services(db_session, a.tenant.id, [a.service.id])
    await fleet._apply_pm_services_to_ro(
        db_session, a.tenant.id, a.order, loaded, actor=a.owner
    )
    await db_session.commit()
    a.service.checklist_template = original
    other = Service(
        id=uuid4(),
        tenant_id=a.tenant.id,
        name="Second",
        duration_minutes=60,
        checklist_template=[
            {"id": str(uuid4()), "label": "New work", "required": True}
        ],
        checklist_version=1,
    )
    db_session.add(other)
    await db_session.commit()
    loaded = await fleet._load_pm_services(
        db_session, a.tenant.id, [a.service.id, other.id]
    )
    await fleet._apply_pm_services_to_ro(
        db_session, a.tenant.id, a.order, loaded, actor=a.owner
    )
    await db_session.commit()
    page = await checks.read_checklist(db_session, a.order.id, a.owner)
    assert page.total == 1 and page.items[0].service_name == "Second"
    await fleet._apply_pm_services_to_ro(
        db_session, a.tenant.id, a.order, loaded, actor=a.owner
    )
    await db_session.commit()
    assert (await checks.read_checklist(db_session, a.order.id, a.owner)).items[
        0
    ].id == page.items[0].id


@pytest.mark.asyncio
async def test_legacy_fleet_add_service_snapshots(db_session, monkeypatch):
    from app.schemas.fleet import AddServiceRequest

    a = await seed(db_session)
    a.order.is_internal = True
    await db_session.commit()
    monkeypatch.setattr(fleet, "_load_fleet_ro_or_404", AsyncMock(return_value=a.order))
    await fleet.add_service_to_work_order(
        a.order.id, AddServiceRequest(service_id=a.service.id), db=db_session, current_user=a.owner
    )
    assert (await checks.read_checklist(db_session, a.order.id, a.owner)).total == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["mechanic", "admin", "approve", "fleet"])
async def test_completion_paths_accept_finished_required_tasks(
    db_session, monkeypatch, route
):
    a = await seed(db_session)
    page = await apply(db_session, a)
    for item in page.items:
        if item.required:
            await checks.update_task(
                db_session,
                a.order.id,
                item.id,
                a.owner,
                ChecklistTaskUpdate(is_completed=True, expected_version=1),
            )
    from app.services import operation_execution
    from app.schemas.operation_execution import OperationCompletion
    await operation_execution.complete(db_session, a.order.id, page.items[0].labor_id, a.owner, OperationCompletion(is_completed=True, expected_version=0))
    a.customer.phone = None
    if route == "mechanic":
        a.owner.role = UserRole.MECHANIC
    if route == "admin":
        a.order.assigned_mechanic_id = None
    if route == "approve":
        a.order.status = Status.PENDING_REVIEW
    await db_session.commit()
    monkeypatch.setattr(repair_orders, "send_email", AsyncMock())
    monkeypatch.setattr(repair_orders, "send_sms", AsyncMock())
    monkeypatch.setattr(repair_orders, "broadcast_repair_order_update", AsyncMock())
    monkeypatch.setattr(fleet, "_load_fleet_ro_or_404", AsyncMock(return_value=a.order))
    if route == "mechanic":
        await repair_orders.complete_work(a.order.id, db_session, a.owner)
    elif route == "admin":
        await repair_orders.admin_complete_unassigned_work(
            a.order.id, db_session, a.owner
        )
    elif route == "approve":
        await repair_orders.approve_completion(
            a.order.id,
            body=None,
            idempotency_key=None,
            db=db_session,
            current_user=a.owner,
        )
    else:
        await fleet.complete_work_order(
            a.order.id, body=None, db=db_session, current_user=a.owner
        )
    await db_session.refresh(a.order)
    assert a.order.status in (
        {Status.PENDING_REVIEW}
        if route in {"mechanic", "admin"}
        else {Status.COMPLETED, Status.INVOICED}
    )
    result = await checks.read_checklist(db_session, a.order.id, a.owner)
    assert result.summary.required_remaining == 0 and result.summary.completed == 2
