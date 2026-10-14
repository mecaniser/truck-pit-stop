# DB119 External service history

Owner: Backend & Integrations. High-risk lane for tenant-scoped data and additive migration.

## Audit and selected outcome

Authenticated, read-only ETS inspection: Vehicles → vehicle → More → Add External Service. Form exposes company/vehicle, number, PO number, vendor, date, odometer, issues, labor/parts, tax/fees/discount and attachments. No form submitted. Fresh assets were captured through the authorized browser and statically parsed using REA6.4.0: five files,42491bytes,10260AST nodes,zero parse failures; evidence ev_30e94734595c3498ed113387938beea58f81e99f031635e316ad3e9532b22277. Manifest and analysis /tmp/dieselbridge-rea-external-20261014. Static analysis does not prove vendor write behavior; no vendor code reused.

Official explanation: https://support.easytruckshop.io/en/articles/11887994-what-is-an-external-service . DieselBridge currently shows native repair-order/inspection history but lacks a dedicated outside-shop work record. Implement a compact historical record: provider/date/work, optional odometer/reference/cost. Explicit source and nonbillable semantics improve on recreating another shop's bill in this shop's order ledger. Receipt upload and detailed external bill reconstruction are follow-ups, not part of this first release.

## Acceptance

Create and revisit external work from customer vehicle context and embedded repair-order customer/vehicle context. Preserve original attribution and recoverable corrections; duplicate-safe explicit retries, retained failed drafts, clear loading/error/empty states. No invoices, balances, PM, current mileage, timer or repair-order status changes. Validate tenant, roles, deleted vehicle, lengths/date/numbers and concurrency. History follows an approved vehicle merge. Desktop1280x720, touch-emulated390/320portrait and740x400landscape: full controls, one parent scroll surface, no horizontal overflow, successful save/reload, error/retry and return navigation. Independent QA/Security, protected PR CI, exact production deployment and synthetic desktop/mobile acceptance required.

## Runtime preflight 2026-10-14

Implementation codex/external-service-history at a7b279d082c0f2a8b102ade3b7fc8063c698518c (clean before intake); approved intentional split uses preview codex/ets-parity-preview846360c3 plus overlays. Source comparison:291backend application files,176migrations,318frontend application files byte-identical (tests/cache excluded). Vite5174 PID47264 cwd preview/frontend, API target127.0.0.1:8001, runtime branch/SHA reflect preview. Docker API dieselbridge_api_ets-workflow-parity binds preview/backend→/app, postgres/truckpitstop_ets_workflow_parity_20261012, alembic168_operation_execution. Readiness direct and proxied healthy; signed-in local DB115-HOLD-QA renders current operation notes, source-matched baseline. Local URL http://127.0.0.1:5174 is aligned and browser-verified for the current baseline; DB119 is not yet implemented. No provider/flag/database reset. Root dirty checkout preserved.

## Implementation and local acceptance (in progress)

Contract approved by Architecture. Dedicated owner/admin/receptionist API, two additive tables, versioned corrections/void/restore and immutable attributed snapshots. Backend55focused cases and9real PostgreSQL concurrency/constraint cases pass; migration168→169 passes on isolated test database. QA/Security independent reviews underway. Preview explicitly migrated169 after isolated proof, seventeen application/migration files mirrored; no reset/provider/flag change.

Frontend initial full suite161files/1489tests passed; subsequent semantic-response guards and denied-editor dismissal/late-save isolation have30focused tests passing. TypeScript and production build pass. Independent QA found the order-header shortcut assumed the target existed in the first customer vehicle page; returned to owner for exact-vehicle resolution/loading/error handling before release.

Actual local1280desktop created one DB119 Local QA Outside Shop record on C-0001, service2026-10-01, historical mileage98000, reported cost240.50, refDB119-LOCAL-ONLY. Current truck mileage100713 and native orderDB115-HOLD-QA total290 remain unchanged. Mobile390edit persisted correction; Change history retained original and edited values with Performance Owner/timestamps. Tab-only blocked *external-services* requests caused visible failed-save and failed-refresh warnings; draft retained. Clearing block, Retry outside history then Retry save saved the intended correction once. Blocking cleared and Network disabled; no claim of post-commit lost-response simulation.

320phone fields270px wide/16px text; document320,390 widths exact; one primary db-customer-embedded__body scroller (textarea may scroll its own content).740x400touch landscape has complete Void reason/Cancel/Void controls and reachable footer. Void removed active entry; Show voided revealed retained record; Restore returned it to active. Screenshots /tmp/db119-ui/local-desktop.png, local-mobile.png, local-320-composer.png, local-landscape.png. Native date selection was verified through segmented keyboard input; CUA fill alone changed DOM but did not update React's date state, so it is not used as acceptance of date entry. Production unchanged.


Final navigation correction uses exact vehicle ID, tenant/actor/role/session-scoped cache and URL customer_vehicle context. Actual order shortcut reload retains C-0001 and its saved record. Back truck→customer→DB115-HOLD-QA clears nested context.390px standalone customer search→truck→New order→Cancel returns to the truck; Back customer→list preserves the nonempty query and results. New screenshot /tmp/db119-ui/local-320-controls.png shows full form controls. Independent review additionally required the direct getter to reject archived trucks and retain owner/operator enrichment; correction in progress.

Final frontend suite161files/1501tests passed46.01s (/tmp/db119-frontend-release.log); TypeScript plus Vite build passed7.32s (/tmp/db119-build-release.log). Changed-source lint zero new errors; two RepairOrdersPage warnings verified identical to HEAD baseline.


Getter correction complete: active vehicle guard, staff-only existing owner/operator enrichment with active same-tenant relationship/customer filters. Backend focused suite62passes; final navigation23passes (two added getter-integration cases after the1501-test full run). All18changed application/migration files byte-identical to the approved preview. Direct and proxied readiness healthy after hot reload. Actual390px final embedded history retains Owner Performance Carrier001; blocking its exact vehicle request shows only Back/Retry, then explicit Retry recovers the correct saved truck. Block cleared, Network disabled.390px document width390 with one587px primary content scroller. Final screenshots /tmp/db119-ui/local-final-phone.png and local-final-desktop.png.
