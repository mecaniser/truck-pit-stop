"""Synthetic SQL integration for historical SMS identity evidence, no provider I/O."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.config import settings
from app.db.models.customer import Customer
from app.db.models.message_thread import MessageThread
from app.db.models.sms_message import SMSMessage, SMSMessageDirection as Direction, SMSMessageSource as Source, SMSDeliveryStatus as Status
from app.db.models.tenant import Tenant
from app.services import communications_service as svc

CANONICAL = '+12025550101'
OTHER = '+12025550102'
SENDER = '+12025550103'


@pytest_asyncio.fixture
async def conversation(db_session, monkeypatch):
    monkeypatch.setattr(settings, 'SMS_TENANT_ROUTING_ENABLED', False)
    monkeypatch.setattr(svc, '_get_twilio_client', lambda: pytest.fail('provider forbidden'))
    tenant = Tenant(name='Synthetic identity', slug=f'identity-{uuid4()}', sms_enabled=True,
                    messaging_enabled=True, sms_phone_number=SENDER)
    db_session.add(tenant)
    await db_session.flush()
    customer = Customer(tenant_id=tenant.id, first_name='Synthetic', last_name='Contact',
                        email=f'{uuid4()}@example.test', phone=CANONICAL)
    db_session.add(customer)
    await db_session.flush()
    thread = MessageThread(tenant_id=tenant.id, customer_id=customer.id)
    db_session.add(thread)
    await db_session.flush()
    return tenant, customer, thread


def message(conversation, remote=OTHER, **overrides):
    tenant, customer, thread = conversation
    values = dict(tenant_id=tenant.id, customer_id=customer.id, thread_id=thread.id,
                  direction=Direction.OUTBOUND, source=Source.MANUAL, body='Synthetic history',
                  from_number=SENDER, to_number=remote, delivery_status=Status.FAILED,
                  error_code='21211', twilio_message_sid=None)
    values.update(overrides)
    return SMSMessage(**values)


async def policy(db, conversation):
    tenant, _, thread = conversation
    result, *_ = await svc.send_policy(db, tenant, thread, SimpleNamespace(ready=True))
    return result


async def history(db):
    return (await db.execute(select(*SMSMessage.__table__.columns).order_by(SMSMessage.id))).all()


@pytest.mark.asyncio
async def test_unsent_invalid_to_rejection_is_not_remote_identity_and_history_is_unchanged(db_session, conversation):
    db_session.add_all([
        message(conversation, CANONICAL, delivery_status=Status.DELIVERED,
                error_code=None, twilio_message_sid=f'SM{uuid4().hex}'),
        *[message(conversation) for _ in range(4)],
    ])
    await db_session.commit()
    before = await history(db_session)
    assert len(before) == 5
    assert await policy(db_session, conversation) == {'can_send': True, 'reason': None}
    await db_session.commit()
    assert await history(db_session) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('overrides', [
    {'direction': Direction.INBOUND, 'source': Source.INBOUND, 'from_number': OTHER, 'to_number': SENDER},
    {'delivery_status': Status.PENDING},
    {'delivery_status': Status.QUEUED},
    {'delivery_status': Status.SENT},
    {'delivery_status': Status.DELIVERED},
    {'delivery_status': Status.UNDELIVERED},
    {'error_code': None},
    {'error_code': '30003'},
    {'error_code': '21211 '},
    {'error_code': '021211'},
    {'twilio_message_sid': f'SM{"a" * 32}'},
    {'twilio_message_sid': ''},
])
async def test_only_conclusive_failed_outbound_without_receipt_is_excluded(db_session, conversation, overrides, monkeypatch):
    # Exercise recipient identity independently of the earlier sender-route gate.
    # Missing receipt/address evidence is covered against the real resolver below.
    monkeypatch.setattr(svc.automatic, 'resolve', AsyncMock(
        return_value=svc.automatic.Route('twilio', SENDER, 'initiation')))
    db_session.add_all([message(conversation, CANONICAL), message(conversation, **overrides)])
    await db_session.commit()
    before = await history(db_session)
    assert await policy(db_session, conversation) == {'can_send': False, 'reason': 'identity_unverified'}
    assert await history(db_session) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('overrides', [
    {'direction': Direction.INBOUND, 'source': Source.INBOUND, 'from_number': OTHER, 'to_number': SENDER},
    {'delivery_status': Status.SENT},
    {'delivery_status': Status.DELIVERED},
])
async def test_unverifiable_authoritative_route_blocks_before_identity_gate(db_session, conversation, overrides):
    # The real resolver must hold invalid newest inbound or accepted outbound
    # evidence, rather than falling back to the shop default or an older sender.
    db_session.add_all([message(conversation, CANONICAL), message(conversation, **overrides)])
    await db_session.commit()
    before = await history(db_session)
    assert await policy(db_session, conversation) == {'can_send': False, 'reason': 'reply_route_unavailable'}
    assert await history(db_session) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('boundary', ['tenant', 'thread', 'deleted'])
async def test_foreign_or_deleted_message_does_not_enter_identity_evidence(db_session, conversation, boundary):
    from datetime import datetime, timezone
    tenant, customer, _ = conversation
    overrides = {'delivery_status': Status.DELIVERED, 'error_code': None}
    if boundary == 'tenant':
        other_tenant = Tenant(name='Other', slug=f'other-{uuid4()}')
        db_session.add(other_tenant)
        await db_session.flush()
        overrides['tenant_id'] = other_tenant.id
    elif boundary == 'thread':
        other_customer = Customer(tenant_id=tenant.id, first_name='Other', last_name='Thread',
                                  email=f'{uuid4()}@example.test', phone='+12025550109')
        db_session.add(other_customer)
        await db_session.flush()
        other_thread = MessageThread(tenant_id=tenant.id, customer_id=other_customer.id)
        db_session.add(other_thread)
        await db_session.flush()
        overrides['thread_id'] = other_thread.id
    else:
        overrides['deleted_at'] = datetime.now(timezone.utc)
    db_session.add_all([message(conversation, CANONICAL), message(conversation, **overrides)])
    await db_session.commit()
    before = await history(db_session)
    assert (await policy(db_session, conversation))['can_send']
    assert await history(db_session) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('boundary', ['opt_out', 'duplicate_customer', 'held_manual', 'held_automated'])
async def test_ignoring_unsent_rejection_does_not_bypass_other_send_gates(db_session, conversation, boundary):
    from app.db.models.communication import SMSSendOperation
    from app.db.models.automated_sms import AutomatedSMSOperation
    tenant, customer, thread = conversation
    db_session.add(message(conversation))
    if boundary == 'opt_out':
        customer.sms_opt_out = True
        expected = 'opted_out'
    elif boundary == 'duplicate_customer':
        db_session.add(Customer(tenant_id=tenant.id, first_name='Other', last_name='Contact',
                                email=f'{uuid4()}@example.test', phone=CANONICAL))
        expected = 'identity_unverified'
    elif boundary == 'held_manual':
        from app.db.models.user import User
        actor = User(tenant_id=tenant.id, first_name='Synthetic', last_name='Operator',
                     email=f'{uuid4()}@example.test', hashed_password='disabled', role='garage_owner')
        held_message = message(conversation, CANONICAL)
        db_session.add_all([actor, held_message])
        await db_session.flush()
        db_session.add(SMSSendOperation(tenant_id=tenant.id, thread_id=thread.id, state='unknown',
            message_id=held_message.id, idempotency_key=uuid4().hex, payload_hash='synthetic',
            channel_account_id=uuid4(), contact_identity_id=uuid4(), from_number=SENDER,
            to_number=CANONICAL, body='Synthetic', actor_id=actor.id))
        expected = 'ambiguous_outcome'
    else:
        from app.db.models.notification import Notification, NotificationType
        notification = Notification(tenant_id=tenant.id, type=NotificationType.SMS,
                                    recipient_phone=CANONICAL, body='Synthetic')
        db_session.add(notification)
        await db_session.flush()
        db_session.add(AutomatedSMSOperation(tenant_id=tenant.id,
            domain_event_id='synthetic', template_name='synthetic', template_version='1',
            recipient_kind='customer', recipient_id=customer.id, notification_id=notification.id,
            event_key=uuid4().hex, payload_hash='synthetic', state='unknown',
            from_number=SENDER, to_number=CANONICAL, body='Synthetic'))
        expected = 'ambiguous_outcome'
    await db_session.commit()
    assert await policy(db_session, conversation) == {'can_send': False, 'reason': expected}
