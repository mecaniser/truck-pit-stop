"""DB-151 source, permission, population and SELECT-only acceptance tests."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.v1.endpoints.dashboard import _native_billing_work_predicate
from app.core.config import settings
from app.core.security import create_access_token
from app.db.models.customer import Customer
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import InvoiceSettlement
from app.db.models.labor import Labor
from app.db.models.parts_operations import CoreObligation, PurchaseOrder, PurchaseOrderLine, VendorReturn, VendorReturnLine
from app.db.models.repair_order import RepairOrder, RepairOrderStatus as Status
from app.db.models.supplier import Supplier
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.services import shop_work_overview as overview
from app.services.native_record_classification import NativeRecordPolicy

T = datetime(2026, 11, 1, 12, tzinfo=UTC)


async def fixture(db, *, role=UserRole.GARAGE_OWNER, parts=True, permissions=None):
    tenant = Tenant(name='Overview test', slug=uuid4().hex, timezone='America/New_York', parts_operations_enabled=parts)
    db.add(tenant)
    await db.flush()
    actor = User(tenant_id=tenant.id, email=f'{uuid4().hex}@example.com', first_name='Test', last_name='User',
                 role=role, permissions=permissions or {}, hashed_password='unused', is_active=True)
    customer = Customer(tenant_id=tenant.id, first_name='Test', last_name='Customer', company_name=f'Fleet {uuid4().hex[:4]}',
                        email=f'{uuid4().hex}@example.com', phone='5550001234')
    supplier = Supplier(tenant_id=tenant.id, name='Test supplier')
    db.add_all([actor, customer, supplier])
    await db.flush()
    vehicle = Vehicle(tenant_id=tenant.id, customer_id=customer.id, make='VOLVO', model='VNR')
    db.add(vehicle)
    await db.flush()
    return SimpleNamespace(tenant=tenant, actor=actor, customer=customer, supplier=supplier, vehicle=vehicle)


def order(fix, **kw):
    data = dict(tenant_id=fix.tenant.id, customer_id=fix.customer.id, vehicle_id=fix.vehicle.id,
                order_number=f'RO-{uuid4().hex[:12]}', status=Status.IN_PROGRESS,
                created_at=T-timedelta(days=3), work_started_at=T-timedelta(days=2))
    return RepairOrder(**(data | kw))


def part(fix, **kw):
    return Inventory(**(dict(tenant_id=fix.tenant.id, sku=uuid4().hex, name='Filter', cost=10, selling_price=20,
                            stock_quantity=0, reorder_level=3, created_at=T-timedelta(days=2)) | kw))


def po(fix, **kw):
    return PurchaseOrder(**(dict(tenant_id=fix.tenant.id, supplier_id=fix.supplier.id,
                                po_number=f'PO-{uuid4().hex[:12]}', status='draft', created_at=T-timedelta(days=1)) | kw))


def po_line(fix, purchase, stock, **kw):
    return PurchaseOrderLine(**(dict(tenant_id=fix.tenant.id, purchase_order_id=purchase.id, inventory_id=stock.id,
        sku_snapshot=stock.sku, description_snapshot=stock.name, unit_type_snapshot='each', unit_cost_snapshot=10,
        ordered_quantity=3, received_quantity=0) | kw))


def invoice(fix, repair, **kw):
    return Invoice(**(dict(tenant_id=fix.tenant.id, repair_order_id=repair.id, billed_customer_id=fix.customer.id,
        invoice_number=f'I-{uuid4().hex[:12]}', status=InvoiceStatus.SENT, subtotal=100, total_amount=100) | kw))


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    monkeypatch.setattr(settings, 'PARTS_OPERATIONS_V1_ENABLED', True)
    monkeypatch.setattr(overview, 'load_native_record_policy', lambda: NativeRecordPolicy(True, {}))


async def read(db, actor, **kw):
    return await overview.read_shop_work_overview(actor, native_predicate=_native_billing_work_predicate(),
        now=T, session_factory=async_sessionmaker(db.bind, expire_on_commit=False), **kw)


def sources(result):
    return {source.id: source for source in result.sources}


@pytest.mark.asyncio
@pytest.mark.parametrize('role', [UserRole.CUSTOMER, UserRole.DRIVER, UserRole.FLEET_MANAGER, UserRole.SUPER_ADMIN])
async def test_invalid_role_denied_before_session(role):
    actor = SimpleNamespace(role=role, tenant_id=uuid4(), is_active=True, deleted_at=None)
    with pytest.raises(HTTPException) as error:
        await overview.read_shop_work_overview(actor, native_predicate=None, session_factory=lambda: pytest.fail('query'))
    assert error.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize('role,permissions', [(UserRole.RECEPTIONIST, {}), (UserRole.GARAGE_ADMIN, {}),
                                               (UserRole.MECHANIC, {})])
async def test_financial_authorization_precedes_read(db_session, monkeypatch, role, permissions):
    fix = await fixture(db_session, role=role, permissions=permissions)
    await db_session.commit()
    async def forbidden(*args):
        pytest.fail('Financial source must not be queried')
    monkeypatch.setattr(overview, 'read_receivables', forbidden)
    result = await read(db_session, fix.actor)
    source = sources(result)['receivables']
    assert source.state == 'restricted' and source.total is None and source.shown == 0
    assert not any(row.source == 'receivables' for row in result.actions)
    assert result.actions_total == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('tenant_flag,global_flag', [(False, True), (True, False)])
async def test_disabled_parts_do_not_query(db_session, monkeypatch, tenant_flag, global_flag):
    fix = await fixture(db_session, parts=tenant_flag)
    await db_session.commit()
    monkeypatch.setattr(settings, 'PARTS_OPERATIONS_V1_ENABLED', global_flag)
    async def forbidden(*args):
        pytest.fail('Disabled source queried')
    for name in ('read_inventory', 'read_purchasing', 'read_returns', 'read_cores'):
        monkeypatch.setattr(overview, name, forbidden)
    result = await read(db_session, fix.actor)
    assert all(sources(result)[name].state == 'disabled' for name in ('inventory', 'purchasing', 'returns', 'cores'))


@pytest.mark.asyncio
async def test_quiet_shop_still_has_parts_purchasing_returns_cores_account_review(db_session):
    db = db_session
    fix = await fixture(db)
    stock = part(fix)
    purchase = po(fix)
    completed = order(fix, status=Status.COMPLETED)
    returned = VendorReturn(tenant_id=fix.tenant.id, supplier_id=fix.supplier.id,
                            return_number='R-1', kind='stock', status='shipped')
    db.add_all([stock, purchase, completed, returned])
    await db.flush()
    usage = PartsUsage(tenant_id=fix.tenant.id, repair_order_id=completed.id, inventory_id=stock.id,
                       quantity=1, unit_price=20, total_price=20)
    bill = invoice(fix, completed)
    db.add_all([usage, bill])
    await db.flush()
    db.add(CoreObligation(tenant_id=fix.tenant.id, parts_usage_id=usage.id, inventory_id=stock.id,
                          quantity=1, unit_core_value_snapshot=5, status='expected'))
    await db.commit()
    result = await read(db, fix.actor)
    assert result.active_jobs == 0
    assert {row.source for row in result.actions} == {'inventory', 'purchasing', 'returns', 'cores', 'receivables'}
    finance = next(row for row in result.actions if row.source == 'receivables')
    assert finance.destination.id == str(fix.customer.id) and finance.action_label == 'Review account'
    assert finance.due_at is None and finance.quantity is None and finance.evidence == 'review_required'
    assert sources(result)['receivables'].state == 'partial'
    assert sources(result)['receivables'].reason == 'account_review_only'
    assert result.actions_total is None
    payload = finance.model_dump()
    assert not {'amount', 'balance', 'overdue', 'invoice_id'} & payload.keys()


@pytest.mark.asyncio
async def test_tenant_links_and_mechanic_scope(db_session):
    db = db_session
    local, foreign = await fixture(db), await fixture(db)
    mechanic = User(tenant_id=local.tenant.id, email=f'{uuid4().hex}@example.com', first_name='Tech', last_name='One',
                    role=UserRole.MECHANIC, hashed_password='unused', is_active=True)
    db.add(mechanic)
    await db.flush()
    assigned = order(local, status=Status.DRAFT, assigned_mechanic_id=mechanic.id)
    operation_assigned = order(local, status=Status.DRAFT)
    hidden = order(local, status=Status.DRAFT)
    cross_customer = order(local, status=Status.DRAFT, customer_id=foreign.customer.id)
    cross_vehicle = order(local, status=Status.DRAFT, vehicle_id=foreign.vehicle.id)
    foreign_order = order(foreign, status=Status.DRAFT, assigned_mechanic_id=mechanic.id)
    db.add_all([assigned, operation_assigned, hidden, cross_customer, cross_vehicle, foreign_order])
    await db.flush()
    db.add(Labor(tenant_id=local.tenant.id, repair_order_id=operation_assigned.id, mechanic_id=mechanic.id,
                 description='Assigned work', hours=1, hourly_rate=100, total_cost=100))
    await db.commit()
    result = await read(db, mechanic)
    assert result.scope == 'assigned' and result.active_jobs == 2
    assert {row.destination.id for row in result.actions} == {str(assigned.id), str(operation_assigned.id)}
    assert all(sources(result)[key].state == 'restricted' for key in ('inventory', 'purchasing', 'returns', 'cores', 'receivables'))
    owner = await read(db, local.actor)
    assert {row.destination.id for row in owner.actions} == {str(assigned.id), str(operation_assigned.id), str(hidden.id)}


@pytest.mark.asyncio
async def test_schedule_dedup_invalid_time_and_timezone(db_session):
    db = db_session
    fix = await fixture(db, role=UserRole.RECEPTIONIST)
    fix.tenant.timezone = 'No/Such_Zone'
    active = order(fix, scheduled_start_at=T+timedelta(hours=1), promised_finish_at=T+timedelta(hours=3))
    overdue = order(fix, promised_finish_at=T-timedelta(hours=1))
    hold = order(fix, hold_reason='waiting_for_customer_approval', promised_finish_at=T+timedelta(hours=2))
    invalid = order(fix, promised_finish_at=T-timedelta(days=5))
    invalid_creation = order(fix, created_at=T+timedelta(days=1), scheduled_start_at=T+timedelta(days=2))
    unscheduled = order(fix)
    db.add_all([active, overdue, hold, invalid, invalid_creation, unscheduled])
    await db.commit()
    result = await read(db, fix.actor)
    assert result.timezone is None and result.active_jobs == 6
    assert [row.destination.id for row in result.upcoming] == [str(active.id)]
    assert result.upcoming[0].due_kind == 'repair_start'
    assert result.actions[0].destination.id == str(overdue.id)
    assert result.actions[0].reason == 'repair_promise_overdue'
    assert {row.destination.id for row in result.actions} == {str(overdue.id), str(hold.id)}


@pytest.mark.asyncio
async def test_shortage_subtracts_ordered_supply_and_only_actual_links_dedup(db_session):
    db = db_session
    fix, foreign = await fixture(db, role=UserRole.RECEPTIONIST), await fixture(db)
    stock = part(fix, reorder_level=2, on_order_quantity=1)
    held = order(fix, hold_reason='waiting_for_parts')
    textual = order(fix, hold_reason='waiting_for_parts')
    purchase = po(fix, status='partially_received', expected_at=T+timedelta(days=2))
    retired = part(fix, ets_retired_at=T)
    placeholder = part(fix, is_placeholder=True)
    db.add_all([stock, held, textual, purchase, retired, placeholder])
    await db.flush()
    db.add_all([PartsUsage(tenant_id=fix.tenant.id, repair_order_id=held.id, inventory_id=stock.id,
                          quantity=5, stock_reserved_packages=1, unit_price=20, total_price=100),
                PartsUsage(tenant_id=foreign.tenant.id, repair_order_id=held.id, inventory_id=stock.id,
                           quantity=100, stock_reserved_packages=0, unit_price=20, total_price=2000),
                po_line(fix, purchase, stock, ordered_quantity=4, received_quantity=2),
                po_line(foreign, purchase, stock, ordered_quantity=99)])
    await db.commit()
    result = await read(db, fix.actor)
    stock_task = next(row for row in result.actions if row.source == 'inventory')
    assert stock_task.quantity == 3  # 4 shortage + 2 shelf - 1 legacy - 2 remaining PO
    assert stock_task.related_repair_order_ids == [str(held.id)]
    assert {row.destination.id for row in result.actions if row.source == 'repairs'} == {str(textual.id)}
    assert len(result.upcoming) == 1 and result.upcoming[0].quantity == 2
    assert result.upcoming[0].destination.view == 'receiving'
    assert sources(result)['inventory'].total == 1


@pytest.mark.asyncio
async def test_return_core_dedup_scopes_both_join_sides(db_session):
    db = db_session
    fix, foreign = await fixture(db), await fixture(db)
    stock, repair = part(fix, reorder_level=0), order(fix, status=Status.COMPLETED)
    db.add_all([stock, repair])
    await db.flush()
    cores = []
    for index in range(4):
        usage = PartsUsage(tenant_id=fix.tenant.id, repair_order_id=repair.id, inventory_id=stock.id,
                           quantity=1, unit_price=20, total_price=20)
        db.add(usage)
        await db.flush()
        core = CoreObligation(tenant_id=fix.tenant.id, parts_usage_id=usage.id, inventory_id=stock.id,
                              quantity=1, unit_core_value_snapshot=5, status='on_hand')
        db.add(core)
        cores.append(core)
    active_return = VendorReturn(tenant_id=fix.tenant.id, supplier_id=fix.supplier.id, return_number='R-A', kind='core', status='submitted')
    foreign_return = VendorReturn(tenant_id=foreign.tenant.id, supplier_id=foreign.supplier.id, return_number='R-B', kind='core', status='submitted')
    db.add_all([active_return, foreign_return])
    await db.flush()
    for core, tenant_id, return_id, deleted_at in [
        (cores[0], fix.tenant.id, active_return.id, None),
        (cores[1], foreign.tenant.id, active_return.id, None),
        (cores[2], fix.tenant.id, foreign_return.id, None),
        (cores[3], fix.tenant.id, active_return.id, T),
    ]:
        db.add(VendorReturnLine(tenant_id=tenant_id, vendor_return_id=return_id, core_obligation_id=core.id,
                               inventory_id=stock.id, quantity=1, expected_credit=5, deleted_at=deleted_at))
    await db.commit()
    result = await read(db, fix.actor)
    assert {row.destination.id for row in result.actions if row.source == 'cores'} == {str(row.id) for row in cores[1:]}
    assert {row.destination.id for row in result.actions if row.source == 'returns'} == {str(active_return.id)}


@pytest.mark.asyncio
async def test_full_counts_before_page_and_honest_cap(db_session, monkeypatch):
    db = db_session
    fix = await fixture(db, role=UserRole.RECEPTIONIST)
    db.add_all([po(fix) for _ in range(4)])
    await db.commit()
    result = await read(db, fix.actor, limit=1)
    assert result.actions_total == 4 and len(result.actions) == 1 and result.has_more_actions
    assert sources(result)['purchasing'].total == 4 and sources(result)['purchasing'].has_more
    monkeypatch.setattr(overview, 'SOURCE_CAP', 2)
    capped = await read(db, fix.actor, limit=1)
    source = sources(capped)['purchasing']
    assert source.state == 'partial' and source.total is None and source.has_more
    assert capped.actions_total is None and capped.upcoming_total is None


@pytest.mark.asyncio
async def test_source_failure_isolated_and_unknown_not_zero(db_session, monkeypatch):
    db = db_session
    fix = await fixture(db)
    db.add(po(fix))
    await db.commit()
    sessions = []
    async def failed(db, *args):
        sessions.append(db)
        raise RuntimeError('PRIVATE source detail must not escape')
    original = overview.read_purchasing
    async def later(db, *args):
        assert db is not sessions[0]
        return await original(db, *args)
    monkeypatch.setattr(overview, 'read_inventory', failed)
    monkeypatch.setattr(overview, 'read_purchasing', later)
    result = await read(db, fix.actor)
    assert sources(result)['inventory'].state == 'unavailable'
    assert sources(result)['inventory'].total is None
    assert sources(result)['purchasing'].total == 1
    assert 'PRIVATE' not in result.model_dump_json()


@pytest.mark.asyncio
async def test_finance_issued_native_resolved_identity_and_test_policy(db_session, monkeypatch):
    db = db_session
    fix, foreign = await fixture(db), await fixture(db)
    rows = []
    for overrides in [{}, {'source': 'easy_truck_shop_import'}, {'accounting_policy': 'historical_export_hold'},
                      {'is_internal': True}, {'voided_at': T}, {'status': InvoiceStatus.DRAFT},
                      {'billed_customer_id': foreign.customer.id}, {'billed_customer_id': uuid4()}]:
        repair = order(fix, status=Status.COMPLETED)
        db.add(repair)
        await db.flush()
        bill = invoice(fix, repair, **overrides)
        db.add(bill)
        rows.append(bill)
    test_customer = Customer(tenant_id=fix.tenant.id, first_name='Test', last_name='Only', phone='5550001244', email=f'{uuid4().hex}@example.com')
    db.add(test_customer)
    await db.flush()
    test_ro = order(fix, customer_id=test_customer.id, status=Status.COMPLETED)
    db.add(test_ro)
    await db.flush()
    test_bill = invoice(fix, test_ro, billed_customer_id=test_customer.id)
    db.add(test_bill)
    await db.flush()
    policy = SimpleNamespace(available=True, classify=lambda invoice, *args, **kw: 'test' if invoice.id == test_bill.id else 'unknown')
    monkeypatch.setattr(overview, 'load_native_record_policy', lambda: policy)
    await db.commit()
    result = await read(db, fix.actor)
    assert [row.destination.id for row in result.actions if row.source == 'receivables'] == [str(fix.customer.id)]
    # An orphan authoritative bill-to must never fall back to its RO customer.
    rows[0].status = InvoiceStatus.DRAFT
    await db.commit()
    result = await read(db, fix.actor)
    assert not [row for row in result.actions if row.source == 'receivables']


@pytest.mark.asyncio
async def test_finance_settlement_validity_grouping_and_constant_query_count(db_session):
    db = db_session
    fix = await fixture(db)
    records = []
    for index in range(5):
        repair = order(fix, status=Status.COMPLETED)
        db.add(repair)
        await db.flush()
        bill = invoice(fix, repair)
        db.add(bill)
        await db.flush()
        settlement = InvoiceSettlement(tenant_id=fix.tenant.id, invoice_id=bill.id, customer_id=fix.customer.id,
            currency='USD', principal_total=100, confirmed_principal=100,
            legacy_reconciliation_status='native')
        db.add(settlement)
        records.append(settlement)
    await db.commit()
    statements = []
    def capture(conn, cursor, statement, *args):
        statements.append(statement)
    event.listen(db.bind.sync_engine, 'before_cursor_execute', capture)
    try:
        result = await read(db, fix.actor)
    finally:
        event.remove(db.bind.sync_engine, 'before_cursor_execute', capture)
    assert not [row for row in result.actions if row.source == 'receivables']
    # One tenant batch each for invoices, settlement rows, baseline markers and
    # imported markers. There are no per-customer account_snapshot calls.
    assert sum('FROM invoice_settlements' in sql for sql in statements) == 1
    assert all(sql.lstrip().upper().startswith('SELECT') for sql in statements)
    records[0].principal_total = Decimal('101')
    records[1].confirmed_principal = Decimal('50')
    await db.commit()
    result = await read(db, fix.actor)
    assert len([row for row in result.actions if row.source == 'receivables']) == 1


@pytest.mark.asyncio
async def test_invalid_policy_is_partial_no_synthetic_identity(db_session, monkeypatch):
    fix = await fixture(db_session)
    await db_session.commit()
    monkeypatch.setattr(overview, 'load_native_record_policy', lambda: NativeRecordPolicy(False, {}))
    result = await read(db_session, fix.actor)
    source = sources(result)['receivables']
    assert source.state == 'partial' and source.total is None and source.reason == 'classification_unavailable'
    assert result.actions_total is None and not result.actions


@pytest.mark.asyncio
async def test_read_does_not_flush_dirty_objects_or_commit(db_session):
    fix = await fixture(db_session)
    await db_session.commit()
    fix.customer.company_name = 'UNCOMMITTED CHANGE'
    result = await read(db_session, fix.actor)
    assert result.active_jobs == 0 and fix.customer in db_session.dirty
    async with async_sessionmaker(db_session.bind)() as fresh:
        saved = await fresh.scalar(select(Customer.company_name).where(Customer.id == fix.customer.id))
        assert saved != 'UNCOMMITTED CHANGE'


@pytest.mark.asyncio
async def test_endpoint_limits_and_private_cache(client, db_session, monkeypatch):
    fix = await fixture(db_session, role=UserRole.RECEPTIONIST)
    await db_session.commit()
    monkeypatch.setattr(overview, 'AsyncSessionLocal', async_sessionmaker(db_session.bind, expire_on_commit=False))
    token = create_access_token({'sub': str(fix.actor.id)})
    headers = {'Authorization': f'Bearer {token}'}
    response = await client.get('/api/v1/dashboard/shop-work-overview', headers=headers)
    assert response.status_code == 200, response.text
    assert {value.strip() for value in response.headers['cache-control'].split(',')} == {'private', 'no-store'}
    assert response.json()['active_jobs'] == 0
    for query in ['limit=0', 'limit=101', 'upcoming_limit=0', 'upcoming_limit=51']:
        invalid = await client.get(f'/api/v1/dashboard/shop-work-overview?{query}', headers=headers)
        assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_quiet_shop_completed_unbilled_and_pending_payment_review(db_session):
    db = db_session
    fix, foreign = await fixture(db), await fixture(db)
    unbilled = order(fix, status=Status.COMPLETED)
    pending = order(fix, status=Status.INVOICED)
    issued = order(fix, status=Status.INVOICED)
    imported = order(fix, status=Status.COMPLETED, source='easy_truck_shop_import')
    released = order(fix, status=Status.COMPLETED, vehicle_released_at=T)
    foreign_link = order(fix, status=Status.COMPLETED)
    db.add_all([unbilled, pending, issued, imported, released, foreign_link])
    await db.flush()
    db.add_all([invoice(fix, pending, zelle_pending_submitted_at=T), invoice(fix, issued),
                invoice(foreign, foreign_link)])
    await db.commit()
    result = await read(db, fix.actor)
    repair_rows = {row.destination.id: row for row in result.actions if row.source == 'repairs'}
    assert result.active_jobs == 0
    assert set(repair_rows) == {str(unbilled.id), str(pending.id), str(foreign_link.id)}
    assert repair_rows[str(unbilled.id)].reason == 'review_closeout'
    assert repair_rows[str(unbilled.id)].destination.view == 'ready_to_close'
    assert repair_rows[str(pending.id)].reason == 'review_payment'
    assert repair_rows[str(pending.id)].destination.view == 'needs_action'
    # Account review owns the ordinary issued invoice, no second RO closeout.
    assert str(issued.id) not in repair_rows
    fix.actor.role = UserRole.RECEPTIONIST
    await db.commit()
    restricted = await read(db, fix.actor)
    assert not any(row.reason == 'review_payment' for row in restricted.actions)
    assert sources(restricted)['receivables'].state == 'restricted'


@pytest.mark.asyncio
async def test_repairs_failure_does_not_hide_other_sources(db_session, monkeypatch):
    fix = await fixture(db_session, role=UserRole.RECEPTIONIST)
    db_session.add(po(fix))
    await db_session.commit()
    async def failed(*args):
        raise RuntimeError('private')
    monkeypatch.setattr(overview, 'read_repairs', failed)
    result = await read(db_session, fix.actor)
    assert result.active_jobs is None and result.actions_total is None and result.upcoming_total is None
    assert sources(result)['repairs'].state == sources(result)['schedule'].state == 'unavailable'
    assert len(result.actions) == 1 and result.actions[0].source == 'purchasing'


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['bad_baseline', 'imported_payment', 'foreign_marker'])
async def test_finance_baseline_and_payment_markers_are_tenant_scoped(db_session, kind):
    from app.db.models.invoice_settlement import InvoicePaymentLedgerEvent
    from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
    db = db_session
    fix, foreign = await fixture(db), await fixture(db)
    repair = order(fix, status=Status.COMPLETED)
    db.add(repair)
    await db.flush()
    bill = invoice(fix, repair)
    db.add(bill)
    await db.flush()
    settlement = InvoiceSettlement(tenant_id=fix.tenant.id, invoice_id=bill.id, customer_id=fix.customer.id,
        currency='USD', principal_total=100, confirmed_principal=100, legacy_reconciliation_status='native')
    db.add(settlement)
    await db.flush()
    if kind != 'imported_payment':
        db.add(InvoicePaymentLedgerEvent(tenant_id=foreign.tenant.id if kind == 'foreign_marker' else fix.tenant.id,
            invoice_id=bill.id, settlement_id=settlement.id, customer_id=fix.customer.id,
            actor_name_snapshot='Test', sequence=1, idempotency_key=uuid4().hex,
            event_type='legacy_paid_snapshot'))
    else:
        db.add(Payment(tenant_id=fix.tenant.id, invoice_id=bill.id, payment_number=uuid4().hex,
                       amount=100, method=PaymentMethod.CASH, status=PaymentStatus.COMPLETED,
                       source='easy_truck_shop_import'))
    await db.commit()
    result = await read(db, fix.actor)
    candidates = [row for row in result.actions if row.source == 'receivables']
    assert len(candidates) == (0 if kind == 'foreign_marker' else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['actor_inactive', 'actor_deleted', 'tenant_inactive', 'tenant_deleted'])
async def test_inactive_deleted_actor_and_tenant_denied(db_session, change):
    fix = await fixture(db_session)
    if change == 'actor_inactive':
        fix.actor.is_active = False
    elif change == 'actor_deleted':
        fix.actor.deleted_at = T
    elif change == 'tenant_inactive':
        fix.tenant.is_active = False
    else:
        fix.tenant.deleted_at = T
    await db_session.commit()
    with pytest.raises(HTTPException) as error:
        await read(db_session, fix.actor)
    assert error.value.status_code == 403
