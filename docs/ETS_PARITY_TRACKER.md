> **C3 accepted — 2026-10-30:** PR698 / `18255c03` is merged, exact Web/Worker deployed and production Day/Night desktop/mobile accepted. All 26,315 fixed source rows unchanged; no production C3 or financial QA writes. [Final receipt](verification/DB146_TRUCK_ISSUES.md). Progress **8/30**; **R3 next**. Earlier handoff entries below are historical. Importer held; Shop Work redesign separate.

> **C3 release — 2026-10-30:** PR698 merged18255c03 after all7 exact-head checks passed; automatic deployment/production acceptance pending. Progress7/30 until acceptance.

> **C3 CI correction — 2026-10-30:** Initial full frontend CI exposed two incomplete theme mocks. Test-only correction passes45 focused checks and fresh independent QA; new exact-head CI remains required. Progress7/30.

> **C3 review — 2026-10-30:** Implementation/local Day/Night desktop/mobile and independent QA/Security gates pass; protected CI/release/production acceptance remain. Progress7/30. No financial/source/importer changes.

> **Implementation intake — 2026-10-30:** C3 / DB-146 implementation is active on `codex/c3-truck-issues-implementation` after finalized contract PR688. Backend owns metadata APIs/migration; Frontend owns compact truck/RO panels. Fresh independent QA/Security and release acceptance remain pending. Isolated fictional local fixtures only; importer held, Shop Work redesign separate, no production financial mutations. Progress remains7/30.

> **Current handoff — 2026-10-30:** A2 and its controls corrections are production-verified through PR694/ce473b88 in Day/Night desktop/mobile. C3 / DB-146 resumes with Architecture-approved merge compatibility and a frozen implementation contract. No C3 implementation or completion claimed. Progress stays7/30; importer held, financial records unchanged.

> **Current parity handoff — 2026-10-30:** A2 is Done after PR687 production Day/Night desktop/mobile acceptance. C3 / DB-146 enters contract/discovery; no C3 implementation yet. Shop Work redesign stays separate/deferred. ETS importer held; no financial changes.

> **2026-10-30 UI follow-up:** A2 Closeout acceptance and C3 draft are recorded in docs PR688. Current DB-145 Fast UI correction styles open dropdowns, restores approved accent digits and fixes Activity count on arrival. See [controls receipt](verification/DB145_SHOP_WORK_CONTROLS.md). C3 remains next; no importer or financial changes.

> **A2 production follow-up, 2026-10-30:** Night contrast verification passed at1280/390 on current production. User identified missing Closeout count; Fast UI correction in `codex/a2-closeout-count` must pass local/CI/release smoke before A2 Done. Shop Work redesign is deferred and not a dependency. C3 remains next; importer held, no financial changes.

> **2026-10-16 source contact evidence gate:** DB-SOURCE-CONTACT-DOM is an acceptance correction to the existing source pipeline, not a new parity outcome. First verification cycle remains safely incomplete; scoped fix and production complete-evidence receipt pending. See [receipt](verification/DB_SOURCE_CONTACT_DOM.md).

# ETS parity implementation tracker

Last updated: 2026-10-30. Program owner: Product & Delivery Lead. Discovery inventory: [audit and evidence](ETS_PARITY_BACKLOG_2026-10-15.md). Delivery history: [PROJECT_BOARD](PROJECT_BOARD.md).

**Progress: 8/30 completed; 6/6 original selected outcomes completed. A2 and C3 are Done. R3 is next; 22 discoveries remain incomplete, including held B4.**

## Approved delivery order

**R1 → P1 → C1 → M1 → B1 → A1.** A1 is last in this selected wave. The other 24 items remain in the delivery backlog after this priority wave; retain every discovery and refine their order when the priority wave closes. B4 is tracked separately from this selected wave; its completed display/queue slices do not close the held importer outcome.

## Operating rules

1. Keep the stable audit IDs; never renumber or remove discoveries. Link each started item to one DB board ID, accountable owner, focused branch/PR and verification receipt.
2. Status moves **Backlog → Queued → In progress → Review → Ready to release → Deployed / verifying → Done**. `Blocked` must state the blocker, owner and next safe step. Failed acceptance returns to `In progress`.
3. Check `[x]` only for **Done**: acceptance, focused tests, required independent gates, protected CI, merge, deployment and actual production acceptance must all have evidence. Code written or CI green alone is not completion.
4. Each completion receipt records local / CI / merge / deployed / production-verified separately. Verify changed complete journeys in Light and Night Shop on desktop and mobile; preserve desktop density and a single compact scroll region. Financial/data work includes tenant, role, concurrency and negative cases.
5. At intake, gate failure, merge and release, update the item's row below and its board record. After Done, update the counts/current/next and immediately begin the next queued item. Do not silently skip a blocker or a dependency.
6. If new discoveries appear, append a stable ID with source evidence. If an outcome is split, retain the parent unchecked until all required child outcomes pass. If superseded, retain its disposition and link the replacement.
7. Before every resumed work session, read this tracker and the latest linked receipt. No scheduled/background work is implied; advancement happens during active implementation sessions.

A2 UI follow-up: user-selected solid Closeout/Activity badges released and production-verified in PR690 (2472e45a); Day/Night desktop/mobile. [Receipt](verification/DB145_SOLID_BADGES.md). Parity completion count and C3 sequence unchanged.

## Selected outcomes

- [x] **R1 — Scheduled start, promised finish and an overdue queue**
  - Status: **Done — merged, deployed and production verified**. Board: **DB-131**. Owner: Backend & Integrations.
  - Evidence: [R1 verification receipt](verification/DB131_REPAIR_ORDER_SCHEDULING.md).
- [x] **P1 — Cost-based parts markup matrices with minimum price and locked-price rules**
  - Status: **Done — merged, deployed and production verified**. Board: **DB-132**. Owner: Backend & Integrations.
  - Evidence: [P1 contract](contracts/db132-parts-pricing-matrix.md); [intake receipt](verification/DB132_PARTS_PRICING_MATRIX.md).
- [x] **C1 — Customer-specific labor rates and parts pricing defaults**
  - Status: **Done — PR550 merged, deployed and production verified; independent QA/Security GO**. Board: **DB-133**. Owner: Backend & Integrations.
  - Approved: new external orders use the customer agreed labor rate, otherwise the shop billing rate; existing orders retain saved rates.
  - Evidence: [C1 readiness notes](verification/DB133_CUSTOMER_PRICING_READINESS.md). [C1 contract](contracts/db133-customer-pricing-defaults.md) and [implementation receipt](verification/DB133_CUSTOMER_PRICING_DEFAULTS.md).
- [x] **M1 — Multiple recurring maintenance programs per truck**
  - Status: **Done — PR #571 and Night correction #572 merged, deployed and production verified; independent QA/Security GO**. Board: **DB-134**. Owner: Backend & Integrations.
  - Evidence: [M1 contract](contracts/db134-maintenance-programs.md); [implementation receipt](verification/DB134_MAINTENANCE_PROGRAMS.md).
- [x] **B1 — Customer transaction ledger, statements and overdue-balance aging**
  - Status: **Done — PR #575 merged, deployed and production verified**. Board: **DB-135**. Owner: Backend & Integrations.
  - Delivered read-only account activity, supported native balances/aging and unsent PDF statements. Owner-approved 34 Test / 13 Real classifications exclude test activity; unknown/source/settlement gaps remain held. Real does not establish payment or collection authority. ETS history remains separate. No financial records changed.
  - Evidence: [final B1 receipt](verification/DB135_CUSTOMER_RECEIVABLES.md#merged-deployed-and-accepted--2026-10-19), [PR575 final release receipt](https://github.com/mecaniser/truck-pit-stop/pull/575). All six checks, exact c66cabf2 Web/Worker, fixed financial retention and actual signed-in Light/Night desktop/mobile account/PDF acceptance passed.
- [x] **A1 — Actual labor cost and defensible job contribution**
  - Status: **Done — PR598 merged, exact Web/Worker deployed, production Day/Night desktop/mobile acceptance and independent release gates passed**. Board: **DB-136**. Owner: Backend & Integrations; Architecture reviews contracts.
  - Source and READ ONLY aggregate intake complete. Technician cost rates are absent; billing hours/rates are not wage expense. Sparse actual job time and missing parts costs prevent a reliable historical whole-job margin.
  - Evidence: [A1 policy proposal and intake](contracts/db136-labor-cost-policy-proposal.md). Owner approved loaded hourly cost from October20 shop-local date, owner-only access and separate overhead. [Final implementation contract](contracts/db136-labor-cost-contract.md) has Architecture GO. Backend/API and owner-only Job Contribution UI pass focused checks, real isolated PostgreSQL migration/API/retention rehearsal and actual Day/Night desktop/mobile owner/admin acceptance. [Verification](verification/DB136_LABOR_COST.md), [PR598](https://github.com/mecaniser/truck-pit-stop/pull/598). No production rates/reviews or QA financial changes. All47 classified invoices retained; postrelease28-cohort hashes match. Initial premerge scheduled ETS sync differences are qualified in the final receipt. ETS importer remains held.

Dependencies: P1 precedes C1 parts-price defaults. M1 must retain existing PM/telemetry provenance. B1 must distinguish native collectible balances from ETS-owned history. A1 requires explicit effective-date labor-cost policy and follows the operational work.

## Retained backlog

- [ ] **B4 — ETS-owned invoice/payment mirror and imported-order billing guard** — **Partially delivered; importer held.** Board DB-139. Reader/API/UI PR576 is merged/deployed: source-backed totals and supported payment states, identity/freshness holds and duplicate native-invoice guards. Compact footer/popover PR582 and native-only Ready to Close PR590 are merged/deployed with signed-in Light/Night desktop/mobile acceptance. History remains reachable; financial rows stayed unchanged. These child releases do not close B4's full source/payment-sync scope. Proposed importer changes remain on `codex/db139-importer-money-held` until existing-payment handling has a guard, contract and independent gates. No collector invocation, configuration change, backfill, financial apply or native invoice creation is authorized. [Contract](contracts/db139-ets-financial-mirror.md), [reader evidence](verification/DB139_ETS_FINANCIAL_MIRROR.md), [footer receipt](verification/DB139_COMPACT_BILLING_SUMMARY.md), [queue final receipt](https://github.com/mecaniser/truck-pit-stop/pull/590). Full reader-only PR576 browser coverage is not inferred solely from the later paid-example/footer checks; retain exact evidence boundaries.


- [ ] **R2 — Repeat or selectively copy a prior repair order/estimate** — Backlog; after the priority wave. Relative value/size: Medium / M. See audit for evidence and dependencies.
- [ ] **R3 — Defer an existing operation into tracked recommended work** — Queued next; source discovery and a separate contract precede implementation. Relative value/size: High / L. See audit for evidence and dependencies.
- [ ] **R4 — Signed authorization attached to the exact estimate revision** — Backlog; after the priority wave. Relative value/size: High / L. See audit for evidence and dependencies.
- [ ] **R5 — Operation/issue findings with linked photos and a customer-ready report** — Backlog; after the priority wave. Relative value/size: Medium / L. See audit for evidence and dependencies.
- [ ] **R6 — Structured arrival and handover details: parking, key location, arrival condition** — Backlog; after the priority wave. Relative value/size: Medium / S–M. See audit for evidence and dependencies.
- [ ] **C2 — Customer groups with directory/report filters** — Backlog; after the priority wave. Relative value/size: Medium / M. See audit for evidence and dependencies.
- [x] **C3 — Truck issues and follow-up work recorded without opening an RO** — **Done — merged, deployed and production accepted**, DB-146. Backend & Integrations accountable. Standalone issues, staff responsibility/date, exact-truck next-visit visibility and metadata-only existing-visit references; priced recommendation conversion remains separate. Independent QA/Security, real PostgreSQL races/retention, all seven protected checks, exact Web/Worker deployment and Day/Night desktop/mobile acceptance passed. No production QA issue or financial writes. [Contract](contracts/db146-truck-issues.md); [final receipt](verification/DB146_TRUCK_ISSUES.md).
- [ ] **C4 — Customer payment terms, credit limits and review warnings** — Backlog; after the priority wave. Relative value/size: High / L. See audit for evidence and dependencies.
- [ ] **S1 — Capacity-aware appointment and dispatch calendar** — Backlog; after the priority wave. Relative value/size: High / L. See audit for evidence and dependencies.
- [ ] **S2 — Reusable fees: flat, percent, capped and quantity-based** — Backlog; after the priority wave. Relative value/size: High / M–L. See audit for evidence and dependencies.
- [ ] **S3 — Shared tags and saved work queues** — Backlog; after the priority wave. Relative value/size: Medium / M. See audit for evidence and dependencies.
- [ ] **S4 — Invoice and contact results in global shop search** — Backlog; after the priority wave. Relative value/size: Medium / M. See audit for evidence and dependencies.
- [ ] **P2 — Canonical part aliases and interchangeable alternatives** — Backlog; after the priority wave. Relative value/size: High / M–L. See audit for evidence and dependencies.
- [ ] **P3 — Purchase-order freight, tax, discounts and other expenses** — Backlog; after the priority wave. Relative value/size: High / M–L. See audit for evidence and dependencies.
- [ ] **P4 — Scan a vendor invoice into a purchase-order draft** — Backlog; after the priority wave. Relative value/size: Medium / L. See audit for evidence and dependencies.
- [ ] **P5 — Formal cycle counts with optional barcode scanning** — Backlog; after the priority wave. Relative value/size: Medium / L. See audit for evidence and dependencies.
- [ ] **P6 — Accurate bulk-fluid and package-to-dispensed-unit stock** — Backlog; after the priority wave. Relative value/size: High if dispensing fluids / L. See audit for evidence and dependencies.
- [ ] **M2 — Shop inspection findings and a versioned inspection report** — Backlog; after the priority wave. Relative value/size: Medium–High when sold by shop / L. See audit for evidence and dependencies.
- [ ] **B2 — Repair-order deposits before the invoice is issued** — Backlog; after the priority wave. Relative value/size: High / L. See audit for evidence and dependencies.
- [ ] **B3 — One fleet remittance allocated across multiple invoices** — Backlog; after the priority wave. Relative value/size: High for fleet billing / L. See audit for evidence and dependencies.
- [x] **A2 — Work-in-progress aging and delay bottlenecks** — **Done — merged, deployed and production accepted (2026-10-30).** DB-145, Frontend & UX. PR676 functionality, PR680 Night contrast, PR687 pending Closeout count/mobile icons. Current waits retain Unknown timing; payment-only closeout remains separate. Prior independent QA/Security and populated synthetic/API gates retained; actual signed-in production Day/Night desktop1280/mobile390 passed on merge `c0eef04a`, exact successful Web deployment/build/readiness. Production zero-active-job coverage is qualified in the [final receipt](verification/DB145_SHOP_WORK_AGING.md#final-production-acceptance--2026-10-30). Redesign is not part of this outcome.
- [ ] **A3 — Deferred-work conversion and follow-up value** — Backlog; after the priority wave. Relative value/size: Medium / M. See audit for evidence and dependencies.
- [ ] **A4 — Inventory velocity, dead stock and purchasing priorities** — Backlog; after the priority wave. Relative value/size: Medium / M–L. See audit for evidence and dependencies.

## Completed: R1 / DB-131

Outcome: staff can set an intended start and promised finish, see approaching/overdue work, and act from a filtered queue. These timestamps are distinct from appointment time, invoice due date and actual work timestamps.

Acceptance before editing application code:
- Optional scheduled start/promised finish persist, clear and reload; validate ordering and explicit timezone semantics without changing existing orders.
- Staff permissions and exact tenant/order scope apply; deleted/terminal work and unauthorized roles reject edits as the approved contract defines. Concurrent edits must not silently overwrite a newer schedule.
- Overdue classification/filter/count/paging/sort are consistent and exclude finished/cancelled/deleted work; deadline transitions become visible without a full reload.
- Compact queue indication and accessible schedule editor preserve search/back/cancel, desktop density, touch controls, single scroll and Light/Night readability.
- No appointment/resource calendar, customer sends, billing, payment, technician time or completion mutation side effects.
- Additive migration/rollback proof, focused backend/frontend tests, independent QA/security appropriate to schema/tenant boundaries, protected CI and deployed acceptance.

Branch: `codex/ets-repair-order-scheduling`. Contract: `docs/contracts/db131-repair-order-scheduling.md` (approved). PR: [538](https://github.com/mecaniser/truck-pit-stop/pull/538) merged as `7b3dc4b30a52e6880580f1511716afc38dbd1ba2` on 2026-10-15. All six protected checks passed on `21546789`; merged tree is identical. Exact Web/Worker and schema173 verified; production Light/Night desktop,390/320 portrait and740 landscape accepted; independent closure GO. Synthetic baseline restored.

## Completed: P1 / DB-132

Accountable: Backend & Integrations. Implementation branch: `codex/ets-parts-pricing-matrix-implementation`; correction branch: `codex/parts-pricing-visible-validation`. PR542 and PR544 are merged/deployed; final corrected production UI and independent QA/Security acceptance passed. R1 and DB137 are also Done.

Acceptance before editing application code:
- Owner/admin can define and preview cost-band markup, optional pricing-cost basis floor, minimum sale price and fixed catalog pricing, with explicit activation and no guessed defaults.
- One Decimal resolver covers new external RO/service/PM/counter-sale attachments; internal fleet remains actual cost. Retained lines, quantity edits and issued financial records preserve their existing snapshots and prices.
- Immutable revision/line provenance, audited authorized overrides and tenant/role/concurrency boundaries prevent silent repricing or cost-data leakage.
- Compact existing price/inventory controls; complete Light/Night desktop/mobile journeys, negative/tenant/concurrency tests, independent QA/Security, protected CI and exact production release evidence before Done.

See [contract](contracts/db132-parts-pricing-matrix.md) for full scope, writer coverage, locking, inactive defaults and safe production verification limits. P1 application changes and additive migration174 are deployed through PR542; correction PR544 is live at70530bda. Both themes passed desktop and emulated mobile production acceptance. Pricing remains inactive; no guessed rates or defaults were configured. The later inventory fingerprint change is attributed to the normal ETS sync; retained usages/invoices are unchanged. See the receipt for exact evidence and limits.

DB-139 presentation follow-up (2026-10-19): compact footer retains source total/status and moves support details into an accessible popover. Frontend & UX owns this Fast UI slice; existing source boundaries and held importer remain unchanged. [Receipt](verification/DB139_COMPACT_BILLING_SUMMARY.md). PR582 CI passed; merged/deployed b994794b is healthy. Signed-in production desktop/mobile acceptance passed after session renewal; compact-footer presentation slice Done. Broader B4/importer remains held; B1 later completed through PR575.

Historical B1 owner steering (2026-10-19; superseded by the completed classification/release above): finish read-only with reviewed real/test classification; real billing remains ETS/QuickBooks. All47 native candidates are listed privately, original32 gaps unchanged. Owner selections were subsequently received and applied to the read-only view; no financial apply was authorized. [Classification proposal](contracts/db135-native-record-classification.md).

DB-139 queue follow-up Done (2026-10-20): PR590 merged76966f24, exact Web/Worker deployed, all six protected checks passed. Actual NC Day/Night desktop1280 andmobile390 acceptance verified native-only Ready to Close, consistent count/value/pagination and reachable ETS history. Financial cohort hashes unchanged, zero acceptance API writes. [Final receipt](https://github.com/mecaniser/truck-pit-stop/pull/590). Importer stays held; that release returned the selected wave to A1 discovery. The current A1 handoff below supersedes that historical stage.

## Current handoff: selected wave complete (2026-10-21)

R1/P1/C1/M1/B1/A1 are Done, with exact release receipts. A1 is available under Shop Analytics → Job Contribution, with owner-only Technician Costs. No actual rates were guessed or entered. The other24 discoveries remain retained; their next delivery order requires a separate priority decision. B4 remains partially delivered and its importer held. No new feature, financial mutation, importer rollout or payroll integration is implied.

## Next wave selection — 2026-10-29

User selected A2 first, with Shop Work as its primary surface. C3, R3, A3 and S1 follow in the recommended sequence, with separate contracts and implementation items. This does not authorize financial/stock/source mutations or release the held B4 importer. A2 and C3 are Done; completed count is 8/30. Continue R3 → A3 → S1 with separate contracts and gates.
