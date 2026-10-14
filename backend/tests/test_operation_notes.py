"""DB118 operation identity, replay, staff privacy and lifecycle acceptance."""
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError
from sqlalchemy import select, func

from app.api.v1.endpoints import repair_orders as routes, customers, invoices, quotes
from app.db.models.invoice import Invoice
from app.db.models.labor import LaborLineType
from app.db.models.mechanic_time import MechanicTimeSession
from app.db.models.quote import Quote
from app.db.models.repair_order import RepairOrder, RepairOrderStatus as Status
from app.db.models.repair_order_history import RepairOrderHistoryEvent as Event
from app.db.models.user import UserRole
from app.schemas.operation_notes import OperationNoteCreate as Create
from app.services import operation_notes as notes, operation_execution as ops
from test_operation_execution import seed, assert_error


def body(text="Air leak confirmed.\nRecheck fitting.", **kwargs):
    return Create(id=kwargs.pop('id', uuid4()), body=text, **kwargs)


@pytest.mark.parametrize('payload', [
    {}, {'id': 'not-uuid', 'body': 'note'}, {'id': str(uuid4()), 'body': None},
    {'id': str(uuid4()), 'body': 123}, {'id': str(uuid4()), 'body': ' \n '},
    {'id': str(uuid4()), 'body': 'x' * 4001},
    *[{'id': str(uuid4()), 'body': 'note', key: 'spoof'}
      for key in ['tenant_id', 'actor_user_id', 'created_at', 'audience', 'labor_id']],
])
def test_validation_rejects_bad_or_server_owned_fields(payload):
    with pytest.raises(ValidationError):
        Create.model_validate(payload)


def test_trimmed_length_boundary_and_internal_whitespace():
    assert body('  ' + 'x' * 4000 + '\n').body == 'x' * 4000
    assert body('  one\n  two  ').body == 'one\n  two'


@pytest.mark.asyncio
@pytest.mark.parametrize('line_type', [LaborLineType.MANUAL, LaborLineType.FLAT_SERVICE, LaborLineType.REPAIR_OPERATION, LaborLineType.SUBLET])
async def test_round_trip_exact_operation_actor_text_and_ordering(db_session, line_type):
    a = await seed(db_session)
    line = a.lines[0]
    line.line_type = line_type
    line.description = 'Operation snapshot ' + 'x' * 300
    await db_session.commit()
    request = body('  <script>literal text</script>\n  inspect  ')
    first, created = await notes.append(db_session, a.order.id, line.id, a.owner, request)
    assert created and first.id == request.id and first.labor_id == line.id
    assert first.body == '<script>literal text</script>\n  inspect'
    assert first.actor_name == 'Casey Owner' and first.actor_user_id == a.owner.id
    assert first.created_at.tzinfo is not None
    second, _ = await notes.append(db_session, a.order.id, line.id, a.owner, body())
    event = await db_session.get(Event, first.id)
    assert event.label.startswith('Shop note · Operation snapshot') and len(event.label) == 255
    event.created_at = datetime.now(UTC) - timedelta(days=1)
    await db_session.commit()
    result = await notes.page(db_session, a.order.id, line.id, a.owner)
    assert [note.id for note in result.items] == [first.id, second.id]
    assert result.can_add and result.read_only_reason is None
    assert (await notes.page(db_session, a.order.id, a.lines[1].id, a.owner)).items == []


@pytest.mark.asyncio
async def test_same_key_replay_original_author_distinct_keys_and_collision_scopes(db_session):
    a, other = await seed(db_session), await seed(db_session)
    request = body()
    first, _ = await notes.append(db_session, a.order.id, a.lines[0].id, a.owner, request)
    await db_session.commit()
    a.owner.first_name = 'Renamed'
    replay, created = await notes.append(db_session, a.order.id, a.lines[0].id, a.owner, request)
    assert not created and replay == first and replay.actor_name == 'Casey Owner'
    distinct, created = await notes.append(db_session, a.order.id, a.lines[0].id, a.owner, body(request.body))
    assert created and distinct.id != first.id
    for order, line, actor, attempt in [
        (a.order, a.lines[0], a.owner, body('Changed', id=request.id)),
        (a.order, a.lines[1], a.owner, request),
        (a.order, a.lines[0], a.lead, request),
        (other.order, other.lines[0], other.owner, request),
    ]:
        await assert_error(409, notes.append(db_session, order.id, line.id, actor, attempt), notes.COLLISION_REASON)
    first_event = await db_session.get(Event, first.id)
    first_event.deleted_at = datetime.now(UTC)
    await db_session.flush()
    await assert_error(409, notes.append(db_session, a.order.id, a.lines[0].id, a.owner, request))
    first_event.deleted_at = None
    first_event.event_type = 'note_shop'
    await db_session.flush()
    await assert_error(409, notes.append(db_session, a.order.id, a.lines[0].id, a.owner, request))
    assert await db_session.scalar(select(func.count(Event.id))) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('role', [UserRole.CUSTOMER, UserRole.FLEET_MANAGER, UserRole.DRIVER, UserRole.SUPER_ADMIN])
async def test_denied_roles_api_and_full_history_never_disclose_note(db_session, role):
    a = await seed(db_session)
    note, _ = await notes.append(db_session, a.order.id, a.lines[0].id, a.owner, body('CONFIDENTIAL OPERATION NOTE'))
    a.order.is_fleet_work = True
    a.order.status = Status.INVOICED
    await db_session.commit()
    denied = SimpleNamespace(role=role, id=uuid4(), tenant_id=a.tenant.id, customer_id=a.customer.id)
    await assert_error(403, notes.page(db_session, a.order.id, a.lines[0].id, denied))
    await assert_error(403, notes.append(db_session, a.order.id, a.lines[0].id, denied, body()))
    detail = await routes.get_repair_order_detail(a.order.id, db_session, denied)
    serialized = detail.model_dump_json()
    assert note.body not in serialized and str(note.id) not in serialized
    assert 'operation_note_shop' not in serialized and detail.history_events == []


@pytest.mark.asyncio
async def test_foreign_tenant_foreign_order_deleted_and_missing_targets(db_session):
    a, b = await seed(db_session), await seed(db_session)
    request = body()
    await notes.append(db_session, a.order.id, a.lines[0].id, a.owner, request)
    for order_id, line_id in [(b.order.id, b.lines[0].id), (a.order.id, b.lines[0].id), (uuid4(), a.lines[0].id), (a.order.id, uuid4())]:
        for call in [notes.page(db_session, order_id, line_id, a.owner), notes.append(db_session, order_id, line_id, a.owner, body())]:
            await assert_error(404, call)
    other_order = RepairOrder(tenant_id=a.tenant.id, customer_id=a.customer.id, vehicle_id=a.vehicle.id,
        order_number=f'OTHER-{uuid4()}', status=Status.IN_PROGRESS)
    db_session.add(other_order); await db_session.flush()
    a.lines[1].repair_order_id = other_order.id
    await db_session.flush()
    await assert_error(404, notes.page(db_session, a.order.id, a.lines[1].id, a.owner))
    await assert_error(404, notes.append(db_session, a.order.id, a.lines[1].id, a.owner, body()))
    no_tenant = SimpleNamespace(role=UserRole.GARAGE_OWNER, tenant_id=None)
    await assert_error(400, notes.page(db_session, a.order.id, a.lines[0].id, no_tenant))
    # Replaying never bypasses removed/deleted-target guards.
    a.lines[0].deleted_at = datetime.now(UTC)
    await db_session.flush()
    await assert_error(404, notes.append(db_session, a.order.id, a.lines[0].id, a.owner, request))
    await assert_error(404, notes.page(db_session, a.order.id, a.lines[0].id, a.owner))
    a.lines[0].deleted_at = None
    a.order.deleted_at = datetime.now(UTC)
    await db_session.flush()
    await assert_error(404, notes.append(db_session, a.order.id, a.lines[0].id, a.owner, request))
    await assert_error(404, notes.page(db_session, a.order.id, a.lines[0].id, a.owner))


@pytest.mark.asyncio
async def test_mechanic_lead_helper_scope_and_reassignment_recheck(db_session):
    a = await seed(db_session)
    request = body()
    await notes.append(db_session, a.order.id, a.lines[1].id, a.helper, request)
    lead_read = await notes.page(db_session, a.order.id, a.lines[1].id, a.lead)
    assert len(lead_read.items) == 1 and not lead_read.can_add
    assert lead_read.read_only_reason == notes.ASSIGNMENT_REASON
    await assert_error(403, notes.append(db_session, a.order.id, a.lines[1].id, a.lead, body()))
    await assert_error(403, notes.page(db_session, a.order.id, a.lines[0].id, a.helper))
    assert (await notes.page(db_session, a.order.id, a.lines[0].id, a.lead)).can_add
    a.lines[1].mechanic_id = a.lead.id
    await db_session.flush()
    await assert_error(403, notes.page(db_session, a.order.id, a.lines[1].id, a.helper))
    await assert_error(403, notes.append(db_session, a.order.id, a.lines[1].id, a.helper, request))
    a.lines[1].line_type = LaborLineType.SUBLET
    await db_session.flush()
    await assert_error(403, notes.page(db_session, a.order.id, a.lines[1].id, a.lead))
    await assert_error(403, notes.append(db_session, a.order.id, a.lines[1].id, a.lead, body()))


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['completed', 'invoiced', 'paid', 'cancelled', 'pricing_lock'])
async def test_finalized_read_only_but_exact_authorized_replay(db_session, state):
    a = await seed(db_session)
    request = body()
    original, _ = await notes.append(db_session, a.order.id, a.lines[0].id, a.owner, request)
    if state == 'pricing_lock':
        a.order.pricing_locked_at = datetime.now(UTC)
        a.order.pricing_lock_reason = 'invoice_created'
    else:
        a.order.status = Status(state)
    await db_session.flush()
    page = await notes.page(db_session, a.order.id, a.lines[0].id, a.owner)
    assert not page.can_add and page.read_only_reason == notes.FROZEN_REASON
    replay, created = await notes.append(db_session, a.order.id, a.lines[0].id, a.owner, request)
    assert not created and replay == original
    await assert_error(409, notes.append(db_session, a.order.id, a.lines[0].id, a.owner, body()))


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['held', 'completed_operation', 'pending_review', 'quote_sent'])
async def test_note_does_not_mutate_timer_execution_order_or_prices(db_session, state):
    a = await seed(db_session)
    line = a.lines[0]
    if state == 'held':
        a.order.hold_reason = 'Parts'
    elif state == 'completed_operation':
        line.execution_status = 'completed'
        line.completed_at = datetime.now(UTC)
        line.completed_by_user_id = a.lead.id
        line.completed_by_name = 'Lead Technician'
    elif state == 'pending_review':
        a.order.status = Status.PENDING_REVIEW
        a.order.work_completed_at = datetime.now(UTC)
        a.order.actual_tracked_minutes = 34
        a.order.total_hold_minutes = 12
    else:
        a.order.pricing_locked_at = datetime.now(UTC)
        a.order.pricing_lock_reason = 'quote_sent'
    timer = MechanicTimeSession(tenant_id=a.tenant.id, mechanic_id=a.lead.id, repair_order_id=a.order.id,
        labor_id=line.id, labor_id_snapshot=line.id, session_type='repair_order', started_at=datetime.now(UTC), started_by_user_id=a.lead.id)
    db_session.add(timer)
    await db_session.commit()
    await db_session.refresh(a.order); await db_session.refresh(line)
    fields = ['status','hold_reason','assigned_mechanic_id','total_cost','total_parts_cost','total_labor_cost',
              'work_completed_at','actual_tracked_minutes','total_hold_minutes','updated_at']
    line_fields = ['hours','hourly_rate','total_cost','mechanic_id','execution_status','execution_version','completed_at','completed_by_user_id']
    before = [getattr(a.order, key) for key in fields], [getattr(line, key) for key in line_fields]
    await notes.append(db_session, a.order.id, line.id, a.lead, body())
    await db_session.commit()
    await db_session.refresh(a.order); await db_session.refresh(line); await db_session.refresh(timer)
    after = [getattr(a.order, key) for key in fields], [getattr(line, key) for key in line_fields]
    assert after == before and timer.ended_at is None
    assert await db_session.scalar(select(func.count(MechanicTimeSession.id))) == 1


@pytest.mark.asyncio
async def test_staff_history_retained_after_removal_and_mechanic_history_active_only(db_session):
    a = await seed(db_session)
    first, _ = await notes.append(db_session, a.order.id, a.lines[0].id, a.owner, body('Removed operation note'))
    second, _ = await notes.append(db_session, a.order.id, a.lines[1].id, a.owner, body('Active operation note'))
    a.legacy.line_type = LaborLineType.SUBLET
    await db_session.flush()
    sublet, _ = await notes.append(db_session, a.order.id, a.legacy.id, a.owner, body('Sublet private note'))
    await db_session.delete(a.lines[0]); await db_session.commit()
    staff = await routes.get_repair_order_detail(a.order.id, db_session, a.owner)
    lead = await routes.get_repair_order_detail(a.order.id, db_session, a.lead)
    assert {event.id for event in staff.history_events} == {first.id, second.id, sublet.id}
    assert {event.id for event in lead.history_events} == {second.id}
    assert staff.history_events[0].label.startswith('Shop note · Operation')
    all_events = (await db_session.scalars(select(Event))).all()
    helper_events = await notes.visible_history(db_session, a.order, a.helper, all_events)
    assert [event.id for event in helper_events] == [second.id]
    await assert_error(404, notes.page(db_session, a.order.id, first.labor_id, a.owner))
    # Existing order-note deletion cannot erase this append-only audit.
    await assert_error(404, routes.delete_repair_order_note(a.order.id, second.id, db_session, a.owner))
    assert await routes.list_repair_order_notes(a.order.id, db_session, a.owner) == []


@pytest.mark.asyncio
async def test_note_excluded_from_customer_authorization_invoice_quote_projections(db_session):
    a = await seed(db_session)
    marker = 'DB118 PRIVATE FINDING'
    await notes.append(db_session, a.order.id, a.lines[0].id, a.owner, body(marker))
    quote = Quote(id=uuid4(), tenant_id=a.tenant.id, repair_order_id=a.order.id, quote_number=f'Q-{uuid4()}', total_amount=100)
    invoice = Invoice(id=uuid4(), tenant_id=a.tenant.id, repair_order_id=a.order.id, invoice_number=f'I-{uuid4()}', subtotal=100, total_amount=100)
    db_session.add_all([quote, invoice]); await db_session.commit()
    customer = SimpleNamespace(role=UserRole.CUSTOMER, customer_id=a.customer.id, tenant_id=a.tenant.id)
    results = [
        await customers.get_customer_history(a.customer.id, db_session, customer),
        await customers.get_customer_history_detail(a.customer.id, a.order.id, db_session, customer),
        (await quotes.get_authorization_history(a.order.id, db_session, a.owner)).model_dump(mode='json'),
        (await quotes.get_quote_by_repair_order(a.order.id, db_session, a.owner)).model_dump(mode='json'),
        (await invoices.get_invoice(invoice.id, db_session, customer)).model_dump(mode='json'),
        (await routes.get_repair_order_workspace(a.order.id, db_session, a.owner)).model_dump(mode='json'),
    ]
    assert marker not in json.dumps(results, default=str)
    assert a.order.internal_notes is None and a.order.shop_notes is None and a.order.customer_notes is None


@pytest.mark.asyncio
async def test_route_response_codes_cache_headers_and_no_broadcast(db_session, monkeypatch):
    a = await seed(db_session)
    broadcast = AsyncMock()
    monkeypatch.setattr(routes, 'broadcast_repair_order_update', broadcast)
    request = body()
    response = Response()
    first = await routes.add_operation_note(a.order.id, a.lines[0].id, request, response, db_session, a.owner)
    assert response.status_code == 201 and response.headers['Cache-Control'] == 'no-store'
    response = Response()
    replay = await routes.add_operation_note(a.order.id, a.lines[0].id, request, response, db_session, a.owner)
    assert response.status_code == 200 and replay == first
    response = Response()
    result = await routes.get_operation_notes(a.order.id, a.lines[0].id, response, db_session, a.owner)
    assert response.headers['Cache-Control'] == 'no-store' and result.items == [first]
    broadcast.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('role', [UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST])
async def test_positive_shop_staff_write_read_policy(db_session, role):
    a = await seed(db_session)
    a.owner.role = role
    await db_session.commit()
    created, _ = await notes.append(db_session, a.order.id, a.lines[0].id, a.owner, body())
    assert (await notes.page(db_session, a.order.id, a.lines[0].id, a.owner)).items == [created]
    assert (await routes.get_repair_order_detail(a.order.id, db_session, a.owner)).history_events[0].id == created.id


@pytest.mark.asyncio
async def test_http_contract_validation_replay_and_privacy(client, db_session):
    from app.main import app
    from app.core.dependencies import get_current_active_user
    a = await seed(db_session)
    route = f'/api/v1/repair-orders/{a.order.id}/operations/{a.lines[0].id}/notes'
    app.dependency_overrides[get_current_active_user] = lambda: a.owner
    try:
        invalid = await client.post(route, json={'id': str(uuid4()), 'body': '  ', 'audience': 'customer'})
        assert invalid.status_code == 422
        request = {'id': str(uuid4()), 'body': '  HTTP operation note  '}
        created = await client.post(route, json=request)
        assert created.status_code == 201 and 'no-store' in created.headers['cache-control']
        assert created.json()['body'] == 'HTTP operation note'
        replay = await client.post(route, json=request)
        assert replay.status_code == 200 and replay.json() == created.json()
        listing = await client.get(route)
        assert listing.status_code == 200 and listing.json()['items'] == [created.json()]
        assert 'no-store' in listing.headers['cache-control']
        a.owner.role = UserRole.FLEET_MANAGER
        denied = await client.get(route)
        assert denied.status_code == 403 and 'HTTP operation note' not in denied.text
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)
