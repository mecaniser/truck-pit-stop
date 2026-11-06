# Customer portal colors and motion — PR816 release

Frontend & UX accountable; Fast UI lane. User approved merge/deployment and read-only desktop/mobile production verification on 2026-11-06. No customer/provider/financial mutations are authorized.

## Protected source and merge

- PR: https://github.com/mecaniser/truck-pit-stop/pull/816
- Final checked head: `aab9166a00617538acf07bbc42c7a4f62b79d6f1`.
- All seven checks pass: https://github.com/mecaniser/truck-pit-stop/actions/runs/42174549839 . Frontend critical/full suites, build and Playwright smoke ran; backend gates use existing frontend-only classification.
- Squash merge: `fb76fa6420b7041978ea8485b52833059a511b1a`, merged 2026-11-06 at06:42:46UTC without protection bypass.
- Merged application/configuration tree matches the checked head. Eleven portal UI/style/test/board files; no preview pages/comparison harness, read-only adapter, runtime configuration, private customer records or screenshots included.
- Local owner verification:287 tests across27 files, build/control checks, baseline-aware lint; dark/light actual dialog component and390px presentation pass. Original parallel dirty-marker test flake is retained as prior evidence; CI-worker-settings run and exact-head CI pass without weakening its assertion.

## Deployment and readiness

- Automatic Railway production Web deployment: `2ef47c3d-c986-46a7-b698-b6f3a79c0c6a`, SUCCESS, source `fb76fa6420b7041978ea8485b52833059a511b1a` on main.
- Public www/API build stamps both match the merge; built2026-11-06T06:45:03.910Z.
- `/health/ready`: ready, database and Redis healthy.
- Prior successful Web deployment: `4951daec-f8ca-4428-b0f7-c8f7ead35560`, source36980c15. Rollback target only; rollback was not invoked.
- Existing deployment hooks/configuration unchanged; no manual migrations, provider operations, financial actions or data corrections performed.

## Production acceptance

Signed-in production acceptance completed in the in-app browser (browser5, tab5), customer role, on the exact deployed merge. Desktop1307px and phone390px were checked.

- Home/navy canvas computed `rgb(13,26,51)`; secondary action hover settles to `rgb(36,62,96)` with Dusk Blue border `rgb(143,180,227)`.
- Home, Repairs, Invoices, Vehicles and Account destinations render. Keyboard navigation selects Vehicles immediately. Existing Account Save changes remains disabled while pristine; saved settings were left unchanged.
- Customer invoice/payment detail renders existing paused/checkout/shop-review states at desktop and390px without horizontal overflow. Payment/provider controls were not submitted, cancelled, refreshed or otherwise invoked by this verifier.
- Main navigation, account and invoice content are contained at390px; mobile section navigation is present. No console errors observed in the final customer pass. The viewport is restored to its original desktop dimensions1307×1313; browser5/tab5 remains at https://www.dieselbridge.com/portal in the customer account. Browser ownership was released to the PR817 owner; no further browser interaction is performed by this verifier.
- Dialog behavior has local dark/light component/browser evidence and passing regressions; no production customer field was edited to force an unsaved-changes dialog during this read-only acceptance.
- Shared session/view changes and conflicting browser observations interrupted initial checks. Coordination established exclusive customer verification, and the browser connection was renewed before the final bounded pass. No payment/save/cancel-checkout/refresh-payment control was invoked by this verifier. User/coordinator authentication restoration is distinct from verifier actions and was not a customer data mutation test.

## Separate existing issue — DB-PORTAL-SERVICE-FILTERS

At390px, Services → All services exposes an existing category row wider than its container (observed main client375px/scroll965px). The unchanged non-wrapping `.cp-category-nav` layout predates PR816; the palette PR changes its colors, not wrapping/layout. This is recorded as a separate Frontend & UX follow-up: wrap category controls or contain intentional horizontal scrolling, retain keyboard/touch access, and verify320/390px without clipping. No unrelated production patch or additional merge was performed. This limitation is disclosed; it is not claimed fixed by the palette release.

Screenshots and any private browser evidence remain outside Git. This document records implementation/deployment evidence, not payment/provider readiness or business outcome verification.

## Evidence publication

Release receipt is prepared on `codex/portal-colors-release-evidence`. Documentation-only publication must not be merged ahead of the active PR818 board update; the coordinator requested deferral to avoid another board-conflict/CI cycle. This does not delay or alter the already successful application deployment. No additional production code or release is bundled in this receipt.
