# DB-048 reviewed test reservation: independent QA

Date: 2026-10-29 (America/New_York).
Reviewer: fresh QA agent `payment_refresh_qa`; no application implementation edits.
Implementation owner: Backend & Integrations / root.
Branch: `codex/reviewed-test-cash-ancestry`, base `4457525009a53bfc7a569418c632f5f47706cc6b`.
Contract: `docs/contracts/db048-owner-attested-test-cash-ancestry.md`.

## Initial gate — NO-GO, returned to implementation

The new helper and two ancestry integrations were reviewed against the Architecture contract. Independent existing/new suite run passes **113/113**:

```sh
DATABASE_URL=sqlite+aiosqlite:///:memory: uv run --no-project --python 3.11 --with-requirements backend/requirements-dev.txt python -m pytest backend/tests/test_db048_reviewed_test_cash.py backend/tests/test_db048_cash.py backend/tests/test_db048_owner_attested_cash.py backend/tests/test_db048_reviewed_sandbox_cash.py -q
```

The positive new integration test verifies actual fixture cash confirmation, cancelled predecessor/attempt/settlement/terminal history digests unchanged, one local receipt, no accounting link and no provider request. Existing suites retain owner-attestation/signed-review and ordinary cash safeguards. Additional private challenge tests found two contract violations:

1. **Release-time inconsistency is accepted.** Starting with `reviewed(...)`, update the failed predecessor attempt's `failed_at` to20days in the future while leaving its terminal ledger event unchanged. `reviewed_test_ancestor(...)` returnsTrue. The contract requires terminal release to agree with failed state/time; this must fail closed.
2. **Provider identity can be hidden inside maintenance evidence.** Starting with the same qualifying history, update the maintenance event's `evidence_snapshot.provider_account` to `{"provider_charge_id":"real-charge"}`. The helper returnsTrue because it checks only top-level allowed keys. The contract permits a non-money provider-account configuration snapshot, not a nested charge/intent/reference identity.

Both expected-denial tests independently fail on the initial implementation (**2 failed**). The private reproducible harness is `backend/tests/qa_db048_reviewed_test_cash.py` (untracked; do not include without owner review). Its first hidden-dot filename caused a pytest import collection error; renaming to the valid module filename enabled the two actual reproductions. No application source was changed by QA.

The owner received exact reproduction paths and must return corrected source plus permanent regression tests for a fresh gate. No final QA approval or release acceptance is issued at this stage.

## Scope and safety

Only isolated SQLite fixtures and source inspection were used. No production database, payment, provider, accounting, customer, tenant flag or credentials were accessed/mutated by this QA work. No browser or local application server was started; read-only review/automated tests do not require local runtime startup. The unchanged frontend/API contract does not require repeating the earlier payment-queue browser fixture gate; actual deployed Cash availability remains the root release owner's separate read-only acceptance.

## Fresh gate after owner corrections — GO

Independent rerun completed2026-10-29 20:46UTC /16:46EDT: **138/138 passed**, including both original private failure reproductions. This supersedes the initial NO-GO for the corrected source only; the initial failure evidence remains above.

```sh
DATABASE_URL=sqlite+aiosqlite:///:memory: uv run --no-project --python 3.11 --with-requirements backend/requirements-dev.txt python -m pytest backend/tests/test_db048_reviewed_test_cash.py backend/tests/test_db048_cash.py backend/tests/test_db048_owner_attested_cash.py backend/tests/test_db048_reviewed_sandbox_cash.py backend/tests/qa_db048_reviewed_test_cash.py -q
```

Corrected source review confirms:

- Release and failed timestamps normalize SQLite naive timestamps as UTC, reject pre-creation/arbitrarily future/inconsistent dates, and use Architecture's explicit five-minute transaction-start/wall-clock bound. The new legitimate two-minute transaction offset test passes; the original20-day drift challenge now denies.
- Maintenance evidence has exact keys, scalar string/null provider account equal to the attempt snapshot, no provider intent and zero money. The original nested `provider_charge_id` challenge now denies.
- Creation and terminal evidence use closed key sets; creation/maintenance/terminal states must form unpaid→payment_pending→unpaid. Terminal additions with hidden provider identity, creation with hidden charge/paid state, and nonempty attempt manual evidence deny.
- New negatives also cover any parent settlement money, an unlinked parent receipt, missing/wrong pending snapshots, hidden top-level charge, nonzero maintenance delta, sequence gaps, second failed attempts, foreign/inactive/unprivileged actors and deleted/nonvoided/wrong-customer parents.
- Both helper reads and final cash confirmation still use the existing eligibility path. Actual confirmation obtains the tenant financial serialization lock, reloads the current invoice, locks/reloads ancestry and proof rows, and rejects new history before receipt creation. No new endpoint, form input, provider contact, state rewrite or migration was added.
- Existing export/accounting restrictions and signed owner-review fingerprint behavior remain in the pass matrix; the narrow recognition is consumed only after predecessor accounting checks and skips only the validated generic historical-attempt/ledger block.

Reviewed implementation file SHA-256 values:

```text
feccdf64063ec49c32523c3f37e83aac289adc5be39865e7a6554ca168ecb052  backend/app/services/invoice_test_attempt_review.py
2db68a76d2ef8c43fa57dd2b60b42fdd2453dcfc61e9e45ad32349229167c673  backend/app/services/invoice_cash_service.py
21d26127e72386fcf420bc450bac99be4feed5dda4828ee0a909bb8c35cc69fa  backend/tests/test_db048_reviewed_test_cash.py
```

`git diff --check` passes. Only existing SQLAlchemy/Pydantic deprecation warnings were emitted by the matrix. An additional lint-tool attempt could not run because Ruff is not installed in the approved requirements-dev environment; this is a tooling availability limit, not a successful lint result. Root retains the normal protected CI/lint gate.

**Independent QA GO for this corrected backend implementation and isolated automated behavior.** Independent Security, protected CI, approved merge/deployment and actual signed-in Cash availability are separate release gates. No additional frontend fixture pass is required for this follow-up because UI/API contracts are unchanged; the earlier exact desktop/mobile queue-refresh runtime gate remains separately recorded. Do not submit a real cash receipt merely to prove availability. No application source was authored by this reviewer and no production/provider/payment mutation was performed during this gate.
