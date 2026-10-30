"""The manifest transports settlement evidence only within the invoice's granted scope."""
import json
from decimal import Decimal as D
from datetime import datetime,timezone
from uuid import uuid4
import pytest
from sqlalchemy import select
from app.db.models.invoice_settlement import InvoiceSettlement,InvoicePaymentAttempt
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.services.invoice_settlement_service import append_ledger_event
from tests.test_db094_repair_history_exports import seed_history
PATH='/api/v1/fleet-invoice-exports/repair-orders/financial'


async def seed_cash(db):
    owner,customer,invoice,vehicle,key=await seed_history(db)
    invoice.subtotal=D('4844.38');invoice.shop_supplies_amount=D('42');invoice.service_fee_amount=D('171.02');invoice.tax_amount=D('0');invoice.total_amount=D('5057.40')
    s=InvoiceSettlement(tenant_id=owner.tenant_id,invoice_id=invoice.id,customer_id=customer.id,principal_total=D('4886.38'),max_card_fee=D('171.02'),max_card_fee_tax=D('0'),confirmed_principal=D('4886.38'),state='paid')
    db.add(s);await db.flush()
    a=InvoicePaymentAttempt(tenant_id=owner.tenant_id,invoice_id=invoice.id,settlement_id=s.id,customer_id=customer.id,source='staff_cash',rail='cash',provider='manual',state='confirmed',principal_amount=D('4886.38'),received_amount=D('4886.38'),applied_principal_amount=D('4886.38'),provider_charge_amount=D('4886.38'),provider_configuration_version=0,actor_name_snapshot='PRIVATE-ACTOR',subject_type='staff',idempotency_key='cash-'+uuid4().hex,request_hash='a'*64,manual_evidence={'note':'PRIVATE-NOTE'},provider_reference='PRIVATE-REFERENCE',confirmed_at=datetime(2026,9,13,tzinfo=timezone.utc))
    db.add(a);await db.commit()
    return owner,customer,invoice,key,s,a


@pytest.mark.asyncio
async def test_v2_exports_cash_principal_and_quote_separately_without_payment_date(client,db_session):
    _o,_c,invoice,key,s,a=await seed_cash(db_session)
    response=await client.get(PATH,headers={'X-API-Key':key['api_key']});assert response.status_code==200,response.text
    value=response.json();row=value['items'][0]
    assert value['version']=='db094-repair-financial-v2'
    assert row['invoice']['total_amount']=='5057.40' and row['invoice']['breakdown']['shop_supplies_amount']=='42.00'
    assert row['settlement']['principal_total']=='4886.38' and row['settlement']['status']=='available'
    payment=row['settlement']['payments'][0]
    assert payment['rail']=='cash' and payment['gross_received_amount']=='4886.38' and payment['applied_card_fee_amount']=='0.00'
    assert payment['actual_paid_date'] is None and payment['paid_date_basis']=='unknown'
    assert 'PRIVATE-' not in response.text
    await db_session.refresh(invoice);assert invoice.total_amount==D('5057.40')


@pytest.mark.asyncio
async def test_payment_change_has_own_revision_and_never_revises_quote_or_ro(client,db_session):
    _o,_c,_i,key,s,a=await seed_cash(db_session);headers={'X-API-Key':key['api_key']}
    before=(await client.get(PATH,headers=headers)).json()
    a.state='reversed';s.confirmed_principal=D('0');s.state='unpaid';await db_session.commit()
    after=(await client.get(PATH,headers=headers)).json()
    assert before['items'][0]['revision']==after['items'][0]['revision']
    assert before['items'][0]['invoice']==after['items'][0]['invoice']
    assert before['items'][0]['settlement']['revision']!=after['items'][0]['settlement']['revision']
    assert before['snapshot_id']!=after['snapshot_id']
    assert after['items'][0]['settlement']['status']=='review_required'


@pytest.mark.asyncio
async def test_no_grant_leaks_no_settlement_or_payment_ids(client,db_session):
    _o,_c,invoice,key,s,a=await seed_cash(db_session)
    invoice.billed_customer_id=None;await db_session.commit()
    response=await client.get(PATH,headers={'X-API-Key':key['api_key']});row=response.json()['items'][0]
    assert row['invoice'] is None and row['settlement'] is None
    assert str(s.id) not in response.text and str(a.id) not in response.text and '4886.38' not in response.text


@pytest.mark.asyncio
async def test_payment_only_ledger_enqueues_new_wakeup_and_rollback_is_atomic(db_session,monkeypatch):
    owner,customer,invoice,_key,s,a=await seed_cash(db_session)
    monkeypatch.setenv('DIESELBRIDGE_FLEET_WEBHOOKS',json.dumps([{'shop_id':str(owner.tenant_id),'customer_id':str(customer.id),'url':'https://edg.example/api/v1/accounting/dieselbridge/webhooks/shop','secret_env':'TEST_FLEET_WEBHOOK_SECRET'}]))
    await append_ledger_event(db_session,settlement=s,attempt=a,actor=None,event_type='cash_payment_confirmed',idempotency_key='first',principal_delta=D('4886.38'))
    await db_session.commit()
    first=(await db_session.execute(select(ProviderOutboxEvent).where(ProviderOutboxEvent.event_type=='fleet.financial.wakeup.v1'))).scalar_one()
    a.state='reversed';s.confirmed_principal=D('0');s.state='unpaid'
    await append_ledger_event(db_session,settlement=s,attempt=a,actor=None,event_type='payment_reversed',idempotency_key='second',principal_delta=D('-4886.38'))
    await db_session.flush()
    events=(await db_session.execute(select(ProviderOutboxEvent).where(ProviderOutboxEvent.event_type=='fleet.financial.wakeup.v1'))).scalars().all()
    assert len(events)==2 and len({x.idempotency_key for x in events})==2
    assert all(set(x.payload)=={'version','event_id','shop_id','customer_id','repair_order_id','kind','occurred_at'} for x in events)
    assert all(x.payload['kind']=='invoice_changed' for x in events)
    await db_session.rollback()
    events=(await db_session.execute(select(ProviderOutboxEvent).where(ProviderOutboxEvent.event_type=='fleet.financial.wakeup.v1'))).scalars().all()
    assert len(events)==1 and events[0].id==first.id


@pytest.mark.asyncio
async def test_joined_payment_limit_rejects_incomplete_snapshot(client,db_session,monkeypatch):
    from app.api.v1.endpoints import fleet_repair_financial_exports as endpoint
    _o,_c,_invoice,key,s,a=await seed_cash(db_session)
    second=InvoicePaymentAttempt(tenant_id=a.tenant_id,invoice_id=a.invoice_id,settlement_id=s.id,customer_id=a.customer_id,source='staff_cash',rail='cash',provider='manual',state='pending',principal_amount=D('1'),provider_charge_amount=D('1'),provider_configuration_version=0,actor_name_snapshot='owner',subject_type='staff',idempotency_key=uuid4().hex,request_hash='b'*64)
    db_session.add(second);await db_session.commit();monkeypatch.setattr(endpoint,'MAX_JOINED_FINANCIAL_ROWS',1)
    response=await client.get(PATH,headers={'X-API-Key':key['api_key']})
    assert response.status_code==409 and response.json()['detail']['code']=='financial_snapshot_too_large'
    assert 'items' not in response.json()
