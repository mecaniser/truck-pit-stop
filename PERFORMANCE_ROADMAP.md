# Multi-tenant performance program

This program changes the application from request-time aggregation to bounded,
screen-specific reads. The objective is reliable interactive latency as tenant
data grows; it is not to make one demo database look fast.

## Service objectives

| Interaction | p95 API target | p95 screen-ready target | Data boundary |
| --- | ---: | ---: | --- |
| Customer and repair-order lists | 250 ms | 750 ms | 50 rows per page |
| Customer and repair-order workspace summary | 300 ms | 900 ms | summary plus active tab |
| Fleet board | 400 ms | 1,000 ms | tenant fleet only |
| Truck history, invoices, photos | 350 ms | 900 ms | independently paginated tab |
| Write acknowledgement | 300 ms | 700 ms | synchronous database transaction only |

The targets are measured at p95 against a representative tenant with at least
500 customers, 2,500 vehicles, 25,000 repair orders, 20,000 invoices, and
20,000 payments. External providers, PDF generation, email, and messaging are
not part of a write acknowledgement path.

## Execution sequence

1. Establish baselines and observability.
   - Request logs and Prometheus record route latency, response size, SQL count,
     cumulative SQL time, and slowest SQL operation.
   - Capture production p50/p95/p99 for the customer list, repair-order list,
     customer workspace, repair-order workspace, fleet board, truck detail, and
     invoices before each phase changes them.
   - Add a repeatable seeded-load profile and CI performance budgets before
     expanding tenant onboarding.

2. Replace aggregate-on-read list endpoints with projections.
   - `customer_read_models` is the first projection. PostgreSQL maintains it in
     the same transaction as changes to customers, vehicles, repair orders,
     invoices, and payments.
   - Add equivalent projections for repair-order list rows, invoice list rows,
     and fleet-board cards. Keep one compact row per screen entity, scoped by
     tenant and indexed by that screen's filters and sort keys.
   - Backfill projections in migrations and retain a temporary legacy fallback
     only to protect restored databases during rollout.

3. Define bounded API contracts by screen.
   - List endpoints return a fixed-size page and only the columns rendered in
     that list. Cursor pagination replaces deep offset pagination where history
     can grow without a practical upper bound.
   - Workspace endpoints return a summary first. Work orders, invoices, history,
     photos, parts, and inspections are separately paginated resources loaded
     when their tab becomes visible.
   - Every new endpoint gets a query-count, payload-size, and p95 latency budget
     in its test plan.

4. Make the browser cache an active read layer.
   - Use stable cache keys and useful stale windows for reference data and list
     rows. Preserve the prior page while a new page is loading.
   - Websocket events patch the affected row or detail cache directly. Full-list
     refetches are reserved for events that truly change membership or ordering.
   - Detail tabs fetch on first view, cancel stale requests on selection change,
     and do not prefetch unbounded history or media.

5. Capacity and database discipline.
   - Set pool size from deployed web-worker count and the database connection
     budget, not a fixed local default. Alert on pool checkout pressure, lock
     waits, statement timeouts, and database CPU/IO saturation.
   - Verify every tenant-scoped query begins with `tenant_id` or reaches it by a
     selective foreign key. Use `EXPLAIN (ANALYZE, BUFFERS)` on seeded data
     before accepting a new high-traffic query.
   - Run provider communication, PDF work, reporting, bulk imports, and
     projection rebuilds through workers/outbox jobs. API transactions should
     only validate, write, publish an event, and return.

6. Protect the result continuously.
   - Run a nightly load profile and a smaller pull-request performance suite.
   - Fail a change that exceeds an endpoint's query or payload budget without an
     explicit reviewed exception.
   - Review monthly p95/p99 trends by route and tenant size; add projections or
     indexes before customer growth turns a trend into an incident.

## Rollout safeguards

The customer projection migration backfills all existing customers before the
application begins reading it. Its PostgreSQL triggers make updates atomic with
their source writes, so a successful write cannot leave a stale customer list.
The endpoint falls back to the previous aggregate query only when a projection
row is absent, which protects manually restored databases while still making a
missing backfill visible in request telemetry.
