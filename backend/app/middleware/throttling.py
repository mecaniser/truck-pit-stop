from __future__ import annotations

import asyncio
import secrets
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.correlation import normalize_correlation_id
from app.core.logging import get_logger
from app.core.rate_limit import rate_limit_key
from app.core.redis import get_redis

logger = get_logger(__name__)

WINDOW_SECONDS = 60
# The repair-order sidekick drawer fires ~4-5 requests per order opened
# (detail, price-build, parts, quotes, invoice, recommended-services), so a
# shop worker fast-paging through 20+ orders in the work queue legitimately
# approaches 100/min on normal use, not just scripted/abusive traffic. Raised
# with headroom for that real workflow while still catching runaway clients.
SOFT_THRESHOLD = 150
HARD_THRESHOLD = 250
MIN_DELAY = 0.1
MAX_DELAY = 0.5
SAFE_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class ThrottlingMiddleware:
    """Throttle heavy consumers using a Redis sliding window."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    @staticmethod
    def _should_apply(scope: Scope) -> bool:
        if scope.get("type") != "http":
            return False

        path = scope.get("path", "")
        return path.startswith("/api/v1")

    @staticmethod
    def _dict_to_headers(headers: dict[str, str]) -> list[tuple[bytes, bytes]]:
        return [(key.encode("latin1"), value.encode("latin1")) for key, value in headers.items()]

    @staticmethod
    def _should_apply_soft_delay(method: str) -> bool:
        """Reserve progressive delays for writes while retaining the hard cap for all API traffic."""
        return method.upper() not in SAFE_READ_METHODS

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._should_apply(scope):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        principal = rate_limit_key(request)
        redis = await get_redis()

        now_ms = int(time.time() * 1000)
        cutoff_ms = now_ms - (WINDOW_SECONDS * 1000)
        now_seconds = int(time.time())
        reset_at = now_seconds + WINDOW_SECONDS
        window_key = f"throttle:window:{principal}"
        # Ensure unique ZSET member per request. Avoid id(request) because it is
        # process-local and can be reused after GC.
        method = scope.get("method", "GET")
        path = scope.get("path", "")
        member = f"{now_ms}:{secrets.token_hex(4)}:{method}:{path}"

        try:
            pipe = redis.pipeline()
            pipe.zremrangebyscore(window_key, 0, cutoff_ms)
            pipe.zadd(window_key, {member: now_ms})
            pipe.zcard(window_key)
            pipe.expire(window_key, WINDOW_SECONDS * 2)
            _, _, count, _ = await pipe.execute()
            request_count = int(count)
        except Exception:
            logger.warning("throttle_redis_unavailable", path=path, method=method)
            await self.app(scope, receive, send)
            return
        remaining = max(0, HARD_THRESHOLD - request_count)
        rate_limit_headers = {
            "X-RateLimit-Limit": str(HARD_THRESHOLD),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_at),
        }

        if request_count > HARD_THRESHOLD:
            state = scope.get("state")
            correlation_id = normalize_correlation_id(None)
            if isinstance(state, dict):
                correlation_id = normalize_correlation_id(
                    state.get("correlation_id")
                )
            logger.warning(
                "request_throttled",
                key=principal,
                count=request_count,
                threshold=HARD_THRESHOLD,
                path=path,
                method=method,
                correlation_id=correlation_id,
            )
            response_headers = {
                **rate_limit_headers,
                "Retry-After": str(WINDOW_SECONDS),
            }
            response = JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests",
                    "error": "Too many requests",
                    "correlation_id": correlation_id,
                },
                headers=response_headers,
            )
            await response(scope, receive, send)
            return

        # Navigation can legitimately issue several concurrent GETs (list,
        # detail, and reference data). Continue counting those requests toward
        # the hard limit, but do not add an artificial delay before the hard
        # protection has been reached. Writes retain progressive backpressure.
        if self._should_apply_soft_delay(method) and request_count > SOFT_THRESHOLD:
            ratio = min(1.0, (request_count - SOFT_THRESHOLD) / (HARD_THRESHOLD - SOFT_THRESHOLD))
            delay = MIN_DELAY + ((MAX_DELAY - MIN_DELAY) * ratio)
            await asyncio.sleep(delay)

        async def send_with_rate_headers(message: Message) -> None:
            if message.get("type") == "http.response.start":
                original_headers = list(message.get("headers", []))
                original_headers.extend(self._dict_to_headers(rate_limit_headers))
                message["headers"] = original_headers
            await send(message)

        await self.app(scope, receive, send_with_rate_headers)
