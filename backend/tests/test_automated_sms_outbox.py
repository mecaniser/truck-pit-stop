"""Real PostgreSQL outbox acceptance using only isolated synthetic recipients."""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select, func

pytestmark = pytest.mark.skipif(os.getenv('COMMUNICATIONS_ISOLATED_LOCAL') != '1', reason='requires dedicated isolated PostgreSQL')


@pytest_asyncio.fixture(autouse=True)
async def isolated_lifecycle():
    yield
    if os.getenv('COMMUNICATIONS_ISOLATED_LOCAL') == '1':
        from app.db.session import engine
        await engine.dispose()


class Sender:
    ready = True
    calls = 0
    outcome = 'accepted'

    async def send(self, **kwargs):
        self.calls += 1
        await asyncio.sleep(0.01)
        if self.outcome == 'unknown':
            raise TimeoutError()
        if self.outcome == 'rejected':
            from twilio.base.exceptions import TwilioRestException
            raise TwilioRestException(400, 'test', code=21610, msg='synthetic opt out')
        if self.outcome == 'no_receipt':
            return {}
        return {'sid': 'SM' + uuid4().hex, 'status': 'queued'}


async def seed():
    from app.db.session import AsyncSessionLocal
    from app.db.models.tenant import Tenant
    from app.db.models.customer import Customer
    from app.db.models.user import User
    tid, cid, uid = uuid4(), uuid4(), uuid4()
    async with AsyncSessionLocal() as db:
        tenant = Tenant(id=tid, name='Outbox synthetic', slug=f'auto-{tid}', sms_enabled=True, messaging_enabled=True, sms_phone_number='+1' + str(2000000000 + tid.int % 7000000000), phone='+15005550999')
        db.add(tenant)
        await db.flush()
        db.add_all([Customer(id=cid, tenant_id=tid, first_name='Synthetic', last_name='Recipient', email=f'{cid}@example.test', phone='+15005550888'), User(id=uid, tenant_id=tid, first_name='Synthetic', last_name='Mechanic', email=f'{uid}@example.test', phone='+15005550777', role='mechanic', hashed_password='disabled', is_active=True)])
        await db.commit()
    return tid, cid, uid


def request(tid, cid, *, event='work:1', **kwargs):
    return dict(tenant_id=tid, customer_id=cid, domain_event_id=event, template_name='work_started_sms', to='+15005550888', body='Synthetic work started', **kwargs)


@pytest.mark.asyncio
async def test_concurrent_domain_replay_one_intent_and_one_provider_call():
    from app.db.session import AsyncSessionLocal
    from app.services import automated_sms_service as svc
    from app.db.models.automated_sms import AutomatedSMSOperation
    from app.db.models.sms_message import SMSMessage
    tid, cid, _ = await seed()
    async def enqueue():
        async with AsyncSessionLocal() as db:
            op = await svc.enqueue_automated_sms(db, **request(tid, cid))
            await db.commit()
            return op.id
    ids = await asyncio.gather(*(enqueue() for _ in range(4)))
    assert len(set(ids)) == 1
    sender = Sender()
    async def tick():
        async with AsyncSessionLocal() as db:
            return await svc.process_pending_automated_operations(db, sender, tenant_id=tid)
    await asyncio.gather(tick(), tick(), tick())
    await tick()
    assert sender.calls == 1
    async with AsyncSessionLocal() as db:
        op = await db.get(AutomatedSMSOperation, ids[0])
        assert op.state == 'accepted' and op.attempt_count == 1
        assert await db.scalar(select(func.count()).select_from(SMSMessage).where(SMSMessage.tenant_id == tid)) == 1
        later = await svc.enqueue_automated_sms(db, **request(tid, cid, event='work:2'))
        await db.commit()
        assert later.id != op.id
    await tick()
    assert sender.calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('changed', ['body', 'to', 'sender'])
async def test_replay_changed_payload_conflicts(changed):
    from app.db.session import AsyncSessionLocal
    from app.services import automated_sms_service as svc
    from app.db.models.tenant import Tenant
    tid, cid, _ = await seed()
    async with AsyncSessionLocal() as db:
        await svc.enqueue_automated_sms(db, **request(tid, cid))
        await db.commit()
        payload = request(tid, cid)
        if changed == 'sender':
            tenant = await db.get(Tenant, tid)
            tenant.sms_phone_number = '+1' + str(2000000000 + uuid4().int % 7000000000)
            await db.flush()
        else:
            payload[changed] = 'Changed body' if changed == 'body' else '+15005550666'
        with pytest.raises(HTTPException) as exc:
            await svc.enqueue_automated_sms(db, **payload)
        assert exc.value.detail['code'] == 'idempotency_conflict'
        await db.rollback()


@pytest.mark.asyncio
async def test_domain_rollback_rolls_back_intent_notification_and_history():
    from app.db.session import AsyncSessionLocal
    from app.db.models.automated_sms import AutomatedSMSOperation
    from app.db.models.notification import Notification
    from app.db.models.sms_message import SMSMessage
    from app.db.models.customer import Customer
    from app.services import automated_sms_service as svc
    tid, cid, _ = await seed()
    async with AsyncSessionLocal() as db:
        customer = await db.get(Customer, cid)
        customer.company_name = 'Domain mutation rolled back'
        await svc.enqueue_automated_sms(db, **request(tid, cid))
        await db.rollback()
    async with AsyncSessionLocal() as db:
        assert (await db.get(Customer, cid)).company_name is None
        for model in (AutomatedSMSOperation, Notification, SMSMessage):
            assert await db.scalar(select(func.count()).select_from(model).where(model.tenant_id == tid)) == 0
        sender = Sender()
        await svc.process_pending_automated_operations(db, sender, tenant_id=tid)
        assert sender.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['opt_out', 'phone', 'sender', 'sms_disabled', 'messaging_disabled', 'tenant_deleted', 'customer_deleted', 'ambiguous_phone', 'staff_disabled', 'staff_phone', 'staff_tenant', 'staff_role', 'tenant_contact_changed'])
async def test_dispatch_revalidates_eligibility_without_provider_call(change):
    from app.db.session import AsyncSessionLocal
    from app.db.models.automated_sms import AutomatedSMSOperation
    from app.db.models.tenant import Tenant
    from app.db.models.customer import Customer
    from app.db.models.user import User
    from app.services import automated_sms_service as svc
    tid, cid, uid = await seed()
    foreign_tid, _, _ = await seed() if change == 'staff_tenant' else (None, None, None)
    async with AsyncSessionLocal() as db:
        payload = request(tid, cid)
        if change.startswith('staff'):
            payload.update(customer_id=None, recipient_user_id=uid, template_name='quote_declined_shop', to='+15005550777')
        if change == 'tenant_contact_changed':
            payload.update(customer_id=None, recipient_tenant_contact=True, template_name='quote_declined_shop', to='+15005550999')
        op = await svc.enqueue_automated_sms(db, **payload)
        await db.commit()
        tenant, customer, user = await db.get(Tenant, tid), await db.get(Customer, cid), await db.get(User, uid)
        if change == 'opt_out': customer.sms_opt_out = True
        elif change == 'phone': customer.phone = '+15005550666'
        elif change == 'sender': tenant.sms_phone_number = '+1' + str(2000000000 + uuid4().int % 7000000000)
        elif change == 'sms_disabled': tenant.sms_enabled = False
        elif change == 'messaging_disabled': tenant.messaging_enabled = False
        elif change == 'tenant_deleted': tenant.deleted_at = datetime.now(timezone.utc)
        elif change == 'customer_deleted': customer.deleted_at = datetime.now(timezone.utc)
        elif change == 'ambiguous_phone':
            db.add(Customer(tenant_id=tid, first_name='Other', last_name='Shared', email=f'{uuid4()}@example.test', phone='(500) 555-0888'))
        elif change == 'staff_disabled': user.is_active = False
        elif change == 'staff_phone': user.phone = '+15005550666'
        elif change == 'staff_tenant': user.tenant_id = foreign_tid
        elif change == 'staff_role': user.role = 'customer'
        elif change == 'tenant_contact_changed': tenant.phone = '+15005550666'
        await db.commit()
        sender = Sender()
        await svc.dispatch_automated_operation(db, op.id, sender)
        await db.refresh(op)
        assert op.state == 'rejected' and op.attempt_count == 0
        assert sender.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['unknown', 'no_receipt', 'rejected'])
async def test_provider_uncertainty_and_rejections_never_retried(outcome):
    from app.db.session import AsyncSessionLocal
    from app.db.models.customer import Customer
    from app.services import automated_sms_service as svc
    tid, cid, _ = await seed()
    async with AsyncSessionLocal() as db:
        op = await svc.enqueue_automated_sms(db, **request(tid, cid))
        await db.commit()
        sender = Sender(); sender.outcome = outcome
        await svc.dispatch_automated_operation(db, op.id, sender)
        for _ in range(3):
            await svc.process_pending_automated_operations(db, sender, tenant_id=tid)
        await db.refresh(op)
        assert sender.calls == 1 and op.attempt_count == 1
        assert op.state == ('rejected' if outcome == 'rejected' else 'unknown')
        if outcome == 'rejected':
            assert (await db.get(Customer, cid)).sms_opt_out
        else:
            assert op.reconciliation_state == 'required'
            other = await svc.enqueue_automated_sms(db, **request(tid, cid, event='work:other'))
            await db.commit()
            await svc.dispatch_automated_operation(db, other.id, sender)
            assert sender.calls == 1
            await db.refresh(other)
            assert other.error_code == 'ambiguous_outcome'


@pytest.mark.asyncio
async def test_restart_recovers_pending_and_holds_stale_claim():
    from app.db.session import AsyncSessionLocal
    from app.db.models.automated_sms import AutomatedSMSOperation
    from app.services import automated_sms_service as svc
    tid, cid, _ = await seed()
    async with AsyncSessionLocal() as db:
        op = await svc.enqueue_automated_sms(db, **request(tid, cid))
        await db.commit()
        op_id = op.id
    sender = Sender()
    async with AsyncSessionLocal() as restarted:
        await svc.process_pending_automated_operations(restarted, sender, tenant_id=tid)
        op = await restarted.get(AutomatedSMSOperation, op_id)
        assert sender.calls == 1 and op.state == 'accepted'
        op.state = 'dispatching'; op.dispatch_started_at = datetime.now(timezone.utc) - timedelta(minutes=6)
        await restarted.commit()
    async with AsyncSessionLocal() as restarted:
        await svc.process_pending_automated_operations(restarted, sender, tenant_id=tid)
        op = await restarted.get(AutomatedSMSOperation, op_id)
        assert op.state == 'unknown' and sender.calls == 1


@pytest.mark.asyncio
async def test_staff_notification_only_callback_terminal_sticky(monkeypatch):
    from app.db.session import AsyncSessionLocal
    from app.db.models.notification import Notification, NotificationStatus
    from app.db.models.sms_message import SMSMessage
    from app.services import automated_sms_service as svc
    from app.services.messaging_service import process_twilio_status_callback
    tid, _, uid = await seed()
    async with AsyncSessionLocal() as db:
        op = await svc.enqueue_automated_sms(db, tenant_id=tid, recipient_user_id=uid, domain_event_id='assignment:1', template_name='quote_declined_shop', to='+15005550777', body='Synthetic assignment')
        await db.commit()
        assert op.message_id is None
        sender = Sender()
        await svc.dispatch_automated_operation(db, op.id, sender)
        await db.refresh(op)
        for status in ['delivered', 'sent', 'failed', 'delivered']:
            await process_twilio_status_callback(db, message_sid=op.provider_message_sid, message_status=status)
        await db.refresh(op)
        notification = await db.get(Notification, op.notification_id)
        assert op.delivery_status == 'delivered'
        assert notification.status == NotificationStatus.DELIVERED
        assert await db.scalar(select(func.count()).select_from(SMSMessage).where(SMSMessage.tenant_id == tid)) == 0


@pytest.mark.asyncio
async def test_cross_tenant_recipient_and_missing_event_fail_closed():
    from app.db.session import AsyncSessionLocal
    from app.services import automated_sms_service as svc
    tid, cid, uid = await seed()
    other_tid, _, _ = await seed()
    async with AsyncSessionLocal() as db:
        for payload in [request(other_tid, cid), dict(tenant_id=other_tid, recipient_user_id=uid, domain_event_id='assignment:1', template_name='quote_declined_shop', to='+15005550777', body='Synthetic')]:
            with pytest.raises(HTTPException) as exc:
                await svc.enqueue_automated_sms(db, **payload)
            assert exc.value.status_code == 404
            await db.rollback()
        with pytest.raises(HTTPException) as exc:
            await svc.enqueue_automated_sms(db, **request(tid, cid, event=''))
        assert exc.value.detail['code'] == 'missing_event_identity'


@pytest.mark.asyncio
async def test_poison_row_does_not_starve_healthy_and_task_fails(monkeypatch):
    from app.db.session import AsyncSessionLocal
    from app.services import automated_sms_service as svc
    tid, cid, uid = await seed()
    async with AsyncSessionLocal() as db:
        poison = await svc.enqueue_automated_sms(db, **request(tid, cid))
        healthy = await svc.enqueue_automated_sms(db, tenant_id=tid, recipient_user_id=uid, domain_event_id='assignment:1', template_name='quote_declined_shop', to='+15005550777', body='Synthetic assignment')
        await db.commit()
        poison.created_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db.commit()
        poison_id = poison.id
        original = svc.dispatch_automated_operation
        async def dispatch(db, op_id, sender):
            if op_id == poison_id: raise RuntimeError('synthetic poison')
            return await original(db, op_id, sender)
        monkeypatch.setattr(svc, 'dispatch_automated_operation', dispatch)
        sender = Sender()
        with pytest.raises(RuntimeError, match='failed for 1 operations'):
            await svc.process_pending_automated_operations(db, sender, limit=1, tenant_id=tid)
        assert sender.calls == 0
        await svc.process_pending_automated_operations(db, sender, limit=1, tenant_id=tid)
        await db.refresh(poison)
        assert poison.state == 'unknown' and poison.error_code == 'internal_recovery_error'
        await db.refresh(healthy)
        assert healthy.state == 'accepted' and sender.calls == 1


@pytest.mark.asyncio
async def test_customer_callback_projects_exact_history_and_preserves_tenant(monkeypatch):
    from unittest.mock import AsyncMock
    from app.db.session import AsyncSessionLocal
    from app.db.models.customer import Customer
    from app.db.models.notification import Notification, NotificationStatus
    from app.db.models.sms_message import SMSMessage, SMSDeliveryStatus
    from app.services import automated_sms_service as svc, messaging_service
    monkeypatch.setattr(messaging_service, 'broadcast_sms_message_event', AsyncMock())
    tid, cid, _ = await seed()
    foreign_tid, foreign_cid, _ = await seed()
    async with AsyncSessionLocal() as db:
        op = await svc.enqueue_automated_sms(db, **request(tid, cid))
        await db.commit()
        await svc.dispatch_automated_operation(db, op.id, Sender())
        await db.refresh(op)
        await messaging_service.process_twilio_status_callback(db, message_sid=op.provider_message_sid, message_status='failed', error_code='21610')
        await db.refresh(op)
        assert op.delivery_status == 'failed'
        assert (await db.get(SMSMessage, op.message_id)).delivery_status == SMSDeliveryStatus.FAILED
        assert (await db.get(Notification, op.notification_id)).status == NotificationStatus.FAILED
        assert (await db.get(Customer, cid)).sms_opt_out
        assert not (await db.get(Customer, foreign_cid)).sms_opt_out


@pytest.mark.asyncio
async def test_dispatch_refreshes_stale_session_tenant_eligibility():
    from app.db.session import AsyncSessionLocal
    from app.db.models.tenant import Tenant
    from app.services import automated_sms_service as svc
    tid, cid, _ = await seed()
    async with AsyncSessionLocal() as db:
        tenant = await db.get(Tenant, tid)
        op = await svc.enqueue_automated_sms(db, **request(tid, cid))
        await db.commit()
        async with AsyncSessionLocal() as concurrent:
            current = await concurrent.get(Tenant, tid)
            current.sms_enabled = False
            await concurrent.commit()
        assert tenant.sms_enabled is True
        sender = Sender()
        await svc.dispatch_automated_operation(db, op.id, sender)
        await db.refresh(op)
        assert op.state == 'rejected' and sender.calls == 0


async def domain_rows(db, tid, cid, uid):
    from app.db.models.vehicle import Vehicle
    from app.db.models.repair_order import RepairOrder
    from app.db.models.invoice import Invoice
    vid, oid, iid = uuid4(), uuid4(), uuid4()
    db.add(Vehicle(id=vid, tenant_id=tid, customer_id=cid, make='Synthetic', model='Truck'))
    await db.flush()
    order = RepairOrder(id=oid, tenant_id=tid, customer_id=cid, vehicle_id=vid, order_number=f'TEST-{oid}', status='invoiced', assigned_mechanic_id=uid, assigned_at=datetime.now(timezone.utc))
    db.add(order)
    await db.flush()
    invoice = Invoice(id=iid, tenant_id=tid, repair_order_id=oid, invoice_number=f'TEST-{iid}', status='sent', subtotal=100, total_amount=100, reminder_count=1)
    db.add(invoice)
    await db.flush()
    return order, invoice


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['none', 'paid', 'void', 'cancelled', 'order_cancelled', 'amount', 'partial_payment', 'pending_zelle', 'reminders_disabled', 'foreign_invoice'])
async def test_delayed_invoice_reminder_rechecks_domain_and_debt(change):
    from app.db.session import AsyncSessionLocal
    from app.db.models.payment import Payment
    from app.db.models.tenant import Tenant
    from app.services import automated_sms_service as svc
    tid, cid, uid = await seed()
    async with AsyncSessionLocal() as db:
        order, invoice = await domain_rows(db, tid, cid, uid)
        op = await svc.enqueue_automated_sms(db, tenant_id=tid, customer_id=cid, domain_event_id=f'invoice:{invoice.id}:reminder:1', template_name='invoice_reminder_sms', to='+15005550888', body='Synthetic invoice for $100.00')
        await db.commit()
        if change == 'paid': invoice.status = 'paid'
        elif change == 'void': invoice.voided_at = datetime.now(timezone.utc)
        elif change == 'cancelled': invoice.status = 'cancelled'
        elif change == 'order_cancelled': order.status = 'cancelled'
        elif change == 'amount': invoice.total_amount = 200
        elif change == 'partial_payment':
            db.add(Payment(tenant_id=tid, invoice_id=invoice.id, payment_number=f'TEST-{uuid4()}', amount=10, method='cash', status='completed'))
        elif change == 'pending_zelle': invoice.zelle_pending_submitted_at = datetime.now(timezone.utc)
        elif change == 'reminders_disabled': (await db.get(Tenant, tid)).invoice_reminders_enabled = False
        elif change == 'foreign_invoice':
            other_tid, _, _ = await seed()
            invoice.tenant_id = other_tid
        await db.commit()
        sender = Sender()
        await svc.dispatch_automated_operation(db, op.id, sender)
        await db.refresh(op)
        assert sender.calls == (1 if change == 'none' else 0)
        assert op.state == ('accepted' if change == 'none' else 'rejected')


@pytest.mark.asyncio
@pytest.mark.parametrize('template', ['pending_zelle_staff_submit_sms', 'pending_zelle_staff_reminder_sms'])
@pytest.mark.parametrize('change', ['none', 'paid', 'new_submission', 'cleared', 'partial_payment'])
async def test_delayed_zelle_alert_rechecks_exact_submission(template, change):
    from app.db.session import AsyncSessionLocal
    from app.db.models.payment import Payment
    from app.services import automated_sms_service as svc
    tid, cid, uid = await seed()
    async with AsyncSessionLocal() as db:
        order, invoice = await domain_rows(db, tid, cid, uid)
        submitted_at = datetime.now(timezone.utc)
        invoice.zelle_pending_submitted_at = submitted_at
        event = f'invoice:{invoice.id}:zelle-submitted:{submitted_at.isoformat()}'
        if template == 'pending_zelle_staff_reminder_sms': event += ':reminder:24'
        op = await svc.enqueue_automated_sms(db, tenant_id=tid, recipient_user_id=uid, domain_event_id=event, template_name=template, to='+15005550777', body='Synthetic Zelle $100.00')
        await db.commit()
        if change == 'paid': invoice.status = 'paid'
        elif change == 'new_submission': invoice.zelle_pending_submitted_at += timedelta(minutes=1)
        elif change == 'cleared': invoice.zelle_pending_submitted_at = None
        elif change == 'partial_payment': db.add(Payment(tenant_id=tid, invoice_id=invoice.id, payment_number=f'TEST-{uuid4()}', amount=10, method='cash', status='completed'))
        await db.commit()
        sender = Sender()
        await svc.dispatch_automated_operation(db, op.id, sender)
        await db.refresh(op)
        assert sender.calls == (1 if change == 'none' else 0)
        assert op.state == ('accepted' if change == 'none' else 'rejected')


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['assignment', 'idle'])
@pytest.mark.parametrize('changed', [False, True])
async def test_stale_operational_alerts_suppressed(kind, changed):
    from app.db.session import AsyncSessionLocal
    from app.db.models.mechanic_time import MechanicIdleAlertStreak
    from app.services import automated_sms_service as svc
    tid, cid, uid = await seed()
    async with AsyncSessionLocal() as db:
        order, invoice = await domain_rows(db, tid, cid, uid)
        if kind == 'assignment':
            event = f'repair-order:{order.id}:assigned:{order.assigned_at.isoformat()}:{uid}'
            template = 'job_assigned_sms'
        else:
            now = datetime.now(timezone.utc)
            streak = MechanicIdleAlertStreak(id=uuid4(), tenant_id=tid, mechanic_id=uid, local_date=now.date(), started_at=now, is_active=True)
            db.add(streak)
            event, template = f'mechanic-idle-streak:{streak.id}', 'mechanic_idle_alert_sms'
        op = await svc.enqueue_automated_sms(db, tenant_id=tid, recipient_user_id=uid, domain_event_id=event, template_name=template, to='+15005550777', body='Synthetic operational alert')
        await db.commit()
        if changed:
            if kind == 'assignment': order.assigned_mechanic_id = None
            else: streak.is_active = False
            await db.commit()
        sender = Sender()
        await svc.dispatch_automated_operation(db, op.id, sender)
        assert sender.calls == (0 if changed else 1)
