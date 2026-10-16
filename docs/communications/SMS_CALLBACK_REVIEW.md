# DB-COMMS-001C independent callback review

Date: 2026-10-16. Reviewer: independent callback QA/Security agent, with no implementation or implementation-direction participation. Accountable implementation owner: SMS Reliability. Branch: `codex/communications-foundation`.

## Decision

**GO for the bounded offline code/test gate.** No actionable P0/P1/P2 findings in the reviewed changes. This is **not PostgreSQL concurrency, configured application runtime, provider retry, merge, deployment, or release approval**. Those outstanding gates remain as recorded in `SMS_CALLBACK_VERIFICATION.md`.

## Scope and findings

Reviewed the working changes in `backend/app/services/messaging_service.py`, `backend/app/api/v1/endpoints/twilio_webhooks.py`, and `backend/tests/test_sms_callback_reliability.py` against the bounded callback subsection of `SMS_CALLBACK_CONTRACT.md`. Read repository instructions, delivery workflow, board, and implementation verification receipt. No implementation files were edited; other agents' UI work was preserved. Documentation/read-only review did not start application services.

No blocking findings. Inspection confirmed:

- `messaging_service.py:633`: SMS row lock plus refreshed ORM state protects the transition decision from stale state under the intended PostgreSQL transaction model. Actual lock serialization is unverified here.
- `messaging_service.py:661`: unsupported callback status cannot reset a known message to pending; missing and unknown SIDs follow the specified 400/503 contract.
- `messaging_service.py:671`: progression is monotonic; duplicates and terminal conflicts preserve timestamps. Notification changes share the commit and use the SMS tenant predicate (`:700`).
- `messaging_service.py:712`: supported failure receipt code 21610 independently enforces opt-out, including terminal conflicts, with customer ID plus tenant matching and a refreshed customer row lock. Duplicate opt-outs preserve their original timestamp.
- `twilio_webhooks.py:128`: service/persistence exceptions roll back and propagate non-success rather than acknowledging failed persistence. Existing signature validation remains before callback processing; this patch does not add a signature bypass.

## Reproduced evidence

Used `/tmp/db128-backend-venv/bin/python` with an empty inherited environment, explicit dummy Twilio credentials, an in-memory SQLite URL and `PYTHONPATH=backend`. No live config, network/provider call, production state, or persistent database was accessed.

`python -m pytest backend/tests/test_sms_callback_reliability.py backend/tests/test_messaging_service.py -q`: **76 passed**, two dependency deprecation warnings. Coverage includes the transition matrix, unknown statuses, terminal-conflict opt-out, duplicate timestamps, HTTP acknowledgement, commit failure rollback and invalid-signature rejection. Fake sessions establish behavior and emitted predicates, not database atomicity or isolation.

Additional independent in-process probe passed: simulated post-commit websocket failure returns 503; repeated delivered callback then returns 200 without changing the original delivered timestamp or broadcasting again. Compiled query bind values matched the exact SMS tenant for Notification and the exact tenant/customer for opt-out. This validates retry harmlessness, not eventual websocket delivery.

`git diff --check`: passed.

## Remaining verification boundaries

Before release, use approved safe PostgreSQL integration infrastructure to verify simultaneous callbacks, transactional rollback, and real cross-tenant fixtures. The fake-row tests cannot prove database enforcement. Verify configured signature handling and deployed provider retry behavior separately; 503 and Retry-After do not establish eventual provider redelivery. No durable receipt inbox or send idempotency was added. Post-commit websocket failure can leave a client without that live event until it refreshes; the bounded contract permits this and duplicate callbacks intentionally do not rebroadcast.

## Compatibility recheck — 2026-10-16

Re-read the revised contract and implementation after the Notification-only branch was added. **Offline QA/Security GO remains valid; no new actionable P0/P1/P2 finding.** At `messaging_service.py:643`, the lookup constrains exact external SID and SMS type and limits results to two. Exactly one row returns without assigning any Notification fields, querying Customer, choosing a tenant, updating consent, or broadcasting. Zero or multiple matches return 503. Signature validation still precedes this path. This global lookup supplies an acknowledgement decision only; it grants no tenant authority and exposes no Notification data.

Independently reran the complete focused pair: **76 passed**, two dependency deprecation warnings. The new cases verify delivered and failed/21610 Notification-only callbacks leave fields unchanged, with exactly two queries and no broadcast; ambiguous rows remain unchanged and return 503 with rollback. True unknown SID tests continue to pass. `git diff --check` passes. The same PostgreSQL/runtime/provider/release exclusions apply. Notification-only delivery tracking and consent interpretation remain explicitly deferred by the revised contract.
