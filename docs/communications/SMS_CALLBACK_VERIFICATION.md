# DB-COMMS-001C SMS callback verification

Accountable implementation owner: SMS Reliability. Architecture contract: `SMS_CALLBACK_CONTRACT.md`.

## Acceptance implemented

- Supported outbound status transitions move forward only. Delivered, failed and undelivered are sticky; conflicting terminal receipts emit a reconciliation warning.
- Duplicate receipts preserve timestamps and do not reapply Notification updates or broadcast a status change.
- Unknown/empty status for a known SID is acknowledged without status mutation. Missing SID returns 400; unknown SID returns 503 and Retry-After, including when its status is unknown.
- SMS rows are selected with FOR UPDATE and refreshed ORM state to serialize concurrent callbacks on PostgreSQL. Notification and opt-out lookups explicitly retain the SMS tenant boundary.
- Failure code 21610 on a supported failure receipt applies opt-out even if the delivery transition is rejected; duplicate opt-out receipts preserve the timestamp.
- Notification-only automated sends retain their existing acknowledgement behavior: exactly one SMS Notification matching the SID is acknowledged without mutation. No match or ambiguous duplicate Notification SID returns 503. This path does not infer customer identity or change consent, even for failure21610.
- Callback exceptions roll back and return 503 instead of success. Signature validation is unchanged. No send/resend path changed; no migration.

## Evidence — 2026-10-16

Worktree: `/Users/sergio_m1_promax/.codex/worktrees/communications-foundation/truck-pit-stop`; branch `codex/communications-foundation`; starting HEAD `1875a71d41d08784666b1d3b02281d68b38cc5ef`.

Runtime preflight: backend/.env absent; port8000 unbound. Port5173 PID27324 belongs to another worktree (`motive-driver-records/frontend`) and was preserved. Full local stack and database acceptance remain blocked by missing approved local configuration. No live credentials, provider calls, sends, retries or production changes were used.

Focused tests used `/tmp/db128-backend-venv/bin/python` with explicit dummy Twilio/config values and SQLite test URL:

```
python -m pytest backend/tests/test_sms_callback_reliability.py backend/tests/test_messaging_service.py -q
76 passed, 2 warnings
```

New regression tests exercise the entire 6-state by 7-provider-status transition matrix, unsupported statuses, sticky terminal conflicts plus opt-out, duplicate timestamps, webhook 400/503/200 responses, commit failure rollback, and invalid-signature rejection. Fake database and ASGI transport perform no network or persistent database operations. SQL assertions prove lock/tenant predicates are emitted; they do not establish PostgreSQL concurrency execution. Notification-only delivered/failed21610 acknowledgement and ambiguous duplicate SID rejection are also covered. Existing messaging tests passed unchanged. `git diff --check` passed.

## Remaining work / evidence boundaries

- Independent QA/security review required before release. No PR, merge or deployment yet.
- Actual PostgreSQL lock behavior, transactional rollback and authenticated runtime acceptance still require configured safe integration infrastructure.
- Returning 503 advertises a retryable failure; it does not prove that Twilio's deployed retry policy will redeliver callbacks. Provider retry configuration and reconciliation must be verified before claiming race recovery.
- Notification-only automated-send delivery remains untracked by callbacks; this patch preserves that existing behavior rather than expanding notification tracking.
- No durable callback inbox/outbox was added. Callbacks that never redeliver still need reconciliation. Send-before-commit ambiguity, automated-notification duplication, provider acceptance and customer receipt remain separate investigation items.
- Existing initial-send response mapping remains unchanged; strict supported-status checking is specific to callbacks.
