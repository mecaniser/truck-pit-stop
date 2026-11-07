# DB-CONTACT-DAILY: verified daily account contact delivery

Accountable owner: Backend & Integrations. Lane: high risk. Branch:
`codex/elis-daily-contact-snapshots`, based on `0bd0b375`.

## Outcome and current state

Implementation and independent local gates pass. Production remains unchanged:
the shared signed delivery connection is paused. This item is not Done. Merge,
deployment, controlled delivery recovery, live source-time parity and current ELIS
phone-identifier acceptance remain pending.

The existing ETS collector already reads contacts daily. On November 7, a
read-only check found 714 accounts with supported imported invoices; 710 had
source observations from that day, including 652 complete and 58 incomplete
observations. Four had no contact evidence. The handoff's eight-event count
covers paid events rather than the separate history stream. Daily evidence
collection alone cannot fix a paused connection.

## Implementation and contract

- A five-minute Worker task considers at most the existing configured capture
  batch of 50 accounts. One deterministic supported, public, nondeleted imported
  invoice anchors each account's genuine source contact read.
- Source evidence must match the tenant, configured ETS shop and customer. The
  source timestamp stays unchanged and must be less than 20 hours old and not
  in the future. Missing evidence is never synthesized.
- Complete, empty, incomplete and same-day changed reads retain their meanings.
  Exact account/read-time/semantic-hash identities use the existing unique
  outbox index. The tenant lock serializes shared invoice observations and
  outbox commits. There is no migration or receiver-schema change.
- Contact history receives priority over bulk history, newest source read first.
  Completion ordering, signatures, allowlists, privacy expiry, retry budgets,
  idempotency and delivery pauses remain enforced.
- Native history remains native and uses v2 without ETS-only contacts when the
  account has a contact stream. This avoids HTTP 422, contact invalidation and
  v1 downgrade. Old fallback snapshots receive the same correction without
  changing their original stored payloads.
- Invalid reads receive terminal non-deliverable diagnostics so they cannot
  starve later accounts. Account-wide redaction barriers prevent reconstructing
  erased source reads through another invoice. Customer erasure acquires the
  same tenant lock as capture, preventing an uncommitted-event race.

Automatic retention uses the same redaction marker, so its barrier is
conservative: a genuine source reread after redaction may be necessary for
priority capture. Ordinary job history and existing financial evidence remain
separate. No financial/profile/consent/manual-link or Google settings were
changed during implementation or verification.

## Verification

Frozen implementation/test fingerprint:
`d0824d81bca3f2519fbbeb314babb404f7854de0c65fb89afe8ce34523fa1607`.
It covers, in order, relative path + NUL + content for:

1. `backend/app/services/account_contact_history.py`
2. `backend/app/services/shop_history_source.py`
3. `backend/app/services/paid_invoice_webhook_service.py`
4. `backend/app/services/conversion_pii_retention_service.py`
5. `backend/app/tasks/__init__.py`
6. `backend/app/tasks/provider_outbox.py`
7. `backend/tests/test_account_contact_history.py`

Owner checks: 225 focused and adjacent Python tests passed; one unrelated legacy
correction PostgreSQL test skipped because `DB002_POSTGRES_URL` was not provided.
Both new PostgreSQL concurrency tests ran against a disposable local database:
concurrent daily/rotating capture preserves identity/sequence, and erasure waits
for uncommitted capture then removes all PII. Ten existing JavaScript collector
contract tests, Python compilation and diff integrity passed.

Independent QA: GO on the frozen fingerprint. 85 tests passed, including the
PostgreSQL checks and independent synthetic reproductions. Actual ELIS schema
validation accepts emitted imported and native wire payloads. Actual signed ELIS
intake/account-index verification preserves imported contact authority after a
native v2/no-contact event. Invalid-account progress, same-day corrections,
freshness, provenance, pause and priority checks passed.

Representative PostgreSQL performance used 700 accounts, 2,562 active invoices
and approximately 61,400 outbox rows with a 15-second statement timeout:

| Operation | Time |
| --- | ---: |
| Initial 50-account candidate query | 0.246 s |
| Full 50-account capture | 0.531 s |
| Completed-account sweep | 0.057 s |

Independent Security: GO on the frozen fingerprint. Independent erasure
reconstruction and real PostgreSQL erasure/capture race reproductions pass:
zero surviving erased PII payloads. Tenant/source boundaries and existing
transport/privacy controls remain enforced.

## Local runtime receipt

November 7 preflight: target checkout is this branch; approved `backend/.env`
and frontend dependencies are absent. Port 8000 belongs to another preserved
sandbox checkout; port 5173 is unbound. Controller dry-run refused the switch.
Status: blocked/mismatched for the full local app. No existing listener, database,
configuration or populated volume was replaced. Verification used synthetic
backend databases and the actual ELIS receiver implementation, not a claim of
signed-in local or production browser acceptance. No UI changed, so browser
interaction is not the feature's local acceptance gate.

## Release and recovery plan

1. Pass protected exact-head PR checks, then obtain the production release and
   shared-feed recovery decision. The shared pause controls completion events
   as well as contact history; clearing it is broader than contact-only capture.
2. Deploy Web and Worker consistently and verify loaded task registration,
   source fingerprint and readiness. Existing ETS collection needs no extra
   credentials or financial-import run.
3. Observe targeted capture and exact immutable receiver receipts. Resolve any
   transport failure before widening recovery; never mark uncertain deliveries
   accepted merely from source status or aggregate counts.
4. Resume only the approved delivery scope. Preserve existing identities, holds,
   old terminal failures and Google-delivery safeguards; no historical Google
   resend is part of this change.
5. Verify account-level source timestamps and current complete/incomplete sets
   in ELIS. Check the actual phone identifier count; the 300-phone target depends
   on genuine current source evidence and is not yet a measured outcome.

Rollback: stop the new task or revert the source change through the normal PR
path; preserve all outbox evidence and keep delivery paused if transport or
privacy checks fail. No data deletion or schema rollback is required.
