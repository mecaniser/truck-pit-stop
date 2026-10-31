"""Source outbox wakes EDG; it never sends amounts or confirms payments."""
from datetime import datetime,timezone
from uuid import uuid4
import json
import pytest
from sqlalchemy import select
from app.api.v1.endpoints import invoices
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.invoice import Invoice
from app.api.v1.endpoints.invoices import InvoiceUpdate
from tests.test_db094_repair_history_exports import seed_history
EVENT='fleet.financial.wakeup.v1'

@pytest.mark.asyncio
async def test_invoice_change_captures_scoped_nonfinancial_wakeup_in_same_commit(db_session,monkeypatch):
    owner,customer,invoice,_vehicle,_key=await seed_history(db_session)
    monkeypatch.setenv('DIESELBRIDGE_FLEET_WEBHOOKS',json.dumps([{'shop_id':str(owner.tenant_id),'customer_id':str(customer.id),'url':'https://edg.example/api/v1/accounting/dieselbridge/webhooks/shop','secret_env':'TEST_FLEET_WEBHOOK_SECRET'}]))
    await invoices.update_invoice(invoice.id,InvoiceUpdate(due_date=datetime(2026,11,1,tzinfo=timezone.utc)),db=db_session,current_user=owner)
    events=(await db_session.execute(select(ProviderOutboxEvent).where(ProviderOutboxEvent.event_type==EVENT))).scalars().all()
    assert len(events)==1
    p=events[0].payload
    assert set(p)=={'version','event_id','shop_id','customer_id','repair_order_id','kind','occurred_at'}
    assert p['kind']=='invoice_changed' and p['customer_id']==str(customer.id)
    assert '100.00' not in json.dumps(p)

async def configured_event(db_session,monkeypatch):
    owner,customer,invoice,_vehicle,_key=await seed_history(db_session)
    monkeypatch.setenv('DIESELBRIDGE_FLEET_WEBHOOKS',json.dumps([{'shop_id':str(owner.tenant_id),'customer_id':str(customer.id),'url':'https://edg.example/api/v1/accounting/dieselbridge/webhooks/shop','secret_env':'TEST_FLEET_WEBHOOK_SECRET'}]))
    await invoices.update_invoice(invoice.id,InvoiceUpdate(due_date=datetime(2026,11,1,tzinfo=timezone.utc)),db=db_session,current_user=owner)
    return (await db_session.execute(select(ProviderOutboxEvent).where(ProviderOutboxEvent.event_type==EVENT))).scalar_one()

@pytest.mark.asyncio
async def test_fleet_worker_delivers_signed_scope_only_wakeup(db_session,monkeypatch):
    import httpx,hmac,hashlib
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services.fleet_financial_wakeup import process_due_financial_wakeups
    from app.core import webhook_destination as boundary
    event=await configured_event(db_session,monkeypatch)
    monkeypatch.setenv('DIESELBRIDGE_FLEET_WEBHOOK_DELIVERY_ENABLED','true')
    monkeypatch.setenv('TEST_FLEET_WEBHOOK_SECRET','fixture-only-signing-secret-32chars')
    async def resolve(url,**kwargs):
        return boundary.ResolvedWebhookDestination(url,'edg.example','edg.example',('93.184.216.34',))
    monkeypatch.setattr(boundary,'resolve_webhook_destination',resolve)
    sent=[]
    async def request(self,method,url,**kwargs):
        sent.append((method,str(url),kwargs))
        return httpx.Response(200,request=httpx.Request(method,url))
    monkeypatch.setattr(httpx.AsyncClient,'request',request)
    result=await process_due_financial_wakeups(session_factory=async_sessionmaker(db_session.bind,expire_on_commit=False))
    assert result['succeeded']==1
    await db_session.refresh(event)
    assert event.status=='succeeded' and event.attempt_count==1
    _,url,kwargs=sent[0];assert '93.184.216.34' in url
    headers=kwargs['headers'];body=kwargs['content'];timestamp=headers['X-DBN-Timestamp']
    expected='v1='+hmac.new(b'fixture-only-signing-secret-32chars',timestamp.encode()+b'.'+body,hashlib.sha256).hexdigest()
    assert headers['X-DBN-Signature']==expected
    assert headers['X-DBN-Event-Id']==str(event.id)
    assert kwargs['extensions']['sni_hostname']=='edg.example'

@pytest.mark.asyncio
async def test_missing_signing_secret_pauses_without_budget_and_backs_off(db_session,monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services.fleet_financial_wakeup import process_due_financial_wakeups
    event=await configured_event(db_session,monkeypatch);before=event.available_at
    monkeypatch.setenv('DIESELBRIDGE_FLEET_WEBHOOK_DELIVERY_ENABLED','true')
    monkeypatch.delenv('TEST_FLEET_WEBHOOK_SECRET',raising=False)
    result=await process_due_financial_wakeups(session_factory=async_sessionmaker(db_session.bind,expire_on_commit=False))
    await db_session.refresh(event)
    assert result['claimed']==0 and result['paused']==1
    assert event.status=='pending' and event.attempt_count==0
    assert event.available_at.replace(tzinfo=timezone.utc)>before.replace(tzinfo=timezone.utc)

@pytest.mark.asyncio
@pytest.mark.parametrize('status',[503,500,302])
async def test_receiver_failure_is_durable_and_redirects_never_followed(db_session,monkeypatch,status):
    import httpx
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services.fleet_financial_wakeup import process_due_financial_wakeups
    from app.core import webhook_destination as boundary
    event=await configured_event(db_session,monkeypatch)
    monkeypatch.setenv('DIESELBRIDGE_FLEET_WEBHOOK_DELIVERY_ENABLED','true');monkeypatch.setenv('TEST_FLEET_WEBHOOK_SECRET','fixture-only-signing-secret-32chars')
    async def resolve(url,**kwargs):return boundary.ResolvedWebhookDestination(url,'edg.example','edg.example',('93.184.216.34',))
    monkeypatch.setattr(boundary,'resolve_webhook_destination',resolve)
    calls=[]
    async def request(self,method,url,**kwargs):
        calls.append(str(url));return httpx.Response(status,headers={'Location':'https://evil.example'},request=httpx.Request(method,url))
    monkeypatch.setattr(httpx.AsyncClient,'request',request)
    result=await process_due_financial_wakeups(session_factory=async_sessionmaker(db_session.bind,expire_on_commit=False))
    await db_session.refresh(event)
    assert len(calls)==1
    assert event.status==('dead' if status==302 else 'pending')
    assert event.attempt_count==(0 if status==503 else 1)
    assert event.payload['event_id']==str(event.id)
    assert 'fixture-only' not in (event.last_error or '')

@pytest.mark.asyncio
async def test_outbox_enqueue_is_idempotent_and_rolls_back_with_source(db_session,monkeypatch):
    from app.services.fleet_financial_wakeup import enqueue_financial_wakeup
    owner,customer,invoice,_vehicle,_key=await seed_history(db_session)
    monkeypatch.setenv('DIESELBRIDGE_FLEET_WEBHOOKS',json.dumps([{'shop_id':str(owner.tenant_id),'customer_id':str(customer.id),'url':'https://edg.example/api/v1/accounting/dieselbridge/webhooks/shop','secret_env':'TEST_FLEET_WEBHOOK_SECRET'}]))
    first=await enqueue_financial_wakeup(db_session,invoice=invoice,order=invoice.repair_order,kind='invoice_finalized')
    await db_session.flush()
    second=await enqueue_financial_wakeup(db_session,invoice=invoice,order=invoice.repair_order,kind='invoice_finalized')
    assert first.id==second.id
    await db_session.rollback()
    assert (await db_session.execute(select(ProviderOutboxEvent).where(ProviderOutboxEvent.event_type==EVENT))).scalars().all()==[]

@pytest.mark.asyncio
async def test_revoked_key_pauses_delivery_and_unattributed_invoice_does_not_enqueue(db_session,monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.db.models.fleet_invoice_api_key import FleetInvoiceApiKey
    from app.services.fleet_financial_wakeup import process_due_financial_wakeups,enqueue_financial_wakeup
    event=await configured_event(db_session,monkeypatch)
    monkeypatch.setenv('DIESELBRIDGE_FLEET_WEBHOOK_DELIVERY_ENABLED','true');monkeypatch.setenv('TEST_FLEET_WEBHOOK_SECRET','fixture-only-signing-secret-32chars')
    key=(await db_session.execute(select(FleetInvoiceApiKey))).scalars().first();key.revoked_at=datetime.now(timezone.utc)
    invoice=(await db_session.execute(select(Invoice))).scalars().first()
    invoice.billed_customer_id=None;await db_session.commit()
    # Explicit async load: relationship identity-cache lifetime must not decide
    # whether this test performs synchronous lazy I/O after commit.
    from app.db.models.repair_order import RepairOrder
    order=await db_session.get(RepairOrder,invoice.repair_order_id)
    assert await enqueue_financial_wakeup(db_session,invoice=invoice,order=order,kind='invoice_changed') is None
    await db_session.rollback()
    result=await process_due_financial_wakeups(session_factory=async_sessionmaker(db_session.bind,expire_on_commit=False))
    await db_session.refresh(event)
    assert result['claimed']==0 and event.attempt_count==0 and event.status=='pending'

@pytest.mark.asyncio
@pytest.mark.parametrize('change',['tax','charges'])
async def test_audited_charge_changes_capture_review_wakeup(db_session,monkeypatch,change):
    from fastapi import Response
    from tests.test_db048_tax_exemption import setup,apply
    from tests.test_db048_invoice_charge_adjustments import adjust
    from app.api.v1.endpoints import fleet_invoice_exports
    ctx=await setup(db_session,monkeypatch);tenant,owner,customer,invoice,_settlement=ctx
    invoice.billed_customer_id=customer.id
    await db_session.flush()
    await fleet_invoice_exports.create_key(fleet_invoice_exports.KeyRequest(customer_id=customer.id,name='fixture'),Response(),db=db_session,user=owner)
    monkeypatch.setenv('DIESELBRIDGE_FLEET_WEBHOOKS',json.dumps([{'shop_id':str(tenant.id),'customer_id':str(customer.id),'url':'https://edg.example/api/v1/accounting/dieselbridge/webhooks/shop','secret_env':'TEST_FLEET_WEBHOOK_SECRET'}]))
    if change=='tax':await apply(db_session,ctx)
    else:await adjust(db_session,ctx,tax=True,supplies=False)
    await db_session.flush()
    events=(await db_session.execute(select(ProviderOutboxEvent).where(ProviderOutboxEvent.event_type==EVENT))).scalars().all()
    assert len(events)==1 and events[0].payload['kind']=='invoice_changed'

@pytest.mark.asyncio
async def test_void_and_reissue_produce_distinct_durable_wakeups(db_session,monkeypatch):
    from sqlalchemy.orm import selectinload
    from app.db.models.repair_order import RepairOrder
    from app.db.models.tenant import Tenant
    owner,customer,invoice,_vehicle,_key=await seed_history(db_session)
    monkeypatch.setenv('DIESELBRIDGE_FLEET_WEBHOOKS',json.dumps([{'shop_id':str(owner.tenant_id),'customer_id':str(customer.id),'url':'https://edg.example/api/v1/accounting/dieselbridge/webhooks/shop','secret_env':'TEST_FLEET_WEBHOOK_SECRET'}]))
    async def no_broadcast(**kwargs):return None
    monkeypatch.setattr(invoices,'broadcast_repair_order_update',no_broadcast)
    await invoices.void_invoice(invoice.id,invoices.InvoiceVoidRequest(reason='Review revised repair'),db=db_session,current_user=owner)
    order=(await db_session.execute(select(RepairOrder).where(RepairOrder.id==invoice.repair_order_id).options(selectinload(RepairOrder.customer),selectinload(RepairOrder.vehicle)))).scalar_one()
    tenant=await db_session.get(Tenant,owner.tenant_id)
    replacement=await invoices.auto_create_invoice_for_order(db_session,order,tenant,created_by_user_id=owner.id,notify=False)
    assert replacement.id!=invoice.id
    events=(await db_session.execute(select(ProviderOutboxEvent).where(ProviderOutboxEvent.event_type==EVENT))).scalars().all()
    assert {e.payload['kind'] for e in events}=={'invoice_cancelled','invoice_finalized'}
    assert len({e.payload['event_id'] for e in events})==2

@pytest.mark.asyncio
async def test_private_dns_destination_is_rejected_before_http(db_session,monkeypatch):
    import httpx,socket
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services.fleet_financial_wakeup import process_due_financial_wakeups
    event=await configured_event(db_session,monkeypatch)
    monkeypatch.setenv('DIESELBRIDGE_FLEET_WEBHOOK_DELIVERY_ENABLED','true');monkeypatch.setenv('TEST_FLEET_WEBHOOK_SECRET','fixture-only-signing-secret-32chars')
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))])
    async def never_request(*args,**kwargs):raise AssertionError('HTTP must not start for private DNS')
    monkeypatch.setattr(httpx.AsyncClient,'request',never_request)
    result=await process_due_financial_wakeups(session_factory=async_sessionmaker(db_session.bind,expire_on_commit=False))
    await db_session.refresh(event)
    assert result['dead']==1 and event.status=='dead'

@pytest.mark.asyncio
async def test_disabled_delivery_preserves_pending_without_attempts(db_session,monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services.fleet_financial_wakeup import process_due_financial_wakeups
    event=await configured_event(db_session,monkeypatch)
    monkeypatch.delenv('DIESELBRIDGE_FLEET_WEBHOOK_DELIVERY_ENABLED',raising=False)
    result=await process_due_financial_wakeups(session_factory=async_sessionmaker(db_session.bind,expire_on_commit=False))
    await db_session.refresh(event)
    assert result['claimed']==0 and event.status=='pending' and event.attempt_count==0

@pytest.mark.asyncio
async def test_stale_worker_completion_cannot_acknowledge_new_lease(db_session,monkeypatch):
    import httpx
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services.fleet_financial_wakeup import process_due_financial_wakeups
    from app.core import webhook_destination as boundary
    event=await configured_event(db_session,monkeypatch);factory=async_sessionmaker(db_session.bind,expire_on_commit=False)
    monkeypatch.setenv('DIESELBRIDGE_FLEET_WEBHOOK_DELIVERY_ENABLED','true');monkeypatch.setenv('TEST_FLEET_WEBHOOK_SECRET','fixture-only-signing-secret-32chars')
    async def resolve(url,**kwargs):return boundary.ResolvedWebhookDestination(url,'edg.example','edg.example',('93.184.216.34',))
    monkeypatch.setattr(boundary,'resolve_webhook_destination',resolve)
    async def request(self,method,url,**kwargs):
        async with factory() as competing:
            row=await competing.get(ProviderOutboxEvent,event.id);row.lock_token='new-lease';await competing.commit()
        return httpx.Response(200,request=httpx.Request(method,url))
    monkeypatch.setattr(httpx.AsyncClient,'request',request)
    result=await process_due_financial_wakeups(session_factory=factory)
    await db_session.refresh(event)
    assert result['succeeded']==0 and event.lock_token=='new-lease' and event.status=='processing'

@pytest.mark.asyncio
async def test_outbox_identity_cannot_reuse_a_different_customer_scope(db_session,monkeypatch):
    from fastapi import Response
    from app.api.v1.endpoints import fleet_invoice_exports
    from app.db.models.customer import Customer
    from app.db.models.historical_invoice_export import HistoricalInvoiceMapping
    from app.services.fleet_financial_wakeup import enqueue_financial_wakeup
    owner,customer,invoice,_vehicle,_key=await seed_history(db_session)
    other=Customer(tenant_id=owner.tenant_id,first_name='Other',last_name='Fleet',email=uuid4().hex+'@example.com')
    db_session.add(other);await db_session.flush()
    await fleet_invoice_exports.create_key(fleet_invoice_exports.KeyRequest(customer_id=other.id,name='fixture2'),Response(),db=db_session,user=owner)
    config=lambda c:{'shop_id':str(owner.tenant_id),'customer_id':str(c.id),'url':'https://edg.example/api/v1/accounting/dieselbridge/webhooks/shop','secret_env':'TEST_FLEET_WEBHOOK_SECRET'}
    monkeypatch.setenv('DIESELBRIDGE_FLEET_WEBHOOKS',json.dumps([config(customer),config(other)]))
    invoice.billed_customer_id=None
    mapping=HistoricalInvoiceMapping(tenant_id=owner.tenant_id,invoice_id=invoice.id,target_customer_id=customer.id,version=1)
    db_session.add(mapping);await db_session.flush()
    first=await enqueue_financial_wakeup(db_session,invoice=invoice,order=invoice.repair_order,kind='invoice_changed');await db_session.flush()
    mapping.target_customer_id=other.id;await db_session.flush()
    second=await enqueue_financial_wakeup(db_session,invoice=invoice,order=invoice.repair_order,kind='invoice_changed')
    assert first.id!=second.id
    assert first.payload['customer_id']==str(customer.id) and second.payload['customer_id']==str(other.id)


def test_fleet_delivery_has_its_own_bounded_celery_cadence():
    from app.tasks import celery_app
    entry=celery_app.conf.beat_schedule.get('process-fleet-financial-wakeups')
    assert entry is not None and entry['task']=='process_fleet_financial_wakeups'
    assert entry['schedule'].total_seconds()==10

@pytest.mark.asyncio
async def test_ro_completion_correction_produces_a_new_revision_wakeup(db_session,monkeypatch):
    from app.services.fleet_financial_wakeup import enqueue_financial_wakeup
    owner,customer,invoice,_vehicle,_key=await seed_history(db_session)
    monkeypatch.setenv('DIESELBRIDGE_FLEET_WEBHOOKS',json.dumps([{'shop_id':str(owner.tenant_id),'customer_id':str(customer.id),'url':'https://edg.example/api/v1/accounting/dieselbridge/webhooks/shop','secret_env':'TEST_FLEET_WEBHOOK_SECRET'}]))
    first=await enqueue_financial_wakeup(db_session,invoice=invoice,order=invoice.repair_order,kind='invoice_changed');await db_session.flush()
    invoice.repair_order.work_completed_at=datetime(2026,10,9,tzinfo=timezone.utc)
    second=await enqueue_financial_wakeup(db_session,invoice=invoice,order=invoice.repair_order,kind='invoice_changed')
    assert first.id!=second.id

@pytest.mark.asyncio
async def test_ro_description_update_captures_wakeup(db_session,monkeypatch):
    from app.api.v1.endpoints import repair_orders
    from app.schemas.repair_order import RepairOrderUpdate
    owner,customer,invoice,_vehicle,_key=await seed_history(db_session)
    monkeypatch.setenv('DIESELBRIDGE_FLEET_WEBHOOKS',json.dumps([{'shop_id':str(owner.tenant_id),'customer_id':str(customer.id),'url':'https://edg.example/api/v1/accounting/dieselbridge/webhooks/shop','secret_env':'TEST_FLEET_WEBHOOK_SECRET'}]))
    await repair_orders.update_repair_order(invoice.repair_order_id,RepairOrderUpdate(description='Corrected completed work'),db=db_session,current_user=owner)
    events=(await db_session.execute(select(ProviderOutboxEvent).where(ProviderOutboxEvent.event_type==EVENT))).scalars().all()
    assert len(events)==1 and events[0].payload['kind']=='invoice_changed'
