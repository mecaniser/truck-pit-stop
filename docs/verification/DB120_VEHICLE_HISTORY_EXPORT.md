# DB120 Vehicle service-history export

Owner: Backend & Integrations. Read-only export with tenant/privacy boundary; Architecture contract and independent QA/Security required. No migration.

## Audit and selected outcome

Fresh authenticated ETS vehicle Service History → More exposes Export History, alongside Add External Service. Official guide: https://support.easytruckshop.io/en/articles/11814293-how-to-export-an-individual-truck-s-history . Observed public browser assets show a vehicle-scoped export using the current URL filters. No vendor data was changed; export control was inspected, but vendor export contents were not accepted as evidence or copied.

REA6.4.0 analyzed four observed public scripts from build2026-10-14-11-35-29: index.XqiapuZd.js, layout.DBlrVM9J.js, FilterBar.CzxWK1ex.js, DateRangeInput.srf08dq8.js. 27605bytes,6708ASTnodes,zero parse failures. Evidence ev_936429546b7aa03e25b11e665c3044fe477a1b22862072de87418f4ac4df3a59. Local manifest/hashes/analysis: /tmp/dieselbridge-rea-history-export-20261014. Static syntax does not prove vendor runtime behavior; no vendor source reused.

DBN CustomerVehicleDetail lists exact-truck repair orders,25 per page, and outside-shop records, but has no staff vehicle-history export. Customer portal's existing CSV only covers its own surface; it does not close this staff workflow. Selected addition: explicit scope and dates, completed service records from all pages, original source/date/odometer labels, exclusion of internal notes and deleted/voided records, no billing side effects. Receipt attachments remain a separate gap.

## Acceptance

From customer truck or repair-order truck shortcut, prepare a scoped CSV for that exact vehicle; include records across pagination, clearly identify native/imported/outside-shop sources, never mistake record creation for service completion or current mileage for historical mileage. Never include private staff notes/contact/payment data. Invalid ranges, empty results, oversized export and failed requests have explicit recovery without navigation loss or partial file downloads. Tenant/role/deleted-vehicle guards and CSV formula protection. Actual desktop1280,320/390portrait and740x400landscape through local and production browser. Independent gates, all protected CI, exact merge/deploy and production download content verification before Done.

## Runtime preflight 2026-10-14

Implementation codex/vehicle-history-export a340cfd9 from main6b7dfcb0 plus prior documentation receipt. Approved preview split codex/ets-parity-preview846360c3 with overlays:295backend app,177migration,320frontend non-test source files byte-identical before new implementation. FrontendPID47264 cwd preview/frontend port5174; effective API127.0.0.1:8001. Docker dieselbridge_api_ets-workflow-parity binds preview/backend to/app. Database postgres/truckpitstop_ets_workflow_parity_20261012; alembic169head. Direct and /health/ready via5174 healthy. Signed-in Performance Owner, exact C-0001 vehicle, outside record and12repair orders rendered. http://127.0.0.1:5174 aligned and browser-verified for baseline; new export not yet implemented. Root dirty checkout, services, provider settings and populated database preserved.

## Implementation handoff and initial UI verification

Architecture approved the new read-only contract in docs/contracts/db120-vehicle-history-export.md. Backend owner implements dedicated endpoint/service/tests; Frontend & UX implements shared inline export form. No migration. CSV is one row per completed/native or imported repair record or active outside-shop service, no financial fields; strict tenant and role guards, explicit provenance, date/odometer basis, limits without partial files.

Frontend initial34focused tests and TypeScript/production build pass; changed-source lint passes. Tests cover explicit retry, error blobs, pending Escape/Cancel abort, stale session/actor/tenant/vehicle completions, malformed responses and source-size/header validation. A disabled pending button initially made Escape unreliable; corrected with scoped document handling and regression. Actual local1280x720 and390x700 form renders: one primary parent scroll area, no horizontal overflow,340px-wide phone inputs at16px, whole44px controls. Screenshots /tmp/db120-ui/local-desktop-form.png and local-mobile-form.png. Export endpoint/download acceptance still pending.

## Local complete workflow

Actual signed-in desktop export downloaded a2463byte CSV containing8rows:7Shop work and1Outside-shop history, all exactvehicle88040033-d530-47a0-99b1-9e9b7ad3b038,18defined columns, no prices or private notes. Three records have operations. Dates:2Work completed,5Record created with blankService date,1Reported service date. In-progress DB115-HOLD-QA/PERF-0000001/QA107-MOBILE and drafts excluded. SHA2560b5fdae0dcca77c6b8994ff7e7520368af56a102c1b25d381dc7472de0a8dedd. Local files retained in /tmp/db120-ui/local-all-history.csv and local-filtered-1.csv/local-filtered-2.csv.

Native date keyboard entry10/01/2026–10/01/2026 downloaded exactly one outside service with98,000historical miles, matching source/reference/date. Currenttruck mileage100713 unchanged. At390px, a tab-only blocked service-history.csv request showed retry error and retained bothdates; download count stayed2. Clearing block→Retry downloaded thirdfile with the same correct1record. Empty1900-01-01range showed explicit empty-history recovery and no fourthfile. A10second tab-only latency override exposedPreparing; Escape aborted, restoredExporthistoryfocus and retained exact truck URL with no form/file. All network overrides were reset/disabled. These are controlled browser-request failures, not outages.

Frontend final62focused tests include export29,sharedvehicle6,customerworkspace27. Capture-phaseEscape also leaves other dialogs alone. No new customer/order/financial mutations.

## Final date-control correction and local acceptance

Mobile automation exposed browser-native date controls whose displayed value could differ from submitted state. Those initial form images are preliminary, not final mobile date-entry acceptance. Replaced this new form's native controls with the existing shared DatePicker: typed ISO dates, optional inline calendar, clear dates, strict calendar-date validation. No shared DatePicker source changed. Calendar opens in the parent scroll flow at320px, so it has no clipped popup or nested scroll area. Enter submission while a calendar is open now closes it and disables dates while pending; independent QA identified that edge before release.

Final52tests pass: export35, shared vehicle6, DatePicker11; production build6.99s and changed-source lint pass. Actual320px typed Oct1–Oct1 downloaded one614byte outside record; actual390px calendar selection Oct2→Oct1 then export also downloaded one correct record. Actual740×400 Clear dates downloaded8records. Final shared-picker files3/5 have the same614byte content;4/6 match the original2463byte8-row hash. UI screenshots: /tmp/db120-ui/local-320-calendar.png, local-320-success.png, local-390-calendar-success.png, local-landscape-success.png and local-desktop-final.png. Exact1280×720 document width1280; portrait/landscape no horizontal overflow.

Actual390px pending-calendar Enter check with tab-only10s latency: calendar disappeared, both typed dates retained and disabled, Preparing visible; Escape cancelled and retained the exact truck. Overrides reset. New repair order→Cancel returned to the exact customer+vehicle URL. Repair order DB115-HOLD-QA→truckdetails→View vehicle history→Export downloaded8records, then Escape closed only export and Back→customer→Back restored the same order. No business data changed.

## Release gates and rollback

Independent Security resolved both resource-boundedness findings and issued GO. Final runtime application files match the approved5174/8001 preview byte-for-byte. Local readiness remains healthy after all downloads. Release requires all six protected CI checks, exact checked-source/merged-tree equivalence, successful main deployment, fresh authenticated production downloads and recovery/return checks, and post-workflow readiness observation.

Rollback signals: any cross-tenant/private-field disclosure, incorrect exact-vehicle/source/date contents, successful truncated artifact, repeat export500, or regression in customer/RO navigation. Revert the additive UI/router/service commit and redeploy the preceding known-good main; no schema/data rollback is required. Existing outside-history audit records and application state must remain intact. Production QA uses the established synthetic truck and recoverable outside record; any temporary restoration returns to its original voided/deleted baseline.
