# DB-121 automatic shop history — production evidence

Backend & Integrations accountable; independent QA/Security GO for implementation.
Final reconciliation evidence is submitted for independent review with this document.

## Release and verification

[PR522](https://github.com/mecaniser/truck-pit-stop/pull/522) merged 2026-10-14
at 23:31:06 UTC as `1e128457a4f9039e5ebcb72fc5018b59575366a7`.
Fifty focused tests and actual PostgreSQL migration/concurrency acceptance passed.
All six gates in [CI38652409965](https://github.com/mecaniser/truck-pit-stop/actions/runs/38652409965)
passed: backend full 3,060 passed/152 skipped in 1,056.58s; critical 530 passed/11 skipped.

Production migration 170 is applied. Initial Web deployment `e7722f26` and activated
Worker `3dd47589` were verified at `1e128457`. Newer Web `53995654`, deployment
`e430fe54`, subsequently succeeded. That [PR523](https://github.com/mecaniser/truck-pit-stop/pull/523)
release contains `1e128457` with unchanged history runtime and is preserved.
Capture and delivery are enabled only for the approved shop allowlist.

## Observed automatic flow

The existing ETS→DieselBridge nightly sync completed 2026-10-14 at 02:11:39 UTC,
adding 10 invoices. Its deployed manifest runs at 00:00 UTC; its source sync/import
code matches the inspected source. The new five-minute history schedule produced
its first 100 observations and 39 deliveries before the separately reviewed initial
catch-up. A full capture found 2,389 invoice histories; a full repeat scan of 2,389
records created 0 additional observations.

A reviewed, private, bounded catch-up accelerated first-attempt **source history**
delivery without changing the normal scheduler or shared delivery batch size.
It did not upload Google conversions. Three source events encountered transport
acknowledgement failures after ELIS had processed them; the existing worker's
idempotent source retry resolved those acknowledgements.

## Final reconciliation

Source checked 2026-10-15 at 00:13:45 UTC; ELIS checked 00:13:46 UTC.

| Evidence | Result |
| --- | ---: |
| Source invoices / observations / history events | 2,389 / 2,389 / 2,389 |
| Source history deliveries succeeded | 2,389 |
| ELIS durable receipts / processed histories | 2,389 / 2,389 |
| Source event, receipt and processed identity sets | Exactly equal |
| Receiver pending or dead history work | 0 |
| Canonical shop jobs / source invoices | 2,380 / 2,389 |
| Automatic matched snapshots | 1 |
| Snapshots retaining a manual link | 3 |
| Source grouping uncertain / missing date | 1,031 / 36 |
| Unmatched snapshots | 1,318 |
| Duplicate opportunity links | 0 |

These are source-history snapshot counts, not new customers, landed jobs or Google
conversions. Multiple invoices can belong to one canonical job. Imported history
retains its historical hold. The 20 native history records lacking payment proof
remain blocked from job delivery; source context does not establish settlement.
Manual links and their holds were preserved.

All 9,356 pre-existing Google delivery attempts retained their verified IDs,
event bindings, destinations, attempt numbers, payload hashes and timestamps.
Existing conversion IDs, types, statuses, creation timestamps and repair-order
bindings were unchanged. Financial revision count remained2; history intake
created no financial rows. Thirteen new
qualified-lead events arose concurrently through normal operations; **zero new job
conversion events** were created. No Google conversion was resent by this work.

## Contract and safeguards

- The invoice's repair-order identity owns the job. Exact ETS operation siblings
  provide context, never additional invoice value. Conflicting equipment/source,
  deleted context and oversized truncated descriptions force review.
- Durable tenant cursors scan 50 invoice records per run (configurable 1–200).
  Per-invoice sequences handle changes including A→B→A; cursor, observation and
  immutable outbox commit together under tenant locking.
- Imported payment dates retain day precision. History snapshots do not create
  settlement revisions, payment authority or Google delivery approval.
- Existing HMAC, leases, retries and absolute PII expiry apply. History failures
  cannot pause native settlement delivery; native delivery has priority.
- Invalid source corrections create an audit and quarantine retained prior context.
  Expired private snapshots are never reconstructed; their failure audit remains
  an explicit exception requiring source repair.

## Boundaries and rollback

Automatic capture, authenticated receipt, projection and conservative matching are
verified. Unmatched/uncertain history remains held; bulk history ingestion does not
mean those jobs are attributable to ads or eligible for conversion delivery.
No payment or campaign settings changed. This backend-only change adds no browser
journey. Local preflight found another checkout on 5173 and no approved local
runtime configuration; isolated tests were followed by PostgreSQL acceptance and
separate production evidence above.

Disable `SHOP_HISTORY_CAPTURE_ENABLED` to stop new history capture and delivery
while leaving native paid delivery running. Preserve cursors, observations, source
receipts and holds. Do not roll back the newer Web release or resend Google
conversions as a cleanup action.
