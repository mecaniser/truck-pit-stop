from typing import Optional, Dict, Any
import json
import redis.asyncio as aioredis
from app.core.config import settings

# Async Redis connection pool
redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global redis_client
    if redis_client is None:
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_keepalive=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            health_check_interval=30,
        )
    return redis_client


async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None


# Token blacklist functions
BLACKLIST_PREFIX = "token_blacklist:"
TOKEN_VERSION_PREFIX = "token_version:"


async def blacklist_token(jti: str, expires_in: int):
    """Add a token to the blacklist until it expires."""
    r = await get_redis()
    await r.setex(f"{BLACKLIST_PREFIX}{jti}", expires_in, "1")


async def is_token_blacklisted(jti: str) -> bool:
    """Check if a token is blacklisted."""
    r = await get_redis()
    return await r.exists(f"{BLACKLIST_PREFIX}{jti}") > 0


async def increment_token_version(user_id: str) -> int:
    """Increment user's token version (invalidates all existing tokens)."""
    r = await get_redis()
    key = f"{TOKEN_VERSION_PREFIX}{user_id}"
    version = await r.incr(key)
    return version


async def get_token_version(user_id: str) -> int:
    """Get current token version for a user."""
    r = await get_redis()
    version = await r.get(f"{TOKEN_VERSION_PREFIX}{user_id}")
    return int(version) if version else 0


# Password reset functions
PASSWORD_RESET_PREFIX = "password_reset:"
INVOICE_ACCESS_PREFIX = "invoice_access:"
INVOICE_ACCESS_CONSUMED_PREFIX = "invoice_access_consumed:"
PORTAL_ENROLLMENT_PREFIX = "portal_enrollment:"
PORTAL_ENROLLMENT_CONSUMED_PREFIX = "portal_enrollment_consumed:"
QUOTE_PORTAL_ENROLLMENT_PREFIX = "quote_portal_enrollment:"
QUOTE_PORTAL_ENROLLMENT_CONSUMED_PREFIX = "quote_portal_enrollment_consumed:"


async def store_password_reset_token(email: str, token: str, expires_in: int = 3600):
    """Store a password reset token for 1 hour (3600 seconds)."""
    r = await get_redis()
    await r.setex(f"{PASSWORD_RESET_PREFIX}{token}", expires_in, email)


async def get_email_from_reset_token(token: str) -> Optional[str]:
    """Get email associated with a password reset token."""
    r = await get_redis()
    email = await r.get(f"{PASSWORD_RESET_PREFIX}{token}")
    return email


async def delete_password_reset_token(token: str):
    """Delete a password reset token after use."""
    r = await get_redis()
    await r.delete(f"{PASSWORD_RESET_PREFIX}{token}")


# One-time token helpers

async def _store_one_time_token(prefix: str, token: str, payload: Dict[str, Any], expires_in: int) -> None:
    r = await get_redis()
    await r.setex(
        f"{prefix}{token}",
        expires_in,
        json.dumps(payload),
    )


async def _get_one_time_payload(prefix: str, consumed_prefix: str, token: str) -> Optional[Dict[str, Any]]:
    r = await get_redis()
    if await r.exists(f"{consumed_prefix}{token}"):
        return None

    raw = await r.get(f"{prefix}{token}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


async def _is_one_time_token_consumed(consumed_prefix: str, token: str) -> bool:
    r = await get_redis()
    return await r.exists(f"{consumed_prefix}{token}") > 0


async def _get_consumed_one_time_payload(consumed_prefix: str, token: str) -> Optional[Dict[str, Any]]:
    r = await get_redis()
    raw = await r.get(f"{consumed_prefix}{token}")
    if not raw:
        return None

    # Backward compatibility for previously stored consumed markers.
    if raw == "1":
        return None

    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


async def _consume_one_time_token(prefix: str, consumed_prefix: str, token: str) -> Optional[Dict[str, Any]]:
    r = await get_redis()
    key = f"{prefix}{token}"
    consumed_key = f"{consumed_prefix}{token}"

    # Atomic check+consume to avoid concurrent double-use.
    raw = await r.eval(
        """
        local key = KEYS[1]
        local consumed_key = KEYS[2]
        local fallback_ttl = tonumber(ARGV[1])

        if redis.call('EXISTS', consumed_key) == 1 then
            return nil
        end

        local payload = redis.call('GET', key)
        if not payload then
            return nil
        end

        local ttl = redis.call('TTL', key)
        redis.call('DEL', key)
        if ttl ~= nil and ttl > 0 then
            redis.call('SETEX', consumed_key, ttl, payload)
        else
            redis.call('SETEX', consumed_key, fallback_ttl, payload)
        end

        return payload
        """,
        2,
        key,
        consumed_key,
        3600,
    )
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


# Invoice access token functions

async def store_invoice_access_token(token: str, payload: Dict[str, Any], expires_in: int = 604800):
    """Store an invoice access token payload (default 7 days)."""
    await _store_one_time_token(INVOICE_ACCESS_PREFIX, token, payload, expires_in)


async def get_invoice_access_payload(token: str) -> Optional[Dict[str, Any]]:
    """Get invoice access payload if token is active and not consumed."""
    return await _get_one_time_payload(INVOICE_ACCESS_PREFIX, INVOICE_ACCESS_CONSUMED_PREFIX, token)


async def is_invoice_access_token_consumed(token: str) -> bool:
    """Check whether an invoice access token has already been consumed."""
    return await _is_one_time_token_consumed(INVOICE_ACCESS_CONSUMED_PREFIX, token)


async def get_consumed_invoice_access_payload(token: str) -> Optional[Dict[str, Any]]:
    """Get consumed invoice access payload when available (for idempotent retries)."""
    return await _get_consumed_one_time_payload(INVOICE_ACCESS_CONSUMED_PREFIX, token)


async def consume_invoice_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Consume an invoice access token and return payload exactly once."""
    return await _consume_one_time_token(INVOICE_ACCESS_PREFIX, INVOICE_ACCESS_CONSUMED_PREFIX, token)


# Portal enrollment token functions

async def store_portal_enrollment_token(token: str, payload: Dict[str, Any], expires_in: int = 86400):
    """Store a portal enrollment token payload (default 24 hours)."""
    await _store_one_time_token(PORTAL_ENROLLMENT_PREFIX, token, payload, expires_in)


async def get_portal_enrollment_payload(token: str) -> Optional[Dict[str, Any]]:
    """Get portal enrollment payload if token is active and not consumed."""
    return await _get_one_time_payload(PORTAL_ENROLLMENT_PREFIX, PORTAL_ENROLLMENT_CONSUMED_PREFIX, token)


async def is_portal_enrollment_token_consumed(token: str) -> bool:
    """Check whether a portal enrollment token has already been consumed."""
    return await _is_one_time_token_consumed(PORTAL_ENROLLMENT_CONSUMED_PREFIX, token)


async def consume_portal_enrollment_token(token: str) -> Optional[Dict[str, Any]]:
    """Consume a portal enrollment token and return payload exactly once."""
    return await _consume_one_time_token(PORTAL_ENROLLMENT_PREFIX, PORTAL_ENROLLMENT_CONSUMED_PREFIX, token)


# Quote portal enrollment token functions

async def store_quote_portal_enrollment_token(
    token: str,
    payload: Dict[str, Any],
    expires_in: int = 86400,
):
    """Store a quote portal enrollment token payload (default 24 hours)."""
    await _store_one_time_token(QUOTE_PORTAL_ENROLLMENT_PREFIX, token, payload, expires_in)


async def get_quote_portal_enrollment_payload(token: str) -> Optional[Dict[str, Any]]:
    """Get quote portal enrollment payload if token is active and not consumed."""
    return await _get_one_time_payload(
        QUOTE_PORTAL_ENROLLMENT_PREFIX,
        QUOTE_PORTAL_ENROLLMENT_CONSUMED_PREFIX,
        token,
    )


async def is_quote_portal_enrollment_token_consumed(token: str) -> bool:
    """Check whether a quote portal enrollment token has already been consumed."""
    return await _is_one_time_token_consumed(QUOTE_PORTAL_ENROLLMENT_CONSUMED_PREFIX, token)


async def consume_quote_portal_enrollment_token(token: str) -> Optional[Dict[str, Any]]:
    """Consume a quote portal enrollment token and return payload exactly once."""
    return await _consume_one_time_token(
        QUOTE_PORTAL_ENROLLMENT_PREFIX,
        QUOTE_PORTAL_ENROLLMENT_CONSUMED_PREFIX,
        token,
    )
