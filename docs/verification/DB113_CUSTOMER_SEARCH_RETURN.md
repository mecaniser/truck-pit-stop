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

All six protected checks passed on17dfdf74 in run38484443162. PR514 merged asd5c870f1 on2026-10-13 at23:41 UTC; automatic Web deploymentdcf1e242 is building. Signed-in production desktop/mobile recheck pending. ETS parity remains paused until DB-114 also passes.


## Production acceptance — 2026-10-13

- PR514: all six protected checks passed (run38484443162), source17dfdf74; merge **d5c870f1dbae403b9e7e3c8acfc6e65b29012e75**.
- Railway Web deployment **dcf1e242-720a-4682-82c0-ab5e620d572e** SUCCESS at that exact merge; `/health/ready` healthy for database and Redis.
- Fresh signed-in production browser loaded `index-A1RSurpp.js`.
-1280×700 desktop and390×700 touch emulation:77 CARGO search → customer → W900 truck → New repair order (correct truck pressed) → Cancel → customer → directory. Search retained, filtered results retained; no horizontal overflow.
- Changed query to77, used customer-level new-order shortcut, verified no truck implicitly selected, closed draft and returned to directory with the new77 query retained.
- No order/customer mutation submitted; captured console errors empty.
- Local proof: `/tmp/db113-production-desktop.png`, `/tmp/db113-production-mobile.png`. Live business screenshots remain local.
- **DB113 Done.** Physical-device/native-keyboard behavior not claimed. ETS parity still waits for DB114 production acceptance.


### Final combined release recheck

Search cancellation was repeated at1280px and320px against final merge `1c76d805`, successful deployment `53448622`, fresh asset `index-TQ0GnU-d.js`: exact W900 selection, Cancel, Back to customer, Back to Customers with77 CARGO retained. Proof: `/tmp/db113-production-desktop-final.png`, `/tmp/db113-production-320-final.png`. DB114 production acceptance also passed; ETS parity is now unblocked.
