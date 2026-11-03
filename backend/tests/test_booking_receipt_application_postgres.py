"""Actual199/200 atomic issuance and two-connection application races."""
import asyncio,importlib.util,ast
from pathlib import Path
from uuid import UUID
import pytest,pytest_asyncio
from sqlalchemy import text,select,func
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.db.models.appointment import Appointment
from app.db.models.invoice import Invoice
from app.db.models.payment import Payment
from app.db.models.booking_application import BookingReceiptApplication
from app.db.models.invoice_settlement import InvoiceSettlement
from app.api.v1.endpoints.appointments import BookingReceiptApplyBody
from app.services.booking_receipt_application import issue_and_apply,prepayment_view
from test_booking_fulfillment_postgres import pg_fulfillment,pg_booking
from test_booking_receipt_application import prepared
from unittest.mock import AsyncMock

@pytest_asyncio.fixture
async def pg_application(pg_fulfillment):
    factory,setup,staff=pg_fulfillment
    async with factory() as db:
        for table in ['booking_accounting_review_events','booking_accounting_review_tasks','booking_receipt_applications']:await db.execute(text(f'DROP TABLE {table} CASCADE'))
        await db.execute(text('DROP INDEX IF EXISTS ix_booking_receipt_tenant_received'))
        await db.execute(text('ALTER TABLE booking_receipts DROP COLUMN version CASCADE'))
        await db.execute(text('ALTER TABLE booking_payment_events DROP COLUMN verified_refund_amount_minor CASCADE'))
        await db.execute(text('ALTER TABLE booking_payment_events DROP COLUMN verified_dispute_amount_minor CASCADE'))
        await db.execute(text('ALTER TABLE booking_payment_events DROP COLUMN verified_refund_delta_minor CASCADE'))
        for name in ['client_idempotency_key','request_sha256','provider_refund_reference']:await db.execute(text(f'ALTER TABLE booking_payment_events DROP COLUMN {name} CASCADE'))
        # Install the real198 confirmation trigger so200 exercises its exact
        # UPDATE-only exception as well as its new application constraints.
        source=ast.parse((Path(__file__).parents[1]/'alembic/versions/198_verified_booking_payments.py').read_text())
        for node in ast.walk(source):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='execute' and node.args and isinstance(node.args[0],ast.Constant):
                sql=node.args[0].value
                if isinstance(sql,str) and (sql.startswith('CREATE FUNCTION guard_booking_confirmation()') or sql.startswith('CREATE TRIGGER verified_booking_confirmation ')):
                    await db.execute(text(sql))
        connection=await db.connection()
        spec=importlib.util.spec_from_file_location('booking_migration200',Path(__file__).parents[1]/'alembic/versions/200_booking_receipt_applications.py')
        migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        def upgrade(sync):
            with Operations.context(MigrationContext.configure(sync)):migration.upgrade()
        await connection.run_sync(upgrade);await db.commit()
    return factory,setup,staff

def fake_notifications(monkeypatch):
    import app.services.service_checklist as checklist
    import app.api.v1.endpoints.invoices as invoices
    import app.services.fleet_financial_wakeup as wakeup
    monkeypatch.setattr(checklist,'guard_completion',AsyncMock())
    monkeypatch.setattr(invoices,'enqueue_invoice_created_email',AsyncMock(return_value=False))
    monkeypatch.setattr(invoices,'enqueue_quickbooks_invoice_sync',AsyncMock())
    monkeypatch.setattr(wakeup,'enqueue_financial_wakeup',AsyncMock())
    monkeypatch.setattr(wakeup,'enqueue_settlement_wakeup',AsyncMock())

@pytest.mark.asyncio
@pytest.mark.parametrize('same_key',[True,False])
async def test_competing_real_native_issuance_applies_once(pg_application,monkeypatch,same_key):
    factory,setup,staff=pg_application;fake_notifications(monkeypatch)
    async with factory() as db:
        apt,order=await prepared(db,setup,staff,monkeypatch);identity=apt.id
        view=await prepayment_view(db,apt)
        body=BookingReceiptApplyBody(repair_order_id=order.id,receipt_id=apt.confirmed_receipt_id,expected_booking_version=apt.booking_version,expected_receipt_version=1,amount_minor=12000,expected_invoice_economics_sha256=view['invoice_preview']['invoice_economics_sha256'],accounting_mode='external_manual')
    async def one(key):
        async with factory() as db:
            try:return await issue_and_apply(db,staff,identity,body,key)
            except Exception as exc:await db.rollback();return exc
    results=await asyncio.gather(one('pg-application-first'),one('pg-application-first' if same_key else 'pg-application-second'))
    assert isinstance(results[0],dict) or isinstance(results[1],dict),results
    if same_key:
        replay=await one('pg-application-first')
        assert isinstance(replay,dict),replay
        assert replay['application_id']==next(row['application_id'] for row in results if isinstance(row,dict))
    async with factory() as db:
        assert await db.scalar(select(func.count(Invoice.id)))==1
        assert await db.scalar(select(func.count(BookingReceiptApplication.id)))==1
        assert await db.scalar(select(func.count(Payment.id)))==0
        settlement=await db.scalar(select(InvoiceSettlement));assert int(settlement.confirmed_principal*100)==12000
        apt=await db.get(Appointment,identity);view=await prepayment_view(db,apt)
        assert view['receipt']['unapplied_minor']==0
        assert view['invoice_payment_summary']['prepayment_applied_amount']=='120.00'

@pytest.mark.asyncio
async def test_task_failure_real_pg_rolls_back_entire_sale(pg_application,monkeypatch):
    factory,setup,staff=pg_application;fake_notifications(monkeypatch)
    async with factory() as db:
        apt,order=await prepared(db,setup,staff,monkeypatch)
        view=await prepayment_view(db,apt)
        body=BookingReceiptApplyBody(repair_order_id=order.id,receipt_id=apt.confirmed_receipt_id,expected_booking_version=apt.booking_version,expected_receipt_version=1,amount_minor=12000,expected_invoice_economics_sha256=view['invoice_preview']['invoice_economics_sha256'],accounting_mode='external_manual')
        import app.services.booking_receipt_application as applications
        monkeypatch.setattr(applications,'ensure_manual_accounting_tasks',AsyncMock(side_effect=RuntimeError('pg synthetic task failure')))
        with pytest.raises(RuntimeError):await issue_and_apply(db,staff,apt.id,body,'pg-rollback-application')
        await db.rollback()
    async with factory() as db:
        assert await db.scalar(select(func.count(Invoice.id)))==0
        assert await db.scalar(select(func.count(BookingReceiptApplication.id)))==0
        assert await db.scalar(select(func.count(InvoiceSettlement.id)))==0

@pytest.mark.asyncio
async def test_real_qbo_refund_after_application_retains_provider_fact_and_invalidates_paid_summary(pg_application,monkeypatch):
    factory,setup,staff=pg_application;fake_notifications(monkeypatch)
    from decimal import Decimal
    from types import SimpleNamespace
    from app.db.models.booking_payment import BookingReceipt,BookingPaymentAttempt,BookingPaymentEvent
    from app.api.v1.endpoints.appointments import BookingRefundVerificationBody
    from app.services import booking_payments as booking
    from app.services.booking_refund_verification import verify_existing_refund
    from test_verified_booking_flow import result
    import app.services.booking_refund_verification as verification
    async with factory() as db:
        apt,order=await prepared(db,setup,staff,monkeypatch)
        view=await prepayment_view(db,apt)
        body=BookingReceiptApplyBody(repair_order_id=order.id,receipt_id=apt.confirmed_receipt_id,expected_booking_version=apt.booking_version,expected_receipt_version=1,amount_minor=12000,expected_invoice_economics_sha256=view['invoice_preview']['invoice_economics_sha256'],accounting_mode='external_manual')
        await issue_and_apply(db,staff,apt.id,body,'pg-apply-before-refund')
        settlement=await db.scalar(select(InvoiceSettlement));old_version=settlement.version
        receipt=await db.scalar(select(BookingReceipt));attempt=await db.scalar(select(BookingPaymentAttempt))
        monkeypatch.setattr(booking.provider,'retrieve_booking_payment',AsyncMock(return_value=result(apt,attempt,provider_id=attempt.provider_intent_id)))
        monkeypatch.setattr(booking.provider,'_connection',AsyncMock(return_value=SimpleNamespace(realm_id='realm-fixture')))
        monkeypatch.setattr(booking.provider,'_healthy_qbo',lambda connection:True)
        monkeypatch.setattr(verification.qbp,'get_refund',AsyncMock(return_value=SimpleNamespace(id='actual-known-refund',status='SETTLED',amount=Decimal('25.00'),raw={'id':'actual-known-refund','status':'SETTLED','amount':'25.00'})))
        response=await verify_existing_refund(db,staff,apt.id,BookingRefundVerificationBody(refund_id='actual-known-refund',expected_receipt_version=receipt.version,expected_booking_version=apt.booking_version),'pg-verify-provider-refund')
        assert receipt.refunded_amount_minor==2500 and apt.status.value=='confirmed'
        assert response['invoice_payment_summary']['state']=='unknown'
        assert response['invoice_payment_summary']['payment_verification_required']
        assert response['receipt']['applied_minor']==12000 and not response['can_apply']
        assert response['refund_verification']['state']=='verified'
        await db.refresh(settlement)
        assert settlement.version==old_version+1 and settlement.confirmed_principal==Decimal('120')
        assert await db.scalar(select(func.count(BookingReceiptApplication.id)))==1
        assert await db.scalar(select(func.count(Payment.id)))==0

@pytest.mark.asyncio
async def test_verified_refund_read_racing_application_records_fresh_fact_then_returns_conflict(pg_application,monkeypatch):
    factory,setup,staff=pg_application;fake_notifications(monkeypatch)
    from decimal import Decimal
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.db.models.booking_payment import BookingReceipt,BookingPaymentAttempt
    from app.api.v1.endpoints.appointments import BookingRefundVerificationBody
    from app.services import booking_payments as booking
    from app.services.booking_refund_verification import verify_existing_refund
    from test_verified_booking_flow import result
    import app.services.booking_refund_verification as verification
    async with factory() as db:
        apt,order=await prepared(db,setup,staff,monkeypatch);identity=apt.id
        view=await prepayment_view(db,apt)
        apply_body=BookingReceiptApplyBody(repair_order_id=order.id,receipt_id=apt.confirmed_receipt_id,expected_booking_version=apt.booking_version,expected_receipt_version=1,amount_minor=12000,expected_invoice_economics_sha256=view['invoice_preview']['invoice_economics_sha256'],accounting_mode='external_manual')
        refund_body=BookingRefundVerificationBody(refund_id='racing-known-refund',expected_receipt_version=1,expected_booking_version=apt.booking_version)
        attempt=await db.scalar(select(BookingPaymentAttempt));evidence=result(apt,attempt,provider_id=attempt.provider_intent_id)
    monkeypatch.setattr(booking.provider,'retrieve_booking_payment',AsyncMock(return_value=evidence))
    monkeypatch.setattr(booking.provider,'_connection',AsyncMock(return_value=SimpleNamespace(realm_id='realm-fixture')))
    monkeypatch.setattr(booking.provider,'_healthy_qbo',lambda connection:True)
    started=asyncio.Event();release=asyncio.Event()
    async def read_refund(**kwargs):
        started.set();await release.wait()
        return SimpleNamespace(id='racing-known-refund',status='SETTLED',amount=Decimal('25.00'),raw={'id':'racing-known-refund','status':'SETTLED','amount':'25.00'})
    monkeypatch.setattr(verification.qbp,'get_refund',AsyncMock(side_effect=read_refund))
    async def verify():
        async with factory() as db:
            try:return await verify_existing_refund(db,staff,identity,refund_body,'pg-racing-refund-verification')
            except HTTPException as exc:return exc
    pending=asyncio.create_task(verify())
    await asyncio.wait_for(started.wait(),5)
    try:
        async with factory() as db:await issue_and_apply(db,staff,identity,apply_body,'pg-apply-during-provider-get')
    finally:release.set()
    conflict=await pending
    assert isinstance(conflict,HTTPException) and conflict.status_code==409
    async with factory() as db:
        receipt=await db.scalar(select(BookingReceipt));assert receipt.refunded_amount_minor==2500
        assert await db.scalar(select(func.count(BookingReceiptApplication.id)))==1
        apt=await db.get(Appointment,identity);view=await prepayment_view(db,apt)
        assert view['invoice_payment_summary']['state']=='unknown' and apt.status.value=='confirmed'

@pytest.mark.asyncio
async def test_signed_dispute_preserves_completed_lifecycle_and_invalidates_application_once(pg_application,monkeypatch):
    factory,setup,staff=pg_application;fake_notifications(monkeypatch)
    from dataclasses import replace
    from app.db.models.booking_payment import BookingPaymentAttempt,BookingReceipt
    from app.db.models.invoice_settlement import TenantPaymentProviderConfiguration
    from app.db.models.appointment import AppointmentStatus
    from app.services import booking_payments as booking
    from app.services.booking_payment_provider import BookingProviderCapability
    from app.db.models.repair_order import RepairOrderStatus
    from uuid import uuid4
    chosen=replace(setup[5],provider='stripe_connect',account_id='acct_pg_dispute',configuration_version=2)
    async with factory() as db:
        config=await db.scalar(select(TenantPaymentProviderConfiguration));config.is_active=False;config.deactivated_at=booking.now()
        db.add(TenantPaymentProviderConfiguration(tenant_id=chosen.tenant_id,version=2,selected_provider=chosen.provider,readiness_state='ready',is_active=True,actor_user_id=setup[3].id,actor_name_snapshot='Synthetic',provider_account_snapshot=chosen.account_id,qbo_realm_snapshot='realm-fixture',writer_strategy='dieselbridge',idempotency_key=str(uuid4()),request_hash='b'*64));await db.commit()
        monkeypatch.setattr(booking.provider,'booking_provider_capability',AsyncMock(return_value=BookingProviderCapability(True,chosen)))
        apt,order=await prepared(db,setup,staff,monkeypatch)
        apt.status=AppointmentStatus.COMPLETED;await db.commit()
        view=await prepayment_view(db,apt)
        body=BookingReceiptApplyBody(repair_order_id=order.id,receipt_id=apt.confirmed_receipt_id,expected_booking_version=apt.booking_version,expected_receipt_version=1,amount_minor=12000,expected_invoice_economics_sha256=view['invoice_preview']['invoice_economics_sha256'],accounting_mode='external_manual')
        await issue_and_apply(db,staff,apt.id,body,'pg-apply-before-dispute')
        attempt=await db.scalar(select(BookingPaymentAttempt))
        settlement=await db.scalar(select(InvoiceSettlement));old_version=settlement.version
        event={'id':'evt_genuine_dispute','type':'charge.dispute.created','account':chosen.account_id,'livemode':False,'data':{'object':{'id':'dp_bound','charge':attempt.provider_charge_id,'payment_intent':attempt.provider_intent_id,'amount':12000,'currency':'usd','status':'needs_response'}}}
        assert await booking.dispatch_connect_event(db,event)
        assert apt.status==AppointmentStatus.COMPLETED and apt.booking_payment_state=='payment_received_review'
        await db.refresh(settlement);assert settlement.version==old_version+1
        receipt=await db.scalar(select(BookingReceipt));assert receipt.refunded_amount_minor==0
        assert await booking.dispatch_connect_event(db,event)
        await db.refresh(settlement);assert settlement.version==old_version+1
        view=await prepayment_view(db,apt)
        assert view['invoice_payment_summary']['state']=='unknown'

@pytest.mark.asyncio
@pytest.mark.parametrize('invoice_minor,fail_after_queue',[(12000,False),(18000,False),(18000,True)])
async def test_actual_endpoint_real_publication_queue_is_atomic_and_async_safe(pg_application,monkeypatch,invoice_minor,fail_after_queue):
    """Exercise real publication helpers; no provider worker or delivery runs."""
    from decimal import Decimal
    import httpx
    from fastapi import FastAPI
    from app.api.v1.endpoints import appointments,invoices
    from app.core.dependencies import get_db,get_current_active_user
    from app.core.config import settings
    from app.db.models.labor import Labor
    from app.db.models.notification import Notification
    from app.db.models.provider_outbox import ProviderOutboxEvent
    factory,setup,staff=pg_application
    monkeypatch.setattr(settings,'PROVIDER_OUTBOX_ENABLED',True)
    monkeypatch.delenv('DIESELBRIDGE_FLEET_WEBHOOKS',raising=False)
    async with factory() as db:
        apt,order=await prepared(db,setup,staff,monkeypatch)
        line=await db.scalar(select(Labor));line.total_cost=Decimal(invoice_minor)/100;line.hourly_rate=line.total_cost
        await db.commit()
        view=await prepayment_view(db,apt);identity=apt.id
        body=BookingReceiptApplyBody(repair_order_id=order.id,receipt_id=apt.confirmed_receipt_id,expected_booking_version=apt.booking_version,expected_receipt_version=1,amount_minor=12000,expected_invoice_economics_sha256=view['invoice_preview']['invoice_economics_sha256'],accounting_mode='external_manual')
    if fail_after_queue:
        original=invoices.enqueue_email_notification
        async def queue_then_fail(*args,**kwargs):
            await original(*args,**kwargs)
            raise RuntimeError('synthetic failure after real publication enqueue')
        monkeypatch.setattr(invoices,'enqueue_email_notification',queue_then_fail)
    async def request_session():
        async with factory() as db:yield db
    app=FastAPI();app.include_router(appointments.router,prefix='/appointments')
    app.dependency_overrides[get_db]=request_session
    app.dependency_overrides[get_current_active_user]=lambda:staff
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,raise_app_exceptions=not fail_after_queue),base_url='http://testserver') as client:
        response=await client.post(f'/appointments/{identity}/issue-invoice-with-prepayment',json=body.model_dump(mode='json'),headers={'Idempotency-Key':'pg-real-publication-endpoint'})
        assert response.status_code==(500 if fail_after_queue else 200),response.text
    async with factory() as db:
        expected=0 if fail_after_queue else 1
        assert await db.scalar(select(func.count(Invoice.id)))==expected
        assert await db.scalar(select(func.count(BookingReceiptApplication.id)))==expected
        assert await db.scalar(select(func.count(InvoiceSettlement.id)))==expected
        assert await db.scalar(select(func.count(Notification.id)))==expected
        assert await db.scalar(select(func.count(ProviderOutboxEvent.id)))==expected
        assert await db.scalar(select(func.count(Payment.id)))==0
        if expected:
            notification=await db.scalar(select(Notification))
            assert 'Prepayment applied' in notification.body
            assert response.json()['invoice_payment_summary']['prepayment_applied_amount']=='120.00'
            invoice=await db.scalar(select(Invoice))
            assert invoice.status.value==('paid' if invoice_minor==12000 else 'sent')
