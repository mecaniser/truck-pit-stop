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
