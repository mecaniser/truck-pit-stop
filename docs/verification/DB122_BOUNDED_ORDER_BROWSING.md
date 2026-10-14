# DB122 — Bounded repair-order browsing

Owner: Frontend & UX. Lane: Fast UI; existing contracts, no migration or permission change.

## Acceptance

- Mobile page-scrolling and desktop list-scrolling request the next page only when the end becomes visible.
- No automatic loading behind New Repair Order, its contextual entry gate, or a covered compact record.
- Explicit Load more remains keyboard accessible; pending requests cannot duplicate, errors stop automatic retries and leave an explicit retry path.
- Search/status changes retain focus, start the correct page, and never append stale-query results.
- Customer/truck preselection and cancel return, order open/close and desktop density remain intact.
- Verify signed-in local and production desktop, portrait and landscape through actual browser interactions; browser emulation is not physical-device certification.

## Discovery

Fresh production reproduction at 390×700: from the synthetic customer truck, New Repair Order loaded 2,525 of 3,520 orders without queue scrolling. The observer root is a mobile content-sized wrapper, so the end is always intersecting that root. No record was created. ETS completed-service/search/intake inspection and four fresh public assets were analyzed with REA 6.4.0 (build 2026-10-14-13-08-02), evidence ev_c0cb0ce145816787c6f1af50b1ba90440a1db8c30eb711cf0bba7666b464c3cc. Static analysis does not establish successful vendor writes. No ETS data changed or source reused. This is a parity-process reliability improvement, not a new ETS capability.

## Runtime preflight

2026-10-14: implementation branch codex/repair-order-bounded-browsing at fdd1eca1; approved split preview at http://127.0.0.1:5174, Vite PID47264, cwd ets-parity-preview/frontend, proxy API8001. Docker dieselbridge_api_ets-workflow-parity binds preview/backend to /app. Database postgres / truckpitstop_ets_workflow_parity_20261012, migration169 head, populated data preserved. All application sources match implementation baseline; differences are tests only. Direct/proxied readiness healthy. Browser acceptance pending.

## Implementation and owner verification

- Viewport intersection now respects both desktop scroll containers and the mobile page. Each observer can request only once; disconnected callbacks cannot fetch another page.
- Automatic loading pauses during the customer entry gate/New Repair Order, covered compact records, search debounce/placeholder results, active requests, and paging failures. Explicit loading remains available after a failure.
- Focused tests: ledger39, customer navigation24, request cancellation16 (79 total); changed-source lint has zero errors and two pre-existing RepairOrdersPage hook warnings. TypeScript and production build pass.
- Signed-in local UI: measured1280×720 desktop search/open/close preserved search; 390×700 customer→truck→new order preserved both identities and cancelled to the same truck; 320×640 intake/Escape retained search; 740×400 touch landscape order controls contained. No horizontal document overflow. Local active order set has21 records, so large-set real pagination acceptance is reserved for production; component/integration fixtures exercise multiple pages and failures.
- Preview5174 is aligned and browser-verified for changed controls. Both modified application files are byte-identical to the approved preview overlay; no backend changes or restart. Captures: /tmp/db122-ui/local-desktop.png, local-320.png, local-landscape.png. No local or production business record was created or modified.

Protected CI, merge, deployment and production large-queue acceptance remain pending. Rollback is a source revert through a focused PR; no data migration is involved.
