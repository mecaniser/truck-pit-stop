# ELIS job history snapshot v1

Architecture handoff: DieselBridge Backend & Integrations owns capture/outbox;
ELIS owns authenticated intake, encrypted history and conservative repair matching.
This is source context, not a Google conversion or native settlement event.
The board owner assigns an unused item ID; DB-119 already names external service
history and must not be reused for this integration.

## Wire contract

POST to the existing configured ELIS shop-outcome webhook URL. Reuse its existing
HMAC, timestamp, event and Idempotency-Key headers and tenant-bound signing secret.
`X-DieselBridge-Event` is `job.history_snapshot`. Existing native v2 paid/refund
contracts and their native-settlement predicates remain unchanged.

The complete synthetic fixture is
`backend/tests/fixtures/job-history-snapshot.json`. Its snapshot revision is
`1e314769448167a4b8f30e613ef1c99618fc41206375211a962f321072f3d084`.

Envelope: schema_version=1, event_type=job.history_snapshot, event_id UUID,
occurred_at aware emission timestamp, shop_id UUID, source_system=dieselbridge,
source_revision SHA-256 hexadecimal string, source_observation positive integer, snapshot object.

Snapshot fields:

| Field | Meaning |
| --- | --- |
| source | dieselbridge or easy_truck_shop_import; preserve provenance |
| repair_order_uuid, repair_order_number | Canonical invoice parent RO identity |
| invoice_id, invoice_number | Stable source invoice identity |
| job_status, invoice_status | Source status strings |
| currency, invoice_total | USD and two-decimal string; invoice face value, not profit or cash |
| completed_date, invoiced_date, paid_date | Nullable ISO calendar dates |
| paid_at | Nullable aware timestamp, only when source has an actual instant |
| paid_time_precision | day, instant or unknown |
| grouping_uncertain | Boolean, defaults false; producer emits explicitly |
| customer | id UUID, nullable name/phone/email |
| vehicle | nullable id UUID/vin/unit_number |
| operations | Objects containing repair_order_uuid, repair_order_number, description |
| attribution | Nullable elis_opportunity_id UUID and callrail_call_id string |

All nullable keys are emitted explicitly. Operations are deterministically ordered
by repair_order_number then repair_order_uuid. Sort object keys, preserve array
order, and serialize snapshot with Python-equivalent
`json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`;
SHA-256 its UTF-8 bytes. Never include emission time/event UUID in this hash.
Receiver verifies the wire snapshot hash before projection; do not hash a
normalized model that changes timestamp spelling or decimal representation.

Imported payment dates use the source UTC calendar date and paid_at=null,
paid_time_precision=day. Do not convert midnight into a claimed payment instant.
Absent payment evidence uses unknown precision and null paid_date/paid_at.
Instant precision requires paid_at. Calendar completion/invoice dates remain dates.

## Identity, concurrency and source grouping

Outbox key: `job-history:{invoice_id}:{source_observation}:{source_revision}`. Store immutable payload
and UUID atomically; concurrent captures converge through the existing unique
outbox key. Retry only that source delivery, not any Google conversion. Changed
source facts create another observation; unchanged polling creates none. A durable
per-invoice sequence increments on changes, including A→B→A returning to a prior
snapshot hash. Receiver chooses the highest observation per invoice so delayed
delivery cannot restore an older observation.

Invoice parent RO is canonical. ETS sibling operation inclusion requires exact
parsed ETS service/customer base and matching tenant, source, customer and
vehicle. Different equipment or ambiguous grouping sets grouping_uncertain.
Do not sum operation RO totals or emit one job per operation. Invoice amount is
the snapshot amount. Do not merge based merely on a stripped numeric suffix.

ELIS reuses its existing (tenant, source, shop, canonical RO UUID) job and
(tenant, source, shop, invoice UUID) invoice keys. In particular, previously
imported historical jobs retain easy_truck_shop_import identity. Persist encrypted
history separately from financial ShopOutcomeRevision; source history must never
be relabeled native settlement or call reconcile_job_delivery.

New history-only jobs remain held. Preserve historical holds, existing financial
proof and manually locked matches. Native snapshots attach context without
altering prior settlement state. No Google delivery, consent or campaign writes.

## Receiver and authorization

Resolve tenant from enabled signing credential bound to shop_id, never a body
ELIS tenant. Authenticate freshness/signature/header consistency before accepting
source facts. Commit encrypted raw event and unique processing job before 202.
Receipt uses existing raw_event_id, job_id, duplicate, event_type and trace_id.
Identical event/body replay returns the existing receipt; reused event or
idempotency identity with different bytes is 409. Invalid authentication is 401;
invalid schema/hash/date semantics is 422; unavailable signing/encryption/routing
is 503. No private source payload in logs or repository fixtures.

## Matching boundary

Resolve explicit opportunity/call references to one current canonical repair.
Other automatic matches require unique recording-grounded identifiers: exact
invoice/order reference, or VIN plus compatible service/date, or verified phone
plus exact unit plus compatible service/date. Reject conflicting equipment,
multiple candidate repairs and grouping_uncertain. Phone/name alone and generic
make/model are insufficient. Preserve human locks and append match evidence with
source revision and recording-analysis revision. Unmatched/uncertain jobs remain
held; matching a job does not establish ad causality or approve a conversion.

## Acceptance and rollout

Deploy accepting receiver before enabling producer event capture. Existing URL,
secret and native event behavior remain compatible. Include new event in outbox
claiming, bounded scheduling and PII expiry/redaction; customer, vehicle,
operations and attribution need the same protection as existing sensitive fields.
Rollback stops new capture while retaining durable source evidence and holds.

Required tests: fixture hash parity; unchanged and concurrent replay; changed
snapshot; wrong tenant/signature/hash; day precision; source identity reuse;
split operations; conflicting equipment; ambiguous matches; human lock retained;
no ShopOutcomeRevision/Google ConversionEvent/ConversionAttempt mutation.
Independent QA and Security must be performed by agents who did not implement
or direct this contract. Production completion additionally requires observed
scheduled capture, durable receipt/projection and verified held unmatched cases.
