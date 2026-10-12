# DB-105 — Customer workspace density

Accountable owner: Frontend & UX. Fast UI; existing contracts only.

## Acceptance and scope

Customer identity, company contact links, balance, connected trucks and their
relationship/financial status lead the record. Account details reveal directly
under their trigger. Contacts and account administration remain available;
existing tax permission, version and idempotency logic is unchanged. Desktop
uses compact pointer controls, phone uses 44px touch heights and reflows records.
No backend, API, migration, permission, financial calculation or data changes.

Source branch `codex/customer-workspace` starts from PR503. The runtime intentionally
uses the combined `codex/ets-parity-preview` branch to preserve DB098–104.
Implementation commits are cherry-picked there; source is not a second server.

## Regression evidence

- RED: eight of nine initial tests failed for missing disclosure, ordering,
  keyboard actions and semantic balance region. Two further tests reproduced
  non-keyboard card activation and the false empty state while loading.
- GREEN: 40 tests across customer record, workstation, tax permission/concurrency,
  vehicle merge and staff type scaling pass. Changed TS/TSX lint and build pass.
- Contact and customer callbacks remain unchanged. Disclosure collapse retains a
  tax draft without a write; switching customer resets disclosure and tax state.
- Browser initial pass found three presentation issues: global 44px defaults
  still inflated desktop controls, phone Back was only32px wide, and history
  spend wrapped its currency across lines. Corrected as one batch.

## Runtime receipt — 2026-10-12

- FE http://127.0.0.1:5174, PID68993, cwd combined preview/frontend. Vite proxy
  targets approved8001. `/health/ready` via FE reports database and Redis ready.
- API container `dieselbridge_api_ets-workflow-parity`, preview/backend mounted
  at `/app`, port127.0.0.1:8001→8000. No restart or config changes.
- DB postgres / `truckpitstop_ets_workflow_parity_20261012`; Redis redis /9.
  Existing sandbox/provider settings and populated database preserved.
- Boot badge predates HMR commits. Process/source ownership and newly rendered
  account disclosure/compact truck rows prove served changes.

## Browser evidence

Real signed-in local app and existing synthetic Performance Carrier001 fixture.
No record, tax, payment, merge or deletion submitted. Customer edit and contact
forms opened and cancelled; truck and history opened by keyboard.
Initial1280x800 measurement: truck heading y913.7, outside visible panel.
After restructuring it is y401.7 before the final desktop control tightening.
390x844 history and320x740 expanded account details have zero horizontal
page or descendant overflow.320 account view has one content scroller.

Captures and command receipts: `output/db105/` (local, untracked).
Physical phone browsers/keyboards are not tested.

## Final local acceptance

- 1280x800: header49px and footer49px (previous77+77); truck heading
  y371.7 (previous913.7), truck row75px. Desktop actions32px high.
- 960x800: single-panel view fits; no horizontal overflow.
- 390x844 and320x740: phone controls44px high, Back44x44, footer stays on
  one row at320px (53px including padding/border). Currency remains whole.
- Account details are directly after their trigger, including at320px. History
  expands by keyboard and reflows into labeled records. No page or component
  horizontal overflow in inspected overview, disclosure and expanded history.
- 40 source-focused tests and43 combined-preview tests passed; both builds pass.
  Exact changed-source lint has zero errors/warnings. Existing toolchain notices
  (Browserslist/React Router future flags) do not indicate test failures.
- The additional customer-switch round trip regression failed first and was
  fixed: returning A→B→A does not reopen A's old account disclosure.
- Layout detector returned an empty finding list. Rendered checks, rather than
  the detector alone, establish the density result. Account links, labels and
  new rows use existing staff color/scale tokens; no animation added.

Final captures: `customer-desktop-final.png`, `customer-mobile-final.png`,
`customer-mobile-320-final.png`, `customer-history-320-final.png`.

Local acceptance only. PR, CI, merge and deployment are separate gates.

