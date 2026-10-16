# Completed invoice outcomes v2

User policy: recognize the final completed repair invoice value before payment.
This signed source contract observes business facts; it never modifies finance or
sends a Google conversion. Deploy the ELIS accepting receiver before enabling this
source revision. Existing configured shops/tenants and HMAC transport are reused.

Both event names remain `repair.completed_invoice_snapshot` and
`repair.completed_invoice_hold`. Envelope `schema_version=2`; remaining fields are
unchanged: event_id, source_system=dieselbridge, shop_id, occurred_at, observed_at,
source_revision, source_observation, snapshot. Hash the full snapshot using sorted
compact JSON. Holds share the source observation stream and canonical job identity.

## ETS

Preserve source=easy_truck_shop_import, ets_shop_id, source_job_id=ets-service:<id>,
service_id/internal_id and repair_order_uuid aliases. Source completed=true,
service_status=60, aware completion instant, invoice_status=10 and verified complete
invoice manifest remain required. Positive USD final invoice totals are observed
without requiring balance zero or payment allocations. V2 invoice entries retain
invoice_id/imported_invoice_uuid/invoice_number/invoice_service_internal_id,
invoice_status=10/currency/total; payment fields are absent. Strict v1 parsing remains
unchanged for old events. Source status10 is retained as the previously verified
code; the current captured production sample contains no completed unpaid invoices,
so an actual unpaid source page still needs runtime proof before claiming that case
has been observed in production.

## Native DBN

Snapshot source=dieselbridge, source_job_id and repair_order_uuid are the same raw
RO UUID used by the paid bridge. Never create a second job at settlement.
completed=true; completed_at is aware work_completed_at, or explicit manager
approval pricing_locked_at only for completed/invoiced/paid orders locked with
invoice_finalized. time_basis is source_work_completed_at or
source_completion_approved_at; value_basis=completed_invoice_total.

Require native source on order/invoice, one active invoice, issued status
sent/overdue/paid, non-null immutable line_items_snapshot, positive exact-cent
invoice total, noninternal/nondeleted/nonvoided resources, and matching tenant/RO
relationships. Drafts and unfinished orders cannot qualify. Invoice manifest:
complete=true, invoice_ids=[UUID], evidence_kind=native_finalized_invoice_manifest.
Invoice fields: invoice_id, invoice_number, invoice_status, currency=USD, total,
finalized=true. Attribution remains nullable elis_opportunity_id/callrail_call_id.

Native hold snapshot contains source/source_job_id/repair_order_uuid/hold_reason.
Reasons: source_fields_missing, source_identity_conflict, source_status_unsupported,
invoice_manifest_incomplete. No initial draft hold event is created; invalidation
of a previously observed completed job creates a hold in its existing stream.

Bounded history capture and tenant lock serialize observations. Native outbox keys
are native-completed:<RO UUID>:<sequence>:<hash>. Payment-only sent/overdue/paid
transitions return the original event; they do not generate another completion.
Actual amount/invoice/identity changes create a source revision. ELIS preserves the
existing repair conversion transaction and holds changes after export; a revision
must never imply a new revenue import. Native unchanged facts do not acquire an
artificial source timestamp on polling. ETS retains the original 24-hour source
freshness rule; native records rely on source invalidation, not ETS scrape TTL.

## Release evidence

Required: version compatibility, draft/internal/tenant/identity negative tests,
completed unpaid native and ETS synthetic tests, replay/payment invariance,
independent QA/Security, protected CI, accepting receiver deployment, source
Web/Worker deployment, and read-only observation of scheduled capture. No manual
source replay, Google resend, campaign change, or financial mutation is included.
