"""Encrypted media reuse with synthetic data only; no live provider transport."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from app.core.config import settings
from app.db.models.callrail import CallRailMediaCache
from app.services import callrail_media as media
from app.services import callrail_media_cache as cache
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_callrail_media import (
    mock_provider,
)
from test_callrail_media import (
    receipt as media_receipt,
)


@pytest_asyncio.fixture
async def receipt(db_session, monkeypatch):
    return await media_receipt.__wrapped__(db_session, monkeypatch)


@pytest.fixture(autouse=True)
def cache_setup(monkeypatch, _db_engine):
    import json

    from app.services import callrail_budget
    monkeypatch.setattr(cache, 'AsyncSessionLocal', async_sessionmaker(_db_engine, expire_on_commit=False))
    monkeypatch.setattr(settings, 'CALLRAIL_MEDIA_ENCRYPTION_KEYS', json.dumps({'v1': Fernet.generate_key().decode()}))
    async def reserve(*args):
        return callrail_budget.Permit(str(uuid4()), datetime.now(UTC) + timedelta(days=1))
    async def complete(*args):
        pass
    monkeypatch.setattr(callrail_budget, 'reserve', reserve)
    monkeypatch.setattr(callrail_budget, 'complete', complete)


@pytest.mark.asyncio
async def test_manifest_image_and_reopening_reuse_without_locators(receipt, monkeypatch):
    db, _tenant, _binding, _thread, _message, context = receipt
    await db.commit()
    calls = mock_provider(monkeypatch, context)
    assert await media.retrieve_cached(context) == {'items': [{'index': 0, 'kind': 'image'}]}
    data, kind = await media.retrieve_cached(context, 0)
    assert data.startswith(b'\x89PNG') and kind == 'image/png'
    assert len(calls) == 2  # one discovery, one image: no second conversation GET
    await media.retrieve_cached(context)
    assert await media.retrieve_cached(context, 0) == (data, kind)
    assert len(calls) == 2
    rows = list(await db.scalars(select(CallRailMediaCache)))
    assert len(rows) == 2
    for row in rows:
        assert 'api.callrail' not in row.encrypted_payload
        assert 'SCIexample' not in row.encrypted_payload
        assert data.hex() not in row.encrypted_payload
        assert row.expires_at - row.created_at <= timedelta(days=30, seconds=1)


@pytest.mark.asyncio
async def test_cache_rechecks_binding_and_tenant_before_hit(receipt, monkeypatch):
    db, _tenant, binding, _thread, message, context = receipt
    await db.commit()
    calls = mock_provider(monkeypatch, context)
    await media.retrieve_cached(context)
    binding.enabled = False
    await db.commit()
    with pytest.raises(HTTPException) as error:
        await media.retrieve_cached(context)
    assert error.value.status_code == 404 and len(calls) == 1
    binding.enabled = True
    message.tenant_id = uuid4()
    await db.commit()
    with pytest.raises(HTTPException):
        await media.retrieve_cached(context)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_corrupt_cache_or_missing_key_never_refetches(receipt, monkeypatch):
    db, _tenant, _binding, _thread, _message, context = receipt
    await db.commit()
    calls = mock_provider(monkeypatch, context)
    await media.retrieve_cached(context)
    row = await db.scalar(select(CallRailMediaCache))
    row.encrypted_payload = 'v1:corrupt'
    await db.commit()
    with pytest.raises(HTTPException):
        await media.retrieve_cached(context)
    monkeypatch.setattr(settings, 'CALLRAIL_MEDIA_ENCRYPTION_KEYS', '{}')
    with pytest.raises(HTTPException):
        await media.retrieve_cached(context)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_expired_cache_refetches_once_and_purge_is_local(receipt, monkeypatch):
    db, _tenant, _binding, _thread, _message, context = receipt
    await db.commit()
    calls = mock_provider(monkeypatch, context)
    await media.retrieve_cached(context)
    row = await db.scalar(select(CallRailMediaCache))
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db.commit()
    await media.retrieve_cached(context)
    assert len(calls) == 2
    await cache.purge_expired(db, now=datetime.now(UTC) + timedelta(days=31))
    await db.commit()
    assert list(await db.scalars(select(CallRailMediaCache))) == []
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_failed_image_preserves_manifest_and_capped_cache_still_opens(receipt, monkeypatch):
    from app.services import callrail_budget
    db, _tenant, _binding, _thread, _message, context = receipt
    await db.commit()
    calls = mock_provider(monkeypatch, context)
    original = media.retrieve
    async def blocked_image(context, index=None, **kwargs):
        if index is not None:
            media.fail('attachment_unavailable')
        return await original(context, index, **kwargs)
    monkeypatch.setattr(media, 'retrieve', blocked_image)
    with pytest.raises(HTTPException):
        await media.retrieve_cached(context, 0)
    assert len(calls) == 1
    monkeypatch.setattr(media, 'retrieve', original)
    data = await media.retrieve_cached(context, 0)
    assert len(calls) == 2
    async def denied(*args):
        raise callrail_budget.CallRailBudgetBlocked('callrail_budget_exceeded')
    monkeypatch.setattr(callrail_budget, 'reserve', denied)
    assert await media.retrieve_cached(context, 0) == data
    assert await media.retrieve_cached(context) == {'items': [{'index': 0, 'kind': 'image'}]}
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_encrypted_blob_cannot_move_between_tenants_or_slots(receipt):
    from types import SimpleNamespace
    _db, tenant, _binding, _thread, message, context = receipt
    digest = cache.fingerprint(context)
    value = cache._seal(['SCIexample'], tenant.id, message.id, -1, digest)
    for scope in ({'tenant_id': uuid4(), 'message_id': message.id, 'slot': -1},
                  {'tenant_id': tenant.id, 'message_id': uuid4(), 'slot': -1},
                  {'tenant_id': tenant.id, 'message_id': message.id, 'slot': 0}):
        with pytest.raises(HTTPException):
            cache._open(SimpleNamespace(encrypted_payload=value, **scope), digest)


@pytest.mark.asyncio
async def test_uncached_media_budget_denial_never_dispatches_provider(receipt, monkeypatch):
    from app.services import callrail_budget
    db, _tenant, _binding, _thread, _message, context = receipt
    await db.commit()
    calls = mock_provider(monkeypatch, context)
    async def deny(*args):
        raise callrail_budget.CallRailBudgetBlocked('callrail_budget_exceeded')
    monkeypatch.setattr(callrail_budget, 'reserve', deny)
    with pytest.raises(HTTPException) as error:
        await media.retrieve_cached(context, 0)
    assert error.value.status_code == 429
    assert calls == []
