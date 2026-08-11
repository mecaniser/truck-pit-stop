from __future__ import annotations

import asyncio
from contextlib import suppress

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.correlation import normalize_correlation_id
from app.core.logging import get_logger

logger = get_logger(__name__)


class TimeoutMiddleware:
    """Apply a request timeout to API routes."""

    def __init__(self, app: ASGIApp, timeout_seconds: float = 30.0) -> None:
        self.app = app
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _should_apply(scope: Scope) -> bool:
        if scope.get("type") != "http":
            return False

        path = scope.get("path", "")
        if not path.startswith("/api/v1"):
            return False
        if path.startswith("/api/v1/assets"):
            return False
        return True

    @staticmethod
    def _extract_correlation_id(scope: Scope) -> str:
        state = scope.get("state")
        if isinstance(state, dict):
            correlation_id = state.get("correlation_id")
            if correlation_id:
                return normalize_correlation_id(correlation_id)
        return normalize_correlation_id(None)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._should_apply(scope):
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        task = asyncio.create_task(self.app(scope, receive, send_wrapper))
        try:
            await asyncio.wait_for(task, timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

            correlation_id = self._extract_correlation_id(scope)
            path = scope.get("path", "")
            method = scope.get("method", "GET")
            logger.warning(
                "request_timeout",
                path=path,
                method=method,
                timeout_seconds=self.timeout_seconds,
                correlation_id=correlation_id,
            )

            if response_started:
                # Response stream already started — a fresh 504 frame is not
                # possible (the client already has a 200 status + headers),
                # so this used to just `return`, leaving the connection in
                # an ambiguous half-sent state with no signal anywhere that
                # anything went wrong. Log it loudly (this is a distinct,
                # worse failure mode than a clean pre-response timeout —
                # the client gets a truncated/empty body with no error) and
                # send an empty http.response.body with more_body=False to
                # close the stream deterministically instead of leaving it
                # hanging for the client's own timeout to eventually trip.
                logger.error(
                    "request_timeout_mid_stream",
                    path=path,
                    method=method,
                    timeout_seconds=self.timeout_seconds,
                    correlation_id=correlation_id,
                )
                with suppress(Exception):
                    await send({"type": "http.response.body", "body": b"", "more_body": False})
                return

            response = JSONResponse(
                status_code=504,
                content={
                    "detail": "Request timeout",
                    "error": "Request timeout",
                    "correlation_id": correlation_id,
                },
            )
            await response(scope, receive, send)
