"""Synthetic report/queue fixtures. No network, send, production or backfill."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from types import SimpleNamespace as NS
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import select,func
from app.db.models.customer import Customer
from app.db.models.user import User,UserRole
from app.db.models.invoice import Invoice
from app.db.models.invoice_settlement import InvoiceSettlement,InvoicePaymentAttempt,InvoicePaymentLedgerEvent
from app.db.models.payment import Payment
from app.services import invoice_settlement_service as domain
from app.services.zelle_transfer_reports import review_queue
from app.api.v1.endpoints.invoice_settlements import create_invoice_payment_attempt
from app.schemas.invoice_settlement import PaymentAttemptCreate
from test_db048_invoice_settlements import _financial_context

@pytest.fixture(autouse=True)
def offline_invalidation(monkeypatch):
    import app.core.websocket as websocket
    monkeypatch.setattr(websocket,'broadcast_repair_order_update',AsyncMock())


async def fictional_zelle_context(db,patcher,*,collection=False,prior_card=None,historical_zelle=False):
    """Fresh fictional268.44 invoice; optional exact-source reviewed payerB.

    Runtime owner may reuse this in a NEW empty QA database with workers off.
    It creates fixtures; it must never be called on production/existing QA data.
    """
    from app.core.config import settings
    from app.services import source_debt_handoff as source
    from app.schemas.source_debt_handoff import PrepareRequest,BillToReview,SourceVersionRequest
    tenant,owner,original_customer,original=await _financial_context(db,patcher,principal=Decimal('268.44'),fee=Decimal('0'))
    tenant.zelle_email='fictional-zelle@example.test'
    tenant.zelle_phone='+15005550000'
    patcher.setattr(settings,'SMS_AUTOMATION_OUTBOX_ENABLED',False)
    patcher.delenv('DIESELBRIDGE_FLEET_WEBHOOKS',raising=False)
    customer=original_customer;invoice=original;handoff=None;proof=None
    if collection:
        original.source='easy_truck_shop_import';original.repair_order.source='easy_truck_shop_import'
        original.invoice_number=f'FICTIONAL-1687-{uuid4().hex[:6]}'
        original_customer.ets_external_id='990001';original_customer.company_name='Fictional reviewed business'
        customer=Customer(tenant_id=tenant.id,first_name='Reviewed',last_name='Payer',company_name='Fictional reviewed business portal account',email=f'{uuid4()}@example.test')
        db.add(customer);await db.flush()
        import json
        from test_db139_imported_billing import snapshot_fixture
        from app.services.ets_source_evidence import _digest
        original.invoice_number='ETSINV-1687'
        original.repair_order.order_number='ETS-7001-8002'
        _,_,envelope=snapshot_fixture(invoice_status='5',invoice_number='1687',total={'amount':'268.44','currency':'USD'},balance={'amount':'268.44','currency':'USD'},payment_lines=[])
        facts=envelope['observations'][0]['evidence']
        facts.update(source_customer_id='990001',source_customer_uuid=str(uuid4()),source_customer_deleted=False,source_customer_binding_kind='embedded_service_customer')
        envelope['observations'][0]['sha256']=_digest(facts)
        shops=json.loads(settings.ETS_IMPORTED_BILLING_SHOPS);shops[str(tenant.id)]='shop1'
        patcher.setattr(settings,'ETS_IMPORTED_BILLING_SHOPS',json.dumps(shops))
        original_capture=source.imported_billing._source_evidence
        async def fictional_capture(db_session,tenant_id,invoice_ids):
            if tenant_id==tenant.id and set(invoice_ids)=={original.id}:return {original.id:envelope}
            return await original_capture(db_session,tenant_id,invoice_ids)
        # Only the capture-input adapter is scoped. All source proof, original
        # customer/manifest/digest/shop authority and lifecycle checks are REAL.
        patcher.setattr(source.imported_billing,'_source_evidence',fictional_capture)
        await db.flush()
        proof=await source.source_proof(db,tenant.id,original.id,customer.id,allow_bill_to_review=True)
        body=PrepareRequest(source_invoice_id=original.id,target_customer_id=customer.id,expected_source_capture_sha256=proof['digest'],expected_source_revision=proof['revision'],acknowledge_dbn_primary=True,bill_to_review=BillToReview(mode='owner_same_legal_entity',source_customer_id=original_customer.id,target_customer_id=customer.id,attested_same_legal_entity=True,confirmation_reference='FICTIONAL QA ONLY reviewed payer',reason='Fictional same legal entity review'))
        handoff=await source.prepare(db,tenant.id,owner,body,f'fictional-prepare-{uuid4()}')
        facts['observed_at_source']=datetime.now(timezone.utc).isoformat()
        envelope['observations'][0]['sha256']=_digest(facts)
        fresh=await source.source_proof(db,tenant.id,original.id,customer.id)
        handoff,_=await source.activate(db,handoff,owner,SourceVersionRequest(expected_version=handoff.version,expected_source_capture_sha256=fresh['digest'],expected_source_revision=fresh['revision']),f'fictional-activate-{uuid4()}')
        proof=fresh
        invoice=await db.get(Invoice,handoff.native_invoice_id)
        original.repair_order.deleted_at=datetime.now(timezone.utc)
    settlement=await domain.get_or_create_settlement(db,invoice=invoice,customer_id=customer.id,tenant=tenant)
    customer_user=User(tenant_id=tenant.id,customer_id=customer.id,first_name='Fictional',last_name='Customer',email=f'{uuid4()}@example.test',role=UserRole.CUSTOMER,is_active=True)
    db.add(customer_user);await db.commit()
    card=None
    if prior_card:
        creation=await domain.create_attempt(db,invoice=invoice,tenant=tenant,customer_id=customer.id,actor=owner,amount=Decimal('100'),rail='card',expected_settlement_version=settlement.version,idempotency_key=f'fictional-card-{uuid4()}',source='customer_portal',subject_type='customer',subject_id=customer_user.id)
        card=creation.attempt
        await db.flush()  # real HTTP separates creation/confirmation transactions
        if prior_card=='confirmed':
            card.provider_intent_id=f'pi_fictional_{uuid4().hex}'
            await domain.confirm_attempt(db,attempt_id=card.id,tenant=tenant,actor=owner,expected_attempt_version=card.version,idempotency_key=f'fictional-confirm-{uuid4()}',received_principal=Decimal('100'),reference=card.provider_intent_id,provider_charge_id=f'ch_fictional_{uuid4().hex}',provider_event_id=f'evt_fictional_{uuid4().hex}')
        await db.commit()
    old_zelle=None
    if historical_zelle:
        # New fixture row representing pre-change unknown instruction intent;
        # no existing row is amended to call it a reported/received transfer.
        old_zelle=InvoicePaymentAttempt(tenant_id=tenant.id,invoice_id=invoice.id,settlement_id=settlement.id,customer_id=customer.id,source='customer_portal',rail='zelle',provider='manual',state='pending',principal_amount=Decimal('168.44'),provider_charge_amount=Decimal('168.44'),provider_configuration_version=1,provider_account_id=tenant.stripe_account_id,manual_evidence={},actor_user_id=customer_user.id,actor_name_snapshot='Fictional customer',actor_role_snapshot='customer',subject_type='customer',subject_id=customer_user.id,idempotency_key=f'fictional-old-request-{uuid4()}',request_hash='c'*64,expires_at=datetime.now(timezone.utc)+timedelta(hours=48))
        db.add(old_zelle);await db.flush()
        prior=settlement.state;settlement.active_pending_principal+=Decimal('168.44');settlement.version+=1;settlement.state=domain.settlement_state(settlement)
        await domain.append_ledger_event(db,settlement=settlement,attempt=old_zelle,event_type='attempt_created',idempotency_key=f'fictional-old-request:{old_zelle.id}',actor=customer_user,prior_state=prior,new_state=settlement.state,pending_delta=Decimal('168.44'),evidence={'source':'customer_portal','rail':'zelle','provider':'manual'})
        await db.commit()
    return NS(tenant=tenant,owner=owner,customer=customer,customer_user=customer_user,invoice=invoice,settlement=settlement,original=original,original_customer=original_customer,handoff=handoff,source_proof=proof,card=card,old_zelle=old_zelle)

@pytest.mark.asyncio
async def test_fixture_exact_archived_crosspayer_pending_card_and_zelle_are_unverified(db_session,monkeypatch):
    ctx=await fictional_zelle_context(db_session,monkeypatch,collection=True,prior_card='pending',historical_zelle=True)
    rows=(await review_queue(db_session,ctx.owner))['rows']
    assert len(rows)==1 and rows[0]['attempt_id']==str(ctx.old_zelle.id)
    assert rows[0]['customer_id']==str(ctx.customer.id) and ctx.customer.id!=ctx.original_customer.id
    assert rows[0]['principal_amount']=='168.44' and rows[0]['report_status']=='unverified_request'
    assert ctx.settlement.confirmed_principal==0 and ctx.settlement.active_pending_principal==Decimal('268.44')
    assert domain.allocatable_balance(ctx.settlement)==0
    assert ctx.original.repair_order.deleted_at is not None

@pytest.mark.asyncio
async def test_explicit_partial_report_reserves_only_requested_amount_without_legacy_or_paid_state(db_session,monkeypatch):
    ctx=await fictional_zelle_context(db_session,monkeypatch,prior_card='confirmed')
    body=PaymentAttemptCreate(amount=Decimal('168.44'),rail='zelle',expected_settlement_version=ctx.settlement.version,transfer_sent_confirmed=True)
    result=await create_invoice_payment_attempt(ctx.invoice.id,body,'explicit-once',db_session,ctx.customer_user)
    again=await create_invoice_payment_attempt(ctx.invoice.id,body,'explicit-once',db_session,ctx.customer_user)
    assert result.attempt_id==again.attempt_id
    assert ctx.invoice.zelle_pending_submitted_at is None and ctx.invoice.status.value=='sent'
    assert ctx.settlement.confirmed_principal==100 and ctx.settlement.active_pending_principal==Decimal('168.44')
    assert await db_session.scalar(select(func.count(Payment.id)))==1
    pending=await db_session.scalar(select(InvoicePaymentAttempt).where(InvoicePaymentAttempt.rail=='zelle'))
    assert pending.manual_evidence['transfer_sent_confirmed'] is True and pending.manual_evidence['reported_at']
    rows=(await review_queue(db_session,ctx.owner))['rows']
    assert rows[0]['principal_amount']=='168.44' and rows[0]['report_status']=='explicit_report'

async def client_for(db,actor):
    import httpx
    from fastapi import FastAPI
    from app.api.v1.endpoints.invoice_settlements import router
    from app.api.v1.endpoints.invoice_access import router as guest_router
    from app.api.v1.endpoints.payments import router as legacy_router
    from app.core.rate_limit import limiter
    from app.main import settlement_domain_exception_handler
    from app.core.dependencies import get_db,get_current_active_user
    app=FastAPI();app.include_router(router,prefix='/payments');app.include_router(guest_router,prefix='/invoice-access');app.include_router(legacy_router,prefix='/payments')
    limiter.reset();app.state.limiter=limiter
    app.add_exception_handler(domain.SettlementDomainError,settlement_domain_exception_handler)
    async def dependency():yield db
    app.dependency_overrides[get_db]=dependency;app.dependency_overrides[get_current_active_user]=lambda:actor
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver')

@pytest.mark.asyncio
async def test_archived_collection_actual_staff_reads_and_exact_confirmation_never_full_invoice(db_session,monkeypatch):
    ctx=await fictional_zelle_context(db_session,monkeypatch,collection=True,prior_card='pending',historical_zelle=True)
    async with await client_for(db_session,ctx.owner) as client:
        queue=await client.get('/payments/zelle-review-queue');assert queue.status_code==200,queue.text
        row=queue.json()['rows'][0];assert row['can_confirm'] and row['principal_amount']=='168.44'
        snapshot=await client.get(f'/payments/invoices/{ctx.invoice.id}/settlement');assert snapshot.status_code==200,snapshot.text
        assert Decimal(snapshot.json()['outstanding_balance'])==Decimal('268.44')
        allocations=await client.get(f'/payments/invoices/{ctx.invoice.id}/allocations');assert allocations.status_code==200,allocations.text
        assert sorted(Decimal(item['principal_amount']) for item in allocations.json()['items'])==[Decimal('100'),Decimal('168.44')]
        confirmed=await client.post(f'/payments/attempts/{ctx.old_zelle.id}/confirm',json={'expected_attempt_version':ctx.old_zelle.version,'received_amount':'168.44','reference':'FICTIONAL-BANK-TRACE'},headers={'Idempotency-Key':'exact-request-only'})
        assert confirmed.status_code==200,confirmed.text
    assert ctx.settlement.confirmed_principal==Decimal('168.44')
    assert ctx.settlement.active_pending_principal==Decimal('100')
    assert ctx.invoice.status.value=='sent' and ctx.original.repair_order.deleted_at is not None
    assert ctx.original.repair_order.customer_id==ctx.original_customer.id
    assert await db_session.scalar(select(func.count(Payment.id)))==1

async def financial_counts(db):
    from app.db.models.notification import Notification
    from app.db.models.automated_sms import AutomatedSMSOperation
    from app.db.models.provider_outbox import ProviderOutboxEvent
    connection=await db.connection()
    return {model.__tablename__:await connection.scalar(select(func.count()).select_from(model)) for model in (Invoice,InvoiceSettlement,InvoicePaymentAttempt,InvoicePaymentLedgerEvent,Payment,Notification,AutomatedSMSOperation,ProviderOutboxEvent)}

@pytest.mark.asyncio
@pytest.mark.parametrize('flag',[None,False,'true',1])
async def test_actual_portal_missing_false_or_nonliteral_report_intent_writes_nothing(db_session,monkeypatch,flag):
    ctx=await fictional_zelle_context(db_session,monkeypatch);before=await financial_counts(db_session)
    payload={'amount':'168.44','rail':'zelle','expected_settlement_version':ctx.settlement.version}
    if flag is not None:payload['transfer_sent_confirmed']=flag
    async with await client_for(db_session,ctx.customer_user) as client:
        response=await client.post(f'/payments/invoices/{ctx.invoice.id}/attempts',json=payload,headers={'Idempotency-Key':'explicit-required'})
    assert response.status_code==422,response.text
    assert await financial_counts(db_session)==before
    assert ctx.settlement.active_pending_principal==0 and ctx.invoice.zelle_pending_submitted_at is None

@pytest.mark.asyncio
async def test_guest_true_report_exact_subject_and_same_key_replay_no_legacy_markers(db_session,monkeypatch):
    from app.api.v1.endpoints import invoice_access
    ctx=await fictional_zelle_context(db_session,monkeypatch)
    claims={'invoice_id':str(ctx.invoice.id),'tenant_id':str(ctx.tenant.id),'customer_id':str(ctx.customer.id)}
    monkeypatch.setattr(invoice_access,'get_invoice_access_payload',AsyncMock(side_effect=lambda token:claims if token=='FICTIONAL-TOKEN' else None))
    monkeypatch.setattr(invoice_access,'is_invoice_access_token_consumed',AsyncMock(return_value=False))
    payload={'token':'FICTIONAL-TOKEN','amount':'168.44','rail':'zelle','expected_settlement_version':ctx.settlement.version,'transfer_sent_confirmed':True,'sender_evidence':{'reported_at':'1999-01-01','transfer_sent_confirmed':False,'provider_reference':'FAKE','sender_name':'Fictional customer'}}
    async with await client_for(db_session,ctx.customer_user) as client:
        first=await client.post('/invoice-access/attempts',json=payload,headers={'Idempotency-Key':'guest-explicit-report'})
        second=await client.post('/invoice-access/attempts',json=payload,headers={'Idempotency-Key':'guest-explicit-report'})
        assert first.status_code==second.status_code==200,(first.text,second.text)
        assert first.json()['attempt_id']==second.json()['attempt_id']
        before=await financial_counts(db_session)
        expired=await client.post('/invoice-access/attempts',json={**payload,'token':'EXPIRED'},headers={'Idempotency-Key':'expired-report'})
        assert expired.status_code==400
        claims['customer_id']=str(uuid4())
        foreign=await client.post('/invoice-access/attempts',json=payload,headers={'Idempotency-Key':'foreign-report'})
        assert foreign.status_code==404
    assert await financial_counts(db_session)==before
    attempt=await db_session.scalar(select(InvoicePaymentAttempt))
    assert attempt.manual_evidence['transfer_sent_confirmed'] is True
    assert attempt.manual_evidence['reported_at']!='1999-01-01' and 'provider_reference' not in attempt.manual_evidence
    assert 'compatibility_submitted_at' not in attempt.manual_evidence and ctx.invoice.zelle_pending_submitted_at is None

@pytest.mark.asyncio
async def test_db048_legacy_explicit_adapter_delegates_partial_once_without_full_invoice_flags(db_session,monkeypatch):
    ctx=await fictional_zelle_context(db_session,monkeypatch,prior_card='confirmed')
    payload={'invoice_id':str(ctx.invoice.id),'amount':'168.44','expected_settlement_version':ctx.settlement.version,'sender_email':'fictional@example.com'}
    async with await client_for(db_session,ctx.customer_user) as client:
        first=await client.post('/payments/submit-zelle',json=payload,headers={'Idempotency-Key':'legacy-partial-report'})
        second=await client.post('/payments/submit-zelle',json=payload,headers={'Idempotency-Key':'legacy-partial-report'})
    assert first.status_code==second.status_code==200,(first.text,second.text)
    assert ctx.invoice.zelle_pending_submitted_at is None
    assert ctx.settlement.confirmed_principal==100 and ctx.settlement.active_pending_principal==Decimal('168.44')
    assert await db_session.scalar(select(func.count(InvoicePaymentAttempt.id)).where(InvoicePaymentAttempt.rail=='zelle'))==1

@pytest.mark.asyncio
async def test_pure_refresh_and_queue_do_not_flush_unrelated_pending_payment_or_create_missing_projection(db_session,monkeypatch):
    from sqlalchemy import event
    ctx=await fictional_zelle_context(db_session,monkeypatch,prior_card='pending',historical_zelle=True)
    pending=Payment(tenant_id=ctx.tenant.id,invoice_id=ctx.invoice.id,payment_number=f'UNFLUSHED-{uuid4()}',amount=1,method='check',status='completed')
    db_session.add(pending);db_session.autoflush=True
    mutations=[]
    def capture(_conn,_cursor,statement,*args):
        if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')):mutations.append(statement)
    engine=db_session.bind.sync_engine;event.listen(engine,'before_cursor_execute',capture)
    try:
        async with await client_for(db_session,ctx.owner) as client:
            for path in (f'/payments/invoices/{ctx.invoice.id}/settlement',f'/payments/invoices/{ctx.invoice.id}/allocations','/payments/zelle-review-queue'):
                result=await client.get(path);assert result.status_code==200,result.text
        assert not mutations and pending in db_session.new
    finally:event.remove(engine,'before_cursor_execute',capture);db_session.autoflush=False

@pytest.mark.asyncio
async def test_missing_settlement_read_returns_unavailable_without_materialization(db_session,monkeypatch):
    tenant,owner,customer,invoice=await _financial_context(db_session,monkeypatch)
    before=await financial_counts(db_session)
    async with await client_for(db_session,owner) as client:
        response=await client.get(f'/payments/invoices/{invoice.id}/settlement')
    assert response.status_code==409 and response.json()['error']['code']=='invoice_settlement_unavailable'
    assert await financial_counts(db_session)==before

@pytest.mark.asyncio
@pytest.mark.parametrize('role,grant,allowed',[(UserRole.GARAGE_OWNER,False,True),(UserRole.GARAGE_ADMIN,True,True),(UserRole.GARAGE_ADMIN,False,False),(UserRole.RECEPTIONIST,True,False),(UserRole.SUPER_ADMIN,True,False),(UserRole.MECHANIC,True,False),(UserRole.CUSTOMER,True,False)])
async def test_queue_review_money_permission_is_not_notification_contact_role(db_session,monkeypatch,role,grant,allowed):
    ctx=await fictional_zelle_context(db_session,monkeypatch,historical_zelle=True)
    actor=NS(id=uuid4(),role=role,tenant_id=ctx.tenant.id,permissions={'payments':grant})
    async with await client_for(db_session,actor) as client:response=await client.get('/payments/zelle-review-queue')
    assert response.status_code==(200 if allowed else 403),response.text
    if allowed:assert len(response.json()['rows'])==1


@pytest.mark.asyncio
@pytest.mark.parametrize('guest',[False,True])
@pytest.mark.parametrize('header',[False,True])
async def test_legacy_omitted_amount_and_version_retry_retains_original_command(db_session,monkeypatch,guest,header):
    from app.api.v1.endpoints import invoice_access
    ctx=await fictional_zelle_context(db_session,monkeypatch,prior_card='confirmed')
    claims={'invoice_id':str(ctx.invoice.id),'tenant_id':str(ctx.tenant.id),'customer_id':str(ctx.customer.id)}
    monkeypatch.setattr(invoice_access,'get_invoice_access_payload',AsyncMock(return_value=claims))
    monkeypatch.setattr(invoice_access,'is_invoice_access_token_consumed',AsyncMock(return_value=False))
    payload={'token':'FICTIONAL-TOKEN'} if guest else {'invoice_id':str(ctx.invoice.id)}
    path='/invoice-access/submit-zelle' if guest else '/payments/submit-zelle'
    headers={'Idempotency-Key':'omitted-legacy-intent'} if header else {}
    async with await client_for(db_session,ctx.customer_user) as client:
        first=await client.post(path,json=payload,headers=headers)
        assert first.status_code==200,first.text
        counts=await financial_counts(db_session)
        for _ in range(2):
            replay=await client.post(path,json=payload,headers=headers)
            assert replay.status_code==200,replay.text
            assert await financial_counts(db_session)==counts
    attempts=(await db_session.scalars(select(InvoicePaymentAttempt).where(InvoicePaymentAttempt.rail=='zelle'))).all()
    assert len(attempts)==1 and attempts[0].principal_amount==Decimal('168.44')
    assert ctx.settlement.active_pending_principal==Decimal('168.44')
    assert ctx.invoice.zelle_pending_submitted_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize('guest',[False,True])
@pytest.mark.parametrize('ambiguous',[False,True])
async def test_old_amount_suffix_headerless_report_replays_or_fails_closed(db_session,monkeypatch,guest,ambiguous):
    from app.api.v1.endpoints import invoice_access
    ctx=await fictional_zelle_context(db_session,monkeypatch)
    claims={'invoice_id':str(ctx.invoice.id),'tenant_id':str(ctx.tenant.id),'customer_id':str(ctx.customer.id)}
    monkeypatch.setattr(invoice_access,'get_invoice_access_payload',AsyncMock(return_value=claims))
    monkeypatch.setattr(invoice_access,'is_invoice_access_token_consumed',AsyncMock(return_value=False))
    subject='guest' if guest else 'customer'
    identity=ctx.customer.id if guest else ctx.customer_user.id
    payload={'token':'FICTIONAL-TOKEN'} if guest else {'invoice_id':str(ctx.invoice.id)}
    path='/invoice-access/submit-zelle' if guest else '/payments/submit-zelle'
    async with await client_for(db_session,ctx.customer_user) as client:
        for amount in (['100.00','20.00'] if ambiguous else ['100.00']):
            key=f'compat:{subject}-zelle:{ctx.invoice.id}:{identity}:{amount}'
            response=await client.post(path,json={**payload,'amount':amount},headers={'Idempotency-Key':key})
            assert response.status_code==200,response.text
        # Reproduce pre-feature records: same immutable original command hash,
        # without explicit-report provenance added by the newer endpoint.
        attempts=(await db_session.scalars(select(InvoicePaymentAttempt).where(InvoicePaymentAttempt.rail=='zelle'))).all()
        for attempt in attempts:
            evidence={k:v for k,v in attempt.manual_evidence.items() if k not in {'reported_at','transfer_sent_confirmed'}}
            attempt.manual_evidence=evidence
            attempt.request_hash=domain._canonical_hash(dict(tenant_id=str(ctx.tenant.id),invoice_id=str(ctx.invoice.id),customer_id=str(ctx.customer.id),subject_type=subject,subject_id=None if guest else str(ctx.customer_user.id),source='compatibility_adapter',rail='zelle',amount=str(attempt.principal_amount),evidence=evidence))
        await db_session.commit();before=await financial_counts(db_session)
        response=await client.post(path,json=payload)
        assert response.status_code==(409 if ambiguous else 200),response.text
        assert await financial_counts(db_session)==before
        assert ctx.settlement.active_pending_principal==Decimal('120.00' if ambiguous else '100.00')

@pytest.mark.asyncio
async def test_queue_cursor_exact_scope_expiry_and_legacy_dedup_are_read_only(db_session,monkeypatch):
    from app.services.zelle_transfer_reports import _queue_cursor
    ctx=await fictional_zelle_context(db_session,monkeypatch,historical_zelle=True)
    ctx.old_zelle.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
    marker=datetime.now(timezone.utc)
    ctx.invoice.zelle_pending_submitted_at=marker
    ctx.old_zelle.manual_evidence={'compatibility_submitted_at':marker.isoformat()}
    await db_session.commit();before=await financial_counts(db_session)
    async with await client_for(db_session,ctx.owner) as client:
        first=await client.get('/payments/zelle-review-queue?limit=1')
        assert first.status_code==200,first.text
        data=first.json();rows=data['rows'];cursor=data['next_cursor']
        while cursor:
            page=await client.get('/payments/zelle-review-queue',params={'limit':1,'cursor':cursor})
            assert page.status_code==200,page.text
            data=page.json();rows+=data['rows'];cursor=data['next_cursor']
        assert len(rows)==1 and rows[0]['attempt_id']==str(ctx.old_zelle.id)
        assert rows[0]['principal_amount']=='168.44' and rows[0]['can_confirm'] is False
        invalid=await client.get('/payments/zelle-review-queue',params={'cursor':'!bad!'})
        assert invalid.status_code==422
        foreign_cursor=_queue_cursor(uuid4(),NS(created_at=marker,kind='canonical_zelle_attempt',row_id=uuid4()))
        foreign=await client.get('/payments/zelle-review-queue',params={'cursor':foreign_cursor})
        assert foreign.status_code==422
    assert await financial_counts(db_session)==before
