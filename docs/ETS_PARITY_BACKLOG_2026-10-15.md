# ETS → DieselBridge: useful workflow gaps for selection

Audit date: 2026-10-15. Accountable owner: Product & Delivery Lead. Board item: DB-101 continuation.

**Decision state: user selected R1 → P1 → C1 → M1 → B1 → A1 on 2026-10-15.** Implementation status and completion evidence now live in [the parity tracker](ETS_PARITY_TRACKER.md). The remaining discoveries are retained for later selection. This document supersedes the original audit's stale missing/partial labels for the areas examined here; it does not supersede release receipts.

## Evidence and boundaries

- Compared the current DBN application tree at `origin/main` **9ec5d0916fcf3a9e837c12e96ad4465f85778867** with the attached integration checkout. Its additional commit changes documentation only.
- Read the delivery board, prior parity evidence, DBN models/endpoints/services and staff workspaces. Checked the signed-in production customer/truck workspace without modifying records.
- Inspected authenticated ETS navigation, price-matrix editor, preventive-maintenance list/new form, and purchase-order/new-order form. Cancelled or left unsaved forms; made no account changes or sends.
- Used REA 6.4.0 on ten freshly observed public JavaScript modules from ETS build **2026-10-14-17-02-12**: **40,646 bytes, 9,707 AST nodes, 193 static findings, zero parse failures, zero integrity contradictions**. Evidence: `ev_dd23a222a269441d5ac9d228ea05477633c66a9e63b0579e43c598ee795c82ee`. Pricing syntax includes cost bands, markup, cost-floor/fixed-price controls; maintenance syntax includes interval types, next due values and hours tracking. [Sanitized manifest and REA summary](verification/ETS_PARITY_BACKLOG_REA_2026-10-15.json).
- Cross-checked vendor behavior against official ETS help. Source code was inspected as inert text, not executed or copied into DBN. Static analysis supports feature discovery; it does not prove server rules, notifications, successful transactions or every role's behavior.
- This is the useful backlog found in the reviewed staff workflows, not a claim that every ETS feature, plan, role and integration has been exhaustively tested. No new desktop/mobile acceptance or deployment is claimed in this audit-only round.

**Status:** Missing = no corresponding implementation found in inspected current DBN paths. Extend = useful base exists but the described workflow is incomplete. **Basis:** ETS = vendor capability evidenced; DBN = proposed improvement beyond confirmed ETS behavior; Mixed = both. **Value:** High = frequent operator, cash-flow, downtime or cost benefit; Medium = volume/use-case dependent. **Size:** S/M/L are relative scope, not delivery estimates. Financial, data and cross-role items need their own contracts and acceptance before selection becomes implementation.

## Repair orders

| ID | Selectable outcome | Status / basis | Value / size | What to improve when implementing | Evidence |
|---|---|---|---|---|---|
| **R1** | Scheduled start, promised finish and an overdue queue | Missing / ETS | High / M | Separate customer promise from booking, actual start/completion and invoice due date. Show remaining time, reason for delay and next action without enlarging the header. | [E1], [D1], [D2] |
| **R2** | Repeat or selectively copy a prior repair order/estimate | Missing / ETS | Medium / M | Choose operations/parts and target truck; preview current prices. Never copy payments, signatures, completion, time logs or stock consumption. Keep source linkage and distinguish copying from moving work. | [E2], [D1] |
| **R3** | Defer an existing operation into tracked recommended work | Extend / ETS | High / L | Preserve source, actual time and consumed parts; show financial/stock effects before deferring. Reuse the duplicate-safe recommendation linkage already shipped. Do not require deleting technicians' time to move work back. | [E3], [D3] |
| **R4** | Signed authorization attached to the exact estimate revision | Extend / ETS | High / L | Build on current approve/decline and immutable revisions. One clear authorization flow, signer identity/time, signed copy and explicit reauthorization when scope changes. | [E4], [D4] |
| **R5** | Operation/issue findings with linked photos and a customer-ready report | Extend / ETS | Medium / L | Keep internal notes private; explicitly select findings/photos/recommendations to share. Order-level photos and internal operation notes already exist. | [E3], [E5], [D3], [D4] |
| **R6** | Structured arrival and handover details: parking, key location, arrival condition | Missing / ETS | Medium / S–M | Put short operational fields beside intake/release; expose only relevant information and retain change history. Do not bury them in a long notes field. | [E6], [D1] |

## Customers and accounts

| ID | Selectable outcome | Status / basis | Value / size | What to improve when implementing | Evidence |
|---|---|---|---|---|---|
| **C1** | Customer-specific labor rates and parts pricing defaults | Missing / ETS | High / M–L | Apply an account agreement automatically; show pricing origin and authorized overrides. Snapshot terms on the estimate so later account edits do not rewrite old work. Parts rules depend on P1; labor-rate defaults can ship separately. | [E6], [E7], [D5] |
| **C2** | Customer groups with directory/report filters | Extend / ETS | Medium / M | Add useful segments such as external fleets, walk-ins or contracted accounts. Existing internal-fleet/fleet-membership flags remain separate. Avoid making groups a substitute for ownership or billing identity. | [E8], [D5], [D10] |
| **C3** | Truck issues and follow-up work recorded without opening an RO | Extend / Mixed | High / M–L | Allow an issue at inspection or customer contact, give it an owner and follow-up date, and surface it next visit. Keep existing carry-forward/conversion history and avoid duplicate recommendations. | [E3], [D3] |
| **C4** | Customer payment terms, credit limits and review warnings | Missing / DBN | High / L | Make due dates consistent and flag exposure before new work. Start with transparent warnings and an attributed override; any hard credit hold is a separate product decision. Auto-approval thresholds already exist and are not this feature. | [D5], [D11] |

## Shop-wide workflow

| ID | Selectable outcome | Status / basis | Value / size | What to improve when implementing | Evidence |
|---|---|---|---|---|---|
| **S1** | Capacity-aware appointment and dispatch calendar | Extend / DBN | High / L | Assign bays/technicians, working hours and absence/capacity; flag conflicts. Existing appointments use shop-wide slot overlap and fixed slot generation, not resource capacity. Coordinate with R1. | [D2], [D1] |
| **S2** | Reusable fees: flat, percent, capped and quantity-based | Extend / ETS | High / M–L | Reuse consistent disposal, mileage, storage or environmental fees; customer exclusions and explicit tax treatment. Show quantity × rate to the customer. Preserve existing card-fee and tax policies. | [E9], [D5] |
| **S3** | Shared tags and saved work queues | Extend / Mixed | Medium / M | Searchable tags for jobs/purchases plus saved views such as waiting on a vendor or insurance work. Retain formal status/hold reasons; tags must not become a parallel lifecycle. Saved views are a DBN improvement. | [E6], [D1], [D6] |
| **S4** | Invoice and contact results in global shop search | Extend / ETS | Medium / M | Extend existing customer/truck/order/part search with authorized results and useful destinations. Keep search partial failures and role boundaries visible. | Original audit [1], [D12] |

## Parts inventory and purchasing

| ID | Selectable outcome | Status / basis | Value / size | What to improve when implementing | Evidence |
|---|---|---|---|---|---|
| **P1** | Cost-based parts markup matrices with minimum price and locked-price rules | Missing / ETS | High / M–L | Define cost bands and explicit precedence; preview margin and price changes. Version/archive rules and retain historical price snapshots so removal never breaks old orders. Supports C1. | [E7], fresh ETS/REA, [D6] |
| **P2** | Canonical part aliases and interchangeable alternatives | Extend / ETS | High / M–L | Find a part using OEM/vendor numbers, then offer suitable replacements. Supplier numbers already exist; distinguish aliases for one SKU from substitutes with their own stock/cost. | [E10], [D6] |
| **P3** | Purchase-order freight, tax, discounts and other expenses | Missing / ETS | High / M–L | Match vendor invoice totals without fake inventory parts. Define which expenses affect landed cost and which remain separate; support review before receipt. | [E11], fresh ETS New PO, [D6] |
| **P4** | Scan a vendor invoice into a purchase-order draft | Missing / ETS | Medium / L | Extract vendor/reference/parts/quantity/cost/expenses with confidence and duplicate detection. Require a human comparison before receiving stock; no autonomous inventory or accounting changes. Depends on P3 for complete invoice coverage. | [E12], fresh ETS AI-Reader control, [D6] |
| **P5** | Formal cycle counts with optional barcode scanning | Extend / DBN | Medium / L | Count by bin, preserve a count session, review variances and post approved adjustments. Stock adjustment reasons and bin locations already exist. Reconcile movements occurring during a count. | [D6] |
| **P6** | Accurate bulk-fluid and package-to-dispensed-unit stock | Extend / DBN | High if dispensing fluids / L | Buy a drum/jug, consume gallons/quarts and retain the remainder. Current fractional billing consumes rounded whole packages; change stock units deliberately with an audited opening conversion. | [D7] |

## Preventive maintenance and inspections

| ID | Selectable outcome | Status / basis | Value / size | What to improve when implementing | Evidence |
|---|---|---|---|---|---|
| **M1** | Multiple recurring maintenance programs per truck | Extend / ETS | High / L | Separate oil, transmission, brakes and other programs; time, mileage or engine-hour intervals; earliest-due rule, template and next-work creation. Existing fleet PM is one mileage/date program. Preview recalculation and never silently reset due dates from unreliable telemetry. | [E13], fresh ETS/REA, [D8] |
| **M2** | Shop inspection findings and a versioned inspection report | Extend / ETS | Medium–High when sold by shop / L | Extend existing weekly fleet inspection/checklist primitives with sectioned results, item photos, repair recommendations and printable reports. Use a reviewed form for any DOT offering; retain corrections as revisions rather than overwriting a signed report. No regulatory equivalence is claimed. | [E5], [D8] |

## Billing and receivables

| ID | Selectable outcome | Status / basis | Value / size | What to improve when implementing | Evidence |
|---|---|---|---|---|---|
| **B1** | Customer transaction ledger, statements and overdue-balance aging | Extend / Mixed | High / L | One account view for invoices, payments, credits and balances; current/1–30/31–60/61–90/90+ buckets with drill-down. Keep imported ETS-owned balances distinct from native collectible debt. Native aging is an improvement beyond ETS, whose guide requires a spreadsheet. | [E14], [D11], [D10] |
| **B2** | Repair-order deposits before the invoice is issued | Extend / ETS | High / L | Record a job-linked deposit, show it on the final settlement and define cancellation/refund/reallocation. Booking payment and invoice credits already exist; neither is a complete RO deposit workflow. Preserve ledger history instead of delete-and-reenter. | [E15], [D2], [D11] |
| **B3** | One fleet remittance allocated across multiple invoices | Extend / ETS | High for fleet billing / L | Enter money received once, suggest allocations, preview remainder and explicitly confirm any credit. DBN has partial/split tenders and credit applications but no comparable single-step multi-invoice allocation UI was found. Separate from provider activation and ETS historical transfer. | [E16], [D11] |

## Analytics and management

| ID | Selectable outcome | Status / basis | Value / size | What to improve when implementing | Evidence |
|---|---|---|---|---|---|
| **A1** | Actual labor cost and defensible job contribution | Extend / ETS | High / L | Effective-date technician cost rates × actual tracked time, parts cost and sublet cost. Preserve cost snapshots and unknown coverage. Reports currently explicitly mark labor cost unavailable; the shop internal billing rate is not each technician's actual cost. This is costing, not payroll. | [E17], [D9], [D10] |
| **A2** | Work-in-progress aging and delay bottlenecks | Missing report / DBN | High / M | Show hours/days awaiting approval, parts, technician or quality review, with drill-down to action. Reuse lifecycle, hold and operation data; add promised-date performance after R1. | [D1], [D10] |
| **A3** | Deferred-work conversion and follow-up value | Missing report / DBN | Medium / M | Track recommended, accepted, completed and still-open work without double-counting conversion. Break out no-estimate work and use the source linkage already shipped. | [D3], [D10] |
| **A4** | Inventory velocity, dead stock and purchasing priorities | Extend / DBN | Medium / M–L | Combine stock movements, actual usage, lead time and open demand to find fast movers, excess stock and stockout risk. Existing valuation/reorder and purchasing views are the base. Recommendations should be explainable, not automatic purchases. | [D6], [D10] |

## Suggested starting choices, not an implementation decision

1. **R1** if dispatch and customer promises cause the most daily friction.
2. **P1 + C1** if inconsistent pricing or missed margin is the main problem. Start with P1, then account defaults.
3. **M1** if recurring fleet work is the main growth/retention opportunity.
4. **B1** if collections and account reconciliation are the bottleneck.
5. **A1** if the immediate question is which jobs actually make money.

Dependencies: C1 parts pricing → P1; P4 complete invoice capture → P3; S1/A2 promised-date views benefit from R1; A1 technician cost → effective-date cost policy; B1/B2/B3/C4 → canonical financial contracts and imported/native ownership boundaries. These are separate selectable outcomes, not a single large release.

## Existing capability: do not rebuild

- Global search across customers, trucks, repair orders and parts.
- Customer contacts; owner/operator/payer relationships; existing customer/fleet/driver portals.
- Service templates, labor/parts packages, required checklists and task completion.
- Recommendation carry-forward and duplicate-safe conversion to operations.
- Operation-level technician assignment, completion, time tracking and internal notes.
- Quote revisions, approval/decline, authorization snapshots, holds/releases, deleted-order restore.
- Customer/truck repair history, search/export, outside-shop service history and private receipts.
- Purchasing demand, supplier sources, PO batches, partial receipts, weighted average cost, cores, vendor returns/credits and inventory activity.
- Workforce attendance/utilization/efficiency and existing sales, tax, fee, parts, inventory, service-type, account revenue and quote-funnel reports.
- Invoice payments, partial/split tenders, credits/refunds and reminders; existing QuickBooks/Stripe/Motive integration code.
- Fleet PM mileage/date scheduling and weekly inspections. Warranty/comeback fields and UI indicators also exist.

**Verify availability rather than calling it missing:** counter-sale flags/backfill, payment/provider activation, QuickBooks mapping, licensed labor-data coverage and role-specific access. Source existence does not establish that every tenant has an enabled and accepted workflow. Customer attachment breadth, warranty recovery and any multi-location consolidation need a focused follow-up before adding a new implementation item.

## Evidence anchors

### DBN current source

- **[D1]** `backend/app/db/models/repair_order.py`, `backend/app/api/v1/endpoints/repair_orders.py`, repair-order frontend workspace. No scheduled-start/promised-finish/bay/key/parking fields in the inspected RO contract; existing completion/hold/release timestamps, warranty linkage and operation workflows present.
- **[D2]** `backend/app/db/models/appointment.py`; `backend/app/api/v1/endpoints/appointments.py` slot generation near line 440. Booking/payment/RO link exists; slot generation is fixed and overlap is not resource-specific.
- **[D3]** `backend/app/db/models/recommended_service.py`; `backend/app/services/recommendation_conversion.py`; `backend/app/services/recommended_work.py`. Recommendation requires an originating RO; resolved/source tracking exists. No independent issue/follow-up/photo contract found.
- **[D4]** `backend/app/db/models/quote.py`, `backend/app/services/pdf_service.py`, quote endpoints and existing order/operation note surfaces. Approval token and revision snapshots exist; signer/signature artifact contract not found.
- **[D5]** `backend/app/db/models/customer.py`, `tenant.py`, `vehicle.py`; `frontend/src/features/customers/CustomerDetailPanel.tsx`. Existing customer tax exemption, auto-approval threshold, fleet flags and shop labor/fee defaults; no customer matrix/rate/terms/credit-limit fields found.
- **[D6]** `backend/app/db/models/inventory.py`, `parts_operations.py`; `backend/app/api/v1/endpoints/parts_operations.py`; `backend/app/services/parts_operations_service.py`; `frontend/src/features/inventory/{PartsInventoryWorkspace,PurchasingWorkspace,PartsOperationsWorkspace,ActivityWorkspace,CounterSalesWorkspace}.tsx`. Supplier aliases, bin/adjustment, demand/PO/receipt/return/core base exists; no matrix, formal count session or non-stock PO expense model found.
- **[D7]** `backend/app/api/v1/endpoints/repair_orders.py:279` `_packages_consumed` and `:311` `_stock_packages_reserved`, with add/update usage paths near 4523 and 4806. Whole packages are intentionally reserved; partial-jug remainders are not tracked.
- **[D8]** `backend/app/db/models/vehicle.py:58`, `backend/app/services/fleet_pm.py`, `backend/app/db/models/fleet.py:95`, fleet scheduling UI. One mileage/date PM pair; fixed weekly inspection item model with attestation and RO linkage.
- **[D9]** `backend/app/db/models/user.py`, mechanic endpoints and time-entry models. Technician time, shifts, utilization and efficiency exist; effective-date per-technician internal cost not found.
- **[D10]** `backend/app/api/v1/endpoints/reports.py`, including explicit `labor_cost_status = unavailable` near lines 1167 and 1280. Accounts analytics represents paid-invoice revenue, not overdue receivables. Existing category reports must not be mistaken for the proposed operational aggregates.
- **[D11]** `backend/app/db/models/invoice_settlement.py`, `backend/app/schemas/invoice_settlement.py`, `backend/app/api/v1/endpoints/invoice_settlements.py`, `frontend/src/features/payments`, customer detail. Payment attempts are invoice-bound; credit application exists. Credit aging near endpoint line 1539 concerns credits owed customers, not unpaid-invoice aging. No staff account statement or single remittance allocation workflow found.
- **[D12]** Existing shop search implementation and bounded source categories; [original audit](ETS_FUNCTIONALITY_AUDIT.md). Invoice/contact aggregate search was explicitly excluded from DB098 scope.

### Official ETS sources

- **[E1]** [Scheduled and due dates](https://support.easytruckshop.io/en/articles/11818999-how-to-set-scheduled-and-due-dates-for-services-estimates).
- **[E2]** [Duplicate a service](https://support.easytruckshop.io/en/articles/11824505-how-to-duplicate-a-service).
- **[E3]** [Recommendations and issues](https://support.easytruckshop.io/en/articles/16515197-recommendations-issues-how-they-work).
- **[E4]** [Estimate signature and authorization](https://support.easytruckshop.io/en/articles/14171620-what-does-the-customer-see-estimates-e-signature-authorization).
- **[E5]** [Inspection workflow](https://support.easytruckshop.io/en/articles/16532503-dot-inspections-how-to-run-an-inspection-from-start-to-finish).
- **[E6]** [Service intake](https://support.easytruckshop.io/en/articles/16515148-service-flow-where-to-create-a-new-service-and-what-to-fill-in) and [service settings](https://support.easytruckshop.io/en/articles/16515152-service-flow-what-each-field-in-service-settings-does); original audit intake observations also cover parking/key fields.
- **[E7]** [Parts price matrix](https://support.easytruckshop.io/en/articles/11664125-using-the-parts-price-matrix).
- **[E8]** [Customer groups](https://support.easytruckshop.io/en/articles/14425711-what-are-customer-groups).
- **[E9]** [Preset fees](https://support.easytruckshop.io/en/articles/16426939-preset-fees-how-to-add-fees-to-a-service-or-parts-sale-original) and [quantity-based fees](https://support.easytruckshop.io/en/articles/16532209-preset-fees-how-to-charge-per-mile-per-tire-or-per-day).
- **[E10]** [Cross-reference and alternate part numbers](https://support.easytruckshop.io/en/articles/12738938-cross-reference-vs-alternate-part-numbers).
- **[E11]** [Other PO expenses](https://support.easytruckshop.io/en/articles/16962466-how-to-add-an-expense-to-a-purchase-order-other-expenses).
- **[E12]** [Purchase-order document scanning](https://support.easytruckshop.io/en/articles/14215442-using-ai-document-scanning-on-purchase-orders).
- **[E13]** [PM intervals](https://support.easytruckshop.io/en/articles/16499786-pm-services-how-intervals-work); hours controls additionally observed in current UI and REA syntax.
- **[E14]** [Receivables and the absence of built-in ETS aging](https://support.easytruckshop.io/en/articles/16739469-who-owes-me-money-getting-your-a-r-and-building-an-aging-report).
- **[E15]** [Prepayment/deposits](https://support.easytruckshop.io/en/articles/16807914-how-do-i-take-a-pre-payment-or-deposit-before-the-invoice-is-finalized).
- **[E16]** [One payment across multiple invoices](https://support.easytruckshop.io/en/articles/16416315-how-to-apply-one-payment-to-multiple-invoices-customer-transactions).
- **[E17]** [Mechanic internal hourly cost](https://support.easytruckshop.io/en/articles/13163454-understanding-mechanic-hourly-pay-rates-profit-visibility).

## Acceptance for the next selected item

Keep desktop information density, compact header/footer and one mobile scroll region. Verify complete desktop and mobile journeys in both Light and Night Shop, including cancel/back, reload, empty/failure states and return context. Include tenant/role negatives for new contracts, snapshot/ledger behavior for prices and money, and independent gates appropriate to actual risk. Keep local, CI, merge, deploy and authenticated production verification as separate evidence. Advance through the selected queue only after closing the current item's required gates; consult the parity tracker before starting work. Unselected items remain backlog.
