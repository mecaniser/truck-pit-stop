"""Run only against a disposable Redis with no customer data or host port."""
import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from app.services import workos_session

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(not os.getenv("DB064_REDIS_TEST_URL"), reason="disposable Redis not configured")]


@pytest_asyncio.fixture
async def redis(monkeypatch):
    client = Redis.from_url(os.environ["DB064_REDIS_TEST_URL"], decode_responses=True)
    async def get():
        return client
    monkeypatch.setattr(workos_session, "get_redis", get)
    yield client
    await client.aclose()


async def test_real_lua_protects_successor_and_deleted_session(redis):
    sid = await workos_session.create_session(refresh_token="original", local_user_id="u", workos_user_id="wu", workos_org_id="org")
    first = await workos_session.acquire_refresh_lock(sid)
    assert await workos_session.rotate_session(sid, "rotated", lock_token=first)
    await workos_session.release_refresh_lock(sid, first)
    successor = await workos_session.acquire_refresh_lock(sid)
    await workos_session.release_refresh_lock(sid, first)
    assert await redis.get(f"{workos_session.REFRESH_LOCK_PREFIX}{sid}") == successor
    assert not await workos_session.rotate_session(sid, "stale", lock_token=first)
    await workos_session.delete_session(sid, lock_token=first)
    assert (await workos_session.get_session(sid))["refresh_token"] == "rotated"
    await workos_session.delete_session(sid)
    assert not await workos_session.rotate_session(sid, "resurrection", lock_token=successor)
    assert await workos_session.get_session(sid) is None


async def test_real_lua_renews_lease_across_original_expiry(redis, monkeypatch):
    monkeypatch.setattr(workos_session, "_refresh_lock_seconds", lambda: 1)
    sid = f"long-call-{uuid.uuid4()}"
    async def slow(token):
        await asyncio.sleep(1.3)
        assert await redis.get(f"{workos_session.REFRESH_LOCK_PREFIX}{sid}") == token
        assert await workos_session.acquire_refresh_lock(sid) is None
        return "completed"
    assert await workos_session.run_with_refresh_lock(sid, slow) == "completed"
    assert await workos_session.acquire_refresh_lock(sid) is not None
