from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.customer import Customer
from app.db.models.customer_notification_preferences import CustomerNotificationPreferences
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.notification import Notification, NotificationStatus
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.api.v1.endpoints.customer_notification_preferences import PreferencesUpdate
from app.services import customer_notification_preferences as service
from app.services.provider_outbox_service import enqueue_email_notification, process_due_provider_outbox_events


async def fixture(db):
    tenant = Tenant(name='Preference Garage', slug=f'prefs-{uuid4().hex}')
    db.add(tenant)
    await db.flush()
    customer = Customer(tenant_id=tenant.id, first_name='Test', last_name='Customer', email='fixture@example.test', phone='+12025550123')
    db.add(customer)
    await db.flush()
    user = User(tenant_id=tenant.id, customer_id=customer.id, role=UserRole.CUSTOMER, email=f'{uuid4().hex}@example.test', hashed_password='unused', first_name='Test', last_name='Customer')
    db.add(user)
    await db.commit()
    return tenant, customer, user


def update(data, **changes):
    return PreferencesUpdate(expected_context=data['context_key'], base_revision=data['revision'], **{name: changes.get(name, data[name]) for name in service.CHOICES})


@pytest.mark.asyncio
async def test_defaults_persist_conflict_and_contact_separation(db_session):
    _, customer, user = await fixture(db_session)
    original_updated = customer.updated_at
    data = await service.get_preferences(db_session, user)
    assert data['revision'] == 0 and all(data[k] for k in service.CHOICES)
    assert await db_session.scalar(select(CustomerNotificationPreferences)) is None
    saved = await service.save_preferences(db_session, user, update(data, invoice_email=False))
    assert saved['revision'] == 1 and saved['invoice_email'] is False and saved['repair_email'] is True
    await db_session.refresh(customer)
    assert customer.updated_at == original_updated
    assert not customer.sms_opt_out
    assert (await service.get_preferences(db_session, user)) == saved
    with pytest.raises(HTTPException) as conflict:
        await service.save_preferences(db_session, user, update(data))
    assert conflict.value.status_code == 409
    await db_session.rollback()


@pytest.mark.asyncio
async def test_scope_role_and_context_cannot_cross_customers(db_session):
    tenant, customer, user = await fixture(db_session)
    data = await service.get_preferences(db_session, user)
    bad = update(data)
    bad.expected_context = '0' * 64
    with pytest.raises(HTTPException) as error:
        await service.save_preferences(db_session, user, bad)
    assert error.value.status_code == 409
    for role, tenant_id, customer_id, expected in [
        (UserRole.GARAGE_OWNER, tenant.id, customer.id, 403),
        (UserRole.CUSTOMER, uuid4(), customer.id, 404),
        (UserRole.CUSTOMER, tenant.id, uuid4(), 404),
    ]:
        with pytest.raises(HTTPException) as error:
            await service.get_preferences(db_session, SimpleNamespace(role=role, tenant_id=tenant_id, customer_id=customer_id))
        assert error.value.status_code == expected
    from datetime import datetime, timezone
    customer.deleted_at = datetime.now(timezone.utc)
    await db_session.flush()
    with pytest.raises(HTTPException) as error:
        await service.get_preferences(db_session, user)
    assert error.value.status_code == 404


def test_update_is_strict_and_rejects_identity_fields():
    valid = dict(expected_context='a'*64, base_revision=0, **{k: True for k in service.CHOICES})
    for changes in [dict(invoice_email='false'), dict(base_revision=True), dict(customer_id=str(uuid4())), dict(invoice_sms=None)]:
        with pytest.raises(ValidationError):
            PreferencesUpdate(**(valid | changes))


@pytest.mark.asyncio
async def test_all_optional_channels_and_essential_exceptions(db_session):
    tenant, customer, user = await fixture(db_session)
    data = await service.get_preferences(db_session, user)
    await service.save_preferences(db_session, user, update(data, **{k: False for k in service.CHOICES}))
    for channel, templates in service.TEMPLATES.items():
        for template in templates:
            assert await service.delivery_reason(db_session, tenant_id=tenant.id, customer_id=customer.id, channel=channel, template_name=template) == service.DISABLED
    for template in ['quote_approval', 'invoice_resend', 'payment_receipt', 'work_pending_review', 'password_reset']:
        assert await service.delivery_reason(db_session, tenant_id=tenant.id, customer_id=customer.id, channel='email', template_name=template) is None
    assert await service.delivery_reason(db_session, tenant_id=uuid4(), customer_id=customer.id, channel='email', template_name='invoice_created') == 'notification_identity_changed'
    assert await service.delivery_reason(db_session, tenant_id=tenant.id, customer_id=customer.id, channel='email', template_name='invoice_created', recipient='someone-else@example.test') == 'notification_identity_changed'
    assert await service.delivery_reason(db_session, tenant_id=tenant.id, customer_id=None, channel='email', template_name='invoice_created') is None


@pytest.mark.asyncio
async def test_queued_email_rechecks_preferences_and_never_replays(_db_engine):
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, user = await fixture(db)
        event = await enqueue_email_notification(db, tenant_id=tenant.id, aggregate_type='test', aggregate_id=uuid4(), idempotency_key=uuid4().hex, recipient=customer.email, subject='Test', body='Test', template_name='invoice_created', customer_id=customer.id, sender_name='Fixture Garage')
        await db.commit()
        event_id = event.id
        data = await service.get_preferences(db, user)
        saved = await service.save_preferences(db, user, update(data, invoice_email=False))
    delivered = []
    async def deliver(email):
        delivered.append(email)
        return 'fake-provider-id'
    result = await process_due_provider_outbox_events(session_factory=factory, deliver_email=deliver)
    assert not delivered and result['dead'] == 1
    async with factory() as db:
        event = await db.get(ProviderOutboxEvent, event_id)
        notification = await db.get(Notification, event.payload['notification_id'])
        assert notification.status == NotificationStatus.FAILED
        assert service.DISABLED in notification.error_message
        assert notification.external_id is None
        await service.save_preferences(db, user, update(saved, invoice_email=True))
    result = await process_due_provider_outbox_events(session_factory=factory, deliver_email=deliver)
    assert result['claimed'] == 0 and not delivered

@pytest.mark.asyncio
async def test_queue_rejects_cross_tenant_notification_without_mutating_it(_db_engine):
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, _ = await fixture(db)
        foreign = Tenant(name='Other Garage', slug=f'other-{uuid4().hex}')
        db.add(foreign)
        await db.flush()
        event = await enqueue_email_notification(db, tenant_id=tenant.id, aggregate_type='test', aggregate_id=uuid4(), idempotency_key=uuid4().hex, recipient=customer.email, subject='Test', body='Test', template_name='invoice_created', customer_id=customer.id, sender_name=None)
        notification_id = event.payload['notification_id']
        notification = await db.get(Notification, notification_id)
        notification.tenant_id = foreign.id
        await db.commit()
    delivered = []
    async def deliver(email):
        delivered.append(email)
    await process_due_provider_outbox_events(session_factory=factory, deliver_email=deliver)
    assert not delivered
    async with factory() as db:
        notification = await db.get(Notification, notification_id)
        assert notification.status == NotificationStatus.PENDING
        assert notification.error_message is None


@pytest.mark.asyncio
async def test_synchronous_email_suppressed_without_provider_call(db_session, monkeypatch):
    from app.services.email_service import send_email
    import resend
    tenant, customer, user = await fixture(db_session)
    data = await service.get_preferences(db_session, user)
    await service.save_preferences(db_session, user, update(data, repair_email=False))
    def forbidden(*args, **kwargs):
        raise AssertionError('provider must not be called')
    monkeypatch.setattr(resend.Emails, 'send', forbidden)
    notification = await send_email(db_session, str(tenant.id), customer.email, 'Test', 'Test', template_name='work_started', customer_id=customer.id)
    assert notification.status == NotificationStatus.FAILED
    assert notification.error_message == service.DISABLED
    assert notification.sent_at is None and notification.external_id is None


@pytest.mark.asyncio
async def test_http_contract_uses_active_customer_and_rejects_unknown_fields(client, db_session):
    from app.main import app
    from app.core.dependencies import get_current_active_user
    _, _, user = await fixture(db_session)
    app.dependency_overrides[get_current_active_user] = lambda: user
    try:
        path = '/api/v1/auth/me/notification-preferences'
        response = await client.get(path)
        assert response.status_code == 200
        body = update(response.json(), repair_sms=False).model_dump()
        assert (await client.put(path, json=body | {'customer_id':str(uuid4())})).status_code == 422
        saved = await client.put(path, json=body)
        assert saved.status_code == 200 and saved.json()['repair_sms'] is False
        assert (await client.put(path, json=body)).status_code == 409
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)

@pytest.mark.asyncio
async def test_postgres_concurrent_save_and_queued_sms_policy():
    import asyncio
    import os
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.db.session import database_url
    from app.services import automated_sms_service as sms
    from app.db.models.automated_sms import AutomatedSMSOperation
    if os.getenv('COMMUNICATIONS_ISOLATED_LOCAL') != '1':
        pytest.skip('requires isolated synthetic PostgreSQL')
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as db:
            tenant, customer, user = await fixture(db)
            tenant.sms_enabled = True
            tenant.messaging_enabled = True
            tenant.sms_phone_number = '+1' + str(2000000000 + tenant.id.int % 7000000000)
            await db.commit()
            data = await service.get_preferences(db, user)
            op = await sms.enqueue_automated_sms(db, tenant_id=tenant.id, customer_id=customer.id, domain_event_id=f'work:{uuid4()}', template_name='work_started_sms', to=customer.phone, body='Synthetic optional update')
            await db.commit()
            op_id=op.id
        async def save():
            async with factory() as db:
                try:
                    return await service.save_preferences(db, user, update(data, repair_sms=False))
                except HTTPException as error:
                    await db.rollback()
                    return error.status_code
        results = await asyncio.gather(save(), save())
        assert sum(isinstance(r, dict) for r in results) == 1 and 409 in results
        class Sender:
            ready=True
            calls=0
            async def send(self, **kwargs):
                self.calls += 1
                return {'sid':'SM' + uuid4().hex, 'status':'queued'}
        sender=Sender()
        async with factory() as db:
            await sms.dispatch_automated_operation(db, op_id, sender)
            op=await db.get(AutomatedSMSOperation, op_id)
            assert op.state == 'rejected' and op.error_code == service.DISABLED
            assert sender.calls == 0 and op.attempt_count == 0
            current=await service.get_preferences(db, user)
            customer=await db.get(Customer, customer.id)
            customer.sms_opt_out=True
            await db.commit()
            await service.save_preferences(db, user, update(current, repair_sms=True))
            await db.refresh(customer)
            assert customer.sms_opt_out is True
            assert (await db.get(AutomatedSMSOperation, op_id)).state == 'rejected'
    finally:
        await engine.dispose()

@pytest.mark.asyncio
@pytest.mark.parametrize('internal_contact', [False, True])
@pytest.mark.parametrize('email_enabled', [False, True])
async def test_legacy_queued_snapshot_honors_real_payer_but_not_external_fleet_contact(_db_engine, internal_contact, email_enabled):
    from app.db.models.invoice import Invoice
    from app.db.models.repair_order import RepairOrder
    from app.db.models.vehicle import Vehicle
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, user = await fixture(db)
        customer.is_internal_fleet=internal_contact
        vehicle=Vehicle(tenant_id=tenant.id,customer_id=customer.id,make='Fixture',model='Truck')
        db.add(vehicle);await db.flush()
        order=RepairOrder(tenant_id=tenant.id,customer_id=customer.id,vehicle_id=vehicle.id,order_number=uuid4().hex,status='invoiced',is_internal=internal_contact)
        db.add(order);await db.flush()
        invoice=Invoice(tenant_id=tenant.id,repair_order_id=order.id,billed_customer_id=customer.id,invoice_number=uuid4().hex,status='sent',subtotal=100,total_amount=100,recipient_email='external-contact@example.test' if internal_contact else customer.email)
        db.add(invoice);await db.flush()
        assert service.invoice_customer_scope(invoice, customer) == (None if internal_contact else customer.id)
        # Payload deliberately omits the new customer_id to exercise old queues.
        await enqueue_email_notification(db,tenant_id=tenant.id,aggregate_type='invoice',aggregate_id=invoice.id,idempotency_key=uuid4().hex,recipient=invoice.recipient_email,subject='Fixture',body='Fixture',template_name='invoice_created',sender_name=None)
        await db.commit()
        data=await service.get_preferences(db,user)
        await service.save_preferences(db,user,update(data,invoice_email=email_enabled))
    sent=[]
    async def deliver(email):
        sent.append(email)
        return 'fake-provider-id'
    result=await process_due_provider_outbox_events(session_factory=factory,deliver_email=deliver)
    expected=internal_contact or email_enabled
    assert bool(sent) == expected
    assert result['succeeded'] == int(expected)
    assert result['dead'] == int(not expected)
