# Easy Truck Shop → DieselBridge functionality audit

Baseline audit date: 2026-10-12. Accountable owner: Product & Delivery Lead. Board item: DB-101.
DieselBridge baseline: `origin/main` at `91045a625f89d84221aaf8ed74d1cdc7d92438b6`.

The matrix below preserves the original baseline comparison. Subsequent implementation and release evidence is recorded in dated continuations and [the delivery board](PROJECT_BOARD.md); baseline gap labels are not a current release-status dashboard.

## Evidence and scope

This is a functional comparison, based on read-only inspection of an authenticated Easy Truck Shop (ETS) account, ETS's official help center, and DieselBridge source. It does not reproduce ETS source code, branding, or proprietary assets. No ETS record, invoice, payment, provider connection, or account setting was changed.

Evidence labels used below:

- **Observed:** visible in the signed-in ETS interface on this date. Controls were inspected, not submitted; a visible control is not proof of its successful write behavior.
- **Documented:** described in ETS's official help center; not necessarily exercised in the inspected account.
- **Code:** present in DieselBridge source at the baseline. Presence does not certify production activation or end-to-end behavior.
- **Gap:** absent or incomplete in the inspected DieselBridge paths. It is not a claim that every branch, tenant flag, or external integration was examined.

The inspection covered global navigation/search, customer and vehicle workspaces, invoiced/completed services, invoice controls, service templates, and vehicle history. The help-center inventory supplied additional workflow coverage. Full exhaustive behavioral parity remains unverified: role-specific experiences, every configuration permutation, notification delivery, provider write outcomes, and accounting reconciliation require separate acceptance scenarios. Customer identities, amounts, and account screenshots are intentionally excluded from this document.

## Workflow and capability inventory

| Workflow | ETS evidence | DieselBridge baseline | Assessment / action |
|---|---|---|---|
| Find a customer, truck, job, or part | Observed grouped global search with five results per group and more-results links; documented partial matching across additional categories [1] | Separate existing customer/vehicle/inventory typeahead and repair-order search, no staff-shell aggregate | **DB-098:** compose existing scoped searches into a keyboard-accessible shop search with real detail destinations. Invoice/contact global search remains outside this slice. |
| Customer directory and contacts | Observed company, vehicle, contact, transaction, PM, service, attachment tabs and balance | Customer directory/detail, contacts, customer portal and tenant relationship model | Existing core capability. Do not rebuild a second CRM. |
| Truck identity and history | Observed truck service history, PM, invoices, attachments, issues; documented history export [2] | Vehicle records, fleet repair orders and inspection history; explicit owner/operator/payer relationships | Existing core history. Validate export presentation separately; exact vehicle identity must remain authoritative. |
| Outside-shop history | Documented external services with vendor, work and supporting receipts [3] | DB119 shipped a separate staff-only outside-shop record and audit trail in PR520 | Core record implemented with provenance and optional cost; receipt attachments remain backlog. |
| Intake and work-order pipeline | Observed estimate/upcoming/on-site/priority/completed/invoiced navigation; documented mileage, parking, key, complaint, assignment, holds and completion flow [4] | Repair-order lifecycle, appointments, assignments, board, notes and history | Core exists. Compare operator decisions and transitions before adding more statuses. |
| Estimates and customer authorization | Documented estimate/approval flow [4]; observed invoice/request-signature controls | Quote revisions, sends, approval/decline and authorization history | Existing. Signature and delivery semantics need separate acceptance; no new provider sends authorized by this audit. |
| Reusable services and labor rates | Observed template list, duration/rate, labor-rate and shop-supply tabs | Service packages with labor duration/flat prices and fractional part quantities | Existing. Improve templates in place rather than adding a duplicate catalog. |
| Template-driven checklists | Documented checklist tasks, completion block and completion attribution [5] | Fixed fleet inspection checklist exists; generic service-template task definitions and job task completion are absent | **DB-102 implemented locally:** versioned template definitions, immutable job snapshots, actor/time completion, required-task gates and PM scope preservation. Migration165 and role/tenant/concurrency behavior independently reviewed; PR/release separate. |
| Recommendations / declined work | Documented truck-level unresolved issues surviving visits, recommendation-to-complaint/template path, invoice visibility [6]; observed vehicle Issues tab | Recommendations stored and managed on an individual RO | **DB-099:** surface unresolved prior-visit recommendations for the exact truck, with priority/date/source. Read-only carry-forward; no automatic duplication, charge or resolution. Conversion, customer follow-up and invoice presentation remain later work. |
| Parts on a service | Observed parts grouped with service items | Inventory-backed and manual part lines, cost snapshots and pricing controls | Existing. Preserve stock, cost and pricing invariants. |
| Cost-based parts pricing | Documented cost bands, customer-specific matrices, floor and saved sale price behavior [7] | Part catalog/pricing operations exist; exact matrix equivalence not established by this audit | Verify existing pricing contracts and customer overrides before declaring a new matrix missing. |
| Inventory and vendors | Observed categories, out-of-stock requests, orders, returns, vendors, sales, activity | Inventory, supplier demand, reorder, procurement batches, partial receipts, core return/waiver and supplier credit reversal | Substantial existing capability. Activation and operation tests are separate from code presence. |
| Purchase-document scanning | Official AI purchase-order document-scanning article [8] | No document-extraction workflow identified in inspected inventory paths | Lower priority than receiving accuracy and costing. Requires confidence review, duplicate prevention and cost controls. |
| Counter / parts sales | Observed Sales navigation | Counter-sales code exists behind deployment/tenant/backfill gates | Verify activation/readiness; do not duplicate or enable flags through this work. |
| Sublet / outsourced work | Documented several ways to represent outsourced cost and customer charges [9] | Labor sublet line type with vendor-cost field | Existing representation. **DB-100** reports known vendor contribution truthfully; no payment or payable automation. |
| Technician attendance and job timers | Observed timesheets/timeline/efficiency/productivity navigation; documented attendance vs job-time distinction [10] | Attendance, breaks, repair-order and miscellaneous timers | Existing. Do not treat attendance as billable labor or infer wages. |
| Technician productivity / efficiency | Documented billed/job hours and job/attendance ratios [10] | Workforce/analytics code exists | Requires formula-by-formula runtime comparison; no unsupported parity claim. |
| Appointment and shop capacity | Documented scheduling and service workflow [4] | Appointment timestamp/duration, fixed hourly slots, no technician/bay resource capacity in inspected model | Valuable backlog: resources, working hours, duration overlap and conflict handling. |
| Preventive maintenance | Observed customer/truck PM and PM-service navigation | Vehicle PM interval/next-due fields and fleet workflows | Existing primitives. Recurring program scheduling and notification equivalence remain unverified. |
| DOT inspection workflow | Documented sectioned pass/NA/repair inspection, photos, recommendations and locked report [11] | Fleet inspection/checklist primitives | Partial domain overlap. Do not claim regulatory equivalence or bolt generic inspection onto compliance paperwork without a reviewed requirement. |
| Attachments, notes, audit history | Observed service/vehicle/customer attachments and service activity with author/time | Existing attachments, internal notes and repair-order activity | Existing; verify visibility and retention per journey. |
| Invoice finalization | Observed finalization/billed/unpaid/paid filters, due date and invoice controls | Native invoice lifecycle and protections | Existing. ETS imported records and native collectible balances must stay distinguishable. |
| Payments and customer credit | Observed payment/credit controls; documented one payment allocated across invoices [12] | Native payment, settlement, credit and split-payment capability with gates | Existing high-risk domain. No provider activation, collection, balance edits or historical payment replay in this initiative. |
| Open balances and A/R aging | ETS explicitly documents no built-in aging report; exports and external worksheet buckets [13] | Invoice/customer balance primitives; accounts analytics is paid-invoice revenue, not A/R aging | Product improvement opportunity, **not ETS parity**. Requires canonical outstanding-balance/credit allocation contract before statements or reminders. |
| Invoice reminders / communication | Documented general invoice workflow [4]; inspected Send controls | Invoice reminders, messaging and customer quote communications exist | Existing. Channel consent/delivery and tenant switches require distinct checks. |
| Reports and exports | Observed sales, fees, tax, part revenue, inventory, orders, service types, payments navigation | Multiple reporting endpoints, analytics and exports | Broad core exists. Compare calculation meaning, not chart count. |
| Profitability / cost truth | ETS separates job time from wage cost in mechanic documentation [10] | Analytics subtracts fields named `total_parts_cost` and `total_labor_cost` that actually represent billed sales; margins clamped to 0–100 | **DB-100:** replace unsupported whole-job margin with parts/sublet contribution and explicit missing-cost states. Labor wages and discount allocation are unavailable. |
| Integrations | Observed QuickBooks links and integration settings; official integration directory lists QuickBooks, Stripe, Samsara and Datatruck [14] | Existing native accounting/payments and Motive/fleet capabilities | Preserve integrations and source provenance. A competitor integration list is not authorization to provision accounts or migrate providers. |
| Roles, mobile and portals | Observed staff account; portal controls visible | Existing staff roles, customer/fleet/driver surfaces and tenant guards | Broader ETS role/write behavior unverified. Every new aggregate must preserve DieselBridge role/tenant boundaries. |

## DieselBridge source anchors

These are the relevant implementation locations, not declarations of deployed acceptance:

- `frontend/src/components/layout/DashboardLayout.tsx`: staff navigation/shell; separate search endpoints live in customer, vehicle, inventory and repair-order APIs.
- `backend/app/db/models/service.py`, `frontend/src/features/repair-orders/PriceBuilderPanel.tsx`: service-package labor and parts.
- `backend/app/api/v1/endpoints/quotes.py`: quote revision and authorization lifecycle.
- `backend/app/api/v1/endpoints/mechanics.py`: attendance, break, job and miscellaneous timers.
- `backend/app/api/v1/endpoints/parts_operations.py`: demand, procurement, receipts, core and supplier returns.
- `backend/app/tasks/invoice_reminders.py`: existing reminder orchestration.
- `backend/app/api/v1/endpoints/fleet.py`: native repair-order and inspection history.
- `backend/app/db/models/recommended_service.py`, `backend/app/api/v1/endpoints/repair_orders.py`: original per-order recommendations.
- `backend/app/api/v1/endpoints/appointments.py`: existing single-resource slot logic.
- `backend/app/services/pricing.py`, `backend/app/api/v1/endpoints/reports.py`, `backend/app/db/models/inventory.py`, `backend/app/db/models/labor.py`: billed totals versus part cost snapshots and vendor cost.
- `backend/app/api/v1/endpoints/invoices.py`, `backend/app/api/v1/endpoints/invoice_settlements.py`: invoice and credit semantics; credit aging is not receivables aging.

## Delivery priorities

| Priority | Outcome and value | Boundary / acceptance | Delivery |
|---|---|---|---|
| P0 | Stop misleading margin figures that can distort pricing decisions | Show known parts/sublet revenue and cost; unknown cost and labor cost remain explicit; signed losses; tenant/deleted guards; preserve invoice revenue semantics | DB-100, `codex/report-cost-evidence`; contract `docs/contracts/db100-profitability-evidence.md` in that branch. |
| P1 | Find the right customer, truck, job or part without switching workspaces | Bounded requests; role-aware sources; query/session isolation; partial failures; accessible keyboard/mobile; result opens actual record in both staff presentations | DB-098, `codex/ets-workflow-parity`. |
| P1 | Keep an unresolved truck problem visible on its next visit | Exact vehicle and current customer relationship; historical source retained; resolved/deleted/canceled excluded; cross-tenant and role negatives; no mutation | DB-099, `codex/recommended-work-carry-forward`; contract `docs/contracts/db099-recommended-work-carry-forward.md` in that branch. |
| P1 selected | Template checklists with completion evidence | Versioned snapshot per job; actor/time; edit and reopen semantics; all completion paths enforce required work; no retroactive template mutation | DB-102 implemented and browser-verified locally on `codex/service-template-checklists`; independent Security/QA GO. Migration165 required; production unchanged. |
| P2 | External service history | External provider/date/work, optional historical odometer/reference/USD cost; duplicate-safe retry and edit audit; no native invoice/payment implied | DB119 shipped in PR520 and production verified; attachments remain follow-up. |
| P2 next | Capacity-aware scheduling | Shop timezone/working hours, resources, duration overlap, reschedule conflict/retry, permission rules | Proposed follow-on, unimplemented. |
| P2 next | Native A/R aging and statements | Canonical collectible balances and credits, as-of basis, due dates, imported provenance, statement preview; no automatic outreach | Opportunity beyond ETS; unimplemented. |
| P3 | Purchase-document extraction | Human review, duplicate matching, tax/currency/quantity confidence, upload security and bounded spend | Unimplemented; evaluate only after inventory fundamentals. |

The four implemented outcomes have focused branches/PRs; DB099 compact scrolling should precede or accompany DB102 Modern rollout. They intentionally avoid creating parallel billing, stock or identity systems. Their verification records and board entries must distinguish source implementation, local browser acceptance, pull request, merge and deployment. This audit does not mark any implementation Done.

Historical delivery snapshot (2026-10-12): [search/audit PR500](https://github.com/mecaniser/truck-pit-stop/pull/500), [recommendations PR498](https://github.com/mecaniser/truck-pit-stop/pull/498), [cost evidence PR499](https://github.com/mecaniser/truck-pit-stop/pull/499), and [checklists PR501](https://github.com/mecaniser/truck-pit-stop/pull/501). All four are locally implemented and authenticated-browser verified in an isolated combined preview at `http://127.0.0.1:5174` (API8001). Independent Security/QA gates for the cross-layer changes pass; combined frontend142files/1247tests pass. PR/CI status is time-sensitive; nothing in this initiative is merged or deployed. Detailed implementation, runtime, migration and remaining release gates are in each focused PR and verification record.

## Official ETS sources

1. [Global search](https://support.easytruckshop.io/en/articles/14175598-how-to-use-global-search)
2. [Export an individual truck's history](https://support.easytruckshop.io/en/articles/11814293-how-to-export-an-individual-truck-s-history)
3. [External service](https://support.easytruckshop.io/en/articles/11887994-what-is-an-external-service)
4. [Complaint-to-invoice workflow](https://support.easytruckshop.io/en/articles/11655319-how-to-create-a-new-service-work-order-complete-flow-from-complaint-to-invoice-original)
5. [Service-template checklists](https://support.easytruckshop.io/en/articles/16415651-service-templates-checklist-template)
6. [Recommendations and issues](https://support.easytruckshop.io/en/articles/16515197-recommendations-issues-how-they-work)
7. [Parts price matrix](https://support.easytruckshop.io/en/articles/11664125-using-the-parts-price-matrix)
8. [Purchase-order document scanning](https://support.easytruckshop.io/en/articles/14215442-using-ai-document-scanning-on-purchase-orders)
9. [Sublet work orders](https://support.easytruckshop.io/en/articles/14658933-what-is-a-sublet-work-order)
10. [Mechanic reports](https://support.easytruckshop.io/en/articles/16751908-where-do-i-check-mechanic-reports)
11. [DOT inspection workflow](https://support.easytruckshop.io/en/articles/16532503-dot-inspections-how-to-run-an-inspection-from-start-to-finish)
12. [Multi-invoice payment allocation](https://support.easytruckshop.io/en/articles/16416315-how-to-apply-one-payment-to-multiple-invoices-customer-transactions)
13. [A/R and aging limitations](https://support.easytruckshop.io/en/articles/16739469-who-owes-me-money-getting-your-a-r-and-building-an-aging-report)
14. [Integrations](https://support.easytruckshop.io/en/collections/19131242-integrations)

[Help center](https://support.easytruckshop.io/en/) and [navigation articles](https://support.easytruckshop.io/en/collections/13751702-navigation) were used to map modules. Authenticated evidence was retained as read-only observations; source account data is not a committed fixture.


## 2026-10-14 focused continuation: operation documentation (DB118)

Fresh authenticated ETS item Notes inspection and REA6.4.0 evidence confirm per-operation notes with separate internal order notes. DieselBridge already had order-level notes but lacked operation linkage. DB118 adds exact labor-linked, attributed, append-only shop notes and safe retry, with shop-only default and explicit role/assignment boundaries instead of copying ETS public-by-default note behavior. Staff history preserves original operation identity after removal. No price/timer/completion side effects or customer publication. Implementation, tests, runtime and release status: [DB118 evidence](verification/DB118_OPERATION_NOTES.md); board remains the current status source. This does not claim all ETS functionality is complete. External service history and capacity-aware scheduling remain separate model/workflow gaps.


## 2026-10-14 continuation: outside-shop service history (DB119)

Read-only authenticated Vehicles → More → Add External Service confirms provider/date/odometer/reference, issue and labor/part amounts, attachments. REA6.4.0 parsed five fresh observed public assets from build2026-10-14-11-35-29:42491bytes,10260ASTnodes,zero parse failures, ev_30e94734595c3498ed113387938beea58f81e99f031635e316ad3e9532b22277. Static syntax is not vendor write acceptance; no ETS data changed or source reused. DBN native repair histories have no equivalent dedicated record. DB119 selected: a staff-only external history entry with original attribution, duplicate-safe retries and recoverable corrections, explicitly excluded from native billing/PM/current mileage. Receipt files and external invoice line-item reconstruction remain separate gaps. See verification/DB119_EXTERNAL_SERVICE_HISTORY.md and the board for implementation/release status.

DB119 release: PR520 merged6b7dfcb0, Web/worker deployed, schema169, independent QA/Security GO, actual desktop/mobile browser workflows verified in production. Outside-shop core record gap closed; receipt attachments and external invoice line-item reconstruction remain separate follow-ups. Full evidence: [DB119 release receipt](verification/DB119_EXTERNAL_SERVICE_HISTORY.md).


## 2026-10-14 continuation: vehicle history export (DB120)

Fresh authenticated vehicle-history menu confirms Export History; official truck-history export guide[2] supplies intended use. REA6.4.0 parsed four observed public history/filter assets (27605bytes,6708ASTnodes,zero parse failures), evidence ev_936429546b7aa03e25b11e665c3044fe477a1b22862072de87418f4ac4df3a59. Source syntax indicates exact-vehicle export with current filters; vendor file contents/write behavior not verified. DBN staff customer/repair-order truck context only provides paginated history. DB120 adds a scoped completed-service CSV with explicit provenance and historical date/mileage semantics, excluding private notes/deleted/voided entries. Customer portal CSV is a distinct existing surface. See [DB120 evidence](verification/DB120_VEHICLE_HISTORY_EXPORT.md) and board for current release status.

DB120 release: PR521 merged648c8ba6; exact Web/worker deployments successful, independent Security/releaseQA GO, all six CI checks green. Actual production desktop,320/390portrait andlandscape verified full/filtered CSV downloads, source/date/mileage truth, empty/failure/retry/cancel and return navigation. Staff export gap closed; all source rows are preserved without importer consolidation. External receipt attachments, capacity-aware scheduling and DB122background ledger paging remain separate follow-ups. See the DB120 release receipt for exact evidence and browser-emulation limits.


## 2026-10-14 continuation: bounded browsing during intake (DB122)

Fresh authenticated ETS completed-service, customer/truck entry, and directory inspection confirms scoped search and bounded result navigation. REA 6.4.0 parsed four observed public list/filter/intake assets from build2026-10-14-13-08-02: 21,369 bytes, 4,844 AST nodes, zero parse failures; evidence ev_c0cb0ce145816787c6f1af50b1ba90440a1db8c30eb711cf0bba7666b464c3cc. Static search/state-preservation syntax supports the UI observation but does not prove vendor writes. No account data or vendor code was reused.

The highest immediate process gap was reproduced in DBN: mobile customer-truck intake drained 2,525 of 3,520 unrelated order rows behind the dialog without scrolling. DB122 corrects the observer boundary and pauses hidden intake/compact-record pagination, while preserving manual loading, search, and return context. This is a reliability improvement to an existing parity workflow, not a newly discovered ETS feature. Receipt attachments and capacity-aware scheduling remain the larger workflow gaps; exact-truck on-screen history search is also a useful follow-up distinct from CSV date filters. Board ID122 supersedes the original paging observation numbered121, which conflicts with the separate signed shop-history integration item. [Verification](verification/DB122_BOUNDED_ORDER_BROWSING.md).


DB122 released: PR523 merged53995654 after six green CI checks; exact Web deployment e430fe54 succeeded. Production desktop1280, portrait390/320 and landscape740×400 verified bounded intake (25 rows versus2,525 previously), actual scroll/keyboard pagination, failure/retry, customer/truck cancellation and search/status preservation. No record writes. [Release receipt](verification/DB122_BOUNDED_ORDER_BROWSING.md). This closes the reproduced queue-loading defect; broader parity remains open.


## 2026-10-14 continuation: on-screen truck history search (DB123)

Fresh authenticated ETS vehicle-history search was exercised with a matching description and a no-match term. Filter state appears in the page URL. REA6.4.0 parsed four observed public assets from build2026-10-14-17-02-12 (17,371bytes,4,248ASTnodes,zero parse failures), evidence ev_bb4bcd33bfc3289d94b1c9d03159b0e9a35c4ec80fa154f0bddeead83855327a. Static syntax corroborates search/status/page routing; no vendor writes or source reuse.

DB123 exposes DBN’s existing exact-vehicle server-side search and status filters in the shared customer/repair-order truck workspace. Filters apply across all pages, preserve navigation context in scoped URL parameters and separate no matches from failures. This shop’s repair history precedes outside-shop records; compact controls wrap on touch screens. Search covers the existing order-number/work-requested contract, not operation notes or outside-shop entries. Receipt attachments and capacity-aware scheduling remain separate gaps. [Evidence](verification/DB123_VEHICLE_HISTORY_SEARCH.md).


DB123 released: PR525 and corrective PR527 are merged; Web732200cf succeeded at01d8146b, authenticated production index-DafQAQ8U.js verified. Exact-truck search/status, cancellation focus, deliberate truck selection/reload and theme-readable actions pass real desktop1280, portrait320/390 and landscape740x400 workflows, including two trucks sharing a unit number. No business writes; touch/browser emulation only. [Final release receipt](verification/DB123_VEHICLE_HISTORY_SEARCH.md).
