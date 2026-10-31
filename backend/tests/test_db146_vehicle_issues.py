"""C3 metadata continuity, privacy, replay and compatibility boundaries."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest
import pytest_asyncio
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, func
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.db.models.vehicle_issue import (
    VehicleIssue,
    VehicleIssueEvent,
    VehicleIssueRequest,
    VehicleIssueLink,
)
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrderStatus
from app.db.models.vehicle_relationship import VehicleCustomerRelationship
from app.schemas import vehicle_issue as wire
from app.services import vehicle_issues as service
from app.services.vehicle_merge import merge_vehicles, VehicleMergeError
from tests.test_db099_recommended_work import customer, vehicle, order, actor, headers


@pytest_asyncio.fixture
async def issue_fixture(db_session):
    db = db_session
    tenant = Tenant(
        name="Fictional C3", slug=f"c3-{uuid4().hex}", timezone="America/New_York"
    )
    other = Tenant(name="Other C3", slug=f"c3-{uuid4().hex}")
    db.add_all([tenant, other])
    await db.flush()
    payer = await customer(db, tenant)
    truck = await vehicle(db, tenant, payer)
    twin = await vehicle(db, tenant, payer)
    owner = await actor(db, tenant, UserRole.GARAGE_OWNER)
    admin = await actor(db, tenant, UserRole.GARAGE_ADMIN)
    receptionist = await actor(db, tenant, UserRole.RECEPTIONIST)
    other_owner = await actor(db, other, UserRole.GARAGE_OWNER)
    foreign_payer = await customer(db, other)
    foreign_truck = await vehicle(db, other, foreign_payer)
    target = await order(db, tenant, payer, truck, status=RepairOrderStatus.IN_PROGRESS)
    await db.commit()
    return SimpleNamespace(
        db=db,
        tenant=tenant,
        other=other,
        payer=payer,
        truck=truck,
        twin=twin,
        owner=owner,
        admin=admin,
        receptionist=receptionist,
        other_owner=other_owner,
        foreign_truck=foreign_truck,
        target=target,
    )


async def create(a, **values):
    values.setdefault("description", "Inspect steering noise")
    return await service.mutate(
        a.db,
        a.truck.id,
        a.owner,
        wire.IssueCreate(request_id=uuid4(), **values),
        operation="create",
    )


async def count(a, model):
    return await a.db.scalar(
        select(func.count()).select_from(model).where(model.tenant_id == a.tenant.id)
    )


@pytest.mark.asyncio
async def test_create_replay_current_state_and_noop_edit(issue_fixture):
    a = issue_fixture
    body = wire.IssueCreate(
        request_id=uuid4(), description="  Inspect steering noise  "
    )
    result, created = await service.mutate(
        a.db, a.truck.id, a.owner, body, operation="create"
    )
    assert created and result.issue.description == "Inspect steering noise"
    identity = result.issue.id
    resolved, _ = await service.mutate(
        a.db,
        a.truck.id,
        a.owner,
        wire.IssueStateChange(
            request_id=uuid4(),
            expected_version=1,
            state="resolved",
            reason="Owner reviewed",
        ),
        operation="state",
        issue_id=identity,
    )
    assert resolved.issue.state == "resolved" and resolved.issue.version == 2
    replayed, _ = await service.mutate(
        a.db, a.truck.id, a.owner, body, operation="create"
    )
    assert (
        replayed.replayed
        and replayed.issue.version == 2
        and replayed.issue.state == "resolved"
    )
    assert await count(a, VehicleIssue) == 1 and await count(a, VehicleIssueEvent) == 2
    with pytest.raises(HTTPException) as error:
        await service.mutate(
            a.db,
            a.truck.id,
            a.owner,
            wire.IssueEdit(request_id=uuid4(), expected_version=2, priority="urgent"),
            operation="edit",
            issue_id=identity,
        )
    assert error.value.detail["code"] == "issue_closed"
    reopened, _ = await service.mutate(
        a.db,
        a.truck.id,
        a.owner,
        wire.IssueStateChange(
            request_id=uuid4(), expected_version=2, state="open", reason="Still present"
        ),
        operation="state",
        issue_id=identity,
    )
    noop, _ = await service.mutate(
        a.db,
        a.truck.id,
        a.owner,
        wire.IssueEdit(
            request_id=uuid4(),
            expected_version=3,
            description=reopened.issue.description,
        ),
        operation="edit",
        issue_id=identity,
    )
    assert noop.issue.version == 3 and await count(a, VehicleIssueEvent) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["payload", "actor", "operation", "vehicle"])
async def test_request_reuse_rejected(issue_fixture, mismatch):
    a = issue_fixture
    key = uuid4()
    body = wire.IssueCreate(request_id=key, description="Inspect leak")
    first, _ = await service.mutate(a.db, a.truck.id, a.owner, body, operation="create")
    kwargs = dict(operation="create")
    if mismatch == "payload":
        body = wire.IssueCreate(request_id=key, description="Other issue")
    if mismatch == "operation":
        body = wire.IssueEdit(
            request_id=key, expected_version=1, description="Inspect leak"
        )
        kwargs = dict(operation="edit", issue_id=first.issue.id)
    with pytest.raises(HTTPException) as error:
        await service.mutate(
            a.db,
            a.twin.id if mismatch == "vehicle" else a.truck.id,
            a.admin if mismatch == "actor" else a.owner,
            body,
            **kwargs,
        )
    assert (
        error.value.detail["code"] == "idempotency_key_reused"
        and await count(a, VehicleIssue) == 1
    )


@pytest.mark.asyncio
async def test_edits_owner_date_and_sort_page(issue_fixture):
    a = issue_fixture
    first, _ = await create(a, priority="monitor")
    second, _ = await create(a, priority="urgent", follow_up_on=date(2026, 1, 1))
    third, _ = await create(a, priority="urgent", follow_up_on=date(2025, 1, 1))
    page = await service.list_issues(a.db, a.truck.id, a.owner, limit=1)
    assert page.total == 3 and page.has_more and page.items[0].id == third.issue.id
    page2 = await service.list_issues(a.db, a.truck.id, a.owner, skip=1, limit=2)
    assert [i.id for i in page2.items] == [
        second.issue.id,
        first.issue.id,
    ] and not page2.has_more
    body = wire.IssueEdit(
        request_id=uuid4(),
        expected_version=1,
        responsible_user_id=a.receptionist.id,
        follow_up_on=date.today(),
    )
    edited, _ = await service.mutate(
        a.db, a.truck.id, a.owner, body, operation="edit", issue_id=first.issue.id
    )
    assert edited.issue.responsible_user.id == a.receptionist.id
    clear, _ = await service.mutate(
        a.db,
        a.truck.id,
        a.owner,
        wire.IssueEdit(request_id=uuid4(), expected_version=2, follow_up_on=None),
        operation="edit",
        issue_id=first.issue.id,
    )
    assert (
        clear.issue.follow_up_on is None
        and clear.issue.responsible_user.id == a.receptionist.id
    )
    with pytest.raises(HTTPException) as error:
        await service.mutate(
            a.db,
            a.truck.id,
            a.owner,
            wire.IssueEdit(request_id=uuid4(), expected_version=1, priority="urgent"),
            operation="edit",
            issue_id=first.issue.id,
        )
    assert error.value.detail["code"] == "issue_changed"


@pytest.mark.asyncio
async def test_link_end_and_replay_do_not_restore_link(issue_fixture):
    a = issue_fixture
    first, _ = await create(a)
    key = wire.IssueLinkCreate(
        request_id=uuid4(), expected_version=1, target_order_id=a.target.id
    )
    linked, created = await service.mutate(
        a.db, a.truck.id, a.owner, key, operation="link", issue_id=first.issue.id
    )
    assert (
        created
        and linked.issue.version == 2
        and linked.issue.current_link.target_order_id == a.target.id
    )
    duplicate, created = await service.mutate(
        a.db,
        a.truck.id,
        a.owner,
        wire.IssueLinkCreate(
            request_id=uuid4(), expected_version=2, target_order_id=a.target.id
        ),
        operation="link",
        issue_id=first.issue.id,
    )
    assert (
        not created
        and duplicate.issue.version == 2
        and await count(a, VehicleIssueEvent) == 2
    )
    await service.mutate(
        a.db,
        a.truck.id,
        a.owner,
        wire.IssueStateChange(
            request_id=uuid4(),
            expected_version=2,
            state="dismissed",
            reason="Not pursuing",
        ),
        operation="state",
        issue_id=first.issue.id,
    )
    ended, _ = await service.mutate(
        a.db,
        a.truck.id,
        a.owner,
        wire.IssueReason(request_id=uuid4(), expected_version=3, reason="Wrong visit"),
        operation="end_link",
        issue_id=first.issue.id,
        link_id=linked.issue.current_link.id,
    )
    assert (
        ended.issue.state == "dismissed"
        and ended.issue.current_link is None
        and ended.issue.version == 4
    )
    replayed, _ = await service.mutate(
        a.db, a.truck.id, a.owner, key, operation="link", issue_id=first.issue.id
    )
    assert (
        replayed.replayed
        and replayed.issue.current_link is None
        and replayed.issue.state == "dismissed"
    )
    assert await count(a, VehicleIssueLink) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["order", "invoice", "historical"])
async def test_ets_ownership_veto_including_deleted_invoice(issue_fixture, source):
    a = issue_fixture
    first, _ = await create(a)
    if source == "order":
        a.target.source = "easy_truck_shop_import"
    else:
        a.db.add(
            Invoice(
                tenant_id=a.tenant.id,
                repair_order_id=a.target.id,
                invoice_number=f"FICTION-{uuid4()}",
                status=InvoiceStatus.CANCELLED,
                subtotal=0,
                total_amount=0,
                source="easy_truck_shop_import" if source == "invoice" else None,
                accounting_policy=(
                    "historical_export_hold" if source == "historical" else "standard"
                ),
                deleted_at=datetime.now(timezone.utc),
            )
        )
    await a.db.flush()
    viewed = await service.get_issue(
        a.db, a.truck.id, first.issue.id, a.owner, context_order_id=a.target.id
    )
    assert not viewed.capabilities.can_link_context
    with pytest.raises(HTTPException) as error:
        await service.mutate(
            a.db,
            a.truck.id,
            a.owner,
            wire.IssueLinkCreate(
                request_id=uuid4(), expected_version=1, target_order_id=a.target.id
            ),
            operation="link",
            issue_id=first.issue.id,
        )
    assert (
        error.value.detail["code"] == "target_not_linkable"
        and await count(a, VehicleIssueLink) == 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [RepairOrderStatus.COMPLETED, RepairOrderStatus.INVOICED, RepairOrderStatus.PAID],
)
async def test_completed_native_visit_reference_does_not_resolve(issue_fixture, status):
    a = issue_fixture
    a.target.status = status
    await a.db.flush()
    first, _ = await create(a)
    linked, _ = await service.mutate(
        a.db,
        a.truck.id,
        a.owner,
        wire.IssueLinkCreate(
            request_id=uuid4(), expected_version=1, target_order_id=a.target.id
        ),
        operation="link",
        issue_id=first.issue.id,
    )
    assert linked.issue.state == "open" and a.target.status == status


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["cancelled", "deleted", "foreign", "wrong_truck"])
async def test_unavailable_current_link_redacts_target(issue_fixture, invalid):
    a = issue_fixture
    first, _ = await create(a)
    await service.mutate(
        a.db,
        a.truck.id,
        a.owner,
        wire.IssueLinkCreate(
            request_id=uuid4(), expected_version=1, target_order_id=a.target.id
        ),
        operation="link",
        issue_id=first.issue.id,
    )
    if invalid == "cancelled":
        a.target.status = RepairOrderStatus.CANCELLED
    if invalid == "deleted":
        a.target.deleted_at = datetime.now(timezone.utc)
    if invalid == "foreign":
        a.target.tenant_id = a.other.id
    if invalid == "wrong_truck":
        a.target.vehicle_id = a.twin.id
    await a.db.flush()
    result = await service.get_issue(a.db, a.truck.id, first.issue.id, a.owner)
    assert (
        result.current_link.availability == "unavailable"
        and result.current_link.target_order_id is None
        and result.current_link.order_number is None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [
        UserRole.SUPER_ADMIN,
        UserRole.MECHANIC,
        UserRole.CUSTOMER,
        UserRole.FLEET_MANAGER,
        UserRole.DRIVER,
    ],
)
async def test_role_denied_before_entity_disclosure(issue_fixture, role):
    a = issue_fixture
    user = await actor(a.db, a.tenant, role)
    with pytest.raises(HTTPException) as error:
        await service.list_issues(a.db, uuid4(), user)
    assert (
        error.value.status_code == 403 and error.value.detail["code"] == "access_denied"
    )


@pytest.mark.asyncio
async def test_tenant_owner_context_negatives_and_inactive_history(issue_fixture):
    a = issue_fixture
    for truck, user in [(a.foreign_truck, a.owner), (a.truck, a.other_owner)]:
        with pytest.raises(HTTPException) as error:
            await service.list_issues(a.db, truck.id, user)
        assert error.value.status_code == 404
    for owner_id in [a.other_owner.id, uuid4()]:
        with pytest.raises(HTTPException) as error:
            await create(a, responsible_user_id=owner_id)
        assert error.value.status_code == 404
    first, _ = await create(a, responsible_user_id=a.admin.id)
    a.admin.is_active = False
    await a.db.flush()
    read = await service.get_issue(a.db, a.truck.id, first.issue.id, a.owner)
    assert read.responsible_user.active is False
    owners = await service.list_owners(a.db, a.truck.id, a.owner)
    assert a.admin.id not in [row["id"] for row in owners["items"]] and all(
        set(row) == {"id", "display_name"} for row in owners["items"]
    )
    with pytest.raises(HTTPException):
        await create(a, responsible_user_id=a.admin.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "relationship", ["owner", "operator", "default_payer", "ended", "future"]
)
async def test_customer_current_relationship_boundary(issue_fixture, relationship):
    a = issue_fixture
    linked = await customer(a.db, a.tenant)
    now = datetime.now(timezone.utc)
    a.db.add(
        VehicleCustomerRelationship(
            tenant_id=a.tenant.id,
            vehicle_id=a.truck.id,
            customer_id=linked.id,
            relationship_type=(
                "owner" if relationship in ("ended", "future") else relationship
            ),
            effective_from=(
                now + timedelta(days=1)
                if relationship == "future"
                else now - timedelta(days=1)
            ),
            effective_to=now if relationship == "ended" else None,
        )
    )
    await a.db.flush()
    if relationship in ("owner", "operator"):
        await service.list_issues(a.db, a.truck.id, a.owner, customer_id=linked.id)
    else:
        with pytest.raises(HTTPException) as error:
            await service.list_issues(a.db, a.truck.id, a.owner, customer_id=linked.id)
        assert error.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["open", "resolved", "dismissed", "deleted"])
@pytest.mark.parametrize("side", ["canonical", "duplicate"])
async def test_all_issue_history_blocks_merge(issue_fixture, state, side):
    a = issue_fixture
    target = a.truck if side == "canonical" else a.twin
    result, _ = await service.mutate(
        a.db,
        target.id,
        a.owner,
        wire.IssueCreate(request_id=uuid4(), description="History"),
        operation="create",
    )
    issue = await a.db.get(VehicleIssue, result.issue.id)
    if state == "deleted":
        issue.deleted_at = datetime.now(timezone.utc)
    else:
        issue.state = state
    await a.db.flush()
    with pytest.raises(VehicleMergeError, match="Truck issue history"):
        await merge_vehicles(
            a.db,
            tenant_id=a.tenant.id,
            canonical_id=a.truck.id,
            duplicate_id=a.twin.id,
            merged_by_user_id=a.owner.id,
            confirm_vin=a.truck.vin,
        )
    assert a.truck.deleted_at is None and a.twin.deleted_at is None


@pytest.mark.parametrize(
    "tz,expected",
    [
        ("America/New_York", "overdue"),
        ("Pacific/Honolulu", "today"),
        ("Missing/Zone", "unknown"),
        (None, "unknown"),
    ],
)
def test_followup_shop_calendar_and_unknown(tz, expected):
    row = SimpleNamespace(state="open", follow_up_on=date(2026, 10, 29))
    assert (
        service.follow_up_state(row, datetime(2026, 10, 30, 5, tzinfo=timezone.utc), tz)
        == expected
    )
    row.state = "resolved"
    assert service.follow_up_state(row, datetime.now(timezone.utc), tz) == "closed"
    row.state = "open"
    row.follow_up_on = None
    assert service.follow_up_state(row, datetime.now(timezone.utc), tz) == "unscheduled"


@pytest.mark.parametrize(
    "patch",
    [
        {"money": 12},
        {"description": " "},
        {"description": None},
        {"priority": None},
        {"follow_up_on": "2026-10-30T00:00:00Z"},
        {"expected_version": True},
    ],
)
def test_strict_edit_validation(patch):
    with pytest.raises(ValidationError):
        wire.IssueEdit.model_validate(
            {"request_id": str(uuid4()), "expected_version": 1, **patch}
        )


@pytest.mark.asyncio
async def test_http_error_shape_cache_and_no_old_recommendation_write(
    issue_fixture, client
):
    a = issue_fixture
    path = f"/api/v1/vehicles/{a.truck.id}/issues"
    response = await client.post(
        path,
        headers=headers(a.owner),
        json={"request_id": str(uuid4()), "description": "Check leak", "total": 100},
    )
    assert (
        response.status_code == 422
        and response.json()["detail"]["code"] == "validation_error"
    )
    response = await client.post(
        path,
        headers=headers(a.owner),
        json={"request_id": str(uuid4()), "description": "Check leak"},
    )
    assert (
        response.status_code == 201 and "no-store" in response.headers["cache-control"]
    )
    assert response.json()["issue"]["capabilities"]["can_link_context"] is False
    response = await client.get(path, headers=headers(a.owner))
    assert response.status_code == 200 and response.json()["total"] == 1
    from app.db.models.recommended_service import RecommendedService
    from app.db.models.labor import Labor

    assert await count(a, RecommendedService) == 0 and await count(a, Labor) == 0


@pytest.mark.asyncio
async def test_conflict_reasons_context_and_role_edges(issue_fixture):
    a = issue_fixture
    first, _ = await create(a)
    identity = first.issue.id
    with pytest.raises(HTTPException) as error:
        await service.mutate(
            a.db,
            a.truck.id,
            a.owner,
            wire.IssueStateChange(
                request_id=uuid4(), expected_version=1, state="open", reason="same"
            ),
            operation="state",
            issue_id=identity,
        )
    assert error.value.detail["code"] == "invalid_state_transition"
    linked, _ = await service.mutate(
        a.db,
        a.truck.id,
        a.owner,
        wire.IssueLinkCreate(
            request_id=uuid4(), expected_version=1, target_order_id=a.target.id
        ),
        operation="link",
        issue_id=identity,
    )
    other = await order(a.db, a.tenant, a.payer, a.truck)
    with pytest.raises(HTTPException) as error:
        await service.mutate(
            a.db,
            a.truck.id,
            a.owner,
            wire.IssueLinkCreate(
                request_id=uuid4(), expected_version=2, target_order_id=other.id
            ),
            operation="link",
            issue_id=identity,
        )
    assert error.value.detail["code"] == "issue_already_linked"
    with pytest.raises(HTTPException) as error:
        await service.mutate(
            a.db,
            a.truck.id,
            a.owner,
            wire.IssueReason(
                request_id=uuid4(), expected_version=2, reason="wrong link"
            ),
            operation="end_link",
            issue_id=identity,
            link_id=uuid4(),
        )
    assert error.value.detail["code"] == "link_changed"
    with pytest.raises(HTTPException) as error:
        await service.get_issue(a.db, a.twin.id, identity, a.owner)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        await service.list_issues(
            a.db, a.twin.id, a.owner, context_order_id=a.target.id
        )
    assert error.value.status_code == 404
    no_tenant = await actor(a.db, None, UserRole.GARAGE_ADMIN)
    with pytest.raises(HTTPException) as error:
        await service.list_issues(a.db, uuid4(), no_tenant)
    assert error.value.detail["code"] == "tenant_required"
    inactive = await actor(a.db, a.tenant, UserRole.RECEPTIONIST)
    inactive.is_active = False
    with pytest.raises(HTTPException) as error:
        await service.list_issues(a.db, a.truck.id, inactive)
    assert error.value.detail["code"] == "access_denied"
    a.target.source = "easy_truck_shop_import"
    a.target.deleted_at = datetime.now(timezone.utc)
    await a.db.flush()
    with pytest.raises(HTTPException) as error:
        await service.list_issues(
            a.db, a.truck.id, a.owner, context_order_id=a.target.id
        )
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_imported_truck_native_issue_and_closed_page_filter(issue_fixture):
    a = issue_fixture
    a.truck.source = "easy_truck_shop_import"
    await a.db.flush()
    first, _ = await create(a)
    await create(a)
    await service.mutate(
        a.db,
        a.truck.id,
        a.owner,
        wire.IssueStateChange(
            request_id=uuid4(),
            expected_version=1,
            state="resolved",
            reason="Staff reviewed",
        ),
        operation="state",
        issue_id=first.issue.id,
    )
    open_page = await service.list_issues(a.db, a.truck.id, a.owner)
    closed_page = await service.list_issues(a.db, a.truck.id, a.owner, state="resolved")
    all_page = await service.list_issues(a.db, a.truck.id, a.owner, state="all")
    assert open_page.total == 1 and closed_page.total == 1 and all_page.total == 2
    assert closed_page.items[0].follow_up_state == "closed"


@pytest.mark.asyncio
async def test_more_than_one_default_page_counts_and_stable_order(
    issue_fixture, client
):
    a = issue_fixture
    instant = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
    priorities = ("monitor", "urgent", "soon")
    rows = []
    for index in range(31):
        row = VehicleIssue(
            tenant_id=a.tenant.id,
            vehicle_id=a.truck.id,
            description=f"Fictional pagination issue {index}",
            priority=priorities[index % 3],
            follow_up_on=None if index % 4 == 0 else date(2026, 11, index % 3 + 1),
            state="open",
            created_by=a.owner.id,
            version=1,
            created_at=instant,
            updated_at=instant,
        )
        a.db.add(row)
        rows.append(row)
    a.db.add_all(
        [
            VehicleIssue(
                tenant_id=a.tenant.id,
                vehicle_id=a.truck.id,
                description="Closed fixture",
                priority="urgent",
                state="resolved",
                created_by=a.owner.id,
                version=1,
                created_at=instant,
                updated_at=instant,
            ),
            VehicleIssue(
                tenant_id=a.other.id,
                vehicle_id=a.foreign_truck.id,
                description="Foreign fixture",
                priority="urgent",
                state="open",
                created_by=a.other_owner.id,
                version=1,
                created_at=instant,
                updated_at=instant,
            ),
        ]
    )
    await a.db.commit()
    rank = {"urgent": 0, "soon": 1, "monitor": 2}
    expected = [
        str(row.id)
        for row in sorted(
            rows,
            key=lambda row: (
                rank[row.priority],
                row.follow_up_on or date.max,
                str(row.id),
            ),
        )
    ]
    path = f"/api/v1/vehicles/{a.truck.id}/issues"
    first = await client.get(path, headers=headers(a.owner))
    second = await client.get(path, headers=headers(a.owner), params={"skip": 25})
    repeated = await client.get(path, headers=headers(a.owner))
    closed = await client.get(
        path, headers=headers(a.owner), params={"state": "resolved"}
    )
    assert (
        first.status_code
        == second.status_code
        == repeated.status_code
        == closed.status_code
        == 200
    )
    first, second, repeated, closed = (
        response.json() for response in (first, second, repeated, closed)
    )
    assert first["total"] == second["total"] == 31
    assert len(first["items"]) == 25 and first["has_more"] is True
    assert len(second["items"]) == 6 and second["has_more"] is False
    ids = [item["id"] for item in first["items"] + second["items"]]
    assert ids == expected and len(set(ids)) == 31
    assert [item["id"] for item in repeated["items"]] == expected[:25]
    assert closed["total"] == 1 and closed["has_more"] is False
    assert closed["items"][0]["description"] == "Closed fixture"


@pytest.mark.asyncio
async def test_http_merge_preview_and_post_match_guard_and_keep_role_boundary(
    issue_fixture, client
):
    from app.db.models.vehicle_merge import VehicleMergeRecord
    from app.db.models.vehicle import Vehicle

    a = issue_fixture
    preview = f"/api/v1/vehicles/{a.truck.id}/merge-preview/{a.twin.id}"
    merge = f"/api/v1/vehicles/{a.truck.id}/merge"
    payload = {"duplicate_vehicle_id": str(a.twin.id), "confirm_vin": a.truck.vin}
    clean = await client.get(preview, headers=headers(a.owner))
    assert clean.status_code == 200
    await create(a)
    await a.db.commit()
    for user in (a.owner, a.admin):
        before = await client.get(preview, headers=headers(user))
        applied = await client.post(merge, headers=headers(user), json=payload)
        assert before.status_code == applied.status_code == 409
        assert (
            before.json()["detail"] == applied.json()["detail"] == service.MERGE_MESSAGE
        )
    denied_preview = await client.get(preview, headers=headers(a.receptionist))
    denied_merge = await client.post(
        merge, headers=headers(a.receptionist), json=payload
    )
    assert denied_preview.status_code == denied_merge.status_code == 403
    assert service.MERGE_MESSAGE not in denied_preview.text + denied_merge.text
    assert await count(a, VehicleMergeRecord) == 0
    trucks = (
        await a.db.scalars(
            select(Vehicle)
            .where(Vehicle.id.in_([a.truck.id, a.twin.id]))
            .execution_options(populate_existing=True)
        )
    ).all()
    assert len(trucks) == 2 and all(truck.deleted_at is None for truck in trucks)


@pytest.mark.parametrize(
    "instant, due, expected",
    [
        (datetime(2026, 3, 8, 6, 59, tzinfo=timezone.utc), date(2026, 3, 8), "today"),
        (datetime(2026, 3, 8, 7, 0, tzinfo=timezone.utc), date(2026, 3, 8), "today"),
        (datetime(2026, 3, 9, 4, 0, tzinfo=timezone.utc), date(2026, 3, 8), "overdue"),
        (datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc), date(2026, 11, 1), "today"),
        (datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc), date(2026, 11, 1), "today"),
        (
            datetime(2026, 11, 2, 5, 0, tzinfo=timezone.utc),
            date(2026, 11, 1),
            "overdue",
        ),
    ],
)
def test_follow_up_dst_uses_shop_calendar_not_elapsed_hours(instant, due, expected):
    row = SimpleNamespace(state="open", follow_up_on=due)
    assert service.follow_up_state(row, instant, "America/New_York") == expected
