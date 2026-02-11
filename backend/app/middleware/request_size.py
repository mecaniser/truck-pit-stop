from __future__ import annotations

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyTooLargeError(Exception):
    """Raised when request body size exceeds configured max bytes."""


class RequestBodyLimitMiddleware:
    """Reject oversized API request bodies with HTTP 413."""

    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    @staticmethod
    def _should_apply(scope: Scope) -> bool:
        if scope.get("type") != "http":
            return False
        path = scope.get("path", "")
        if not path.startswith("/api/v1"):
            return False
        return True

    @staticmethod
    def _headers_to_dict(scope: Scope) -> dict[str, str]:
        headers: dict[str, str] = {}
        for key, value in scope.get("headers", []):
            headers[key.decode("latin1").lower()] = value.decode("latin1")
        return headers

    @staticmethod
    def _extract_correlation_id(scope: Scope, headers: dict[str, str]) -> str:
        state = scope.get("state")
        if isinstance(state, dict):
            correlation_id = state.get("correlation_id")
            if correlation_id:
                return str(correlation_id)
        return headers.get("x-correlation-id", "unknown")

    async def _send_413(self, send: Send, correlation_id: str) -> None:
        response = JSONResponse(
            status_code=413,
            content={
                "detail": f"Request body too large (max {self.max_body_bytes} bytes)",
                "error": "Request body too large",
                "correlation_id": correlation_id,
            },
            headers={"X-Correlation-ID": correlation_id},
        )
        await send(
            {
                "type": "http.response.start",
                "status": response.status_code,
                "headers": [(k.encode("latin1"), v.encode("latin1")) for k, v in response.headers.items()],
            }
        )
        await send({"type": "http.response.body", "body": response.body, "more_body": False})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._should_apply(scope):
            await self.app(scope, receive, send)
            return

        headers = self._headers_to_dict(scope)
        correlation_id = self._extract_correlation_id(scope, headers)

        content_length = headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_body_bytes:
                    await self._send_413(send, correlation_id)
                    return
            except ValueError:
                # Let downstream parsers decide how to handle malformed lengths.
                pass

        consumed_bytes = 0

        async def limited_receive() -> Message:
            nonlocal consumed_bytes

            message = await receive()
            if message.get("type") != "http.request":
                return message

            chunk = message.get("body", b"")
            consumed_bytes += len(chunk)
            if consumed_bytes > self.max_body_bytes:
                raise RequestBodyTooLargeError
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLargeError:
            await self._send_413(send, correlation_id)
