from __future__ import annotations

import re
import time
from collections import OrderedDict
from typing import Optional

from fastapi import Request
from slowapi import Limiter

from app.core.config import settings
from app.core.security import decode_token

_CACHE_MISS = object()
_token_user_cache: "OrderedDict[str, tuple[Optional[str], float]]" = OrderedDict()
_PERFORMANCE_LOAD_ACTOR_HEADER = "x-dieselbridge-load-actor"
_PERFORMANCE_LOAD_ACTOR_PATTERN = re.compile(r"k6-vu-[1-9][0-9]*$")


def _get_cached_user_id(token: str) -> object:
    now = time.time()
    cached = _token_user_cache.get(token)
    if not cached:
        return _CACHE_MISS

    cached_user_id, expires_at = cached
    if expires_at <= now:
        _token_user_cache.pop(token, None)
        return _CACHE_MISS

    # Keep LRU order hot for active tokens. In rare races, key may already
    # be evicted between get() and move_to_end(); treat that as cache miss.
    try:
        _token_user_cache.move_to_end(token)
    except KeyError:
        return _CACHE_MISS
    return cached_user_id


def _cache_user_id(token: str, user_id: Optional[str], ttl_seconds: int) -> None:
    if ttl_seconds <= 0:
        return

    expires_at = time.time() + ttl_seconds
    _token_user_cache[token] = (user_id, expires_at)
    _token_user_cache.move_to_end(token)

    max_entries = settings.RATE_LIMIT_TOKEN_CACHE_MAX_ENTRIES
    while len(_token_user_cache) > max_entries:
        try:
            _token_user_cache.popitem(last=False)
        except KeyError:
            break


def clear_rate_limit_token_cache() -> None:
    """Testing helper to reset in-memory token cache."""
    _token_user_cache.clear()


def _payload_expiry_epoch(payload: dict) -> Optional[int]:
    exp = payload.get("exp")
    if exp is None:
        return None
    try:
        return int(exp)
    except (TypeError, ValueError):
        return None


def _cache_ttl_for_payload(payload: dict) -> int:
    configured_ttl = settings.RATE_LIMIT_TOKEN_CACHE_TTL_SECONDS
    exp_epoch = _payload_expiry_epoch(payload)
    if exp_epoch is None:
        return configured_ttl

    remaining = exp_epoch - int(time.time())
    if remaining <= 0:
        return 0
    return min(configured_ttl, remaining)


def _extract_user_id_from_request(request: Request) -> Optional[str]:
    """Best-effort extraction of authenticated user id for rate-limit keys."""
    token: Optional[str] = None

    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()

    if not token:
        token = request.cookies.get("access_token")

    if not token:
        return None

    cached_user_id = _get_cached_user_id(token)
    if cached_user_id is not _CACHE_MISS:
        if isinstance(cached_user_id, str):
            return cached_user_id
        return None

    payload = decode_token(token)
    if not payload:
        _cache_user_id(
            token=token,
            user_id=None,
            ttl_seconds=settings.RATE_LIMIT_INVALID_TOKEN_CACHE_TTL_SECONDS,
        )
        return None

    user_id = payload.get("sub")
    normalized_user_id = str(user_id) if user_id else None
    _cache_user_id(
        token=token,
        user_id=normalized_user_id,
        ttl_seconds=_cache_ttl_for_payload(payload),
    )
    return normalized_user_id


def rate_limit_key(request: Request) -> str:
    """Use authenticated user id first, then client IP.

    Isolated performance tests log in multiple synthetic staff accounts from one
    k6 host. Give only those login requests distinct principals so the login
    brute-force guard does not mask application capacity. Authenticated test
    traffic still keys on each real staff user id.
    """
    performance_actor = request.headers.get(_PERFORMANCE_LOAD_ACTOR_HEADER)
    if (
        settings.ENVIRONMENT.strip().lower() == "performance"
        and request.url.path == "/api/v1/auth/login"
        and performance_actor
        and _PERFORMANCE_LOAD_ACTOR_PATTERN.fullmatch(performance_actor)
    ):
        return f"performance-load:{performance_actor}"

    user_id = _extract_user_id_from_request(request)
    if user_id:
        return f"user:{user_id}"

    if request.client:
        return f"ip:{request.client.host}"

    return "ip:unknown"


# Shared limiter instance for the whole API.
# Stricter per-endpoint limits remain via decorators.
# 300/minute (was 120): the repair-order drawer alone fires ~5 requests per
# order opened (detail, price-build, parts, quotes, recommended-services),
# and a shop user triaging the work queue can legitimately open several
# orders within a few seconds — 120/min was tight enough for that normal
# workflow to trip the limiter on its own.
limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=["300/minute"],
    # Concrete magic-link URLs contain credentials. Endpoint function identity
    # keeps rate-limit scopes stable without placing path tokens in storage or
    # SlowAPI diagnostics.
    key_style="endpoint",
)
