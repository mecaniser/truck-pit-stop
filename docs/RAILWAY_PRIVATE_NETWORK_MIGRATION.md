# Railway Private Network Migration

## Purpose

Move the API, worker, PostgreSQL, and Redis into one Railway project and
environment so application traffic uses Railway private hostnames instead of
public TCP proxies. This reduces connection setup and tail latency, especially
for the database-heavy dashboard, fleet board, and repair-order workspace.

## Current Constraint

Private networking is scoped to a Railway project/environment. The API and
worker currently run separately from the PostgreSQL and Redis services, so
changing a URL alone cannot make those connections private.

## Recommended Target

1. Create PostgreSQL and Redis services in the project/environment that hosts
   the API and worker.
2. Restore production PostgreSQL data into the new PostgreSQL service.
3. Use the new services' Railway private connection variables for `DATABASE_URL`
   and `REDIS_URL` on both API and worker.
4. Keep the public-service variables recorded for rollback until the new path
   has been stable through a business day.

Moving the API and worker into the existing data project is also valid, but
increases the chance of missing app-service variables and deployment settings.
Co-locating data services with the existing app services is the lower-risk path.

## Preflight

1. Schedule a maintenance window and name an operator and rollback owner.
2. Record the current public `DATABASE_URL` and `REDIS_URL` in Railway's secret
   store; do not put connection strings in this repository or ticket text.
3. Capture a verified PostgreSQL backup with `pg_dump` and restore it into a
   disposable database before the production cutover.
4. Inventory Redis usage. Cache-only keys can be allowed to expire. If Redis is
   used for sessions, rate-limit state, or queues, plan the short interruption
   and restart API/worker together after cutover.
5. Rehearse the procedure in a staging environment with a copy of the schema.
6. Confirm `alembic heads` has exactly one result before deploying. The startup
   command intentionally runs `alembic upgrade head`, so a multiple-head graph
   blocks the service before it can serve traffic.

## Cutover

1. Put the application into maintenance mode or pause write-heavy work.
2. Take the final PostgreSQL dump and restore it to the new Railway PostgreSQL
   service.
3. Validate table counts for the critical tables: tenants, users, customers,
   vehicles, repair orders, invoices, payments, and inventory.
4. Set API and worker `DATABASE_URL` and `REDIS_URL` to the private variables
   supplied by the new Railway services. Apply the same environment values to
   every replica.
5. Deploy the worker first and confirm it completes startup and migration
   preflight. Deploy the API next.
6. Run a smoke test: sign in, load dashboard action queue, open a repair order,
   create a draft, add a part, complete a test workflow, and confirm a worker
   task and WebSocket notification.
7. Watch Grafana for 30 minutes: API P95, database query P95, error rate,
   request rate, and database connection errors. Keep the alert channel open.

## Rollback

1. Restore the prior public `DATABASE_URL` and `REDIS_URL` variables on API and
   worker.
2. Redeploy worker, then API.
3. Confirm the previous app services are healthy and verify the same smoke test.
4. Preserve the new database for investigation; do not delete it until data
   ownership and write timing have been reconciled.

## Success Criteria

- API and worker start without migration-preflight failures.
- Private service hostnames resolve only inside Railway.
- No increase in 4xx/5xx rate after cutover.
- Database query P95 and API P95 improve under comparable production traffic.
- Dashboard, fleet board, and repair-order workspace no longer show repeated
  multi-second database waits attributable to the public network path.
