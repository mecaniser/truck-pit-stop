# DB118 Operation-specific shop notes

Owner: Backend & Integrations. Standard product; independent QA and privacy review because new internal text must not reach customer output.

## Audit and outcome

Read-only authenticated ETS service1764 displays a Notes disclosure beneath each service item. Opening the first shows “No notes yet”. No vendor records changed or locked job unlocked.

REA6.4.0 analyzed five observed assets from static.easytruck.shop/2026-10-14-10-25-33/build/assets (index.PfOqtQm_.js, layout.7LDOdxhs.js, ServiceItem.BR9NdJJi.js, InternalNotes.Ctb7RDNB.js, NoteForm.CMYd-eXf.js). Result ok:true, evidence ev_79b1aff8c76047112620105d2d43b77d7742fad2fba87a539d845c86687bb646;135248bytes;31627ASTnodes;zero parse failures. Manifest/hashes and raw output: /tmp/dieselbridge-rea-notes-20261014. Static inspection confirms item-scoped notes route, create permission, locked guard, and form default is_public:true. This is static behavior evidence, not a claim of ETS write testing.

DieselBridge currently has order-level customer/shop notes, but no operation-specific note relationship. Add explicit internal-only operation notes so a finding stays with the correct work item. Avoid copying ETS public-by-default behavior. Preserve existing order/invoice note workflow. No vendor code reused.

## Acceptance

- Package and labor operation notes retain exact identity, author/time and text across collapse/reopen/reload.
- Explicit shop-only notice; no leakage to customer/fleet/driver/quote/invoice output.
- Validate nonblank text/length, operation membership, tenant, staff permissions and order lifecycle. No price, timer, assignment or completion side effects.
- Preserve failed draft and explicit retry, prevent duplicate saves/replays; operation switching cannot post to another order.
- Dense desktop,320/390portrait and740x400landscape touch browser journeys; one scroll surface and complete labels.
- Focused backend/frontend regressions, independent QA/privacy review, protected CI, merged/deployed exact source, production synthetic workflow acceptance.

## Runtime preflight 2026-10-14

Implementation codex/operation-shop-notes at a55c0f53 (clean before intake), shared approved preview codex/ets-parity-preview846360c3 plus previously verified overlays. All backend/app and frontend/src application source bytes matched at intake. Frontend5174 restarted because absent, PID47264, cwd ets-parity-preview/frontend, validated branch/SHA and DIESELBRIDGE_API_ORIGIN=http://127.0.0.1:8001. API container dieselbridge_api_ets-workflow-parity binds preview/backend to/app;localhost8001. DBpostgres/truckpitstop_ets_workflow_parity_20261012;alembic168_operation_execution head. Direct and proxied readiness DB/Redis healthy; existing provider settings and populated DB preserved. Signed-in Performance Owner local dashboard loaded matching runtime badge and shared source. Local aligned and browser-verified. Production authenticated separately; release remains pending.

## Implementation and gates

Shared operation-note component in the staff price builder and mechanic operations view. Notes load on explicit intent, stay with exact Labor.id, keep drafts while collapsed, and use stable UUID retries. Author/time/plain text, explicit shop-only wording, read-only reasons and visible recovery are provided. Existing history stores the original operation description; staff history retains it after operation removal. No migration or dependency/provider/flag changes.

Independent Security caught two shared full-detail cache boundaries and a stale denied-response rendering path. Staff and fleet detail caches now include tenant/actor/role/session epoch while retaining existing invalidation prefixes; fleet presentation excludes shop notes entirely. Failed notes refresh hides prior body/author/count and disables new saves. Tests cover warm-cache account/session transitions and denied refresh. [Security GO](DB118_SECURITY.md). QA raised long-label wrapping and a stale-key deletion assertion; both corrected. [QA receipt](DB118_QA.md).

Automated:131frontend cases across seven affected suites pass; raw changed-source ESLint zero errors/two unchanged RepairOrdersPage hook warnings; TypeScript/production build passes. Backend140 focused cases pass (39new plus execution/hold regressions), eight real PostgreSQL races pass on isolated test database. Logs /tmp/db118-frontend-focused.log, /tmp/db118-frontend-privacy.log, /tmp/db118-backend-focused.log, /tmp/db118-postgres-tests.log. Source comparison shows all application files match approved preview. Initial lint:changed invocation before commit saw no committed diff; use committed-head lint at release, not that no-op as evidence.

## Local browser acceptance 2026-10-14

Actual authenticated browser local preview, Performance Owner. Desktop1280x720; touch390x700,320x640,740x400 landscape. Browser emulation, not physical device/native keyboard. Desktop800px emulation exceeded the in-app native capture surface and produced a screenshot artifact; acceptance uses measured720px desktop instead. Phone screenshots and DOM dimensions match.

- DB115-HOLD-QA (46d5bd79-254e-4a0e-b282-c169cdfd04f5), Brake inspection2d89f51a-09cf-43c7-be2e-8025a008d5fb: desktop draft survives operation collapse/reopen, saves with Performance Owner/time, remains on phone reload. Mobile blocked exact notes endpoint causes visible read/save failure, preserves draft, then Retry notes and Retry save succeeds. Exactly two distinct QA notes; no automatic write retry. Order remains in_progress/$290, operation completed, assigned Hold QA Alex,3m41s tracked; no timer/status/pricing actions submitted.
- DB110-MOBILE0c1832b1-ada2-4076-8c2a-ca0426225f1d, service-package laborbedb535b-150a-449b-bf56-f9d31bceed84: mobile package note saves and persists after reload; other operations remain separate; total$253.75 and completion unchanged.
- DB110-DESKTOP02c73fd3-fb52-4890-b524-a08c6b3e83e3, finalized invoice: operation notes read endpoint succeeds, explicit finalized/cancelled read-only reason, no Add action. No invoice/payment mutation.
- Mobile measured scrollWidth equals320/390/740; only .db-workspace-scroll scrolls vertically. Notes controls44px, textarea16px after correcting the global type-scale override. Complete Cancel/Save labels fit320px. Landscape composer and footer remain reachable.
- Screenshots: /tmp/db118-ui/local-desktop-720.png (clean 1280×720 desktop), local-mobile.png, local-320-composer.png, local-landscape.png, local-finalized.png. Earlier local-desktop.png has capture artifact and is not visual acceptance evidence.

The browser network failure was deliberately injected only into this QA tab; blocking was cleared and Network disabled. True ambiguous post-commit replay/concurrent retry is proven by backend PostgreSQL and client stable-ID tests; blocked browser request is not claimed as a committed response loss. Local synthetic notes are retained as audit evidence. Production acceptance remains pending.

## Rollback

No migration. Stop adding notes and retain the operation_note_shop privacy filter if rolling application code back: older full-detail serializers do not recognize the new event. Rollback trigger: unauthorized note disclosure, duplicate/lost notes, or changed lifecycle/accounting behavior. Do not roll back to a serializer that would reveal existing new events.

## Release tracking

PR519: https://github.com/mecaniser/truck-pit-stop/pull/519. Source eab4b2477bf3672a6f94529a9dee21560ca8d981. Committed-head BASE_SHA=origin/main lint passes across11files. Quality gates38614337519 running; no merge/deployment acceptance yet. Pre-push MEDIUM scanner warning was inspected: a synthetic confidentiality marker in backend/tests/test_operation_notes.py:105, not production data or a credential.

### CI correction

Initial run38614337519 passed five jobs, including backend2967passed/140skipped, but frontend full suite stalled. Local full run isolated RepairOrdersPage.customer.test.tsx (159of160files completed): its existing auth mock recreates the user object, exposing a repeating workspace sync effect introduced by the cache scoping. Memoize the selected detail key using the same primitive tenant/actor/role/session/order values; effect now depends on that stable key. No privacy partition or authorization change. Independent QA53passed and Security4privacy cases pass. Corrected full local suite **160files/1464tests passed**,45.75s (/tmp/db118-frontend-full-fixed.log). Initial cancelled run is not a complete CI gate; fresh corrected-head CI required.

### Second CI assertion and local browser recheck

Corrected-head CI38617876518 frontend completed1463passed/1failed. The sole failure expected no query-cache entry after deletion; a disabled observer had recreated the scoped entry with undefined data. The assertion now requires no retained data across all scoped keys, preserving the real privacy/stale-data requirement and the existing no-unavailable-requests/Restore checks. Application code is unchanged by this test correction.

After sign-in restoration, source-matched preview readiness/database/Redis healthy. Actual1280desktop customer→same order→exact Brake inspection notes retains both notes. Actual390phone customer→New repair order→Cancel returns focus to New repair order and retains selected order/queue/customer route; Back→Close returns exactly/dashboard?queue=on_floor. Customer has one .db-customer-embedded__body scroller,390px document width; screenshot /tmp/db118-ui/local-customer-return-390.png. No new orders or notes created during this recheck.

## Final release candidate and production fixture

Final candidate14bd7819c8d7cb30ecabcff1e43a9cce1a59db89; committed-head changed-source lint passes11files (/tmp/db118-lint-final.log). Corrected CI38618926558 has passed frontend full suite, frontend checks, critical backend tests, migration graph and Playwright smoke; full backend is still running. No merge/deployment claim yet.

Production session restored by product owner. Existing synthetic orderTPS-828ACD84-000056 (bce9b62b-a7e3-4ba9-a740-6ced6857e9b3), customer DB115 Production QA — not customer work, vehicle DB115-QA, was restored through UI for verification. Added DB118 QA Note Verification,15minutes booked, then set hourly rate0; order total0, not completed, unassigned, no tracked time. No estimate/invoice/payment or technician/time actions submitted. These setup actions used the prior deployed version and are not DB118 release acceptance. After deployment, validate notes then return this fixture to recoverable deleted state.

## Merge and deployment

All six Quality gates38618926558 succeeded on14bd7819c8d7cb30ecabcff1e43a9cce1a59db89: frontend160files/1464passed, critical backend530passed/11skipped, full backend2967passed/140skipped, frontend build/lint, migration graph and Playwright smoke. Full backend703.13s. Logs /tmp/db118-ci-frontend-final.log, /tmp/db118-ci-backend-critical.log, /tmp/db118-ci-backend-final.log.

PR519 squash merged2026-10-14T19:07:37Z as182fa5f6b58ef0bce78716cb7b9266fbcc930374. Checked and merge trees bothcd43ed6654958cc6704d5ab0f224c8d2f14e00b4. Automatic Railway Web deployment89cc30b4-7c70-4028-8990-ebd73fe19e49 started19:07:40Z for that exact merge; building at this checkpoint. No migration. Production acceptance follows confirmed deployment.

Railway deployment89cc30b4 reached SUCCESS for182fa5f6. Readiness at initial acceptance: ready,production,database/Redisok,uptime55s (/tmp/db118-production-ready.json). Fresh signed-in browser loads /assets/index-B9r7oiQG.js. Production operationdc20ee71-a00b-4913-be51-7fd3ea32eb87 notesGET200; desktop draft collapse/reopen retained, first save succeeded with actor/time, total0/unassigned/incomplete/no tracked time unchanged. Desktop1280x720 document width1280, one db-workspace-body scroller. Full phone/landscape/recovery/finalized acceptance still in progress.

Production mobile390x700 reload retained desktop note. Exact QA notes URL blocked only in this browser tab: Save showed explicit error, retained80-character draft, hid cached list after failed refresh. Cleared block; Retry notes restored original note; Retry save created second intended note, count2. This simulates blocked requests, not a lost response after commit. No live outage claimed. At320x640 composer is280px wide with16px text; note/Cancel/Save controls44px tall. At740x400 touch landscape textarea, whole Cancel/Save labels and footer are reachable. All three mobile document widths match viewport and only db-workspace-scroll scrolls. Empty third composer cancelled without a write.

Production390 full reload confirms exactly two saved notes with correct actor/time and unchanged operation/order state. Customer→New Repair Order loaded→Cancel retains selected order/customer URL and returns focus to New repair order; Back returns same order; Close leaves exactly/dashboard/repair-orders with no order workspace. Customer390 has one db-customer-embedded__body scroll and no horizontal overflow. Repeated desktop customer→New Repair Order→Cancel retains DB115 Production QA queue search, selected order/customer and focus; Back returns same order. No new order was submitted. Screenshots customer-mobile.png and customer-desktop.png in the production artifact directory.

Finalized production orderTPS-828ACD84-000054 (5d8249a2-ea8a-404e-8e9d-0f20b59a589b) inspected read-only at1280desktop and390phone: operation notes load successfully, explicit finalized/cancelled read-only explanation and zero Add operation note buttons. No note, invoice, payment, revision or customer mutation on this real order. Screenshot finalized-mobile.png.

## Production acceptance complete — independent QA GO

2026-10-14: exact deployed merge182fa5f6; signed-in desktop1280x720 and touch-emulated390x700,320x640,740x400 passed. Both intended notes persist after reload; per-operation author/time, retained collapsed draft, blocked-request recovery with explicit refresh/save, customer navigation/cancellation/search preservation, Close and finalized read-only behavior verified. No added notes on real customer work; no invoice/payment/technician/timer/completion actions submitted. Pricing remains0 on the synthetic fixture. Browser emulation does not establish physical-device or native-keyboard behavior.

Cleanup: syntheticTPS-828ACD84-000056 was soft-deleted through the mobile UI. Deletion returned to the order ledger. Opening the known deleted-order URL then shows Deleted, actor/time, preserved-record explanation and Restore; operation/checklist/history unavailable panels stay absent with no error. Two QA notes and their zero-charge operation remain recoverable as audit evidence. This is not claimed as an immediate in-place Restore transition, because this ledger flow closes the selected workspace after delete.

All injected request blocking was cleared and Network observation disabled. Final readiness remains ready with database/Redisok, uptime416s (/tmp/db118-production-ready-final.json), after approximately six minutes of production UI acceptance. No rollback trigger observed.

Production screenshots are local artifacts under /Users/sergio_m1_promax/.codex/visualizations/2026/10/14/db118-production/: desktop.png, mobile.png, mobile-320-composer.png, landscape.png, customer-mobile.png, customer-desktop.png, finalized-mobile.png and cleanup-deleted.png. Independent QA reviewed the first five without a visual blocker; final receipt/images supplied for closure.

## Closure

Independent QA reviewed all eight production screenshots, final journey/cleanup receipt, CI logs, readiness and exact tree identity: GO, recorded in DB118_QA.md. Security GO remains valid on the unchanged application source. DB118 is Done. Temporary local/production QA tabs closed; device/touch overrides and browser viewport reset; shared preview services remain running.

Final post-release documentation is committed locally on the delivery branch for the next documentation checkpoint. It is release evidence, not a second production code change. Full ETS parity remains incomplete; the scoped operation-note gap is released.
