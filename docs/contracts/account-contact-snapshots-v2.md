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
