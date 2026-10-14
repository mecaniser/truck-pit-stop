# DB119 backend implementation evidence

2026-10-14, `codex/external-service-history`, implementation checkout
`/Users/sergio_m1_promax/.codex/worktrees/ets-checkpoint-merge/truck-pit-stop`.
Backend & Integrations owns implementation; this receipt is not an independent
QA or Security approval. No commits, merge or deployment performed by this owner.

## Delivered contract

Implemented [approved contract](../contracts/db119-external-service-history.md):
private tenant/vehicle-scoped list/create/full correction/void/restore/history;
owner/admin/receptionist only; explicit source and informational USD cost;
immutable event snapshots and actor attribution; same-request retries return
current data; stale writes and reused keys reject; active vehicle first lock
serializes saves with merge. Voided records remain recoverable. No native
billing, work, timer, mileage or PM side effect.

Two additive tables, migration169 after168. Composite tenant+vehicle and
tenant+record FKs, scoped request/revision uniqueness and check constraints.
Vehicle merge moves active and voided rows while preserving original vehicle
ID, versions and event snapshots. Summary adds `external_service_count` and
`moved.external_services`. Existing vehicle/customer/order/fleet/invoice/quote
payloads do not embed these private records. Routes explicitly send no-store.

Application files:

- `backend/app/db/models/external_service.py`, model registration;
- `backend/app/schemas/external_service.py`, additive merge-summary field;
- `backend/app/services/external_service.py`, vehicle merge integration;
- `backend/app/api/v1/endpoints/external_services.py`, router registration;
- `backend/alembic/versions/169_external_service_history.py`.

No contract deviation. PUT requires the optional business fields explicitly
(with null allowed) to avoid partial-update ambiguity. Server formats Decimal
cost with two fractional digits. Date uses Tenant.timezone, not UTC date.
Receipt upload and fleet/customer-portal exposure remain explicit follow-up.

## Runtime boundary

Read mandatory local-runtime skill in this session. Rechecked delivery branch
and HEAD `a7b279d082c0f2a8b102ade3b7fc8063c698518c`, frontend listener47264 on5174,
and API container bind mount from the intentionally separate approved preview
checkout `ets-parity-preview`. Parent performed initial source equality/readiness
and signed-in UI proof, recorded in the main DB119 receipt. This backend owner
did not restart servers, copy secrets, modify feature flags, migrate the populated
preview database, or touch production. Parent explicitly owns mirroring and the
preview migration after isolated schema verification. Implementation test results
below are not a claim that production or browser acceptance is complete.

## Automated evidence

Interpreter: existing repository Python3.11 virtual environment. From `backend/`:

```sh
python -m pytest tests/test_external_service.py tests/test_vehicle_merge.py tests/test_vehicle_identity_relationships.py -q --tb=short
```

**55 passed**,12.12seconds. Log `/tmp/db119-backend-focused.log`.

Proof includes field bounds/precision/strict dates and odometer; every role;
tenant, wrong-truck and archived boundaries; full lifecycle and all exact-replay
actions after later writes; changed content/actor/action/target collisions;
stale and lifecycle guards; pagination and unknown-versus-zero cost; native
financial/mileage/PM invariants; active/voided vehicle merge; actual customer
relink and customer merge without lost history; retained attribution/snapshots;
real ASGI401/403/422/409/201/200 and no-store headers; existing customer,
vehicle, order, quote, invoice and fleet serializers exclude private marker and
record ID; injected audit-write failures roll back create and correction; shop
timezone boundary when UTC and local dates differ.

Initial test-only corrections: router inventory must skip WebSocketRoute;
cache assertion accepts stronger `no-store, private` middleware value; fleet
serializer fixture needs a real active FleetMembership. All are corrected and
included in final passing run; no production defect was hidden by those fixes.

PostgreSQL evidence uses existing restricted `/tmp/db110-postgres-test-url`,
read in-process and never printed. Fixture and launch guard allow only
localhost/127.0.0.1 and `db110_test*`; actual database was
`db110_test_operation_execution`. No preview or production database connection.

```sh
python -m alembic upgrade head
python -m pytest tests/test_external_service_postgres.py -q --tb=short
```

**168→169 upgrade succeeded. Nine PostgreSQL tests passed**,13.76seconds.
Logs `/tmp/db119-migration.log`, `/tmp/db119-postgres-tests.log`.
`alembic heads` reports only `169_external_service_history (head)`.

Actual two-session contention proves one record/event for duplicate create;
one winner for simultaneous corrections or correction/void; cross-vehicle key
collision rolls back the losing root insert, leaves transaction usable, and
returns generic409; create and correction versus vehicle merge in both lock
orders either move the committed record or reject the archived target.
Real migration-installed checks, request/revision uniqueness and composite FKs
are exercised, including a different **existing** tenant (not merely a missing
tenant). Tests insert synthetic unique tenant fixtures and clean only those
fixtures. Both tables remain installed in the isolated test database.

Changed-source compileall and `git diff --check` passed. Only existing SQLAlchemy/
Pydantic deprecations and existing fixture metadata dependency-cycle warnings
appeared. The full protected CI suite remains the integration gate.

## Handoff and rollback

Parent owns final browser desktop/phone/landscape journeys, preview migration,
independent QA/Security, protected PR/merge, exact deployment/migration readiness,
and production synthetic acceptance. Do not mark Done from this receipt alone.

Rollback application code if privacy, duplicate/lost data, or primary workspace
behavior fails. Leave additive tables and recorded audit intact; do not downgrade
and drop tables after user writes. No native financial backfill exists to undo.
