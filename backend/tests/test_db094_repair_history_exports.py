import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import Response
from sqlalchemy import select

from app.api.v1.endpoints import fleet_invoice_exports as invoices
from app.api.v1.endpoints import fleet_repair_history_exports as history
from app.db.models.customer import Customer
from app.db.models.fleet_invoice_api_key import FleetInvoiceApiKey
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder
from app.db.models.vehicle import Vehicle
from app.db.models.repair_order import RepairOrderStatus
from tests.test_db094_fleet_invoice_exports import _seed

PATH = '/api/v1/fleet-invoice-exports/repair-orders'


@pytest.mark.asyncio
async def test_completed_history_returns_service_date_without_invoice_amounts(client, db_session):
    owner, customer, invoice, vehicle = await _seed(db_session, f'history-{uuid4().hex}')
    order = invoice.repair_order
    order.status = RepairOrderStatus.PAID
    order.description = 'Customer-visible engine service'
    order.work_completed_at = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
    await db_session.commit()
    created = await invoices.create_key(invoices.KeyRequest(customer_id=customer.id, name='Elis history'), Response(), db=db_session, user=owner)
    response = await client.get(PATH, headers={'X-API-Key': created['api_key']})
    assert response.status_code == 200, response.text
    item = response.json()['items'][0]
    assert item['service_date'] == '2026-10-08'
    assert 'total_amount' not in item

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


async def seed_history(db):
    owner, customer, invoice, vehicle = await _seed(db, f'history-{uuid4().hex}')
    order = invoice.repair_order
    order.status = RepairOrderStatus.PAID
    order.work_completed_at = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
    await db.commit()
    key = await invoices.create_key(invoices.KeyRequest(customer_id=customer.id, name='Elis operational history'), Response(), db=db, user=owner)
    return owner, customer, invoice, vehicle, key


@pytest.mark.asyncio
async def test_complete_fifteen_ro_snapshot_covers_null_bill_to_without_duplicate_invoice_versions(client, db_session):
    owner, customer, first_invoice, first_vehicle, key = await seed_history(db_session)
    first_vehicle.unit_number = '603'
    second_vehicle = Vehicle(tenant_id=owner.tenant_id, customer_id=customer.id,
                             vin='1M8GDM9AXKP042788', unit_number='609', make='Volvo', model='VNL')
    db_session.add(second_vehicle); await db_session.flush()
    orders = [first_invoice.repair_order]
    for index in range(1, 15):
        order = RepairOrder(tenant_id=owner.tenant_id, customer_id=customer.id,
                            vehicle_id=first_vehicle.id if index < 6 else second_vehicle.id,
                            order_number=f'RO-{uuid4().hex}', status=RepairOrderStatus.PAID,
                            work_completed_at=datetime(2026, 10, 1, 12, tzinfo=timezone.utc))
        db_session.add(order); await db_session.flush(); orders.append(order)
        db_session.add(Invoice(tenant_id=owner.tenant_id, repair_order_id=order.id,
                               billed_customer_id=customer.id if index < 7 else None,
                               invoice_number=f'INV-{uuid4().hex}', status=InvoiceStatus.PAID,
                               subtotal=Decimal('100'), tax_amount=Decimal('0'),
                               discount_amount=Decimal('0'), total_amount=Decimal('100')))
    # An additional invoice revision must not create a sixteenth service record.
    db_session.add(Invoice(tenant_id=owner.tenant_id, repair_order_id=first_invoice.repair_order_id,
                           billed_customer_id=customer.id, invoice_number=f'OLD-{uuid4().hex}',
                           status=InvoiceStatus.CANCELLED, subtotal=Decimal('100'),
                           tax_amount=Decimal('0'), discount_amount=Decimal('0'), total_amount=Decimal('100')))
    await db_session.commit()
    response = await client.get(PATH, headers={'X-API-Key': key['api_key']})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['complete'] is True and result['count'] == 15
    assert len({i['repair_order_id'] for i in result['items']}) == 15
    assert sum(i['unit_number'] == '603' for i in result['items']) == 6
    assert sum(i['unit_number'] == '609' for i in result['items']) == 9


@pytest.mark.asyncio
async def test_history_read_does_not_grant_historical_invoice_or_pdf_access(client, db_session):
    _owner, _customer, invoice, _vehicle, key = await seed_history(db_session)
    invoice.billed_customer_id = None
    await db_session.commit()
    headers = {'X-API-Key': key['api_key']}
    assert (await client.get(PATH, headers=headers)).json()['count'] == 1
    result = await client.get('/api/v1/fleet-invoice-exports/invoices', headers=headers,
                              params={'updated_since':'1970-01-01T00:00:00Z',
                                      'updated_before':datetime.now(timezone.utc).isoformat()})
    assert result.status_code == 200 and result.json()['items'] == []
    pdf = await client.get(f'/api/v1/fleet-invoice-exports/invoices/{invoice.id}/pdf', headers=headers)
    assert pdf.status_code == 404
    await db_session.refresh(invoice)
    assert invoice.billed_customer_id is None


@pytest.mark.asyncio
async def test_private_fields_never_enter_metadata_payload(client, db_session):
    _owner, _customer, invoice, _vehicle, key = await seed_history(db_session)
    order = invoice.repair_order
    order.description = 'Public work — contrôle'
    order.internal_notes = 'PRIVATE-INTERNAL-MARKER'
    order.shop_notes = 'PRIVATE-SHOP-MARKER'
    order.customer_notes = 'PRIVATE-CUSTOMER-MARKER'
    order.utm_source = 'PRIVATE-ATTRIBUTION-MARKER'
    await db_session.commit()
    response = await client.get(PATH, headers={'X-API-Key':key['api_key']})
    assert response.status_code == 200
    item = response.json()['items'][0]
    assert set(item) == {'repair_order_id','order_number','vehicle_id','vin','unit_number','status','description','created_at','work_completed_at','service_date','service_date_source','revision'}
    assert item['description'] == 'Public work — contrôle'
    assert 'PRIVATE-' not in response.text
    assert {'private', 'no-store'} <= {v.strip() for v in response.headers['cache-control'].split(',')}


@pytest.mark.asyncio
async def test_scope_excludes_other_tenant_and_other_customer_on_same_vin(client, db_session):
    owner, customer, invoice, vehicle, key = await seed_history(db_session)
    other = Customer(tenant_id=owner.tenant_id, first_name='Other', last_name='Customer', email=f'{uuid4().hex}@example.com')
    db_session.add(other); await db_session.flush()
    db_session.add(RepairOrder(tenant_id=owner.tenant_id, customer_id=other.id, vehicle_id=vehicle.id,
                               order_number=f'RO-{uuid4().hex}', status=RepairOrderStatus.PAID))
    _owner2, _customer2, foreign, foreign_vehicle = await _seed(db_session, f'foreign-{uuid4().hex}')
    foreign.repair_order.status = RepairOrderStatus.PAID
    foreign_vehicle.vin = vehicle.vin
    await db_session.commit()
    result = await client.get(PATH, headers={'X-API-Key':key['api_key']})
    assert [i['repair_order_id'] for i in result.json()['items']] == [str(invoice.repair_order_id)]


@pytest.mark.asyncio
async def test_vehicle_tenant_mismatch_is_excluded(client, db_session):
    _owner, _customer, invoice, _vehicle, key = await seed_history(db_session)
    _owner2, _customer2, _foreign, foreign_vehicle = await _seed(db_session, f'foreign-{uuid4().hex}')
    invoice.repair_order.vehicle_id = foreign_vehicle.id
    await db_session.commit()
    assert (await client.get(PATH, headers={'X-API-Key':key['api_key']})).json()['count'] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [RepairOrderStatus.DRAFT, RepairOrderStatus.IN_PROGRESS, RepairOrderStatus.CANCELLED])
async def test_incomplete_or_cancelled_ro_is_excluded(client, db_session, status):
    _owner, _customer, invoice, _vehicle, key = await seed_history(db_session)
    invoice.repair_order.status = status
    await db_session.commit()
    assert (await client.get(PATH, headers={'X-API-Key':key['api_key']})).json()['count'] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [RepairOrderStatus.COMPLETED, RepairOrderStatus.INVOICED, RepairOrderStatus.PAID])
async def test_all_completed_workflow_statuses_qualify(client, db_session, status):
    _owner, _customer, invoice, _vehicle, key = await seed_history(db_session)
    invoice.repair_order.status = status
    await db_session.commit()
    assert (await client.get(PATH, headers={'X-API-Key':key['api_key']})).json()['count'] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['internal','deleted'])
async def test_internal_and_deleted_ros_are_excluded(client, db_session, change):
    _owner, _customer, invoice, _vehicle, key = await seed_history(db_session)
    if change == 'internal': invoice.repair_order.is_internal = True
    else: invoice.repair_order.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()
    assert (await client.get(PATH, headers={'X-API-Key':key['api_key']})).json()['count'] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['revoked_key','inactive_shop','deleted_customer'])
async def test_key_revocation_and_inactive_scope_fail_closed(client, db_session, change):
    owner, customer, _invoice, _vehicle, key = await seed_history(db_session)
    if change == 'revoked_key':
        row = (await db_session.execute(select(FleetInvoiceApiKey).where(FleetInvoiceApiKey.id == key['id']))).scalar_one()
        row.revoked_at = datetime.now(timezone.utc)
    elif change == 'inactive_shop': owner.tenant.is_active = False
    else: customer.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()
    assert (await client.get(PATH, headers={'X-API-Key':key['api_key']})).status_code == 401


@pytest.mark.asyncio
async def test_missing_and_invalid_key_are_rejected(client):
    assert (await client.get(PATH)).status_code == 401
    assert (await client.get(PATH, headers={'X-API-Key':'not-a-credential'})).status_code == 401


@pytest.mark.asyncio
async def test_created_date_fallback_is_explicit_and_utc_normalized(client, db_session):
    _owner, _customer, invoice, _vehicle, key = await seed_history(db_session)
    order = invoice.repair_order
    order.work_completed_at = None
    order.created_at = datetime(2026, 7, 4, 13, tzinfo=timezone.utc)
    await db_session.commit()
    item = (await client.get(PATH, headers={'X-API-Key':key['api_key']})).json()['items'][0]
    assert item['service_date'] == '2026-07-04'
    assert item['service_date_source'] == 'created_at_fallback'
    assert item['created_at'] == '2026-07-04T13:00:00+00:00'
    assert item['work_completed_at'] is None


@pytest.mark.asyncio
async def test_snapshot_and_unicode_item_hashes_are_stable_and_change_with_source_revision(client, db_session):
    _owner, _customer, invoice, _vehicle, key = await seed_history(db_session)
    invoice.repair_order.description = 'Service — contrôle'
    await db_session.commit()
    headers = {'X-API-Key':key['api_key']}
    first = (await client.get(PATH, headers=headers)).json()
    second = (await client.get(PATH, headers=headers)).json()
    assert first == second
    item = dict(first['items'][0]); revision = item.pop('revision')
    assert revision == digest(item)
    assert first['snapshot_id'] == digest({k:first[k] for k in ('version','shop_id','customer_id','items')})
    invoice.repair_order.description = 'Revised customer-visible service'
    await db_session.commit()
    third = (await client.get(PATH, headers=headers)).json()
    assert third['snapshot_id'] != first['snapshot_id']
    assert third['items'][0]['revision'] != revision


@pytest.mark.asyncio
async def test_oversize_snapshot_is_rejected_without_partial_items(client, db_session, monkeypatch):
    owner, customer, _invoice, vehicle, key = await seed_history(db_session)
    for _ in range(2):
        db_session.add(RepairOrder(tenant_id=owner.tenant_id, customer_id=customer.id, vehicle_id=vehicle.id,
                                   order_number=f'RO-{uuid4().hex}', status=RepairOrderStatus.PAID))
    await db_session.commit()
    monkeypatch.setattr(history, 'MAX_REPAIR_HISTORY_ROWS', 2)
    response = await client.get(PATH, headers={'X-API-Key':key['api_key']})
    assert response.status_code == 409
    assert response.json()['detail']['code'] == 'repair_history_snapshot_too_large'
    assert 'items' not in response.json()


@pytest.mark.asyncio
async def test_query_selectors_and_partial_filters_are_rejected(client, db_session):
    _owner, _customer, _invoice, _vehicle, key = await seed_history(db_session)
    response = await client.get(PATH, headers={'X-API-Key':key['api_key']}, params={'customer_id':str(uuid4())})
    assert response.status_code == 422


def test_timestamp_normalization_preserves_utc_date_boundary():
    local = datetime(2026, 10, 9, 1, tzinfo=timezone(timedelta(hours=3)))
    assert history._utc(local).isoformat() == '2026-10-08T22:00:00+00:00'


@pytest.mark.asyncio
async def test_vehicle_identity_correction_changes_revision_without_new_ro_identity(client, db_session):
    _owner, _customer, invoice, vehicle, key = await seed_history(db_session)
    headers = {'X-API-Key':key['api_key']}
    first = (await client.get(PATH, headers=headers)).json()['items'][0]
    vehicle.vin = '1M8GDM9AXKP042788'
    await db_session.commit()
    second = (await client.get(PATH, headers=headers)).json()['items'][0]
    assert second['repair_order_id'] == first['repair_order_id']
    assert second['revision'] != first['revision']


@pytest.mark.asyncio
async def test_operational_scope_is_not_inferred_from_current_vehicle_owner(client, db_session):
    owner, customer, invoice, vehicle, key = await seed_history(db_session)
    other = Customer(tenant_id=owner.tenant_id, first_name='New', last_name='Vehicle owner', email=f'{uuid4().hex}@example.com')
    db_session.add(other); await db_session.flush()
    vehicle.customer_id = other.id
    await db_session.commit()
    response = await client.get(PATH, headers={'X-API-Key':key['api_key']})
    assert [i['repair_order_id'] for i in response.json()['items']] == [str(invoice.repair_order_id)]
