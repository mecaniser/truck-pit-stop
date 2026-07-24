# Performance Environment Runbook

This environment is for synthetic capacity testing only. It must never share a
database, Redis instance, domain, customer records, payment configuration, or
provider credentials with production.

## Create The Railway Environment

1. In the Diesel Bridge Railway project, create an environment named
   `performance` from the current `main` deployment configuration.
2. Add a new PostgreSQL service and a new Redis service to that environment.
   Do not reference production service variables.
3. Deploy the backend from `main` and set these backend variables:

   ```text
   ENVIRONMENT=performance
   DATABASE_URL=<the new PostgreSQL private connection variable>
   REDIS_URL=<the new Redis private connection variable>
   SECRET_KEY=<a new unique secret, at least 32 characters>
   FRONTEND_URL=<the performance frontend URL>
   PUBLIC_API_BASE_URL=<the performance backend URL>
   CORS_ORIGINS_STR=<the performance frontend URL>
   ```

   Keep payment, email, SMS, Cloudinary, and external provider credentials
   empty or pointed at their own non-production sandboxes.

4. Deploy a frontend service for the same environment with its API base URL set
   to the performance backend URL. Keep it behind an unguessable Railway URL;
   do not add the production custom domain.
5. Confirm the backend deployment completes its migrations and schema preflight.

## Seed Synthetic Data

Open the backend service shell in the `performance` environment and run:

```bash
LOAD_TEST_SEED_CONFIRM=seed-performance-data \
python scripts/seed_performance_environment.py \
  --owner-email performance-owner@dieselbridge.com \
  --owner-password 'use-a-unique-secret'
```

The command creates the following default profile:

| Data | Count |
| --- | ---: |
| External customers | 150 |
| Internal fleet trucks | 120 |
| Total vehicles | 270 |
| Repair orders | 2,500 |
| Inventory items | 600 |
| Workspace lines | 12 parts, 6 labor |

The command prints the generated workspace repair-order UUID. It is idempotent
for the tenant slug: a second run exits without adding duplicate data.

## Run Capacity Test

Provision the ten dedicated load-test admins. Each k6 virtual user logs in once
as a separate account, so the load test does not accidentally exercise a
single-user rate limit instead of multi-user application capacity.

```bash
LOAD_TEST_SEED_CONFIRM=seed-performance-data \
python scripts/provision_performance_load_users.py \
  --password 'use-a-different-unique-load-test-secret'
```

Then run this from the repository's `performance/k6` directory:

```bash
BASE_URL="https://YOUR-PERFORMANCE-BACKEND-URL" \
TARGET_ENV=performance \
K6_LOAD_TEST_PASSWORD='use-a-different-unique-load-test-secret' \
REPAIR_ORDER_ID="WORKSPACE_REPAIR_ORDER_ID" \
k6 run scenarios/performance_capacity.js
```

This workload ramps through 2, 5, and 10 concurrent virtual staff users. It is
blocked by code from targeting production. Stop the test if error rate reaches
1%, API P95 crosses the route threshold, database query P95 rises materially,
or the service shows pool exhaustion, CPU saturation, or memory pressure.

## Tear Down

Delete the entire `performance` Railway environment, including its PostgreSQL
and Redis services, when the capacity investigation is complete. No synthetic
data should persist in production.
