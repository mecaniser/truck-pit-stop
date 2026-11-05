"""Fictional EFS bearer-secret tests; no provider/redemption or actual messages."""
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock
import json
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select,func
from test_zelle_explicit_confirmation import fictional_zelle_context as base_context,client_for,financial_counts
from app.core.config import settings
from app.core import efs_crypto
from app.services import customer_efs as efs,invoice_settlement_service as domain
from app.db.models.efs_instrument import EfsInstrumentSubmission as Claim
from app.db.models.invoice_settlement import InvoicePaymentAttempt as Attempt,InvoicePaymentLedgerEvent as Event
from app.db.models.payment import Payment
from app.db.models.user import UserRole
from app.schemas.efs_submission import EfsSubmit,EfsVerify

async def fictional_zelle_context(db,monkeypatch,**kwargs):
    ctx=await base_context(db,monkeypatch,**kwargs)
    enabled=settings.EFS_CUSTOMER_ENABLED_TENANT_IDS
    monkeypatch.setattr(settings,'EFS_CUSTOMER_ENABLED_TENANT_IDS',','.join(filter(None,[enabled,str(ctx.tenant.id)])))
    return ctx

CODE='0012345678'
@pytest.fixture(autouse=True)
def fictional_keys(monkeypatch):
    monkeypatch.setattr(settings,'EFS_INSTRUMENT_ENCRYPTION_KEYS',json.dumps({'v1':Fernet.generate_key().decode()}))
    monkeypatch.setattr(settings,'EFS_INSTRUMENT_ENCRYPTION_ACTIVE_KEY','v1')
    monkeypatch.setattr(settings,'EFS_INSTRUMENT_FINGERPRINT_KEY',Fernet.generate_key().decode())
    import app.core.websocket as websocket
    monkeypatch.setattr(websocket,'broadcast_repair_order_update',AsyncMock())

def payload(ctx,code=CODE,amount='168.44'):
    return dict(code=code,amount=amount,expected_settlement_version=ctx.settlement.version,submitted_for_verification=True)

async def submit(db,ctx,code=CODE,amount='168.44',key='fictional-efs-submit'):
    a,s=await efs.submit(db,invoice=ctx.invoice,tenant=ctx.tenant,customer_id=ctx.customer.id,actor=ctx.customer_user,body=EfsSubmit(**payload(ctx,code,amount)),idempotency_key=key)
    await db.commit();return a,s

@pytest.mark.asyncio
@pytest.mark.parametrize('collection',[False,True])
async def test_customer_pending_exact_partial_encrypted_private_and_replay(db_session,monkeypatch,collection):
    ctx=await fictional_zelle_context(db_session,monkeypatch,collection=collection,prior_card='pending')
    body=payload(ctx)
    async with await client_for(db_session,ctx.customer_user) as client:
        first=await client.post(f'/payments/invoices/{ctx.invoice.id}/efs-submissions',json=body,headers={'Idempotency-Key':'customer-efs-command'})
        assert first.status_code==200,first.text
        result=first.json();assert result['efs']['status']=='awaiting_verification' and result['efs']['code_last4']=='5678'
        assert not result['efs']['can_reveal'] and not result['efs']['can_verify']
        assert CODE not in first.text and result['rail']=='fleet_payment'
        before=await financial_counts(db_session)
        again=await client.post(f'/payments/invoices/{ctx.invoice.id}/efs-submissions',json=body,headers={'Idempotency-Key':'customer-efs-command'})
        assert again.status_code==200 and again.json()['attempt_id']==result['attempt_id']
        changed=await client.post(f'/payments/invoices/{ctx.invoice.id}/efs-submissions',json={**body,'code':'0098765432'},headers={'Idempotency-Key':'customer-efs-command'})
        assert changed.status_code==409
        assert await financial_counts(db_session)==before
        history=await client.get(f'/payments/invoices/{ctx.invoice.id}/allocations')
        assert history.status_code==200 and CODE not in history.text
    claim=await db_session.scalar(select(Claim));assert CODE not in claim.secret_ciphertext
    assert efs_crypto.decrypt(claim)==CODE
    assert ctx.settlement.confirmed_principal==0 and ctx.settlement.active_pending_principal==Decimal('268.44')
    assert await db_session.scalar(select(func.count(Payment.id)))==0
    attempt=await db_session.get(Attempt,claim.attempt_id)
    assert CODE not in json.dumps(attempt.manual_evidence)
    for event in (await db_session.scalars(select(Event))).all():assert CODE not in json.dumps(event.evidence_snapshot)

@pytest.mark.asyncio
@pytest.mark.parametrize('code',[None,1234567890,'123','１２３４５６７８９０','0012-345678','0012 345678','00123456789'])
async def test_invalid_code_validation_never_echoes_input(db_session,monkeypatch,code,caplog):
    ctx=await fictional_zelle_context(db_session,monkeypatch);body=payload(ctx);body['code']=code
    before=await financial_counts(db_session)
    async with await client_for(db_session,ctx.customer_user) as client:
        response=await client.post(f'/payments/invoices/{ctx.invoice.id}/efs-submissions',json=body,headers={'Idempotency-Key':'invalid-code-command'})
    assert response.status_code==422,response.text
    assert 'input' not in response.text and (not isinstance(code,str) or code not in response.text)
    assert await financial_counts(db_session)==before
    assert str(code) not in caplog.text or code is None

@pytest.mark.asyncio
async def test_staff_reveal_verify_receipt_and_generic_confirmation_bypass(db_session,monkeypatch):
    ctx=await fictional_zelle_context(db_session,monkeypatch);a,s=await submit(db_session,ctx)
    async with await client_for(db_session,ctx.owner) as client:
        unsafe=await client.post(f'/payments/attempts/{a.id}/confirm',json={'expected_attempt_version':a.version,'received_amount':'168.44','reference':'GUESS'},headers={'Idempotency-Key':'generic-bypass-efs'})
        assert unsafe.status_code==409,unsafe.text
        revealed=await client.post(f'/payments/attempts/{a.id}/efs-code/reveal',json={'expected_attempt_version':a.version,'reason':'Merchant authorization review'})
        assert revealed.status_code==200,revealed.text
        assert revealed.json()['code']==CODE and 'no-store' in revealed.headers['cache-control']
        body=dict(action='confirm_received',expected_attempt_version=a.version,expected_settlement_version=s.version,reason='Merchant confirmed authorization and receipt.',merchant_authorized=True,authorization_reference='APPROVAL-NEW-123',received_amount='168.44')
        verified=await client.post(f'/payments/attempts/{a.id}/efs-verification',json=body,headers={'Idempotency-Key':'verify-exact-efs'})
        assert verified.status_code==200,verified.text
        assert verified.json()['efs']['status']=='received' and CODE not in verified.text
        replay=await client.post(f'/payments/attempts/{a.id}/efs-verification',json=body,headers={'Idempotency-Key':'verify-exact-efs'})
        assert replay.status_code==200,replay.text
    assert s.confirmed_principal==Decimal('168.44') and s.active_pending_principal==0
    payment=await db_session.scalar(select(Payment));assert payment.reference_number=='APPROVAL-NEW-123' and CODE not in str(payment.__dict__)

@pytest.mark.asyncio
@pytest.mark.parametrize('reference',['0012-345678','0012 345678','MoneyCode 0012345678','Prefix 0012-345678 suffix','MoneyCode 0012\t345678','MoneyCode 0012\n345678','MoneyCode 0012\u00a0345678'])
async def test_legacy_staff_efs_cannot_wrap_claimed_customer_code(db_session,monkeypatch,reference):
    ctx=await fictional_zelle_context(db_session,monkeypatch);await submit(db_session,ctx)
    before=await financial_counts(db_session)
    with pytest.raises(domain.SettlementDomainError) as denied:
        await domain.create_attempt(db_session,invoice=ctx.invoice,tenant=ctx.tenant,customer_id=ctx.customer.id,actor=ctx.owner,amount=Decimal('10'),rail='fleet_payment',expected_settlement_version=ctx.settlement.version,idempotency_key='legacy-wrapped-code',source='staff',subject_type='staff',subject_id=ctx.owner.id,sender_evidence={'fleet_provider':'EFS','reference_number':reference})
    assert denied.value.code=='efs_code_requires_review'
    assert await financial_counts(db_session)==before

@pytest.mark.asyncio
@pytest.mark.parametrize('amount',['NaN','Infinity','-Infinity','1e999999','1e-999999','1.001','100.009','9'*200])
async def test_invalid_exact_money_has_safe_422_in_secret_body(db_session,monkeypatch,amount):
    ctx=await fictional_zelle_context(db_session,monkeypatch);body=payload(ctx);body['amount']=amount
    async with await client_for(db_session,ctx.customer_user) as client:
        response=await client.post(f'/payments/invoices/{ctx.invoice.id}/efs-submissions',json=body,headers={'Idempotency-Key':'invalid-amount-command'})
    assert response.status_code==422 and CODE not in response.text and amount not in response.text
    assert await db_session.scalar(select(func.count(Claim.id)))==0

@pytest.mark.asyncio
async def test_hmac_replacement_and_encrypt_rotation_fail_closed_without_duplicate(db_session,monkeypatch):
    ctx=await fictional_zelle_context(db_session,monkeypatch);a,s=await submit(db_session,ctx)
    first=await db_session.scalar(select(Claim));old=json.loads(settings.EFS_INSTRUMENT_ENCRYPTION_KEYS)
    monkeypatch.setattr(settings,'EFS_INSTRUMENT_ENCRYPTION_KEYS',json.dumps({**old,'v2':Fernet.generate_key().decode()}));monkeypatch.setattr(settings,'EFS_INSTRUMENT_ENCRYPTION_ACTIVE_KEY','v2')
    assert efs_crypto.decrypt(first)==CODE
    with pytest.raises(domain.SettlementDomainError) as duplicate:await submit(db_session,ctx,key='same-code-rotated')
    assert duplicate.value.code=='efs_code_requires_review'
    monkeypatch.setattr(settings,'EFS_INSTRUMENT_FINGERPRINT_KEY',Fernet.generate_key().decode())
    with pytest.raises(domain.SettlementDomainError) as wrong:await submit(db_session,ctx,key='same-code-wrong-key')
    assert wrong.value.code=='efs_unavailable'
    assert await db_session.scalar(select(func.count(Claim.id)))==1
    with pytest.raises(efs_crypto.EfsCryptoUnavailable):efs_crypto.decrypt(first)

@pytest.mark.asyncio
@pytest.mark.parametrize('role',[UserRole.RECEPTIONIST,UserRole.MECHANIC,UserRole.SUPER_ADMIN,UserRole.CUSTOMER])
async def test_reveal_and_verification_denied_roles_without_secret_disclosure(db_session,monkeypatch,role):
    ctx=await fictional_zelle_context(db_session,monkeypatch);a,s=await submit(db_session,ctx)
    actor=SimpleNamespace(id=ctx.owner.id,tenant_id=ctx.tenant.id,role=role,permissions={'payments':True})
    async with await client_for(db_session,actor) as client:
        response=await client.post(f'/payments/attempts/{a.id}/efs-code/reveal',json={'expected_attempt_version':a.version,'reason':'Merchant review'})
    assert response.status_code==404 and CODE not in response.text
    assert await db_session.scalar(select(func.count(Event.id)).where(Event.event_type=='efs_code_revealed'))==0

@pytest.mark.asyncio
@pytest.mark.parametrize('reference',[CODE,'MoneyCode '+CODE,'Authorization 0012-345678 confirmed'])
async def test_staff_cannot_copy_bearer_into_approval_or_reason(db_session,monkeypatch,reference):
    ctx=await fictional_zelle_context(db_session,monkeypatch);a,s=await submit(db_session,ctx)
    before=await financial_counts(db_session)
    body=EfsVerify(action='confirm_received',expected_attempt_version=a.version,expected_settlement_version=s.version,reason='Merchant authorization and receipt confirmed.',merchant_authorized=True,authorization_reference=reference,received_amount='168.44')
    with pytest.raises(domain.SettlementDomainError) as denied:await efs.verify(db_session,a.id,ctx.owner,body,'bad-bearer-reference')
    assert denied.value.code=='efs_reference_invalid'
    assert await financial_counts(db_session)==before

@pytest.mark.asyncio
@pytest.mark.parametrize('actual',['100.00','150.00'])
async def test_under_and_excess_difference_resolves_bound_observation_once(db_session,monkeypatch,actual):
    from app.core import payment_step_up as step,redis as redis_store
    ctx=await fictional_zelle_context(db_session,monkeypatch);a,s=await submit(db_session,ctx,amount='120.00')
    observed=EfsVerify(action='confirm_received',expected_attempt_version=a.version,expected_settlement_version=s.version,reason='Merchant authorized and actual funds were received.',merchant_authorized=True,authorization_reference='DIFFERENT-APPROVAL-123',received_amount=actual)
    await efs.verify(db_session,a.id,ctx.owner,observed,'observe-real-difference');await db_session.commit()
    assert await efs.has_review(db_session,ctx.tenant.id,ctx.invoice.id)
    assert await db_session.scalar(select(func.count(Payment.id)))==0
    observation=await db_session.scalar(select(Event).where(Event.event_type=='efs_received_difference'))
    summary=(await efs.summaries(db_session,[a],actor=ctx.owner,audience='staff'))[a.id]
    assert summary.can_resolve_received_difference and summary.difference_review['actual_received_amount']==actual
    context=step.PaymentStepUpContext(raw_grant=None,session_jti='fictional-efs-resolution',token_version=0,current_user=ctx.owner,correlation_id=str(uuid4()))
    grant,raw=step.issue_step_up_grant(context=context,scope=step.PaymentStepUpScope.EFS_RECEIVED_DIFFERENCE,target_tenant_id=None);db_session.add(grant);await db_session.commit()
    context=step.PaymentStepUpContext(raw_grant=raw,session_jti=context.session_jti,token_version=0,current_user=ctx.owner,correlation_id=context.correlation_id)
    monkeypatch.setattr(redis_store,'get_token_version',AsyncMock(return_value=0))
    body=EfsVerify(action='resolve_received_difference',observation_id=observation.id,expected_attempt_version=a.version,expected_settlement_version=s.version,reason='Record the immutable verified merchant receipt amount.')
    await efs.verify(db_session,a.id,ctx.owner,body,'resolve-real-difference',step_up_context=context);await db_session.commit()
    await db_session.refresh(grant);assert grant.consumed_at is not None
    assert a.received_amount==Decimal(actual) and s.active_pending_principal==0
    assert s.confirmed_principal==min(Decimal(actual),Decimal('120.00'))
    assert s.unapplied_credit==max(Decimal(actual)-Decimal('120.00'),Decimal('0'))
    assert not await efs.has_review(db_session,ctx.tenant.id,ctx.invoice.id)
    await efs.verify(db_session,a.id,ctx.owner,body,'resolve-real-difference',step_up_context=None)
    assert await db_session.scalar(select(func.count(Payment.id)))==1
    if Decimal(actual)>120:
        with pytest.raises(domain.SettlementDomainError) as denied:
            await domain.create_attempt(db_session,invoice=ctx.invoice,tenant=ctx.tenant,customer_id=ctx.customer.id,actor=ctx.customer_user,amount=Decimal('1'),rail='card',expected_settlement_version=s.version,idempotency_key='new-collection-blocked',source='customer_portal',subject_type='customer',subject_id=ctx.customer_user.id)
        assert denied.value.code=='efs_unapplied_funds_review'

@pytest.mark.asyncio
async def test_manual_readiness_independent_of_card_onboarding(db_session,monkeypatch):
    ctx=await fictional_zelle_context(db_session,monkeypatch)
    ctx.tenant.stripe_onboarding_complete=False
    monkeypatch.setattr(settings,'STRIPE_CONNECT_INVOICE_PAYMENTS_APPROVED',False)
    await db_session.commit()
    capability,_=await efs.submit_capability(db_session,ctx.invoice,ctx.settlement,ctx.tenant,actor=ctx.customer_user)
    assert capability
    a,s=await submit(db_session,ctx)
    assert a.rail=='fleet_payment' and s.active_pending_principal==Decimal('168.44')

@pytest.mark.asyncio
async def test_full_middleware_never_caches_reveal_or_echoes_secret_headers(db_session,monkeypatch):
    from fastapi import FastAPI
    from app.middleware.observability import ObservabilityMiddleware
    from app.middleware.idempotency import IdempotencyMiddleware
    import app.middleware.idempotency as idem
    import app.middleware.observability as observation
    ctx=await fictional_zelle_context(db_session,monkeypatch);a,s=await submit(db_session,ctx)
    cache=AsyncMock(side_effect=AssertionError('EFS responses must never enter Redis convenience cache'));monkeypatch.setattr(idem,'get_redis',cache)
    emitted=[]
    class Logs:
        def debug(self,*args,**kwargs):emitted.append(kwargs)
        info=warning=error=debug
    monkeypatch.setattr(observation,'logger',Logs());monkeypatch.setattr(observation,'bind_contextvars',lambda **kwargs:emitted.append(kwargs))
    async with await client_for(db_session,ctx.owner) as client:
        outer=FastAPI();outer.mount('/api/v1',client._transport.app)
        client._transport.app=ObservabilityMiddleware(IdempotencyMiddleware(outer))
        headers={'Idempotency-Key':'prefix-'+CODE+'-suffix','X-Correlation-ID':CODE,'User-Agent':'accidental-'+CODE}
        url=f'/api/v1/payments/attempts/{a.id}/efs-code/reveal'
        first=await client.post(url,json={'expected_attempt_version':a.version,'reason':'Merchant authorization review'},headers=headers)
        assert first.status_code==200,first.text
        assert first.json()['code']==CODE and CODE not in str(first.headers)
        ctx.owner.role=UserRole.MECHANIC;await db_session.commit()
        second=await client.post(url,json={'expected_attempt_version':a.version,'reason':'Merchant authorization review'},headers=headers)
        assert second.status_code==404 and CODE not in second.text
        assert 'no-store' in first.headers['cache-control'] and 'no-store' in second.headers['cache-control']
    cache.assert_not_called();assert CODE not in json.dumps(emitted,default=str)

@pytest.mark.asyncio
async def test_optin_default_deny_and_gate_off_does_not_strand_existing_claim(db_session,monkeypatch):
    from app.schemas.efs_submission import EfsReveal
    ctx=await fictional_zelle_context(db_session,monkeypatch);a,s=await submit(db_session,ctx)
    monkeypatch.setattr(settings,'EFS_CUSTOMER_ENABLED_TENANT_IDS','')
    capability,_=await efs.submit_capability(db_session,ctx.invoice,s,ctx.tenant,actor=ctx.customer_user)
    assert not capability
    with pytest.raises(domain.SettlementDomainError) as denied:await submit(db_session,ctx,code='0098765432',amount='1',key='gate-off-new-code')
    assert denied.value.code=='efs_unavailable'
    raw=await efs.reveal(db_session,a.id,ctx.owner,EfsReveal(expected_attempt_version=a.version,reason='Existing merchant review'))
    assert raw['code']==CODE
    verified=EfsVerify(action='confirm_received',expected_attempt_version=a.version,expected_settlement_version=s.version,reason='Merchant confirmed the existing instrument receipt.',merchant_authorized=True,authorization_reference='EXISTING-AUTH-123',received_amount='168.44')
    await efs.verify(db_session,a.id,ctx.owner,verified,'gate-off-existing-receipt');await db_session.commit()
    assert a.state=='confirmed'

@pytest.mark.asyncio
async def test_guest_secret_submission_reauth_and_cancel_claim_is_permanent(db_session,monkeypatch):
    from app.api.v1.endpoints import invoice_access
    ctx=await fictional_zelle_context(db_session,monkeypatch)
    claims={'invoice_id':str(ctx.invoice.id),'tenant_id':str(ctx.tenant.id),'customer_id':str(ctx.customer.id)}
    consumed=AsyncMock(return_value=False);monkeypatch.setattr(invoice_access,'is_invoice_access_token_consumed',consumed)
    monkeypatch.setattr(invoice_access,'get_invoice_access_payload',AsyncMock(side_effect=lambda token:claims if token=='FICTIONAL-TOKEN' and not consumed.return_value else None))
    body={**payload(ctx),'token':'FICTIONAL-TOKEN'}
    async with await client_for(db_session,ctx.customer_user) as client:
        response=await client.post('/invoice-access/efs-submissions',json=body,headers={'Idempotency-Key':'guest-efs-command'})
        assert response.status_code==200,response.text
        result=response.json();assert not result['efs']['can_reveal'] and result['efs']['can_cancel']
        consumed.return_value=True
        revoked=await client.post('/invoice-access/efs-submissions',json=body,headers={'Idempotency-Key':'guest-efs-command'})
        assert revoked.status_code in {401,403,404,410} and CODE not in revoked.text
    # Guest cancellation uses a fresh token context, without a Zelle assertion.
    consumed.return_value=False
    from uuid import UUID
    a=await db_session.get(Attempt,UUID(result['attempt_id']));s=ctx.settlement
    from app.services.payment_attempt_resolution import execute
    from app.schemas.invoice_settlement import AttemptResolutionCommand
    command=AttemptResolutionCommand(action='cancel_unsent',reason_code='not_used',reason='This code was not used by the merchant.',expected_attempt_version=a.version,expected_settlement_version=s.version)
    await execute(db_session,a.id,command,'guest-efs-cancel',guest_invoice=ctx.invoice,guest_customer_id=ctx.customer.id);await db_session.commit()
    assert s.active_pending_principal==0 and await db_session.scalar(select(func.count(Claim.id)))==1
    from app.services.payment_attempt_resolution import project_many
    closed=(await project_many(db_session,[a],audience='guest',customer_id=ctx.customer.id))[a.id]
    assert closed.resolution_notice['message']=='To try again, use a different code or contact the shop.'
    with pytest.raises(domain.SettlementDomainError) as duplicate:await submit(db_session,ctx,key='same-code-after-cancel')
    assert duplicate.value.code=='efs_code_requires_review'
    # A genuine late merchant receipt is retained against the released request.
    late=EfsVerify(action='confirm_received',expected_attempt_version=a.version,expected_settlement_version=s.version,reason='Merchant confirmed funds received after cancellation.',merchant_authorized=True,authorization_reference='LATE-MERCHANT-AUTH',received_amount='168.44')
    await efs.verify(db_session,a.id,ctx.owner,late,'late-efs-real-receipt');await db_session.commit()
    assert a.received_amount==Decimal('168.44') and await db_session.scalar(select(func.count(Payment.id)))==1

@pytest.mark.asyncio
async def test_discrepancy_cannot_be_resolved_without_grant_or_with_overrides(db_session,monkeypatch):
    ctx=await fictional_zelle_context(db_session,monkeypatch);a,s=await submit(db_session,ctx)
    observation=EfsVerify(action='confirm_received',expected_attempt_version=a.version,expected_settlement_version=s.version,reason='Merchant authorized the actual receipt amount.',merchant_authorized=True,authorization_reference='ACTUAL-RECEIPT-AUTH',received_amount='150')
    await efs.verify(db_session,a.id,ctx.owner,observation,'observe-without-grant');await db_session.commit()
    event=await db_session.scalar(select(Event).where(Event.event_type=='efs_received_difference'))
    body=dict(action='resolve_received_difference',observation_id=str(event.id),expected_attempt_version=a.version,expected_settlement_version=s.version,reason='Record the actual merchant receipt.')
    async with await client_for(db_session,ctx.owner) as client:
        override=await client.post(f'/payments/attempts/{a.id}/efs-verification',json={**body,'received_amount':'168.44'},headers={'Idempotency-Key':'cannot-override-observation'})
        assert override.status_code==422 and CODE not in override.text
    with pytest.raises(domain.SettlementDomainError) as denied:await efs.verify(db_session,a.id,ctx.owner,EfsVerify(**body),'no-grant-difference')
    assert denied.value.code=='payment_step_up_required'
    assert await db_session.scalar(select(func.count(Payment.id)))==0 and await efs.has_review(db_session,ctx.tenant.id,ctx.invoice.id)

@pytest.mark.asyncio
async def test_bearer_cannot_be_persisted_in_later_refund_reason(db_session,monkeypatch):
    ctx=await fictional_zelle_context(db_session,monkeypatch);a,s=await submit(db_session,ctx)
    before=await financial_counts(db_session)
    with pytest.raises(domain.SettlementDomainError) as denied:
        await domain.create_refund(db_session,attempt=a,tenant_id=ctx.tenant.id,actor=ctx.owner,amount=Decimal('1'),reason='Refund MoneyCode '+CODE,idempotency_key='secret-refund-denied')
    assert denied.value.code=='efs_reference_invalid'
    assert await financial_counts(db_session)==before

@pytest.mark.asyncio
async def test_foreign_tenant_cannot_submit_reveal_or_verify_exact_claim(db_session,monkeypatch):
    own=await fictional_zelle_context(db_session,monkeypatch);foreign=await fictional_zelle_context(db_session,monkeypatch)
    a,s=await submit(db_session,own)
    before=await financial_counts(db_session)
    async with await client_for(db_session,foreign.customer_user) as client:
        response=await client.post(f'/payments/invoices/{own.invoice.id}/efs-submissions',json=payload(own,code='0098765432'),headers={'Idempotency-Key':'foreign-efs-customer'})
        assert response.status_code==404 and CODE not in response.text
    async with await client_for(db_session,foreign.owner) as client:
        response=await client.post(f'/payments/attempts/{a.id}/efs-code/reveal',json={'expected_attempt_version':a.version,'reason':'Review exact merchant authorization'})
        assert response.status_code==404 and CODE not in response.text
        response=await client.post(f'/payments/attempts/{a.id}/efs-verification',json=dict(action='reject',expected_attempt_version=a.version,expected_settlement_version=s.version,reason='Foreign review is prohibited'),headers={'Idempotency-Key':'foreign-efs-staff'})
        assert response.status_code==404 and CODE not in response.text
    assert await financial_counts(db_session)==before

@pytest.mark.asyncio
@pytest.mark.parametrize('extra',[{'history':['MoneyCode 0012\t345678']},{'MoneyCode 0012\t345678':'ignored'}])
async def test_nested_legacy_evidence_cannot_persist_claimed_moneycode(db_session,monkeypatch,extra):
    ctx=await fictional_zelle_context(db_session,monkeypatch);await submit(db_session,ctx)
    before=await financial_counts(db_session)
    with pytest.raises(domain.SettlementDomainError) as denied:
        await domain.create_attempt(db_session,invoice=ctx.invoice,tenant=ctx.tenant,customer_id=ctx.customer.id,actor=ctx.owner,amount=Decimal('10'),rail='fleet_payment',expected_settlement_version=ctx.settlement.version,idempotency_key='nested-protected-code',source='staff',subject_type='staff',subject_id=ctx.owner.id,sender_evidence={'fleet_provider':'EFS','reference_number':'OTHER-REFERENCE','extra':extra})
    assert denied.value.code=='efs_code_requires_review'
    assert await financial_counts(db_session)==before

@pytest.mark.asyncio
async def test_real_main_asgi_preserves_efs_private_headers_on_success_denial_and_validation(db_session,monkeypatch):
    import httpx
    from app.main import app
    from app.core.dependencies import get_db,get_current_active_user
    import app.middleware.throttling as throttling
    import app.middleware.idempotency as idem
    ctx=await fictional_zelle_context(db_session,monkeypatch);a,s=await submit(db_session,ctx)
    class UnavailableThrottle:
        def pipeline(self):raise RuntimeError('fictional test throttle unavailable')
    monkeypatch.setattr(throttling,'get_redis',AsyncMock(return_value=UnavailableThrottle()))
    cache=AsyncMock(side_effect=AssertionError('Private EFS route must bypass convenience caching'))
    monkeypatch.setattr(idem,'get_redis',cache)
    previous=dict(app.dependency_overrides)
    async def dependency():yield db_session
    app.dependency_overrides[get_db]=dependency
    app.dependency_overrides[get_current_active_user]=lambda:ctx.owner
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
            url=f'/api/v1/payments/attempts/{a.id}/efs-code/reveal'
            body={'expected_attempt_version':a.version,'reason':'Merchant authorization review'}
            headers={'Idempotency-Key':'full-asgi-reveal-'+CODE,'X-Correlation-ID':CODE}
            first=await client.post(url,json=body,headers=headers)
            invalid=await client.post(url,json={**body,'expected_attempt_version':CODE},headers=headers)
            ctx.owner.role=UserRole.MECHANIC;await db_session.commit()
            denied=await client.post(url,json=body,headers=headers)
            oversized=await client.post(url,json=body,headers={**headers,'Content-Length':str(settings.MAX_REQUEST_BODY_BYTES+1)})
            assert oversized.status_code==413,oversized.text
            assert [first.status_code,invalid.status_code,denied.status_code]==[200,422,404],(first.text,invalid.text,denied.text)
            assert first.json()['code']==CODE and CODE not in invalid.text+denied.text
            for response in (first,invalid,denied,oversized):
                assert response.headers['referrer-policy']=='no-referrer'
                assert 'no-store' in response.headers['cache-control'] and 'private' in response.headers['cache-control']
                assert response.headers['pragma']=='no-cache' and CODE not in str(response.headers)
            cache.assert_not_called()
    finally:
        app.dependency_overrides.clear();app.dependency_overrides.update(previous)
