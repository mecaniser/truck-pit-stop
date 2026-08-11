# DieselBridge Delivery Board

Last consolidated: 2026-08-10. This board was reconstructed from DieselBridge
task histories, the repository, recent commits, known PRs, and the current dirty
working tree. Reconcile it whenever newer GitHub or deployment evidence exists.

## Operating rules

- One item has one accountable owner, even when several roles contribute.
- `Done` requires merge/release and acceptance evidence; “implemented in a task”
  is not sufficient.
- Preserve the current uncommitted backend/payment/conversion work until its
  owner separates and verifies it.
- New requests enter Inbox through Product & Delivery Lead.

## In progress

| ID | Outcome | Owner | Evidence now | Next gate |
|---|---|---|---|---|
| DB-HC001 | House Cleanup: finish and release all intentional in-progress work, preserve or explicitly defer everything else, and return the project to a clean trusted baseline | Product & Delivery Lead; release owner: Release & Reliability | Repository has a dirty mixed backend/integration/tooling tree and multiple historical branches/PRs requiring authoritative reconciliation | Read-only team audit → scoped completion/fixes → Architecture/Security/QA GO → focused commit/PR/CI → merge/deploy/canary → clean worktree |
| DB-002 | Ship the supported paid repair-order conversion export | Backend & Integrations | Migration/UI landed earlier in #209; backend API/model/service/task/payment integration remains local. Audit: 28 focused/adjacent tests pass and Alembic has one head, but SSRF, tenant/key/admin, correction validation, worker runtime, secret operations, Postgres migration, and browser acceptance gates are incomplete | Reconstruct on current `main`; close Architecture/Security/test/runtime gaps; focused PR/CI; Railway deploy and canary |
| DB-003 | Finish versioned additional-work authorizations | Backend & Integrations | PR #196 merged at `e20fa1a` with implementation commit `a51f2af`; immutable revisions/finalization guard exist, but task validation found the portal action still depends on the staff-send flow | Architecture decides automatic vs staff-reviewed publication and any threshold policy; then run mechanic addition → customer prompt → approve/decline → invoice Playwright acceptance, Security GO, QA GO |
| DB-004 | Reconcile customer portal redesign and active-repair workflow | Frontend & UX | PRs #189 and #194 are merged and included in current production | Run and record one mobile customer portal acceptance journey; then move to Done |
| DB-009 | Make Playwright the regression safety net | QA Gatekeeper | Existing Playwright runtime retained; package commands added; 5/5 staff-login/public-invoice smoke tests passed locally on 2026-08-10 | Add repair order, estimate authorization, payment, customer portal, driver custody, and tenant-isolation journeys; then add a stable CI gate |

## Blocked

| ID | Outcome | Owner | Blocker | Unblock evidence |
|---|---|---|---|---|
| DB-006 | Prove driver portal custody-only equipment isolation | QA Gatekeeper | Requires an authenticated WorkOS driver session for the exact linked driver; prior manager/invitation checks passed but driver isolation remained NO-GO | Positive current-custody view plus denial of released, unrelated, fleet-wide, and cross-tenant equipment |
| DB-007 | Enable Google Business Profile review integration | Backend & Integrations | Google Basic API Access case `1-9174000041216` remained in progress with quota 0 in the latest task evidence | Vendor approval and non-zero quota, then location-selection and tenant-isolation acceptance |
| DB-008 | Complete QuickBooks production readiness | Product & Delivery Lead | External Intuit questionnaire/production approval and test-account steps are not conclusively closed in task evidence | Approved credentials, documented environment setup, sandbox-to-production acceptance |

## Ready / backlog

| ID | Outcome | Owner | Acceptance target |
|---|---|---|---|
| DB-010 | Add Sentry error monitoring | Release & Reliability | Backend/frontend SDKs configured without secrets in git; releases/environment tags; source maps; alert ownership; verified test event and privacy filtering |
| DB-011 | Connect the board to Linear | Product & Delivery Lead | Connected workspace/team, statuses matching this board, ownership/priority/acceptance fields, and import without duplicate issues |
| DB-012 | Promote trustworthy CI checks to required | Release & Reliability | Full backend/frontend baselines green; Playwright smoke stable; migration graph, backend, frontend, and acceptance gates protected on `main` |
| DB-013 | Create an isolated staging environment | Release & Reliability | Production-like configuration with isolated data; migrations, acceptance suite, rollback rehearsal, and promotion record |
| DB-014 | Fix local seed idempotency | Backend & Integrations | Seed works with existing multi-tenant data without `MultipleResultsFound`, does not duplicate records, and supports a clean first run |
| DB-015 | Remediate WebSocket token logging | Security & Identity | No bearer/session token appears in client, API, proxy, or observability logs; regression coverage proves redaction |
| DB-016 | Add repair-order concurrency and audit hardening | Architecture & API Contracts | `lock_version` conflict behavior, before/after audit for financial/workflow changes, user-visible history, and simultaneous-edit tests |
| DB-017 | Verify canonical work-first repair workflow end to end | QA Gatekeeper | Execute `FLOW_VERIFICATION.md`, including internal fleet, payment methods, void/revise, worker/outbox email, and immutable invoice behavior |
| DB-018 | Restore a trustworthy green full-suite baseline | Release & Reliability | Current GitHub required gates pass, but informational CI reports frontend 2 failed/115 passed and backend 32 failed/536 passed/3 skipped | Classify and repair every failure, then make full suites required |
| DB-019 | Protect `main` with enforced delivery gates | Release & Reliability | GitHub currently has no branch protection or ruleset | After stable checks exist, require PRs, migration/backend/frontend/Playwright gates, resolved conversations, and block force push/deletion |
| DB-020 | Fix production apex-domain availability | Release & Reliability | `www.dieselbridge.com` and API return 200; bare `dieselbridge.com` timed out during 2026-08-10 release audit | Verify DNS/TLS/redirect ownership and make apex reliably redirect or serve without affecting `www` |

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
| Core delivery team operating model | Seven role tasks pinned; `AGENTS.md`, delivery charter, board, and validated `dieselbridge-delivery-team` skill created |
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
