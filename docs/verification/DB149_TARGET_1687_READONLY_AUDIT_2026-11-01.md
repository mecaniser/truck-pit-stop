# DB149 — corrected target invoice1687: read-only audit

November1,2026. Correct conversion candidate is ETS invoice1687/service1821,
268.44USD for the authorized customer's truck609. The earlier314.02historical
invoice is not this target; user states it was cleared. This audit does not
clear, convert or otherwise modify that earlier record.

## Exact source and DBN identity

User opened the actual ETS service1821 invoice and parent verified current total
and balance268.44. The source page's QuickBooks link identifies transaction7104.
Preserved source evidence independently binds public service1821 to internal
service506423 and immutable invoice468019/number1687 in the verified shop.
DBN has one exact matching imported invoiceETSINV-1687 on its active imported
repair order. Private receipts retain UUIDs and tenant/customer/vehicle identifiers;
no name/amount-only association was used. Source vehicle mapping agrees with609.

Exact-source-envelope, direct repair-order, same service-job, and supersession
lineage searches found only that existing imported invoice, not a native copy.
No target accounting links exist. This excludes matches by those retained
identities; it does not invent a match for unrelated or unlinked manual records.

## Financial evidence

At20:47:57UTC production audit ran under PostgreSQL `SET TRANSACTION READ ONLY`.
The existing DBN row is sent, unpaid, total268.44USD. Subtotal248.12 and tax20.32
agree with the source total; the supplies1.80field must not be added again to
that subtotal (source screenshots show60labor,186.32parts and1.80supplies).
No paid timestamp, settlement, Payment row, payment attempt, ledger event,
refund or targeted credit application exists for this exact invoice.

Canonical imported billing passes validation: evidence_basis=ets_source_snapshot,
payment_status=unpaid, completed0.00, remaining268.44, review_required=false, no
review reasons. Complete singleton manifest identifies invoice468019 and internal
service506423; USD source total and balance both268.44, status5, zero payment
allocations and untruncated coverage. Stored revision digest
`d514f1708673c1e0715c1a70a4286957948636d09f2f6a7a0835b4d0d32e4bbf`
validates. Original facts were captured October21; a digest-bound matching-fact
confirmation at2026-11-01T02:06:33.240Z supplies the current source watermark.
The reader accepts it within24hours; that window ends2026-11-02T02:06:33.240Z.
Recheck before adoption/collection rather than treating this result as permanent.

This proves the source-observed unpaid balance under the current mirror contract.
Its retained settlement_semantics remains unverified: native collection ownership,
idempotency, synchronization and duplicate-accounting handoff still require the
new reviewed collection contract. No existing native settlement is fabricated.

## Accounting and QuickBooks read limitation

The imported row currently has standard accounting_policy but no QuickBooks
invoice ID, shop activation or accounting link; its pending sync label is not
proof that an accounting invoice was created. Do not automatically create a new
QBO invoice: the exact ETS page already links transaction7104.

A targeted QBO GET for invoice7104 used the existing shop connection and
decrypted access token only in memory. At20:50:25UTC the stored token was
expired and the GET returned401. No OAuth refresh, POST, token/configuration
write or accounting mutation occurred. The shop connection is connected with
a configured realm, but current QBO7104 document identity, balance, payments,
credits and customer mapping were not verified by that failed read. A legitimate
QBO UI read or authorized normal credential renewal/read is needed to close
that exact accounting check; do not infer zero from unavailable data.

## Boundary and receipts

No invoice, settlement, payment, repair order, source status, provider financial
operation, import, collector job, restored record, email/SMS or configuration was
created or changed. The user requests a DBN-primary collection flow with manual
ETS acknowledgement and confirmed ETS payments imported back; this audit supplies
the corrected exact identity and source balance for that implementation, not
a payment attempt or an ETS-paid action.

Private owner-only local receipts retain full source envelope, exact identities,
canonical reader output, duplicate/lineage result and the401 accounting response.
No credentials, customer PII or access-bearing token URLs are emitted here.

### Later authenticated QuickBooks UI verification

On November1 at approximately21:05UTC the user completed normal QuickBooks
Chrome sign-in. Parent opened the exact source-linked transaction7104 and
observed Invoice1687 in the shop's company, with the matching customer context,
truck609/wiper work, subtotal248.12, tax20.32, total268.44 and balance due268.44.
This is actual read-only UI confirmation of the existing accounting debt; no
payment or edit was submitted. An initial unsaved blank invoice reached during
login redirection was left without saving before exact7104 was opened.

The earlier API401 remains a separate credential-health fact; no token refresh
or API success is claimed. The current QBO UI balance is verified, replacing
the earlier unavailable-current-balance checkpoint. No additional QBO invoice
should be created for this existing debt.

Parent then read exact QBO audit history for transaction7104: Invoice1687 has
two visible October20 10:06amEDT timeline events (Added and indirect system
edit); both versions show amount268.44 and open balance268.44. No payment
activity is displayed in that history. This is visible-history corroboration,
not proof about every possible in-flight provider payment. No edit/save occurred.

### Bounded refresh implementation (not executed in production)

The normal nightly importer is unsuitable for an evidence refresh: it can
create/backfill repair orders, invoices and payments before preserving source
evidence. The additive targeted commands separate source reads from database
metadata persistence:

- `backend/scripts/easytruck_sync/capture_invoice_evidence.js` defaults to a
  no-login plan. Explicit `--capture` reads the complete source invoice manifest
  and exactly one invoice page, checks configured HTTPS shop and all source
  identities, and exclusively creates a private normalized evidence file.
  It invokes no importer, payment action or provider accounting action.
- `backend/scripts/easytruck_sync/persist_invoice_evidence.py` defaults to a
  serializable read-only plan. Explicit `--commit` requires exact capture and
  existing-envelope SHA256 plus handoff version, the prepared tenant/source
  identity, complete singleton manifest and a source observation after the
  owner acknowledgement and within24hours. It acquires the same tenant
  financial advisory lock as collection, appends a digest-bound observation
  and updates only `invoices.ets_source_evidence`. Scoped financial fingerprints
  before/after guard against incidental invoice/payment/accounting/task writes;
  mismatch rolls the transaction back. No automatic retry is implemented.

Operator template (all IDs/digests must come from the prepared handoff; database
and collector credentials remain in approved private environment configuration):

```sh
node backend/scripts/easytruck_sync/capture_invoice_evidence.js \
  --tenant-id '<tenant UUID>' --shop sh_15mw458gpRl487OF \
  --service-number 1821 --service-internal-id 506423 \
  --invoice-internal-id 468019 --invoice-number 1687
# Add --capture --out '<new private file>' only for an authorized source read.
python backend/scripts/easytruck_sync/persist_invoice_evidence.py \
  --tenant-id '<tenant UUID>' --handoff-id '<prepared handoff UUID>' \
  --invoice-id '<source DBN invoice UUID>' --capture '<private capture file>'
# Explicit metadata commit additionally requires --commit,
# --expected-capture-sha256, --expected-envelope-sha256 and --expected-version.
```

Importer create/backfill/payment-sync paths now take the same tenant advisory
lock and skip a permanently assigned source identity in every handoff state,
including closed/deleted records. Trusted immutable shop/invoice identity and
known source invoice UUID are primary guards; service/invoice-number matching
also conservatively fences missing-capture cases. This does not permit source
payment mirroring into a new duplicate invoice; the collection service owns
confirmed receipt reconciliation.

Only the allowlisted `DBN-RECEIPT:<UUID>` marker survives source payment notes;
other notes are discarded, ambiguous markers are omitted. Genuine explicit UTC
ISO source dates with valid calendar values can use `source_datetime_utc`;
naive, day-only, invalid-calendar and other dates remain unverified and must
hold date-dependent reconciliation.

Verification: parser/ingestion/source-evidence Python34PASS, Node5PASS;
additional actual disposable PostgreSQL11PASS exercises all handoff states,
deleted identity permanence, tenant lock contention, evidence-only commit,
read-only dry-run and rollback when a deliberately malicious trigger changes a
payment. Tests use their own random schema on the disposable fixture and clean
only that schema. No production capture, metadata commit, financial write,
provider action, credential refresh, deploy or nightly run occurred here.
Implementation owner cannot approve the independent QA/security/release gate.

### Source customer proof extension

A later read-only customer-binding check found the original repair order belongs
to the ETS customer97052, while the existing portal account belongs to a distinct
DBN customer record in the same tenant. Current vehicle ownership points to the
DBN customer but is not bill-to authority. There was no historical mapping,
verified evidence or decision for this invoice. User subsequently explicitly
authorized the same-legal-business cross-customer bill-to; that authorization
must be separately snapshotted by the handoff service, not inferred from names
or vehicle ownership.

Parent grounded the current source schema with a full reload of exact service1821:
component `services/show/invoice`, linked service internal506423 and invoice468019,
with embedded `service.customer.id` public97052, a separate customer UUID and
`deleted:false`. The public ID matches the visible customer route. No numeric
customer internal ID, customer number or customer shop ID is present; none is
invented. Full reload matters because an earlier SPA data-page attribute was stale.

The extractor now retains only `source_customer_id`, `source_customer_uuid`,
`source_customer_deleted` and `source_customer_binding_kind` equal to
`embedded_service_customer` from that exact component and association. Names,
contact details and arbitrary customer fields are discarded. Both normalizers
conditionally retain only complete, valid proof; legacy evidence shape and hashes
remain unchanged. Wrong source component is rejected. A customer change is a
new digest-bound fact revision, allowing collection validation to hold explicitly.

Target capture requires the customer proof. Evidence persistence holds a
cross-customer handoff lacking proof, while retaining a changed customer proof
as evidence rather than silently discarding source drift. The handoff service
must compare it with immutable approved original source customer identity;
this parser/ops partition does not itself approve legal bill-to reassignment.

Updated checks: Python36PASS, Node6PASS, disposable PostgreSQL12PASS. The added
PG case proves missing-proof cross-customer hold, preservation of changed
customer identity and unchanged financial fingerprints. No production capture,
metadata write, identity reassignment or financial mutation was executed.

### Evidence bootstrap before preparation

Strict remote customer proof is required before creating a handoff. Legacy
captures lack that proof, so the evidence-only command now has an explicit
`--bootstrap` path after migration197 exists. It requires no canonical handoff
for the invoice or exact remote debt in any state, including closed/deleted.
After preparation only the existing versioned handoff mode is permitted.

Bootstrap requires original imported invoice/repair-order/customer identity in
the same tenant, original source customer UUID and ETS public ID, reviewed remote
customer UUID, exact service/invoice IDs, complete singleton manifest and fresh
source proof. Deleted, cancelled, voided, internal or mismatched identities hold.
Existing envelope and last immutable fact digests must match. The owner-only
capture file is separately bound by its SHA256 before database access.

Example supplements to the existing persistence command (placeholders are
reviewed values, not permission to infer them from names or vehicle ownership):

```sh
--bootstrap --ets-shop-id sh_15mw458gpRl487OF \
--source-service-number 1821 --ets-service-internal-id 506423 \
--ets-invoice-internal-id 468019 --source-invoice-number 1687 \
--source-customer-id '<original ETS customer DB UUID>' \
--expected-source-customer-id 97052 \
--expected-source-customer-uuid '<reviewed remote customer UUID>' \
--expected-capture-sha256 '<private capture file SHA256>' \
--expected-envelope-sha256 '<current envelope SHA256>' \
--expected-evidence-sha256 '<current last observation SHA256>'
```

Default remains serializable read-only dry-run. Only explicit `--commit` takes
the tenant financial lock and updates the original invoice evidence column.
Before/after fingerprints include financial rows plus the entire original repair
order and customer rows, so even incidental trigger changes to billing identity
roll back. No invoice creation, settlement/payment, customer or repair-order
mutation, importer execution or provider action is performed.

Disposable PostgreSQL35PASS covers bootstrap dry-run, evidence commit, subsequent
prepared fixture and post-acknowledgement versioned refresh; foreign/deleted/
identity/digest/customer drift holds; all permanent handoff states reject bypass;
lock contention; and rollback of deliberately malicious related-customer writes.
The middle preparation row is explicitly a synthetic fixture; actual migration197
service preparation/activation acceptance remains the independent service gate.
No production bootstrap or other production operation was executed.

### Independent archived-source bootstrap correction

The independent full-migration service rehearsal found the bootstrap ownership
guard was stricter than the frozen handoff contract: it rejected a soft-archived
source repair order even with exact verified live ETS lineage. The bootstrap
now permits that archive only within the existing exact imported source,
tenant, invoice, customer and fresh proof checks. It never clears the repair
order archive timestamp or changes its work/status. Missing or non-imported
repair orders, cancelled records, deleted original invoices/customers and
identity mismatches still hold. This supersedes the earlier blanket reference
to rejecting every deleted source record; a soft-archived historical source
repair order is the explicit exception.

Disposable PostgreSQL38PASS includes an archived-source read-only dry run and
commit with identical full repair-order/customer/financial fingerprints and a
retained archive timestamp, plus hard missing/wrong-source/cancelled negatives.
Independent full migration197 bootstrap→prepare→activate acceptance remains a
separate reviewer gate; these focused subset fixtures cannot prove compatibility
with every existing DB048 integrity trigger. No production action occurred.
