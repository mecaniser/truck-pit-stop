"""A2: clocks, source ownership, tenant isolation, full facets and read-only API."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import event

from app.api.v1.endpoints.dashboard import _native_billing_work_predicate
from app.core.security import create_access_token
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.labor import Labor
from app.db.models.quote import Quote
from app.db.models.repair_order import RepairOrder, RepairOrderStatus as Status
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.schemas.wip_aging import WipFilters
from app.services import wip_aging as wip

T = datetime(2026, 10, 29, 12, tzinfo=UTC)


def raw(**overrides):
    values = dict(id=uuid4(), order_number='A2-001', status=Status.IN_PROGRESS,
                  created_at=T-timedelta(days=3), hold_reason='waiting_for_parts', held_at=T-timedelta(hours=5),
                  assigned_at=None, acknowledged_at=None, work_started_at=T-timedelta(days=2), work_completed_at=None,
                  assigned_mechanic_id=None, scheduled_start_at=None, promised_finish_at=T-timedelta(hours=2),
                  customer_first_name='Contact', customer_last_name='Person', customer_company_name='Fictional Fleet',
                  is_internal_fleet=False, vehicle_year=2020, vehicle_make='VOLVO', vehicle_model='VNR',
                  vehicle_unit_number='609', quote_id=None, quote_sent=False, quote_sent_at=None,
                  quote_approved=False, quote_declined=False, quote_decision_at=None, quote_expires_at=None,
                  order_user_id=None, order_first_name=None, order_last_name=None, operation_mechanic_id=None,
                  operation_user_id=None, operation_first_name=None, operation_last_name=None, live_work=False)
    values.update(overrides)
    return values


def projected(**overrides):
    return wip.project_rows([raw(**overrides)], now=T, fleet_name=None)[0]


def test_three_clocks_are_distinct_and_updates_do_not_reset_them():
    evidence = raw()
    first = wip.project_rows([evidence], now=T, fleet_name=None)[0]
    evidence['updated_at'] = T
    assert wip.project_rows([evidence], now=T, fleet_name=None)[0] == first
    assert first.category == 'parts'
    assert first.current_wait.seconds == 18000
    assert first.order_age.seconds == 259200
    assert first.overdue_seconds == 7200


@pytest.mark.parametrize('changed,issue', [
    ({'held_at': None}, 'missing_timestamp'),
    ({'held_at': T+timedelta(seconds=1)}, 'future_timestamp'),
    ({'held_at': T-timedelta(days=4)}, 'inconsistent_evidence'),
    ({'created_at': T+timedelta(days=1)}, 'future_timestamp'),
    ({'live_work': True}, 'inconsistent_evidence'),
])
def test_wait_unknown_is_never_zero(changed, issue):
    value = projected(**changed).current_wait
    assert value.state == 'unknown' and value.issue == issue
    assert value.seconds is None and value.since is None


@pytest.mark.parametrize('reason,category,expected', [
    ('waiting_for_parts', 'parts', 'waiting_for_parts'),
    ('waiting_for_customer_approval', 'approval', 'approval_hold'),
    ('need_more_info', 'other_hold', 'need_more_info'),
    ('switched_to_other_ro', 'other_hold', 'technician_switched'),
    ('waiting for parts perhaps', 'other_hold', 'other_hold'),
])
def test_hold_categories_use_exact_source_codes(reason, category, expected):
    value = projected(hold_reason=reason)
    assert (value.category, value.reason) == (category, expected)


def test_live_work_is_not_zero_wait_and_stale_hold_fields_are_ignored():
    assert projected(hold_reason=None).current_wait.state == 'not_applicable'
    draft = projected(status=Status.DRAFT)
    assert draft.hold_reason is None
    assert draft.current_wait.state == 'unknown'
    assert draft.reason == 'prepare_estimate'


@pytest.mark.parametrize('changed,reason,state', [
    ({'quote_sent': False, 'quote_sent_at': None}, 'quote_not_sent', 'unknown'),
    ({'quote_sent_at': None}, 'quote_evidence_unknown', 'unknown'),
    ({'quote_approved': True}, 'quote_evidence_unknown', 'unknown'),
    ({'quote_decision_at': T}, 'quote_evidence_unknown', 'unknown'),
    ({'quote_expires_at': T-timedelta(hours=1)}, 'quote_expired', 'unknown'),
    ({'quote_expires_at': T-timedelta(days=2)}, 'quote_evidence_unknown', 'unknown'),
    ({}, 'awaiting_customer_decision', 'known'),
])
def test_quote_wait_requires_consistent_published_pending_unexpired_revision(changed, reason, state):
    values = dict(status=Status.QUOTED, quote_id=uuid4(), quote_sent=True,
                  quote_sent_at=T-timedelta(days=1), hold_reason=None)
    values.update(changed)
    row = projected(**values)
    assert row.reason == reason and row.current_wait.state == state


def test_quote_seven_day_boundary_and_review_missing_time():
    values = dict(status=Status.QUOTED, quote_id=uuid4(), quote_sent=True,
                  quote_sent_at=T-timedelta(days=7), created_at=T-timedelta(days=10), hold_reason=None)
    assert projected(**values).category == 'approval'
    values['quote_sent_at'] -= timedelta(seconds=1)
    assert projected(**values).reason == 'quote_expired'
    review = projected(status=Status.PENDING_REVIEW, hold_reason=None)
    assert review.category == 'review' and review.current_wait.state == 'unknown'


def test_assignment_must_have_valid_current_order_identity_to_support_ack_clock():
    tech = uuid4()
    row = projected(status=Status.ASSIGNED, hold_reason=None, work_started_at=None,
                    assigned_at=T-timedelta(hours=1), assigned_mechanic_id=tech,
                    order_user_id=tech, order_first_name='Fictional', order_last_name='Tech')
    assert row.current_wait.seconds == 3600 and row.assignment == 'assigned'
    invalid = projected(status=Status.ASSIGNED, hold_reason=None, work_started_at=None,
                        assigned_at=T-timedelta(hours=1), assigned_mechanic_id=tech)
    assert invalid.assignment == 'unknown' and invalid.current_wait.state == 'unknown'


def test_facets_before_filters_and_pagination_and_literal_search():
    rows = [projected(order_number=f'A2-{n}') for n in range(51)]
    rows += [projected(status=Status.PENDING_REVIEW, hold_reason=None, order_number='review_100%')]
    response = wip.build_response(rows, now=T, zone='UTC', scope='shop', filters=WipFilters(category='parts'), offset=0, limit=50)
    assert response.summary.total_jobs == 52
    assert response.summary.category_counts['review'] == 1
    assert response.filtered_total == 51 and len(response.items) == 50 and response.has_more
    last = wip.build_response(rows, now=T, zone='UTC', scope='shop', filters=WipFilters(category='parts'), offset=50, limit=50)
    assert len(last.items) == 1 and not last.has_more
    literal = wip.build_response(rows, now=T, zone='UTC', scope='shop', filters=WipFilters(search='_100%'), offset=0, limit=50)
    assert literal.summary.total_jobs == 1 and literal.items[0].order_number == 'review_100%'


@pytest.mark.asyncio
@pytest.mark.parametrize('role', [UserRole.CUSTOMER, UserRole.DRIVER, UserRole.FLEET_MANAGER, UserRole.SUPER_ADMIN])
async def test_denied_role_before_any_query(role):
    actor = SimpleNamespace(role=role, tenant_id=uuid4(), is_active=True, deleted_at=None)
    with pytest.raises(HTTPException) as error:
        await wip.read_wip_aging(object(), actor, native_predicate=None, filters=WipFilters())
    assert error.value.status_code == 403


async def fixture(db):
    tenant = Tenant(name='A2 fictional shop', slug=f'a2-{uuid4().hex}', timezone='America/New_York')
    db.add(tenant)
    await db.flush()
    owner = User(email=f'a2-{uuid4().hex}@example.com', first_name='A2', last_name='Owner',
                 role=UserRole.GARAGE_OWNER, tenant_id=tenant.id, hashed_password='unused', is_active=True)
    mechanic = User(email=f'a2-{uuid4().hex}@example.com', first_name='A2', last_name='Tech',
                    role=UserRole.MECHANIC, tenant_id=tenant.id, hashed_password='unused', is_active=True)
    customer = Customer(tenant_id=tenant.id, first_name='Contact', last_name='Person', company_name='Fictional Fleet', email=f'customer-{uuid4().hex}@example.com', phone='5550001234')
    db.add_all([owner, mechanic, customer])
    await db.flush()
    vehicle = Vehicle(tenant_id=tenant.id, customer_id=customer.id, make='VOLVO', model='VNR', unit_number='609')
    db.add(vehicle)
    await db.flush()
    return tenant, owner, mechanic, customer, vehicle


def order(fix, **overrides):
    tenant, _, _, customer, vehicle = fix
    values = dict(tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id,
                  order_number=f'A2-{uuid4().hex[:16]}', status=Status.IN_PROGRESS,
                  created_at=T-timedelta(days=3), updated_at=T, hold_reason='waiting_for_parts',
                  held_at=T-timedelta(hours=5), work_started_at=T-timedelta(days=2),
                  promised_finish_at=T-timedelta(hours=2))
    values.update(overrides)
    return RepairOrder(**values)


async def read(db, actor, **kw):
    return await wip.read_wip_aging(db, actor, native_predicate=_native_billing_work_predicate(),
                                  filters=kw.pop('filters', WipFilters()), now=T, **kw)


@pytest.mark.asyncio
async def test_database_ownership_scope_latest_quote_and_read_only(db_session):
    db = db_session
    fix = await fixture(db)
    other = await fixture(db)
    keep = order(fix, status=Status.QUOTED, hold_reason=None)
    hidden = [order(fix, status=s) for s in (Status.COMPLETED, Status.INVOICED, Status.PAID, Status.CANCELLED)]
    hidden += [order(fix, source='easy_truck_shop_import'), order(fix, deleted_at=T), order(fix, vehicle_released_at=T)]
    historical, foreign_link = order(fix), order(fix)
    cross_customer = order(fix, customer_id=other[3].id)
    db.add_all([keep, historical, foreign_link, cross_customer, *hidden])
    await db.flush()
    old_quote = Quote(tenant_id=fix[0].id, repair_order_id=keep.id, quote_number=f'Q-{uuid4().hex}',
                      revision=1, total_amount=1, sent_to_customer=True, sent_at=T-timedelta(days=1))
    new_quote = Quote(tenant_id=fix[0].id, repair_order_id=keep.id, quote_number=f'Q-{uuid4().hex}',
                      revision=2, total_amount=1, sent_to_customer=False)
    db.add_all([old_quote, new_quote,
        Invoice(tenant_id=fix[0].id, repair_order_id=historical.id, invoice_number=f'I-{uuid4().hex}',
                status=InvoiceStatus.CANCELLED, deleted_at=T, accounting_policy='historical_export_hold', subtotal=0, total_amount=0),
        Invoice(tenant_id=other[0].id, repair_order_id=foreign_link.id, invoice_number=f'I-{uuid4().hex}',
                status=InvoiceStatus.CANCELLED, source='easy_truck_shop_import', subtotal=0, total_amount=0)])
    await db.commit()
    queries = []
    listener = lambda conn, cursor, statement, *args: queries.append(statement.strip().split()[0].upper())
    event.listen(db.bind.sync_engine, 'before_cursor_execute', listener)
    try:
        result = await read(db, fix[1])
    finally:
        event.remove(db.bind.sync_engine, 'before_cursor_execute', listener)
    assert queries == ['SELECT', 'SELECT']
    assert {r.id for r in result.items} == {str(keep.id), str(foreign_link.id)}
    assert next(r for r in result.items if r.id == str(keep.id)).reason == 'quote_not_sent'
    assert 'total_cost' not in result.model_dump_json()
    assert 'quote_token' not in result.model_dump_json()
    assert not db.new and not db.dirty and not db.deleted
    contact = await read(db, fix[1], filters=WipFilters(search='Contact Person'))
    assert contact.summary.total_jobs == 2


@pytest.mark.asyncio
async def test_database_mechanic_scope_before_summary_and_operation_dedup(db_session):
    db = db_session
    fix = await fixture(db)
    other = await fixture(db)
    assigned, private = order(fix), order(fix)
    db.add_all([assigned, private])
    await db.flush()
    for n in range(2):
        db.add(Labor(tenant_id=fix[0].id, repair_order_id=assigned.id, mechanic_id=fix[2].id,
                     description=f'Fictional {n}', hours=0, hourly_rate=0, total_cost=0, execution_status=None))
    db.add(Labor(tenant_id=other[0].id, repair_order_id=private.id, mechanic_id=fix[2].id,
                 description='Foreign invalid link', hours=0, hourly_rate=0, total_cost=0))
    await db.commit()
    result = await read(db, fix[2])
    assert result.scope == 'assigned' and result.summary.total_jobs == 1
    assert result.summary.overdue_jobs == 1
    assert result.items[0].id == str(assigned.id)
    assert result.items[0].technician_names == ['A2 Tech']
    assert result.items[0].assignment == 'assigned'


@pytest.mark.asyncio
async def test_endpoint_validates_queries_and_denies_inactive_tenant(client, db_session):
    fix = await fixture(db_session)
    await db_session.commit()
    token = create_access_token({'sub': str(fix[1].id)})
    headers = {'Authorization': f'Bearer {token}'}
    for query in ['category=money', 'limit=101', 'offset=-1', 'timing=zero', 'search='+('x'*201)]:
        response = await client.get('/api/v1/dashboard/wip-aging?'+query, headers=headers)
        assert response.status_code == 422
    response = await client.get('/api/v1/dashboard/wip-aging', headers=headers)
    assert response.status_code == 200 and response.json()['summary']['total_jobs'] == 0
    fix[0].is_active = False
    await db_session.commit()
    response = await client.get('/api/v1/dashboard/wip-aging', headers=headers)
    assert response.status_code == 403


@pytest.mark.parametrize('values', [
    {'promised_finish_at': T-timedelta(days=4)},
    {'scheduled_start_at': T-timedelta(hours=1)},
    {'created_at': T+timedelta(days=1)},
])
def test_contradictory_deadlines_do_not_make_overdue_claims(values):
    row = projected(**values)
    assert row.promised_finish_at is None and not row.is_overdue and row.overdue_seconds is None


def test_future_promise_is_a_valid_deadline_and_utc_crosses_dst():
    row = projected(promised_finish_at=T+timedelta(hours=2))
    assert row.promised_finish_at == T+timedelta(hours=2) and not row.is_overdue
    from zoneinfo import ZoneInfo
    before = datetime(2026, 11, 1, 1, 30, tzinfo=ZoneInfo('America/New_York'), fold=0)
    after = datetime(2026, 11, 1, 1, 30, tzinfo=ZoneInfo('America/New_York'), fold=1)
    assert wip.clock(before, after.astimezone(UTC)).seconds == 3600


@pytest.mark.asyncio
async def test_database_all_rows_before_pagination_and_no_scope_leak(db_session):
    db = db_session
    fix, other = await fixture(db), await fixture(db)
    jobs = [order(fix, order_number=f'A2-page-{uuid4().hex[:8]}') for _ in range(53)]
    db.add_all([*jobs, order(other)])
    await db.commit()
    first = await read(db, fix[1])
    second = await read(db, fix[1], offset=50)
    assert first.summary.total_jobs == second.summary.total_jobs == 53
    assert len(first.items) == 50 and len(second.items) == 3
    assert first.has_more and not second.has_more
    assert len({row.id for row in first.items+second.items}) == 53
    unknown = await read(db, fix[1], filters=WipFilters(timing='unknown'))
    assert unknown.summary.total_jobs == 53 and unknown.filtered_total == 0
