# DB-036 fixture persistence verification

Date: 2026-09-28, final local checks at 23:41 UTC.
Owner/implementer: Backend & Integrations, root agent.
Branch: `codex/db036-motive-sandbox`; draft PR #443.
Base: `origin/main` `88995fc2`.

## Implemented boundary

- Four tables for one disabled fixture account per tenant, reviewed historical
  powered-truck bindings, normalized samples and metadata-only delivery receipts.
- Composite foreign keys enforce account/binding/vehicle/sample tenant identity.
- Owner/admin management, account locks, time-interval matching, semantic
  duplicate/conflict detection, ordered latest-point reads and 30-day retention.
- Provider odometer stays virtual. Canonical mileage, driver and manual location
  are unchanged. No credential, raw webhook body, HTTP route, live client, worker
  registration or customer-facing telemetry is added.

## Evidence

- 49 focused tests pass with normal repository fixtures and the opt-in real
  PostgreSQL test fixture. Cases include role/tenant denial, disabled/deleted
  records, FK violations, duplicate concurrency, conflicts, exact reassignment
  cutover, late/equal/newer points, malformed signed input and retention/replay.
- Existing Fleet board and projection regression tests: 14 pass.
- Ruff passes for the new/changed integration source, tests and migration.
- `alembic heads` reports only `151_motive_sandbox`.
- Temporary PostgreSQL 15, synthetic database `db036_test`: complete migration
  history from an empty public schema through 151 passed. Downgrade 151 to 150
  and re-upgrade to 151 passed with SQL readback of `alembic_version`.
- Independent QA also ran the focused suite and reproduced stable equal-time
  selection with deliberately reversed random UUID order.

Reproduce focused tests from `backend` with the pinned development requirements:

```sh
uv run --python 3.11 --with-requirements requirements-dev.txt python -m pytest -q \
  tests/test_db036_motive_events.py tests/test_db036_motive_sandbox.py \
  tests/test_db036_motive_postgres.py
```

The PostgreSQL cases require `DB036_TEST_DATABASE_URL` to point to a disposable
loopback database named `db036_test`; otherwise they skip. Each case creates and
removes its own randomly named schema. The test container used for this run is
temporary and is removed after verification; no shared application database was
migrated or reseeded.

## Independent gates

Architecture agent `motive_contract` approved the bounded storage/service contract.
Independent `motive_security` and `motive_qa` did not implement or direct the work.

- Security initially returned P2 NO-GO for signed integer/time overflow and
  database-unrepresentable identifiers escaping normal invalid-event handling.
  Owner fixed the boundaries and added regressions. Independent recheck: GO,
  no unresolved security findings in this slice.
- QA initially returned P2 NO-GO for random UUID tie-breaking at identical
  provider and receipt timestamps. Owner added a durable account-scoped sequence
  and exact reproduction test. Independent recheck: GO, 49/49 tests pass.

## Runtime and remaining work

Local process preflight: this worktree is based on the intended main commit;
ports 5173/8000 are unbound. Controller dry run reports missing approved
`backend/.env` and installed Vite. These URLs are blocked, not browser-verified.
The isolated test runtime has all pinned backend dependencies and needs no real
provider secret. Browser acceptance does not apply to this service-only slice;
it remains mandatory when the endpoint/UI is wired.

Remaining DB-036 work: secure company connection, real payload/device validation,
collection endpoint and worker/reconciliation with scheduled purge, Fleet API/UI,
live two-truck pilot, deployment approval and release evidence. User confirmed
the two pilot trucks have Motive devices and share one Motive company; company
administrator/API access remains to be established.
