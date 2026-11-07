# Current account contact evidence (history v2)

Owner: Backend & Integrations. High-risk: tenant-bound contact evidence, source
collector, nullable migration175, and attribution consumer compatibility.

`job.history_snapshot` envelope version2 adds `customer.source_customer_id`
(ETS numeric string, nullable when absent/native) and nullable
`customer.contact_phone_snapshot`. Existing customer.id stays the DBN UUID.
Accounts with no captured contact evidence keep the exact v1 shape/envelope.
After a stream exists, a later v1 event (for example a lost source column)
is a detectable downgrade: the reader invalidates account phone authority
using event.occurred_at ordering. An older late-arriving v1 cannot invalidate a
newer v2; a subsequent valid v2 restores evidence. Contact freshness still uses
the source observed_at, never the history delivery time.

Contact snapshot fields: source_system=`easy_truck_shop`, source_shop_id,
source_customer_id, dbn_customer_id, observed_at (aware UTC), complete, reason,
contacts, semantic_hash. The shop must match the trusted configured tenant/ETS
mapping. Both customer identifiers must match the enclosing account. Complete
source_customer_id is digits, at most50 characters; incomplete may be null.

Contacts contain source_contact_id (nullable, at most140 characters) and phone
(canonical NANP +1 number). Current collector has no verified source IDs and
uses null. It includes current account-header phone and current active table
phones from the same account page, never the legacy database phone. Empty
phones are omitted; any unsupported nonblank phone invalidates the entire set.
At most200 entries, exact pairs deduplicated and sorted by phone then source ID.

SHA256 covers compact sorted-key UTF8 JSON (`ensure_ascii=True`) of all snapshot fields except
observed_at and semantic_hash. Nulls are included. Fresh confirmations preserve
semantic_hash but update observed_at. Changed facts, including A→B→A, retain
their chronological meaning. Equal-time different facts invalidate; older
success/failure cannot replace a newer observation.

Incomplete has contacts=[] and reason one of read_unavailable,
account_mismatch, filtered, page_incomplete, schema_unsupported. Complete has
reason=null. A current complete empty set removes all old phone authority.
Once a contact stream exists, incomplete/stale evidence grants no fallback to
historical primary or alternate phones. Consumer freshness is24hours.

Collector completeness requires exact bound account route, blank search,
archived unchecked, expected six columns, current account header, exact
`Showing 1 to N of N results` count and no active next control. Explicit zero
footer permits an empty table. Unknown/multiple-page UI fails closed. No
pagination URLs, source IDs, or old contacts are guessed.

Read-only authenticated AX inspection verified a current account page with two
contacts and a matching2-of2 footer. DOM inspection was unavailable; exact
collector selector verification remains a runtime acceptance requirement.

## Release and rollback

First deploy both compatible ELIS completion and historyv2 readers. The source release consolidates the independently reviewed freshness, completion and contact changes.
Then apply nullable migration175 and deploy DBN Web/Worker, then ETS collector.
Only the normal scheduled scrape creates fresh source evidence. No replay or
Google resend is part of this change. Verify aggregate complete/incomplete
counts and fresh timestamps without emitting private contact data. Confirm
existing manual qualification and financial records unchanged.

Rollback code before dropping the nullable column; preserve captured evidence
for investigation. Stop contact-based automatic matching on identity/hash/
freshness anomalies. Do not restore historical phone unions.

## Capture during delivery pauses

A delivery pause stops outbound webhook requests. Enabled, allowlisted shops
continue durable history capture under the existing retention ceiling, so current
source observations are not frozen during receiver outages. Disabled integrations
remain excluded. Resuming delivery preserves event IDs, idempotency keys and
attempt history; terminal dead events require a separate review and are not
replayed by a resume.

## History delivery fairness

A dedicated ten-second sender slot claims at most one eligible history event through
the existing signed delivery service. Completion traffic retains its independent
slot and configured batch. History uses the same tenant allowlist, pause, privacy
expiry, lease, SKIP LOCKED, idempotency and failure rules; its total delivery budget
remains 35 seconds within the 45-second task soft limit. No terminal or uncertain
event replay is introduced.

## ETS history value provenance

Imported financial mirrors are intentionally not rewritten by later source reads.
History invoice totals may use the collector-verified current ETS total only when
the immutable evidence digest and confirmation bind, the observation is within
24 hours, and the existing completed-source verifier proves the exact tenant,
shop, service, imported invoice alias, complete single-invoice manifest, completed
status and positive USD total. Missing or conflicting proof retains the original
history context and existing holds. This does not change invoice/payment rows or
constitute completion, consent or Google-delivery authorization.

## Daily account delivery (DB-CONTACT-DAILY)

The existing ETS collector already performs genuine daily contact reads. The
Worker checks for undispatched source observations every five minutes, bounded
to50 accounts per transaction. One deterministic public, nondeleted invoice
with imported invoice/order/customer provenance anchors each account. The
configured tenant/ETS shop binding is mandatory. No financial capture runs in
this path.

Only source observations less than20hours old, not in the future, may enter this
priority path. The payload retains the source observed_at unchanged. Complete,
empty and incomplete observations all retain their original meaning. Missing
evidence remains unavailable and is excluded, never manufactured. Existing rotating
history capture remains unchanged for stale context and ordinary job updates.

The immutable idempotency key binds account, original UTC source read time
(including its day) and the validated semantic hash. Together these cover every
contact observation field and use the existing exact outbox identity index. Same-read reruns produce no second event; changed
same-day evidence gets a distinct correction identity. The tenant lock
serializes the shared invoice observation sequence and outbox commit. These
history events use the existing signed sender, with priority over bulk history
only, newest source observation first (including invalidations). Bulk history
retains FIFO and completion ordering is unchanged. Pause, allowlist, privacy
expiry and retry budgets remain authoritative.
Old events are neither marked delivered nor replayed by capture.

Native histories keep source=dieselbridge. If the customer has a contact stream,
they use v2 and source_customer_id, without contact_phone_snapshot. This avoids
asserting ETS evidence on a native repair, clearing valid imported contact
authority, or downgrading the account to v1.

Release acceptance must compare exact event receipts and account/source times,
then count current eligible phones in ELIS. A300-phone target is conditional
on real current source completeness; it is not inferred from account totals.

An exact invalid source read receives a terminal non-deliverable diagnostic,
containing only observation identity and a safe reason, so bad accounts cannot
strand later accounts. A new source read is eligible for retry. Any prior
account-wide PII redaction blocks priority reconstruction from a source read
observed at or before redaction, including alternate invoice anchors. Because
automatic retention uses the same redaction marker, this is conservative:
a source reread after that barrier is needed for fresh priority capture.
