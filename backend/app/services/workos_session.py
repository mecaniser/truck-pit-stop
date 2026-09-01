"""Opaque browser session with encrypted, server-side WorkOS refresh state."""
import asyncio
import base64
import hashlib
import json
import secrets
import time
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.redis import get_redis


SESSION_PREFIX = "workos:session:"
REFRESH_LOCK_PREFIX = "workos:session-refresh-lock:"


def session_ttl_seconds() -> int:
    return settings.WORKOS_SESSION_TTL_DAYS * 24 * 60 * 60


def _refresh_lock_seconds() -> int:
    return settings.WORKOS_SESSION_REFRESH_LOCK_SECONDS


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
    current = await redis.get(f"{REFRESH_LOCK_PREFIX}{session_id}")
    if current == token:
        await redis.delete(f"{REFRESH_LOCK_PREFIX}{session_id}")


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


async def rotate_session(session_id: str, refresh_token: str) -> bool:
    payload = await get_session(session_id)
    if not payload:
        return False
    payload["refresh_token"] = _cipher().encrypt(refresh_token.encode()).decode()
    await (await get_redis()).setex(f"{SESSION_PREFIX}{session_id}", session_ttl_seconds(), json.dumps(payload))
    return True


async def delete_session(session_id: str) -> None:
    await (await get_redis()).delete(f"{SESSION_PREFIX}{session_id}")
