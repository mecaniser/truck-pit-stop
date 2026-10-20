# DB-VOID-002 local review

Owner: Frontend & UX. Lane: Fast UI. Status: Local review; not released.
Timestamp: 2026-10-20T14:42:23-04:00.
Branch: `codex/void-order-dialog`, base `064db78cccf57be3f26d559972bdecfe3df4e233`; task changes uncommitted.

## Outcome and contract

The native invoice card exposes **Void entire order** for the existing owner/admin override. A compact Headless UI dialog names the order and invoice, labels the reason/password, and states that the order is cancelled while the invoice is voided and history retained. The existing invoice correction action is labeled **Revise invoice**; its existing mutation still voids the unpaid invoice and reopens the order for revision. No API, authorization, tenant, payment, data-model, migration, dependency, or provider behavior changes.

Protected orders no longer expose the ineffective Delete/danger-sheet entry. Draft Delete and deleted-order Restore remain reachable. Imported history gains no native void action. The dialog validates a trimmed 3–1000 character reason and password, prevents duplicate submission and dismissal during a pending request, traps keyboard focus, returns focus on dismissal, clears fields when abandoned, retains the reason after rejection, and clears the password after an attempt. Server-authoritative errors remain visible; no automatic retry was added. Success retains the existing cache refresh, workspace closure, and dismissible order-number confirmation.

## Verification

- Four focused suites: 108/108 passed (`RepairOrdersPage.force-void`, `RepairOrdersPage.void-revision`, `RepairOrdersPage.abort`, `PriceBuilderPanel.pending-feedback`). Final focused void rerun: 12/12 passed after the dialog root visibility correction.
- Production build including TypeScript: passed. Changed-source ESLint: zero errors, two existing page hook dependency warnings (lines 1147 and 1434).
- New dialog Impeccable detector: `[]`. Diff whitespace check: passed.
- Playwright CLI with actual page/components and browser-only synthetic owner/receptionist/paid fixtures: desktop 1440x1000 and compact 390x844 passed; reduced viewport height 390x500 retains reachable cancellation. Verified labels, initial focus, forward/reverse focus containment, Escape without closing the order, focus return, validation, password rejection, reason retention/password clearing, cancellation reset, success confirmation/closure, role visibility, and the paid-invoice revision guard.
- Browser check reports zero page errors and zero real API requests. Existing React Router future warnings remain. Preview intercepts all HTTP API calls with a local Axios adapter and replaces its WebSocket; fixture submission changes only browser memory.
- Captures: `output/playwright/void-order-dialog/desktop-invoice.png`, `desktop-dialog.png`, `mobile-dialog.png`. Browser check and logs are in the same output area and `output/void-order-dialog/`.

## Local runtime receipt

Frontend **aligned and browser-verified with fixtures**: `http://127.0.0.1:5173/local-void-preview.html`, listener PID `20817`, source/cwd `/Users/sergio_m1_promax/.codex/worktrees/void-order-dialog/truck-pit-stop/frontend`. Served changed module contains `Void entire order?`; process source and branch agree. Preview HTML/TSX are local review scaffolding outside `src`, excluded from the production build and intended delivery diff.

Full frontend/backend runtime is **blocked**. Controller dry-run found repository migration `185_callrail_inquiry_main_merge` versus configured local database `truckpitstop_db048_local_e2e_20260912` revision `148_elis_outcome_source`. No service switch, database migration, reseed, payment, provider call, or financial state mutation was performed. Existing canonical backend configuration and Python runtime are referenced through local ignored symlinks rather than copied. Port 8000 has no task-owned backend. Existing other local APIs were preserved.

Local serving and fixture acceptance do not establish authenticated full-stack or production behavior. No PR, merge, or deployment in this local-review stage.

## Compact invoice header follow-up — 2026-10-20T14:46:02-04:00

Removed the separate void-action row and divider. The invoice disclosure and void confirmation now use sibling buttons on one header row. Desktop shows the action label; compact screens show the labeled circle-slash icon with a 44px target. The decorative invoice icon is hidden on compact screens to preserve space for the invoice number and payment status. Invoice status truncates instead of wrapping when space is constrained.

Browser geometry compares eligible and readonly fixtures: the collapsed card is 70px high in both at 1440, 390, and 320 widths, without horizontal overflow. A long invoice number `TPS-828ACD84-000003` also remains 70px at all three sizes. Verified disclosure expansion/collapse never opens confirmation; void confirmation never toggles disclosure; Escape returns to the existing order. Captures: `output/playwright/void-order-dialog/inline-invoice-1440.png`, `inline-invoice-390.png`, `inline-invoice-320.png`, and `inline-desktop.png`. Focused void tests 12/12, changed-source ESLint, TypeScript, and diff checks pass. Frontend remains PID20817 on this worktree; fixture-only browser verification and full-stack schema blocker still apply.
