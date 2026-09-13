"""Opaque browser session with encrypted, server-side WorkOS refresh state."""
import asyncio
import base64
import hashlib
import json
import secrets
import time
from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar
from contextlib import suppress

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.redis import get_redis


SESSION_PREFIX = "workos:session:"
REFRESH_LOCK_PREFIX = "workos:session-refresh-lock:"


def session_ttl_seconds() -> int:
    return settings.WORKOS_SESSION_TTL_DAYS * 24 * 60 * 60


def _refresh_lock_seconds() -> int:
    return settings.WORKOS_SESSION_REFRESH_LOCK_SECONDS


# Compare and mutate in one Redis operation: an expired owner must never clear
# a successor's lock, overwrite its credential, or resurrect a logged-out session.
RELEASE_LOCK_SCRIPT = """-- db064_release_lock
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""
RENEW_LOCK_SCRIPT = """-- db064_renew_lock
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""
UPDATE_SESSION_SCRIPT = """-- db064_update_session
if redis.call('get', KEYS[1]) ~= ARGV[1] then return 0 end
if ARGV[4] ~= '' and redis.call('get', KEYS[2]) ~= ARGV[4] then return 0 end
redis.call('setex', KEYS[1], ARGV[3], ARGV[2])
return 1
"""
DELETE_SESSION_SCRIPT = """-- db064_delete_session
if redis.call('get', KEYS[2]) ~= ARGV[1] then return 0 end
return redis.call('del', KEYS[1])
"""


class RefreshLockUnavailable(Exception):
    pass


_Result = TypeVar("_Result")


async def run_with_refresh_lock(session_id: str, operation: Callable[[str], Awaitable[_Result]]) -> _Result:
    """Hold a renewable lease for the entire refresh, cancelling on lease loss."""
    token = await acquire_refresh_lock(session_id)
    if token is None:
        raise RefreshLockUnavailable()

    async def maintain_lease():
        redis = await get_redis()
        while True:
            await asyncio.sleep(_refresh_lock_seconds() / 3)
            if not await redis.eval(RENEW_LOCK_SCRIPT, 1, f"{REFRESH_LOCK_PREFIX}{session_id}", token, _refresh_lock_seconds()):
                return

    work = asyncio.create_task(operation(token))
    lease = asyncio.create_task(maintain_lease())
    try:
        done, _ = await asyncio.wait({work, lease}, return_when=asyncio.FIRST_COMPLETED)
        if lease in done:
            raise RefreshLockUnavailable()
        return await work
    finally:
        for task in (work, lease):
            task.cancel()
        for task in (work, lease):
            with suppress(asyncio.CancelledError, Exception):
                await task
        await release_refresh_lock(session_id, token)


async def acquire_refresh_lock(session_id: str) -> Optional[str]:
    """Best-effort single-flight lock for one session's provider refresh.

    Returns an owner token when acquired, or None when another caller holds it.
    The lock self-expires so a crashed holder cannot wedge the session.
    """
    token = secrets.token_urlsafe(16)
    redis = await get_redis()
    acquired = await redis.set(
        f"{REFRESH_LOCK_PREFIX}{session_id}",
        token,
        nx=True,
        ex=_refresh_lock_seconds(),
    )
    return token if acquired else None


async def release_refresh_lock(session_id: str, token: str) -> None:
    """Release the lock only if we still own it (avoids clearing a re-acquire)."""
    redis = await get_redis()
    await redis.eval(RELEASE_LOCK_SCRIPT, 1, f"{REFRESH_LOCK_PREFIX}{session_id}", token)


async def wait_for_rotated_session(
    session_id: str,
    previous_refresh_token: str,
    *,
    timeout_seconds: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Poll for the sibling refresh to publish a rotated session, then return it.

    Used by a caller that lost the refresh lock: rather than call WorkOS with a
    refresh token that is about to be (or already) invalidated, it waits for the
    winner to store the new one and reuses that fresh session.
    """
    deadline = time.monotonic() + (
        timeout_seconds if timeout_seconds is not None else float(_refresh_lock_seconds())
    )
    while time.monotonic() < deadline:
        await asyncio.sleep(0.25)
        payload = await get_session(session_id)
        if payload is None:
            return None
        if payload.get("refresh_token") and payload["refresh_token"] != previous_refresh_token:
            return payload
    return None


def _cipher() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256((settings.SECRET_KEY + ":workos-session").encode()).digest())
    return Fernet(key)


async def create_session(*, refresh_token: str, local_user_id: str, workos_user_id: str, workos_org_id: str) -> str:
    session_id = secrets.token_urlsafe(32)
    payload = {
        "refresh_token": _cipher().encrypt(refresh_token.encode()).decode(),
        "local_user_id": local_user_id,
        "workos_user_id": workos_user_id,
        "workos_org_id": workos_org_id,
    }
    await (await get_redis()).setex(f"{SESSION_PREFIX}{session_id}", session_ttl_seconds(), json.dumps(payload))
    return session_id


async def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    raw = await (await get_redis()).get(f"{SESSION_PREFIX}{session_id}")
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        payload["refresh_token"] = _cipher().decrypt(payload["refresh_token"].encode()).decode()
        return payload
    except (ValueError, KeyError, TypeError, InvalidToken, json.JSONDecodeError):
        return None


async def rotate_session(session_id: str, refresh_token: str, *, lock_token: Optional[str] = None) -> bool:
    redis = await get_redis()
    key = f"{SESSION_PREFIX}{session_id}"
    raw = await redis.get(key)
    if not raw:
        return False
    payload = json.loads(raw)
    payload["refresh_token"] = _cipher().encrypt(refresh_token.encode()).decode()
    return bool(await redis.eval(
        UPDATE_SESSION_SCRIPT, 2, key, f"{REFRESH_LOCK_PREFIX}{session_id}",
        raw, json.dumps(payload), session_ttl_seconds(), lock_token or "",
    ))


async def delete_session(session_id: str, *, lock_token: Optional[str] = None) -> None:
    redis = await get_redis()
    if lock_token is not None:
        await redis.eval(DELETE_SESSION_SCRIPT, 2, f"{SESSION_PREFIX}{session_id}", f"{REFRESH_LOCK_PREFIX}{session_id}", lock_token)
    else:
        await redis.delete(f"{SESSION_PREFIX}{session_id}")
