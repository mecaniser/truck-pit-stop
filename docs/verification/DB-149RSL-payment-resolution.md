# DB-149RSL — Payment request resolution

Status: implemented; isolated desktop/mobile acceptance passed. Draft review and protected integration CI pending. Not merged or deployed.

Accountable owner: Backend & Integrations. Contract: [payment-attempt-resolution-v1](../contracts/payment-attempt-resolution-v1.md).

## Behavior

- Customer and guest can cancel an unsent Zelle request only after explicitly confirming no transfer was sent. Cancellation ends the local request; it cannot cancel a bank transfer.
- New card checkouts that have not been submitted can be canceled. Submitted or historical card attempts remain reserved until authoritative cancellation, terminal provider evidence, or a genuine receipt establishes the outcome.
- Shop review combines card and Zelle requests, opens the exact selected attempt, and requires a distinct one-time password verification for evidence-backed release. Missing historical binding remains blocked.
- Retrying opens current full or partial payment choices. It never submits a replacement payment automatically. Uncertain command retries reuse the same body and key.
- Genuine receipts arriving during or after cancellation remain recorded through existing settlement and overpayment handling.

## Scope and records

Worktree `/tmp/payment-attempt-resolution`, branch `codex/payment-attempt-resolution`, baseline `e393684453354bdb2be50ccb5c60ea19a1539d94`. No migrations, production actions, existing-record corrections, or real provider/bank calls. Acceptance uses newly created fictional local records and disposable PostgreSQL schemas.

## Automated evidence

- Full frontend: 249 files, 2,783 tests passed before final button/copy refinements and two additional negative cases.
- Final focused frontend confirmation: 128 tests passed, including the real wire adapter and staff callback-focus regressions. Changed-source ESLint passed. Typecheck and production build passed; existing chunk-size warning remains.
- Staff queue: 90 focused tests passed, plus exact-attempt targeting regression.
- Impeccable detector: no findings in changed resolution controls, CSS, or summary surface.
- Historical cash compatibility: 84 direct cases and 21 consumer cases passed with direct synthetic historical fixtures; original assertions and marker policy preserved.
- Backend affected policy: 303 tests passed. Final authorization/savepoint slice: 38 passed, including actual HTTP staff release, concurrent revocation and received-money preservation. Dedicated PostgreSQL races: three passed.
- Independent source QA/Security: GO for final nine-file sorted path/hash map `49a6ca681fecd6a0db3d74a3f39d3c5fdc549804e329246e73cebfe92d9d6a1f` (owner aggregate `39499b9dfef7282c96c95d2e546708f1ae68b7ff4debf2d0c733d1f5e9637c2c`). Independent final checks include 38 resolution cases, two selected-customer-link cases, two cookie/origin cases, three PostgreSQL races, and 107 frontend cases.
- Initial broad backend run: 5,581 passed, 82 failed, 532 skipped while policy/fixtures were evolving. All 82 failures were classified as 80 historical-fixture consumers and two superseded policy expectations; corrected cases passed their focused reruns. Protected exact-head CI remains the full integration gate.

## Runtime acceptance

Isolated frontend5175/API8018, separate fictional database, final backend source loaded. Real browser login uses fictional customer/owner accounts; guest access uses an actual scoped local token. No auth/domain/source-proof mocks.

- Customer Zelle: explicit unsent checkbox, exact100 cancellation, pending0/full268.44 available, immutable history and one result announcement. Full and partial50 choices checked without payment submission.
- Unsubmitted card: real immutable submission protocol, no submission-start event, exact100 cancellation, no provider call or Payment, retry choices restored.
- Guest Zelle: own guest-subject attempt, explicit50 cancellation, full268.44 available, partial25 choice checked. Print remains the authorized PDF destination.
- Unknown submitted card: actual QBP service/endpoint reached an allowlisted low HTTP transport timeout. Card stayed held until exact stored binding, synthetic support case and actual one-time password grant authorized release. Exactly one terminal event, grant consumed, no Payment.
- Late fictional Zelle receipt: confirmed50 after cancellation; current balance218.44 and cancellation/receipt history preserved.
- Historical missing binding: read-only actual HTTP detail denies cancel, retry and evidence release; no protocol retrofit.
- Desktop1440 and mobile390 inspected. No horizontal overflow; mobile buttons and inputs44px. One bounded visual correction pass fixed field borders and callback focus; final confirmation passed.

Screenshots are local review artifacts under `/Users/sergio_m1_promax/.codex/visualizations/2026/10/31/01a1903f-abe6-7d20-bd1a-7bf7df5f4a4a/payment-resolution/`: `zelle-desktop-confirmation.png`, `zelle-mobile-confirmation.png`, `zelle-desktop-retry.png`, `zelle-mobile-retry.png`, `card-desktop-confirmation.png`, `card-mobile-confirmation.png`, `guest-mobile-retry.png`, `shop-desktop-review.png`, `shop-mobile-review.png`, `late-receipt-mobile.png`. Identifiers and amounts in these previews are fictional.

Existing live invoice and its payment attempts remain unchanged. Final independent runtime/visual QA and Security GO: all five old database full-table fingerprints, three old stack protected fingerprints, and preexisting rows in the new fictional database are exactly unchanged. Actual runtime source map matches the independently reviewed map. Schema remains200; migrations0; real external network/payment/email/SMS activity0. Low HTTP timeout fixtures are counted separately from real provider calls.

## Release boundary

Preview approval is required before merging or deploying this change. Do not clear existing pending attempts as part of release. Historical attempts require their own audited resolution with verified evidence. Roll back code if cross-account disclosure, duplicate reservation release, receipt loss, or unsafe unknown-card retry appears.
