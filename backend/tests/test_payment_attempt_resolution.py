"""Exact resolution against synthetic invoices; no provider transport."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from sqlalchemy import select,func,event
from test_zelle_explicit_confirmation import fictional_zelle_context,client_for,financial_counts
from app.services import invoice_settlement_service as domain,payment_attempt_resolution as resolution
from app.schemas.invoice_settlement import AttemptResolutionCommand as Command
from app.db.models.invoice_settlement import InvoicePaymentAttempt as Attempt,InvoicePaymentLedgerEvent as Event
from app.db.models.user import UserRole
from app.db.models.payment import Payment

@pytest.fixture(autouse=True)
def no_broadcast(monkeypatch):
    import app.core.websocket as websocket
    monkeypatch.setattr(websocket,'broadcast_repair_order_update',AsyncMock())

async def pending(db,ctx,rail='zelle',subject='customer',amount='168.44'):
    created=await domain.create_attempt(db,invoice=ctx.invoice,tenant=ctx.tenant,customer_id=ctx.customer.id,actor=ctx.customer_user if subject=='customer' else None,amount=Decimal(amount),rail=rail,expected_settlement_version=ctx.settlement.version,idempotency_key=f'new-attempt-{uuid4()}',source='customer_portal' if subject=='customer' else 'guest_token',subject_type=subject,subject_id=ctx.customer_user.id if subject=='customer' else ctx.customer.id,transfer_sent_confirmed=rail=='zelle')
    await db.commit();return created.attempt

def command(a,s,**kw):return Command(action='cancel_unsent',expected_attempt_version=a.version,expected_settlement_version=s.version,reason_code='not_sent',transfer_not_sent_confirmed=True,**kw)

@pytest.mark.asyncio
@pytest.mark.parametrize('collection',[False,True])
async def test_customer_partial_cancel_exact_reservation_and_immutable_replay(db_session,monkeypatch,collection):
    ctx=await fictional_zelle_context(db_session,monkeypatch,collection=collection,prior_card='pending');a=await pending(db_session,ctx);body=command(a,ctx.settlement)
    async with await client_for(db_session,ctx.customer_user) as client:
        url=f'/payments/attempts/{a.id}/resolution';headers={'Idempotency-Key':'cancel-exact-request'}
        first=await client.post(url,json=body.model_dump(mode='json'),headers=headers)
        assert first.status_code==200,first.text
        assert first.json()['resolution']['checkout_status']=='cancelled' and first.json()['resolution']['can_retry']
        before=await financial_counts(db_session)
        replay=await client.post(url,json=body.model_dump(mode='json'),headers=headers);assert replay.status_code==200,replay.text
        conflict=await client.post(url,json={**body.model_dump(mode='json'),'reason_code':'changed'},headers=headers);assert conflict.status_code==409
        other=await client.post(url,json=body.model_dump(mode='json'),headers={'Idempotency-Key':'different-command'});assert other.status_code==409
        page=await client.get(f'/payments/invoices/{ctx.invoice.id}/allocations')
        row=next(x for x in page.json()['items'] if x['attempt_id']==str(a.id));assert row['resolution']['resolution_notice']['kind']=='request_cancelled'
        assert await financial_counts(db_session)==before
    assert ctx.settlement.active_pending_principal==100 and ctx.settlement.confirmed_principal==0
    assert ctx.invoice.zelle_pending_submitted_at is None

@pytest.mark.asyncio
@pytest.mark.parametrize('defect',['assertion','stale_attempt','stale_settlement','staff_subject','foreign_customer','foreign_tenant','receptionist','mechanic','admin_no_grant','superadmin'])
async def test_cancel_denial_preserves_records(db_session,monkeypatch,defect):
    ctx=await fictional_zelle_context(db_session,monkeypatch);a=await pending(db_session,ctx);actor=ctx.customer_user;data=command(a,ctx.settlement).model_dump(mode='json')
    if defect=='assertion':data['transfer_not_sent_confirmed']=False
    if defect=='stale_attempt':data['expected_attempt_version']+=1
    if defect=='stale_settlement':data['expected_settlement_version']+=1
    if defect=='staff_subject':a.subject_type='staff'
    if defect=='foreign_customer':actor.customer_id=uuid4()
    if defect=='foreign_tenant':actor.tenant_id=uuid4()
    if defect in {'receptionist','mechanic','admin_no_grant','superadmin'}:
        actor=SimpleNamespace(id=ctx.owner.id,tenant_id=ctx.tenant.id,role={'receptionist':UserRole.RECEPTIONIST,'mechanic':UserRole.MECHANIC,'admin_no_grant':UserRole.GARAGE_ADMIN,'superadmin':UserRole.SUPER_ADMIN}[defect],permissions={'payments':False})
    await db_session.flush();before=await financial_counts(db_session)
    with pytest.raises(domain.SettlementDomainError):await resolution.execute(db_session,a.id,Command(**data),'negative-command',actor=actor)
    assert a.state=='pending' and ctx.settlement.active_pending_principal==Decimal('168.44')
    assert await financial_counts(db_session)==before

@pytest.mark.asyncio
async def test_new_card_local_cancel_blocks_stale_dispatch(db_session,monkeypatch):
    ctx=await fictional_zelle_context(db_session,monkeypatch);a=await pending(db_session,ctx,rail='card')
    dto=(await resolution.project_many(db_session,[a],actor=ctx.customer_user))[a.id];assert dto.checkout_status=='checkout_started' and dto.actions.cancel_unsent
    await resolution.execute(db_session,a.id,command(a,ctx.settlement),'cancel-new-card',actor=ctx.customer_user);await db_session.commit()
    with pytest.raises(domain.SettlementDomainError):await resolution.mark_submission_started(db_session,a,ctx.customer_user)
    assert a.state=='failed' and ctx.settlement.active_pending_principal==0

@pytest.mark.asyncio
async def test_committed_submission_unknown_no_id_cannot_cancel_or_generic_fail(db_session,monkeypatch):
    ctx=await fictional_zelle_context(db_session,monkeypatch);a=await pending(db_session,ctx,rail='card');await resolution.mark_submission_started(db_session,a,ctx.customer_user)
    with pytest.raises(domain.SettlementDomainError,match='terminal provider proof'):
        await domain.fail_attempt(db_session,attempt_id=a.id,tenant_id=ctx.tenant.id,actor=ctx.owner,expected_attempt_version=a.version,failure_code='browser_closed',idempotency_key='unsafe-fail')
    with pytest.raises(domain.SettlementDomainError):await resolution.execute(db_session,a.id,command(a,ctx.settlement),'cancel-unknown-card',actor=ctx.customer_user)
    dto=(await resolution.project_many(db_session,[a],actor=ctx.customer_user))[a.id]
    assert not dto.actions.cancel_unsent and not dto.can_retry and dto.checkout_status=='review_required'
    assert ctx.settlement.active_pending_principal==Decimal('168.44')

@pytest.mark.asyncio
async def test_late_actual_zelle_receipt_preserves_money_and_cancellation_history(db_session,monkeypatch):
    ctx=await fictional_zelle_context(db_session,monkeypatch);a=await pending(db_session,ctx)
    await resolution.execute(db_session,a.id,command(a,ctx.settlement),'cancel-late-money',actor=ctx.customer_user);await db_session.commit()
    result=await domain.confirm_attempt(db_session,attempt_id=a.id,tenant=ctx.tenant,actor=ctx.owner,expected_attempt_version=a.version,idempotency_key='real-bank-receipt',received_principal=Decimal('168.44'),reference='FICTIONAL-BANK-REFERENCE');await db_session.commit()
    assert result.settlement.confirmed_principal==Decimal('168.44') and result.settlement.active_pending_principal==0
    dto=(await resolution.project_many(db_session,[a],actor=ctx.customer_user))[a.id]
    assert dto.checkout_status=='received' and dto.resolution_notice['kind']=='late_receipt'
    assert await db_session.scalar(select(func.count(Payment.id)))==1

@pytest.mark.asyncio
async def test_projection_read_never_flushes_unrelated_payment(db_session,monkeypatch):
    ctx=await fictional_zelle_context(db_session,monkeypatch);a=await pending(db_session,ctx)
    extra=Payment(tenant_id=ctx.tenant.id,invoice_id=ctx.invoice.id,payment_number='UNFLUSHED-RESOLUTION',amount=1,method='check',status='completed');db_session.add(extra);db_session.autoflush=True;calls=[]
    def capture(_c,_cu,sql,*args):
        if sql.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')):calls.append(sql)
    engine=db_session.bind.sync_engine;event.listen(engine,'before_cursor_execute',capture)
    try:
        await resolution.project_many(db_session,[a],actor=ctx.customer_user);assert not calls and extra in db_session.new
    finally:event.remove(engine,'before_cursor_execute',capture);db_session.autoflush=False

async def historical_card(db,ctx):
    a=Attempt(tenant_id=ctx.tenant.id,invoice_id=ctx.invoice.id,settlement_id=ctx.settlement.id,customer_id=ctx.customer.id,source='customer_portal',rail='card',provider='stripe_connect',state='pending',principal_amount=Decimal('25.00'),provider_charge_amount=Decimal('25.00'),provider_configuration_version=1,provider_account_id=ctx.tenant.stripe_account_id,manual_evidence={},actor_user_id=ctx.customer_user.id,actor_name_snapshot='Historical fictional customer',subject_type='customer',subject_id=ctx.customer_user.id,idempotency_key='historical-'+str(uuid4()),request_hash='f'*64)
    db.add(a);ctx.settlement.active_pending_principal+=Decimal('25.00');ctx.settlement.version+=1;await db.commit();return a

@pytest.mark.asyncio
async def test_historical_missing_protocol_never_dispatches_and_review_survives_refresh(db_session,monkeypatch):
    ctx=await fictional_zelle_context(db_session,monkeypatch);a=await historical_card(db_session,ctx)
    before=await financial_counts(db_session)
    with pytest.raises(domain.SettlementDomainError) as denied:await resolution.mark_submission_started(db_session,a,ctx.customer_user)
    assert denied.value.code=='provider_review_required'
    assert await financial_counts(db_session)==before
    body=Command(action='request_review',expected_attempt_version=a.version,expected_settlement_version=ctx.settlement.version,reason_code='unknown_old_reference',reason='Please review the original merchant support case.')
    await resolution.execute(db_session,a.id,body,'historical-review-request',actor=ctx.customer_user);await db_session.commit()
    dto=(await resolution.project_many(db_session,[a],actor=ctx.customer_user))[a.id]
    assert dto.review_status=='requested' and not dto.can_retry
    detail=await resolution.staff_detail(db_session,a,actor=ctx.owner)
    assert detail['binding']['environment'] is None and detail['binding']['provider_request_id'] is None
    assert not detail['evidence_requirements']['can_submit_terminal_evidence']


def stripe_intent(a,status):
    return dict(id=a.provider_intent_id,status=status,currency='usd',amount=int(a.provider_charge_amount*100),amount_received=int(a.provider_charge_amount*100) if status=='succeeded' else 0,amount_capturable=0,livemode=False,latest_charge='ch_fictional' if status=='succeeded' else None,metadata=dict(tenant_id=str(a.tenant_id),invoice_id=str(a.invoice_id),customer_id=str(a.customer_id),invoice_payment_attempt_id=str(a.id),provider_configuration_version=str(a.provider_configuration_version),stripe_connected_account_id=a.provider_account_id,principal_amount=resolution.cash(a.principal_amount),card_fee_amount=resolution.cash(a.card_fee_amount),card_fee_tax_amount=resolution.cash(a.card_fee_tax_amount)))

@pytest.mark.asyncio
@pytest.mark.parametrize('state',['requires_action','processing','succeeded','wrong_amount','missing_zero_proof','timeout'])
async def test_known_stripe_exact_bound_status_cancel_and_terminal_proof(db_session,monkeypatch,state):
    import stripe
    ctx=await fictional_zelle_context(db_session,monkeypatch);a=await pending(db_session,ctx,rail='card')
    await resolution.mark_submission_started(db_session,a,ctx.customer_user);a.provider_intent_id='pi_fictional_'+uuid4().hex;await db_session.commit()
    cancelled=[]
    def retrieve(identity,**kw):
        assert identity==a.provider_intent_id and kw['stripe_account']==a.provider_account_id
        if state=='timeout':raise stripe.error.APIConnectionError('fictional read timeout')
        value=stripe_intent(a,'canceled' if cancelled else state if state in {'requires_action','processing','succeeded'} else 'canceled')
        if state=='wrong_amount':value['amount']+=1
        if state=='missing_zero_proof':value.pop('amount_capturable')
        return value
    def cancel(identity,**kw):cancelled.append(identity)
    monkeypatch.setattr(stripe.PaymentIntent,'retrieve',retrieve);monkeypatch.setattr(stripe.PaymentIntent,'cancel',cancel)
    body=command(a,ctx.settlement)
    a,s=await resolution.execute(db_session,a.id,body,'bound-stripe-resolution',actor=ctx.customer_user);await db_session.commit()
    dto=(await resolution.project_many(db_session,[a],actor=ctx.customer_user))[a.id]
    if state=='requires_action':assert dto.checkout_status=='cancelled' and s.active_pending_principal==0 and cancelled==[a.provider_intent_id]
    elif state=='succeeded':assert dto.checkout_status=='received' and s.confirmed_principal==Decimal('168.44') and not cancelled
    else:assert a.state=='pending' and not dto.can_retry and s.active_pending_principal==Decimal('168.44') and not cancelled


def terminal_body(binding):
    from datetime import datetime,timedelta,timezone
    created=datetime.fromisoformat(binding['attempted_at'])
    return dict(kind='provider_terminal_no_charge',provider=binding['provider'],provider_account_id=binding['provider_account_id'],environment=binding['environment'],configuration_version=binding['configuration_version'],provider_request_id=binding['provider_request_id'],attempted_at=binding['attempted_at'],review_window_start=(created-timedelta(minutes=1)).isoformat(),review_window_end=datetime.now(timezone.utc).isoformat(),provider_case_reference='SUPPORT-CASE-123',evidence_reference='SUPPORT-CASE-123',evidence_context_sha256=binding['evidence_context_sha256'],terminal_outcome='no_charge',reviewer_statement='The merchant support team confirmed this exact request is terminal and cannot settle under the referenced case.')

@pytest.mark.parametrize('field,value',[('provider_case_reference','   '),('evidence_reference','  x  '),('reviewer_statement',' '*35),('reviewer_statement',' '+('x'*29)+' '),('provider_reference','  '),('reviewer_statement','Provider statement includes token=secret-do-not-store and confirms no charge.'),('reviewer_statement','Support saw card number 4111111111111111 and confirmed no transaction.'),('reviewer_statement','Support saw bank account: 12345678901 and confirmed no transaction.')])
def test_terminal_evidence_rejects_blank_short_or_sensitive_text(field,value):
    from app.schemas.invoice_settlement import TerminalEvidence
    from datetime import datetime,timezone
    b=dict(provider='stripe_connect',provider_account_id='acct_example',environment='sandbox',configuration_version=1,provider_request_id='request_example',attempted_at=datetime.now(timezone.utc).isoformat(),evidence_context_sha256='a'*64)
    body=terminal_body(b);body[field]=value
    with pytest.raises(ValueError):TerminalEvidence(**body)

@pytest.mark.asyncio
async def test_terminal_evidence_exact_stepup_consumed_with_release_and_replay_needs_no_new_grant(db_session,monkeypatch):
    from app.core import payment_step_up as step
    from app.core import redis as redis_store
    ctx=await fictional_zelle_context(db_session,monkeypatch);a=await pending(db_session,ctx,rail='card')
    await resolution.mark_submission_started(db_session,a,ctx.customer_user)
    info=await resolution.staff_detail(db_session,a,actor=ctx.owner)
    context=step.PaymentStepUpContext(raw_grant=None,session_jti='fictional-resolution-session',token_version=0,current_user=ctx.owner,correlation_id=str(uuid4()))
    grant,raw=step.issue_step_up_grant(context=context,scope=step.PaymentStepUpScope.ATTEMPTS_RESOLVE,target_tenant_id=None)
    db_session.add(grant);await db_session.commit()
    context=step.PaymentStepUpContext(raw_grant=raw,session_jti=context.session_jti,token_version=0,current_user=ctx.owner,correlation_id=context.correlation_id)
    monkeypatch.setattr(redis_store,'get_token_version',AsyncMock(return_value=0))
    body=Command(action='release_with_terminal_evidence',expected_attempt_version=a.version,expected_settlement_version=ctx.settlement.version,reason_code='provider_terminal_case',reason='Provider support verified the original immutable request.',evidence=terminal_body(info['binding']))
    a,s=await resolution.execute(db_session,a.id,body,'review-terminal-request',actor=ctx.owner,step_up_context=context);await db_session.commit()
    await db_session.refresh(grant)
    assert grant.consumed_at is not None and a.state=='failed' and s.active_pending_principal==0
    before=await financial_counts(db_session)
    await resolution.execute(db_session,a.id,body,'review-terminal-request',actor=ctx.owner,step_up_context=None)
    assert await financial_counts(db_session)==before

@pytest.mark.asyncio
async def test_manage_grant_cannot_authorize_terminal_release(db_session,monkeypatch):
    from app.core import payment_step_up as step,redis as redis_store
    from fastapi import HTTPException
    ctx=await fictional_zelle_context(db_session,monkeypatch);a=await pending(db_session,ctx,rail='card');await resolution.mark_submission_started(db_session,a,ctx.customer_user)
    info=await resolution.staff_detail(db_session,a,actor=ctx.owner)
    context=step.PaymentStepUpContext(raw_grant=None,session_jti='wrong-scope-session',token_version=0,current_user=ctx.owner,correlation_id=str(uuid4()))
    grant,raw=step.issue_step_up_grant(context=context,scope=step.PaymentStepUpScope.MANAGE,target_tenant_id=None);db_session.add(grant);await db_session.commit()
    context=step.PaymentStepUpContext(raw_grant=raw,session_jti=context.session_jti,token_version=0,current_user=ctx.owner,correlation_id=context.correlation_id)
    monkeypatch.setattr(redis_store,'get_token_version',AsyncMock(return_value=0))
    body=Command(action='release_with_terminal_evidence',expected_attempt_version=a.version,expected_settlement_version=ctx.settlement.version,reason_code='provider_case',reason='Review exact request.',evidence=terminal_body(info['binding']))
    with pytest.raises(HTTPException) as denied:await resolution.execute(db_session,a.id,body,'deny-manage-release',actor=ctx.owner,step_up_context=context)
    assert denied.value.status_code==403 and a.state=='pending' and ctx.settlement.active_pending_principal==Decimal('168.44')

@pytest.mark.asyncio
async def test_guest_cancel_exact_token_subject_and_foreign_invoice_denied(db_session,monkeypatch):
    from app.api.v1.endpoints import invoice_access
    ctx=await fictional_zelle_context(db_session,monkeypatch);a=await pending(db_session,ctx,subject='guest')
    claims=dict(invoice_id=str(ctx.invoice.id),tenant_id=str(ctx.tenant.id),customer_id=str(ctx.customer.id))
    monkeypatch.setattr(invoice_access,'get_invoice_access_payload',AsyncMock(side_effect=lambda token:claims if token=='FICTIONAL-GUEST-TOKEN' else None))
    monkeypatch.setattr(invoice_access,'is_invoice_access_token_consumed',AsyncMock(return_value=False))
    body={**command(a,ctx.settlement).model_dump(mode='json'),'token':'FICTIONAL-GUEST-TOKEN'}
    async with await client_for(db_session,ctx.customer_user) as client:
        denied=await client.post(f'/invoice-access/attempts/{a.id}/resolution',json={**body,'token':'EXPIRED-TOKEN'},headers={'Idempotency-Key':'guest-expired-command'});assert denied.status_code==400
        before=await financial_counts(db_session)
        read=await client.post(f'/invoice-access/attempts/{a.id}/resolution/read',json={'token':'FICTIONAL-GUEST-TOKEN'});assert read.status_code==200,read.text
        assert await financial_counts(db_session)==before
        cancelled=await client.post(f'/invoice-access/attempts/{a.id}/resolution',json=body,headers={'Idempotency-Key':'guest-exact-command'});assert cancelled.status_code==200,cancelled.text
        assert cancelled.json()['resolution']['checkout_status']=='cancelled'
        claims['customer_id']=str(uuid4())
        foreign=await client.post(f'/invoice-access/attempts/{a.id}/resolution/read',json={'token':'FICTIONAL-GUEST-TOKEN'});assert foreign.status_code==404

@pytest.mark.asyncio
async def test_combined_queue_staff_detail_exact_card_and_generic_fail_bypass_denied(db_session,monkeypatch):
    ctx=await fictional_zelle_context(db_session,monkeypatch);a=await pending(db_session,ctx,rail='card')
    async with await client_for(db_session,ctx.owner) as client:
        queue=await client.get('/payments/attempt-review-queue');assert queue.status_code==200,queue.text
        row=queue.json()['rows'][0];assert row['kind']=='canonical_card_attempt' and row['rail']=='card' and row['can_confirm'] is False
        assert row['resolution']['checkout_status']=='checkout_started'
        old=await client.get('/payments/zelle-review-queue');assert old.json()['rows']==[]
        detail=await client.get(f'/payments/attempts/{a.id}/resolution/read');assert detail.status_code==200,detail.text
        assert detail.json()['binding']['provider_request_id']==a.idempotency_key
        before=await financial_counts(db_session)
        unsafe=await client.post(f'/payments/attempts/{a.id}/fail',json={'expected_attempt_version':a.version,'failure_code':'closed_browser'},headers={'Idempotency-Key':'forbidden-old-fail'});assert unsafe.status_code==409
        assert await financial_counts(db_session)==before
    async with await client_for(db_session,ctx.customer_user) as client:
        private=await client.get(f'/payments/attempts/{a.id}/resolution/read');assert private.status_code==404

@pytest.mark.asyncio
async def test_staff_terminal_release_actual_http_header_token_and_stepup_context(db_session,monkeypatch):
    from app.core import payment_step_up as step,redis as redis_store
    from app.core.security import create_access_token
    ctx=await fictional_zelle_context(db_session,monkeypatch);a=await pending(db_session,ctx,rail='card');await resolution.mark_submission_started(db_session,a,ctx.customer_user)
    info=await resolution.staff_detail(db_session,a,actor=ctx.owner)
    token=create_access_token({'sub':str(ctx.owner.id)});from app.core.security import decode_token
    claims=decode_token(token);context=step.PaymentStepUpContext(raw_grant=None,session_jti=claims['jti'],token_version=claims.get('ver',0),current_user=ctx.owner,correlation_id=str(uuid4()))
    grant,raw=step.issue_step_up_grant(context=context,scope=step.PaymentStepUpScope.ATTEMPTS_RESOLVE,target_tenant_id=None);db_session.add(grant);await db_session.commit()
    monkeypatch.setattr(redis_store,'get_token_version',AsyncMock(return_value=context.token_version))
    body=Command(action='release_with_terminal_evidence',expected_attempt_version=a.version,expected_settlement_version=ctx.settlement.version,reason_code='support_confirmed_terminal',reason='Provider support confirmed this exact request cannot settle.',evidence=terminal_body(info['binding']))
    async with await client_for(db_session,ctx.owner) as client:
        response=await client.post(f'/payments/attempts/{a.id}/resolution',json=body.model_dump(mode='json'),headers={'Authorization':f'Bearer {token}','X-Step-Up-Authorization':raw,'Idempotency-Key':'http-terminal-release'})
        assert response.status_code==200,response.text
        assert response.json()['resolution']['checkout_status']=='failed'
        assert response.json()['resolution']['can_retry'] is True
    await db_session.refresh(grant);assert grant.consumed_at is not None

@pytest.mark.asyncio
async def test_staff_role_revoked_between_provider_io_and_release_denies_stale_authority(db_session,monkeypatch):
    from sqlalchemy import update
    ctx=await fictional_zelle_context(db_session,monkeypatch);a=await pending(db_session,ctx,rail='card')
    await resolution.mark_submission_started(db_session,a,ctx.customer_user);a.provider_intent_id='pi_revocation_case';await db_session.commit()
    original=(await resolution.staff_detail(db_session,a,actor=ctx.owner))['resolution']
    body=command(a,ctx.settlement)
    async def revoked_during_io(*args,**kw):
        # Emulate another transaction's committed authority change while this
        # request retains the earlier ORM User in its identity map.
        from app.db.models.user import User
        await db_session.execute(update(User).where(User.id==ctx.owner.id).values(role=UserRole.MECHANIC).execution_options(synchronize_session=False))
        await db_session.commit()
        return 'terminal',None,a.provider_intent_id
    monkeypatch.setattr(resolution,'_provider_result',revoked_during_io)
    with pytest.raises(domain.SettlementDomainError) as denied:await resolution.execute(db_session,a.id,body,'revoke-during-provider',actor=ctx.owner)
    assert denied.value.status_code==404
    assert a.state=='pending' and ctx.settlement.active_pending_principal==Decimal('168.44')

@pytest.mark.asyncio
async def test_verified_provider_receipt_survives_initiator_revocation(db_session,monkeypatch):
    from sqlalchemy import update
    from app.db.models.user import User
    import stripe
    ctx=await fictional_zelle_context(db_session,monkeypatch);a=await pending(db_session,ctx,rail='card');await resolution.mark_submission_started(db_session,a,ctx.customer_user)
    a.provider_intent_id='pi_receipt_after_revocation';await db_session.commit();body=command(a,ctx.settlement)
    provider=stripe_intent(a,'succeeded')
    original=resolution._provider_result
    async def received_after_demotion(*args,**kw):
        await db_session.execute(update(User).where(User.id==ctx.owner.id).values(role=UserRole.MECHANIC).execution_options(synchronize_session=False));await db_session.commit()
        # Keep all provider envelope validation real; only transport is fake.
        monkeypatch.setattr(stripe.PaymentIntent,'retrieve',lambda *args,**kw:provider)
        return await original(*args,**kw)
    monkeypatch.setattr(resolution,'_provider_result',received_after_demotion)
    with pytest.raises(domain.SettlementDomainError) as denied:await resolution.execute(db_session,a.id,body,'received-during-revoke',actor=ctx.owner)
    assert denied.value.status_code==404
    await db_session.refresh(a);await db_session.refresh(ctx.settlement)
    assert a.state=='confirmed' and ctx.settlement.confirmed_principal==Decimal('168.44')
    assert ctx.settlement.active_pending_principal==0
    assert await db_session.scalar(select(func.count(Payment.id)))==1
