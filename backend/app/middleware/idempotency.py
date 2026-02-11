from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from typing import Callable, Optional

from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import get_logger
from app.core.rate_limit import rate_limit_key
from app.core.redis import get_redis

logger = get_logger(__name__)

KEY_HEADER_LOOKUP = "idempotency-key"
REPLAY_HEADER = "X-Idempotency-Replayed"
LOCK_TTL_SECONDS = 30
RESULT_TTL_SECONDS = 24 * 60 * 60
MAX_CACHED_RESPONSE_BYTES = settings.IDEMPOTENCY_MAX_CACHED_RESPONSE_BYTES
STORED_RESPONSE_HEADERS = (
    "content-type",
    "location",
    "cache-control",
    "pragma",
    "expires",
)
CACHEABLE_ERROR_STATUSES = frozenset({400, 409, 422})


class IdempotencyMiddleware:
    """Provide optional idempotent behavior for mutating POST API routes."""

    def __init__(self, app) -> None:
        self.app = app

    @staticmethod
    def _should_apply(scope: dict) -> bool:
        if scope.get("type") != "http":
            return False
        if scope.get("method") != "POST":
            return False

        path = scope.get("path", "")
        if not path.startswith("/api/v1"):
            return False
        if path.startswith("/api/v1/webhooks/"):
            return False
        return True

    @staticmethod
    def _normalize_body(raw_body: bytes) -> str:
        if not raw_body:
            return ""

        try:
            parsed = json.loads(raw_body.decode("utf-8"))
            return json.dumps(parsed, separators=(",", ":"), sort_keys=True)
        except (ValueError, UnicodeDecodeError):
            return raw_body.decode("utf-8", errors="ignore")

    @staticmethod
    def _build_fingerprint(method: str, path: str, principal: str, normalized_body: str) -> str:
        payload = f"{method}|{path}|{principal}|{normalized_body}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _headers_to_dict(raw_headers: list[tuple[bytes, bytes]]) -> dict[str, str]:
        headers: dict[str, str] = {}
        for key, value in raw_headers:
            headers[key.decode("latin1").lower()] = value.decode("latin1")
        return headers

    @staticmethod
    def _dict_to_headers(headers: dict[str, str]) -> list[tuple[bytes, bytes]]:
        return [(k.encode("latin1"), v.encode("latin1")) for k, v in headers.items()]

    @staticmethod
    def _is_cacheable_status(status_code: int) -> bool:
        if 200 <= status_code < 300:
            return True
        return status_code in CACHEABLE_ERROR_STATUSES

    @staticmethod
    async def _send_json(send: Callable, status_code: int, payload: dict, extra_headers: Optional[dict[str, str]] = None) -> None:
        response = JSONResponse(status_code=status_code, content=payload)
        headers = dict(response.headers)
        if extra_headers:
            headers.update(extra_headers)

        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": IdempotencyMiddleware._dict_to_headers(headers),
            }
        )
        await send({"type": "http.response.body", "body": response.body, "more_body": False})

    async def __call__(self, scope, receive, send) -> None:
        if not self._should_apply(scope):
            await self.app(scope, receive, send)
            return

        request_headers = self._headers_to_dict(scope.get("headers", []))
        idempotency_key = request_headers.get(KEY_HEADER_LOOKUP)

        if not idempotency_key:
            # Do not alter receive semantics for non-idempotent requests.
            await self.app(scope, receive, send)
            return

        if len(idempotency_key) < 16 or len(idempotency_key) > 128:
            await self._send_json(send, 400, {"detail": "Idempotency-Key must be 16-128 characters"})
            return

        # Read request body once and re-inject to downstream app.
        body = b""
        while True:
            message = await receive()
            message_type = message.get("type")
            if message_type == "http.disconnect":
                break
            if message_type != "http.request":
                continue
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break

        receive_state = {"sent_body": False, "sent_empty": False}

        async def replay_receive():
            if not receive_state["sent_body"]:
                receive_state["sent_body"] = True
                return {"type": "http.request", "body": body, "more_body": False}
            if not receive_state["sent_empty"]:
                receive_state["sent_empty"] = True
                return {"type": "http.request", "body": b"", "more_body": False}
            return {"type": "http.disconnect"}

        # Build a lightweight request object for key resolution.
        from starlette.requests import Request

        request = Request(scope)
        principal = rate_limit_key(request)
        normalized_body = self._normalize_body(body)
        fingerprint = self._build_fingerprint(scope["method"], scope.get("path", ""), principal, normalized_body)

        redis = await get_redis()
        response_key = f"idempotency:response:{principal}:{idempotency_key}"
        lock_key = f"idempotency:lock:{principal}:{idempotency_key}"

        cached_raw = await redis.get(response_key)
        if cached_raw:
            cached = json.loads(cached_raw)
            if cached.get("fingerprint") != fingerprint:
                logger.warning("idempotency_conflict", key=idempotency_key, path=scope.get("path"))
                await self._send_json(send, 409, {"detail": "Idempotency key reuse with different payload"})
                return

            headers = cached.get("headers", {})
            headers[REPLAY_HEADER] = "true"
            body_bytes = base64.b64decode(cached.get("body_b64", "")) if cached.get("body_b64") else b""

            await send(
                {
                    "type": "http.response.start",
                    "status": int(cached.get("status_code", 200)),
                    "headers": self._dict_to_headers(headers),
                }
            )
            await send({"type": "http.response.body", "body": body_bytes, "more_body": False})
            return

        lock_acquired = await redis.set(lock_key, "1", ex=LOCK_TTL_SECONDS, nx=True)
        if not lock_acquired:
            for _ in range(30):
                await asyncio.sleep(0.1)
                cached_raw = await redis.get(response_key)
                if cached_raw:
                    cached = json.loads(cached_raw)
                    if cached.get("fingerprint") != fingerprint:
                        await self._send_json(send, 409, {"detail": "Idempotency key reuse with different payload"})
                        return
                    headers = cached.get("headers", {})
                    headers[REPLAY_HEADER] = "true"
                    body_bytes = base64.b64decode(cached.get("body_b64", "")) if cached.get("body_b64") else b""
                    await send(
                        {
                            "type": "http.response.start",
                            "status": int(cached.get("status_code", 200)),
                            "headers": self._dict_to_headers(headers),
                        }
                    )
                    await send({"type": "http.response.body", "body": body_bytes, "more_body": False})
                    return
            await self._send_json(send, 409, {"detail": "Request with this idempotency key is already in progress"})
            return

        status_code: int = 500
        response_headers: dict[str, str] = {}
        response_body = b""

        async def capture_send(message):
            nonlocal status_code, response_headers, response_body
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                response_headers = self._headers_to_dict(message.get("headers", []))
            elif message["type"] == "http.response.body":
                response_body += message.get("body", b"")

        try:
            await self.app(scope, replay_receive, capture_send)

            response_headers[REPLAY_HEADER] = "false"

            if self._is_cacheable_status(status_code):
                if len(response_body) <= MAX_CACHED_RESPONSE_BYTES:
                    stored_headers: dict[str, str] = {}
                    for header_name in STORED_RESPONSE_HEADERS:
                        header_value = response_headers.get(header_name)
                        if header_value is not None:
                            stored_headers[header_name] = header_value

                    payload = {
                        "fingerprint": fingerprint,
                        "status_code": status_code,
                        "headers": stored_headers,
                        "body_b64": base64.b64encode(response_body).decode("utf-8"),
                    }
                    await redis.setex(response_key, RESULT_TTL_SECONDS, json.dumps(payload))
                    logger.info("idempotency_stored", key=idempotency_key, path=scope.get("path"), status_code=status_code)
                else:
                    logger.warning(
                        "idempotency_not_stored_body_too_large",
                        key=idempotency_key,
                        path=scope.get("path"),
                        status_code=status_code,
                        body_bytes=len(response_body),
                        max_cached_response_bytes=MAX_CACHED_RESPONSE_BYTES,
                    )

            await send(
                {
                    "type": "http.response.start",
                    "status": status_code,
                    "headers": self._dict_to_headers(response_headers),
                }
            )
            await send({"type": "http.response.body", "body": response_body, "more_body": False})
        finally:
            await redis.delete(lock_key)
