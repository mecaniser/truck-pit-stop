# Diesel Bridge Load Tests

These k6 scenarios exercise the hot **read-only** staff flows that appear in
production telemetry:

- Dashboard action queue
- Repair-order list
- Fleet Board
- One explicitly selected repair-order detail and Price Builder workspace

The scripts never create, edit, price, approve, invoice, or delete data.
They authenticate with a bearer token supplied at runtime. Do not commit a
token, customer credential, or a real repair-order identifier.

## Prerequisites

Create a dedicated active staff user in a seeded load-test tenant. Obtain a
short-lived access token for that user and pass it as `K6_ACCESS_TOKEN`.
Choose a stable non-sensitive order from the same tenant and pass its UUID as
`REPAIR_ORDER_ID` when workspace coverage is wanted.

Run k6 directly, or use the official Docker image. From the repository root:

```bash
docker run --rm -i \
  -e BASE_URL=http://host.docker.internal:8000 \
  -e TARGET_ENV=local \
  -e K6_ACCESS_TOKEN="$K6_ACCESS_TOKEN" \
  -e REPAIR_ORDER_ID="$REPAIR_ORDER_ID" \
  -v "$PWD/performance/k6:/scripts" \
  grafana/k6:latest run /scripts/scenarios/read_only_canary.js
```

For a non-local deployment, replace `BASE_URL`. The token must have access to
the selected order. `host.docker.internal` is for Docker Desktop local runs.

## Production Canary

The canary has a deliberately small default: two iterations per minute for five
minutes. Each iteration reads the dashboard, repair-order list, Fleet Board,
and optional workspace. It is the only profile that can target production.

```bash
docker run --rm -i \
  -e BASE_URL=https://www.dieselbridge.com \
  -e TARGET_ENV=production \
  -e ALLOW_PRODUCTION=true \
  -e K6_ACCESS_TOKEN="$K6_ACCESS_TOKEN" \
  -e REPAIR_ORDER_ID="$REPAIR_ORDER_ID" \
  -v "$PWD/performance/k6:/scripts" \
  grafana/k6:latest run /scripts/scenarios/read_only_canary.js
```

The explicit production flag prevents an accidental live run. Keep the default
rate until the canary is clean. k6 aborts when its error threshold is crossed.

## Staging Ramp

Run the staged ramp only against a production-like staging tenant with seeded
data. It refuses `TARGET_ENV=production`.

```bash
docker run --rm -i \
  -e BASE_URL=https://staging.example.com \
  -e TARGET_ENV=staging \
  -e K6_ACCESS_TOKEN="$K6_ACCESS_TOKEN" \
  -e REPAIR_ORDER_ID="$REPAIR_ORDER_ID" \
  -v "$PWD/performance/k6:/scripts" \
  grafana/k6:latest run /scripts/scenarios/staging_ramp.js
```

The default ramp is 2, then 5, 10, and 20 arrivals per minute. Change the
stages only after the lower level is stable. Review the k6 endpoint-specific
P95/P99 and failure thresholds together with Grafana's API latency, database
query P95, Redis latency, CPU, memory, and connection-pool metrics.

## Success Criteria

- Error rate remains below 1% and checks remain above 99%.
- Dashboard and repair-order list P95 stay below 1.2–1.5 seconds.
- Repair-order workspace P95 stays below 1.5–2.0 seconds.
- P99 stays below twice the P95 budget; stop and investigate otherwise.
- The matching Grafana interval shows no database pool exhaustion, 5xx spike,
  sustained database query regression, or Redis regression.

The scripts label each request with a stable route name. Those labels make the
k6 summary useful even when the selected order UUID changes between runs.
