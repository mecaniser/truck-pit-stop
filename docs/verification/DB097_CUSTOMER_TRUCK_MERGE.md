# DB-097 customer truck merge

2026-10-07. Owner: Frontend & UX. Fast UI lane; existing API contracts only.

The customer dialog omitted `include_unit_matches=true`, always sent `confirm_vin`,
and described every match as a VIN match. The existing backend already accepts
unit matches inside a shared customer/fleet, rejects conflicting VINs, and filters
by tenant. The fix connects that contract without altering backend eligibility.
The preview now counts history from the actual archived record when the server
recommends keeping the other record. Confirmation remains explicit.

## Verification

- Customer merge tests: 4/4 (VIN and unit confirmation payloads, recommended
  survivor/history direction, explicit confirmation, empty candidates, rejected pair).
- Existing customer workstation: 15/15.
- TypeScript and ESLint for changed source/tests passed. Diff check passed.
- Actual component rendered with a synthetic API adapter at
  http://127.0.0.1:5197/output/merge-preview/ . Desktop 1440x1000 and phone
  320x844 checked with Playwright. Missing VIN, Unit 077 candidate, recommendation,
  moved count 2 rather than 9, and unit confirmation rendered. Merge disabled
  before confirmation and enabled afterward. Phone document width 320,
  scrollWidth 320; button width/scrollWidth 233 with nowrap.
- Local screenshots: output/playwright/merge-desktop.png and merge-mobile.png.
  Preview adapter cannot mutate real customer data. No merge submitted in browser.

## Runtime receipt and boundaries

Worktree: /Users/sergio_m1_promax/.codex/worktrees/truck-unit-merge/truck-pit-stop
Branch: codex/truck-unit-merge; base d0311ffd2971bab0b9758eea141e745ed3931122.
Frontend PID 41524 serves this worktree on 5197; HTTP 200 and changed component
rendering verified. API default is localhost:8000; this synthetic preview intercepts
requests in memory. Full-stack runtime is BLOCKED: approved backend/.env absent,
8000 unbound; existing 5173 belongs to another worktree and was preserved.
No DB identity or migrations verified, no credentials copied or migrations run.
A preview favicon 404 is unrelated to the dialog. This is synthetic browser
acceptance, not authenticated API acceptance. Protected CI, authenticated journey,
merge and deployment remain pending. No production records changed.
