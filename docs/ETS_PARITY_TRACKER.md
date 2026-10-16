> **2026-10-16 source contact evidence gate:** DB-SOURCE-CONTACT-DOM is an acceptance correction to the existing source pipeline, not a new parity outcome. First verification cycle remains safely incomplete; scoped fix and production complete-evidence receipt pending. See [receipt](verification/DB_SOURCE_CONTACT_DOM.md).

# ETS parity implementation tracker

Last updated: 2026-10-16. Program owner: Product & Delivery Lead. Discovery inventory: [audit and evidence](ETS_PARITY_BACKLOG_2026-10-15.md). Delivery history: [PROJECT_BOARD](PROJECT_BOARD.md).

**Progress: 3/29 completed; 3/6 selected outcomes completed. Current: M1 release preparation. Next: B1 after M1.**

## Approved delivery order

**R1 → P1 → C1 → M1 → B1 → A1.** A1 is last in this selected wave. The other 23 items remain in the delivery backlog after this priority wave; retain every discovery and refine their order when the priority wave closes.

## Operating rules

1. Keep the stable audit IDs; never renumber or remove discoveries. Link each started item to one DB board ID, accountable owner, focused branch/PR and verification receipt.
2. Status moves **Backlog → Queued → In progress → Review → Ready to release → Deployed / verifying → Done**. `Blocked` must state the blocker, owner and next safe step. Failed acceptance returns to `In progress`.
3. Check `[x]` only for **Done**: acceptance, focused tests, required independent gates, protected CI, merge, deployment and actual production acceptance must all have evidence. Code written or CI green alone is not completion.
4. Each completion receipt records local / CI / merge / deployed / production-verified separately. Verify changed complete journeys in Light and Night Shop on desktop and mobile; preserve desktop density and a single compact scroll region. Financial/data work includes tenant, role, concurrency and negative cases.
5. At intake, gate failure, merge and release, update the item's row below and its board record. After Done, update the counts/current/next and immediately begin the next queued item. Do not silently skip a blocker or a dependency.
6. If new discoveries appear, append a stable ID with source evidence. If an outcome is split, retain the parent unchecked until all required child outcomes pass. If superseded, retain its disposition and link the replacement.
7. Before every resumed work session, read this tracker and the latest linked receipt. No scheduled/background work is implied; advancement happens during active implementation sessions.

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
- [ ] **M1 — Multiple recurring maintenance programs per truck**
  - Status: **In progress — independent implementation GO and saved local workflows verified; ordered integration, CI and production acceptance pending**. Board: **DB-134**. Owner: Backend & Integrations.
  - Evidence: [M1 contract](contracts/db134-maintenance-programs.md); [implementation receipt](verification/DB134_MAINTENANCE_PROGRAMS.md).
- [ ] **B1 — Customer transaction ledger, statements and overdue-balance aging**
  - Status: **Queued**. Board: **DB-135**. Owner: Backend & Integrations.
  - Evidence: Not started.
- [ ] **A1 — Actual labor cost and defensible job contribution**
  - Status: **Queued**. Board: **DB-136**. Owner: Backend & Integrations.
  - Evidence: Not started.

Dependencies: P1 precedes C1 parts-price defaults. M1 must retain existing PM/telemetry provenance. B1 must distinguish native collectible balances from ETS-owned history. A1 requires explicit effective-date labor-cost policy and follows the operational work.

## Retained backlog

- [ ] **R2 — Repeat or selectively copy a prior repair order/estimate** — Backlog; after the priority wave. Relative value/size: Medium / M. See audit for evidence and dependencies.
- [ ] **R3 — Defer an existing operation into tracked recommended work** — Backlog; after the priority wave. Relative value/size: High / L. See audit for evidence and dependencies.
- [ ] **R4 — Signed authorization attached to the exact estimate revision** — Backlog; after the priority wave. Relative value/size: High / L. See audit for evidence and dependencies.
- [ ] **R5 — Operation/issue findings with linked photos and a customer-ready report** — Backlog; after the priority wave. Relative value/size: Medium / L. See audit for evidence and dependencies.
- [ ] **R6 — Structured arrival and handover details: parking, key location, arrival condition** — Backlog; after the priority wave. Relative value/size: Medium / S–M. See audit for evidence and dependencies.
- [ ] **C2 — Customer groups with directory/report filters** — Backlog; after the priority wave. Relative value/size: Medium / M. See audit for evidence and dependencies.
- [ ] **C3 — Truck issues and follow-up work recorded without opening an RO** — Backlog; after the priority wave. Relative value/size: High / M–L. See audit for evidence and dependencies.
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
- [ ] **A2 — Work-in-progress aging and delay bottlenecks** — Backlog; after the priority wave. Relative value/size: High / M. See audit for evidence and dependencies.
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
