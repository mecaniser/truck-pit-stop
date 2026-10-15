# DB137 compact repair-order controls

Accountable: Frontend & UX. Fast UI lane. State: local acceptance passed; protected CI/release pending. User approved this release before P1 on 2026-10-15.

## Acceptance
Full-width search in narrow ledger, grouped status/Overdue, explicit active check, concise count/value row and aligned total. Smaller heading/add control, 44px targets, accessible labels and Escape/focus. Preserve all filters, totals/loading/error states, pagination, row/details/create/cancel, customer and browser Back, daily queue/full-ledger and scope navigation. Wide full-ledger quick statuses remain available. No API/data/auth/migration change.

## Runtime
Branch `codex/compact-repair-order-controls`, baseline `7face2d6` (R1 deployed application `7b3dc4b3` plus release/intake documentation). Vite 5174 PID17589 serves this checkout/frontend, verified branch badge; its owned stale-stamp process was restarted. API8001 Docker mounts the same checkout/backend. Preserved `postgres/truckpitstop_ets_workflow_parity_20261012`, schema173. Backend untouched; no provider/config/data/flag changes. Backend and Vite-proxied readiness: database/Redis healthy.

## Local verification
- TypeScript and changed-source ESLint pass; 53 focused tests pass (40 ledger, 13 schedule). Coverage includes filters, selected state, Escape/focus, totals and unavailable/loading states, pagination, scope, creation and row/details callbacks.
- Actual signed-in Light/Day and Night browser at 1280x900, 390x844, 320x740 and 740x400. Mobile is browser emulation, not physical-device testing.
- DB115 synthetic order: search typed character by character, In Progress, Overdue on/off (1/$290 versus 0/$0), wide Deleted and dropdown options, Escape/focus, details/open/close, new-order cancellation retaining search/status, customer return, and daily All overdue work transition retaining selected identity all pass. No business data mutated.
- Mobile inspection found existing full-ledger grid specificity forcing three columns and placing money into a zero-width track. Scoped responsive rules now keep identity/money side by side, work request across the row, and a separate 44px Details disclosure below. Confirmed no page horizontal overflow and readable date/amount.
- Original local Night appearance and temporary viewport restored.

Evidence: [Light desktop](db137/local-light-desktop.png), [Night phone](db137/local-night-390.png), [Light narrow phone](db137/local-light-320.png), [wide filters/empty](db137/local-light-wide-empty.png).

## CI correction
Initial run38801191200 rejected the existing search cancellation test because it used the old placeholder. Locator updated to the stable accessible searchbox name; same-element, retained value and mounted-state assertions remain unchanged. Final-revision CI must pass.

## Release
Protected CI, merge, exact Web deployment and production Light/Night desktop/mobile acceptance pending. P1 remains contract-only until this release passes.
