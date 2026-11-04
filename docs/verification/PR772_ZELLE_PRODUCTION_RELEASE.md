# PR772 Zelle release

Accountable: Backend & Integrations. Release & Reliability executing. User explicitly approved desktop/mobile previews and authorized merge/deployment plus read-only customer, guest and shop acceptance.

## Merge and checks

- PR772 corrected head `51f8f37d0f73ff5f20cda0b1825fb3920728ff21`: all seven checks passed, run41886417690. Protected backend1021 passed/67 explicit skips; disjoint full backend4619 passed/462 explicit skips. Frontend checks/build and full partition2308 passed; browser smoke passed.
- Independent QA/Security source GO, plus independent122/122 test-fixture correction pass. Product source unchanged by correction; no safeguards weakened.
- Squash merge `4519098d1b6c1cca5d1e5176c0c2702c06bded3b`, 2026-11-04T18:30:25Z. Checked head and merged tree are identical.
- No migration or financial backfill; schema200 expected.

## Deployment

Final Web913c83d7-1385-45f7-ac08-3436a9b6226c and Worker1cd4c4cd-7346-4dc3-b792-8e53070f17b1 succeeded on the exact merge. Both runtime Git metadata and all14 reviewed backend/frontend source hashes match4519098d. Public www/api build stamps match; schema200, database/Redis, provider readiness and existing gates pass. Existing registered expiry task retains60-second schedule; no task manually run.

The first automatic Web build initially exposed unresolved metadata that looked incorrect; its final resolved manifest was correct. An unnecessary clean-checkout upload also succeeded but lacked the build-time Git stamp. A final exact-commit repository redeploy restored public version metadata and its staleness guard. No service configuration, financial record, provider credential or gate was changed by these deployments. Final manifests use checked-in Dockerfile/preflight/uvicorn/health and Celery worker/Beat settings. Bounded runtime logs show no actual ERROR/CRITICAL/Traceback markers. Rollback is code-only to the prior immutable healthy image, with no schema downgrade or financial reversal.

## Preservation and acceptance boundary

No transfer reports, receipt confirmations, release/cancel actions, real payments or test notifications are authorized. Existing financial records remain protected. One unsent guest access token was generated through the existing service, bounded to one hour, using an existing native invoice with pre-existing settlement; exact tenant/customer/invoice binding and unchanged financial fingerprints verified. Token and private customer details are excluded from this report.

Existing customer invoice has no available balance because of historical pending attempts. Live customer checks must preserve these reservations, show correct requested amounts and refresh feedback; no assertion that historical requests prove a transfer. Guest instructions can exercise full/partial read-only draft views. Shop review must open the exact request and amount without confirming receipt.

[Implementation evidence](DB149Z_ZELLE_CONFIRMATION_2026_11_04.md).

## Live browser acceptance so far

- Signed-in customer desktop1440px and mobile390px: one pending summary, collapsed activity by default, accurate requested Zelle/card amounts, visible Checking and No change yet feedback; no horizontal overflow. Existing fully reserved balance preserved.
- Guest desktop1440px and mobile390px: full and partial instructions, optional sender/details, explicit final report button and safe Back verified without submitting. A partial draft showed10.00 and31.42 remaining after confirmation; no transfer assertion created. Repeated instructions/Back generated zero network requests, with complete untruncated observation. Print remains an actual inline-PDF link.
- Actual shop Closeout queue displays one unverified Zelle request and exact168.44 requested amount. Opening its review dialog and final mobile capture are currently blocked by browser input availability, not claimed complete; user asked to close Chrome’s Window menu/unlock if needed.
- Financial comparison: invoice/payment/settlement/ledger/accounting/outbox/handoff protected hashes unchanged. One pre-existing pending card attempt has routine maintenance metadata updates; prospective all-column comparison proves only version, expires_at and updated_at changed, with all other columns and21 other attempts identical. Scheduled logs and no-provider-reference code branch corroborate retry maintenance without a provider charge. The initial whole-row digest alone cannot retrospectively name changed fields; that evidence limit is retained. No new reports or payment submissions.

Screenshots and financial receipts are private local artifacts; guest token, customer identities and production identifiers are excluded. Final post-browser snapshot and remaining shop gate are required before Done.
