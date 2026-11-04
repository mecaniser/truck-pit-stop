"""Real PostgreSQL transactions; explicit NEW disposable database only, no IO."""
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from sqlalchemy import select,func
from test_booking_readiness_legacy_mirrors_postgres import pg_readiness
from test_zelle_explicit_confirmation import (
    fictional_zelle_context,client_for,financial_counts,
    test_archived_collection_actual_staff_reads_and_exact_confirmation_never_full_invoice as archived_check,
    test_pure_refresh_and_queue_do_not_flush_unrelated_pending_payment_or_create_missing_projection as readonly_check,
)
from app.core.config import settings
from app.db.models.automated_sms import AutomatedSMSOperation
from app.db.models.notification import Notification
from app.db.models.invoice_settlement import InvoicePaymentAttempt
from app.services import automated_sms_service as sms
from app.services import invoice_settlement_service as domain

@pytest.fixture(autouse=True)
def no_broadcast(monkeypatch):
    import app.core.websocket as websocket
    monkeypatch.setattr(websocket,'broadcast_repair_order_update',AsyncMock())

@pytest.mark.asyncio
async def test_pg_archived_exact_source_routes_and_partial_confirmation(pg_readiness,monkeypatch):
    await archived_check(pg_readiness,monkeypatch)

@pytest.mark.asyncio
async def test_pg_readonly_refresh_never_autoflushes(pg_readiness,monkeypatch):
    await readonly_check(pg_readiness,monkeypatch)

async def report(db,ctx,key='pg-explicit-report'):
    return await domain.create_attempt(db,invoice=ctx.invoice,tenant=ctx.tenant,customer_id=ctx.customer.id,actor=ctx.customer_user,amount=Decimal('168.44'),rail='zelle',expected_settlement_version=ctx.settlement.version,idempotency_key=key,source='customer_portal',subject_type='customer',subject_id=ctx.customer_user.id,transfer_sent_confirmed=True)

@pytest.mark.asyncio
@pytest.mark.parametrize('collection',[False,True])
async def test_pg_report_transaction_dedupes_exact_notice_and_dispatches_mock_only(pg_readiness,monkeypatch,collection):
    db=pg_readiness
    ctx=await fictional_zelle_context(db,monkeypatch,collection=collection,prior_card='confirmed')
    ctx.tenant.sms_enabled=True;ctx.tenant.messaging_enabled=True
    ctx.tenant.sms_phone_number='+15005550111';ctx.owner.phone='+15005550777'
    await db.commit();monkeypatch.setattr(settings,'SMS_AUTOMATION_OUTBOX_ENABLED',True)
    creation=await report(db,ctx);await db.commit()
    replay=await report(db,ctx);await db.commit()
    assert replay.replayed and replay.attempt.id==creation.attempt.id
    operations=(await db.scalars(select(AutomatedSMSOperation))).all()
    assert len(operations)==1
    op=operations[0]
    assert '$168.44' in op.body and '$268.44' not in op.body
    assert 'not verified receipt' in op.body
    assert op.recipient_id==ctx.owner.id
    assert await db.scalar(select(func.count(Notification.id)))==1
    class Sender:
        ready=True
        calls=0
        async def send(self,**kwargs):
            self.calls+=1
            return {'sid':'SM'+uuid4().hex,'status':'queued'}
    sender=Sender()
    await sms.dispatch_automated_operation(db,op.id,sender)
    assert sender.calls==1,(op.state,op.error_code)
    assert op.state=='accepted'
    await sms.dispatch_automated_operation(db,op.id,sender)
    assert sender.calls==1
    await db.refresh(ctx.invoice)
    assert ctx.invoice.zelle_pending_submitted_at is None

@pytest.mark.asyncio
async def test_pg_failed_enqueue_rolls_back_report_money_reservation_and_notice(pg_readiness,monkeypatch):
    db=pg_readiness;ctx=await fictional_zelle_context(db,monkeypatch)
    ctx.tenant.sms_enabled=True;ctx.tenant.messaging_enabled=True
    ctx.tenant.sms_phone_number='+15005550111';ctx.owner.phone='+15005550777'
    await db.commit();monkeypatch.setattr(settings,'SMS_AUTOMATION_OUTBOX_ENABLED',True)
    before=await financial_counts(db)
    import app.services.zelle_transfer_reports as notices
    original_enqueue=notices.enqueue_report_notice
    async def failure(*args,**kwargs):
        await original_enqueue(*args,**kwargs)
        await db.flush()
        assert await db.scalar(select(func.count(AutomatedSMSOperation.id)))==1
        raise RuntimeError('fictional durable enqueue failure')
    monkeypatch.setattr(notices,'enqueue_report_notice',failure)
    with pytest.raises(RuntimeError,match='durable enqueue'):
        await report(db,ctx)
    await db.rollback()
    assert await financial_counts(db)==before
    assert await db.scalar(select(func.count(InvoicePaymentAttempt.id)))==0

@pytest.mark.asyncio
async def test_pg_concurrent_same_command_has_one_reservation_and_notice(pg_readiness,monkeypatch):
    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker
    db=pg_readiness
    assert db.bind.dialect.name=='postgresql'
    ctx=await fictional_zelle_context(db,monkeypatch)
    ctx.tenant.sms_enabled=True;ctx.tenant.messaging_enabled=True
    ctx.tenant.sms_phone_number='+15005550111';ctx.owner.phone='+15005550777'
    await db.commit();monkeypatch.setattr(settings,'SMS_AUTOMATION_OUTBOX_ENABLED',True)
    sessions=async_sessionmaker(db.bind,expire_on_commit=False,autoflush=False)
    async def execute():
        async with sessions() as separate:
            try:
                creation=await report(separate,ctx,key='pg-concurrent-report')
                await separate.commit();return creation.attempt.id
            except domain.SettlementDomainError as error:
                await separate.rollback()
                assert error.code=='invoice_busy'
                return None
    ids=await asyncio.gather(execute(),execute())
    replay_id=await execute()
    assert replay_id is not None and {identity for identity in ids if identity}=={replay_id}
    assert await db.scalar(select(func.count(InvoicePaymentAttempt.id)))==1
    assert await db.scalar(select(func.count(AutomatedSMSOperation.id)))==1
    assert await db.scalar(select(func.count(Notification.id)))==1


@pytest.mark.asyncio
async def test_pg_financial_notice_recipient_demotion_is_rechecked_before_mock_transport(pg_readiness,monkeypatch):
    from app.db.models.user import UserRole
    db=pg_readiness
    assert db.bind.dialect.name=='postgresql'
    ctx=await fictional_zelle_context(db,monkeypatch)
    ctx.tenant.sms_enabled=True;ctx.tenant.messaging_enabled=True
    ctx.tenant.sms_phone_number='+15005550111';ctx.owner.phone='+15005550777'
    await db.commit();monkeypatch.setattr(settings,'SMS_AUTOMATION_OUTBOX_ENABLED',True)
    await report(db,ctx);await db.commit()
    op=await db.scalar(select(AutomatedSMSOperation))
    assert op.recipient_id==ctx.owner.id and op.state=='pending'
    ctx.owner.role=UserRole.MECHANIC;await db.commit()
    class Sender:
        ready=True
        send=AsyncMock(side_effect=AssertionError('A demoted recipient must not receive financial SMS'))
    sender=Sender()
    result=await sms.dispatch_automated_operation(db,op.id,sender)
    assert result=='rejected'
    assert op.state=='rejected' and op.error_code=='recipient_unavailable'
    sender.send.assert_not_called()

@pytest.mark.asyncio
@pytest.mark.parametrize('eligible',[False,True])
async def test_pg_explicit_report_persists_with_mixed_or_no_consented_destinations(pg_readiness,monkeypatch,eligible):
    import json
    from datetime import datetime,timezone
    from app.db.models.user import User,UserRole
    from app.db.models.messaging_business import MessagingBusiness,TenantSMSBinding,SMSConsentEvidence
    from app.services.zelle_transfer_reports import review_queue
    db=pg_readiness
    assert db.bind.dialect.name=='postgresql'
    ctx=await fictional_zelle_context(db,monkeypatch)
    ctx.tenant.sms_enabled=True;ctx.tenant.messaging_enabled=True
    ctx.owner.phone='+15005550777'
    admin=User(tenant_id=ctx.tenant.id,first_name='Fictional',last_name='Admin',email=f'{uuid4()}@example.test',phone='+15005550778',role=UserRole.GARAGE_ADMIN,hashed_password='disabled',is_active=True)
    db.add(admin)
    db.add(User(tenant_id=ctx.tenant.id,first_name="Invalid",last_name="Destination",email=f"{uuid4()}@example.test",phone="not-a-number",role=UserRole.RECEPTIONIST,hashed_password="disabled",is_active=True))
    business=MessagingBusiness(tenant_id=ctx.tenant.id,legal_name='Fictional consent test LLC');db.add(business);await db.flush()
    account='AC'+uuid4().hex
    db.add(TenantSMSBinding(tenant_id=ctx.tenant.id,business_id=business.id,account_sid=account,customer_profile_sid='BU'+uuid4().hex,brand_sid='BN'+uuid4().hex,campaign_sid='QE'+uuid4().hex,messaging_service_sid='MG'+uuid4().hex,sender_sid='PN'+uuid4().hex,sender_phone='+15005550111',credential_ref=str(ctx.tenant.id),registration_status='approved',enabled=True,verified_at=datetime.now(timezone.utc),revision=1))
    db.add(SMSConsentEvidence(tenant_id=ctx.tenant.id,recipient_kind='user',recipient_id=ctx.owner.id,phone=ctx.owner.phone,purpose='service_notifications',status='withdrawn',source='synthetic',disclosure_version='1',collected_at=datetime.now(timezone.utc),actor_id=ctx.owner.id))
    if eligible:
        db.add(SMSConsentEvidence(tenant_id=ctx.tenant.id,recipient_kind='user',recipient_id=admin.id,phone=admin.phone,purpose='service_notifications',status='granted',source='synthetic',disclosure_version='1',collected_at=datetime.now(timezone.utc),actor_id=ctx.owner.id))
    await db.commit()
    monkeypatch.setattr(settings,'SMS_AUTOMATION_OUTBOX_ENABLED',True)
    monkeypatch.setattr(settings,'SMS_TENANT_ROUTING_ENABLED',True)
    monkeypatch.setattr(settings,'SMS_TENANT_CREDENTIALS_JSON',json.dumps({str(ctx.tenant.id):{'account_sid':account,'auth_token':'synthetic-not-a-provider-credential'}}))
    payload={'amount':'168.44','rail':'zelle','expected_settlement_version':ctx.settlement.version,'transfer_sent_confirmed':True}
    async with await client_for(db,ctx.customer_user) as client:
        response=await client.post(f'/payments/invoices/{ctx.invoice.id}/attempts',json=payload,headers={'Idempotency-Key':'consent-filtered-report'})
    assert response.status_code==200,response.text
    operations=(await db.scalars(select(AutomatedSMSOperation))).all()
    assert len(operations)==int(eligible)
    if eligible:assert operations[0].recipient_id==admin.id
    assert await db.scalar(select(func.count(Notification.id)))==int(eligible)
    rows=(await review_queue(db,ctx.owner))['rows']
    assert len(rows)==1 and rows[0]['report_status']=='explicit_report'
    assert rows[0]['principal_amount']=='168.44'
    assert ctx.settlement.active_pending_principal==Decimal('168.44')
