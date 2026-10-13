# DB-113 Customer search return

Accountable: Frontend & UX. Fast UI, no server/API/data changes.

## Acceptance and implementation

- Customer search, results page and sort survive customer/truck → New repair order → Cancel → Back to customer → Back to Customers.
- Existing bill-to/truck selection, route parameters and focus return remain intact.
- Clearing or replacing a search starts at page one; no order is created on cancel.
- Directory context travels only in the existing router return state. It is validated before initialization and is not persisted globally.

## Local evidence — 2026-10-13

- Regression failed before the fix: expected Northline search, received empty string.
- RepairOrdersPage.customer and CustomersPage.workstation:40 passed. Added full route-remount round trip with a non-first results page and subsequent new search.
- Changed-source ESLint, TypeScript/Vite production build and git diff whitespace check passed.
- Runtime aligned: implementation ets-checkpoint-merge, selective owned-file mirror into approved ets-parity-preview5174/API8001; readiness healthy, populated database preserved. Signed-in Performance Owner used.
- Actual desktop1280×700 and touch-emulated390×700: searched Performance Carrier001, opened its C-0001 truck, opened the correctly selected new-order draft, cancelled, returned through truck/customer to the same search. No submit. Mobile screenshot `/tmp/db113-local-mobile.png` shows preserved text and bounded layout.
- Physical mobile device/native keyboard behavior not claimed.

## Release gate

Protected CI, merge/deployment identity and signed-in production desktop/mobile recheck pending. ETS parity remains paused until DB-114 also passes.
