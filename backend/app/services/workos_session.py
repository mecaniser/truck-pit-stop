"""Opaque browser session with encrypted, server-side WorkOS refresh state."""
import base64
import hashlib
import json
import secrets
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.redis import get_redis


SESSION_PREFIX = "workos:session:"
def session_ttl_seconds() -> int:
    return settings.WORKOS_SESSION_TTL_DAYS * 24 * 60 * 60


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
