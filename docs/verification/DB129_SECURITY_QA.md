# DB-129 independent Security and QA gate

Historical ID correction (2026-10-15): this receipt outcome was reviewed as DB-128 before main PR530 assigned that ID to a separate infrastructure item. The canonical receipt item is now DB-129. Existing `/tmp/db128*` evidence paths, fixture names and original execution records retain their historical identifiers. This documentation-only correction does not change the reviewed application or test behavior.

Reviewer: fresh independent Security & QA agent; no implementation or design participation. Scope: private outside-shop receipt storage, authorization, request handling, replay/concurrency, migration, frontend isolation, and owner-provided browser acceptance. Only this verification record is owned by the reviewer.

Review date: 2026-10-14. Worktree: `ets-checkpoint-merge/truck-pit-stop`; branch `codex/external-service-receipts`; starting HEAD `d07759a43fd8905ebf9f7a95dac36d501c0d90a5`, with implementation uncommitted and still in progress. The local-runtime skill was read; this review does not start, restart, or control browser/runtime services.

## Gate status

**Independent Security GO and local QA GO — 2026-10-15 03:49UTC (Oct14 local).** All initial findings are resolved, final focused checks pass, and the local authenticated workflow plus PostgreSQL race/migration evidence has been reviewed. Backend & Integrations remains accountable. No unresolved implementation blocker was found.

This approves progression to release gates; it does not mark DB-129 Done or approve production solely from local evidence. Protected CI, current integration migration head, merge/deploy SHA, production readiness and the scoped synthetic production workflow remain required. The delivery owner records those separately.

ID-correction recheck at branch HEAD `e3918085c47bf98ec99b692cc2c8036832d1334a`: all17 reviewed implementation/migration files retain manifest SHA256 `71a5b40e17647e6c4935c5030707c1aee4e96d639568ba8fdd470da7cd199df3`. The same application manifest remains Security GO and local QA GO. The delivery owner will rerun protected CI after integrating current main; this recheck is not a claim that the integration/deployment gate has passed.

## Initial findings returned to owner

1. **P1 — alternate UUID spelling bypasses the receipt middleware boundary.** `receipt_paths.py` initially recognizes only dashed UUID route segments. Pydantic's UUID validator accepts compact hex, braces and `urn:uuid:` forms, so valid receipt routes using those spellings re-enter generic idempotency buffering and Redis response replay. Reproduced with the current validator and matcher: all three alternate forms validate as the same UUID while `is_receipt_path()` returns false. This defeats the required current authorization and database-owned replay boundary.
2. **P1 — database failure diagnostics can expose private file content.** The engine initially omits SQLAlchemy parameter hiding and the generic database exception handler logs/persists exception strings and tracebacks. A synthetic `IntegrityError` whose bound blob value is `SYNTHETIC_RECEIPT_PRIVATE_BYTES` retains that marker through the application's `redact_text()`. Metadata inserts can similarly carry filename/hash. Receipt write failures must remain diagnosable without file data, names or hashes entering diagnostics.
3. **P2 — application headers overwrite download containment policy.** `main.add_security_headers` initially overwrites the receipt download's `Referrer-Policy: no-referrer` with `strict-origin-when-cross-origin`. Verify the final fully assembled application response, not just the route helper.
4. **P2 — outer request-size errors lack receipt cache policy.** Actual `RequestBodyLimitMiddleware` outside `CacheControlMiddleware` returns an oversized remove request's 413 without Cache-Control or Pragma. Reproduced with an in-process ASGI harness and synthetic bytes. Receipt errors from ingress and global failures must be private/noncacheable.

Additional deployment check sent to owner: the application CORS allowlist initially omits the upload's three new metadata headers. Verify intended cross-origin support with a real preflight test; a same-origin Vite proxy does not establish cross-origin acceptance.

Remediation recheck: the owners added identity-segment receipt matching, receipt route exception containment, SQL parameter hiding, private outer headers, receipt-specific diagnostic suppression and the upload CORS headers. A second error-policy finding identified the global exception handler running from outer `ServerErrorMiddleware`, whose unexpected-error response bypasses `add_security_headers`. The owner corrected that response too. The final privacy test builds a real FastAPI middleware stack with the production handler/header function and an injected failing middleware; it confirms private500 headers and suppression of file-derived persisted diagnostics. All initial findings are resolved at2026-10-15 03:43UTC (Oct14 local).

## Final independent automated checks

- `/tmp/db128-backend-venv/bin/python -m pytest tests/test_external_service_receipts.py tests/test_external_receipt_privacy_boundary.py tests/test_database_resilience.py tests/test_external_service.py -q --tb=short`: **117 passed**,19.02s (29 receipt,11 privacy,33 database/error resilience,44 existing service cases). This includes lifecycle/replay, no native side effects, metadata-only queries, roles/tenant/target checks, actual oversized image headers, bounded file validation, header/stream handling, pre-body authorization, private diagnostics, CORS and the outer global500 path.
- `npm test -- --run src/features/external-services/ExternalServiceReceipts.test.tsx src/features/external-services/ExternalServiceHistory.test.tsx`: **85 passed**,4.31s (55 receipt,30 existing history). This covers malformed/foreign data, download validation and URL revocation, scope/session transitions and late results, retry identity, stale drafts, retained quotas, remove/restore and voided controls.
- `git diff --check`: clean. Final reviewed17 implementation/migration files' sorted `SHA256 path` manifest hash: `71a5b40e17647e6c4935c5030707c1aee4e96d639568ba8fdd470da7cd199df3` (HEAD still `d07759a43fd8905ebf9f7a95dac36d501c0d90a5`, implementation uncommitted).

## Runtime evidence reviewed

Reviewed the completed owner record [DB129_EXTERNAL_SERVICE_RECEIPTS.md](DB129_EXTERNAL_SERVICE_RECEIPTS.md) and independently inspected all four parent-provided screenshots: `/tmp/db128-qa/local-desktop.png`, `local-mobile-390.png`, `local-mobile-320.png`, `local-landscape.png`. Desktop,320/390 portrait and740x400 landscape show readable receipt metadata, whole action labels, recovery history and removal controls without visible horizontal clipping.

The parent executed the authenticated browser journey; this reviewer did not control the browser. The record documents exact-byte PDF and restored PNG downloads, reload persistence, duplicate/invalid/oversize rejection, failed mobile upload followed by explicit one-copy retry, removal cancellation/focus and attributed remove/restore, customer/repair-order return navigation, voided-service restrictions, unchanged native values and single-scroll measurements. JPEG content handling was verified by backend tests; the documented browser upload/download paths used PDF and PNG. Mobile evidence is viewport/touch emulation, not physical-device certification. The approved split preview has scoped-source comparison and migration172/readiness evidence; it does not represent all unrelated main changes.

## PostgreSQL and migration evidence reviewed

Independently read the backend owner's secret-free runner and durable output under `/tmp/db128-backend-evidence/`. Execution at2026-10-15 03:48:05–03:48:17UTC targets only `127.0.0.1:5432/db110_test_db128_receipts`, the opt-in isolated synthetic fixture database. `runtime-receipt.log` records the worktree, branch, HEAD and successful exit codes; `postgres-tests.log` records **10 passed**,7.48s. The source tests cover identical upload replay/deduplication, cross-vehicle request collision with no losing rows, capacity including removed receipts, revision winner/replay, both upload-versus-void orders, both upload-versus-merge orders, and actual composite FK/unique/type/size constraints. Reviewed the fixture's reverse-order tenant cleanup.

`downgrade-172-171.log`, `upgrade-171-172.log` and `migration-current.log` show successful disposable-test172→171→172 and final `172_external_service_receipts (head)`. The migration is additive with no native financial backfill. The owner also documents preserved preview upgrade through172. These results were executed by the backend owner and independently reviewed here; this reviewer did not run a migration against the preview or production database.

## Accepted security limits and release conditions

The PDF check establishes a bounded envelope, not structural validation or malware scanning. Security GO accepts the documented private, authenticated, octet-stream forced-download boundary with no inline preview, OCR, public URL or rendering. Images are decoded only within the byte/dimension/pixel/single-frame limits. Any future preview or sharing capability requires a new security review.

Rollback must retain all three additive receipt tables and uploaded data. Do not downgrade/drop them after real uploads; the downgrade evidence above is for the disposable fixture database only. Roll back application code on disclosure, duplicate/orphan files, limit bypass, failed recovery/download or financial/PM effects. Release must verify the same synthetic workflow, health and rollback signals on the actual deployed revision before closing the board item.

## Source observations

- The authorized blob SELECT joins tenant, current vehicle, exact service record and receipt, and repeats active lifecycle checks. It does not rely solely on the earlier metadata checks.
- Storage is bounded raw-body upload, deferred/raiseload private bytes, retained per-record deduplication, and independent receipt versions/events. Parent service/financial changes are absent from the receipt service.
- The app uses authenticated blob downloads, validates response type/size, creates temporary object URLs and revokes them. Tenant/actor/role/session/vehicle/record scope changes remount receipt state and cancel/discard stale results.
- These observations are not a substitute for final negative HTTP, PostgreSQL concurrency, migration and browser acceptance evidence.

## Reproduction boundary

All independent reproduction so far uses synthetic constants and in-process validation/ASGI calls. No customer document, production mutation, browser, server, provider setting, or unrelated file was touched. Python: `/Users/sergio_m1_promax/GitHub/truck-pit-stop/backend/venv/bin/python` (Pillow 10.1.0 available). No secrets were printed.
