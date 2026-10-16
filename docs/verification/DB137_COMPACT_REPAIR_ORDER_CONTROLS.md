# DB137 compact repair-order controls

Accountable: Frontend & UX. Fast UI lane. State: Done — merged, deployed and production verified. User approved this release before P1 on 2026-10-15.

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
Initial run38801191200 rejected the existing search cancellation test because it used the old placeholder. Locator updated to the stable accessible searchbox name; same-element, retained value and mounted-state assertions remain unchanged. Final-revision CI passed as recorded below.

## Release
[PR539](https://github.com/mecaniser/truck-pit-stop/pull/539) merged 2026-10-15 20:54:17 UTC as `fc92c7b9944a0d07db80399b9f6e1eda13840b87`. Merged tree equals checked `ace37a55db3ec3d7efa0e51cf04f174e693030b9` (`6b6a87cb03808147ac5af9647007cad41ee22dbc`). All six required gates pass in run38801823489: frontend1645; critical backend530 passed/11 skipped; full backend3259 passed/169 skipped; production build, migration graph and browser smoke pass. Final local targeted checks69 plus deleted-order4 pass. An old-run deleted-order timeout passed both focused recheck and unchanged final full CI; no assertion/timeout weakening.

Web deployment `51df3b07-b952-4f97-b993-ae032a95a2d8` succeeded on exact merged `fc92c7b9944a0d07db80399b9f6e1eda13840b87`. Public `/build-version` reports the same SHA (built_at2026-10-15T21:00:07.058Z); `/health/ready` reports ready/databaseOK/RedisOK. No Worker or extra canary gate for this frontend-only change.

Production acceptance completed after the user restored sign-in. Light/Day and Night Shop checked at measured 1280x900,390x844,320x740 and740x400 viewports, with touch emulation for mobile (not physical-device testing). Search by exact order and typed work text, All/Deleted status, Overdue0→1 return, selected-state check, Escape/focus, new-order Cancel, details→open→close and customer→Back retained filters/context. Visible controls remain44px; no horizontal overflow. Deleted-order Restore stays available without unavailable-panel errors. Production console warnings/errors: none. Synthetic `TPS-828ACD84-000056` remains soft-deleted, $0 and unmodified. Restored original Day appearance and viewport/touch settings. DB137 is Done; P1 may now enter implementation.

Production evidence: [Light desktop](db137/production-light-desktop.png), [Night desktop](db137/production-night-desktop.png), [Light phone](db137/production-light-390.png), [Night phone](db137/production-night-390.png), [Night narrow phone](db137/production-night-320.png), [Night landscape](db137/production-night-landscape.png). The Night repair detail's existing light interior is outside this toolbar change; acceptance covers the changed controls and navigation, not a claim that every existing surface has been restyled.

Additional local landscape check used a measured740x400 per-tab viewport: status menu→Deleted reachable, URL selection retained, no horizontal overflow. Cleared temporary local viewport/touch overrides. Native browser viewport capability affects the selected tab; verify `innerWidth/innerHeight` on the target before accepting evidence. CDP screenshot dimensions larger than the underlying in-app surface produced stale compositor tiles; for production use the supported viewport on its selected QA tab before per-tab emulation/capture. The stale baseline capture is not acceptance evidence.
