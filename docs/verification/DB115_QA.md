# DB-115 independent QA gate

Reviewer: fresh QA agent `staff_hold_qa`, no implementation or contract participation. Source: `codex/staff-work-hold`, based on `b318bb94`, uncommitted implementation reviewed on 2026-10-13 local. This review does not authorize merge/deploy and is not production acceptance.

## Final local gate: GO

**GO for the scoped implementation and local runtime acceptance.** No unresolved DB115 QA finding remains. The reviewer independently inspected the implementation, contract and focused tests, ran the checks below, and critically reviewed owner-authored runtime screenshots, database receipts and measured browser evidence. The reviewer did not drive the shared browser or mutate the preview database. Protected PR CI, merge and production release remain separate gates.

## Independently executed checks

- Four frontend files: `StaffHoldDialog`, `PriceBuilderPanel.hold`, `PriceBuilderPanel.pending-feedback`, `RepairOrdersPage.abort`: **100 passed**. `/tmp/db115-independent-qa-frontend.log`.
- Frontend production build (`tsc && vite build`): **passed**. `/tmp/db115-independent-qa-build.log`.
- Final dialog/panel rerun after the completion-guard correction: **17 passed**, including both admin/internal held-while-armed cases. `/tmp/db115-independent-qa-hold-final.log`.
- Backend `test_staff_work_hold`, `test_operation_execution`, `test_repair_order_hold_notifications`, `test_repair_order_workspace_projection`, `test_repair_order_shop_notes`: **98 passed**, including central customer-websocket redaction regressions. `/tmp/db115-independent-qa-backend.log`. Existing SQLAlchemy/Pydantic deprecations only.
- `git diff --check`: passed during review.

The reviewed tests exercise exact timestamp precision, stale and repeated requests, pending duplicate/dismissal guards, failed drafts, invalid success envelopes, authorization/fleet scope, tenant/missing/deleted boundaries, transaction rollback, timer attribution, unaffected other work, preservation of financial/checklist/provenance/attendance snapshots, no automatic restart, mechanic resume compatibility and customer disclosure paths. PostgreSQL race evidence is owner-authored: seven cases passed, inspected in `DB115_BACKEND.md` and the test source; this reviewer has not independently repeated the database races.

Final privacy corrections were source-reviewed: separate/redacted customer websocket payload, existing staff guard before legacy stats queries, and explicit operational-reader allowlist across alternate repair-order reads/history. Owner's affected suite **99 passed** and fresh independent Security's **91 + 2 probe tests passed** are recorded in [backend evidence](DB115_BACKEND.md) and [Security GO](DB115_SECURITY.md). Transaction logic is unchanged since the QA backend run; no additional duplicate full-suite run was necessary. Current frontend uses the already-scoped action-queue/daily-workset rather than legacy stats, so the restricted legacy endpoint removes no observed active frontend workflow.

## Findings and recheck

- **P2, resolved and independently rechecked:** arming admin completion or internal finalization before a hold left an enabled confirmation panel after the order became held (`PriceBuilderPanel.tsx`, original review lines 3006/3039). Existing server guards reject it, but the UI offered an impossible action. Owner added guards to both panels and clears armed state on hold; both new regressions pass independently, including no automatic re-arm after release.
- **Visual concern resolved:** the desktop hold banner inherited a global amber text override with poor contrast in the initial image. Owner changed the banner to an explicit dark brown. Runtime foreground `rgb(120,53,15)` on `rgb(255,251,235)` yields an independently calculated **8.75:1** contrast ratio; the final 390px image is legible.

## Runtime artifacts reviewed

- `/tmp/db115-desktop-held.png`: 1280×700 signed-in synthetic order; dense single-row footer with release, operation progress and technician action; visible hold reason; both operation rows retain assignment and stopped tracked time.
- `/tmp/db115-runtime-held.json` and `/tmp/db115-runtime-released.json`: the same two order timers stop at `2026-10-14T00:31:16.299302+00:00` with reason `hold` and staff actor; unrelated misc timer stays active. Release changes only hold/version state, adds internal history and creates no timers. Both operation assignments/status/version and $290 order total remain unchanged.
- `/tmp/db115-mobile-error.png`: 390px form with retained custom reason and recoverable failure; named dialog/close and intact, reachable action labels. This image alone does not prove the subsequent retry/reload or 320px flow.
- `/tmp/db115-mobile-held.png`: 390px held workspace with legible dark reason banner and one-row release/More footer.
- `/tmp/db115-320-stale.png`: 320px stale dialog retains the custom draft, shows the server conflict and refreshed stale state, disables save, and keeps Cancel/close visible. The two stale messages are redundant but do not block recovery.
- `/tmp/db115-landscape-dialog.png`: 740×400 custom-reason dialog keeps header/close and footer actions visible while the body scrolls to the input; no action-label clipping.
- `/tmp/db115-runtime-final.json`: four accepted holds and four releases, no duplicate stale-request transition; final state released/in progress, $290 unchanged, both original timer stop boundaries preserved. Brake inspection is completed/version 1 and retains its technician across the final hold/release; Steering check remains pending/version 0. The unrelated synthetic timer was stopped later with a distinct `manual` cleanup event, after isolation had been verified.

Final owner browser receipt in [DB115_STAFF_HOLD.md](DB115_STAFF_HOLD.md) covers desktop cancel/hold/release/reload, mobile custom-reason blank guard, exact-request failure and explicit retry, reload, customer return navigation, second-window stale conflict, and operation completion unavailable while held then enabled and successfully saved after release. Recorded bounds: 390px document without horizontal overflow, one 567px workspace scroller, 57px footer at y643; landscape one 254px dialog body over 327px content, 44px buttons at y336–380. Desktop footer remains one 57px row at a 716px order-panel width.

The reviewer independently SHA-256 compared **all 11 changed application files** between source and preview: every file matches [DB115_PREVIEW_MANIFEST.json](DB115_PREVIEW_MANIFEST.json), including final privacy and completion-guard corrections. The owner confirms final direct/proxy readiness and preserved runtime identity after autoreload.

Bounds: these checks establish local browser-emulated desktop/390/320/landscape behavior, not physical-device or native-keyboard behavior. No production journey, merge, deployment or final protected CI pass is claimed. Existing operation-completion history contains technical identifiers; owner recorded that separate next-audit refinement without folding it into DB115 acceptance.
