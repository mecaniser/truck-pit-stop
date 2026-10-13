from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.models.customer import Customer
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.invoice_settlement import InvoiceSettlement
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.labor import Labor
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.recommended_service import RecommendedService, RecommendedServicePriority
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.user_customer_link import UserCustomerLink
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership, VehicleCustomerRelationship

PATH = '/api/v1/repair-orders/recommended-work'
NOW = datetime.now(timezone.utc)


def headers(user):
    return {'Authorization': f"Bearer {create_access_token({'sub': str(user.id)})}"}


async def customer(db, tenant, **values):
    row = Customer(tenant_id=tenant.id, first_name='Private payer', last_name='Old', email=f'{uuid4()}@example.com', **values)
    db.add(row)
    await db.flush()
    return row


async def vehicle(db, tenant, payer, **values):
    row = Vehicle(tenant_id=tenant.id, customer_id=payer.id, vin='1FUJGLDR9CSBD1234', unit_number='031', make='Freightliner', model='Cascadia', **values)
    db.add(row)
    await db.flush()
    return row


async def order(db, tenant, payer, truck, **values):
    row = RepairOrder(tenant_id=tenant.id, customer_id=payer.id, vehicle_id=truck.id, order_number=f'RO-{uuid4().hex}', **values)
    db.add(row)
    await db.flush()
    return row


async def recommendation(db, tenant, source, **values):
    values.setdefault('description', 'Inspect wheel seal')
    values.setdefault('priority', RecommendedServicePriority.SOON)
    values.setdefault('created_at', NOW)
    row = RecommendedService(tenant_id=tenant.id, repair_order_id=source.id, notes='Private notes', estimated_cost=Decimal('123.45'), **values)
    db.add(row)
    await db.flush()
    return row


async def actor(db, tenant, role):
    row = User(tenant_id=tenant.id if tenant else None, email=f'{uuid4()}@example.com', hashed_password='hashed', first_name='Staff', last_name='User', role=role, is_active=True, is_verified=True)
    db.add(row)
    await db.flush()
    return row


@pytest_asyncio.fixture
async def fixture(db_session):
    db = db_session
    a, b = [Tenant(name=name, slug=f'{name}-{uuid4().hex}') for name in ('actor', 'foreign')]
    db.add_all([a, b])
    await db.flush()
    old, new, foreign = await customer(db, a), await customer(db, a), await customer(db, b)
    x, y, foreign_truck = await vehicle(db, a, old), await vehicle(db, a, old), await vehicle(db, b, foreign)
    source = await order(db, a, old, x, status=RepairOrderStatus.PAID)
    context = await order(db, a, new, x)
    foreign_order = await order(db, b, foreign, foreign_truck)
    rec = await recommendation(db, a, source)
    current_rec = await recommendation(db, a, context)
    owner = await actor(db, a, UserRole.GARAGE_OWNER)
    for relationship in ('owner', 'operator'):
        db.add(VehicleCustomerRelationship(tenant_id=a.id, vehicle_id=x.id, customer_id=new.id, relationship_type=relationship, effective_from=NOW-timedelta(days=1)))
    await db.commit()
    return dict(a=a, b=b, old=old, new=new, foreign=foreign, x=x, y=y, foreign_truck=foreign_truck, source=source, context=context, foreign_order=foreign_order, rec=rec, current_rec=current_rec, owner=owner)


async def get(client, f, **params):
    return await client.get(PATH, headers=headers(f['owner']), params={key: str(value) for key, value in params.items()})


async def snapshot(db):
    await db.rollback()
    db.expire_all()
    result = []
    for model in (RecommendedService, RepairOrder, Vehicle, Customer, Labor, PartsUsage, Inventory, Invoice, InvoiceSettlement, ProviderOutboxEvent, RepairOrderHistoryEvent):
        rows = (await db.execute(select(model).order_by(model.id))).scalars().all()
        result.append((model.__tablename__, tuple(tuple((c.name, repr(getattr(row, c.name))) for c in model.__table__.columns) for row in rows)))
    return tuple(result)


@pytest.mark.asyncio
async def test_technical_continuity_reduced_payload_and_no_side_effects(client, db_session, fixture, monkeypatch):
    from app.api.v1.endpoints import repair_orders
    f = fixture
    events = []
    async def capture(**event):
        events.append(event)
    monkeypatch.setattr(repair_orders, 'broadcast_repair_order_update', capture)
    inventory = Inventory(tenant_id=f['a'].id, sku='SEALED-PART', name='Seal', stock_quantity=7, cost=10, selling_price=20)
    invoice = Invoice(tenant_id=f['a'].id, repair_order_id=f['source'].id, billed_customer_id=f['old'].id, invoice_number=f'INV-{uuid4()}', status=InvoiceStatus.PAID, subtotal=120, total_amount=120)
    db_session.add_all([inventory, invoice])
    await db_session.flush()
    db_session.add_all([
        Labor(tenant_id=f['a'].id, repair_order_id=f['source'].id, description='Existing work', hours=1, hourly_rate=100, total_cost=100),
        PartsUsage(tenant_id=f['a'].id, repair_order_id=f['source'].id, inventory_id=inventory.id, quantity=1, unit_cost=10, unit_price=20, total_price=20),
        InvoiceSettlement(tenant_id=f['a'].id, invoice_id=invoice.id, customer_id=f['old'].id, principal_total=120, confirmed_principal=120, state='paid'),
    ])
    db_session.add(ProviderOutboxEvent(tenant_id=f['a'].id, event_type='boundary.seed', aggregate_type='repair_order', aggregate_id=f['source'].id, payload={'private': 'seed'}, idempotency_key=f'db099:{uuid4()}', status='pending', attempt_count=0, available_at=NOW))
    await db_session.commit()
    params = dict(vehicle_id=f['x'].id, customer_id=f['new'].id, context_order_id=f['context'].id)
    expected_id, source_id, payer_id = str(f['rec'].id), str(f['source'].id), str(f['old'].id)
    auth = headers(f['owner'])
    before = await snapshot(db_session)
    for _ in range(2):
        response = await client.get(PATH, headers=auth, params={k: str(v) for k, v in params.items()})
        assert response.status_code == 200, response.text
        assert 'no-store' in response.headers['cache-control'].split(', ')
        page = response.json()
        assert (page['total'], page['skip'], page['limit']) == (1, 0, 25)
        row = page['items'][0]
        assert row['id'] == expected_id and row['source_order']['id'] == source_id
        assert set(row) == {'id', 'description', 'priority', 'created_at', 'vehicle', 'source_order'}
        assert set(row['vehicle']) == {'id', 'unit_number', 'year', 'make', 'model'}
        assert set(row['source_order']) == {'id', 'order_number', 'status', 'created_at'}
        assert payer_id not in response.text and '123.45' not in response.text and 'Private' not in response.text
    source_response = await client.get(f'/api/v1/repair-orders/{source_id}/workspace', headers=auth)
    assert source_response.status_code == 200, source_response.text
    assert await snapshot(db_session) == before
    assert not events


@pytest.mark.asyncio
@pytest.mark.parametrize('role', list(UserRole))
async def test_role_allowlist_even_context_assigned_mechanic(client, db_session, fixture, role):
    f = fixture
    user = await actor(db_session, f['a'], role)
    f['context'].assigned_mechanic_id = user.id
    if role == UserRole.CUSTOMER:
        db_session.add_all([UserCustomerLink(user_id=user.id, tenant_id=f['a'].id, customer_id=f['new'].id), UserCustomerLink(user_id=user.id, tenant_id=f['b'].id, customer_id=f['foreign'].id)])
    await db_session.commit()
    response = await client.get(PATH, headers=headers(user), params={'vehicle_id': str(f['x'].id), 'context_order_id': str(f['context'].id)})
    if role in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST):
        assert response.status_code == 200
    else:
        assert response.status_code == 403
        assert response.json()['detail'] == 'Access denied'


@pytest.mark.asyncio
async def test_auth_and_missing_tenant(client, db_session):
    assert (await client.get(PATH)).status_code == 401
    user = await actor(db_session, None, UserRole.GARAGE_OWNER)
    await db_session.commit()
    response = await client.get(PATH, headers=headers(user))
    assert response.status_code == 400
    assert response.json()['detail'] == 'User must be associated with a tenant'


@pytest.mark.asyncio
async def test_exact_vehicle_and_all_malformed_source_joins(client, db_session, fixture):
    f = fixture
    # Same VIN/unit is never an alias. Foreign and malformed tenant links are hidden.
    y_order = await order(db_session, f['a'], f['old'], f['y'])
    await recommendation(db_session, f['a'], y_order)
    await recommendation(db_session, f['b'], f['source'])
    await recommendation(db_session, f['a'], f['foreign_order'])
    bad_vehicle = await order(db_session, f['a'], f['old'], f['foreign_truck'])
    bad_customer = await order(db_session, f['a'], f['foreign'], f['x'])
    for source in (bad_vehicle, bad_customer):
        await recommendation(db_session, f['a'], source)
    await db_session.commit()
    response = await get(client, f, vehicle_id=f['x'].id, context_order_id=f['context'].id)
    assert [row['id'] for row in response.json()['items']] == [str(f['rec'].id)]
    shop = (await get(client, f)).json()
    assert shop['total'] == 3


@pytest.mark.asyncio
async def test_deleted_resolved_cancelled_suppressed_and_final_sources_eligible(client, db_session, fixture):
    f = fixture
    for values in ({'is_resolved': True}, {'resolved_by_repair_order_id': f['context'].id}, {'deleted_at': NOW}):
        await recommendation(db_session, f['a'], f['source'], **values)
    for values in ({'status': RepairOrderStatus.CANCELLED}, {'deleted_at': NOW}):
        source = await order(db_session, f['a'], f['old'], f['x'], **values)
        await recommendation(db_session, f['a'], source)
    deleted_customer = await customer(db_session, f['a'], deleted_at=NOW)
    deleted_vehicle = await vehicle(db_session, f['a'], f['old'], deleted_at=NOW)
    for payer, truck in ((deleted_customer, f['x']), (f['old'], deleted_vehicle)):
        source = await order(db_session, f['a'], payer, truck)
        await recommendation(db_session, f['a'], source)
    valid_ids = {str(f['rec'].id), str(f['current_rec'].id)}
    for status in (RepairOrderStatus.COMPLETED, RepairOrderStatus.DECLINED, RepairOrderStatus.INVOICED):
        source = await order(db_session, f['a'], f['old'], f['x'], status=status)
        valid_ids.add(str((await recommendation(db_session, f['a'], source)).id))
    await db_session.commit()
    page = (await get(client, f)).json()
    assert page['total'] == len(valid_ids)
    assert {row['id'] for row in page['items']} == valid_ids


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['ended', 'future', 'default_payer', 'deleted', 'foreign', 'fleet', 'owner', 'operator', 'legacy'])
async def test_current_customer_relationship_rules(client, db_session, fixture, kind):
    f = fixture
    payer = await customer(db_session, f['a'])
    values = dict(tenant_id=f['a'].id, vehicle_id=f['x'].id, customer_id=payer.id, relationship_type='owner', effective_from=NOW-timedelta(days=1))
    if kind == 'ended': values['effective_to'] = NOW
    if kind == 'future': values['effective_from'] = NOW+timedelta(days=1)
    if kind == 'default_payer': values['relationship_type'] = 'default_payer'
    if kind == 'deleted': values['deleted_at'] = NOW
    if kind == 'foreign': values['tenant_id'] = f['b'].id
    if kind == 'operator': values['relationship_type'] = 'operator'
    if kind == 'legacy': f['x'].customer_id = payer.id
    elif kind == 'fleet': db_session.add(FleetMembership(tenant_id=f['a'].id, vehicle_id=f['x'].id, fleet_customer_id=payer.id, effective_from=NOW-timedelta(days=1)))
    else: db_session.add(VehicleCustomerRelationship(**values))
    await db_session.commit()
    allowed = kind in ('owner', 'operator', 'legacy')
    response = await get(client, f, vehicle_id=f['x'].id, customer_id=payer.id, context_order_id=f['context'].id)
    assert response.status_code == (200 if allowed else 404)
    page = (await get(client, f, customer_id=payer.id, context_order_id=f['context'].id, vehicle_id=f['x'].id)).json() if allowed else (await get(client, f, customer_id=payer.id)).json()
    assert page['total'] == (1 if allowed else 0)


@pytest.mark.asyncio
async def test_invalid_contexts_are_indistinguishable(client, db_session, fixture):
    f = fixture
    deleted_customer = await customer(db_session, f['a'], deleted_at=NOW)
    deleted_truck = await vehicle(db_session, f['a'], f['old'], deleted_at=NOW)
    deleted_order = await order(db_session, f['a'], f['old'], f['x'], deleted_at=NOW)
    cancelled_order = await order(db_session, f['a'], f['old'], f['x'], status=RepairOrderStatus.CANCELLED)
    await db_session.commit()
    cases = [
        {'vehicle_id': value} for value in (uuid4(), f['foreign_truck'].id, deleted_truck.id)
    ] + [
        {'customer_id': value} for value in (uuid4(), f['foreign'].id, deleted_customer.id)
    ] + [
        {'vehicle_id': f['x'].id, 'context_order_id': value} for value in (uuid4(), f['foreign_order'].id, deleted_order.id, cancelled_order.id)
    ] + [
        {'vehicle_id': f['y'].id, 'context_order_id': f['context'].id},
        {'vehicle_id': f['y'].id, 'customer_id': f['new'].id},
    ]
    for params in cases:
        response = await get(client, f, **params)
        assert response.status_code == 404, (params, response.text)
        assert response.json()['detail'] == 'Recommended work context not found'


@pytest.mark.asyncio
@pytest.mark.parametrize('params', [{'vehicle_id': 'bad'}, {'customer_id': 'bad'}, {'context_order_id': 'bad'}, {'context_order_id': str(uuid4())}, {'skip': -1}, {'skip': 'bad'}, {'limit': 0}, {'limit': 101}])
async def test_query_validation(client, fixture, params):
    assert (await get(client, fixture, **params)).status_code == 422


@pytest.mark.asyncio
async def test_stable_priority_date_id_pages_and_empty_context(client, db_session, fixture):
    f = fixture
    expected = [(1, NOW, f['rec'].id)]
    for index in range(31):
        priority = list(RecommendedServicePriority)[index % 3]
        recorded = NOW - timedelta(days=index % 2)
        rec = await recommendation(db_session, f['a'], f['source'], id=UUID(int=index+1), priority=priority, created_at=recorded)
        expected.append((index % 3, recorded, rec.id))
    await db_session.commit()
    base = dict(vehicle_id=f['x'].id, context_order_id=f['context'].id)
    collected = []
    for skip in (0, 25, 50):
        page = (await get(client, f, **base, skip=skip)).json()
        assert page['total'] == 32 and page['skip'] == skip and page['limit'] == 25
        assert len(page['items']) == {0:25, 25:7, 50:0}[skip]
        collected += [row['id'] for row in page['items']]
    assert collected == [str(item[2]) for item in sorted(expected)]
    empty = (await get(client, f, vehicle_id=f['y'].id)).json()
    assert empty == {'items': [], 'total': 0, 'skip': 0, 'limit': 25}
