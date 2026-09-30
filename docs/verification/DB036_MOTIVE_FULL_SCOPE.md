# DB-036 complete integration verification

2026-09-30. Candidate: working changes on `codex/db036-motive-sandbox`, following
`d41f33d6`, draft PR443. Accountable owner: Backend & Integrations.

## Application and delivery state

The product owner confirmed submission of the general Motive partner application
for Elis Tech LLC / DieselBridge Network. Submission is not approval. No live
provider credentials, consent, webhook subscription, merge or deployment are
claimed. The full implementation target is recorded in
`docs/DB-036_MOTIVE_FULL_CONTRACT.md`.

## Implemented surfaces under verification

- Explicit company administrator grants and customer portal connection/mapping.
- Full read scopes, real vehicle and gateway discovery, current location/speed,
  bounded reading history, distinct calibrated/virtual odometer and engine hours,
  fault lifecycle, per-stage cursors and ongoing reconciliation.
- Public raw-body HMAC-SHA1 signed webhook ingress with durable receipt, opaque
  generation-specific routes, secret rotation and background API reconciliation.
- Tenant/company/membership enforcement, encrypted credentials/secrets, one-time
  secret response outside generic idempotency and frontend mutation caches.
- Disconnect/rotation invalidation and thirty-day telemetry/receipt retention.

## Verification evidence

- Root access/HTTP tests: six passed, covering explicit grants, selected tenant
  differing from global identity home tenant, revocation of pending OAuth,
  unlinked/inactive users, real zero vs missing/virtual readings, expired
  memberships, raw body limit, durable DB failure response and configured URL.
- Final isolated PostgreSQL15: full empty migration chain to153, downgrade153
  to152 and re-upgrade153 passed. All six model column sets match the migrated
  database, including the final fixed reconciliation cutoff.
- Backend owner final suite: **140 passed, no skips**, with real disposable
  PostgreSQL enabled. Includes fixed-cutoff catch-up for seven trucks, normalized
  equivalent timestamps, webhook concurrency and rotated-credential durability.
  New backend source/tests Ruff checks passed. Motive tests now run in the critical
  CI regression job; PostgreSQL-specific tests require its opt-in disposable DSN.
- Frontend: **39 focused tests passed**. Final TypeScript, targeted ESLint and
  production build pass. Browser fixture exercised setup, VIN
  mapping, sync/readings/faults, grant/revoke, one-time webhook setup/hide and
  confirmed disconnect. Desktop/mobile390×844 checked without horizontal clipping;
  browser console had zero errors (two existing router warnings). Screenshots:
  `/tmp/db036-fullscope-ui-20260930/desktop.png` and `mobile.png`. The temporary
  browser and exact owned Vite process were stopped; port5173 is unbound.
- Independent QA/security found and returned recovery issues to backend: resumed
  history windows exceeded the client bound; moving full-fleet completion cutoff
  prevented larger fleets completing. Backend added regressions and corrections,
  plus UTC timestamp normalization and token-rotation preservation after actor
  revocation. Independent reviewer reran all140 backend cases without skips and
  independently reproduced customer grant revocation:403 with rotated credentials
  durable after request rollback. Equivalent timestamp duplicates are accepted.

## Runtime and external gates

Runtime preflight selected the correct worktree; normal app startup is blocked
by missing approved backend environment configuration and dirty-checkout switch
protection. Shared app containers/databases were untouched. Disposable synthetic
PostgreSQL is used for migrations/tests. Synthetic browser evidence does not
establish authenticated backend integration or provider connectivity.

Required activation evidence: approved app credentials and exact callback/scopes,
per-company webhook subscription provisioning, real consenting-fleet/device
payload checks, authenticated runtime acceptance, independent gates and approved
release. Backup retention/deletion and provider-side revocation procedures must
be confirmed operationally before production activation.

## Independent gate

Offline QA **GO** and application-security **GO**, with no remaining blocking
finding in the reviewed candidate. See `DB036_MOTIVE_FULL_INDEPENDENT_QA.md`
for reviewer digest, independent tests and reproduced fixes. Reviewer independently
executed37 frontend cases; frontend owner executed39 including additional cases.
These gates do not approve live activation or production release.
