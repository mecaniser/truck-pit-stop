# API Security Summary

**Last Updated:** 2026-02-11
**Scope:** HTTP API security controls for `/api/v1` (GraphQL/gRPC intentionally deferred)

## Control Matrix

| Control | Status | Implementation | Notes |
|---|---|---|---|
| JWT auth + role authorization | Implemented | `backend/app/core/dependencies.py`, endpoint role guards | Existing baseline retained |
| Shared rate-limit primitive | Implemented | `backend/app/core/rate_limit.py` | Uses `user_id` key first, IP fallback |
| Endpoint strict rate limits | Implemented | `auth.py`, `quotes.py` decorators | Existing stricter limits retained |
| HTTP throttling | Implemented | `backend/app/middleware/throttling.py` | Sliding window: soft delay + hard 429 |
| Request timeout | Implemented | `backend/app/middleware/timeout.py` | API timeout returns 504 JSON |
| API cache policy | Implemented | `backend/app/middleware/cache_control.py` | `no-store, private` on `/api/v1` |
| Idempotency | Implemented | `backend/app/middleware/idempotency.py` | Optional `Idempotency-Key` for POST |
| Pagination hardening | Implemented | `backend/app/core/pagination.py` + endpoint updates | Opt-in `paginated=true` envelope |
| Webhook ingress exception for idempotency | Implemented | `idempotency.py` path exclusion | `/api/v1/webhooks/*` excluded |
| API gateway integration | Planned (docs-only) | This document | Deferred infra implementation |
| GraphQL surface | Deferred | N/A | Explicitly out of scope |
| gRPC surface | Deferred | N/A | Explicitly out of scope |

## Operational Defaults

| Setting | Value |
|---|---|
| Default limiter baseline | `120/minute` per resolved key |
| Throttling window | `60s` |
| Throttling soft band | `61-100 req/min` |
| Throttling delay | `100-500ms` linear |
| Throttling hard cap | `>100 req/min -> 429` + `Retry-After: 60` |
| Request timeout | `30s` |
| Idempotency key length | `16-128` chars |
| Idempotency lock TTL | `30s` |
| Idempotency response TTL | `24h` |
| Idempotency in-flight duplicate wait | `~3s` (30 polls x 100ms), then `409` |
| Max cached idempotency response body | `1MB` raw body (larger responses are not cached) |
| API cache headers | `Cache-Control: no-store, private`, `Pragma: no-cache`, `Expires: 0` |

## Idempotency Behavior

### Request
- Header: `Idempotency-Key` (optional)
- Scope: `POST /api/v1/**` except `/api/v1/webhooks/**`

### Outcomes
- Missing key: request behaves normally.
- Valid key, first request: processed normally and response cached.
- Same key + same payload/fingerprint: cached response replayed.
- Same key + different payload/fingerprint: `409` conflict.
- Duplicate in-flight with same key: waits up to ~3s for the first request result, then returns `409` in-progress.
- Large successful/error responses above the idempotency cache-size cap are returned normally but not stored for replay.

### Replay Signal
- Header `X-Idempotency-Replayed: true|false` is set on keyed requests.

## Pagination Contract (Opt-in)

- Query flag: `paginated=true`
- Envelope:

```json
{
  "items": [...],
  "total": 123,
  "skip": 0,
  "limit": 100,
  "has_more": true
}
```

- Default behavior (`paginated=false` or omitted): legacy list response is preserved.

## Incident and Debug Guidance

### Headers to Inspect
- `X-Correlation-ID`: trace request path through logs and error records.
- `X-Idempotency-Replayed`: detect replayed writes.
- `Retry-After`: provided on throttling/rate-limit denials.

### Common Security Events
- `request_timeout` (timeout middleware)
- `request_throttled` (throttling middleware)
- `idempotency_stored` / `idempotency_replay` / `idempotency_conflict` (idempotency middleware)

### Recommended Triage Workflow
1. Find request by `X-Correlation-ID` in logs and error dashboard.
2. Check whether the call was replayed (`X-Idempotency-Replayed`).
3. Confirm whether denial was throttle (`429`) or timeout (`504`).
4. Validate caller identity key resolution (user key vs IP fallback).

## API Gateway Rollout Plan (Docs-Only)

### Candidate Platforms
- Cloudflare (managed edge security + WAF)
- Kong (API-focused policy engine)
- Traefik (Kubernetes-friendly edge routing)
- Nginx/Envoy (self-managed reverse proxy)

### Required Gateway Capabilities
- IP reputation and bot filtering
- WAF managed rules
- Edge rate limiting and burst controls
- TLS policy enforcement (modern ciphers, HSTS alignment)
- Request body/size limits and header normalization
- Structured access logs with correlation ID passthrough

### Phased Adoption
1. **Shadow Mode:** mirror logs/metrics only; no blocking.
2. **Protect Mode:** enable non-breaking protections (size limits, basic bot mitigations).
3. **Enforce Mode:** enable WAF/rate policies with rollback playbook.
4. **Optimize:** tune limits per endpoint class and tenant profile.

### Acceptance Checks
- No increased auth failure false positives.
- P95/P99 latency impact within target budget.
- Correlation IDs preserved end-to-end.
- No webhook delivery regressions.
