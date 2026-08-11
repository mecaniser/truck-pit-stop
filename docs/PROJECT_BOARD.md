# DieselBridge Delivery Board

Last consolidated: 2026-08-11. This board was reconstructed from DieselBridge
task histories, the repository, GitHub, CI, and Railway production evidence.
House Cleanup is complete. The former dirty tree remains recoverably preserved
on `codex/house-cleanup-preservation`; its intentional outcomes have been rebuilt,
reviewed, merged, and released. Reconcile this board whenever newer evidence exists.

## Operating rules

- One item has one accountable owner, even when several roles contribute.
- `Done` requires merge/release and acceptance evidence; “implemented in a task”
  is not sufficient.
- Keep `codex/house-cleanup-preservation` as recovery evidence until the product
  owner deliberately archives it; it is not an active implementation branch.
- New requests enter Inbox through Product & Delivery Lead.

## In progress

| ID | Priority | State | Outcome | Owner | Evidence now | Next gate |
|---|---|---|---|---|---|---|
| DB-003 | P1 | Discovery | Finish versioned additional-work authorizations | Backend & Integrations | PR #196 merged at `e20fa1a` with implementation commit `a51f2af`; immutable revisions/finalization guard exist, but task validation found the portal action still depends on the staff-send flow | Architecture decides automatic vs staff-reviewed publication and any threshold policy; then run mechanic addition → customer prompt → approve/decline → invoice Playwright acceptance, Security GO, QA GO |
| DB-004 | P1 | QA/Security | Reconcile customer portal redesign and active-repair workflow | Frontend & UX | PRs #189 and #194 are merged and included in current production | Run and record one mobile customer portal acceptance journey; then move to Done |

## Blocked

| ID | Priority | State | Outcome | Owner | Blocker | Resolver / next safe action | Unblock evidence |
|---|---|---|---|---|---|---|---|
| DB-006 | P0 | Blocked | Prove driver portal custody-only equipment isolation | QA Gatekeeper | Requires an authenticated WorkOS driver session for the exact linked driver; prior manager/invitation checks passed but driver isolation remained NO-GO | Product owner completes exact linked-driver MFA; QA then runs read-only isolation checks | Positive current-custody view plus denial of released, unrelated, fleet-wide, and cross-tenant equipment |
| DB-007 | P1 | Blocked | Enable Google Business Profile review integration | Backend & Integrations | Google Basic API Access case `1-9174000041216` remained in progress with quota 0 in the latest task evidence | Google approves the existing case; Backend rechecks quota without resubmitting | Vendor approval and non-zero quota, then location-selection and tenant-isolation acceptance |
| DB-008 | P1 | Blocked | Complete QuickBooks production readiness | Product & Delivery Lead | External Intuit questionnaire/production approval and test-account steps are not conclusively closed in task evidence | Product owner/Intuit completes approval or credential step; Backend performs sandbox-to-production verification | Approved credentials, documented environment setup, sandbox-to-production acceptance |

## Ready / backlog

| ID | Priority | State | Outcome | Owner | Acceptance target |
|---|---|---|---|---|---|
| DB-010 | P1 | Ready | Add Sentry error monitoring | Release & Reliability | Backend/frontend SDKs configured without secrets in git; releases/environment tags; source maps; alert ownership; verified test event and privacy filtering |
| DB-011 | P2 | Ready | Connect the board to Linear | Product & Delivery Lead | Connected workspace/team, statuses matching this board, ownership/priority/acceptance fields, and import without duplicate issues |
| DB-013 | P1 | Ready | Create an isolated staging environment | Release & Reliability | Production-like configuration with isolated data; migrations, acceptance suite, rollback rehearsal, and promotion record |
| DB-014 | P1 | Ready | Fix local seed idempotency | Backend & Integrations | Seed works with existing multi-tenant data without `MultipleResultsFound`, does not duplicate records, and supports a clean first run |
| DB-015 | P0 | Ready | Remediate WebSocket token logging | Security & Identity | No bearer/session token appears in client, API, proxy, or observability logs; regression coverage proves redaction |
| DB-016 | P1 | Ready | Add repair-order concurrency and audit hardening | Architecture & API Contracts | `lock_version` conflict behavior, before/after audit for financial/workflow changes, user-visible history, and simultaneous-edit tests |
| DB-017 | P0 | Ready | Verify canonical work-first repair workflow end to end | QA Gatekeeper | Execute `FLOW_VERIFICATION.md`, including internal fleet, payment methods, void/revise, worker/outbox email, and immutable invoice behavior |
| DB-020 | P1 | Ready | Fix production apex-domain availability | Release & Reliability | Verify DNS/TLS/redirect ownership and make apex reliably redirect or serve without affecting `www` |
| DB-022 | P0 | Ready | Expand Playwright from smoke coverage into the product regression safety net | QA Gatekeeper | Add repair order, estimate authorization, payment, customer portal, driver custody, and cross-tenant denial journeys; require them in CI only after stable repeated runs |
| DB-023 | P1 | Ready | Restore a clean repository-wide frontend lint baseline | Frontend & UX | Resolve the recorded 175 errors and 27 warnings without behavior regressions, then make repository-wide lint blocking |
| DB-024 | P0 | Ready | Remediate frontend dependency risk | Security & Identity | Triage the recorded npm audit baseline (1 low, 5 moderate, 26 high, 4 critical), upgrade safely, produce SBOM/audit evidence, and keep build plus browser journeys green |
| DB-025 | P1 | Ready | Add infrastructure-level outbound webhook egress defense | Release & Reliability | Route conversion webhooks through an egress control that denies loopback, private, link-local, metadata, and ULA destinations; Railway currently provides outbound networking/static IP features but no configured per-service private-address deny. Keep the application DNS pinning and URL controls as the primary guard until then |
| DB-026 | P1 | Ready | Run the Celery worker as a non-root user | Release & Reliability | Container starts under a dedicated unprivileged UID, worker/beat tasks remain healthy, filesystem permissions are explicit, and the Celery root warning disappears |

## Completed with evidence to retain

These outcomes retain their implementation, review, CI, and release evidence.
Rows that lack an explicit production record remain implementation evidence only.

| Outcome | Evidence |
|---|---|
| Mobile repair-order scrolling and finalized-photo behavior | PR #195, commit `222ba23`, focused mobile/runtime checks reported |
| Mobile platform performance layout | PR #161, commit `7789b0e`, 320px no-overflow/build evidence reported |
| Customer portal visual redesign | PR #189, commit `d9daf91`, build and portal/logo tests reported |
| Customer portal active repairs/action-required restoration | PR #194, commit `37e5e9a`, build and targeted tests reported |
| Local Docker database alignment | Commit `12dbbe1`, `truckpitstop` database configuration |
| WorkOS identity and authorization rollout | PRs #225–#240 are merged and retained in production SHA `2ff3910b`; authorization regression coverage passed the repaired full-suite and every later required release gate; no duplicate stale-branch reship is required |
| Fleet performance optimization | PR #193 is merged and included in current production; no PR retry is required |
| DB-HC001 — House Cleanup and delivery-team governance | PR #241; all intentional dirty paths classified; source work preserved without deleting local backups/tooling; focused follow-up releases #242–#246; final clean workspace branch created from current `main` |
| DB-018 — Green full-suite baseline | PRs #242 and #243; frontend 117/117 and backend 568/568 passed before later DB-002 expansion; the final DB-002 CI run also passed every required and informational check |
| DB-009 — Playwright CI smoke foundation | PR #244; PostgreSQL and Redis-backed CI starts the real services and passes 5/5 staff-login/public-invoice smoke tests; broader product journeys are DB-022 |
| DB-012 / DB-019 — Protected delivery workflow | `main` requires strict migration, frontend, backend, full-suite, and Playwright contexts; administrators are included; force push/deletion are blocked; linear history and resolved conversations are required |
| DB-021 — Railway health-gated cutover | PR #245; production API deployment `ac540450-8f13-4fa6-b7ba-6461e75b9526` and performance deployment `c83d792f-68d5-4d5e-9660-8d0357bea7a4` passed `/health` with a 300-second gate at `2ff3910b`; repeated probes had no connection-refused/5xx responses |
| DB-002 — Paid repair-order conversion export | PR #246, production SHA `2ff3910b`; all six CI contexts green; final Security and QA GO; migration 117 applied on PostgreSQL; API and worker deployments succeeded; worker registered and executed `process_paid_invoice_webhooks` every 10 seconds with zero pending events and registered daily PII retention. Versioned keyring parity and safe batch/lease/time budgets are configured. No tenant receiver was enabled or sent data during release; the first tenant enablement must use its approved receiver and acceptance canary |

## Intake template

Copy this row into Inbox before implementation:

```markdown
| DB-### | User/business outcome | Product & Delivery Lead | Priority | Acceptance criteria needed | Unassigned technical owner |
```

For every active item, add links or identifiers for its branch/PR and record the
last passing automated and runtime evidence in the item or associated issue.

## DB-HC001 acceptance criteria

- Every modified or untracked path is assigned to a coherent outcome, identified
  as generated/local-only material, or explicitly deferred without deletion.
- Branch and PR state is reconciled against GitHub; merged work is not reshipped
  and unmerged intentional work is not lost.
- Migration history has one Alembic head and the application starts against the
  expected schema.
- Backend, frontend, Playwright, security, tenant-isolation, payment/integration,
  and build checks required by the actual diff pass with fresh evidence.
- Independent Architecture, Security, QA, and pre-landing review gates are GO.
- Intentional work is committed in reviewable scope, pushed through PR and CI,
  merged, deployed, and verified with health/canary evidence and rollback notes.
- The primary repository ends clean. Remaining future work exists only as named
  board items, not unexplained local changes or ambiguous feature chats.

## DB-021 acceptance criteria

- Both Railway web services using root `railway.json` (`diesel-bridge-network`
  and performance `truck-pit-stop`) wait for HTTP `200` from `/health` before a
  new deployment becomes active and receives production traffic.
- A new instance has up to 300 seconds to complete legitimate startup; failure
  to become healthy in that window fails the deployment instead of replacing
  the last healthy instance.
- Automated coverage fails if the API health-check path or timeout is removed or
  changed, and `railway.json` validates against Railway's published JSON schema.
- There is no application behavior, API/data contract, migration, frontend, or
  worker deployment change in this item. Regression enforcement stays outside
  `backend/**` so the worker watch pattern is not triggered.
- Release evidence records both web deployment IDs/SHAs, successful Railway
  health gates, API health, and absence of connection-refused responses during
  each cutover; the worker is not redeployed.
