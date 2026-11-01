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
