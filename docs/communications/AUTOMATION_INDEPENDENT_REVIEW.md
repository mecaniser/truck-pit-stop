# DB-COMMS-003 independent QA and security review

Reviewer: independent automation QA/security agent, with no implementation or direction of the reviewed changes. Scope: `codex/automated-sms-recovery`, against parent `54bc9f58`. Date: 2026-10-16. Deployment remains HOLD for real SMS acceptance.

## Gate status

**QA/security GO for the reviewed local implementation.** Both independent findings below were corrected and the final delta was independently reviewed and tested. This is not approval to deploy: required CI, release coordination and real SMS delivery acceptance remain separate gates.

1. **Recovery starvation:** per-row exceptions were rolled back but left oldest pending rows eligible forever. A full batch of poison rows could prevent all newer messages from reaching dispatch. Resolved: deterministic row failures now persist an unknown/reconciliation hold, while database failures remain visible. Batch-size-one tests prove the next tick reaches the healthy row, with no retry of the held operation.
2. **Delayed financial notifications:** invoice and Zelle reminders became durably delayed but initial dispatch checks covered recipient identity/consent only. A payment, cleared/replaced Zelle submission, or cancellation between enqueue and recovery could produce a stale financial reminder. Resolved: dispatch acquires the financial mutex, refreshes the tenant-qualified invoice/order, checks the exact pending occurrence and compares a normalized financial fingerprint. Payment, partial payment, changed amount, cancellation, cleared/replaced Zelle submission and disabled reminders reject before provider I/O. Current unchanged financial events pass. Assignment and idle alerts also suppress obsolete occurrences. These checks authorize the dispatch claim; they cannot recall provider traffic after that claim.

## Evidence reviewed

- Domain event + template/version + stable recipient uniqueness; immutable payload conflicts; transactional enqueue flush only, database claim before provider call, attempt bound, unknown outcome hold.
- Assignment, start/completion, quote publication and decline, invoice reminders, Zelle submit/reminders, idle streak, and generic task producer inventory. Email/network effects follow domain/SMS commit.
- Current tenant, sender, customer opt-out/identity ambiguity, same-tenant active staff and tenant-contact checks; no automated legacy direct-provider fallback.
- Customer automated history versus staff Notification-only projection; exact SID and sticky terminal callbacks.
- Default-disabled recovery registration and execution, production live-provider and tenant allowlist checks, bounded execution and lease ownership, schema readiness additions.
- Migration 178 adds a new outbox without replaying historical messages and refuses destructive downgrade with populated rows.

## Independently executed checks

Using `/tmp/db128-backend-venv/bin/python scripts/communications_local.py exec python -m pytest` against the authorized isolated PostgreSQL configuration:

- Initial outbox, guards, producers and recovery modules: **51 passed**, no skips.
- Final outbox, guards, producers, scheduler and manual communications modules: **88 passed**, no skips (29.59 seconds), including real PostgreSQL concurrency and financial-delay cases.
- Scheduler/manual delta run: **26 passed**, including tenant/queue fairness and manual poison progression.
- Assignment notifications, invoice payment race, Zelle reminders/websocket routes, callback reliability: **78 passed**, no skips.

Only synthetic fixtures/fake senders were used. No real SMS, production mutation, merge, deployment, or production configuration activation was performed. Root-owned full CI and actual Celery runtime evidence are separate gates and must be recorded independently.

The monetary snapshot normalization correction was specifically reviewed: equal values such as integer 100 and persisted 100.00 produce the same fingerprint. The final positive unchanged-domain tests pass alongside the negative debt-change cases. `git diff --check` passes.

Reviewed source/test/script aggregate: SHA-256 `14dde2351016842e85dee97f82c2782ea181803ec7ac3f263021ec9f0060c474` across 40 changed Python files relative to parent `54bc9f58` (sorted path, NUL, contents, NUL). Documentation is excluded. Later implementation changes require delta review.
