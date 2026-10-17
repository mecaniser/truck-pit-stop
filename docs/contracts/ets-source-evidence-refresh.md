# ETS mirror evidence refresh

DB-ETS-FRESHNESS; Backend & Integrations accountable. This changes local source
provenance storage only, not the signed ELIS outcome contract or Google delivery.

`invoices.ets_source_evidence` remains schema version 1. Existing immutable
`observations` rows are preserved byte-for-byte. A new optional
`latest_confirmation` stores `sha256` of the final immutable evidence row and the
latest successful `observed_at_source` for exactly the same facts. Only the source
observation timestamp is excluded from fact comparison. Customer, source identity,
completion, invoices, allocation data and all other evidence remain meaningful.
The completion adapter overlays the timestamp only if the digest matches and the
time is not older than the original observation. Its 24-hour freshness and future
time checks remain unchanged.

A changed fact set appends a new row, including A→B→A. A replay at or before the
latest source observation or failure cannot replace it. Older pre-timestamp rows
remain readable; no time is invented for them. Legacy timestamp-only rows are
retained but do not consume additional semantic revision capacity. Twenty actual
consecutive fact revisions are permitted, with a hard 39-row bound to accommodate
nineteen old timestamp-only rows. A further changed observation sets an explicit
`revision_capacity_exceeded` hold and records `revision_capacity_observed_at`.
Only a later successful complete read matching retained facts can clear that
hold without appending; genuine changed facts remain held at capacity.

Failure invalidation compares against the effective latest confirmation. A fresh
successful read clears an older source-read failure; delayed successful reads do
not. Tenant-scoped invoice row locking remains the storage concurrency boundary.
No invoice amounts/status, job identities, match locks, human decisions, campaigns,
or conversion requests are changed by this implementation.

## Rollout and rollback

Deploy the new completion reader in Web/Worker before the ETS Sync writer. An old
reader ignores confirmation metadata and conservatively holds stale or 20-row
records; it must not be presented as refreshed. No backfill is required: the next
normal successful scrape refreshes matching facts. Rollback stops fresh confirmation
use and can create holds; it must never bypass freshness or replay Google requests.
Verify the deployed reader/writer revision, a scheduled successful same-fact scrape,
unchanged immutable rows, fresh completion observation, and existing event identity.
Independent QA/Security and protected CI are release gates, not owner self-approval.

The daily midnight UTC scrape cadence still meets a strict 24-hour freshness window
only narrowly. Runtime duration/jitter can produce stale intervals. Investigate a
separate bounded refresh cadence and source freshness alerts; do not extend the
freshness window or increase scrape frequency silently as part of this fix.
