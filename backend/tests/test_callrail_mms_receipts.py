"""Attachment receipt visibility: synthetic in-memory SQLite, no media downloads."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, func

from app.db.models.callrail import CallRailNumberBinding, CallRailQuarantine
from app.db.models.message_thread import MessageThread
from app.db.models.sms_message import SMSMessage
from app.db.models.tenant import Tenant
from app.services import callrail_service as cr, communications_service as comm


@pytest_asyncio.fixture
async def inbox(db_session, monkeypatch):
    tenant = Tenant(name='MMS synthetic', slug='mms-'+uuid4().hex, messaging_enabled=True)
    db_session.add(tenant)
    await db_session.flush()
    binding = CallRailNumberBinding(tenant_id=tenant.id, account_id='ACC'+uuid4().hex,
        company_id='COMsynthetic', tracker_id='TRKmms', sender_phone='+15005550011',
        credential_ref='CALLRAIL_MMS_TEST_API', signing_secret_ref='CALLRAIL_MMS_TEST_SIGNING',
        enabled=True, accept_new_inquiries=True)
    db_session.add(binding)
    await db_session.commit()
    monkeypatch.setenv('CALLRAIL_MMS_TEST_SIGNING', 'synthetic-mms-signing')
    return db_session, tenant, binding


def event(binding, **changes):
    value = dict(resource_id='SCI'+uuid4().hex, company_resource_id=binding.company_id,
        source_number='+15005550022', destination_number=binding.sender_phone,
        content='', message_type='mms', media_urls=['https://media.invalid/opaque'],
        timestamp=datetime.now(timezone.utc).isoformat(), conversation_id='MMSsynthetic')
    value.update(changes)
    return value


@pytest.mark.asyncio
@pytest.mark.parametrize('changes,caption', [({}, ''), ({'content': None}, ''),
    ({'content': 'Photo of the truck'}, 'Photo of the truck'),
    ({'message_type': 'sms', 'content': 'Caption'}, 'Caption'),
    ({'message_type': 'MMS', 'media_urls': []}, '')])
async def test_attachment_is_visible_in_existing_wire_contract(inbox, changes, caption, monkeypatch):
    db, tenant, binding = inbox
    monkeypatch.setattr(cr.httpx, 'AsyncClient', lambda **kw: pytest.fail('receipt must not fetch media'))
    result = await cr.apply_event(db, binding.id, event(binding, **changes), 'received')
    assert result['status'] == 'received'
    await db.commit()
    message = await db.scalar(select(SMSMessage))
    wire = await comm.message_json(db, message)
    expected = (caption+'\n\n' if caption else '')+cr.ATTACHMENT_NOTICE
    assert wire['body'] == expected and wire['direction'] == 'inbound'
    assert wire['delivery_status'] == 'received'
    assert 'media.invalid' not in str(message.__dict__)
    thread = await db.get(MessageThread, message.thread_id)
    assert thread.thread_kind == 'inquiry' and thread.customer_id is None
    assert thread.last_message_preview == expected[:160] and thread.unread_count_staff == 1


@pytest.mark.asyncio
async def test_refreshed_media_locator_does_not_duplicate_or_increment_unread(inbox):
    db, tenant, binding = inbox
    payload = event(binding, id=12345)
    first = await cr.apply_event(db, binding.id, payload, 'received')
    await db.commit()
    second = await cr.apply_event(db, binding.id, {**payload, 'media_urls':['https://other.invalid/refreshed']}, 'received')
    await db.commit()
    assert second['status'] == 'duplicate' and second['message_id'] == first['message_id']
    assert await db.scalar(select(func.count()).select_from(SMSMessage)) == 1
    thread = await db.scalar(select(MessageThread))
    assert thread.unread_count_staff == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('changes,reason', [
    ({'content': {}}, 'unsupported_message'), ({'content': 'x'*10001}, 'unsupported_message'),
    ({'message_type': None}, 'unsupported_message'), ({'message_type': 'email'}, 'unsupported_message'),
    ({'media_urls': 'https://media.invalid/file'}, 'unsupported_message'),
    ({'media_urls': [None]}, 'unsupported_message'), ({'media_urls': ['']}, 'unsupported_message'),
    ({'media_urls': ['x']*11}, 'unsupported_message'),
    ({'company_resource_id': 'COMforeign'}, 'company_mismatch'),
    ({'destination_number': '+15005550099'}, 'sender_mismatch'),
    ({'source_number': 'invalid'}, 'invalid_contact_phone'),
])
async def test_invalid_or_foreign_mms_stays_quarantined(inbox, changes, reason):
    db, tenant, binding = inbox
    result = await cr.apply_event(db, binding.id, event(binding, **changes), 'received')
    assert result['reason'] == reason
    assert await db.scalar(select(func.count()).select_from(SMSMessage)) == 0
    assert await db.scalar(select(func.count()).select_from(MessageThread)) == 0
    quarantine = await db.scalar(select(CallRailQuarantine))
    assert 'media_urls' not in quarantine.payload


@pytest.mark.asyncio
@pytest.mark.parametrize('gate', ['binding', 'intake', 'outbound'])
async def test_disabled_or_outbound_attachment_cannot_create_inquiry(inbox, gate):
    db, tenant, binding = inbox
    payload = event(binding)
    kind = 'received'
    if gate == 'binding':
        binding.enabled = False
        reason = 'binding_disabled'
    elif gate == 'intake':
        binding.accept_new_inquiries = False
        reason = 'unmapped_contact'
    else:
        kind = 'sent'
        payload.update(source_number=binding.sender_phone, destination_number='+15005550022')
        reason = 'unsupported_message'
    await db.flush()
    assert (await cr.apply_event(db, binding.id, payload, kind))['reason'] == reason
    assert await db.scalar(select(func.count()).select_from(MessageThread)) == 0


@pytest.mark.asyncio
async def test_stop_caption_is_not_hidden_by_attachment_notice(inbox):
    db, tenant, binding = inbox
    result = await cr.apply_event(db, binding.id, event(binding, content=' stop '), 'received')
    await db.commit()
    message = await db.get(SMSMessage, __import__('uuid').UUID(result['message_id']))
    thread = await db.get(MessageThread, message.thread_id)
    assert thread.inquiry_opted_out
    policy, *_ = await comm.send_policy(db, tenant, thread, SimpleNamespace(ready=True))
    assert policy['can_send'] is False and policy['reason'] == 'recipient_opted_out'


@pytest.mark.asyncio
async def test_signed_company_callback_accepts_attachment_and_rejects_bad_signature(inbox):
    import base64
    import hashlib
    import hmac
    import json
    from fastapi import FastAPI
    from app.api.v1.endpoints.callrail import router
    from app.core.dependencies import get_db
    db, tenant, binding = inbox
    app = FastAPI()
    app.include_router(router, prefix='/callrail')
    async def local_db():
        yield db
    app.dependency_overrides[get_db] = local_db
    raw = json.dumps(event(binding)).encode()
    signature = base64.b64encode(hmac.new(b'synthetic-mms-signing', raw, hashlib.sha1).digest()).decode()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        url = f'/callrail/{binding.id}/company/received'
        denied = await client.post(url, content=raw, headers={'signature':'invalid'})
        assert denied.status_code == 403
        assert await db.scalar(select(func.count()).select_from(SMSMessage)) == 0
        accepted = await client.post(url, content=raw, headers={'signature':signature})
        assert accepted.status_code == 200 and accepted.json()['status'] == 'received'
        replayed = await client.post(url, content=raw, headers={'signature':signature})
        assert replayed.json()['status'] == 'duplicate'
    assert await db.scalar(select(func.count()).select_from(SMSMessage)) == 1
    message = await db.scalar(select(SMSMessage))
    assert (await comm.message_json(db, message))['body'] == cr.ATTACHMENT_NOTICE
