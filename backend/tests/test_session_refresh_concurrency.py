"""Concurrency guards that keep a multi-tab browser from self-logging-out.

Both auth systems hand the browser a short-lived local credential backed by a
long server session. When several tabs renew at once they used to invalidate
each other's rotating refresh token and drop the whole browser to the login
screen. These tests cover the two guards that prevent that:

  * WorkOS: a per-session refresh lock plus a "wait for the sibling's rotated
    token" path.
  * Legacy: a short grace window during which a just-rotated refresh token is
    still honored.
"""
import pytest

from app.core import redis as redis_module
from app.core.config import settings
from app.services import workos_session

pytestmark = pytest.mark.asyncio


async def _resolved(value):
    return value


@pytest.fixture
def wire_redis(monkeypatch, fake_redis):
    monkeypatch.setattr(workos_session, "get_redis", lambda: _resolved(fake_redis))
    monkeypatch.setattr(redis_module, "get_redis", lambda: _resolved(fake_redis))
    return fake_redis


class TestWorkOSRefreshLock:
    async def test_lock_is_exclusive_and_releasable(self, wire_redis):
        first = await workos_session.acquire_refresh_lock("sess-1")
        assert first is not None

        # A second caller cannot take the same session's lock.
        assert await workos_session.acquire_refresh_lock("sess-1") is None
        # A different session is unaffected.
        assert await workos_session.acquire_refresh_lock("sess-2") is not None

        await workos_session.release_refresh_lock("sess-1", first)
        assert await workos_session.acquire_refresh_lock("sess-1") is not None

    async def test_release_only_clears_own_lock(self, wire_redis):
        owner = await workos_session.acquire_refresh_lock("sess-1")
        # A stale releaser holding the wrong token must not free the lock.
        await workos_session.release_refresh_lock("sess-1", "not-the-owner-token")
        assert await workos_session.acquire_refresh_lock("sess-1") is None
        await workos_session.release_refresh_lock("sess-1", owner)
        assert await workos_session.acquire_refresh_lock("sess-1") is not None

    async def test_wait_returns_when_sibling_rotates_token(self, wire_redis, monkeypatch):
        monkeypatch.setattr(settings, "SECRET_KEY", "x" * 40)
        session_id = await workos_session.create_session(
            refresh_token="old-refresh",
            local_user_id="u1",
            workos_user_id="wu1",
            workos_org_id="org1",
        )
        # Simulate the lock winner completing its rotation.
        assert await workos_session.rotate_session(session_id, "new-refresh")

        rotated = await workos_session.wait_for_rotated_session(
            session_id, "old-refresh", timeout_seconds=1
        )
        assert rotated is not None
        assert rotated["refresh_token"] == "new-refresh"

    async def test_wait_times_out_when_no_rotation(self, wire_redis, monkeypatch):
        monkeypatch.setattr(settings, "SECRET_KEY", "x" * 40)
        session_id = await workos_session.create_session(
            refresh_token="old-refresh",
            local_user_id="u1",
            workos_user_id="wu1",
            workos_org_id="org1",
        )
        rotated = await workos_session.wait_for_rotated_session(
            session_id, "old-refresh", timeout_seconds=0.5
        )
        assert rotated is None

    async def test_wait_returns_none_when_session_deleted(self, wire_redis, monkeypatch):
        monkeypatch.setattr(settings, "SECRET_KEY", "x" * 40)
        session_id = await workos_session.create_session(
            refresh_token="old-refresh",
            local_user_id="u1",
            workos_user_id="wu1",
            workos_org_id="org1",
        )
        await workos_session.delete_session(session_id)
        rotated = await workos_session.wait_for_rotated_session(
            session_id, "old-refresh", timeout_seconds=0.5
        )
        assert rotated is None


class TestLegacyRotationGrace:
    async def test_recently_rotated_token_is_flagged_then_expires_semantically(self, wire_redis):
        assert await redis_module.was_refresh_token_recently_rotated("jti-1") is False
        await redis_module.mark_refresh_token_rotated("jti-1", grace_seconds=20)
        assert await redis_module.was_refresh_token_recently_rotated("jti-1") is True

    async def test_grace_marker_is_scoped_per_jti(self, wire_redis):
        await redis_module.mark_refresh_token_rotated("jti-1", grace_seconds=20)
        assert await redis_module.was_refresh_token_recently_rotated("jti-2") is False
