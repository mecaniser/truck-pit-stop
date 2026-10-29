# DB-048 fresh-request cash confirmation — independent Security gate

Reviewer: `pending_release_security`. Date: 2026-10-29. Owner/implementer: root, Backend & Integrations. Branch: `codex/cash-confirmation-customer-load`, base `e8f5feae146b6209e1a4e06de85a822ef88ecb99`.

## Result

**GO for reviewed source and focused automated behavior.** This is independent Security evidence, not production payment, merge/deployment or runtime acceptance evidence. Reviewer made no application/test edits, production calls, provider calls or financial mutations.

The defect occurs when the ancestry reader refreshes the order and expires its customer relationship. The old expression could initiate implicit async ORM I/O while evaluating the paid-outcome enqueue arguments. The change explicitly awaits loading the same order's customer after locked eligibility, then holds those request-local order/customer objects for the existing paid transition and outcome enqueue. It introduces no shared cache or cross-request identity reuse.

## Boundary review

- Existing staff/payment permission, active tenant/customer/order, invoice lifecycle, settlement tenant/customer linkage, full-balance, expected-version and idempotency checks remain unchanged and precede the new load.
- The existing tenant financial lock and locked ancestry/accounting proof remain in force. The explicit relationship load follows successful locked eligibility and precedes receipt/status changes. The same checked order is retained through final enqueue.
- Same-key replay still returns before the new load and cannot create another receipt. No new mutation, provider dispatch, retry, credential, endpoint, schema or migration is added.
- Cash accounting policy, invoice/order paid transitions, immutable predecessor history and event delivery behavior are unchanged. The existing outcome service also validates tenant/order/customer resource coherence when enabled.
- Existing export reconciliation/provider guards are preserved; the new refresh is database I/O only. The reviewed test-ancestry no-provider path remains local.
- Commit still occurs only in the existing endpoint after the service returns. A precommit enqueue error therefore leaves the request transaction uncommitted; dependency session closure rolls it back. No new mid-service commit is present.

## Independent verification

Ran the new fresh-request endpoint regression plus existing cash, reviewed-test, owner-attested and reviewed-sandbox cash suites against isolated memory-backed SQLite:

```text
DATABASE_URL=sqlite+aiosqlite:///:memory: uv run --no-project --python 3.11 \
  --with-requirements backend/requirements-dev.txt python -m pytest \
  backend/tests/test_db048_cash_fresh_request.py \
  backend/tests/test_db048_cash.py \
  backend/tests/test_db048_reviewed_test_cash.py \
  backend/tests/test_db048_owner_attested_cash.py \
  backend/tests/test_db048_reviewed_sandbox_cash.py -q
```

**138 passed**, exit0; 39 existing SQLAlchemy/Pydantic deprecation warnings. The new regression uses separate AsyncSessions, invokes the actual endpoint commit/response path, verifies exactly one persisted receipt and paid invoice/order, proves fresh-session same-key replay does not duplicate, and checks Ready-to-Close exclusion/Closed Today inclusion/value total removal. Its second case injects an enqueue failure before endpoint commit, rolls back and verifies zero receipts with unpaid invoice/invoiced order. Existing suites retain tenant, permission, stale/pending/confirmed, accounting/history and malformed-attestation negative coverage. `git diff --check` passed.

Reviewed working-source SHA256:

- `backend/app/services/invoice_cash_service.py`: `f7dac25570b8cb0de9e01e3732daa41ead74aa1c30e0d57a2499b3ef53fa5526`
- `backend/tests/test_db048_cash_fresh_request.py`: `aa059c2492bdbe17d733c34883b93e0dd4342dd34491a0409366e8ebd8c94e85`

Protected PR CI, independent QA, approved merge/deployment and fresh actual-runtime acceptance remain release gates. Do not submit a real customer payment solely to verify the fix.
