# DB-048 cash confirmation fresh-request QA

Independent QA: `payment_refresh_qa`, 2026-10-29. No application implementation participation or production mutation.

**GO for the customer-loading correction and isolated endpoint behavior.** Branch `codex/cash-confirmation-customer-load`; reviewed base `e8f5feae146b6209e1a4e06de85a822ef88ecb99`, implementation `0c4e3066`, current integration head `46c2ee9a`. CI/merge/deployment and production acceptance remain separate release gates.

## Scope and findings

The ancestry proof can refresh the repair-order ORM object and expire its customer relationship. Prior cash confirmation later accessed that relationship synchronously while constructing the paid-invoice webhook, causing `MissingGreenlet` before the endpoint commit. Strong fixture references masked the issue in earlier same-session tests.

The correction explicitly awaits the repair-order `customer` relationship refresh after successful eligibility and retains local order/customer references through receipt creation and webhook enqueue. It changes no permission, tenant check, eligibility rule, invoice amount, accounting policy, idempotency contract, external provider call or migration.

Independent source inspection confirms the explicit load runs only after existing cash eligibility succeeds. The endpoint still commits after the full transaction, and retry returns the existing receipt under the existing idempotency rules. Capturing the loaded customer avoids a later implicit database request during enqueue.

## Automated evidence

The independent eight-file regression matrix produced **198 passing permanent tests**, covering:

- `test_db048_cash_fresh_request.py`;
- `test_db048_reviewed_test_cash.py`;
- `test_db048_cash.py`;
- `test_db048_owner_attested_cash.py`;
- `test_db048_reviewed_sandbox_cash.py`;
- `test_db048_cash_panel_availability.py`;
- `test_db048_cash_payment_timing.py`;
- `test_db048_nonfinancial_history_outbox.py`.

All used `DATABASE_URL=sqlite+aiosqlite:///:memory:` and the approved Python3.11 requirements-dev environment. Only existing SQLAlchemy/Pydantic deprecation warnings appeared.

The fresh-session tests establish the actual endpoint boundary with separately opened `AsyncSession`s:

1. Before confirmation, the order appears in Ready to Close and its queue value is positive.
2. Confirmation commits a paid settlement, invoice and repair order, with exactly one Payment row.
3. Repeating the same request/idempotency key returns the same receipt; no duplicate payment is created.
4. A subsequent request finds the order absent from Ready to Close, present in Closed Today, and the Ready-to-Close count/value both zero.
5. An injected paid-webhook enqueue exception before commit, followed by rollback, leaves zero Payment rows, the invoice sent/unpaid with null `paid_at`, and the repair order invoiced.

## Independent red proof

Private harness `backend/tests/qa_db048_cash_fresh_request_red.py` loads only the previous deployed `confirm_full_cash` function from explicit commit `e8f5feae146b6209e1a4e06de85a822ef88ecb99` into an in-memory test namespace and invokes the same fresh endpoint fixture. It asserts the previous function raises `MissingGreenlet`: **1/1 passed**. No application file is replaced or edited.

The initial private proof used dynamic `HEAD` and passed before the root commit. When included at the end of the broader matrix, root had advanced HEAD to the fixed implementation; the private assertion therefore correctly reported “did not raise” while all198 permanent tests passed. Pinning the historical commit removes that moving-target artifact; the pinned red proof passes. This was a harness-target race, not a corrected-source failure.

An earlier matrix was started while the owner strengthened the fresh test and corrected UUID/string comparisons; its closed-today assertion used the older compiled test while traceback source had changed. The final saved test and subsequent matrix pass supersede that intermediate result.

## Reviewed source identity

```text
f7dac25570b8cb0de9e01e3732daa41ead74aa1c30e0d57a2499b3ef53fa5526  backend/app/services/invoice_cash_service.py
aa059c2492bdbe17d733c34883b93e0dd4342dd34491a0409366e8ebd8c94e85  backend/tests/test_db048_cash_fresh_request.py
```

These hashes remained unchanged through the root's commit/docs integration during QA. `git diff --check` passed.

## Limits

This gate uses disposable SQLite fixtures and direct endpoint function calls, not a live provider or a production payment submission. No production state was accessed or changed by this reviewer. No local app/browser server was needed for this unchanged frontend/API contract; the existing desktop/mobile queue-refresh fixture acceptance is recorded separately. Root owns protected CI, approved release, exact deployed revision and safe production verification. Do not replay the user's payment merely to prove the release.

Final pinned check on saved integration source: **3/3 passed** (`test_db048_cash_fresh_request.py` plus `qa_db048_cash_fresh_request_red.py`,6.84s). This independently verifies both corrected endpoint cases and the historical red proof together after the root commit, without a moving HEAD target.
