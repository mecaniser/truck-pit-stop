# DB-036 OAuth offline acceptance

Date: 2026-09-29. Accountable owner: Backend & Integrations.
Branch: `codex/db036-motive-sandbox`, draft PR443.
Implementers: root (UI/integration delivery) and motive_backend (backend).
Architecture: motive_contract. Independent reviewers: motive_security, motive_qa.

## Candidate scope

Company-scoped Motive OAuth connect/callback, versioned encrypted tokens,
refresh and local disconnect; reviewed truck mapping; bounded Vehicle Gateway
current-location discovery, sample ordering, freshness and retention; default-off
five-minute worker; staff Fleet → profile menu → Integrations UI. Callback secrets
are removed before auth bootstrap, excluded from analytics/caching/error echoes,
and not automatically retried or persisted in browser storage.

This is latest current-location/speed collection. No live provider connection,
odometer, engine-hours, fault-code or HOS collection is claimed. Existing fixture
history remains independent; canonical truck fields are unchanged.

## Automated evidence

- Backend: **101 passed**, no PostgreSQL skips in the combined parser, fixture
  persistence, OAuth, old sandbox PostgreSQL and new OAuth PostgreSQL suites.
  QA independently reproduced 101/101.
- Real PostgreSQL cases use separate sessions: one-use callback exchange,
  disconnect racing callback, refresh locking/concurrent disconnect and tenant
  FK enforcement, plus earlier sandbox receipt concurrency/constraints.
- Frontend: **29 passed** across Motive integration17, Fleet return2,
  callback capture2, auth refresh7 and cancellation1. Independent QA reproduced
  the same set excluding cancellation (28/28).
- Changed/new frontend lint, TypeScript and production build pass. Existing
  React Router future notices and stale Browserslist notice are nonblocking.
- New backend source, tests and migration Ruff plus diff integrity pass.

## Migration

Disposable PostgreSQL15 container `db036-oauth-pg-20260929`, loopback port54183,
synthetic `db036_test` database; no shared application database was touched.
Full empty-database chain reaches152. Final migration152 downgrade151/re-upgrade
passes; SQL readback confirms `152_motive_oauth` and `mapped_by_user_id` column.
Final migration SHA256:
`babf8a5199c7a697050dc84444d47a375901a86da1291cb258039b2c4c51cafe`.
Disposable container is removed after checks; do not reuse this ephemeral DSN.

## Independent gates

Initial Security NO-GO returned Origin/CSRF, post-provider session revalidation,
token scope/keyring, cross-company mapping, idempotency and error-echo issues to
implementation. All were corrected and retested. QA returned actual UI/API
status/denial/internal-fleet/cooldown mismatches, Retry-After and worker starvation;
these were corrected with focused regressions.

Final Security **GO, offline scope**. Final service SHA256:
`32c68d552226778d6976f502d0e06cf3f249b83f838f01be4c663fcbb118bb57`.
Final QA **GO, offline implementation**, with browser/pilot limitations below.
No implementing agent approved its own independent gate.

## Runtime evidence and limits

Mandatory runtime preflight found intended clean cc8bfefb worktree and no5173/8000
listeners. Approved `backend/.env` was absent; no secrets were copied or invented.
Pinned frontend dependencies installed. Normal authenticated application runtime
remains **blocked**, not aligned or browser-verified.

An isolated development fixture was served from this worktree at
`http://127.0.0.1:5173/tests/motive-preview.html` by PID11413 (Vite); cwd and actual
fixture HTML200 confirmed. Every fixture HTTP call is handled by an in-memory
adapter; synthetic identity uses nonpersistent storage and no provider/backend.
QA visually verified setup-pending/disabled Connect at desktop and390×844 with no
clipping. Browser click/keyboard input failed in the automation tool despite
accessible snapshots, so full browser connect/map/sync/disconnect is **unverified**.
Automated component/ASGI interactions cover those paths; fixture visuals are not
live or authenticated end-to-end proof. Preview process stopped after checks.

## Outstanding release gates

- Motive reply/developer approval; real client credentials and exact callback.
- Full authenticated browser journey once local configuration/input is available.
- Two-truck provider/device/permissions/unit validation and consent.
- Explicit production rollout, approved tenant allowlist, Web/Worker/Beat identity,
  post-release observation and rollback evidence.
- Customer-portal self-service requires explicit company administrator grants;
  current shop owner/admin roles can manage the fleet-company connections.

No merge, deployment, live data collection or Done status is claimed. See
`docs/DB-036_MOTIVE_SETUP.md` for activation and rollback guidance.
