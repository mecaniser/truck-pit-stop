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
| DB-030 | P1 | Review | Restore mobile customer-portal touch targets | Frontend & UX | `codex/portal-touch-targets` gives the four reported controls literal 44px mobile dimensions while retaining the 34/36px desktop treatment. Portal/route tests 16/16, full frontend 145/145, production build, exact changed-scope lint, diff check, and the expanded compact-font DB-004 Playwright journey 2/2 passed at 390/320 with full-surface target sweeps and no overflow/browser errors. | Fresh independent QA verifies the focused diff and repeats the committed 390/320 runtime gate; no merge or release before QA GO |

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
| DB-028 — Rich homepage repair-order proof | PR #251 merged as `c65af774`; all six required and informational CI contexts passed. Independent QA and Impeccable finish re-reviews returned GO with no P0–P2 findings after target-size, financial arithmetic, first-viewport, glass-edge, motion, responsive-contract, and active-card geometry remediations. Railway production deployment `3c80c935-df22-4796-aa7e-a53cd0b6278c` and performance deployment `a9bda4f1-5677-49f7-a7f7-ab589dda81bd` succeeded on the merge SHA while worker deployment `2066ffd9-8d61-4326-8c1b-e03833cd99e3` remained unchanged. Production acceptance passed the desktop/mobile Playwright journey 2/2 across 1440/1366/1280/1120/960/390/320, ten consecutive homepage probes returned HTTP 200, API health was alive, and the live approved-shop feed returned HTTP 200 with two records. No real PII, testimonial, performance, pricing, API, data, auth, tenant, or migration change. |
| DB-029 — Interactive homepage product tour | PR #253 merged as `f9f4f12ddb94fd745bd0310eb4a8361b40ed3e2b`; all six protected CI contexts passed: Migration graph, Frontend checks, Frontend full suite, Backend tests, Backend full suite, and Playwright smoke. Independently tested application SHA `ac18a2adf8a6b083c6f2d7eef389efe9a0b512a4` passed focused 27/27, full frontend 143/143, production build, changed-file ESLint/diff, dedicated Playwright 3/3, functional QA, and Impeccable/Emil review with no P0–P2 findings. Railway production deployment `97733b7e-127a-4e39-87ad-b337bef34b81` and performance deployment `cd9eba54-9954-4f44-882e-e708c3bb7711` succeeded on the merge SHA and passed `/health`; worker deployment `2066ffd9-8d61-4326-8c1b-e03833cd99e3` remained unchanged before and after release. Production acceptance passed DB-029 Playwright 3/3 twice across desktop/mobile and seven widths, including five source-grounded surfaces, Repair Orders and Invoices event routes, keyboard and rapid retargeting, disclosures, no overflow or undersized controls, reduced modes, and clean console/page/network capture. Ten initial homepage probes and 11 observation rounds over 10 minutes returned HTTP 200 with no 502/5xx; production and performance health stayed 200, and the live approved-shop feed returned HTTP 200 with two records. Rollback target was `74cb317a2578c8f1a064c583588418902483ddd5`; no rollback trigger fired. No API, auth, tenant, payment, backend, dependency, worker, data, or migration change. |
| DB-004 — Customer portal mobile closure | PR #255 merged as `b2ceba0bd9c298fc1ff4a3df525f1f8b105a7069`; all six protected CI contexts passed: Migration graph, Frontend checks, Frontend full suite, Backend tests, Backend full suite, and Playwright smoke. Implementation `552f5942f5ef0c8d2fa09bb37fe5ee778a18da4a` received fresh independent QA GO with no findings: portal/title/route tests 16/16, full frontend 145/145, production build, changed-file lint, diff check, and committed mobile Playwright 2/2 passed at 390px and 320px with exact viewport containment, every visible target at least 44×44, correct route-aware titles, working dashboard → active repair/detail → history/paid-detail navigation, and no page/console errors. Railway production deployment `17c333e0-b311-4b2a-a24c-f92dd51e0d1b` and performance deployment `6815f0a9-d2e4-4280-bffa-6e968d5baeb1` succeeded on the merge SHA and passed `/health`; worker deployment `2066ffd9-8d61-4326-8c1b-e03833cd99e3` remained unchanged. Production acceptance used the deployed frontend with a non-mutating authenticated safe fixture and passed Playwright 2/2 twice at 390px and 320px. Five initial portal probes and 11 observation rounds returned HTTP 200; production and performance health stayed 200, and Railway showed no 5xx entries during the release window. Rollback target was `6f7f7e6317bca3409d768158903faad96ce95aca`; no rollback trigger fired. Real auth/tenant runtime remained green from the independent QA gate. No backend, API, auth, tenant, payment, dependency, worker, data, or migration change. |
| DB-027 — Shop-first public homepage | PR #249 merged as `c31d91de`; every required and informational CI job passed. Independent QA and Impeccable finish review returned GO with no P0–P2 findings. Railway production deployment `c919050e-d583-4a48-b39c-1070354a4838` and performance deployment `fb386e4c-c6bd-483d-83dd-dfdf4d6d730a` succeeded on the merge SHA while worker deployment `2066ffd9-8d61-4326-8c1b-e03833cd99e3` remained unchanged. Production acceptance passed the 320/390 Playwright journey, ten consecutive homepage probes, API health, and the live approved-shop feed with HTTP 200. No API, data, auth, tenant, or migration change. |
| DB-002 — Paid repair-order conversion export | PR #246, production SHA `2ff3910b`; all six CI contexts green; final Security and QA GO; migration 117 applied on PostgreSQL; API and worker deployments succeeded; worker registered and executed `process_paid_invoice_webhooks` every 10 seconds with zero pending events and registered daily PII retention. Versioned keyring parity and safe batch/lease/time budgets are configured. No tenant receiver was enabled or sent data during release; the first tenant enablement must use its approved receiver and acceptance canary |

## Intake template

Copy this row into Inbox before implementation:

```markdown
| DB-### | User/business outcome | Product & Delivery Lead | Priority | Acceptance criteria needed | Unassigned technical owner |
```

For every active item, add links or identifiers for its branch/PR and record the
last passing automated and runtime evidence in the item or associated issue.

## DB-004 acceptance criteria

- Authenticated customer portal dashboard, active repair, repair detail, estimate
  action, history list, and paid history detail render without clipping or hidden
  horizontal overflow at both 390px and 320px.
- The portal brand/home link, repair-detail back control, every history filter,
  and every other visible interactive target measure at least 44 by 44 CSS pixels
  at both required mobile widths.
- Portal routes expose an accurate customer-portal document title and never retain
  the staff-login title after authentication or client-side navigation.
- Customer login, active-repair/action-required state, detail/history navigation,
  keyboard focus and activation, unauthenticated denial, other-customer denial,
  and cross-tenant customer/order denial remain green.
- Focused portal tests, production build, changed-file lint/diff, and a real
  390/320 browser journey pass with no console, page, or failed-request errors.
  Independent QA must return GO before the focused PR can merge and release.

## DB-030 acceptance criteria

- At 390px and 320px, dashboard `Select & pay` and `Pay`, invoice-detail
  `Download PDF`, and `Review payment options` each measure at least 44 by 44
  CSS pixels; committed Playwright scrolls the full dashboard and invoice detail
  and measures every named control.
- Literal CSS pixel minimums remain effective under the compact portal root font,
  while desktop layout, visible labels, keyboard/focus behavior, payment behavior,
  authorization boundaries, and API/data contracts remain unchanged.
- Neither viewport has horizontal page overflow. Focused and full frontend tests,
  production build, exact/changed-file lint and diff checks, DB-004 mobile
  regressions, and independent QA must pass before merge or release.

## DB-029 acceptance criteria

- Remove the visible “Illustrative sample” and “Fictional repair-order data”
  disclaimer. Keep the example internally safe without adding visible legalistic
  copy, customer claims, testimonials, performance claims, or real PII.
- The curated rail order, labels, and Lucide icons are exactly Repair Orders /
  `ClipboardList`, Customers / `Users`, Shop Work / `Wrench`, Invoices /
  `FileText`, and Vehicle History / `History`. These are keyboard-operable tabs;
  selection replaces the entire miniature and is exposed semantically.
- Each miniature is faithful to its current product source rather than an
  invented generic dashboard: Repair Orders uses the repair-order workspace,
  invoice, work/labor, total, and history anatomy; Customers uses the real list,
  detail, Overview, and History patterns; Shop Work uses Shop Cockpit, Work Queue,
  Queue/Activity, and its three lanes; Invoices uses the embedded invoice-card
  states; Vehicle History uses vehicle details and Repair History rows.
- There is no global Intake/Estimate/Approval/Invoice/Payment stage rail and no
  module-by-stage Cartesian state. Each miniature exposes only authentic local
  controls: repair-order history/invoice/work evidence, customer Overview/History,
  Shop Work Queue/Activity and order cards, invoice selection/expansion, and
  vehicle-history row selection/expansion. Per-module local state is preserved.
- Fixtures are typed, deeply frozen, locally imported, internally reconciled,
  and use masked/safe values. Preview interaction performs no network request,
  auth/tenant read, WebSocket, storage write, or mutation and never mounts the
  authenticated production pages or their data hooks.
- The module route begins at the selected rail control and terminates at the
  context sheet. An event route appears only for an authentic selected row, card,
  disclosure, or history event and terminates at its evidence sheet. Routes and
  nodes never cross text, controls, or card interiors. Geometry comes from live
  rendered anchors, inflates obstacles by at least 8px, remeasures after resize,
  fonts, expansion, or content change, and suppresses any invalid route.
- The authored focal motion is the selected event travelling through its route
  into a capability-based morphing evidence sheet. Module-screen morph, glass
  depth, pointer-down feedback, focus, and CTA material motion stay subordinate,
  interruptible, and latest-selection-safe; there is no ambient loop or repeated
  generic rise. The CTA uses layered DieselBridge copper/orange material rather
  than a flat generic orange rectangle.
- Context and optional event sheets use functional Apple-style glass with clear
  edge, depth, translucency, hierarchy, and restrained specular response. If a
  module has no authentic secondary selection, the event sheet collapses rather
  than inventing evidence.
- Desktop keeps the product and its external evidence legible as one composition.
  At widths below 1200px routes are absent and evidence stacks in semantic order.
  At 390/320 the rail becomes a wrapping grid and authentic tables become compact
  rows/cards. The page has no horizontal overflow at 1440, 1366, 1280, 1120, 960,
  390, or 320 CSS pixels; visible interactive targets are at least 44px.
- Keyboard operation, focus visibility, reduced motion, reduced transparency,
  contrast, coarse-pointer behavior, 200% zoom, rapid retargeting, empty/optional
  data, late fonts, missing observers, and rotation/resize are verified without
  stale selection, focus, sheet, or route state.
- Dynamic replacement uses one visually hidden `role="status"` live region with
  polite, atomic announcements. A module change announces the selected module and
  screen; an authentic local selection announces its module, selected control or
  record, and evidence title. Initial render, focus-only movement, resize, and
  geometry/motion changes do not announce. A cancelable 120ms trailing update,
  guarded by the latest transition epoch, ensures rapid input announces only the
  final committed state with no stale or repeated intermediate message.
- Scope is frontend presentation only. No API, auth, tenant, payment, backend
  data, WebSocket, worker, route, or migration change is part of this outcome.
- Focused unit tests, full frontend tests, production build, lint/diff checks,
  source-fidelity and fixture invariants, responsive Playwright geometry and
  interaction coverage, independent QA, and an independent Impeccable/Emil
  finish review must pass before release.
- Release evidence must record the focused PR/merge SHA, required CI contexts,
  both Railway web deployment IDs and health gates, changed homepage canary, and
  proof that the worker deployment remained unchanged.

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
