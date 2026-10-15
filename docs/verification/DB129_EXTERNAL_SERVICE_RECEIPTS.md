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

All six initial protected checks passed on e3918085 after the targeted smoke retry (run38678423462 attempt2). Main then advanced with reviewed CI infrastructure d31d6597; branch merged it and reconciled board/audit links. Final receipt application files remain identical to the independent manifest. Refreshed protected run38680555945 tests7950b335; shared disposable workers are online and executing earlier queued jobs. No gate or runner setting was changed by this feature.

Production fixture preparation while refreshed CI queued: at the existing synthetic DB115 QA customer/truck, created outside entry `DB129 Production Receipt QA`, Oct1,2026, reference DB129-PRODUCTION-QA, explicit synthetic/no-service/no-billing description. Mileage and cost left unknown. Existing DB119 UI saved it (active outside count0→1); this is fixture preparation on the previous production build, not receipt-feature acceptance. Screenshot `/tmp/db128-qa/production-fixture-baseline.png`, measured1280×720. Must void this new synthetic entry after acceptance or before ending a blocked release.

## Merge and deployment

All six protected gates passed on7950b335a78da0c00eacc23afac467efa386ef7e (run38680555945). PR533 merged2d9c8b1733eff8da7da78bf93e481077d0d7b2f8 at2026-10-15T04:50:05Z. Checked and merged trees both4c35bd5143fe78a329cb8a7d3a812e68b4a601e0. No protection bypass. Deployment/migration and production acceptance pending.

Independent integration recheck confirms all six checks are required by strict main protection and actually passed. Final full frontend164files/1622tests, backend3195passed/162skipped in850.50s, Playwright5passed in13.7s. All17 application Git blobs retain the approved manifest. Web299db445-d870-4a21-882d-97cadbe2f8c6 and Worker20742f2c-9065-4f96-9759-c9b828c23371 building exact2d9c8b17.

## Production visual gate failure

Web and Worker SUCCESS at2d9c8b17; startup log confirms171→172, readiness database/Redis healthy. Authenticated asset index-axINRxWi.js exposes receipt controls. Production synthetic service a10024be-93d9-4f85-b56c-58ff71a47809: PDF618bytes uploaded/downloaded byte-identically; authenticated download private/no-store/nosniff/no-referrer/octет-stream/attachment/CSP sandbox. Anonymous route401private. Duplicate copy rejected, disguisedHTMLPDF rejected, >5MiB blocked. Screenshot `/tmp/db128-qa/production-desktop.png` then revealed unreadable inherited dark foreground in Night Shop across receipts and pre-existing outside-history text. Local light-theme evidence missed this production theme defect. Visual acceptance failed; scoped theme correction required before Done. One PDF remains attached to the active synthetic QA entry; final void cleanup pending.

## Scoped Night Shop correction

Branch `codex/outside-history-theme` changes only outside-history/receipt CSS: workspace foreground/muted/border tokens, themed surfaces, readable hover/status/error colors, and scoped form overrides for the shell's forced light input background. No API, schema, layout, or lifecycle change. 85 focused frontend tests, app TypeScript, changed-source lint and whitespace checks pass. Exact two-file preview overlay preserved unrelated work. Local sign-in expired; corrected actual light/Night Shop desktop/mobile acceptance remains pending before merge.

Production functional continuation on2d9c8b17: 390px blocked PNG upload retained its selection; explicit retry saved exactly one PNG. Remove Escape returned focus; reasoned remove→Show removed→Restore retained uploaded/removed/restored actor/time events. 320px restored PNG browser download matches original bytes. Document width320, all receipt buttons44px, one slide-panel-content scroller. 740x400 Cancel and named Close both dismissed removal without mutation. These are functional results on the visually defective version, not visual acceptance. PDF and PNG retained on synthetic entry; final void cleanup pending.

Production functional lifecycle completed before CSS release: JPEG upload/download byte-identical (4,321 bytes). Full reload retained receipts. New-order Cancel returned the exact customer/truck. Temporarily restored only existing synthetic order bce9b62b-a7e3-4ba9-a740-6ced6857e9b3 to verify repair-order header→View vehicle history→same receipts→mobile Back through customer→same order, then soft-deleted it back to its baseline. Zero-dollar order/customer values, no tracked time, and unknown current mileage remained unchanged. Voided only new outside entry a10024be-93d9-4f85-b56c-58ff71a47809; active outside history0/native history0. All three receipts retain metadata/history while upload/download/remove are disabled. Previous DB119 voided entry untouched. Network block removed and debugger Network disabled. Corrected visual acceptance still pending.

CSS correction draft [PR535](https://github.com/mecaniser/truck-pit-stop/pull/535), e4b1e426, protected run38684645801. Local staff login required to complete the explicit both-theme desktop/mobile gate.

## PR535 resumed acceptance, Oct15

All six protected checks passed at e4b1e426 (run38684645801): frontend164 files, backend3195passed/162skipped, criticalbackend530passed/11skipped, Playwright5passed; no bypass. Current main remains2d9c8b17. Local frontend5174 was absent on resume; restarted only the approved preview with validated preview branch/SHA and API origin8001. VitePID35642, preview/frontend; Docker dieselbridge_api_ets-workflow-parity still binds preview/backend to /app, development database postgres/truckpitstop_ets_workflow_parity_20261012, migration172. Direct and proxied readiness healthy; both corrected CSS files byte-identical to implementation. No database/provider/flag changes. Local actual route still reports expired session; user asked to sign in after runtime restoration. Production authenticated fixture loads successfully. Runtime process/HTTP aligned; corrected local browser acceptance not yet established.

Corrected local browser acceptance PASSED: authenticated1280×800 Night Shop and Day Shop show readable titles, filenames, metadata and controls.390×700 Night receipt removal form and320×700 Day form have44px buttons,16px textarea, no horizontal overflow and one slide-panel-content scroller. Escape returns focus; named Close and landscape Cancel dismiss without mutation.740×400 Day outside-service editor and desktop Night editor show readable themed fields; all six Night editor fields resolve light text over dark overlay surfaces. Original Night Shop preference restored. Only DB128 synthetic entry was restored for testing and voided again; previous DB119 active entry retained. Proof files `/tmp/db128-qa/pr535-local-{night-desktop,night-mobile,light-desktop,light-mobile,light-landscape,night-editor}.png`. Preview5174 is aligned and browser-verified for the scoped correction.

PR535 merged at2026-10-15T14:27:16Z as1a7b629872cd0231aa90a16f83ebeedf5eabd123. Exact CI sourcee4b1e426 and merge trees both499f2081e23f4d864b5cfbe874af4781a7763964. No bypass; frontend CSS-only correction. Production deployment and both-theme visual acceptance pending.


## Corrected production acceptance, Oct15

PR535 Web deployment `bb9eeb6a-fc30-4c68-8a5e-b1cdc955db4b` succeeded at exact merge `1a7b629872cd0231aa90a16f83ebeedf5eabd123`. Final public `/build-version` independently returns the same SHA (built2026-10-15T14:30:34.111Z); `/health`200alive and `/health/ready`200ready with database/Redis healthy. Evidence `/tmp/db128-qa/pr535-final-health.json`. This CSS correction requires no new migration or worker behavior. Original receipt feature Web/Worker and migration172 release evidence remains above.

Authenticated production browser loaded new entry `index-pTZ_N61I.js` and corrected stylesheet `useCustomerVehicleGroups-SJNvYegu.css`. An existing document initially retained the prior release assets; normal reload resolved that stale-document observation. Only screenshots from the confirmed new assets count for corrected acceptance.

Actual desktop1280×720 in both Night Shop and Day Shop shows readable receipt filenames, metadata, action controls and history. Night390×700 and Day320×700 portrait show readable removal forms,16px textareas,44px receipt actions, no horizontal document overflow and exactly one slide-panel-content scroller. Day740×400 landscape editor fields and footer actions remain reachable by scrolling and keyboard focus; Cancel returns without mutation. Day named Close and Cancel, and Night Escape with focus return, passed. Production preference restored to original Day Shop. Mobile evidence uses browser viewport/touch emulation, not a physical phone or native keyboard.

Production PDF download and restored PNG download match original bytes. Night reasoned removal→Show removed→Restore adds the expected immutable actor/time/reason events. Full document navigation retains all three PDF/PNG/JPEG receipts. Prior full invalid/oversize/duplicate/retry, customer/order navigation and financial-isolation acceptance is recorded above; the CSS correction did not alter those contracts.

Cleanup completed: only synthetic outside entry `a10024be-93d9-4f85-b56c-58ff71a47809` was restored for this correction and voided again with reason “PR535 verification complete. Synthetic QA only; return to voided baseline.” All three files retain metadata/history while upload/download/remove are disabled. Previous DB119 voided entry untouched. Show voided off confirms active outside history0; native history remains0. No real customer work or billing changed. Temporary metrics/touch/network settings cleared and temporary production tabs closed.

Screenshots inspected: `/tmp/db128-qa/pr535-production-night-desktop.png`, `pr535-production-night-mobile.png`, `pr535-production-light-desktop.png`, `pr535-production-light-mobile.png`, `pr535-production-light-landscape.png`, `pr535-production-light-landscape-actions.png`, `pr535-production-cleanup.png`. Independent final Security and production QA GO received; the prior visual NO-GO is superseded. [Independent review](DB129_SECURITY_QA.md) records its evidence boundaries. DB129 is Done with no required unresolved follow-up.
