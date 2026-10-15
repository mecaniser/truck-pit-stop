# DB129 — Outside-shop receipt attachments

Accountable owner: Backend & Integrations. High-risk lane: private documents and additive schema.

## Audit

Read-only ETS customer → vehicle → More → Add External Service exposes Attachments / Upload Files beside historical provider/date/odometer/work. No vendor form submitted or file uploaded. CUA captured three already-loaded public static scripts (external service, attachment button and thumbnail); REA6.4.0 analyzed39,401bytes/9,506ASTnodes with zero parse failures. Evidence `ev_8c62aaba7f205ccdbdeb37e0588ee4902f012ad7ee69865d2970e91ccceb64f5`; local artifacts `/tmp/dieselbridge-rea-receipts-20261014`. Static syntax corroborates the UI; it does not prove vendor write behavior. No vendor code reused.

DB119 already records outside work but explicitly deferred receipt files. Selected improvement: attach once to the exact outside-work entry, private staff download, duplicate detection and recoverable removal with attribution. No external bill reconstruction or accounting effects.

## Runtime preflight

2026-10-14 local: implementation `codex/external-service-receipts`, base1c1e34cf with only intake documentation dirty. Approved intentional split preview `codex/ets-parity-preview`846360c3 retains prior overlays. Vite5174 PID97270 cwd preview/frontend; API target127.0.0.1:8001. Docker `dieselbridge_api_ets-workflow-parity`, image truck-pit-stop-api, preview/backend→/app, localhost8001→8000. Database postgres/truckpitstop_ets_workflow_parity_20261012 at169_external_service_history. Proxied readiness confirms database/Redis healthy. User restored authentication; local customer dashboard and production staff dashboard render. No new feature is yet visible. Additive migration170/171 plus the forthcoming receipt schema will be explicitly applied to this preserved local database after contract verification; no reset, provider flags or live payment changes. Exact changed-file overlay and browser proof required before claiming alignment for DB128.

## Required acceptance

Upload valid bounded PDF/PNG/JPEG, download after reload with matching bytes, duplicate retry and explicit duplicate detection, remove/show removed/restore with immutable actor/time events, and voided-record read-only behavior. Reject role/tenant/vehicle/record mismatch, invalid/oversize content, stale mutations and tampered request IDs. Preserve parent customer/order return context and compact desktop/390/320portrait/740x400landscape controls with no horizontal overflow. Independent QA/Security, protected CI, exact deployment and synthetic production workflow remain pending.


## Implementation and local acceptance

Architecture contract approved. Three additive private tables store metadata, separately deferred bounded binary data and immutable receipt events. Receipt uploads authenticate before bounded raw-body reading and bypass generic idempotency caches, including noncanonical UUID routes. Private forced downloads reauthorize exact tenant/truck/service/receipt. Generic SQL bind diagnostics are hidden; receipt errors suppress file-derived message/stack data. Removal is recoverable and retained files count capacity. No external provider, public URL, accounting or current-mileage writes.

Local preview received 17 scoped runtime files; existing unrelated overlays preserved. Models init has the equivalent receipt import while preserving its existing baseline. Direct file comparison confirms the other 16 changed runtime files match implementation; Vite97270 still5174 with approved8001 proxy and backend bind mount. Preserved database169→170→171→172 migration succeeded, database/Redis readiness healthy after reload. URL http://127.0.0.1:5174 is aligned and browser-verified for DB128. Existing main-only unrelated changes are not claimed to be previewed.

Owner checks: 85 frontend cases (55 receipts, 30 existing outside-history), app TypeScript and changed-source ESLint; 29 backend receipt cases, 25 middleware cases, 44 DB119 regressions; 11 receipt diagnostic/header cases plus 33 database resilience; 10 isolated real PostgreSQL race/constraint cases. Isolated empty database upgrade through172 and empty172→171→172 passed.

Actual authenticated local 1280x720 desktop, 390x700/320x640 portrait and 740x400 touch landscape: PDF upload then browser download exactly matched 618 original bytes; duplicate upload rejected with one copy; disguisedHTML PDF rejected; 5 MiB+ file visibly blocked. Mobile PNG network failure retained selection; explicit Retry saved one copy. Remove→Escape returned focus; remove with reason→Show removed→Restore retained three attributed events. Restored PNG browser download byte-identical. Full reload retained both files; new-order Cancel returned exact truck; repair-order header→View vehicle history exposed same files; Back returned through customer to same order. Customer balance 145.00, vehicle mileage 100713 and order 290.00 stayed unchanged. Voiding only DB128 synthetic outside entry retained metadata/history and disabled upload/download/remove. Localfixture left voided for cleanup; no native order/timer/billing writes.

Measured 390 portrait has one `.slide-panel-content` scroller, no document overflow and 44px receipt controls; 740 landscape order has one `.db-workspace-scroll`, no overflow. Screenshots `/tmp/db128-qa/local-desktop.png`, `local-mobile-390.png`, `local-mobile-320.png`, `local-landscape.png`; mobile captures use CDP actual emulated viewport because ordinary tab screenshot scaled its output. Touch emulation is not physical-device/native-keyboard certification. Temporary network block removed and Network disabled. Independent final gate, protected CI and production acceptance pending.

## Independent local gate

Independent Security and local QA GO at 2026-10-15 03:49 UTC (Oct14 local), with all initial findings resolved. See [review receipt](DB129_SECURITY_QA.md). Fresh durable PostgreSQL evidence at `/tmp/db128-backend-evidence/runtime-receipt.log` records 10 passes and the empty172→171→172 migration cycle; guarded runner and step logs are retained beside it. Protected CI and production release acceptance remain pending.

## Protected integration gate

PR #533 tests `e3918085c47bf98ec99b692cc2c8036832d1334a`; Quality gates run38678423462. Initial Playwright job116237297248 failed before checkout at container initialization after three registry `toomanyrequests: Data limit exceeded` responses. No application test ran in that job. A job retry while the overall run was still active was refused; retry awaits run completion. All six protected checks remain required.

Oct15 local day refresh during CI: implementation e3918085 with only release documentation dirty; approved preview Vite PID97270 on5174, cwd preview/frontend, effective API origin8001. Docker bind mount and ports unchanged; database postgres/truckpitstop_ets_workflow_parity_20261012, development, migration172 current, proxied database/Redis ready. All16 directly comparable DB128 application files still match; models init retains documented equivalent import. No restart/migration/setting change. Current-day source/HTTP aligned; local browser acceptance is the completed Oct14 record above, not a new Oct15 browser run.

## Integration refresh and board identity

The concurrent infrastructure PR530 reserved DB-128 and merged as d31d6597. This receipt item is now DB-129; earlier artifact paths and synthetic labels intentionally retain DB128 for traceability. No application code changed with this renumbering. Initial CI passed migration, frontend build/critical, full frontend1622 and backendcritical530/full3195 (162skipped). The Playwright retry cleared its initial registry block. Strict branch protection requires incorporation of updated main and a fresh exact-head CI run.
