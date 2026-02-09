# Observability Guide for Beginners

This guide explains application monitoring, logging, and metrics in plain English. If you're new to observability, start here.

---

## Table of Contents

1. [What is Observability?](#what-is-observability)
2. [The Three Pillars](#the-three-pillars)
3. [Structured Logging](#structured-logging)
4. [Request Tracing](#request-tracing)
5. [Metrics & Monitoring](#metrics--monitoring)
6. [Health Checks](#health-checks)
7. [Error Handling](#error-handling)
8. [Error Tracking System](#error-tracking-system)
9. [Common Tools](#common-tools)
10. [Glossary](#glossary)

---

## What is Observability?

**Observability** = Understanding what's happening inside your application by looking at its outputs.

Think of it like a car dashboard:
- **Speedometer** → Request rate
- **Fuel gauge** → Memory/CPU usage
- **Check engine light** → Error alerts
- **Trip computer** → Request logs

### Why It Matters

Without observability:
```
User: "The app is slow"
You: "Which page? When? For how long? What were you doing?"
User: "I don't know, it was just slow"
You: 😭
```

With observability:
```
Alert: "Latency spike on /api/v1/quotes at 14:32"
Logs: "Database query took 5000ms, correlation_id: abc-123"
Metrics: "DB connection pool exhausted"
You: "Found it! DB pool needs tuning" 🎯
```

---

## The Three Pillars

Observability has three main components:

| Pillar | What It Is | Example |
|--------|------------|---------|
| **Logs** | Detailed event records | "User john@example.com logged in at 14:32:05" |
| **Metrics** | Numeric measurements over time | "Average response time: 150ms" |
| **Traces** | Request journey through the system | "Request abc-123 → auth → db → response" |

### How They Work Together

```
User reports: "Checkout is broken"

1. METRICS show: Error rate spiked at 14:30
2. LOGS show: "Payment service timeout" with correlation_id: xyz-789
3. TRACES show: Request xyz-789 waited 30s for payment API

Root cause: Payment provider had an outage
```

---

## Structured Logging

### The Problem with Basic Logging

```python
# Bad: Unstructured logging
print(f"User {user_id} logged in")
logger.info(f"Order {order_id} created for ${amount}")
```

Output:
```
User 123 logged in
Order 456 created for $99.99
```

**Problems:**
- Can't search by user_id
- Can't filter by order amount
- Can't correlate related events
- Different formats everywhere

### The Solution: Structured Logs

```python
# Good: Structured logging
logger.info("user_login", user_id=123, ip="1.2.3.4")
logger.info("order_created", order_id=456, amount=99.99, user_id=123)
```

Output (JSON):
```json
{"event": "user_login", "user_id": 123, "ip": "1.2.3.4", "timestamp": "2026-02-08T14:32:05Z"}
{"event": "order_created", "order_id": 456, "amount": 99.99, "user_id": 123, "timestamp": "2026-02-08T14:32:06Z"}
```

**Benefits:**
- Machine-readable (JSON)
- Searchable: `user_id=123`
- Filterable: `amount > 100`
- Consistent format

### Log Levels

| Level | When to Use | Example |
|-------|-------------|---------|
| **DEBUG** | Detailed debugging info | "Parsing request body: {...}" |
| **INFO** | Normal operations | "User logged in" |
| **WARNING** | Something unexpected but handled | "Rate limit approaching" |
| **ERROR** | Something failed | "Database query failed" |
| **CRITICAL** | System is unusable | "Cannot connect to database" |

```python
logger.debug("Checking password hash")      # Only in development
logger.info("Login successful", user_id=1)  # Normal operation
logger.warning("Login attempt #4", user_id=1)  # Suspicious
logger.error("Login failed", user_id=1, reason="invalid_password")
logger.critical("Database connection lost")  # Wake someone up!
```

### What to Log

**DO log:**
- Authentication events (login, logout, failed attempts)
- Authorization failures (access denied)
- Business events (order created, payment processed)
- Errors with context
- Performance issues (slow queries)

**DON'T log:**
- Passwords (even hashed)
- Full credit card numbers
- Personal health information
- Session tokens
- API keys

```python
# Bad
logger.info("Login", password=user_password)  # NEVER!

# Good
logger.info("Login attempt", user_email=email, success=False)
```

---

## Request Tracing

### What is a Correlation ID?

A **correlation ID** is a unique identifier that follows a request through your entire system.

```
Without correlation ID:
  Log 1: "User logged in"
  Log 2: "Database error"
  Log 3: "Payment failed"
  Question: Are these related? 🤷

With correlation ID:
  Log 1: "User logged in" correlation_id=abc-123
  Log 2: "Database error" correlation_id=xyz-789
  Log 3: "Payment failed" correlation_id=abc-123
  Answer: Logs 1 and 3 are the same request! ✅
```

### How It Works

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Client  │────▶│  API     │────▶│  Service │────▶│ Database │
│          │     │          │     │          │     │          │
│          │     │ id=abc   │     │ id=abc   │     │ id=abc   │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
                      │                │                │
                      ▼                ▼                ▼
                 ┌─────────────────────────────────────────┐
                 │              Log Aggregator             │
                 │  Search: correlation_id=abc             │
                 │  Result: All 3 logs for this request    │
                 └─────────────────────────────────────────┘
```

### Implementation

```python
# Middleware adds correlation ID to every request
@app.middleware("http")
async def add_correlation_id(request, call_next):
    # Use existing ID or generate new one
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    
    # Add to logging context
    with structlog.contextvars.bind_contextvars(correlation_id=correlation_id):
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response
```

Now every log automatically includes the correlation ID:
```json
{"event": "login_attempt", "correlation_id": "abc-123", "user_id": 1}
{"event": "db_query", "correlation_id": "abc-123", "duration_ms": 50}
{"event": "login_success", "correlation_id": "abc-123", "user_id": 1}
```

---

## Metrics & Monitoring

### What are Metrics?

**Metrics** = Numbers that describe your system's behavior over time.

```
Logs tell you WHAT happened:
  "Request to /api/orders took 500ms"

Metrics tell you HOW MUCH:
  "Average latency: 150ms, 99th percentile: 500ms, requests/sec: 100"
```

### Metric Types

| Type | Description | Example |
|------|-------------|---------|
| **Counter** | Only goes up | Total requests, total errors |
| **Gauge** | Goes up and down | Current memory usage, active connections |
| **Histogram** | Distribution of values | Request latency buckets |

```python
# Counter: Total login attempts
login_attempts.inc()  # Now: 1, 2, 3, 4...

# Gauge: Current active users
active_users.set(150)  # Can be 150, then 140, then 160

# Histogram: Request duration
request_duration.observe(0.150)  # Records 150ms in appropriate bucket
```

### Common Metrics to Track

**RED Method** (for services):
- **R**ate: Requests per second
- **E**rrors: Failed requests per second
- **D**uration: How long requests take

**USE Method** (for resources):
- **U**tilization: % of resource used
- **S**aturation: Queue depth / waiting
- **E**rrors: Error count

### Prometheus Format

Prometheus is the standard for metrics. Format:

```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",path="/api/orders",status="200"} 1234
http_requests_total{method="POST",path="/api/orders",status="201"} 567
http_requests_total{method="POST",path="/api/orders",status="500"} 12

# HELP http_request_duration_seconds Request latency
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{le="0.1"} 800
http_request_duration_seconds_bucket{le="0.5"} 950
http_request_duration_seconds_bucket{le="1.0"} 1000
http_request_duration_seconds_sum 150.5
http_request_duration_seconds_count 1000
```

### Alerting

Metrics enable alerting rules:

```yaml
# Alert if error rate > 5% for 5 minutes
- alert: HighErrorRate
  expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "High error rate detected"
```

---

## Health Checks

### Why Health Checks?

Health checks tell orchestrators (Kubernetes, load balancers) if your app is working.

```
Load Balancer
     │
     ├── Server 1: /health → 200 OK ✅ (send traffic)
     ├── Server 2: /health → 200 OK ✅ (send traffic)
     └── Server 3: /health → 503 ❌ (don't send traffic)
```

### Types of Health Checks

| Check | Purpose | When It Fails |
|-------|---------|---------------|
| **Liveness** | "Is the process alive?" | Restart the container |
| **Readiness** | "Can it handle requests?" | Stop sending traffic |
| **Startup** | "Has it finished starting?" | Wait before checking liveness |

### Implementation

```python
# Liveness: Is the process running?
@app.get("/health/live")
async def liveness():
    return {"status": "alive"}

# Readiness: Can we handle requests?
@app.get("/health/ready")
async def readiness():
    checks = {}
    
    # Check database
    try:
        await db.execute("SELECT 1")
        checks["database"] = "ok"
    except:
        checks["database"] = "failed"
    
    # Check Redis
    try:
        await redis.ping()
        checks["redis"] = "ok"
    except:
        checks["redis"] = "failed"
    
    # Overall status
    all_ok = all(v == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503
    
    return JSONResponse(
        {"status": "ready" if all_ok else "not_ready", "checks": checks},
        status_code=status_code
    )
```

### Kubernetes Configuration

```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
```

---

## Error Handling

### The Problem

```python
# Bad: Exposes internal details
@app.get("/users/{id}")
async def get_user(id: int):
    try:
        return await db.get_user(id)
    except Exception as e:
        raise HTTPException(500, detail=str(e))
        # Returns: "Connection refused to postgres://admin:secret@db:5432"
        # Attacker now knows: database type, credentials, internal hostname
```

### The Solution

```python
# Good: Log details, return generic message
@app.get("/users/{id}")
async def get_user(id: int):
    try:
        return await db.get_user(id)
    except Exception as e:
        logger.error(
            "user_fetch_failed",
            user_id=id,
            error=str(e),
            traceback=traceback.format_exc()
        )
        raise HTTPException(500, detail="Unable to fetch user")
```

### Global Exception Handler

```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    correlation_id = request.state.correlation_id
    
    # Log full details internally
    logger.error(
        "unhandled_exception",
        correlation_id=correlation_id,
        path=request.url.path,
        method=request.method,
        error=str(exc),
        traceback=traceback.format_exc()
    )
    
    # Return safe message to client
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "correlation_id": correlation_id,
            "message": f"An error occurred. Reference: {correlation_id}"
        }
    )
```

User sees:
```json
{"error": "Internal server error", "correlation_id": "abc-123", "message": "An error occurred. Reference: abc-123"}
```

Your logs show:
```json
{
    "event": "unhandled_exception",
    "correlation_id": "abc-123",
    "path": "/api/users/1",
    "error": "Connection refused",
    "traceback": "Traceback (most recent call last):\n  File..."
}
```

---

## Error Tracking System

Beyond logging errors to stdout, TruckPitStop includes a **persistent error tracking system** that stores errors in the database for historical analysis and resolution tracking.

### Why Persistent Error Tracking?

Logs are great, but they have limitations:
- **Lost on restart** (unless using log aggregation)
- **Hard to search** without specialized tools
- **No resolution tracking** - who fixed it? when?
- **No visibility** for non-technical admins

Our error tracking system solves these problems:

```
┌─────────────────────────────────────────────────────────────┐
│                    Error Occurs                              │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
         ┌─────────────────┴─────────────────┐
         │                                   │
         ▼                                   ▼
┌─────────────────┐               ┌─────────────────┐
│  Log to stdout  │               │  Save to DB     │
│  (structlog)    │               │  (ErrorLog)     │
└─────────────────┘               └─────────────────┘
         │                                   │
         ▼                                   ▼
┌─────────────────┐               ┌─────────────────┐
│  Loki/Grafana   │               │  Admin Dashboard│
│  (optional)     │               │  (built-in)     │
└─────────────────┘               └─────────────────┘
```

### Error Categories

Errors are classified into categories for easier filtering:

| Category | Examples | When It's Used |
|----------|----------|----------------|
| `payment` | Card declined, Stripe API error | Payment processing failures |
| `auth` | Invalid credentials, token expired | Authentication/authorization |
| `validation` | Invalid input, missing fields | Request validation errors |
| `database` | Connection lost, query timeout | Database operations |
| `external_api` | Stripe timeout, third-party failure | External service calls |
| `unhandled` | Unexpected exceptions | Anything not caught elsewhere |

### Severity Levels

| Severity | When to Use | Action Required |
|----------|-------------|-----------------|
| `warning` | Handled gracefully, but notable | Monitor trends |
| `error` | Something failed, needs attention | Investigate soon |
| `critical` | System at risk, immediate action | Wake someone up! |

### What Gets Stored

Each error record includes:

```json
{
    "id": "uuid",
    "correlation_id": "abc-123",
    "created_at": "2026-02-08T14:32:05Z",
    
    "error_type": "StripeCardError",
    "error_category": "payment",
    "severity": "error",
    
    "endpoint": "/api/v1/payments/confirm",
    "method": "POST",
    "status_code": 400,
    
    "user_id": "uuid (if authenticated)",
    "tenant_id": "uuid (if applicable)",
    
    "message": "Your card was declined",
    "stack_trace": "Traceback...",
    "request_context": {
        "invoice_id": "...",
        "amount": 150.00
    },
    
    "resolved": false,
    "resolved_at": null,
    "resolved_by_id": null,
    "notes": null
}
```

### Using the Error Dashboard

Access the error dashboard at **Platform Analytics → Errors** (Super Admin only).

**Features:**
- **Stats cards**: Total errors, unresolved count, critical count
- **Category breakdown**: Click to filter by category
- **Search**: Find by message, error type, or correlation ID
- **Filters**: Category, severity, status, date range
- **Detail view**: Full stack trace, request context
- **Resolution tracking**: Mark as resolved with notes

### Payment Error Handling

Payment errors get special treatment because they directly impact revenue:

```python
# Stripe errors are caught and categorized
try:
    payment_intent = stripe.PaymentIntent.create(...)
except stripe.error.CardError as e:
    # User-friendly message returned
    # Full details logged to database
    # Metrics incremented
```

**Stripe Webhooks** also log payment failures:
- `payment_intent.payment_failed` - Card declined, insufficient funds
- `charge.failed` - Charge processing failed
- `charge.dispute.created` - **CRITICAL** - Chargeback initiated

### Finding Related Errors

Use the **correlation ID** to find all errors from the same request:

```
User reports: "Payment failed with reference abc-123"

1. Search for correlation_id: abc-123
2. See all errors from that request
3. Find: ValidationError → StripeCardError → HTTPException
4. Root cause: Card expired
```

### Resolving Errors

When you fix an issue:

1. Click the error in the dashboard
2. Click "Mark Resolved"
3. Add notes explaining the fix
4. Error moves to "Resolved" status

**Why track resolution?**
- Know which errors are addressed
- Track who fixed what
- Build institutional knowledge
- Identify recurring issues

### Best Practices

1. **Check errors daily** - Don't let them pile up
2. **Resolve with notes** - Future you will thank you
3. **Watch for patterns** - Same error 100 times = systemic issue
4. **Critical = immediate** - Set up alerts for critical errors
5. **Use correlation IDs** - Link user reports to actual errors

---

## Common Tools

### Logging

| Tool | Description | Self-Hosted |
|------|-------------|-------------|
| **structlog** | Structured logging for Python | N/A (library) |
| **Loki** | Log aggregation (like Prometheus for logs) | ✅ |
| **ELK Stack** | Elasticsearch + Logstash + Kibana | ✅ |
| **Fluentd** | Log collector/forwarder | ✅ |

### Metrics

| Tool | Description | Self-Hosted |
|------|-------------|-------------|
| **Prometheus** | Metrics collection and storage | ✅ |
| **Grafana** | Dashboards and visualization | ✅ |
| **AlertManager** | Alert routing and notifications | ✅ |
| **VictoriaMetrics** | Prometheus-compatible, better performance | ✅ |

### Tracing

| Tool | Description | Self-Hosted |
|------|-------------|-------------|
| **Jaeger** | Distributed tracing | ✅ |
| **Zipkin** | Distributed tracing | ✅ |
| **OpenTelemetry** | Vendor-neutral observability standard | ✅ |

### All-in-One

| Tool | Description | Self-Hosted |
|------|-------------|-------------|
| **Grafana Stack** | Loki + Prometheus + Tempo + Grafana | ✅ |
| **SigNoz** | Open-source APM | ✅ |

---

## Glossary

| Term | Definition |
|------|------------|
| **APM** | Application Performance Monitoring - tracks app health |
| **Cardinality** | Number of unique label combinations in metrics |
| **Chargeback** | Customer disputes a charge with their bank (bad for merchants) |
| **Correlation ID** | Unique identifier linking related log entries |
| **Dashboard** | Visual display of metrics and logs |
| **Error Category** | Classification of error type (payment, auth, database, etc.) |
| **Error Severity** | How urgent an error is (warning, error, critical) |
| **Histogram** | Metric type showing distribution of values |
| **Instrumentation** | Adding observability code to your application |
| **Label** | Key-value pair attached to metrics (e.g., `method="GET"`) |
| **Latency** | Time taken to complete a request |
| **Log Aggregation** | Collecting logs from multiple sources into one place |
| **Metric** | Numeric measurement of system behavior |
| **P99/P95/P50** | Percentile latencies (99% of requests faster than X) |
| **Prometheus** | Popular open-source metrics system |
| **Rate** | Requests per second |
| **Resolution Tracking** | Recording when/how errors were fixed |
| **Retention** | How long data is kept before deletion |
| **Sampling** | Recording only a percentage of traces |
| **Scraping** | Prometheus pulling metrics from your app |
| **SLA/SLO/SLI** | Service Level Agreement/Objective/Indicator |
| **Span** | Single operation within a trace |
| **Stack Trace** | Full error path showing where code failed |
| **Structured Logging** | Logs in machine-readable format (JSON) |
| **Throughput** | Number of requests handled per time unit |
| **Trace** | Complete journey of a request through the system |
| **Webhook** | HTTP callback triggered by external events (e.g., Stripe) |

---

## Quick Reference

### What to Monitor

| Category | Metrics | Logs | Error Dashboard |
|----------|---------|------|-----------------|
| **Availability** | Uptime %, health check status | Startup/shutdown events | - |
| **Performance** | Latency P50/P95/P99, throughput | Slow query warnings | - |
| **Errors** | Error rate, error count by type | Error details with stack traces | Full history, resolution tracking |
| **Saturation** | CPU %, memory %, connection pool | Resource exhaustion warnings | - |
| **Security** | Failed login rate, blocked IPs | Auth failures, suspicious activity | Auth errors with user context |
| **Payments** | Payment success/failure rate | Stripe API errors | Payment failures, disputes |

### Log Levels Cheat Sheet

```
DEBUG   → "I'm checking the password hash now"
INFO    → "User logged in successfully"
WARNING → "This is the 5th failed login attempt"
ERROR   → "Database query failed, retrying..."
CRITICAL→ "Cannot connect to database, shutting down"
```

### Error Severity Cheat Sheet

```
WARNING  → Handled gracefully, monitor trends
ERROR    → Something failed, investigate soon
CRITICAL → System at risk, immediate action required
```

### Metric Naming Convention

```
# Format: namespace_subsystem_name_unit
truckpitstop_http_requests_total
truckpitstop_http_request_duration_seconds
truckpitstop_db_connections_active
truckpitstop_auth_login_attempts_total
truckpitstop_errors_total
truckpitstop_payment_errors_total
```

### Error Dashboard Filters

| Filter | Values | Use Case |
|--------|--------|----------|
| Category | payment, auth, validation, database, external_api, unhandled | Focus on specific area |
| Severity | warning, error, critical | Prioritize urgent issues |
| Resolved | true, false | Find open issues |
| Date range | Start/end dates | Investigate incidents |
| Search | Free text | Find by message or correlation ID |

---

## Further Reading

- [Google SRE Book - Monitoring](https://sre.google/sre-book/monitoring-distributed-systems/)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/naming/)
- [The Three Pillars of Observability](https://www.oreilly.com/library/view/distributed-systems-observability/9781492033431/)
- [structlog Documentation](https://www.structlog.org/)

---

## Questions?

Observability can be overwhelming. Start simple:

1. **Week 1**: Add structured logging
2. **Week 2**: Add correlation IDs
3. **Week 3**: Add basic metrics
4. **Week 4**: Set up dashboards

You don't need everything at once. Each piece adds value independently.
