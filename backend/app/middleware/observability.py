"""
Observability Middleware

Provides request tracing with correlation IDs, request/response logging,
and timing metrics for all HTTP requests.
"""
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging import get_logger, bind_contextvars, clear_contextvars
from app.core.metrics import normalize_endpoint_label, record_endpoint_duration
from app.core.redaction import redact_sensitive, redact_text
from app.core.request_performance import (
    begin_request_database_stats,
    end_request_database_stats,
)
from app.core.request_activity import request_activity_window

logger = get_logger(__name__)

# Header name for correlation ID
CORRELATION_ID_HEADER = "X-Correlation-ID"


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds observability features to all requests:
    
    1. Generates or accepts correlation IDs for request tracing
    2. Logs request start/end with timing
    3. Binds request context to all logs
    4. Returns correlation ID in response headers
    """
    
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate or use existing correlation ID
        correlation_id = request.headers.get(CORRELATION_ID_HEADER) or str(uuid.uuid4())
        
        # Store in request state for access in endpoints
        request.state.correlation_id = correlation_id
        
        # Get client IP (handle proxies)
        client_ip = self._get_client_ip(request)
        
        # Bind context for all logs in this request
        bind_contextvars(
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
            client_ip=client_ip,
        )
        
        # Start timing and request-scoped database accounting.
        start_time = time.perf_counter()
        database_stats_token = begin_request_database_stats()
        database_stats = None
        
        # Log request start (debug level to avoid noise)
        logger.debug(
            "request_started",
            query_params=(
                redact_sensitive(dict(request.query_params))
                if request.query_params
                else None
            ),
            user_agent=request.headers.get("user-agent"),
        )
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Log request completion
            log_method = logger.warning if response.status_code >= 400 else logger.info
            database_stats = end_request_database_stats(database_stats_token)
            endpoint = (
                normalize_endpoint_label(request.scope.get("route").path)
                if request.scope.get("route")
                else normalize_endpoint_label(request.url.path)
            )
            record_endpoint_duration(
                endpoint, request.method, response.status_code, duration_ms
            )
            request_activity_window.record(endpoint, duration_ms, response.status_code)
            log_method(
                "request_completed",
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
                endpoint=endpoint,
                response_size_bytes=int(response.headers.get("content-length", 0)),
                **self._database_log_fields(database_stats),
            )
            
            # Add correlation ID to response headers
            response.headers[CORRELATION_ID_HEADER] = correlation_id
            
            return response
            
        except Exception as exc:
            # Calculate duration even on error
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Log the exception (will be re-raised)
            if database_stats is None:
                database_stats = end_request_database_stats(database_stats_token)
            logger.error(
                "request_failed",
                duration_ms=round(duration_ms, 2),
                error_type=type(exc).__name__,
                error_message=redact_text(str(exc)),
                **self._database_log_fields(database_stats),
            )
            raise
            
        finally:
            # Cancellation does not enter the Exception branch, but must not
            # leave request-local accounting bound to its task context.
            if database_stats is None:
                end_request_database_stats(database_stats_token)
            # Clear context at end of request
            clear_contextvars()

    @staticmethod
    def _database_log_fields(stats) -> dict:
        return {
            "db_query_count": stats.query_count,
            "db_duration_ms": round(stats.total_duration_ms, 2),
            "db_slowest_query_ms": round(stats.slowest_duration_ms, 2),
            "db_slowest_operation": stats.slowest_operation,
        }
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP, handling common proxy headers."""
        # Check X-Forwarded-For (comma-separated list, first is client)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        # Check X-Real-IP
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fall back to direct client
        if request.client:
            return request.client.host
        
        return "unknown"


def get_correlation_id(request: Request) -> str:
    """
    Get correlation ID from request state.
    
    Usage in endpoints:
        @router.get("/example")
        async def example(request: Request):
            correlation_id = get_correlation_id(request)
    """
    return getattr(request.state, "correlation_id", "unknown")
