# DB-136 / A1 — labor cost policy proposal

Status: proposed for owner review, 2026-10-20. No application implementation, schema migration, rate configuration or financial record change is authorized by this document.

Accountable owner: Backend & Integrations. Architecture completed a read-only source and proposal-fidelity review: GO for owner review only, not implementation. Any implementation needs its finalized API/data contract, sensitive-cost permission design, independent QA/security and normal release gates. This document is the policy proposal, not implementation approval.

## Existing evidence

Source baseline: released main `064db78cccf57be3f26d559972bdecfe3df4e233`.

- `backend/app/db/models/labor.py::Labor` stores billed/book hours, charged hourly rate and line charge. `price_build_service.py` recalculates charge from hours × rate. These are selling-price facts, not technician expense. Sublet `vendor_cost` is a separate whole-line expense.
- `User` has no wage or technician cost-rate field. `Tenant.labor_rate` and `internal_labor_rate` are existing pricing policies; neither establishes a particular technician's actual cost.
- `MechanicTimeSession` stores technician, RO, start/end and optional operation identity snapshots. Current assignment is not historical attribution. `finish_order` summarizes session minutes but does not preserve each technician's cost basis; do not use the summary as a cost ledger.
- Attendance/break sessions and audits exist. They preserve work schedules/timezone, not compensation or paid/unpaid-break policy. Time sessions can be edited/deleted with before/after audits. Auto-midnight, manual, switching and other stop reasons exist.
- `reports.py::get_analytics_profitability` intentionally returns `labor_cost_status="unavailable"`, nullable whole-job margin and parts/sublet contribution from current lines before order discounts. Its hours are billed hours. Existing cash-sales reports use a distinct payment-period basis.

Fresh NC aggregate intake used PostgreSQL REPEATABLE READ READ ONLY at 2026-10-20T18:24:05Z, sole schema `185_callrail_inquiry_main_merge`. No customer/technician identities or amounts are published. Private mode-0600 evidence: `~/.codex/private-audits/db136-labor-cost-intake-20261020/aggregate-intake.json`.

- 3,580 retained ETS orders and 22 retained native-source orders. These are source counts, not a declaration that all native rows are real business activity.
- 38 retained native labor lines: 13 manual, 2 flat-service, 23 repair-operation; only 2 lines have a mechanic assignment. All 38 have positive billed hours. There are 4,597 imported labor lines, which do not prove actual labor time.
- 9 retained RO time sessions link to 7 order identities; after excluding deleted orders, 7 closed sessions cover 6 existing native orders. No RO time session has an operation snapshot. All observed RO durations/tenant links are valid; none exceeds 16 hours. This does not prove that all work was recorded or approved.
- 23 miscellaneous sessions, including 1 active; 20 attendance sessions and 5 break sessions. No overlap among closed same-technician sessions or closed sessions versus closed breaks was observed. Open intervals and attendance coverage still require later eligibility checks.
- 10 native orders have an actual-minutes summary; summary presence is not complete costing evidence.
- 74 native parts usages: 10 lack a unit-cost snapshot; 2 record zero. Imported parts include recorded zeros that cannot establish free stock or reliable current job cost. No retained sublet lines were found in the inspected NC labor cohort.

No historical whole-job profit can be certified from these facts. Business/test eligibility for A1 needs an explicit scope; prior owner classifications were authorized for the read-only B1 view only and must not be silently repurposed as global job classification.

## Recommended V1 policy

1. **Prospective costing.** Activate on an owner-approved date in the shop timezone. Do not assign today's rate to past work, populate missing history or backfill invoices. Historical work remains unavailable/partial until separately reviewed time and historical cost policies exist. A session crossing activation retains an unavailable pre-activation segment; activation cannot retroactively authorize that segment.
2. **Separate approved technician cost.** Maintain tenant + technician + currency + effective interval, approved hourly cost, basis label, approving actor, reason and version. Recommend an owner-declared loaded direct hourly cost for job-management purposes; label it a declared costing basis, not payroll-reconciled expense. Owner can choose base hourly cost instead. Define loaded direct-rate inclusions explicitly (owner-declared direct pay and employment burden); exclude separately reported shop overhead/idle allocation to avoid double counting. No guessed statutory burden, overtime multiplier, salary conversion, billing-rate fallback or default zero.
3. **Exact time calculation.** Eligible closed, nondeleted RO sessions use actual elapsed UTC seconds for the technician who recorded the work. Split at rate boundaries; use Decimal and round monetary aggregates, not each minute. Different technicians' legitimate simultaneous work adds person-time. A single technician's overlaps are held, never double-counted or silently divided among jobs.
4. **Explicit eligibility and holds.** Require exact same-tenant technician/order lineage and a valid covering rate. Open, malformed, overlapping, outside-attendance, break-conflicting or unresolved source sessions remain provisional/review-required. Auto-stopped or manager-corrected records need visible provenance and defined approval before final costing. Never silently clip or invent time. General RO time stays at RO level; do not allocate it to an operation without its recorded identity snapshot.
5. **Separate shop time.** Keep miscellaneous work, attendance-only/idle time and breaks separate in V1. Do not distribute overhead across jobs or infer paid/unpaid treatment. No payroll, wage payment, timecard approval, tax calculation or benefits integration.
6. **Preserve evidence.** A cost calculation references exact source session/audit state, technician-rate version, effective segments and calculation version. Finalized/exported snapshots remain immutable. Corrections create visible superseding cost revisions; an open current view may recalculate with its changed basis disclosed. No invoice, settlement, payment, credit, order status or imported financial fact is rewritten.
7. **Coverage before margin.** Show known recorded direct cost plus costed, unrated and held seconds/counts. Use complete/partial/unavailable/not-applicable states. No timers means unavailable, never zero actual cost. Complete eligible-record coverage does not prove complete time capture; a final whole-job contribution needs an explicit completion/coverage review.
8. **Source and privacy boundaries.** Start with prospectively eligible native business work. ETS history remains source-separated, unsupported historical cost stays unavailable, and the importer remains held. Internal fleet/warranty work may show actual cost without inventing external revenue. Zero-charge jobs must not disappear merely because the existing scatter report selects positive totals. Technician cost detail is owner-only initially; explicitly granted cost access for another role is a later owner decision. Existing admin/report/mechanic/customer/fleet responses must not leak rates or cost snapshots.

## Contribution and reporting basis

Recommended new management metric: **direct job contribution**, not net profit or cash flow.

For a finalized eligible job: recorded net labor + parts + sublet revenue after line discounts and the explicitly allocated order discount, minus recorded direct technician cost, parts usage cost snapshots and sublet vendor cost. Exclude sales tax, customer deposits, payments and credit balances from this revenue basis. Show fees separately in V1 to avoid mixing fee treatment with direct labor contribution. Use the issued/revision-bound financial source where available; unissued estimate/current-line values are a separate provisional view, never realized revenue. No changes to issued financial records are needed.

Before implementation Architecture must specify deterministic order-discount allocation, void/revision source selection, rounding, returns/credits and cost-coverage semantics. Retain the existing cash-sales charts and current-lines component report semantics; add a clearly named/versioned A1 response rather than silently redefining them. Missing labor/parts/sublet expense blocks final combined contribution; show known components and coverage instead of a misleading margin percentage.

## Decisions requested before implementation

- Adopt owner-declared **loaded direct hourly cost** or **base hourly cost**? Recommendation: loaded direct cost, with assumptions labeled and supplied by the owner.
- Approve **prospective-only activation** and provide the intended start date/timezone. Actual per-technician rates must be supplied through the future protected configuration flow, not public docs or chat.
- Approve **owner-only cost visibility** initially and **separate idle/misc/break overhead** in V1. No broad admin access by inheritance.

## Future implementation acceptance

- Tenant/role-negative cases cover rates, sessions, snapshots, APIs, exports and stale cached UI; no cost data leaks through general reports.
- Effective boundaries, midnight/DST, multiple technicians, same-technician overlaps, breaks/attendance, open/auto-stopped/corrected/deleted time, rate gaps and concurrency have deterministic outcomes.
- Billed versus tracked time stays explicit. Missing time/cost stays unknown. No operation allocation without source evidence; no sublet double count.
- Actual time × approved cost reconciles to segments; all discount/revision and component-coverage cases reconcile to the documented contribution basis.
- Existing invoices/payments/settlements/credits/statuses and ETS collector deployment/config/watch exclusions remain unchanged.
- Independent QA/security, focused tests, required CI and actual signed-in Light/Night desktop/mobile acceptance precede Done.

## This intake's verification boundary

Documentation and read-only source/database inspection only. No application code, tests, migration, cost-rate writer, local server, production financial mutation, provider call or collector action was introduced. Local-runtime skill was read; its documentation/read-only exception applies, so no services were started or restarted. Product implementation remains unstarted pending owner policy decisions and the finalized Architecture contract.
