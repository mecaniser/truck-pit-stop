# DB-129 — private outside-shop receipts

2026-10-14. Architecture & API Contracts: approved for implementation against
the contract below. Backend & Integrations accountable; Frontend & UX consumes
the shared fixture. High-risk lane: private files, tenant boundary and additive
migration. This document is design evidence, not implementation, QA, security,
merge or production acceptance. Independent gates require fresh reviewers who
did not implement or direct the work.

## Outcome and scope

Allow existing DB119 staff to attach PDF, JPEG and PNG receipts to one exact
outside-shop service record, download them after reload, and recover removed
files through Restore. Preserve who uploaded, removed and restored each file.
Explicit retries after uncertain responses must not create duplicate files or
audit events. No external URL input, public object URLs, Cloudinary, previews,
OCR, invoice import, payment, accounting, inventory, mileage or PM effects.

Use a private database blob table for this bounded first release. PostgreSQL
already provides durable private storage and transactional linkage; no provider
account, credential, bucket, worker or external scanning service is needed.
Blobs increase database and backup storage; the following limits are mandatory:

- One file per upload, 1 through **5,242,880 bytes (5 MiB)** inclusive.
- At most **10 retained files / 52,428,800 bytes per service record**. Removed
  files count toward both limits because their bytes remain recoverable.
- Raw request body cap: **5,242,880 bytes**, counted while streaming.
  No multipart parsing, unbounded request read or spooling.
- No replace or hard-delete endpoint. Upload a different receipt or restore the
  retained one. Exhaustion returns a useful capacity error; removal never
  pretends to reclaim storage. Retention/purge policy is a separate outcome.

## Data model and migration

Add `172_external_service_receipts` after `171_ets_source_evidence`, subject to
rechecking the actual integration head before merge. At contract inspection,
the checkout and origin/main have head171; merged PR532 contains no migration.
Keep one Alembic head; if another migration lands first, renumber/reparent before
release and rerun the migration checks. No backfill and no native financial
table changes.

Register three models in `app.db.models`. Use existing BaseModel timestamps and
UUID conventions, but do not use `deleted_at` for receipt removal.

`ExternalServiceReceipt` / `external_service_receipts`:

- `tenant_id`, `record_id` required; composite RESTRICT FK to
  `external_service_records(tenant_id,id)`. Unique `(tenant_id,id)` and
  `(tenant_id,record_id,id)` for downstream composite FKs.
- The **current vehicle is derived through the record**, never independently
  mutable on a receipt. `uploaded_vehicle_id` is an immutable UUID audit value
  recording the route at upload, not a current-vehicle authority or cascading FK.
- `filename` String(180), `media_type` String(32), `size_bytes` Integer,
  `content_sha256` String(64): immutable after upload. Detected MIME is exactly
  `application/pdf`, `image/jpeg` or `image/png`.
- Unique `(tenant_id,record_id,content_sha256)` includes removed rows. The same
  bytes may belong to a different service record; never deduplicate across
  records or tenants and never disclose a cross-record hash match.
- `version` Integer starts at1; `removed_at` nullable timezone timestamp.
  `created_by_user_id/name` and `updated_by_user_id/name` use actor UUID and name
  snapshots, with no user FK that could break retained attribution on deletion.
- Checks: version >=1; size 1..5,242,880; MIME allowlist. Index
  `(tenant_id,record_id,created_at,id)`. Filename, hash and content are not editable.

`ExternalServiceReceiptBlob` / `external_service_receipt_blobs`:

- `tenant_id`, `receipt_id`, unique `(tenant_id,receipt_id)`; composite RESTRICT
  FK to receipt `(tenant_id,id)`.
- `content` non-null LargeBinary / PostgreSQL BYTEA, deferred with implicit
  loading disabled (`raiseload`), with PostgreSQL octet-length check
  1..5,242,880. Fetch explicitly only from the authorized download service.
- Create metadata, blob and upload event in one transaction. Stored bytes are
  the original validated upload; metadata size/hash must match those bytes.
  No response schema, audit snapshot, generic record list or error serializes
  content. No eager relationship loads of blobs.

`ExternalServiceReceiptEvent` / `external_service_receipt_events`:

- `tenant_id`, `record_id`, `receipt_id`; composite RESTRICT FK to receipt
  `(tenant_id,record_id,id)` prevents cross-record audit attachment.
- `request_id` UUID, `request_hash` String(64), unique `(tenant_id,request_id)`
  within this receipt-event namespace. DB119 service-event IDs remain a separate
  namespace; frontend nevertheless generates a fresh UUID per logical action.
- `version` Integer >=1, unique `(tenant_id,receipt_id,version)`; `action` is
  upload/remove/restore. Actor UUID/name, timestamp, nullable reason and JSONB
  snapshot of receipt metadata after the action, including the then-current
  vehicle ID. No bytes or URLs in snapshots. Events are append-only.

Receipt actions do **not** increment `ExternalServiceRecord.version`, rewrite
its attribution, or create DB119 service events. Each receipt owns its version.
All actions still check the current parent record version/lifecycle under lock.
Existing service edit/void/restore API shapes and service history remain intact.

## Authorization and parent lifecycle

Use `get_current_active_user` and exactly the DB119 allowlist: garage_owner,
garage_admin, receptionist. Deny other roles before receipt queries or reading
upload bodies. No platform-super-admin, customer, driver, mechanic or
fleet-manager exception. Missing tenant is400, missing authentication401,
forbidden role403.

Load active vehicle by authenticated tenant + vehicle ID, then service record
by tenant + record ID + current vehicle ID, then receipt by tenant + record ID +
receipt ID. Unknown, foreign, archived or wrong-parent identities return the
same404 with no filename, content, actor or other identity disclosure. Never
accept tenant, actor, current vehicle, hash or MIME authority from form fields.

List and audit metadata are readable while the service is voided, through the
existing explicit Show voided flow. **New upload/remove/restore and downloads
require an active service record.** Removed receipts cannot be downloaded until
restored. Voiding a service does not remove its receipts or alter their versions;
restoring the service reveals their retained active/removed states. Exact replay
of an already committed mutation may return current metadata after a later
void/removal; this performs no new write and grants no download access.

Vehicle merge needs no receipt move: current linkage follows the existing
record move inside merge's transaction. Keep uploaded_vehicle_id and earlier
audit snapshots unchanged. Old archived-vehicle routes return404; no silent
redirect of uploads or stale write retries. Customer relinks do not duplicate,
move, expose or purge receipt files.

## HTTP contract

Base: `/api/v1/vehicles/{vehicle_id}/external-services/{record_id}/receipts`.
Every success and error is private and non-cacheable. All JSON mutation bodies
use extra=forbid. Upload uses raw binary bytes, not multipart.

`GET ?include_removed=false` returns metadata only. The complete retained set
is bounded at10, so this endpoint needs no pagination:

```json
{
  "items": [{
    "id": "33333333-3333-4333-8333-333333333333",
    "record_id": "22222222-2222-4222-8222-222222222222",
    "vehicle_id": "11111111-1111-4111-8111-111111111111",
    "uploaded_vehicle_id": "11111111-1111-4111-8111-111111111111",
    "filename": "QA-outside-shop-receipt.pdf",
    "media_type": "application/pdf",
    "size_bytes": 1024,
    "version": 1,
    "removed_at": null,
    "created_at": "2026-10-14T15:00:00Z",
    "updated_at": "2026-10-14T15:00:00Z",
    "created_by_user_id": "44444444-4444-4444-8444-444444444444",
    "created_by_name": "QA Staff",
    "updated_by_user_id": "44444444-4444-4444-8444-444444444444",
    "updated_by_name": "QA Staff"
  }],
  "total": 1,
  "retained_count": 1,
  "retained_bytes": 1024,
  "max_files": 10,
  "max_file_bytes": 5242880,
  "max_total_bytes": 52428800,
  "record_version": 3,
  "record_voided_at": null
}
```

`total` counts the filtered items; retained counts include removed items.
Order created_at DESC, id DESC. SHA256 is internal and omitted from API output.
The IDs and1024-byte size above are the shared UI fixture, not production data.

`POST` uploads the File as raw request bytes with these required headers:

| Header | Value |
|---|---|
| `Content-Type` | `application/octet-stream` |
| `X-Request-ID` | Canonical UUID string |
| `X-Expected-Record-Version` | Positive base-10 integer string; reject signs, fractions and coercible junk |
| `X-Receipt-Filename` | `encodeURIComponent(file.name)`; percent-encoded UTF-8, at most2048 ASCII characters |

Reject duplicate metadata headers, invalid percent escapes, invalid UTF-8 and
missing/invalid fields as422. Decode filename exactly once, then normalize as
below. Header declarations never determine detected file type. Metadata is in
headers rather than URL query strings so receipt names do not enter access URLs.

Authenticate and verify parent access before consuming the body. Read
`Request.stream()` incrementally, rejecting once actual bytes exceed5,242,880;
never call an unbounded `request.body()` or form parser. Content-Length is only
an early rejection hint, not the limit authority: missing, dishonest and chunked
bodies are still bounded. Release buffers on failure/disconnect; validate bytes
before acquiring write locks. Multipart and other declared content types return
415 `receipt_type`. Browser client posts the File with the existing authenticated
API client and explicit application/octet-stream header.

201 first upload,200 exact replay. All receipt mutations return:

```json
{"receipt": "<full receipt item above>", "replayed": false, "record_version": 3, "record_voided_at": null}
```

The quoted receipt placeholder means an object with that schema, not a string
in the actual response. Return the current receipt and current parent version,
including for replay; never return a stale event snapshot as current state.

`POST /{receipt_id}/remove` JSON:

```json
{"request_id":"55555555-5555-4555-8555-555555555555","expected_record_version":3,"expected_version":1,"reason":"Attached the wrong receipt"}
```

Reason is required trimmed text,1..500 characters. Set removed_at, increment
receipt version once and append one remove event. Preserve bytes and original
upload attribution.200 mutation envelope.

`POST /{receipt_id}/restore` JSON:

```json
{"request_id":"66666666-6666-4666-8666-666666666666","expected_record_version":3,"expected_version":2}
```

Clear removed_at, increment receipt version once and append one restore event.
Restoration consumes no new capacity.200 mutation envelope. A new remove against
removed or restore against active is409, not a second success event.

`GET /{receipt_id}/history?skip=0&limit=10` returns
`{items,total,has_more}`; skip >=0, limit1..100, version DESC. Each item contains
id, receipt_id, record_id, version, action, actor_user_id, actor_name, created_at,
reason (nullable) and snapshot (the receipt item at that action). This remains
readable for removed receipts and voided parents under the same access checks.

`GET /{receipt_id}/download` returns only the authorized original bytes with:

```text
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="<safe ASCII filename>"; filename*=UTF-8''<percent-encoded normalized filename>
Cache-Control: private, no-store, max-age=0
Pragma: no-cache
X-Content-Type-Options: nosniff
Content-Security-Policy: sandbox; default-src 'none'
Referrer-Policy: no-referrer
Content-Length: <validated stored size>
```

No redirect, signed/public URL, ETag, conditional304, range206 or inline preview.
Ignore Range and return an authorized full200. Every request independently
checks current access and lifecycle, with receipt/parent/active vehicle joined
when selecting the blob so separate pre-checks cannot authorize another route.
A download authorized immediately before a concurrent removal can complete;
subsequent requests see the removal. Browser-download authorization is not
revocation of already downloaded copies.

Use these response headers for metadata/mutations/errors as applicable:
Cache-Control private,no-store,max-age=0; Pragma no-cache; nosniff. Do not cache
private error bodies via middleware or convert auth errors into downloadable
error files. Do not log body/file data, unsanitized filenames or file hashes.

Receipt-specific errors use FastAPI's `detail` object
`{"code":"...","message":"..."}`. Ordinary request field validation may
retain the standard422 validation list. Codes/messages are stable:

| Status / code | Meaning and operator message |
|---|---|
|404 `receipt_not_found`|Vehicle, service record or receipt not found.|
|409 `request_id_conflict`|This save ID has already been used. Refresh and try again.|
|409 `record_changed`|This service record has changed. Refresh it before saving.|
|409 `receipt_changed`|This receipt has changed. Refresh it before saving.|
|409 `record_voided`|Restore this service record before using its receipts.|
|409 `receipt_removed`|Restore this receipt before downloading it.|
|409 `receipt_already_removed`|This receipt is already removed.|
|409 `receipt_already_active`|This receipt is already active.|
|409 `duplicate_receipt`|This file is already attached to this service record.|
|409 `duplicate_removed_receipt`|This file is retained under Show removed. Restore it there.|
|409 `receipt_capacity`|This service record has reached its retained receipt limit. Removed files still count.|
|413 `receipt_too_large`|Use a file up to5 MiB.|
|415 `receipt_type`|Use a PDF, JPEG or PNG receipt.|
|422 `receipt_invalid`|This receipt file is empty, invalid or cannot be safely processed.|

Duplicate errors may include `receipt_id` for the already-authorized same
record, never another record/tenant. Unexpected database/transport failures
remain5xx or network failures; never report success while discarding a file.

## Validation and content handling

Trust bytes rather than filename or declared MIME. Upload transport uses only
`application/octet-stream`; detect PDF/JPEG/PNG from the bounded bytes. Reject
empty/unsupported content. Normalize the extension to the detected type rather
than accepting it as authority.

Normalize display/download filename server-side: Unicode NFC; take basename
after treating both slash types as separators; remove C0/C1 controls, DEL and
bidi control characters; trim surrounding whitespace/dots; bound to180 Unicode
characters. Use `receipt` when empty. Replace its extension with the detected
type's canonical `.pdf`, `.jpg` or `.png`, preserving the180-character limit.
Never use this value as a storage path. Header ASCII fallback is separately
allowlisted to letters/digits/dot/underscore/hyphen, bounded and quoted; use a
standard UTF-8 RFC5987 percent encoder for filename*. No raw CR/LF, quote,
backslash or unescaped Unicode interpolation into headers. UI renders text only.

JPEG/PNG: use the existing Pillow dependency; verify format and integrity, then
reopen and decode under a maximum of **20,000,000 pixels** and maximum **10,000
pixels per dimension**. Reject decompression-bomb warnings/errors, truncated
images and multi-frame/animated files. Check dimensions before decode; do not
generate thumbnails or otherwise process EXIF. Bound processing off the async
event loop. Retain original bytes after successful validation, not a recompressed
substitute. Byte signature alone is insufficient for images.

PDF: bound bytes, require a `%PDF-1.x` (x=0..7) or `%PDF-2.0` header at byte0 and
a terminal `%%EOF` marker after stripping permitted trailing ASCII whitespace.
Reject obvious incomplete/non-PDF bodies. Do not parse/render/decompress PDF
objects on the server and do not display the file inline in the app. Signature
checks do **not** prove PDF structural validity or absence of scripts, links,
embedded files or malware. Do not claim “scanned” or “safe PDF,” and do not use
regex keyword blacklists as a substitute for a parser/scanner. Authenticated
storage plus octet-stream forced download is the containment boundary for this
release. Any future preview/render/OCR/public-sharing capability requires its
own parser/sandbox/security contract before activation.

## Replay, concurrency and capacity

Validate bounded content before taking write locks. Parent/role pre-checks do
not replace the transactional revalidation. Every mutation acquires fresh
`FOR UPDATE` locks in the existing order: active vehicle, service record, then
target receipt when one exists. Never lock a receipt first. This serializes
against service edits/voids, record merges and other uploads to the same record.

After authorization and exact route revalidation:

1. Compute canonical input hash including action, tenant-independent route
   vehicle/record/receipt IDs, normalized filename, detected MIME, size and
   SHA256 for uploads, expected_record_version, expected_version when present,
   and normalized reason. Actor identity is checked separately. Request ID is
   the lookup key, not a content field. Use stable sorted canonical JSON.
2. Look up `(tenant_id,request_id)` before stale-version, capacity, duplicate or
   lifecycle checks. Exact same actor/action/target/input is replay: return
   current authorized metadata, no second blob/event/version advance. A changed
   actor, target, file bytes, filename, reason or version is409 conflict.
3. For a new action, check expected_record_version and parent active state;
   check receipt expected_version and lifecycle for remove/restore.
4. For upload, check retained same-record content hash **before** capacity:
   active duplicate409 or removed duplicate409, without a new event. New request
   IDs do not silently restore a removed file or bypass duplicate detection.
5. Count all retained metadata and sum sizes under the record lock. Reject a
   file that would exceed either bound. Insert metadata/blob/upload event as
   one savepoint/transaction; remove/restore update+event is equally atomic.

Database uniques are final concurrent guards. Cross-vehicle request-ID
collisions must safely roll back the losing savepoint and resolve to exact
replay or generic409; no orphan metadata/blob and no raw integrity500. Do not
swallow unrelated integrity failures. Replays and reads never alter attribution.

Two new uploads of identical bytes with different IDs yield one upload and one
same-record duplicate409. A lost-response retry with the original ID yields200
replayed even if capacity is now full or the file/parent later changed lifecycle.
Concurrent upload versus service void/edit obeys the locked parent version:
upload wins and persists before void, or changed parent rejects the upload.
Concurrent remove/restore from one receipt version has one winner. Merge wins
against an old URL ->404; upload wins -> receipt follows its moved record.

## Frontend consumption and acceptance fixture

Add a compact Receipts disclosure per saved service record in
`ExternalServiceHistory`. Do not change creation of the service into a combined
file transaction. Once the record is saved, the operator can attach receipts to
that exact record; later upload failure must not imply the service save failed.
Use the app's Lucide chevron, named controls and visible uploaded/removed states.
Only fetch metadata on opening. Show filename/type/size and actor/date, with
Download and Remove; Show removed exposes Restore and retained attribution.
Expandable receipt history shows upload/remove/restore actor/time and reason.
For voided parents show retained metadata with Restore service instruction.

Use the DB119 tenant/actor/role/authSessionEpoch/vehicle scoped remount and query
keys, adding record ID and receipt ID where needed. Abort requests on context
change, discard late responses, clear file handles/error/draft state on identity
change, and remove incompatible cached metadata. Validate response IDs against
the active vehicle/record/receipt using schemas; do not trust a valid-looking
response for another target. No file blobs or request payloads in localStorage,
query persistence, analytics, monitoring breadcrumbs or global caches.

File input accepts `.pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png`;
client size/type checks help the operator but do not replace server checks.
Use single-flight actions. Keep selected File, normalized action payload and
request UUID in memory for explicit Retry after uncertain transport; changed
file/action/version creates a fresh UUID. No automatic mutation retries. If
reload loses an uncertain attempt, reload metadata first; dedupe prevents a
later selection of the same bytes from making a copy.

Stale409 retains the file/reason draft and offers Refresh receipts/record.
Adopting a refreshed version requires an explicit resubmit with a new attempt
ID; do not silently overwrite another staff member's change. Successful write
plus failed refetch remains a saved result with a separately retryable list.
Capacity, duplicate, removed duplicate, invalid and oversize errors are local
to this section, leaving service edit/history and truck return state intact.

Download via the authenticated API client with `responseType: 'blob'`; validate
status/expected binary response and identity before creating a temporary object
URL and clicking an `a` with `download`. Never `window.open` a receipt or embed
it in an iframe/image/PDF viewer. Revoke object URLs after initiating download
and on cleanup; no persistent client blob cache. Decode an error response as
bounded JSON/text for a visible error, not a saved “receipt.”

Remove confirmation explains recovery and requires a reason. Cancel/Escape/
named close issue no write and return focus. Keep whole button labels, compact
desktop rows and the existing single mobile scroll owner; long filenames wrap
within their column. Preserve customer/order return URLs and history filters.

Shared synthetic fixture: use the UUIDs/list item above with a saved parent
version3. Upload returns201 item version1; lost-response retry returns200 same
ID/version with replayed true; remove returns version2/removed_at set and one
remove event; restore returns version3/removed_at null and one restore event.
Parent version stays3 throughout. Include another tenant and another truck in
test setup, a second service on the same truck, a removed file, a voided parent,
a long Unicode filename and two distinct same-name files. Real HTTP tests must
generate actual minimal PDF/JPEG/PNG bytes locally; the UI size1024 is a mock,
not a validation assertion. Do not upload real customer documents for QA.

## Verification and release

Backend focused tests extend DB119 fixture/HTTP patterns and include: complete
upload/reload/download/remove/restore audit; actor snapshots; role matrix before
body consumption; cross-tenant/vehicle/record/receipt404; archived/voided parent;
removed downloads; exact replay after later mutations; changed actor/payload/
action/version collisions; same-file duplicates including removed; quotas with
removed rows; overflow including chunked/no Content-Length, rejected multipart and invalid
metadata headers; misleading extensions, malformed/truncated/decompression-bomb/multiframe
images, malformed PDF envelope, safe filename/headers and private errors.
Prove list/history queries do not load blob content. Assert service version,
native invoice/payment/order totals and vehicle mileage/PM remain unchanged.

Use the opt-in isolated PostgreSQL fixture in
`test_operation_execution_postgres.py` and DB119's lock-wait pattern for actual
two-session duplicate upload, cross-vehicle request collision, capacity boundary,
receipt revision conflict, upload-versus-void and upload-versus-vehicle-merge.
Assert one durable blob/event or a clean loser, unchanged earlier snapshots and
no dangling rows. Run PostgreSQL migration upgrade, constraints and clean empty
downgrade/upgrade cycle; SQLite create_all alone is insufficient. Verify
composite FKs, per-record hash uniqueness and byte-length checks directly.

Frontend/component tests cover the shared fixture and malformed/mismatched
responses, permission/session/vehicle changes and late results, failed download,
lost-response retry, stale draft, limits, duplicates, remove/cancel/restore,
disabled voided actions and full filename wrapping. Independent browser QA
covers both customer and repair-order entry paths at1280 desktop,390/320 phone
and740x400 landscape: upload, reload, authenticated download byte comparison,
remove, Show removed, restore, return navigation, error recovery and one scroll
owner. Record viewport emulation as such; do not imply physical-device proof.

No production real-customer documents. Use a labeled synthetic QA service and
locally generated non-sensitive receipt, exercise download/remove/restore, then
leave the synthetic receipt removed and service voided. Record exact tested
head, protected CI, merge/deploy SHA, migration head and database readiness.
Independent Security/QA must accept privacy, bounded parsing/storage, replay,
merge isolation and the explicit download-only PDF containment boundary.

Rollback on disclosure, duplicate/orphan blobs, resource-limit bypass, failed
download/restore, any financial/PM effect or unusable staff workspace. Revert
application code to the previous release while **retaining all three additive
tables and stored data**; old code ignores them. Do not downgrade/drop tables
after any upload. Empty disposable databases may test downgrade in order:
events, blobs, receipts. No financial backfill or provider mutation to reverse.
Observe readiness/errors and the changed synthetic workflow after deploy;
complete the board only after required independent/release evidence exists.

## Handoff

Board ID: DB-129.
From / To: Architecture & API Contracts → Backend & Integrations / Frontend & UX.
User outcome: private, recoverable receipts attached to exact outside-shop work.
Scope completed: API, data, validation, lifecycle, retry, fixtures and rollback
contract; repository/source inspection only.
Scope explicitly not completed: implementation, migration execution, tests,
runtime acceptance, independent gates, PR/merge/deploy.
Contract or migration impact: three additive private tables and nested routes;
DB119 record contract and native financial/vehicle semantics preserved.
Acceptance evidence: existing DB119 service/model/API/tests, Pillow dependency,
head171 and PR532 file inventory inspected; no runtime claim.
Known failures / risks: database storage increases within per-record bounds;
signature-valid PDFs are not claimed malware-free; raw upload cap must apply
while reading actual streamed bytes. Recheck migration head at integration.
Branch / environment: `codex/external-service-receipts`,
`/Users/sergio_m1_promax/.codex/worktrees/ets-checkpoint-merge/truck-pit-stop`.
Next required action: owner implements contract, frontend consumes fixture,
then fresh independent Security/QA review and authorized release.
Return condition: changed roles, file/storage limits, inline rendering/public
URLs, duplicate policy, parent-version/lifecycle or retention behavior.
