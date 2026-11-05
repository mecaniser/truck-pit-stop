# DB-159 customer vehicle page action placement

Frontend & UX owns this Fast UI change on `codex/portal-vehicle-header-action`, based on `efd5fd4a`.

Add vehicle moves from immediately below the last vehicle card into the page header beside the vehicle scope control. The existing settings destination is retained. It is the page-level primary action; Book service and View history remain scoped row actions. A narrow mobile override in the shared control layer left-aligns the header action. No API, permissions, data or migration changes.

## Acceptance evidence

- Three new component tests plus existing vehicle-scope/context checks: **21 passed**. Cover one header action, existing creation destination, exact-ID row destinations, empty list and foreign scope denial.
- Changed-source/test ESLint, production build/typecheck/control check and diff check passed. Final CSS rebuilt successfully; existing bundle-size advisory remains.
- Signed-in local synthetic fleet account at1380/390/320px: header precedes list with at least20px separation; no horizontal document overflow; one Add vehicle action; selected vehicle shows one row; creation link navigates to the existing settings tab without submitting a form; foreign scope exposes no vehicle/create action; keyboard focus is visible. Screenshots inspected at desktop and320px. Initial mobile centering from shared control-layer important rules was corrected within that same layer, and computed left alignment passed.
- In-app automation binding failed with `browser.user is unavailable`; verification used the existing dedicated Playwright CLI browser instead. No claim of IAB automation acceptance.

## Runtime receipt — November 5, 2026

Checkout `/Users/sergio_m1_promax/GitHub/truck-portal-overview`, branch above, base HEADefd5fd4a, task edits uncommitted during runtime checks. Frontend5173 PID63651, process working directory in this checkout's frontend; proxy target8020. Backend `portal-overview-preview-api` mounts this checkout's backend read-only. Through-proxy readiness200 with DB/Redis ready. Existing isolated synthetic database/provider settings retained, no migration/reseed. Frontend restarted after branch switch with matching branch/HEAD stamp; rendered header action proves served edits. **Aligned and browser-verified** at http://127.0.0.1:5173/portal/vehicles. Private synthetic session stored outside repository; local screenshot/check artifacts under `output/vehicle-header/`, not committed.

## Related discovery, separate scope

DB-160 records the user's editing-permissions question. Customer Account→Vehicles currently exposes a plate-only editor, despite copy promising additional fields. Source also shows different field restrictions between general and nested customer update routes. No blanket shop-only enforcement claim is made, and no broader editing or permission change is bundled into this UI refinement. Product field policy and independent sensitive-boundary review are required before remediation. No exploit, customer edit or provider mutation was performed.

Local implementation verified; protected PR CI, merge and production deployment remain pending.
