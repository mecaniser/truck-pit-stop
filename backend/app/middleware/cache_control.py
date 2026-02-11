from __future__ import annotations

from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class CacheControlMiddleware(BaseHTTPMiddleware):
    """Set strict no-store cache headers for API responses."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    @staticmethod
    def _should_apply(request: Request) -> bool:
        return request.url.path.startswith("/api/v1")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        if self._should_apply(request):
            response.headers["Cache-Control"] = "no-store, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        return response
