from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.api.v1.endpoints import customers, vehicles
from app.core.dependencies import get_current_active_user
from app.db.models.user import UserRole
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import VehicleCustomerRelationship
from app.main import app


@pytest_asyncio.fixture
async def edit_case(db_session, monkeypatch):
    from test_service_checklists import seed
    a = await seed(db_session)
    a.vehicle.vin = '1M8GDM9AXKP042788'
    a.vehicle.unit_number = '603'
    a.vehicle.license_plate = 'OLD'
    a.vehicle.equipment_type = 'tractor'
    a.vehicle.nhtsa_decoded_at = datetime.now(UTC)
    await db_session.commit()
    a.actor = SimpleNamespace(id=uuid4(), role=UserRole.CUSTOMER, tenant_id=a.tenant.id, customer_id=a.customer.id)
    a.lookup = AsyncMock()
    monkeypatch.setattr(customers, 'sync_vehicle_nhtsa_snapshot', a.lookup)
    monkeypatch.setattr(vehicles, 'sync_vehicle_nhtsa_snapshot', a.lookup)
    app.dependency_overrides[get_current_active_user] = lambda: a.actor
    try:
        yield a
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)


def url(a, route):
    return f'/api/v1/customers/{a.customer.id}/vehicles/{a.vehicle.id}' if route == 'nested' else f'/api/v1/vehicles/{a.vehicle.id}'


async def send(client, a, route, payload):
    return await getattr(client, 'put' if route == 'nested' else 'patch')(url(a, route), json=payload)


@pytest.mark.asyncio
@pytest.mark.parametrize('route', ['nested', 'direct'])
async def test_customer_can_update_labels_without_changing_identity(client, db_session, edit_case, route):
    a = edit_case
    response = await send(client, a, route, {'unit_number': 'NEW-603', 'license_plate': 'NEW', 'color': 'Blue', 'notes': 'Customer note'})
    assert response.status_code == 200, response.text
    await db_session.refresh(a.vehicle)
    assert (a.vehicle.unit_number, a.vehicle.license_plate, a.vehicle.color, a.vehicle.notes) == ('NEW-603', 'NEW', 'Blue', 'Customer note')
    assert a.vehicle.vin == '1M8GDM9AXKP042788' and a.vehicle.equipment_type == 'tractor'
    assert a.vehicle.customer_id == a.customer.id
    a.lookup.assert_not_awaited()
    cleared = await send(client, a, route, {'license_plate': None})
    assert cleared.status_code == 200
    await db_session.refresh(a.vehicle)
    assert a.vehicle.license_plate is None and a.vehicle.unit_number == 'NEW-603'


@pytest.mark.asyncio
@pytest.mark.parametrize('route', ['nested', 'direct'])
@pytest.mark.parametrize('forbidden', [
    {'vin': '1M8GDM9AXKP042788'}, {'vin': '1M8GDM9AXKP042789'}, {'vin': None},
    {'make': 'Other'}, {'model': 'Other'}, {'year': 2025}, {'mileage': 900},
    {'equipment_type': 'trailer'}, {'customer_id': str(uuid4())}, {'tenant_id': str(uuid4())},
    {'driver_name': 'Other'}, {'unknown_field': 'value'},
])
async def test_customer_protected_field_requests_fail_atomically(client, db_session, edit_case, route, forbidden):
    a = edit_case
    before = dict((await db_session.execute(select(Vehicle.__table__).where(Vehicle.id == a.vehicle.id))).mappings().one())
    response = await send(client, a, route, {'license_plate': 'SHOULD-NOT-SAVE', **forbidden})
    assert response.status_code == 422, response.text
    await db_session.refresh(a.vehicle)
    assert dict((await db_session.execute(select(Vehicle.__table__).where(Vehicle.id == a.vehicle.id))).mappings().one()) == before
    a.lookup.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('route', ['nested', 'direct'])
@pytest.mark.parametrize('payload', [{'unit_number': 'x'*51}, {'license_plate': 'x'*21}, {'color': 'x'*51}])
async def test_customer_label_lengths_are_validated(client, edit_case, route, payload):
    assert (await send(client, edit_case, route, payload)).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize('route', ['nested', 'direct'])
@pytest.mark.parametrize('boundary', ['customer', 'tenant', 'missing_customer', 'driver', 'deleted_vehicle', 'deleted_customer', 'fleet_manager'])
async def test_customer_vehicle_update_access_boundaries(client, db_session, edit_case, route, boundary):
    a = edit_case
    if boundary == 'customer': a.actor.customer_id = uuid4()
    elif boundary == 'tenant': a.actor.tenant_id = uuid4()
    elif boundary == 'missing_customer': a.actor.customer_id = None
    elif boundary == 'driver': a.actor.role = UserRole.DRIVER
    elif boundary == 'deleted_vehicle': a.vehicle.deleted_at = datetime.now(UTC)
    elif boundary == 'deleted_customer': a.customer.deleted_at = datetime.now(UTC)
    elif boundary == 'fleet_manager': a.actor.role = UserRole.FLEET_MANAGER
    await db_session.commit()
    response = await send(client, a, route, {'license_plate': 'SHOULD-NOT-SAVE'})
    assert response.status_code in (403, 404), response.text
    await db_session.refresh(a.vehicle)
    assert a.vehicle.license_plate == 'OLD'


@pytest.mark.asyncio
@pytest.mark.parametrize('relationship', ['owner', 'operator', 'default_payer', 'ended', 'deleted', 'foreign'])
async def test_nested_customer_vehicle_link_boundaries(client, db_session, edit_case, relationship):
    from app.db.models.customer import Customer
    a = edit_case
    linked = Customer(id=uuid4(), tenant_id=a.tenant.id, first_name='Linked', last_name='Account', email=f'{uuid4()}@example.invalid')
    db_session.add(linked)
    await db_session.flush()
    link = VehicleCustomerRelationship(tenant_id=uuid4() if relationship == 'foreign' else a.tenant.id,
        vehicle_id=a.vehicle.id, customer_id=linked.id,
        relationship_type=relationship if relationship in ('owner', 'operator', 'default_payer') else 'operator',
        effective_to=datetime.now(UTC) if relationship == 'ended' else None,
        deleted_at=datetime.now(UTC) if relationship == 'deleted' else None)
    db_session.add(link)
    await db_session.commit()
    a.customer = linked
    a.actor.customer_id = linked.id
    response = await send(client, a, 'nested', {'license_plate': 'LINKED'})
    assert response.status_code == (200 if relationship in ('owner', 'operator') else 404), response.text
    if relationship in ('owner', 'operator'):
        direct = await send(client, a, 'direct', {'license_plate': 'DIRECT'})
        assert direct.status_code in (403, 404)


@pytest.mark.asyncio
@pytest.mark.parametrize('route', ['staff', 'nested'])
async def test_authorized_staff_can_still_correct_vin(client, edit_case, route):
    a = edit_case
    a.actor = a.owner
    target = f'/api/v1/vehicles/{a.vehicle.id}' if route == 'staff' else url(a, 'nested')
    response = await client.put(target, json={'vin': '1m8gdm9axkp042789'})
    assert response.status_code == 200, response.text
    assert response.json()['vin'] == '1M8GDM9AXKP042789'
    a.lookup.assert_awaited_once()
