# DB-COMMS-003 verification

Owner: Backend & Integrations. Branch: `codex/automated-sms-recovery`, stacked on
shared inbox PR562. Draft PR563: https://github.com/mecaniser/truck-pit-stop/pull/563. Deployment remains HOLD until authorized real SMS acceptance.

## Local evidence — 2026-10-16

- Additive migration178 applied only to dedicated local PostgreSQL16 on55460,
  database `communications_local`; Alembic graph has one head.
- 125 focused backend tests passed: real PostgreSQL concurrency, one provider
  attempt, transactional rollback, callback mapping, changed debt/event guards,
  tenant/consent/identity negatives and malformed-row progress.
- Independent QA/security GO after correcting malformed-row starvation and stale
  financial reminders. Reviewer separately ran88 final focused tests and78
  producer/callback checks. See `AUTOMATION_INDEPENDENT_REVIEW.md`.
- 15 scheduler tests cover disabled/no-I/O, allowlists, credentials, overlapping
  leases, bounds, infrastructure failures, schema gating, sync Celery wrapper,
  Beat cadence/expiry and fairness across every tenant/queue pair.
- Actual Celery Worker and Beat using the isolated simulated adapter passed:
  pending intent survives before worker start; exactly one provider invocation;
  repeated domain event and worker restart add none; uncertain outcome remains
  held across repeated scheduled ticks. Final run `verify_sms_recovery_local.py`
  passed after domain guards were added; child services stopped after verification.
- Full authenticated shared-inbox HTTP acceptance passed again against API8006:
  concurrent replay, assignment/status/read, signed callback/inbound processing,
  opt-out, unknown/rejected and cross-tenant/role negatives.
- Production frontend build passed. Full local frontend run1820 passed with one
  unrelated5second timeout in `RepairOrdersPage.void-revision`; focused rerun of
  that file passed3/3. Required CI full suite remains separate evidence.
- Full backend run with the isolated-PG opt-in was stopped because legacy SQLite
  test fixtures globally patch UUID result processing, contaminating later PG
  tests. PG suites pass in separate focused processes; standard CI-environment
  full backend suite is run separately, with opt-in PG tests skipped by design.

## Runtime receipt

API PID98149 serves this worktree's backend at127.0.0.1:8006 using guarded
`communications_local_app:app`; frontend PID56726 serves this worktree's prototype
at127.0.0.1:5186, with `/api` proxy8006. Both roots and commands verified after
restart. Database/Redis readiness200. No real Twilio credentials or HTTP access.

Authenticated browser at5186 shows automatic `Service update` rows with queued
and unknown outcomes. Ava's uncertain automatic send displays `Delivery needs
verification`, a draft-only composer and disabled Send SMS. This is **aligned and
browser-verified** local behavior, not real provider delivery. Screenshot:
`.impeccable/review/automated-recovery-desktop.png` (local ignored artifact).

## Remaining release gates

Required exact-revision CI, approved real SMS/handset and provider callbacks,
explicit deployment approval, staged migration/worker/Beat enablement. Recovery
is false by default; deploying without enablement intentionally holds automated
intents pending. Partial-balance reminder copy is conservatively rejected for
review rather than sending a misleading total. See `SMS_RECOVERY_RUNBOOK.md`.

The required Quality gates workflow is dispatched on this branch. Its final
exact-revision run and job conclusions are recorded in the PR description, which
can be updated without changing the tested revision. No merge/deploy is authorized.
