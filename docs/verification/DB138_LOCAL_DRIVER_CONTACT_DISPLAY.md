# DB-138 local driver contact display

Accountable: Frontend & UX. Fast UI lane. State: implementation complete; protected PR and production acceptance pending.

## Scope and acceptance

Remove locally stored contact names/phone sublines and phone call actions from read-only fleet cards, Trips rows, map focus, and truck details. Keep the displayed current driver name and safety score. Preserve contact records, API contracts, driver assignment/edit forms, and provider data.

## Implementation and automated evidence

- Shared current-driver display no longer renders a local alias/phone contact subline.
- Trips overview no longer adds the separate local contact row.
- Map focus and truck details no longer expose `tel:` contact actions.
- Fleet cards and Drivers view use the shared display; edit and assignment forms continue to accept phone values.
- Focused Vitest: 4 files, 62 tests passed (`DriverRecord`, `FleetProximity`, `TruckDetailHarden`, `TripOverview.driver-contact`). Tests assert names/scores remain and phone/alias sublines and `tel:` actions are absent.
- Explicit ESLint on all changed TS/TSX files passed.
- `npm run build` passed, including TypeScript and Vite production build.
- `git diff --check` passed.

## Runtime and release evidence

The production Trips page showed local contact sublines at 2026-10-17 03:35 UTC before this change. The local runtime was not used for browser acceptance because 5173/5177 are owned by other worktrees and port 8000 has no listener; those processes were preserved. Authenticated desktop and compact/mobile production checks, including popover dismissal without opening the underlying truck, remain pending deployment of the reviewed PR. Do not mark DB-138 Done until the exact merged source is deployed and those checks pass.

Branch: `codex/remove-local-driver-contact-lines`. Pull request, six protected checks, merge SHA, and deployment identity will be appended after they exist.
