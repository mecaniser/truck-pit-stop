# DB-131 / R1 repair-order scheduling

Accountable: Backend & Integrations. Schema/cross-layer workflow: contract-first with independent QA and tenant/migration review. User-selected first outcome in [parity tracker](../ETS_PARITY_TRACKER.md).

## State
Implementation complete; local runtime acceptance and independent review in progress. No PR, merge or deployment claimed yet.

## Acceptance
See [tracker](../ETS_PARITY_TRACKER.md#current-implementation-r1--db-131) and [approved Architecture contract](../contracts/db131-repair-order-scheduling.md).

## Runtime alignment
Preflight in progress. Existing preview5174/API8001 belong to this parity chat but serve the older intentional overlay. Other task owns5173; preserve it. Database is the preserved local `truckpitstop_ets_workflow_parity_20261012`, schema172; direct and proxied readiness pass. Exact source alignment is required before implementation/browser acceptance.

### Aligned and browser-verified — 2026-10-15T18:21:28.535116+00:00
Implementation checkout `ets-checkpoint-merge/truck-pit-stop`, branch `codex/ets-repair-order-scheduling`, HEAD905aaf2c plus contract docs. Frontend PID52743 serves this exact checkout at http://127.0.0.1:5174; API8001 `dieselbridge_api_ets-workflow-parity` now mounts the same checkout/backend at/app. Original preview overlay remains intact, no files overwritten. Other task's5173/8002/8003 services untouched. Existing local configuration reused via its Compose env-file/no-outbound overrides; comparison found zero configured environment changes. Original image was unavailable in image storage; reused cached development imagebde2e27b only after matching requirements SHA256. Database remains `postgres/truckpitstop_ets_workflow_parity_20261012`, schema172, no migration/reseed. Proxy readiness reports database/Redis OK. Signed-in Performance Owner sees the exact branch indicator and loaded21-order repair ledger. This confirms baseline alignment; R1 rendering remains pending implementation.

### Preserved preview schema
Applied additive migration172→173_repair_order_schedule after reviewing nullable UTC date columns, ordering constraint and tenant/promise index. Existing dates remainNULL; no backfill/reseed, provider or tenant flag changes. Preview schema reports173head. Downgrade testing will use a disposable database; rollback of populated preview/production must retain dates.

## Implementation and automated evidence
- Nullable schedule fields, migration173, staff-only schedule editor/API, shop-time/DST validation, optimistic concurrency and staff audit history. No status, timer, money or customer-send changes.
- Shared overdue filter/count/value/paging rules; bounded source joins enrich projections; dashboard date visibility respects exact fleet/mechanic scope.
- Compact header control, full-width single-line queue deadline, search/return context and visible60-second queue/workspace refresh.
- Backend owner:216 focused regressions,7 PostgreSQL cases; disposable base→173→172→173 migration. Logs `/tmp/db131-backend-evidence/`.
- Frontend owner:179 focused tests, TypeScript pass, ESLint zero errors with two confirmed pre-existing hook warnings.320px correction13 schedule tests pass.
- [Independent review](DB131_INDEPENDENT_REVIEW.md): source/privacy checks pass; final runtime gate pending. Review caught dashboard overexposure and stale selected-workspace deadlines; both corrected and independently tested.

## Local runtime acceptance in progress
Synthetic pre-existing `DB115-HOLD-QA` in Performance Lab only; initial dates both null, In Progress, $290, two existing operations. Browser IAB uses supported CDP viewport emulation, not a physical-device claim. Browser timezone overridden to America/Los_Angeles; fields and display remain explicitly America/New_York.
- Save/reload Oct14 08:00→17:00 EDT; overdue queue1/$290; clearing both dates removes queue row and returns0/$0. Search/filter context survives customer workspace and Back.
- Reversed dates rejected. New York spring gap02:30 rejected. Autumn repeated01:30 offers first/second occurrences; second choice persisted as2026-11-01T06:30Z (read-only database confirmation).
- Escape discards draft and returns focus to named Schedule trigger. Named close, Cancel and Clear exercised.
- Two real browser editors: newer18:00 saved, stale19:00 rejected;19:00 draft preserved alongside18:00 saved values, Save disabled until explicit Keep my draft; subsequent save succeeds.
- At320px, actual screenshot caught date AM/PM clipping. Corrected narrow layout moves Clear beside label and gives date field full width.390px save/clear/reload complete; desktop Light snapshot shows compact queue deadline and aligned values.
- Initial `tab.screenshot` after emulation produced host-canvas scaling artifacts; those images are NOT acceptance evidence. Exact-viewport `Page.captureScreenshot` and DOM client/scroll dimensions are used for final receipts in `/tmp/db131-qa/`.
- Still pending: live deadline transition, final Night/landscape screenshots, final independent gate and release.
