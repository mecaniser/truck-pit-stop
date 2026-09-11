# DB-048 inline cash tender

Owner: Frontend & UX. Fast UI layout refinement; base `460ae91a`.

Cash shares the staff payment tender radiogroup with configured card, Zelle,
Check and ACH. Selecting it shows the existing full-cash confirmation under the
selector, not a separate card. Other tenders remain visible. The partial amount
and generic submit are absent during cash selection; switching restores them.

No backend/API/migration, accounting/export eligibility, tenant authorization,
historical holds or reservation changes. Customer/guest surfaces receive no cash
control. The cash controller remains mounted through selection changes, retaining
receipt retry identity, note lock and stale-version protection. Tender switching
is disabled while cash confirmation or noncash attempt creation is in flight.

Acceptance evidence 2026-09-10:

- Full-cash9, settlement27 and staff-choice6 tests: **42/42 passed**.
- TypeScript and all four changed TS/TSX files ESLint passed; diff check clean.
- Independent source layout assessment informed common radio/focus semantics,
  wrapping, and preservation of the cash controller across selection changes.
- Mechanical layout scan: no findings.
- Real-component isolated browser fixture at1280 and390: all five options share
  one grid, cash selection hides editable partial amount, full amount and receipt
  confirmation wrap correctly, and switching back restores noncash amount.
  Screenshots: `output/playwright/inline-cash-{desktop,selected-desktop,selected-mobile}.png`
  in the main workspace. API requests blocked; no payment submitted. Only browser
  console error was the temporary fixture's absent favicon.
- Production signed-in browser is temporarily unavailable because the Mac is
  locked. Protected PR checks, deploy identity and signed-in acceptance are tracked
  in the focused PR; this is not yet a production-completion claim.

Rollback: previous frontend image. No schema or financial data changes required.
