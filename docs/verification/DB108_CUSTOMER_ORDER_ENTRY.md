# DB-108: contextual repair-order entry and queue totals

2026-10-13. Owner: Frontend & UX. Standard product lane for a new entry journey
using existing authenticated GET/POST contracts; no backend or schema change.
Source `codex/customer-order-entry`, stacked on PR506. Combined preview remains
`codex/ets-parity-preview` on approved5174/API8001 with existing database retained.

## Acceptance defined before implementation

- Align filtered/work value amount with the right edge of order row amounts.
- Start a repair order from customer and truck records in both workspace hosts.
- Fetch and validate exact existing customer/truck context; preserve chosen
  bill-to customer even when truck ownership differs. Do not auto-create records.
- Missing/inaccessible customer, unrelated truck or failed requests show a
  recoverable error, never a blank draft that conceals the failure.
- Cancel restores the originating workspace; success opens the new order.
- Existing manual customer/truck selection, service application, validation and
  backend tenant/permission checks remain authoritative.
- Failed save retains the draft; repeated clicks while saving cannot submit twice.
- Verify desktop,390px and320px browser journeys with synthetic local fixtures,
  focused automated tests, changed-source lint, build and independent QA.

## Audit

Read-only ETS company → truck → New Service was exercised. The form visibly
retained company, contact and truck. No ETS record was submitted. Four loaded
JavaScript modules were captured through the browser and analyzed with the
approved isolated `rea-agents@6.4.0` web subset. Static results are navigation
evidence only; vendor code stays in `/tmp/dieselbridge-rea-order-entry-20261013`.

## Runtime preflight

New-day receipt: preview6fbd1a64, Vite PID68993/source preview/frontend;
container dieselbridge_api_ets-workflow-parity mounts preview/backend,8001→8000;
database postgres/truckpitstop_ets_workflow_parity_20261012; migration head167;
readiness through5174 healthy for database/Redis. No restart/migration/reseed.
Source branch begins at76aaa3a9; intentionally integrated into combined preview
after focused validation. Browser acceptance and final gates pending.

## Implementation and process improvement

Customer and truck workspaces now offer **New repair order**, including the
embedded workspace inside Shop Work. Existing exact customer and linked-truck
GETs validate context before the existing form opens. Company entry leaves truck
selection deliberate. Ownership never replaces the chosen bill-to customer.
The modal supports keyboard focus containment/Escape; Cancel restores the source
record, filters and initiating action. Failed saves retain inputs and pending
saves disable cancellation and repeated submission. Fresh typeahead mileage is
retained for the preselected truck. No new backend/API/schema/permission contract.

## Final local browser acceptance — 2026-10-13

Authenticated CUA in-app Chromium, Performance Owner / Diesel Bridge Performance
Lab. Tested the running UI, not a static mock. User's browser zoom was preserved;
viewport overrides were adjusted and actual `innerWidth/innerHeight` measured.
These are browser viewport checks, not physical iOS/Android or mobile-keyboard QA.

- **1280×800:** Shop Work and Repair Orders totals share the queue row amount
  edge (summary x=508.9204, row amount x=509.0057; difference0.0853 CSSpx).
  Desktop customer and truck shortcuts open correct context. Embedded Escape
  returns focus to the initiating action; Customers→truck→draft→Escape restores
  the truck, customer query and action focus.
- **Lookup failure/retry:** blocked exact customer request using CDP only in the
  agent QA tab. Visible generic error with Retry/Cancel. Unblocking and Retry
  opens the correct company draft. Customer-only Create correctly requires a
  selected truck and does not create a record.
- **Save failure/retry:** blocked order POST in that QA tab. Visible failure;
  company, selected C-0001 and description retained. Unblocked retry creates
  `PERF-295757AF-000003` / `f8e6f743-6ba7-4d4d-9270-d0c1bd500379`, description
  `QA108 desktop contextual entry`; new order opens directly, correct company,
  C-0001, draft status, $0. No invoice/payment/notification action.
- **390×844:** customer/truck entry, deliberate selection, service select/remove,
  Escape/Cancel, focus trap and origin restoration. Final intake buttons measure
  43.991px (44px rounding), truck55.298px. Form clientWidth=scrollWidth=376;
  document width390. Fresh screenshot after final CSS correction.
- **320×740:** full truck name, scrollable form, wrapping whole footer controls,
  document width320 and final form clientWidth=scrollWidth=306. A real delayed
  POST displayed spinner and disabled Create/Cancel; controls remained fully
  within the viewport. Created `PERF-295757AF-000004` /
  `04687a0f-5801-45d0-be4f-51cc894054e1`, description `QA108 mobile contextual entry`,
  correct company/C-0001, draft $0. New order work area and actions are reachable
  through the existing single-sheet scroll. Final320 Cancel rechecked after CSS.
- Narrow-screen testing exposed footer/mileage overflow and fine-pointer rules
  shrinking service touch targets. Both corrected; full name truck cards use
  one column, hints and footer wrap, intake buttons have44px targets.
- Network blocking/throttling reset after testing. Only the two labeled local
  synthetic orders were created. Existing orders/recommendations were preserved.

Screenshots in source-worktree `output/db108/` (local evidence, not committed):
`desktop-queue-final.png`, `desktop-customer-entry-final.png`,
`desktop-draft.png`, `desktop-created.png`, `mobile-390-draft-final.png`,
`mobile-320-pending.png`, `mobile-320-created.png`, `mobile-320-final.png`,
`mobile-save-error.png`. Final390 failure visibility confirmed: alert at y758–796
in844px viewport, draft retained and Cancel preserved original Shop Work queue.
The error is beside the retry action and announced as an alert.
Temporary QA tab closed and viewport override reset after verification.

## Checks and integration

- Source a24cfb53 (final d36f89a7 affected 8-test file and build rechecked): **92 tests pass** across six focused files; `npm run build`
  passes. Changed-source ESLint has0errors and2unchanged preexisting hook warnings.
- Combined preview c39f5d53 (final product integration7029d4c5):27customer/context integration tests pass, including
  three preexisting global-search tests absent from this focused source branch.
- Independent QA found and returned three edge cases (origin query loss, late
  refresh resetting selected truck, capped vehicle-list lookup); all corrected
  with regressions and exact linked-truck endpoint. See independent QA report.
- Final runtime receipt: Vite PID68993 serves combined-preview/frontend5174;
  API container still mounts combined-preview/backend and exposes loopback8001;
  `/health/ready` via5174 confirms database and Redis healthy. No server restart,
  DB migration/reseed, credentials or5173 ownership change. The Vite startup badge
  retains its startup SHA; current source was confirmed by rendered features.
- Independent QA GO at d36f89a7 / preview7029d4c5. PR/CI handoff follows; no merge/deployment. DB-108 is not release-Done.


## Remaining audit scope

This increment addresses contextual customer/truck intake and queue alignment.
The earlier audit still leaves service-level assignment/completion, staff hold
and resume, scheduling, and maintenance recurrence for separate scoped analysis.
REA's static evidence is partial, not proof of complete ETS parity. Deeper vendor
workflows need direct observation before choosing their DieselBridge contracts.
