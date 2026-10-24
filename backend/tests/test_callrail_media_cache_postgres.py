"""Opt-in disposable PostgreSQL concurrency and revocation evidence."""
import asyncio
import json
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from app.core.config import settings
from app.db.base import Base
from app.db.models.callrail import CallRailMediaCache, CallRailNumberBinding
from app.db.models.message_thread import MessageThread
from app.db.models.sms_message import SMSMessage
from app.db.models.tenant import Tenant
from app.services import callrail_media as media
from app.services import callrail_media_cache as cache
from app.services import callrail_service as cr
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_callrail_media import pixels

pytestmark = pytest.mark.skipif(not os.getenv('CALLRAIL_CACHE_TEST_POSTGRES_URL'), reason='disposable PostgreSQL only')


@pytest_asyncio.fixture
async def pg(monkeypatch):
    url = os.environ['CALLRAIL_CACHE_TEST_POSTGRES_URL']
    schema = 'cr_cache_probe_' + uuid4().hex
    owner = create_async_engine(url)
    async with owner.begin() as db:
        await db.execute(text('CREATE SCHEMA ' + schema))
    engine = create_async_engine(url, connect_args={'server_settings': {'search_path': schema}})
    async with engine.begin() as db:
        await db.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(cache, 'AsyncSessionLocal', factory)
    monkeypatch.setattr(settings, 'CALLRAIL_MEDIA_ENCRYPTION_KEYS', json.dumps({'v1': Fernet.generate_key().decode()}))
    async with factory() as db:
        tenant = Tenant(name='Synthetic', slug='crprobe-' + uuid4().hex, messaging_enabled=True)
        db.add(tenant)
        await db.flush()
        binding = CallRailNumberBinding(tenant_id=tenant.id, account_id='ACCsynthetic', company_id='COMsynthetic',
            tracker_id='TRKsynthetic', sender_phone='+15005550011', credential_ref='CALLRAIL_MEDIA_PROBE',
            signing_secret_ref='CALLRAIL_MEDIA_SIGN_PROBE', enabled=True, accept_new_inquiries=True)
        db.add(binding)
        await db.commit()
        event = {'id': 23456, 'resource_id': 'SCIexample', 'company_resource_id': binding.company_id,
            'source_number': '+15005550022', 'destination_number': binding.sender_phone, 'content': 'A caption',
            'message_type': 'mms', 'timestamp': '2026-10-23T12:00:00Z', 'conversation_id': 'CONsynthetic'}
        result = await cr.apply_event(db, binding.id, event, 'received')
        await db.commit()
        message = await db.get(SMSMessage, result['message_id'])
        thread = await db.get(MessageThread, message.thread_id)
        context = await media.context_for(db, tenant.id, thread, message.id)
    try:
        yield factory, binding.id, context
    finally:
        await engine.dispose()
        async with owner.begin() as db:
            await db.execute(text('DROP SCHEMA ' + schema + ' CASCADE'))
        await owner.dispose()


@pytest.mark.asyncio
async def test_concurrent_first_manifest_image_reopen_has_single_fetch(pg, monkeypatch):
    factory, _binding_id, context = pg
    calls = []
    async def retrieve(context, index=None, **kwargs):
        calls.append(index)
        await asyncio.sleep(.05)
        if kwargs.get('return_urls'):
            return [f'https://api.callrail.com/v3/a/{context.account}/text-messages/SCIexample/media/0']
        return pixels(), 'image/png'
    monkeypatch.setattr(media, 'retrieve', retrieve)
    results = await asyncio.wait_for(asyncio.gather(*(media.retrieve_cached(context, 0) for _ in range(8))), 10)
    assert len(set(results)) == 1
    assert calls == [None, 0]
    async with factory() as db:
        assert len(list(await db.scalars(select(CallRailMediaCache)))) == 2


@pytest.mark.asyncio
async def test_revocation_during_fetch_never_serves_or_persists(pg, monkeypatch):
    factory, binding_id, context = pg
    async def retrieve(context, index=None, **kwargs):
        async with factory() as db:
            binding = await db.get(CallRailNumberBinding, binding_id)
            binding.enabled = False
            await db.commit()
        return [f'https://api.callrail.com/v3/a/{context.account}/text-messages/SCIexample/media/0']
    monkeypatch.setattr(media, 'retrieve', retrieve)
    with pytest.raises(HTTPException) as error:
        await asyncio.wait_for(media.retrieve_cached(context), 10)
    assert error.value.status_code == 404
    async with factory() as db:
        assert list(await db.scalars(select(CallRailMediaCache))) == []


@pytest.mark.asyncio
async def test_revocation_after_image_decode_does_not_persist_bytes(pg, monkeypatch):
    factory, binding_id, context = pg
    async def retrieve(context, index=None, **kwargs):
        if kwargs.get('return_urls'):
            return [f'https://api.callrail.com/v3/a/{context.account}/text-messages/SCIexample/media/0']
        async with factory() as db:
            binding = await db.get(CallRailNumberBinding, binding_id)
            binding.enabled = False
            await db.commit()
        return pixels(), 'image/png'
    monkeypatch.setattr(media, 'retrieve', retrieve)
    with pytest.raises(HTTPException) as error:
        await asyncio.wait_for(media.retrieve_cached(context, 0), 10)
    assert error.value.status_code == 404
    async with factory() as db:
        assert list(await db.scalars(select(CallRailMediaCache))) == []


@pytest.mark.asyncio
async def test_foreign_thread_cannot_use_cached_message(pg, monkeypatch):
    factory, _binding_id, context = pg
    async def retrieve(*args, **kwargs):
        return [f'https://api.callrail.com/v3/a/{context.account}/text-messages/SCIexample/media/0']
    monkeypatch.setattr(media, 'retrieve', retrieve)
    await media.retrieve_cached(context)
    async with factory() as db:
        foreign = Tenant(name='Foreign synthetic', slug='foreign-' + uuid4().hex)
        db.add(foreign)
        await db.flush()
        thread = await db.get(MessageThread, context.message.thread_id)
        thread.tenant_id = foreign.id
        await db.commit()
    with pytest.raises(HTTPException) as error:
        await media.retrieve_cached(context)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_budget_denial_is_definite_unsent_and_never_automatically_retried(pg, monkeypatch):
    from app.db.models.user import User, UserRole
    from app.services import callrail_budget
    from app.services import communications_service as comm
    from test_callrail_dispatch import TwilioMustNotSend, request_for
    factory, _binding_id, context = pg
    async def allowed(*args, **kwargs):
        return True
    monkeypatch.setattr(comm, 'enforce_tenant_send_rate_limit', allowed)
    monkeypatch.setattr(comm.routing, 'enabled', lambda: False)
    attempts = []
    async def blocked(*args):
        attempts.append(1)
        raise callrail_budget.CallRailBudgetBlocked('callrail_budget_exceeded')
    monkeypatch.setattr(cr, 'send', blocked)
    async with factory() as db:
        tenant = await db.get(Tenant, context.message.tenant_id)
        thread = await db.get(MessageThread, context.message.thread_id)
        user = User(tenant_id=tenant.id, email=uuid4().hex + '@example.test', first_name='Synthetic',
            last_name='Owner', role=UserRole.GARAGE_OWNER, is_active=True)
        db.add(user)
        await db.commit()
        request = await request_for(db, tenant, thread)
        request.expected_version = (await comm.workflow(db, thread)).version
        operation, _ = await comm.create_operation(db, user, tenant, thread.id, request, 'blocked-once', TwilioMustNotSend())
        await comm.dispatch_operation(db, operation.id, TwilioMustNotSend())
        await comm.dispatch_operation(db, operation.id, TwilioMustNotSend())
        await db.refresh(operation)
        assert operation.state == 'rejected'
        assert operation.error_code == 'callrail_budget_exceeded'
        assert operation.attempt_count == 0 and operation.dispatch_started_at is None
        assert operation.reconciliation_state == 'none' and attempts == [1]
