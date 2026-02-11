from __future__ import annotations

import asyncio
import secrets
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger
from app.core.rate_limit import rate_limit_key
from app.core.redis import get_redis

logger = get_logger(__name__)

WINDOW_SECONDS = 60
SOFT_THRESHOLD = 60
HARD_THRESHOLD = 100
MIN_DELAY = 0.1
MAX_DELAY = 0.5


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

        pipe = redis.pipeline()
        pipe.zremrangebyscore(window_key, 0, cutoff_ms)
        pipe.zadd(window_key, {member: now_ms})
        pipe.zcard(window_key)
        pipe.expire(window_key, WINDOW_SECONDS * 2)
        _, _, count, _ = await pipe.execute()
        request_count = int(count)
        remaining = max(0, HARD_THRESHOLD - request_count)
        rate_limit_headers = {
            "X-RateLimit-Limit": str(HARD_THRESHOLD),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_at),
        }

        if request_count > HARD_THRESHOLD:
            state = scope.get("state")
            correlation_id = "unknown"
            if isinstance(state, dict):
                correlation_id = str(state.get("correlation_id", "unknown"))
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

        if request_count > SOFT_THRESHOLD:
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
