# DB-115 production release

2026-10-13 America/New_York. User explicitly authorized finishing CI, merging and deploying PR516, then production desktop/mobile hold/release verification before continuing ETS parity. Backend & Integrations remains the item owner; Release & Reliability owns this release handoff. Independent local QA/Security GO is recorded separately.

## Release acceptance

- All six protected checks pass on exact PR head `694e7aa5ac7cee9504403dcf6234aa08ba4d2f20`; merge the checked head without bypassing protection.
- Record merge SHA, Railway Web deployment ID/status/SHA, readiness and browser-loaded asset identity. No migration is introduced.
- Use a clearly identified synthetic production customer/vehicle/order with no real contact details, no technician assignment and no charge or invoice. Confirm desktop hold reason, Cancel/Escape, save/reload, release/reload and internal history. Confirm mobile reason entry, retained failed draft/stale protection where safe, visible action controls and scroll/overflow bounds.
- Verify release starts no timers and preserves order state/price; do not interfere with real mechanic work. Multi-technician atomic stop/race cases have local real-database evidence; do not claim those as live multi-technician tests.
- Clean up the agent-created QA order through the application's recoverable deletion flow after acceptance. Preserve audit evidence; no permanent deletion.
- Independent QA reviews the production evidence before marking DB115 Done. Physical-device/native-keyboard coverage is not implied by browser emulation.

## Rollback

Prior healthy production Web deployment: `53448622-82bd-4f19-a4ce-b53de71cefec`, source `1c76d805079c6225e0d4af74a43cb24be471d591`. Stop acceptance on unexpected timer changes, internal reason disclosure, stale/failed writes reported as success or unusable controls. No schema reversal is needed; preserve hold history and investigate/revert through the protected branch workflow if required.

## Source and deployment

All six protected checks passed on exact head `694e7aa5ac7cee9504403dcf6234aa08ba4d2f20`, [CI run 38492057105](https://github.com/mecaniser/truck-pit-stop/actions/runs/38492057105). Full backend: 2928 passed, 132 skipped, 78 warnings in 921.67 seconds. PR516 merged without bypass at 2026-10-14 01:04:55 UTC as `2461084e45d77cc3e84d2d77e76fe55939079c12`; checked-head and merge trees are identical (`1201bbab4bd0b7788d324a78147fdc43f4172a88`).

Automatic Web deployment `04a94deb-08de-43f4-9616-3dddea3dcce9` reached **SUCCESS** on that exact main merge. Application startup completed at 01:07:52 UTC. Public `/health` is alive; `/health/ready` is ready with database and Redis both ok. Fresh signed-in production page loaded `https://www.dieselbridge.com/assets/index-0SQE4SMf.js`. Independent QA separately confirmed GitHub checks/merge/tree and Railway deployment/readiness. No migration added; automatic predeploy remains unchanged.

## Production fixture and scope

All interactions used the actual signed-in production UI in the Codex in-app Chromium browser, active Truck Pit Stop shop. The dedicated QA fixture was created through New Repair Order with no catalog services, phone, actual VIN or real customer email:

- Customer `3425eb75-fb47-4581-bc2d-ba78f69b8b2d`: **DB115 Production QA — not customer work**, synthetic `db115-verification@example.invalid`.
- Vehicle `64aec3ce-cb8a-4149-b804-0fccf53fa488`: unit **DB115-QA**, model **QA ONLY — no physical vehicle**.
- Order `bce9b62b-a7e3-4ba9-a740-6ced6857e9b3`, **TPS-828ACD84-000056**. Description explicitly identifies the test and excludes customer work, technician assignment, payment and invoice.
- Owner's **Start without a technician** action used `override-start-work` (HTTP200). No mechanic assignment/start-work, attendance, invoice, payment, estimate-send or customer-notification action was taken. Setup endpoint implementations were inspected before use; these synthetic create/override flows do not send customer email/SMS.

Initial and final workspace readbacks: in_progress, assignee null, parts/labor/total $0, work_completed_at null, actual_tracked_minutes null, no invoice. Both holds returned stopped_sessions_count 0. Both releases returned cleared hold/held_at and stopped_sessions_count 0. This proves the saved hold transitions and preserved visible/workspace state; stopped_sessions_count is **not** a timer-start count. No production database timer-count query or live multi-technician test was performed. No automatic timer start was observed in the UI; the no-restart invariant and multi-technician atomic-stop behavior retain the local PostgreSQL/independent-test evidence in DB115_BACKEND.md and DB115_QA.md.

## Changed journey acceptance

**Desktop 1280×700:** Hold dialog is named, Escape and Cancel dismiss without a transition. Default Waiting for parts saved at `2026-10-14T01:08:29.213395Z` (HTTP200), displaying the On Hold badge/reason and hiding Mark Completed. Reload retained the hold; release dialog displayed the saved reason and explicit no-automatic-timer message. Release Cancel preserved the hold. Accepted release at `01:08:48.792950Z` (HTTP200) survived reload and restored Mark Completed. History displayed readable actor/reason for both transitions. $0 and unassigned shop-managed status unchanged.

**Mobile 390×700 touch emulation:** More → Put on hold opens the same dialog. Other reason with an empty draft disables submission. Browser-side blocking of only this fixture's exact staff-hold URL produced the recoverable failure; custom text remained intact, no false success or automatic replay. The block was cleared, and explicit retry saved **DB115 QA: waiting for inspection confirmation** at `01:09:56.609391Z` (HTTP200). Reload preserved the custom reason and direct footer Release hold. Settled document is 390×700 with no horizontal document overflow; one workspace vertical scroller (567px viewport / 713px content), footer 57px at y643.

**Narrow mobile 320×700:** Release dialog, named Close, Cancel and Release hold all fit. Dialog action controls are 44px tall, labels intact. Accepted release at `01:10:29.275481Z` (HTTP200) survived reload; Complete reappeared, Release hold disappeared, and hold/held_at remained null.

**Landscape 740×400 touch emulation:** Custom reason draft can be entered and read. Dialog has one 254px body scroller over 327px content; close is y20/44px and both bottom actions y336/44px, fully inside the viewport. Named Close dismissed the unsaved landscape draft. No extra history event resulted.

Final history before cleanup contains exactly six events: creation, admin start override, two holds, two releases. Cancel, Escape, failed request and abandoned landscape draft did not add transitions. Final workspace readback preserves the $0/unassigned/in_progress baseline. No console errors were captured during the changed hold/release journey. Stale-version rejection was covered by prior local browser/database tests; production stale/conflict injection was not repeated.

## Cleanup and separate follow-up

The released QA order was soft-deleted through the visible, explicitly recoverable Delete order flow (HTTP204). Readback confirms `deleted_at: 2026-10-14T01:11:34.337869Z`, hold_reason null and total $0. It is absent from active DB115-filtered orders and present in Deleted. A fresh load exposes **Restore order** and the actor/time of deletion; nothing was permanently deleted. The clearly labeled synthetic customer and vehicle remain, with zero order value, to retain provenance without irreversible cleanup.

Cleanup exposed a separate existing Deleted-view defect: immediate reopening after soft deletion used the legacy shell without Restore until reload, and deleted-order checklist/recommendation/notes/quote requests return404 with error panels. PR516 changes RepairOrdersPage only by supplying workHoldOrder; deleted selection/fetch behavior is outside this change. This is recorded as **DB116**, owned by Frontend & UX, to address before another parity feature. Do not claim the entire application or Deleted workflow is error-free. This does not invalidate the completed active-order hold/release checks.

## Artifacts

- `/tmp/db115-production-desktop-held.png`
- `/tmp/db115-production-mobile-error.png`
- `/tmp/db115-production-mobile-held.png`
- `/tmp/db115-production-320-release.png`
- `/tmp/db115-production-landscape-dialog.png`
- `/tmp/db115-production-cleanup.png` (initial Deleted-view defect)
- `/tmp/db115-production-cleanup-restorable.png` (persisted deletion and Restore control after reload)
- `/tmp/db115-production-fixture.json`, `db115-production-before.json`, `db115-production-released-workspace.json`, `db115-production-cleanup.json`
- `/tmp/db115-production-desktop-hold.json`, `db115-production-desktop-release.json`, `db115-production-mobile-hold.json`, `db115-production-mobile-release.json`, `db115-production-history.txt`
- `/tmp/db115-railway-deployed.json`, `/tmp/db115-production-ready.json`, `/tmp/db115-independent-production-deployment.json`

Browser viewport/touch/request-block overrides were cleared after verification, and the temporary production QA tab was closed. These are actual production browser journeys at desktop/mobile dimensions, **not physical-device or native mobile-keyboard tests**. Independent post-release QA **GO** is recorded in DB115_QA.md: no unresolved DB115 finding, independently verified source/release identity and critical review of the production UI/readback evidence. DB115 is Done; DB116 is the next existing-UI correction before another parity feature.
