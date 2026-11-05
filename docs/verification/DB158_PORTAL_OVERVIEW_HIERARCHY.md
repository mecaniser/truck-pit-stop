# DB-158 portal overview hierarchy

Frontend & UX owns this Fast UI refinement on `codex/portal-overview-hierarchy`, based on `82c95576640cd5027d0d2a30ef232ca86d808216`.

The overview groups attention tasks in one named action section, gives its payable invoice links the existing primary treatment, keeps account/vehicle summaries quieter, labels the outstanding total separately from pending and available amounts, removes duplicate fleet-summary titles, and separates completed-service history with aligned links. Existing invoice arithmetic, eligibility, permissions, scoped routes and APIs are unchanged. Empty/incomplete attention states keep a neutral boundary.

## Verification

- Focused dashboard/context/invoice tests: **52 passed** across three files. Includes named action/history regions, destinations, pending/available/total distinctions, ambiguous vehicle warning/count, unknown balances, stale failed reads, foreign IDs and exact cent arithmetic.
- Changed TSX/test ESLint and `git diff --check`: passed. Production build: passed, with existing bundle-size advisory.
- Real signed-in synthetic customer journey on local frontend/backend: rendered changed overview, invoice/approval/in-progress actions and summaries. Initial fixture has no completed orders or pending payment.
- Separate browser response fixtures add fictional completed services and pending payment to inspect all four sections. Preview screenshots are **illustrative synthetic data**, not production acceptance. Desktop1380 and mobile390/320 contain horizontally; desktop history links align, payment link focus outline exists, history navigation works, foreign-ID view exposes no payment action.
- No payment submitted or customer/provider state changed. Initial history-click probe timed out because the real synthetic account had no history; the representative fixture navigation check subsequently passed. Browser console showed no errors and a development WebSocket teardown warning.

## Local runtime receipt — 2026-11-05, America/New_York

Intended checkout: `/Users/sergio_m1_promax/GitHub/truck-portal-overview`; branch above; base HEAD above; four task files changed during acceptance. Frontend `http://127.0.0.1:5173/portal`, PID43837, working directory `truck-portal-overview/frontend`, Vite proxy target `http://127.0.0.1:8020`. Backend `portal-overview-preview-api`, source mount `truck-portal-overview/backend:/app:ro`, same checkout. Readiness through frontend proxy returned200 with database/Redis ready. Rendered `.cp-overview`, `.cp-attention` and `.cp-history` confirm changed source. **Aligned and browser-verified** for local synthetic acceptance.

Existing fixture runtimes preserved. Earlier API startup attempts rejected older/mismatched fixture schemas before serving. Final database is an isolated clone of the existing synthetic task-first fixture in `portal-overview-pg`, database `portal_overview_current`, migrated only on that clone to current head and schema-preflight passed. Test environment/provider settings retained; live card rails disabled; no provider credentials introduced. The unused EFS clone could not migrate its renamed revision and was not used. No existing database was migrated/reseeded.

Raw browser state is private outside the repository. Local screenshots and browser script are under `output/portal-overview/` and are not committed. Local serving is separate from PR/CI, merge and production release.

Draft PR: https://github.com/mecaniser/truck-pit-stop/pull/799. Current main `21684af1` integrated; append-only CSS conflict resolved by retaining both overview refinements and the booking-field alignment rule.

## Financial statement and vehicle directory refinement — 2026-11-05

User requested stronger differentiation of the two summaries. Account balance now uses a label/value financial statement and an explicit account-wide invoice link. The vehicle section is an unboxed directory with up to three authorized vehicle records, unit/model/plate identity, exact-ID destinations and a compact total count. Selected scope shows only its vehicle; an empty account and colliding identities remain explicit. No records, statuses or API data are invented. Existing primary task button styling stays consistent.

Verification: **55 focused tests passed**, changed TSX/test ESLint passed, production build passed (existing chunk-size advisory), `git diff --check` passed. Real signed-in IAB synthetic fleet account shows three vehicles. Clicking Unit609 opens only that exact vehicle; Home retains scope; View all invoices opens the unscoped account invoice list. Directory keyboard traversal has a solid visible outline. At390px and320px, document width equals viewport width; inspected account/directory layout wraps without clipping. Browser returned to all-vehicle Home and viewport override reset. Updated desktop screenshot: local `output/portal-overview/directory-desktop.png` (fictional local account; not production).

Runtime rechecked at implementation start: branch `codex/portal-overview-hierarchy`, HEAD `ea039aae6d240c4f490d7da77c05039ea7ee85eb` before refinement commit, Vite PID46992/source `truck-portal-overview/frontend`, API container `portal-overview-preview-api`/mount `truck-portal-overview/backend`, proxy5173→8020 readiness200/database+Redis ready. Changed statement/directory rendered directly in the user's open IAB tab. Same isolated cloned synthetic DB and disabled provider settings retained; no restart or migration required in this refinement. **Aligned and browser-verified** at http://127.0.0.1:5173/portal.

Draft PR799 remains the delivery artifact. This is local implementation/verification evidence; protected CI, merge and deployment remain pending.

## Production release and acceptance — November 5, 2026

User approved deployment after reviewing the local overview. PR799 was marked ready and all seven exact-head checks passed on `5dc18df6e8635e7ec93bb66ed2123a9a4d09cedc`, workflow run42085052478. Backend jobs were scoped as unaffected, not represented as rerun backend coverage. Protected squash merge `230381952d3ca5519dada3fbc4efca6b168e9886` completed at18:38:51UTC. Checked and merged frontend trees are identical. No branch protection bypass was used.

Automatic production deployment `0ce53fb0-3a5f-4524-a1e7-606e305d4905` succeeded on that exact merge SHA. `https://www.dieselbridge.com/build-version` matches; readiness reports database/Redis ready; portal HTTP200. Downloaded deployed JS/CSS contain the attention/history sections, financial statement, invoice link and vehicle directory. No forced or duplicate deployment, configuration change or worker action was performed. Rollback reference: prior source `21684af1e2f479c0a1d29b238357836e2813507f`, successful deployment `c3bd6d7d-a332-44ba-ac69-f5f5f3e07d57`.

The initial production session was shop staff; user restored the normal customer session. Actual signed-in customer overview now displays the financial statement, three directory rows with the true seven-vehicle account count, and retained shop-review warnings. Clicking one directory row opens exactly its vehicle. Home preserves that vehicle scope; View all invoices opens the account-wide invoice list. Returning Home restores all-vehicle scope. Recent-history detail links share the same desktop right edge.

Desktop and390/320px phone layouts were inspected. At each phone width, document width equals viewport width. Long vehicle descriptions wrap, the directory and financial summary remain readable, and the mobile navigation remains present. No console errors were reported in the inspected production tab. Temporary viewport override was cleared and the browser left on the normal all-vehicle portal overview. Private desktop/mobile screenshots are stored locally under `pr799-live`; no screenshot, access token, record identifier or raw response is published here.

Displayed outstanding, pending-confirmation and available-to-pay amounts match the predeployment customer overview. This is UI readback evidence, not an independent financial-record audit. No Pay invoice, approval, booking, provider, transfer-reporting or other record-changing action was submitted.

**DB-158 is Done:** implementation, local checks, protected exact-head CI, merge, successful deployment and real signed-in production desktop/mobile acceptance exist. This documentation-only follow-up records those completed release facts; it does not change application code.
