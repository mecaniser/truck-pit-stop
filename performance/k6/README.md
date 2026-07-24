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

## Isolated Performance Environment

For capacity work, use a separate Railway environment with fresh PostgreSQL and
Redis services. Set the backend `ENVIRONMENT` variable to `performance`. Never
point this setup at the production database or production URL.

The repository provides a synthetic data generator for that environment. It
creates one large tenant with 151 customers, 270 vehicles (120 fleet trucks),
2,500 repair orders, 600 inventory items, and a detailed workspace order by
default. It exits unless its environment and confirmation phrase are explicit.

From the Railway backend shell, after migrations complete:

```bash
ENVIRONMENT=performance \
LOAD_TEST_SEED_CONFIRM=seed-performance-data \
python scripts/seed_performance_environment.py \
  --owner-email performance-owner@dieselbridge.com \
  --owner-password 'use-a-unique-secret'
```

Provision ten active garage-admin accounts for the capacity profile. These
accounts are only for the isolated environment, and each virtual user signs in
once as a different account so the test respects production-like per-user
throttling.

```bash
LOAD_TEST_SEED_CONFIRM=seed-performance-data \
python scripts/provision_performance_load_users.py \
  --password 'use-a-different-unique-load-test-secret'
```

Record the printed `workspace_repair_order_id`, then run the capacity profile
only against the isolated environment URL:

```bash
BASE_URL="https://YOUR-PERFORMANCE-URL" \
TARGET_ENV=performance \
K6_LOAD_TEST_PASSWORD='use-a-different-unique-load-test-secret' \
REPAIR_ORDER_ID="WORKSPACE_REPAIR_ORDER_ID" \
k6 run scenarios/performance_capacity.js
```

The profile ramps from 1 to 2, 5, and 10 concurrent virtual staff users. It
rejects production by design. Watch Grafana for API latency, database P95,
connection-pool waits, Redis latency, CPU, memory, and error rate throughout.

## Success Criteria

- Error rate remains below 1% and checks remain above 99%.
- Dashboard and repair-order list P95 stay below 1.2–1.5 seconds.
- Repair-order workspace P95 stays below 1.5–2.0 seconds.
- P99 stays below twice the P95 budget; stop and investigate otherwise.
- The matching Grafana interval shows no database pool exhaustion, 5xx spike,
  sustained database query regression, or Redis regression.

The scripts label each request with a stable route name. Any non-2xx response
is printed with its endpoint and HTTP status, so rate limits and server errors
are visible immediately in terminal output.
