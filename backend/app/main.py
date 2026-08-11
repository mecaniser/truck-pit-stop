import time
import traceback
import asyncio
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.exc import (
    SQLAlchemyError,
    IntegrityError,
    OperationalError,
    TimeoutError as SQLAlchemyTimeoutError,
)
from pydantic import ValidationError
import stripe

from app.core.config import settings
from app.core.correlation import normalize_correlation_id
from app.core.logging import setup_logging, get_logger
from app.core.metrics import setup_metrics, record_error, record_payment_error, record_unhandled_exception
from app.core.rate_limit import limiter
from app.middleware.observability import ObservabilityMiddleware
from app.middleware.timeout import TimeoutMiddleware
from app.middleware.throttling import ThrottlingMiddleware
from app.middleware.cache_control import CacheControlMiddleware
from app.middleware.idempotency import IdempotencyMiddleware
from app.middleware.request_size import RequestBodyLimitMiddleware
from app.api.v1.router import api_router
from app.db.session import engine
from app.core.redis import close_redis, get_redis
from app.core.redaction import redact_sensitive, redact_text
from app.db.models.error_log import ErrorCategory, ErrorSeverity
from app.services import error_service

# Initialize structured logging
setup_logging()
logger = get_logger(__name__)

# Track startup time
_startup_time: float = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global _startup_time
    settings.validate_workos_deployment()
    _startup_time = time.time()
    
    logger.info("application_starting", environment=settings.ENVIRONMENT)
    
    yield
    
    # Shutdown
    logger.info("application_shutting_down")
    try:
        await close_redis()
    finally:
        # Release pooled connections so deploys, test lifespans, and graceful
        # shutdowns do not leave database connections checked out.
        await engine.dispose()


app = FastAPI(
    title="Truck Pit Stop API",
    description="API for managing semi-truck repair garages",
    version="1.0.0",
    lifespan=lifespan,
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Register API middlewares.
# NOTE: Starlette applies middleware in reverse order of registration (last added is outermost).
# Observability must be outermost among API middlewares so correlation IDs are available
# to throttling/timeout short-circuit responses.
app.add_middleware(TimeoutMiddleware, timeout_seconds=30.0)
app.add_middleware(ThrottlingMiddleware)
app.add_middleware(CacheControlMiddleware)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=settings.MAX_REQUEST_BODY_BYTES)
app.add_middleware(ObservabilityMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-Correlation-ID"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses"""
    if request.url.path == "/metrics" and settings.ENVIRONMENT == "production":
        expected_token = settings.METRICS_AUTH_TOKEN
        provided_token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if not expected_token or not secrets.compare_digest(provided_token, expected_token):
            # Avoid advertising a sensitive operational endpoint to callers.
            return JSONResponse(status_code=404, content={"detail": "Not found"})

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if settings.COOKIE_SECURE_EFFECTIVE:  # Only add HSTS in production (HTTPS)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ============ Helper Functions for Exception Handlers ============

def _get_user_context(request: Request) -> tuple[Optional[UUID], Optional[UUID]]:
    """Extract user_id and tenant_id from request state if available."""
    user_id = None
    tenant_id = None
    
    # Try to get user from request state (set by auth middleware/dependencies)
    if hasattr(request.state, "user"):
        user = request.state.user
        if user:
            user_id = getattr(user, "id", None)
            tenant_id = getattr(user, "tenant_id", None)
    
    return user_id, tenant_id


def _get_request_context(request: Request) -> dict:
    """Build sanitized request context for error logging."""
    context = {
        "url": redact_text(str(request.url)),
        "client_ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    
    # Add query params (sanitized by error_service)
    if request.query_params:
        context["query_params"] = redact_sensitive(dict(request.query_params))
    
    return context


def _get_correlation_id(request: Request) -> str:
    """Return only a bounded safe request correlation identifier."""
    correlation_id = normalize_correlation_id(
        getattr(request.state, "correlation_id", None)
    )
    request.state.correlation_id = correlation_id
    return correlation_id


async def _log_error_async(
    error_type: str,
    message: str,
    category: ErrorCategory,
    severity: ErrorSeverity,
    request: Request,
    status_code: int,
    stack_trace: Optional[str] = None,
):
    """Log error to database asynchronously (fire and forget)."""
    try:
        correlation_id = _get_correlation_id(request)
        user_id, tenant_id = _get_user_context(request)
        request_context = _get_request_context(request)
        
        await error_service.log_error(
            error_type=error_type,
            message=message,
            category=category,
            severity=severity,
            correlation_id=correlation_id,
            endpoint=request.url.path,
            method=request.method,
            status_code=status_code,
            user_id=user_id,
            tenant_id=tenant_id,
            stack_trace=stack_trace,
            request_context=request_context,
        )
    except Exception as e:
        # Don't let error logging failures break the response
        logger.error("failed_to_log_error_to_db", error=redact_text(str(e)))


# ============ Global Exception Handlers ============

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Handle HTTPException with logging for 4xx/5xx errors.
    
    - 4xx: Log as warning (client errors)
    - 5xx: Log as error and persist to database
    """
    correlation_id = _get_correlation_id(request)
    
    # Determine severity and category based on status code
    if exc.status_code >= 500:
        severity = ErrorSeverity.ERROR
        category = ErrorCategory.UNHANDLED
        log_level = "error"
    elif exc.status_code >= 400:
        severity = ErrorSeverity.WARNING
        log_level = "warning"
        # Categorize by specific status codes
        if exc.status_code == 422:
            category = ErrorCategory.VALIDATION
        elif exc.status_code in (401, 403):
            category = ErrorCategory.AUTH  # Only auth-related status codes
        else:
            category = ErrorCategory.VALIDATION  # 400, 404, 405, 409, etc.
    else:
        # 1xx, 2xx, 3xx - don't log
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )
    
    # Log to stdout
    getattr(logger, log_level)(
        "http_exception",
        correlation_id=correlation_id,
        path=request.url.path,
        method=request.method,
        status_code=exc.status_code,
        detail=exc.detail,
    )
    
    # Record metric
    record_error(
        error_type="HTTPException",
        error_category=category.value,
        endpoint=request.url.path,
    )
    
    # Persist 5xx errors to database
    if exc.status_code >= 500:
        asyncio.create_task(_log_error_async(
            error_type="HTTPException",
            message=str(exc.detail),
            category=category,
            severity=severity,
            request=request,
            status_code=exc.status_code,
        ))
    
    # Include both 'detail' (FastAPI standard) and 'error' for backward compatibility
    detail_msg = exc.detail if exc.status_code < 500 else "Internal server error"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": detail_msg,  # FastAPI standard - frontend expects this
            "error": detail_msg,   # Additional field for observability
            "correlation_id": correlation_id,
        },
        headers=exc.headers,
    )


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    """Handle Pydantic validation errors."""
    correlation_id = _get_correlation_id(request)
    
    logger.warning(
        "validation_error",
        correlation_id=correlation_id,
        path=request.url.path,
        errors=exc.errors(),
    )
    
    # Record metric
    record_error(
        error_type="ValidationError",
        error_category=ErrorCategory.VALIDATION.value,
        endpoint=request.url.path,
    )
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",  # FastAPI standard
            "error": "Validation error",
            "correlation_id": correlation_id,
            "details": exc.errors(),
        },
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    """
    Handle SQLAlchemy database errors.
    
    - Logs full details internally
    - Returns generic message to client
    - Persists to error log
    """
    correlation_id = _get_correlation_id(request)
    error_type = type(exc).__name__
    
    # A SQLAlchemy timeout at this boundary is pool checkout exhaustion. It is
    # transient, so make that explicit to the client instead of presenting it
    # as a generic database failure that invites an immediate retry storm.
    is_pool_timeout = isinstance(exc, SQLAlchemyTimeoutError)

    # Determine severity
    if isinstance(exc, OperationalError):
        severity = ErrorSeverity.CRITICAL
    elif isinstance(exc, IntegrityError):
        severity = ErrorSeverity.ERROR
    else:
        severity = ErrorSeverity.ERROR
    
    # Log full error details
    logger.error(
        "database_error",
        correlation_id=correlation_id,
        path=request.url.path,
        method=request.method,
        error_type=error_type,
        error_message=str(exc),
        traceback=traceback.format_exc(),
    )
    
    # Record metric
    record_error(
        error_type=error_type,
        error_category=ErrorCategory.DATABASE.value,
        endpoint=request.url.path,
    )
    record_unhandled_exception(error_type)
    
    # Persist to database (use a separate connection since current may be broken)
    status_code = 503 if is_pool_timeout else 500
    asyncio.create_task(_log_error_async(
        error_type=error_type,
        message=str(exc),
        category=ErrorCategory.DATABASE,
        severity=severity,
        request=request,
        status_code=status_code,
        stack_trace=traceback.format_exc(),
    ))

    if is_pool_timeout:
        return JSONResponse(
            status_code=status_code,
            content={
                "detail": "Database temporarily unavailable. Please try again.",
                "error": "Database temporarily unavailable",
                "correlation_id": correlation_id,
            },
            headers={"Retry-After": "1"},
        )
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Database error",  # FastAPI standard
            "error": "Database error",
            "correlation_id": correlation_id,
            "message": f"A database error occurred. Reference: {correlation_id}",
        },
    )


@app.exception_handler(stripe.error.StripeError)
async def stripe_exception_handler(request: Request, exc: stripe.error.StripeError):
    """
    Handle Stripe API errors.
    
    Different error types get different handling:
    - CardError: 400, user-friendly message
    - InvalidRequestError: 400, generic message
    - AuthenticationError: 500, critical
    - RateLimitError: 503, retry later
    - APIConnectionError: 503, retry later
    """
    correlation_id = _get_correlation_id(request)
    error_type = type(exc).__name__
    
    # Determine status code and message based on error type
    if isinstance(exc, stripe.error.CardError):
        status_code = 400
        severity = ErrorSeverity.WARNING
        # CardError has user-friendly messages
        user_message = exc.user_message or "Your card was declined"
    elif isinstance(exc, stripe.error.InvalidRequestError):
        status_code = 400
        severity = ErrorSeverity.ERROR
        user_message = "Invalid payment request"
    elif isinstance(exc, stripe.error.AuthenticationError):
        status_code = 500
        severity = ErrorSeverity.CRITICAL
        user_message = "Payment service configuration error"
    elif isinstance(exc, stripe.error.RateLimitError):
        status_code = 503
        severity = ErrorSeverity.WARNING
        user_message = "Payment service temporarily unavailable. Please try again."
    elif isinstance(exc, stripe.error.APIConnectionError):
        status_code = 503
        severity = ErrorSeverity.ERROR
        user_message = "Unable to connect to payment service. Please try again."
    else:
        status_code = 500
        severity = ErrorSeverity.ERROR
        user_message = "Payment processing error"
    
    # Log full error details
    logger.error(
        "stripe_error",
        correlation_id=correlation_id,
        path=request.url.path,
        method=request.method,
        error_type=error_type,
        error_code=getattr(exc, "code", None),
        error_message=str(exc),
        stripe_error_code=getattr(exc, "code", None),
        stripe_param=getattr(exc, "param", None),
    )
    
    # Record metrics
    record_error(
        error_type=error_type,
        error_category=ErrorCategory.PAYMENT.value,
        endpoint=request.url.path,
    )
    record_payment_error(error_type=error_type, provider="stripe")
    
    # Persist to database
    asyncio.create_task(_log_error_async(
        error_type=error_type,
        message=str(exc),
        category=ErrorCategory.PAYMENT,
        severity=severity,
        request=request,
        status_code=status_code,
        stack_trace=traceback.format_exc(),
    ))
    
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": user_message,  # FastAPI standard - frontend expects this
            "error": "Payment error",
            "correlation_id": correlation_id,
            "message": user_message,
            "code": getattr(exc, "code", None),
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catch-all exception handler for unhandled errors.
    
    - Logs full details internally
    - Returns sanitized message to client
    - Includes correlation ID for debugging
    - Persists to error log database
    """
    correlation_id = _get_correlation_id(request)
    error_type = type(exc).__name__
    
    # Log full error details
    logger.error(
        "unhandled_exception",
        correlation_id=correlation_id,
        path=request.url.path,
        method=request.method,
        error_type=error_type,
        error_message=str(exc),
        traceback=traceback.format_exc(),
    )
    
    # Record metrics
    record_error(
        error_type=error_type,
        error_category=ErrorCategory.UNHANDLED.value,
        endpoint=request.url.path,
    )
    record_unhandled_exception(error_type)
    
    # Persist to database
    asyncio.create_task(_log_error_async(
        error_type=error_type,
        message=str(exc),
        category=ErrorCategory.UNHANDLED,
        severity=ErrorSeverity.ERROR,
        request=request,
        status_code=500,
        stack_trace=traceback.format_exc(),
    ))
    
    # Return sanitized response
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",  # FastAPI standard
            "error": "Internal server error",
            "correlation_id": correlation_id,
            "message": f"An unexpected error occurred. Reference: {correlation_id}",
        },
    )


# ============ Health Check Endpoints ============

@app.get("/health", tags=["Health"])
async def health_check():
    """Basic liveness probe - is the process running?"""
    return {"status": "alive"}


@app.get("/health/live", tags=["Health"])
async def liveness_check():
    """Kubernetes liveness probe."""
    return {"status": "alive"}


@app.get("/health/ready", tags=["Health"])
async def readiness_check():
    """
    Kubernetes readiness probe - can we handle requests?
    
    Checks:
    - Database connection
    - Redis connection
    """
    checks = {}
    all_ok = True
    
    # Check database
    try:
        start = time.perf_counter()
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        latency_ms = (time.perf_counter() - start) * 1000
        checks["database"] = {"status": "ok", "latency_ms": round(latency_ms, 2)}
    except Exception as e:
        logger.error("health_check_database_failed", error=str(e))
        checks["database"] = {"status": "failed", "error": "Connection failed"}
        all_ok = False
    
    # Check Redis
    try:
        start = time.perf_counter()
        redis = await get_redis()
        await redis.ping()
        latency_ms = (time.perf_counter() - start) * 1000
        checks["redis"] = {"status": "ok", "latency_ms": round(latency_ms, 2)}
    except Exception as e:
        logger.error("health_check_redis_failed", error=str(e))
        checks["redis"] = {"status": "failed", "error": "Connection failed"}
        all_ok = False
    
    # Calculate uptime
    uptime_seconds = round(time.time() - _startup_time) if _startup_time else 0
    
    response = {
        "status": "ready" if all_ok else "not_ready",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "uptime_seconds": uptime_seconds,
        "checks": checks,
    }
    
    status_code = 200 if all_ok else 503
    return JSONResponse(content=response, status_code=status_code)


@app.get("/health/db", tags=["Health"])
async def db_health_check():
    """Legacy database health check (kept for compatibility)."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Database connection unavailable")


# ============ API Router ============

app.include_router(api_router, prefix="/api/v1")


# ============ Metrics Endpoint ============
# Must be registered BEFORE catch-all SPA routes

instrumentator = setup_metrics(app)
if instrumentator:
    instrumentator.expose(app, endpoint="/metrics", include_in_schema=False)
    logger.info("metrics_enabled", endpoint="/metrics")


# ============ Frontend Static Files ============

frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    # Serve static assets (JS, CSS, etc.)
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")
    
    # Serve root-level static files used by the frontend shell (favicon, logos, robots, etc.)
    static_files = [
        "favicon.ico",
        "robots.txt",
        "sitemap.xml",
        "DB_bridge_logo_favi_figma_public.svg",
        "DB_bridge_logo_favi_figma_public.png",
        "DB_bridge_logo_favi_figma_public_B.svg",
        "DB_bridge_logo_favi_figma_public_B.png",
        "DB_bridge_logo_favi_figma_admin.svg",
        "DB_bridge_logo_favi_figma_admin.png",
        "DB-favicon-corrected-transparent-admin.png",
        "DB_bridge_logo_figma.png",
        "logo-transparent.png",
    ]
    for filename in static_files:
        file_path = frontend_dist / filename
        if file_path.exists():
            async def serve_static_file(path: Path = file_path):
                return FileResponse(str(path))

            app.add_api_route(
                f"/{filename}",
                serve_static_file,
                methods=["GET"],
                include_in_schema=False,
            )
    
    # Serve index.html for root and all non-API routes (SPA routing)
    @app.get("/")
    async def serve_root():
        index_path = frontend_dist / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"status": "ok", "message": "Truck Pit Stop API - Frontend not built"}
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Don't serve index.html for API routes
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        
        # Don't serve index.html for static assets
        if full_path.startswith("assets/"):
            raise HTTPException(status_code=404, detail="Not found")
        
        # Don't serve index.html for health/metrics endpoints
        if full_path.startswith(("health", "metrics")):
            raise HTTPException(status_code=404, detail="Not found")
        
        index_path = frontend_dist / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        raise HTTPException(status_code=404, detail="Frontend not built")
else:
    # Fallback if frontend not built
    @app.get("/")
    async def root():
        return {"status": "ok", "message": "Truck Pit Stop API"}
    
    @app.get("/{full_path:path}")
    async def fallback_spa(full_path: str):
        # Don't catch API, health, or metrics routes
        if full_path.startswith(("api/", "health", "metrics")):
            raise HTTPException(status_code=404, detail="Not found")
        raise HTTPException(status_code=404, detail="Frontend not built")
