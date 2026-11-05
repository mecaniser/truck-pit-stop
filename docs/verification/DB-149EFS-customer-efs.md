# DB-149EFS — Customer EFS submissions

Status: implemented and verified in the isolated runtime; ready for customer preview review. Not merged or deployed. Backend & Integrations accountable; Frontend & UX owns presentation. Independent QA/Security approved the final source and whole preview/PR scope at backend digest `707d2a4e8046e8b34b4ff9cee7a582acc148de4d2696ab7ac31f11bd4004c6df`, reviewed frontend, actual UI captures and final preservation receipts.

Contract: [customer-efs-submissions-v1](../contracts/customer-efs-submissions-v1.md). [Draft PR784](https://github.com/mecaniser/truck-pit-stop/pull/784), branch `codex/customer-efs-payments`, based on draft PR778 head `c4094ede907eb222592fc47aee99981d36ca2a75`. This EFS outcome is separately reviewable and targets the payment-request recovery branch in PR778. Protected main-branch release CI and production approval remain future release gates; local and independent checks above are the completed preview evidence.

## Customer flow

Card, Zelle and EFS are compact named methods, with full/partial amount selection kept separate. EFS uses a dedicated server capability and endpoint; it never enables generic customer fleet, Comchek or ACH submissions. Code entry is local and masked by default. Review shows the last four digits and exact amount, then requires explicit Submit for verification. Opening, editing and returning from review creates no payment request. Unknown submissions retry the identical body/key. Accepted submissions clear the raw draft. No code persists in browser storage, query caches or URLs.

EFS submission reserves only the chosen principal and enters the shop review queue. It never marks money received or an invoice paid. Authorized staff can explicitly reveal the code, perform merchant authorization outside the app, and attest the amount actually received with a separate merchant reference. Rejection/cancellation releases the exact local reservation and retains the code claim; retry uses a different code. History stays masked.

A genuine received difference remains held for review. The staff resolution screen displays the immutable observation, requires reason and a distinct one-time identity grant, and submits only the observation ID and versions. Canonical receipt allocation handles the actual amount; excess stays in existing credit/refund review and blocks further collection. No caller amount override or silent release.

## Local scope and readiness

New isolated frontend5176/API8019/database `customer_efs_qa`; old environments remain preserved. Customer and staff aliases are `efs-customer.localhost:5176` and `efs-shop.localhost:5176` to isolate preview cookies from earlier local environments. Only fictional records and new test keys are allowed. No real provider, EFS redemption, bank, email or SMS action; no existing financial-row correction.

Migration201, dedicated purpose-bound encryption keys and a stable fingerprint key are required. Intake is explicitly tenant opt-in through `EFS_CUSTOMER_ENABLED_TENANT_IDS`, empty by default. Only newly created fictional fixture tenants are enabled during verification. Production TPS activation and key configuration belong to a later authorized rollout. Intake disabled does not strand existing receipt/history/resolution workflows.

## Automated evidence

- Frontend full regression: 251 files and 2,817 tests passed. Focused payment/queue coverage passed 148 tests; the final four-file delta passed 76 tests, independently repeated by QA. Final staff received-state heading refinement passed 36 adjacent tests and ESLint.
- Typecheck, shared-controls check, production build and changed-source ESLint passed. Critical-test partition verification covers all 251 files with no overlap. Impeccable's static detector returned no findings on the four changed/new payment surfaces.
- Matching-image affected backend coverage passed 224 tests. Final EFS and resolution coverage passed 83 tests; EFS/security middleware coverage passed 70 tests. These overlap and are not additive totals.
- Owner and independent reviewer each passed seven real PostgreSQL migration/concurrency/notification cases. Independent review also passed the actual archived 001→200→201 migration and source-customer A→reviewed payer B receipt with a separate $100 card reservation preserved. Existing source and tenant boundaries stayed enforced.
- Corrected migration changes only the intended legacy fleet guard and adds deferred exact attempt/claim binding. All 202 preexisting tables and seeded financial rows remained unchanged; 161 other existing database functions remained identical. Five foreign keys validated; no claim backfill. Migration graph has one head at 201.
- Independent excess disposition tests passed both legitimate credit and refund cases. Actual full-app ASGI tests passed successful reveal, invalid body, demoted same-key replay and early oversized-request rejection, including private/no-store/no-referrer headers and no secret cache replay.
- Returned gate failures were corrected and independently closed: wrapped/whitespace/nested legacy evidence bypasses, actual migration146 trigger incompatibility and outer middleware overriding private response headers. Early frontend notice/copy regressions were corrected before the full passing run; no collection guard was weakened.

## Actual desktop/mobile acceptance

Normal UI login used newly created fictional customer and owner accounts, separate local host aliases, actual auth/source/accounting services and the actual migration chain. No domain/auth/source-proof mocks, provider redemption or real merchant authorization was used.

- Customer: Card/Zelle/EFS in one row; full and partial selection; masked local entry; review and explicit submit. Desktop 1440px, mobile 390px and compact 320px passed. Methods remain 44px tall, with no horizontal overflow.
- New fictional invoice `158f6067-cc68-48df-a756-c59d541ebdc1`: $100 of $268.44 submitted, exact shop queue request opened, explicit reveal/hide checked, simulated merchant reference and receipt attestation recorded. Exactly one Payment for $100; confirmed $100, pending $0, remaining $168.44. Customer history says Payment received and offers all three methods for the remainder.
- New guest invoice `92b75b6e-370d-46fc-a03b-9596d7b45be6`: $75 submitted and explicitly canceled; no Payment, pending $0, balance $268.44. Different-code retry reviewed without resubmission. Final copy uses ordinary customer language. Guest desktop/mobile parity passed.
- New full-payment preview invoice `0e189bd2-f62e-4ed1-8b1c-1d58dc2ff2c7`: $268.44 full review shown, with no attempt or Payment created; settlement remains version1.
- Shop: exact queue target, private reveal, disabled receipt action before authorization reference/attestation, desktop/mobile verification and truthful received-state details passed. Generic manual confirmation does not handle protected EFS codes.
- Ten separate actual API checkpoints passed: cancellation/replay/duplicate retention/new-code retry, reject/retry, exact receipt, forbidden generic bypass, immutable under-receipt resolution with fresh scoped grant, overpayment and source-collection excess holds, concurrent duplicate submissions, and EFS-ready/Card-unavailable readiness. No real payment occurred.

Review captures are the `customer-efs` local visualization artifacts presented in the Codex review, including `desktop-review.png`, `mobile-full-review.png`, `shop-desktop-review.png`, `shop-mobile-review.png`, `mobile-partial-received.png` and `guest-mobile-retry-review.png`.

## Preservation and release boundary

The final runtime receipt verifies all six prior databases, three prior application stacks and every original cloned financial row unchanged. Only newly created fictional test records changed. Low-level provider HTTP, email and SMS counters are zero. Production was not changed.

Local evidence: `/tmp/customer-efs-qa/final-runtime-preservation-receipt-private.json`, `/tmp/customer-efs-qa/efs-api-acceptance-receipt-private.json`, `/tmp/customer-efs-qa/backend-freeze-final.json`; independent migration, lifecycle and preservation receipts use `/tmp/customer-efs-independent-*-receipt.json`. Private credentials, codes, keys and full private receipts are not committed.

This item is not released or Done. Deployment requires approval, the PR778 dependency, protected exact-head release checks, migration201 and configured dedicated encryption/fingerprint keys. Production TPS acceptance must be separately enabled in the exact tenant allowlist; other tenants remain disabled. Rollback disables new EFS intake while retaining old decrypt keys, immutable claims and access to received-money resolution. Never downgrade/remove retained claims or rewrite existing financial records.

## Centered payment methods — November 4 preview refinement

Frontend & UX owns this Fast UI follow-up in draft PR784. The only product diff changes customer/guest tender alignment classes to center each icon-and-label group. Staff alignment, handlers, selection logic, request bodies, amount handling and all backend files remain unchanged.

Runtime revalidated at branch `codex/customer-efs-payments`, starting HEAD `be4236a9` plus this class-only edit: Vite PID92596/source `/private/tmp/customer-efs-payments/frontend`, customer preview `http://efs-customer.localhost:5176/portal/invoices/0e189bd2-f62e-4ed1-8b1c-1d58dc2ff2c7`, effective API origin8019, mounted backend `/tmp/customer-efs-payments/backend`, isolated `customer_efs_qa` test DB. Readiness confirms database/Redis ready. Aligned and browser-verified; no restart, migration or reseeding.

37 existing EFS/Zelle component tests and changed-source ESLint passed. Signed-in desktop1440px and mobile390/320px show all three icon-label groups centered to within0.01px, each44px high, with no horizontal overflow. Arrow-key selection Card→Zelle→EFS remains functional. Only local method selection was exercised: no payment submitted or financial record changed. New review captures are `customer-efs/centered-methods-desktop.png` and `customer-efs/centered-methods-mobile.png`. No merge or deployment.
