# Zelle instructions for the reviewed invoice payer

Owner: Backend & Integrations; parent delivery item DB-149 release follow-up.
Branch: `codex/tps-zelle-read-access`, base `9ad6809e6700d2109e4654480de37215f7ba23d4`.

Architecture-approved scope: GET Zelle instructions uses exact principal/invoice/repair-order tenant binding and the existing `invoice_customer_access_clause`. Source collection reads additionally validate the active, exact, hash-bound `invoice_handoff` and reviewed customer. Ordinary customer and same-tenant staff response fields remain unchanged. No submission, charge, bank configuration, migration, or financial write.

Acceptance: reviewed payer B and ordinary owner can read configured destinations; original service customer A and foreign principals cannot. Archived source orders remain readable for a valid active collection. Missing, inactive, or forged handoffs are denied. Missing destinations remain the existing nullable DTO. GET performs no initialization, commit, flush, notification, or provider call.

## Local runtime preflight

Mandatory runtime and delivery skills read before implementation. Fresh isolated checkout `/private/tmp/tps-zelle-read-access` is on the exact fetched `origin/main` base above, initially clean. Default frontend 5173 has no listener; backend8000 belongs to an unrelated Docker runtime. Existing EFS API container is mounted read-only from `/tmp/customer-efs-payments/backend`, and was preserved. No server, environment file, database volume, or old worktree was changed.

Per explicit parent authorization, changed-route runtime acceptance uses an in-process ASGI app importing this checkout and a fresh disposable SQLite database per test, inside the existing matching backend test image with networking disabled. Dependency overrides provide fictional authenticated principals and the disposable database only; production ownership/handoff logic remains real. No local browser/frontend change is part of this fix, and no claim that this checkout is browser-served is made.

## Verification

Test-first regression: on the unchanged base, the ordinary customer read passed while the real reviewed-payer/archived-order case returned403 (1 pass /1 fail), matching the live defect.

Matching backend image `portal-booking-backend-tests:136b96d5-node22`, repository mounted at `/workspace`, no container network:

```sh
python -m pytest tests/test_zelle_explicit_confirmation_info_access.py tests/test_zelle_websocket_updates.py tests/test_zelle_explicit_confirmation.py tests/test_customer_efs_submissions.py -q
```

Result:97 passed (21 new access cases +76 existing Zelle/EFS cases); the final renamed critical-pattern collection also passed21/21. Every new case fingerprints tenant/invoice/settlement/attempt/ledger/payment/handoff/event rows before and after GET, rejects initializer/commit/flush/send/provider collaborators, and checks the session remains clean. Denied reads do not repair deliberately invalid fictional handoffs. Destination values in fixtures are fictional. Missing destinations preserve the nullable DTO. Endpoint keeps same-tenant owner/admin/receptionist/mechanic access and separately rejects foreign staff.

Product delta is only `backend/app/api/v1/endpoints/payments.py:get_zelle_info`; no migration, configuration, frontend, submission, mutation permission, or provider contract changes. Existing application imports were exercised through the ASGI suite. `git diff --check` passed. No existing runtime/database or production state was touched by this implementation.

Independent QA/security, protected CI, commit/PR, release, and live customer/guest acceptance remain parent-owned. No claim of deployment or browser-visible local serving is made.
