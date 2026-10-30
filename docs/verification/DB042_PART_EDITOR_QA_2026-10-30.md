# DB-042 — Part editor fixes and repeat QA

Date: October 30, 2026, 18:10 EDT. Accountable owner: Frontend & UX. Lane: Fast UI, existing inventory and pricing contracts. Branch: `codex/part-editor-qa-fixes`, based on `a84bbe3981ed991e71cb181e872ec99abb67b440`.

## Result

The four reproduced functional bugs and the wide-layout Cancel CSS conflict are corrected locally. No backend, auth, tenant, migration, pricing policy, invoice or payment writer changed. No production records were changed. This is implementation and synthetic browser acceptance, not full-stack or production release acceptance.

| Finding | Correction | Evidence |
|---|---|---|
| Blank money fields became zero | Nonempty decimal validation; explicit zero remains valid | Cost/selling/core validation tests; explicit-zero payload test; blank-cost browser check makes no write |
| Invalid values silently disappeared from a partial save | Actionable amount/whole-number validation; invalid markup participates in native form validity and leaves the hidden selling price unchanged | Negative cost, invalid core, fractional/empty On order, empty/invalid/<-100% markup regressions; browser invalid quantity/markup checks |
| Reopen used cached values | Wait for successful fresh detail fetch before initializing; keep active drafts intact on later refetch | Fresh name/cost/version regression; failed fetch hides cached form and supports Retry; browser sees Fresh fitting / $20 after external fixture change |
| Old request could close another editor | Disable Cancel during save/photo; scope async completion/error/loading state to editor session | Deferred save, selection change, save-failure and photo-failure regressions; browser pending-save Cancel disabled, failure retains draft and enables recovery |
| Wide Cancel hidden | Apply docked-layout hide rule only when not editing | Before: display:none at container1576px. After: display:flex with44x44px rect at1576px and visible at1280px/1281px; click closes editor and restores Edit focus |

## Automated checks

- Before implementation, the new targeted regression group: **12 failed, 1 passed**, for the expected original bugs. Explicit zero already worked.
- After implementation: inventory **47/47** and pricing configuration **16/16** passed together (**63**).
- Two additional recovery cases (failed fresh fetch/Retry, pending photo failure) passed separately, bringing unique executed passing cases to **65** (49 inventory +16 configuration).
- Changed-source ESLint including the dev fixture: clean with `--max-warnings 0`.
- `npm run build`: TypeScript and production Vite build passed. The dev fixture is absent from `dist/tests`.
- `git diff --check`: passed.
- Existing React Router future flags and outdated Browserslist data warnings remain. Fixture hot updates produced React createRoot warnings during development; fixture disposal was added and the final page reloaded. No application failure was observed during the final browser checks.

## Browser setup and acceptance

Reproducible development-only fixture: `/tests/part-editor-preview.html`. It imports the actual `PartsInventoryWorkspace` and production CSS, uses a synthetic owner and tenant, and replaces Axios's adapter with in-memory handlers. Unexpected requests throw; there is no inventory/provider/backend connection. Test controls simulate an external update, a slow save, and one failing save. Nothing in this fixture changes server authentication or authorization. It is not a substitute for signed-in full-stack acceptance.

Temporary fixture URL: `http://127.0.0.1:5198/tests/part-editor-preview.html`.

Verified in the in-app browser:

1. At1600x1000, workbench1576px: Cancel exists,44x44px, computed display:flex. On baseline source it had display:none.
2. At1304/1305 viewport widths, workbench1280/1281px: Cancel stays visible across the exact80rem boundary.
3. Cancel click closes the editor and restores focus to Edit details; Escape also closes an idle editor.
4. Empty cost: inline validation, Save disabled, no synthetic writes. Fractional On order likewise rejected.
5. Empty markup: visible validation and native validity false. Enter25% and a new name: saves selling_price12.50 with expected_pricing_version1, then closes normally.
6. Simulated external saved name/cost change: reopening displays fresh name and20.00 cost.
7. Simulated save failure: draft remains; actionable error displayed; Cancel usable. Retrying succeeds.
8. Simulated slow save: Saving shown, Cancel disabled until completion.
9. At390x844: validation present, Cancel usable, editor closes, document has no horizontal overflow.

[Wide editor screenshot](db042-part-editor-2026-10-30/wide-editor.png) · [Compact pricing screenshot](db042-part-editor-2026-10-30/compact-editor.png).

## Runtime receipt and limits

Intended implementation checkout is the isolated part-editor-qa-fixes worktree. Shared5173 PID17535 and API8000/docker remain owned by machined-sidebar and were not stopped, repointed, migrated or reseeded. The new worktree has no backend/.env; no secrets were copied or invented. Full application runtime is **blocked/unconfigured**, and signed-in backend acceptance is still required.

The intentional client-only fixture is **source-aligned and browser-verified**, with no backend/database by design: Vite PID44862 serves5198 from this worktree's frontend; process command and cwd were checked. Runtime env stamp identifies base a84bbe39 and branch codex/part-editor-qa-fixes; uncommitted edits were corroborated through rendered new validation and corrected Cancel behavior. This URL must not be described as an aligned full-stack app. Its default Vite API proxy was never used by the fixture; the in-memory adapter handles every app request. No real inventory mutations or payments.

Browser extension actions timed out; switched to the in-app browser for successful interaction QA. Temporary viewport override was restored after testing.

## Release status

Local implementation and synthetic acceptance complete at implementation commit `31eb3dc144cba9c37b98a5084dbf2a04d75d5d55`. [Draft PR705](https://github.com/mecaniser/truck-pit-stop/pull/705) is open; no checks were reported on the draft at creation. Protected CI, merge, deployment and signed-in acceptance remain pending. Do not mark the board item Done or infer production availability from this receipt.
