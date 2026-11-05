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
