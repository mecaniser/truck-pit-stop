# DB-131 / R1 repair-order scheduling

Accountable: Backend & Integrations. Schema/cross-layer workflow: contract-first with independent QA and tenant/migration review. User-selected first outcome in [parity tracker](../ETS_PARITY_TRACKER.md).

## State
Implementation, local runtime acceptance, independent QA/Security and all six protected CI checks passed. PR #538 merged as `7b3dc4b30a52e6880580f1511716afc38dbd1ba2` at 2026-10-15T19:41:35Z. The exact merge is deployed and authenticated production acceptance passed; independent QA/Security/production closure is GO. R1/DB-131 is Done.

## Acceptance
See [tracker](../ETS_PARITY_TRACKER.md#completed-r1--db-131) and [approved Architecture contract](../contracts/db131-repair-order-scheduling.md).

## Runtime alignment
Initial preflight (superseded by the aligned receipt below): existing preview5174/API8001 belong to this parity chat but serve the older intentional overlay. Other task owns5173; preserve it. Database is the preserved local `truckpitstop_ets_workflow_parity_20261012`, schema172; direct and proxied readiness pass. Exact source alignment is required before implementation/browser acceptance.

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
- [Independent review](DB131_INDEPENDENT_REVIEW.md): source/privacy and final local runtime gates pass. Review caught dashboard overexposure and stale selected-workspace deadlines; both corrected and independently tested.

## Completed local runtime acceptance
Synthetic pre-existing `DB115-HOLD-QA` in Performance Lab only; initial dates both null, In Progress, $290, two existing operations. Browser IAB uses supported CDP viewport emulation, not a physical-device claim. Browser timezone overridden to America/Los_Angeles; fields and display remain explicitly America/New_York.
- Save/reload Oct14 08:00→17:00 EDT; overdue queue1/$290; clearing both dates removes queue row and returns0/$0. Search/filter context survives customer workspace and Back.
- Reversed dates rejected. New York spring gap02:30 rejected. Autumn repeated01:30 offers first/second occurrences; second choice persisted as2026-11-01T06:30Z (read-only database confirmation).
- Escape discards draft and returns focus to named Schedule trigger. Named close, Cancel and Clear exercised.
- Two real browser editors: newer18:00 saved, stale19:00 rejected;19:00 draft preserved alongside18:00 saved values, Save disabled until explicit Keep my draft; subsequent save succeeds.
- At320px, actual screenshot caught date AM/PM clipping. Corrected narrow layout moves Clear beside label and gives date field full width.390px save/clear/reload complete; desktop Light snapshot shows compact queue deadline and aligned values.
- Initial `tab.screenshot` after emulation produced host-canvas scaling artifacts; those images are NOT acceptance evidence. Exact-viewport `Page.captureScreenshot` and DOM client/scroll dimensions are used for final receipts in `/tmp/db131-qa/`.
- Live deadline: saved Oct15 14:40 EDT; observed Due with0/$0 before deadline, then Overdue in selected workspace and queue1/$290 without reload. Tab remained visibility=visible; bringing the test tab to front is also an allowed focus refresh. Interval-specific behavior is separately covered by the page clock test.
- Both Light and Night: desktop1280×800, portrait390×844, narrow320×568 and landscape740×400 inspected; layoutfits, namedclose/Cancel/Save accessible. Landscape panel448×328 with Save44px high, inside400px viewport.320px full-width date controls visible after reopening.
- Night landscape edited and saved, Night phone cleared/reloaded. Invoiced DB110-DESKTOP exposes disabled dates/Clear and noSave. Phoneclose retainssearch=DB110-DESKTOP.
- From dashboardOnFloor queue, All overdue work removes boundedqueue and routes to full ledger withoverdue=true while preservingselectedorder.
- Multipage count/value/search semantics are covered by real PostgreSQL fixtures and frontend page tests, not a claimed25-row browser fixture.
- Both localfixture dates restorednull and verifiedafterreload; status/total/operations unchanged. Original Night appearance restored. Browser timezone and viewport overrides cleared. Final QA has no consoleerrors; earlier18:25hot-reload errors predatefrozen18:34candidate.
- Local acceptance was followed by the independent local GO, protected CI and production acceptance recorded below.

## Protected CI and merge
PR [538](https://github.com/mecaniser/truck-pit-stop/pull/538), independently reviewed application candidate `e12994da`; final candidate `21546789d591e214ed2a579d6e43c5e8f80d17d2` adds documentation/screenshots only. All six required checks passed in [run 38788259786](https://github.com/mecaniser/truck-pit-stop/actions/runs/38788259786). Actual logs confirm 1,644 frontend tests passed across 166 files; critical backend 530 passed/11 skipped; full backend 3,259 passed/169 skipped. Migration graph, production frontend build and Playwright smoke passed. Real PostgreSQL schedule tests are separately recorded above; CI skips are not claimed as executions. No protection bypass or unrelated-run cancellation.

Squash merge `7b3dc4b30a52e6880580f1511716afc38dbd1ba2` at 2026-10-15T19:41:35Z. A full Git tree diff from tested `21546789` to the merge is empty (tree `d222f84b0aaa0299bfa8dcb491e55170cca0c8ca`). Deployment and production gates are recorded below.

## Durable visual evidence
Synthetic QA content only. Exact viewport captures (not physical-device screenshots):
- [Light desktop](db131/light-desktop.png), [Light320 editor](db131/light-320.png)
- [Night desktop](db131/night-desktop.png), [Night390 editor](db131/night-390.png), [Night320 editor](db131/night-320.png), [Night landscape](db131/night-landscape.png)


## Production release — 2026-10-15

- Exact merge `7b3dc4b30a52e6880580f1511716afc38dbd1ba2`: Web `1638efbd-d4ec-4047-ace8-717452930791` and Worker `ca80a3a3-86dc-4738-bb36-87446d656a50` both SUCCESS. Public `/build-version` reports that SHA, built at 19:46:47Z. `/health` and `/health/ready` return 200, database and Redis OK.
- Independent release checks confirm Web pre-deploy upgraded 172→173 at 19:49:13Z before application startup at 19:49:35Z. Read-only SQL confirms `173_repair_order_schedule`, both nullable timezone-aware columns, ordering constraint and tenant/promise index. Worker overlap inspection found no missing-column errors. Keep additive schema on any application rollback.
- Tested source and merged tree equality, exact protected CI and independent observations are recorded in [independent receipt](DB131_INDEPENDENT_REVIEW.md).

### Production acceptance and restoration

Authenticated Chromium through the supported in-app browser. Viewports are browser emulation, **not physical-device or soft-keyboard certification**. Both Light/Day Shop and Night Shop inspected at 1280×800, 390×844, 320×568 and 740×400. Dates and AM/PM remain visible; 320px inputs and Clear/Close/Cancel/Save controls measured 44px high, within the viewport; document width/scroll width both 320. Landscape panel and footer fit within 400px. Existing light repair-order work sheet in Night Shop is intentional.

Only business-record writes used existing synthetic order `TPS-828ACD84-000056` / `bce9b62b-a7e3-4ba9-a740-6ced6857e9b3`, tenant `828acd84-38bf-4a66-8fa1-cdf076f4e241`, customer `3425eb75-fb47-4581-bc2d-ba78f69b8b2d` (DB115 Production QA — not customer work), vehicle `64aec3ce-cb8a-4149-b804-0fccf53fa488` (DB115-QA / no physical vehicle). Normal recoverable Restore/Delete used to return it to its original deleted state. Baseline: underlying In Progress, $0, one pre-existing operation, zero invoices, no technician/hold/release; work_started_at `2026-10-14T01:05:50.048351Z`, no completed/tracked timestamp; both new dates null. No price, timer, operation, assignment, invoice, payment or communication mutation.

- **Desktop Day:** start Oct14 08:00 and finish 17:00 saved and reloaded in America/New_York. Past promise showed Overdue in workspace and one-row filtered queue; count/value 1/$0. Invalid finish07:00 rejected with draft retained; Escape discarded it and restored focus to named Schedule control. Named Close also verified.
- **Concurrent editors:** first draft19:00, second editor saved18:00. First save rejected, retained19:00 and showed saved18:00; Save disabled until explicit Keep my draft. Explicit retry succeeded. Clear start then preserved19:00 on reopen.
- **Day phone/narrow/landscape:** 390px start09:00 saved and reloaded with finish19:00. 320px complete date text and44px targets verified. Landscape Clear both/Save/reload returned null/null; overdue queue became0/$0.
- **Night:** desktop08:00→17:00 save/readback; 320px Clear start/Save preserved17:00 finish; landscape Clear finish/Save/reload returnednull/null. 390px finish-only18:00 saved and survived full reload. Native browser input automation required focusing the actual date segment and ArrowUp/Down after fill; attempts that changed DOM value without the React draft were not counted as successful edits. Final evidence uses matching draft/DOM values followed by saved reload, not synthetic event/API writes.
- **Navigation:** customer workspace→Back retained searchDB115, overdue and selected order; closing and browserBack restored the same order/filter. Dashboard On Floor→All overdue work opened the full repair ledger, removed boundedqueue and preservedselected/search/overdue. One-row transition is production evidence; >25-row/role/tenant proof remains the accepted real PostgreSQL and automated evidence, not a claimed production mass-fixture run.
- **Terminal behavior:** existing completed ETS order inspected read-only: explicit read-only notice, disabled dates/Clear, noSave. No lifecycle change or business write to that order.
- **Cleanup:** final dates cleared and confirmednull/null afterreload, QA order soft-deleted again at15:56EDT, reopening showedDeleted andRestore. Normal audit entries and updated deletion/version timestamps remain. Day Shop restored throughAppearance; temporaryviewport/touch/page-scale overrides removed. Final browserconsoleerrors `[]`. Independent invariant comparison follows in the independent receipt.

Production captures: [Day desktop](db131/production-light-desktop.png), [Day390](db131/production-light-390.png), [Day320](db131/production-light-320.png), [Day landscape](db131/production-light-landscape.png), [Night desktop](db131/production-night-desktop.png), [Night390](db131/production-night-390.png), [Night320](db131/production-night-320.png), [Night landscape](db131/production-night-landscape.png).


### Independent closure
Independent QA/Security/production closure GO on 2026-10-15. Read-only final comparison confirmed all17 fixture identity/status/money/operation/timing/invoice/release/hold/assignment invariants unchanged, null schedule and recovered soft-deleted state; only expected version/deletion timestamps advanced. Exact deployed build and readiness remained healthy; zero Web HTTP5xx in the startup-through19:58Z observation window. All eight durable screenshots byte-match inspected originals. [Independent receipt](DB131_INDEPENDENT_REVIEW.md). R1 checkbox completed; P1 contract intake begins next.
