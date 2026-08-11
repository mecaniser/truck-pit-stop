# DieselBridge Delivery Board

Last consolidated: 2026-08-10. This board was reconstructed from DieselBridge
task histories, the repository, recent commits, known PRs, and production state.
The former dirty tree is preserved on `codex/house-cleanup-preservation` and the
primary worktree is clean. Reconcile this board whenever newer evidence exists.

## Operating rules

- One item has one accountable owner, even when several roles contribute.
- `Done` requires merge/release and acceptance evidence; “implemented in a task”
  is not sufficient.
- Preserve backend/payment/conversion commit `2bdc53c` until its owner rebuilds
  and verifies that work on current `main`.
- New requests enter Inbox through Product & Delivery Lead.

## In progress

| ID | Priority | State | Outcome | Owner | Evidence now | Next gate |
|---|---|---|---|---|---|---|
| DB-HC001 | P0 | Review | House Cleanup: finish and release all intentional in-progress work, preserve or explicitly defer everything else, and return the project to a clean trusted baseline | Product & Delivery Lead; release owner: Release & Reliability | Read-only team audit complete; preservation commits `2bdc53c`, `444c92d`, and `d1040c8`; primary tree clean; governance is in independent review on `codex/house-cleanup` | Governance re-review → focused PR/CI/merge → DB-002 completion → QA tooling → production verification → clean baseline |
| DB-002 | P0 | In Progress | Ship the supported paid repair-order conversion export | Backend & Integrations | Migration/UI landed earlier in #209; backend preserved at `2bdc53c`. Audit: 28 focused/adjacent tests pass and Alembic has one head, but SSRF, tenant/key/admin, correction validation, worker runtime, secret operations, Postgres migration, and browser acceptance gates are incomplete | Reconstruct on current `main`; close Architecture/Security/test/runtime gaps; focused PR/CI; Railway deploy and canary |
| DB-003 | P1 | Discovery | Finish versioned additional-work authorizations | Backend & Integrations | PR #196 merged at `e20fa1a` with implementation commit `a51f2af`; immutable revisions/finalization guard exist, but task validation found the portal action still depends on the staff-send flow | Architecture decides automatic vs staff-reviewed publication and any threshold policy; then run mechanic addition → customer prompt → approve/decline → invoice Playwright acceptance, Security GO, QA GO |
| DB-004 | P1 | QA/Security | Reconcile customer portal redesign and active-repair workflow | Frontend & UX | PRs #189 and #194 are merged and included in current production | Run and record one mobile customer portal acceptance journey; then move to Done |
| DB-009 | P1 | In Progress | Make Playwright the regression safety net | QA Gatekeeper | Commands preserved at `d1040c8`; first independent gate returned NO-GO for missing Redis readiness, weak API evidence, floating Python test tools, and incomplete failure artifacts; `codex/playwright-ci` now addresses those findings for the existing 5 staff-login/public-invoice tests | Fresh independent Release & Reliability QA of the smoke gate; then add repair order, estimate authorization, payment, customer portal, driver custody, and tenant-isolation journeys before treating Playwright as the full regression gate |
| DB-021 | P0 | Review | Prevent Railway from routing production API traffic before Uvicorn is accepting requests | Release & Reliability | Deployment `f9a81d2` was marked successful and became the only active instance before Uvicorn listened, causing HTTP 502 connection refusals from approximately 03:17:09Z through 03:17:15Z; `codex/railway-healthcheck` adds the `/health` gate and 300-second timeout; focused regression 1 passed, Railway schema validation passed, full backend suite 569 passed/3 skipped | Independent review → focused PR/CI → deploy → verify Railway health-gated cutover and no connection-refused responses |

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
| DB-012 | P0 | Ready | Promote trustworthy CI checks to required | Release & Reliability | Full backend/frontend baselines green; Playwright smoke stable; migration graph, backend, frontend, and acceptance gates protected on `main` |
| DB-013 | P1 | Ready | Create an isolated staging environment | Release & Reliability | Production-like configuration with isolated data; migrations, acceptance suite, rollback rehearsal, and promotion record |
| DB-014 | P1 | Ready | Fix local seed idempotency | Backend & Integrations | Seed works with existing multi-tenant data without `MultipleResultsFound`, does not duplicate records, and supports a clean first run |
| DB-015 | P0 | Ready | Remediate WebSocket token logging | Security & Identity | No bearer/session token appears in client, API, proxy, or observability logs; regression coverage proves redaction |
| DB-016 | P1 | Ready | Add repair-order concurrency and audit hardening | Architecture & API Contracts | `lock_version` conflict behavior, before/after audit for financial/workflow changes, user-visible history, and simultaneous-edit tests |
| DB-017 | P0 | Ready | Verify canonical work-first repair workflow end to end | QA Gatekeeper | Execute `FLOW_VERIFICATION.md`, including internal fleet, payment methods, void/revise, worker/outbox email, and immutable invoice behavior |
| DB-018 | P0 | Ready | Restore a trustworthy green full-suite baseline | Release & Reliability | Current GitHub required gates pass, but informational CI reports frontend 2 failed/115 passed and backend 32 failed/536 passed/3 skipped; classify and repair every failure, then make full suites required |
| DB-019 | P0 | Ready | Protect `main` with enforced delivery gates | Release & Reliability | After stable checks exist, require PRs, migration/backend/frontend/Playwright gates, resolved conversations, and block force push/deletion |
| DB-020 | P1 | Ready | Fix production apex-domain availability | Release & Reliability | Verify DNS/TLS/redirect ownership and make apex reliably redirect or serve without affecting `www` |

## Completed with evidence to retain

These outcomes have strong implementation/PR evidence in task history but should
not be treated as proof of current production state without a release record.

| Outcome | Evidence |
|---|---|
| Mobile repair-order scrolling and finalized-photo behavior | PR #195, commit `222ba23`, focused mobile/runtime checks reported |
| Mobile platform performance layout | PR #161, commit `7789b0e`, 320px no-overflow/build evidence reported |
| Customer portal visual redesign | PR #189, commit `d9daf91`, build and portal/logo tests reported |
| Customer portal active repairs/action-required restoration | PR #194, commit `37e5e9a`, build and targeted tests reported |
| Local Docker database alignment | Commit `12dbbe1`, `truckpitstop` database configuration |
| WorkOS identity and authorization rollout | PRs #225–#240 are merged; production matches #240 at `04c4be79…`; API health 200. Final runtime/security acceptance remains recorded under DB-HC001 before archival |
| Fleet performance optimization | PR #193 is merged and included in current production; no PR retry is required |

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

- The Railway API service waits for HTTP `200` from `/health` before a new
  deployment becomes active and receives production traffic.
- A new instance has up to 300 seconds to complete legitimate startup; failure
  to become healthy in that window fails the deployment instead of replacing
  the last healthy instance.
- Automated coverage fails if the API health-check path or timeout is removed or
  changed, and `railway.json` validates against Railway's published JSON schema.
- There is no application behavior, API/data contract, migration, frontend, or
  worker deployment change in this item.
- Release evidence records the deployment ID/SHA, a successful Railway health
  gate, API health, and absence of connection-refused responses during cutover.
