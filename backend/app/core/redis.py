from typing import Optional
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
