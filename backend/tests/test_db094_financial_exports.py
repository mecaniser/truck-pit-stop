"""Current financial authority is separate from operational RO visibility."""
from decimal import Decimal
from uuid import uuid4
import pytest
from app.db.models.invoice import Invoice,InvoiceStatus
from tests.test_db094_repair_history_exports import seed_history
PATH='/api/v1/fleet-invoice-exports/repair-orders/financial'

@pytest.mark.asyncio
async def test_financial_manifest_uses_service_completion_and_authorized_current_invoice(client,db_session):
    _owner,_customer,invoice,_vehicle,key=await seed_history(db_session)
    response=await client.get(PATH,headers={'X-API-Key':key['api_key']})
    assert response.status_code==200,response.text
    body=response.json();row=body['items'][0]
    assert body['complete'] is True and body['count']==1
    assert row['authorization']=='authorized'
    assert row['invoice']['invoice_id']==str(invoice.id)
    assert row['invoice']['total_amount']=='100.00'
    assert row['service_date']=='2026-10-08'

@pytest.mark.asyncio
async def test_visible_history_does_not_reveal_unattributed_invoice_identity_or_amount(client,db_session):
    _owner,_customer,invoice,_vehicle,key=await seed_history(db_session)
    invoice.billed_customer_id=None
    await db_session.commit()
    response=await client.get(PATH,headers={'X-API-Key':key['api_key']})
    assert response.status_code==200
    row=response.json()['items'][0]
    assert row['authorization']=='attribution_required' and row['invoice'] is None
    assert str(invoice.id) not in response.text and invoice.invoice_number not in response.text
    assert '100.00' not in response.text

@pytest.mark.asyncio
async def test_current_inaccessible_invoice_never_falls_back_to_visible_cancelled_predecessor(client,db_session):
    owner,customer,current,_vehicle,key=await seed_history(db_session)
    current.billed_customer_id=None
    db_session.add(Invoice(tenant_id=owner.tenant_id,repair_order_id=current.repair_order_id,
        billed_customer_id=customer.id,invoice_number='OLD-'+uuid4().hex,status=InvoiceStatus.CANCELLED,
        subtotal=Decimal('50'),tax_amount=Decimal('0'),discount_amount=Decimal('0'),total_amount=Decimal('50')))
    await db_session.commit()
    response=await client.get(PATH,headers={'X-API-Key':key['api_key']})
    assert response.status_code==200
    assert response.json()['items'][0]['invoice'] is None

@pytest.mark.asyncio
async def test_draft_current_invoice_is_unavailable_not_an_expense(client,db_session):
    _owner,_customer,invoice,_vehicle,key=await seed_history(db_session)
    invoice.status=InvoiceStatus.DRAFT
    await db_session.commit()
    response=await client.get(PATH,headers={'X-API-Key':key['api_key']})
    assert response.status_code==200
    row=response.json()['items'][0]
    assert row['authorization']=='not_finalized' and row['invoice'] is None

@pytest.mark.asyncio
async def test_foreign_tenant_historical_mapping_cannot_authorize_invoice(client,db_session):
    from app.db.models.historical_invoice_export import HistoricalInvoiceMapping
    from tests.test_db094_fleet_invoice_exports import _seed
    _owner,customer,invoice,_vehicle,key=await seed_history(db_session)
    foreign_owner,_customer,_invoice,_v=await _seed(db_session,'other-'+uuid4().hex)
    invoice.billed_customer_id=None
    db_session.add(HistoricalInvoiceMapping(tenant_id=foreign_owner.tenant_id,invoice_id=invoice.id,target_customer_id=customer.id,version=1))
    await db_session.commit()
    response=await client.get(PATH,headers={'X-API-Key':key['api_key']})
    assert response.status_code==200
    row=response.json()['items'][0]
    assert row['authorization']=='attribution_required' and row['invoice'] is None

@pytest.mark.asyncio
async def test_financial_hash_is_stable_when_source_is_marked_paid(client,db_session):
    from datetime import datetime,timezone
    _owner,_customer,invoice,_vehicle,key=await seed_history(db_session)
    headers={'X-API-Key':key['api_key']}
    before=(await client.get(PATH,headers=headers)).json()
    invoice.status=InvoiceStatus.PAID;invoice.paid_at=datetime.now(timezone.utc)
    await db_session.commit()
    after=(await client.get(PATH,headers=headers)).json()
    assert before==after

@pytest.mark.asyncio
async def test_snapshot_hash_and_retail_privacy(client,db_session):
    import hashlib,json
    _owner,_customer,invoice,_vehicle,key=await seed_history(db_session)
    invoice.line_items_snapshot={'labor':[{'description':'Oil change','total_cost':'100.00','mechanic_id':'PRIVATE-MECHANIC','internal_notes':'PRIVATE-NOTE'}],
        'parts':[{'name':'Filter','quantity':'1','unit_price':'10.00','unit_cost':'PRIVATE-COST','supplier':'PRIVATE-SUPPLIER'}],
        'contact_email':'PRIVATE-CONTACT'}
    invoice.repair_order.internal_notes='PRIVATE-RO'
    await db_session.commit()
    response=await client.get(PATH,headers={'X-API-Key':key['api_key']});result=response.json()
    assert 'PRIVATE-' not in response.text
    def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    assert result['snapshot_id']==digest({k:result[k] for k in ('version','shop_id','customer_id','items')})
    row=result['items'][0];inv=row['invoice']
    assert row['revision']==digest({k:v for k,v in row.items() if k not in ('revision','settlement')})
    assert inv['revision']==digest({k:v for k,v in inv.items() if k!='revision'})
    assert 'private' in response.headers['cache-control']

@pytest.mark.asyncio
async def test_imported_invoice_creation_timestamp_is_not_an_issue_date(client,db_session):
    _owner,_customer,invoice,_vehicle,key=await seed_history(db_session)
    invoice.repair_order.source='easy_truck_shop_import';invoice.ets_invoiced_at=None
    invoice.repair_order.work_completed_at=None
    await db_session.commit()
    row=(await client.get(PATH,headers={'X-API-Key':key['api_key']})).json()['items'][0]
    assert row['service_date'] is None
    assert row['invoice']['invoice_date'] is None and row['invoice']['invoice_date_basis']=='unknown'

@pytest.mark.asyncio
async def test_fifteen_current_orders_seven_authorized_eight_attribution_required(client,db_session):
    from app.db.models.repair_order import RepairOrder,RepairOrderStatus
    owner,customer,first,vehicle,key=await seed_history(db_session)
    for n in range(1,15):
        order=RepairOrder(tenant_id=owner.tenant_id,customer_id=customer.id,vehicle_id=vehicle.id,
            order_number='RO-'+uuid4().hex,status=RepairOrderStatus.COMPLETED)
        db_session.add(order);await db_session.flush()
        db_session.add(Invoice(tenant_id=owner.tenant_id,repair_order_id=order.id,billed_customer_id=customer.id if n<7 else None,
            invoice_number='I-'+uuid4().hex,status=InvoiceStatus.SENT,subtotal=Decimal('100'),tax_amount=Decimal('0'),discount_amount=Decimal('0'),total_amount=Decimal('100')))
    await db_session.commit()
    result=(await client.get(PATH,headers={'X-API-Key':key['api_key']})).json()
    assert result['count']==15 and len({i['repair_order_id'] for i in result['items']})==15
    assert sum(i['authorization']=='authorized' for i in result['items'])==7
    assert sum(i['authorization']=='attribution_required' and i['invoice'] is None for i in result['items'])==8

@pytest.mark.asyncio
async def test_revoked_key_and_partial_filters_are_rejected(client,db_session):
    from fastapi import Response
    from app.api.v1.endpoints import fleet_invoice_exports as exports
    owner,_customer,_invoice,_vehicle,key=await seed_history(db_session)
    headers={'X-API-Key':key['api_key']}
    assert (await client.get(PATH,headers=headers,params={'limit':1})).status_code==422
    await exports.revoke_key(key['id'],db=db_session,user=owner)
    assert (await client.get(PATH,headers=headers)).status_code==401
