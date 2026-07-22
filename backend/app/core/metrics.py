"""
Prometheus Metrics Configuration

Exposes application metrics for monitoring and alerting.
"""
import re
from typing import Optional

from prometheus_fastapi_instrumentator import Instrumentator, metrics
from prometheus_client import Counter, Histogram, Gauge
from fastapi import FastAPI

from app.core.config import settings

# Custom business metrics
AUTH_LOGIN_TOTAL = Counter(
    "dieselbridge_auth_login_total",
    "Total login attempts",
    ["status", "tenant_id"],
)

AUTH_LOGOUT_TOTAL = Counter(
    "dieselbridge_auth_logout_total",
    "Total logout events",
    ["tenant_id"],
)

REPAIR_ORDERS_CREATED = Counter(
    "dieselbridge_repair_orders_created_total",
    "Total repair orders created",
    ["tenant_id"],
)

QUOTES_TOTAL = Counter(
    "dieselbridge_quotes_total",
    "Total quotes by status",
    ["status", "tenant_id"],
)

PAYMENTS_TOTAL = Counter(
    "dieselbridge_payments_total",
    "Total payment events",
    ["status", "payment_method", "tenant_id"],
)

ACTIVE_USERS = Gauge(
    "dieselbridge_active_users",
    "Currently active users (approximation)",
)

DB_QUERY_DURATION = Histogram(
    "dieselbridge_db_query_duration_seconds",
    "Database query duration",
    ["operation"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

HTTP_ENDPOINT_DURATION = Histogram(
    "dieselbridge_http_endpoint_duration_seconds",
    "End-to-end HTTP request duration by route",
    ["endpoint", "method", "status_code"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.5, 5.0, 10.0, 30.0),
)

EXTERNAL_API_DURATION = Histogram(
    "dieselbridge_external_api_duration_seconds",
    "External API call duration",
    ["service", "operation"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# Error tracking metrics
ERRORS_TOTAL = Counter(
    "dieselbridge_errors_total",
    "Total application errors",
    ["error_type", "error_category", "endpoint"],
)

PAYMENT_ERRORS_TOTAL = Counter(
    "dieselbridge_payment_errors_total",
    "Payment-specific errors",
    ["error_type", "provider"],
)

UNHANDLED_EXCEPTIONS_TOTAL = Counter(
    "dieselbridge_unhandled_exceptions_total",
    "Total unhandled exceptions",
    ["exception_type"],
)


_UUID_PATH_SEGMENT = re.compile(
    r"(?<=/)[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}(?=/|$)"
)


def normalize_endpoint_label(endpoint: Optional[str]) -> str:
    """Return a bounded-cardinality endpoint label for custom metrics.

    Exception handlers receive the concrete request URL, which can contain a
    distinct UUID for every repair order, invoice, vehicle, and so on. Storing
    those raw paths as Prometheus labels can exhaust the metrics process during
    an incident. The normal HTTP instrumentator uses FastAPI route templates;
    this preserves the same safety for custom error metrics until a route
    template is available at every exception boundary.
    """
    path = (endpoint or "unknown").split("?", 1)[0]
    return _UUID_PATH_SEGMENT.sub(":id", path)


def record_endpoint_duration(
    endpoint: str,
    method: str,
    status_code: int,
    duration_ms: float,
) -> None:
    """Record request latency with stable, route-level Prometheus labels."""
    HTTP_ENDPOINT_DURATION.labels(
        endpoint=normalize_endpoint_label(endpoint),
        method=method,
        status_code=str(status_code),
    ).observe(duration_ms / 1000)


def setup_metrics(app: FastAPI) -> Instrumentator:
    """
    Configure Prometheus metrics for the FastAPI application.
    
    Returns the instrumentator for potential customization.
    """
    if not settings.METRICS_ENABLED:
        return None
    
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/health", "/health/live", "/health/ready", "/metrics"],
        inprogress_name="dieselbridge_http_requests_inprogress",
        inprogress_labels=True,
    )
    
    # Add default metrics
    instrumentator.add(
        metrics.default(
            metric_namespace="dieselbridge",
            metric_subsystem="http",
        )
    )
    
    # Add latency histogram with custom buckets
    instrumentator.add(
        metrics.latency(
            metric_namespace="dieselbridge",
            metric_subsystem="http",
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        )
    )
    
    # Add request size
    instrumentator.add(
        metrics.request_size(
            metric_namespace="dieselbridge",
            metric_subsystem="http",
        )
    )
    
    # Add response size
    instrumentator.add(
        metrics.response_size(
            metric_namespace="dieselbridge",
            metric_subsystem="http",
        )
    )
    
    # Instrument the app
    instrumentator.instrument(app)
    
    return instrumentator


# Helper functions for recording custom metrics
def record_login(success: bool, tenant_id: str = "unknown") -> None:
    """Record a login attempt."""
    status = "success" if success else "failure"
    AUTH_LOGIN_TOTAL.labels(status=status, tenant_id=tenant_id).inc()


def record_logout(tenant_id: str = "unknown") -> None:
    """Record a logout event."""
    AUTH_LOGOUT_TOTAL.labels(tenant_id=tenant_id).inc()


def record_repair_order_created(tenant_id: str) -> None:
    """Record a new repair order."""
    REPAIR_ORDERS_CREATED.labels(tenant_id=tenant_id).inc()


def record_quote(status: str, tenant_id: str) -> None:
    """Record a quote event (created, approved, declined, expired)."""
    QUOTES_TOTAL.labels(status=status, tenant_id=tenant_id).inc()


def record_payment(status: str, payment_method: str, tenant_id: str) -> None:
    """Record a payment event."""
    PAYMENTS_TOTAL.labels(
        status=status,
        payment_method=payment_method,
        tenant_id=tenant_id,
    ).inc()


def set_active_users(count: int) -> None:
    """Set the current active user count."""
    ACTIVE_USERS.set(count)


def record_error(
    error_type: str,
    error_category: str,
    endpoint: str = "unknown",
) -> None:
    """Record an application error."""
    ERRORS_TOTAL.labels(
        error_type=error_type,
        error_category=error_category,
        endpoint=normalize_endpoint_label(endpoint),
    ).inc()


def record_payment_error(
    error_type: str,
    provider: str = "stripe",
) -> None:
    """Record a payment-specific error."""
    PAYMENT_ERRORS_TOTAL.labels(
        error_type=error_type,
        provider=provider,
    ).inc()


def record_unhandled_exception(exception_type: str) -> None:
    """Record an unhandled exception."""
    UNHANDLED_EXCEPTIONS_TOTAL.labels(exception_type=exception_type).inc()


class DBQueryTimer:
    """
    Context manager for timing database queries.
    
    Usage:
        with DBQueryTimer("select_user"):
            result = await db.execute(query)
    """
    
    def __init__(self, operation: str):
        self.operation = operation
        self.start_time = None
    
    def __enter__(self):
        import time
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        duration = time.perf_counter() - self.start_time
        DB_QUERY_DURATION.labels(operation=self.operation).observe(duration)
        return False


class ExternalAPITimer:
    """
    Context manager for timing external API calls.
    
    Usage:
        with ExternalAPITimer("stripe", "create_payment_intent"):
            result = await stripe.create_payment_intent(...)
    """
    
    def __init__(self, service: str, operation: str):
        self.service = service
        self.operation = operation
        self.start_time = None
    
    def __enter__(self):
        import time
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        duration = time.perf_counter() - self.start_time
        EXTERNAL_API_DURATION.labels(
            service=self.service,
            operation=self.operation,
        ).observe(duration)
        return False
