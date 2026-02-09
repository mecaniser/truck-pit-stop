# Observability Implementation Plan

Self-hosted monitoring and error tracking system for TruckPitStop.

**Created:** 2026-02-08  
**Status:** Implemented

---

## Overview

Build a full observability stack without external services (Sentry, Datadog, etc.). All data stays on your infrastructure.

### Goals
- Structured JSON logging for log aggregation
- Request tracing with correlation IDs
- Prometheus metrics for dashboards/alerting
- Global exception handling with context
- Enhanced health checks for orchestration

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI App                              │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  Logging    │  │  Metrics    │  │  Tracing Middleware     │  │
│  │  (structlog)│  │ (prometheus)│  │  (correlation IDs)      │  │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘  │
│         │                │                     │                 │
│         ▼                ▼                     ▼                 │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              Observability Middleware                        ││
│  │  - Injects correlation_id into every request                ││
│  │  - Logs request/response with timing                        ││
│  │  - Records metrics (latency, status codes)                  ││
│  │  - Captures exceptions with full context                    ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
         │                │                     │
         ▼                ▼                     ▼
   ┌──────────┐    ┌──────────────┐    ┌──────────────┐
   │  stdout  │    │  /metrics    │    │  Log Files   │
   │  (JSON)  │    │  (Prometheus)│    │  (optional)  │
   └────┬─────┘    └──────┬───────┘    └──────────────┘
        │                 │
        ▼                 ▼
   ┌──────────┐    ┌──────────────┐
   │  Loki /  │    │  Prometheus  │
   │  ELK     │    │  + Grafana   │
   └──────────┘    └──────────────┘
```

---

## Implementation Phases

### Phase 1: Structured Logging

**Files to create/modify:**
- `backend/app/core/logging.py` (new)
- `backend/app/main.py` (modify)
- `backend/app/core/config.py` (add settings)

**Tasks:**
- [x] **1.1** Create `logging.py` with structlog configuration
- [x] **1.2** Configure JSON formatter for production, pretty-print for dev
- [x] **1.3** Add log level configuration via environment variable
- [ ] **1.4** Replace all `print()` statements with structured logging
- [x] **1.5** Add context processors (timestamp, level, logger name)

**Dependencies:**
```
structlog>=24.1.0
python-json-logger>=2.0.7
```

**Config additions:**
```python
# config.py
LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT: str = "json"  # "json" or "console"
```

---

### Phase 2: Request Tracing

**Files to create/modify:**
- `backend/app/middleware/observability.py` (new)
- `backend/app/main.py` (add middleware)

**Tasks:**
- [x] **2.1** Create middleware that generates `X-Correlation-ID` per request
- [x] **2.2** Accept existing correlation ID from headers (for distributed tracing)
- [x] **2.3** Bind correlation ID to structlog context
- [x] **2.4** Include correlation ID in all log entries
- [x] **2.5** Return correlation ID in response headers
- [x] **2.6** Log request start/end with timing

**Request context to capture:**
```python
{
    "correlation_id": "uuid",
    "method": "POST",
    "path": "/api/v1/auth/login",
    "user_id": "uuid or null",
    "tenant_id": "uuid or null",
    "client_ip": "x.x.x.x",
    "user_agent": "...",
    "duration_ms": 123,
    "status_code": 200
}
```

---

### Phase 3: Prometheus Metrics

**Files to create/modify:**
- `backend/app/core/metrics.py` (new)
- `backend/app/main.py` (add instrumentator)

**Tasks:**
- [x] **3.1** Install and configure `prometheus-fastapi-instrumentator`
- [x] **3.2** Expose `/metrics` endpoint
- [x] **3.3** Add default metrics (request count, latency histogram)
- [x] **3.4** Add custom business metrics:
  - Active users (gauge)
  - Login attempts (counter, success/failure)
  - Repair orders created (counter by tenant)
  - Quote approval rate (counter)
  - Background job durations (histogram)
- [ ] **3.5** Add database pool metrics (future)
- [ ] **3.6** Add Redis connection metrics (future)

**Default metrics exposed:**
| Metric | Type | Description |
|--------|------|-------------|
| `http_requests_total` | Counter | Total requests by method, path, status |
| `http_request_duration_seconds` | Histogram | Request latency distribution |
| `http_requests_in_progress` | Gauge | Currently processing requests |

**Custom metrics:**
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `auth_login_total` | Counter | status, tenant_id | Login attempts |
| `repair_orders_created_total` | Counter | tenant_id | Orders created |
| `quotes_total` | Counter | status, tenant_id | Quote outcomes |
| `db_pool_size` | Gauge | - | Active DB connections |
| `db_pool_overflow` | Gauge | - | Overflow connections |

---

### Phase 4: Global Exception Handler

**Files to modify:**
- `backend/app/main.py`

**Tasks:**
- [x] **4.1** Add global exception handler for unhandled exceptions
- [x] **4.2** Log full stack trace with request context
- [x] **4.3** Return sanitized error to client (no internal details)
- [ ] **4.4** Increment error counter metric (future)
- [x] **4.5** Handle specific exception types differently:
  - `HTTPException` → pass through
  - `ValidationError` → 422 with details
  - `SQLAlchemyError` → 500, log details
  - `Exception` → 500, generic message

**Error response format:**
```json
{
    "error": "Internal server error",
    "correlation_id": "abc-123",
    "message": "An unexpected error occurred. Reference ID: abc-123"
}
```

---

### Phase 5: Enhanced Health Checks

**Files to modify:**
- `backend/app/main.py`

**Tasks:**
- [x] **5.1** Enhance `/health` → basic liveness probe
- [x] **5.2** Enhance `/health/ready` → full readiness check:
  - Database connection
  - Redis connection
  - Critical config validation
- [x] **5.3** Add `/health/live` → Kubernetes liveness probe
- [x] **5.4** Add component status in response
- [x] **5.5** Add startup time and version info

**Health response format:**
```json
{
    "status": "healthy",
    "version": "1.0.0",
    "uptime_seconds": 3600,
    "checks": {
        "database": {"status": "ok", "latency_ms": 5},
        "redis": {"status": "ok", "latency_ms": 2},
        "config": {"status": "ok"}
    }
}
```

---

## File Structure (Final)

```
backend/app/
├── core/
│   ├── config.py          # + LOG_LEVEL, LOG_FORMAT
│   ├── logging.py         # NEW: structlog config
│   └── metrics.py         # NEW: Prometheus metrics
├── middleware/
│   └── observability.py   # NEW: tracing + logging middleware
└── main.py                # Modified: middleware, exception handler, health
```

---

## Dependencies to Add

```txt
# requirements.txt additions
structlog>=24.1.0
python-json-logger>=2.0.7
prometheus-fastapi-instrumentator>=6.1.0
```

---

## Configuration

Add to `backend/.env`:

```bash
# Observability
LOG_LEVEL=INFO              # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT=json             # "json" for production, "console" for dev
METRICS_ENABLED=true        # Enable /metrics endpoint
```

---

## Testing Plan

| Component | Test |
|-----------|------|
| Logging | Verify JSON output, check all fields present |
| Correlation ID | Send request, verify ID in response header and logs |
| Metrics | Curl `/metrics`, verify Prometheus format |
| Exception handler | Trigger error, verify sanitized response + logged details |
| Health checks | Stop DB, verify `/health/ready` returns unhealthy |

---

## Deployment Considerations

### Log Aggregation Options

| Tool | Complexity | Cost |
|------|------------|------|
| **Loki + Grafana** | Medium | Free (self-hosted) |
| **ELK Stack** | High | Free (self-hosted) |
| **File + logrotate** | Low | Free |

### Metrics Visualization

1. **Prometheus** - scrapes `/metrics` endpoint
2. **Grafana** - dashboards and alerting
3. **AlertManager** - notification routing

### Recommended Stack (Self-Hosted)

```yaml
# docker-compose.observability.yml
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3001:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin

  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"
```

---

## Rollout Order

1. **Phase 1** (Logging) - Foundation, no breaking changes
2. **Phase 2** (Tracing) - Adds headers, backward compatible
3. **Phase 3** (Metrics) - New endpoint, opt-in
4. **Phase 4** (Exceptions) - Improves error handling
5. **Phase 5** (Health) - Enhances existing endpoints

Each phase can be deployed independently.

---

---

### Phase 6: Error Visibility System

**Status:** ✅ Implemented (2026-02-08)

Build a comprehensive error tracking system with database persistence, searchable dashboard, and Stripe payment error handling.

**Files created:**
- `backend/app/db/models/error_log.py` - ErrorLog model with categories, severity, resolution tracking
- `backend/app/services/error_service.py` - Error logging and querying service
- `backend/alembic/versions/023_add_error_logs.py` - Database migration
- `frontend/src/features/platform-admin/ErrorsTab.tsx` - Error dashboard UI

**Files modified:**
- `backend/app/core/metrics.py` - Added error counter metrics
- `backend/app/main.py` - Enhanced exception handlers (HTTPException, SQLAlchemy, Stripe)
- `backend/app/api/v1/endpoints/payments.py` - Stripe error handling with logging
- `backend/app/api/v1/endpoints/stripe_webhooks.py` - Payment failure webhooks
- `backend/app/api/v1/endpoints/admin.py` - Error management API endpoints
- `frontend/src/features/platform-admin/PlatformAnalyticsPage.tsx` - Added Errors tab

**Tasks:**
- [x] **6.1** Create ErrorLog database model with categories and severity
- [x] **6.2** Create ErrorService for logging and querying errors
- [x] **6.3** Add error counter metrics (ERRORS_TOTAL, PAYMENT_ERRORS_TOTAL)
- [x] **6.4** Enhance global exception handlers with DB persistence
- [x] **6.5** Add Stripe error handling to all payment endpoints
- [x] **6.6** Add Stripe webhooks for payment failures and disputes
- [x] **6.7** Create admin API endpoints for error management
- [x] **6.8** Build ErrorsTab UI with filters, search, and detail modal
- [x] **6.9** Add Errors tab to Platform Analytics page

**Error Categories:**
| Category | Examples | Severity |
|----------|----------|----------|
| `payment` | CardError, PaymentFailed, Dispute | error/critical |
| `auth` | InvalidCredentials, TokenExpired | warning/error |
| `validation` | ValidationError, InvalidInput | warning |
| `database` | ConnectionError, IntegrityError | error/critical |
| `external_api` | StripeAPIError, Timeout | error |
| `unhandled` | Uncaught exceptions | error |

**API Endpoints:**
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/errors` | GET | List errors with filters and pagination |
| `/admin/errors/stats` | GET | Aggregated error statistics |
| `/admin/errors/{id}` | GET | Full error details with stack trace |
| `/admin/errors/correlation/{id}` | GET | Find related errors |
| `/admin/errors/{id}/resolve` | PATCH | Mark error as resolved |
| `/admin/errors/{id}/unresolve` | PATCH | Reopen error |

**Stripe Webhook Events Handled:**
- `payment_intent.payment_failed` - Logs failure reason
- `charge.failed` - Logs charge failure details
- `charge.dispute.created` - CRITICAL severity, immediate attention

---

## Success Criteria

- [x] All logs in JSON format with correlation IDs
- [x] `/metrics` returns valid Prometheus format
- [x] Unhandled exceptions logged with full context
- [x] Health checks report component status
- [ ] No `print()` statements in codebase (pending cleanup)
- [x] Error responses don't leak internal details
- [x] Errors persisted to database for historical analysis
- [x] Error dashboard with search, filter, and resolution tracking
- [x] Payment errors tracked with Stripe-specific context
- [x] Webhook handlers for payment failure events

---

## Future Enhancements

- [ ] Distributed tracing (OpenTelemetry)
- [ ] APM integration
- [ ] Custom dashboards per tenant
- [ ] Anomaly detection alerts
- [ ] Log retention policies
- [ ] PII scrubbing in logs
- [ ] Error data retention cleanup job (90 days)
- [ ] Email alerts for critical errors
- [ ] Error grouping/deduplication
