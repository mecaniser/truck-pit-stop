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
