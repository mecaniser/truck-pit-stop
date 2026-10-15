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

2026-10-14: implementation branch codex/repair-order-bounded-browsing at fdd1eca1; approved split preview at http://127.0.0.1:5174, Vite PID47264, cwd ets-parity-preview/frontend, proxy API8001. Docker dieselbridge_api_ets-workflow-parity binds preview/backend to /app. Database postgres / truckpitstop_ets_workflow_parity_20261012, migration169 head, populated data preserved. The approved preview keeps the existing migration169 API; the new branch includes independently merged PR522 (default-off shop-history source, migration170), which is outside this frontend change and is not applied to the populated local database. All frontend application sources match the implementation; remaining frontend differences are tests only. Repair-order API contracts are unchanged. Direct/proxied readiness healthy. Browser acceptance pending.

## Implementation and owner verification

- Viewport intersection now respects both desktop scroll containers and the mobile page. Each observer can request only once; disconnected callbacks cannot fetch another page.
- Automatic loading pauses during the customer entry gate/New Repair Order, covered compact records, search debounce/placeholder results, active requests, and paging failures. Explicit loading remains available after a failure.
- Focused tests: ledger39, customer navigation24, request cancellation16 (79 total); changed-source lint has zero errors and two pre-existing RepairOrdersPage hook warnings. TypeScript and production build pass.
- Signed-in local UI: measured1280×720 desktop search/open/close preserved search; 390×700 customer→truck→new order preserved both identities and cancelled to the same truck; 320×640 intake/Escape retained search; 740×400 touch landscape order controls contained. No horizontal document overflow. Local active order set has21 records, so large-set real pagination acceptance is reserved for production; component/integration fixtures exercise multiple pages and failures.
- Preview5174 is aligned and browser-verified for changed controls. Both modified application files are byte-identical to the approved preview overlay; no backend changes or restart. Captures: /tmp/db122-ui/local-desktop.png, local-320.png, local-landscape.png. No local or production business record was created or modified.

At the local handoff, protected CI, merge, deployment and production large-queue acceptance were still pending; the completed release receipt below supersedes that state. Rollback is a source revert through a focused PR; no data migration is involved.

## Release

PR523 https://github.com/mecaniser/truck-pit-stop/pull/523 passed all six checks on611ade28ea9b3cc3649712fccbdb48a6a42da860 (Quality run38655143713): full frontend1,546 /162files, full backend3,060passed /152skipped, critical backend530passed /11skipped, frontend lint/critical/build, migration graph and Playwright smoke green. Merged539956543399894a9f5c8e0565c50e6542dd3bff at2026-10-14T23:56:03Z; checked source and merge trees identical. Production acceptance completed below.


## Production acceptance — complete

- Web deployment e430fe54-9cdc-41a4-b16b-4eaf23230cf4 SUCCESS at539956543399894a9f5c8e0565c50e6542dd3bff. Browser loaded index-CvYcVhd7.js and /health/ready reported healthy database/Redis. No worker canary required for this Fast UI change.
- Actual signed-in browser, measured1280×720 desktop,390×700 and320×640 portrait,740×400 touch landscape. Customer→exact truck→New Repair Order retains both identities. Across repeated opens, typing, resizing and cancel/Escape, the background queue stayed at25 of3,520. Network evidence has only skip0 requests (including normal refresh and exact-vehicle history), no next-page requests while intake owns the interaction. Cancellation returns to the same customer/truck URL and focused entry button.
- Desktop queue: actual wheel scroll fetched25→50; keyboard Enter on Load more fetched50→75. Search ETS-1750 returned4 records; opening/closing one across desktop/phone retained search. Compact record had one db-workspace-scroll area.
- Phone queue: initial25 records remain bounded; blocked only the skip25 request in the test tab, observed the existing two-attempt retry budget, then zero further order requests over10seconds after the error. Cleared the test block; explicit Load more recovered to50 and removed the error, normal wheel scrolling loaded75. This was an injected browser request failure, not a service outage.
- Empty search→new order→cancel retained the exact query and empty state. Paid/Completed filters with the same search produced0/4 records as expected. Document widths matched all measured viewports; desktop density is unchanged.
- All inspection was read-only or cancelled unsaved forms. Production synthetic vehicle still has zero active outside-service/native history; deleted QA order was not restored. No customer, repair-order, invoice or payment writes occurred.
- Evidence files: /tmp/db122-ui/production-desktop-intake.png, production-desktop-queue.png, production-390-intake.png, production-landscape-intake.png; intake-pagination.json and queue-pagination.json contain sanitized request parameters. baseline-pagination.json is a partial/truncated network capture; the separately observed2,525 rendered rows are the baseline proof, not an inferred request total.
- Temporary network/viewport/touch overrides cleared after acceptance. Physical phones and mobile Safari were not tested; this is actual production UI in browser touch/viewport emulation.

Owner acceptance: complete. The broader ETS parity audit remains open; outside-service attachments, capacity-aware scheduling and on-screen exact-truck history search remain separate work.
