# DB-COMMS-005 independent QA and security review

Reviewer: independent gatekeeper with no implementation participation. Scope: `codex/multishop-sms-onboarding`, multi-shop contract and current uncommitted implementation. Provider registration submissions, live provider calls, merge and deployment remain on HOLD.

## Gate status

**Security and focused regression GO for isolated review.** No unresolved implementation blocker found in the reviewed source. This is not production or deployment approval. Parent-owned runtime/browser acceptance and protected integration CI remain separate gates.

Initial blocking findings were returned to the routing owner and independently rechecked after correction:

- Disabling managed routing could dispatch a managed pending automated intent using the global client. Pending managed manual/automated intents now reject with `routing_disabled`, and new manual/automated/legacy sends for previously managed tenants also fail closed. Never-migrated legacy tenants retain their existing behavior.
- Managed callback account authentication and account-scoped message selection now remain enforced when rollout is disabled. Global/no-account callbacks cannot mutate managed rows; original managed account receipts remain accepted.
- Missing or blank managed inbound `MessageSid` now rejects with 400 before customer opt-out or message mutation, preserving duplicate guarantees.

## Independently executed checks

- Initial dedicated isolated PostgreSQL onboarding/routing baseline: **29 passed**.
- Final independent isolated PostgreSQL rerun: `scripts/communications_local.py exec python -m pytest tests/test_sms_onboarding.py tests/test_tenant_sms_routing.py tests/test_communications_service.py tests/test_automated_sms_outbox.py tests/test_automated_sms_guards.py tests/test_automated_sms_producers.py tests/test_messaging_service.py -q`: **127 passed**. Includes concurrent replay, account/service/sender isolation, staff/contact evidence, wrong account/signature, duplicate inbound, STOP/START, retired receipts, rollout rollback and malformed receipt regressions.
- Frontend: SMS setup, onboarding client and connected inbox suites: **12 passed**, 3 files.
- `git diff --check`: pass.

No real provider/network calls, registration, live messages, production mutations or deployment were made by this reviewer.

## Reviewed boundaries

- Tenant owner/admin access and server-derived tenant scope; ordinary staff denied onboarding access while authorized messaging staff may record own-customer evidence.
- Strict request schemas reject tenant, account, approval, credential, enabled and tax-ID injection. Website validation does not fetch URLs.
- Tenant responses redact credentials and provider account identifiers; review action changes local review state only and no registration activation/submission endpoint exists.
- Additive schema, nullable legacy snapshots, account-scoped provider identifiers and deduplication; no consent backfill or live provisioning migration.
- Immutable binding replacement, sender uniqueness and provider-account/business ownership check, with PostgreSQL advisory serialization for shared-account assignment.
- Managed manual, automated customer, staff/contact and legacy sends resolve checked account/service/sender; consent is bound to tenant, recipient identity, current phone and purpose, with opt-outs checked separately.
- Known account signature selection, account plus sender inbound resolution, account plus message status matching, sender/service mismatch rejection, retired-binding historical receipts, STOP isolation and START not fabricating consent.
- SDK transport retries disabled; durable operation claims and existing unknown-outcome holds retained.
- Frontend review-only state, version conflicts, draft preservation, role-aware setup entry, explicit consent evidence form, and tenant/user/customer remount keys.

## Remaining acceptance boundaries

Parent-owned HTTP/browser/runtime evidence, migration receipt, required protected CI and exact final source state are separate from this source and focused-test review. Real registration approval, provider associations, handset/reply and public signed-callback delivery remain required before deployment. A GO for isolated development never authorizes registration submission or deployment.
