# DB-105 — Customer workspace density and consistent shell

Owner: Frontend & UX. Fast UI; existing API, permissions and data contracts.

## Final accepted direction

Customer and repair-order workspaces use the available height, with actions at
the bottom. Customer identity, company contact and balance lead, followed by
visible compact account facts, connected trucks and named contacts. Only the
customer tax control is inside collapsed Business settings, per the latest user
request. The control retains its existing permission, version, idempotency and
save behavior. No backend, schema, tenant or financial calculation changes.

The first account-disclosure and content-sized customer-shell iterations were
rejected by the user and are superseded. The board retains that history.

## Implementation and regressions

- Corrected the repair-order grid fraction clamp: 29fr/71fr consumes available
  width when the queue reaches its minimum. At the original 1295px viewport,
  previously unused 213px is now consumed by the detail panel.
- Embedded customer header/body/footer uses a full-height flex shell. Customer
  body is the sole content scroller; Edit, Merge and Delete remain at the bottom.
- Phone repair orders keep one scrolling sheet and a sticky action footer;
  header and workflow can scroll to preserve access to work at narrow heights.
- Removed the account-details disclosure. Address, customer since, US DOT,
  MC, source and QuickBooks remain visible; no duplicate summary/activity tiles.
- Compact truck rows keep relationship, vehicle, VIN, plate and balance; list
  and card controls support keyboard activation. Loading is not shown as empty.
- Business settings uses a Lucide chevron, keyboard button and aria-expanded.
  Closing preserves an unsaved draft; a different customer resets it. Existing
  role and tenant guards also govern the disclosure; opening does not save.

## Automated evidence

Full-height revision: 73 source / 76 combined-preview focused tests pass across
customer record, workstation, tax, merge, repair-order host, ledger and type scale.
Final Business settings revision: three RED failures reproduced the missing
placement; all 19 affected record/tax tests pass in source and combined preview.
Both final production builds pass. Final changed-source lint is clean; the wider
repair-order file retains two pre-existing hook-dependency warnings, no errors.
All command receipts are in local, untracked output/db105/ or preview/output/.

## Signed-in browser evidence

Actual local app, existing synthetic Performance Carrier 001. No customer, tax,
payment, merge or deletion submitted. Editor/contact open-cancel and existing
canonical truck/history keyboard flows checked earlier; final edit open-cancel
and back-to-order preserve selected order and queue.

- RED: embedded panel bottom503 vs workspace1169; account details hidden.
- Final shell at1295x900: both customer and repair-order panels top17/bottom883,
  both action bars bottom882. No horizontal document overflow.
- Embedded customer at390x844: panel fills700px available staff area; footer
  stays at776 while customer body scrolls222px to reach contacts.
- Embedded320x740 and canonical Customers320x740: one content scroller, all
  footer labels fit, actions44px high, no horizontal overflow.
- Final Business settings desktop: checkbox hidden initially, address visible,
  Enter opens the tax control. At320x740, disclosure44px, zero overflow, footer
  stays anchored. Open/close leaves the saved setting unchanged.
- Browser console errors: none. Physical phones/native mobile keyboards untested.

Final captures: output/db105/customer-final-desktop.png and
output/db105/customer-final-mobile.png. Earlier full-height captures and RED/
GREEN geometry retained. Temporary viewport overrides reset and QA tabs closed.

## Runtime receipt — 2026-10-12, 17:52 America/New_York

Source codex/customer-workspace, implementation b402407d; intentionally served
through combined codex/ets-parity-preview bb949f9b, preserving earlier ETS work.
FE http://127.0.0.1:5174, PID68993, cwd preview/frontend. API container
 dieselbridge_api_ets-workflow-parity mounts preview/backend at /app and maps
127.0.0.1:8001 to8000. FE proxy/health/ready reports database and Redis ready.
DB postgres/truckpitstop_ets_workflow_parity_20261012; Redis redis/9; populated
volumes and provider settings unchanged, no restarts. HMR feature elements and
process/source ownership corroborate the older boot badge. Aligned and
browser-verified locally; not deployed.

## Review and boundaries

Draft PR504: https://github.com/mecaniser/truck-pit-stop/pull/504, stacked on503.
Earlier CI38311300548 passed required frontend/backend/migration/Playwright
jobs at the older ecef56d3 head; it does not cover these corrections. A new
quality workflow is dispatched on the final review head. Not merged or deployed;
board remains Review, not Done.

The embedded host's pre-existing no-op truck selection and empty history detail
callbacks are outside this layout change and remain repair-order parity follow-ups.
Canonical Customers truck/history behavior is covered; do not claim the embedded
callbacks were implemented by this change.
