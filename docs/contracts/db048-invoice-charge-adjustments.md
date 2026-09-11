# DB-048 reversible invoice tax, supplies and customer card surcharge

Owner Backend; root frontend/release. Extends the one-time exemption UI without
editing its immutable legacy audit. Migration145 follows customer-default144.

POST `/api/v1/payments/invoices/{id}/charge-adjustments`, Idempotency-Key:
`{expected_settlement_version:int>=1,tax_exempt:bool,shop_supplies_enabled:bool,card_fee_enabled?:bool|null,support_reference?:string|null}`.
Card fee is a strict boolean when supplied. Omission/null preserves the current
saved setting; historical audit settings without this field default to true.
Omitted/null card_fee_enabled is excluded from request hashing, preserving exact
pre-extension idempotent retries. Explicit true/false participates in the hash.
No reason. Trim optional reference, max255; forbid extras. Response canonical
settlement. Owner/admin plus payments, active same-tenant invoice/customer/order/
tenant only. Required version, settlement/invoice/ancestry locks, exact replay and conflicting
key rejection. Zero existing payments/attempts/ledger/credits/refunds/reservations;
unsafe export/history/ancestry remains blocked by existing exemption guards.

Add optional `charge_controls` to summary:
`{tax_exempt,shop_supplies_enabled,card_fee_enabled,can_adjust,unavailable_reason,support_reference,
original_shop_supplies_amount,original_tax_amount,original_card_fee_amount}`. Reference staff-only.
Sales tax ON means tax_exempt=false; supplies/card fee ON means enabled=true.
OFF keeps its breakdown row visible at $0.00. These controls do not choose tender.
UI toggles save immediately with one serialized request; optional reference saves
on blur/Enter. No Update invoice confirmation is required. Pause payment while
saving; authoritative response updates totals. Explicit rejection restores saved
state; uncertain responses lock further edits and retry the identical request/key.
Stale version refreshes rather than overwrites. No quote endpoint or automatic
tender selection; ordinary payment quote recalculates after save.

First original snapshot is legacy invoice.tax_exemption.before (including
customer-profile source), else untouched invoice money. Later adjustments reuse
the immutable first original. Validate current against last adjusted snapshot (or
legacy audit.after before first adjustment); reject unknown drift/incoherence.
Subtotal is repair net, invoice discount after tax. Preserve both. Restore exact
original supplies/fee/tax when enabled/taxable. Supplies off makes supplies0 and
fee=round(subtotal*originalfee/(subtotal+originalsupplies)); taxable tax uses frozen
originaltax/(subtotal+originalsupplies+originalfee) on newsubtotal+supplies+fee.
Exemption makes tax0 including fee tax. Never read current tenant rates. Reject
negative/inconsistent or nonpositive principal; no invented original supplies.
Card fee OFF makes service_fee_amount=0 and taxable tax is recalculated from the
same frozen ratio on subtotal+enabled supplies only. This waives the customer
surcharge and its tax; the shop absorbs actual processor fees, which this command
does not invent, alter or record. ON restores frozen original/prorated fee.
Settlement max_card_fee and max_card_fee_tax are zero while waived; the existing
quote, partial/full attempts, refund and accounting paths consume these persisted
zero customer-charge components. Existing money still prevents later adjustment.

Store append-only before/after/settings/original/actor/time/idempotency evidence
in InvoiceChargeAdjustment, tenant-safe insertion and immutable UPDATE/DELETE.
Update existing invoice money and settlement money snapshots/version, not its
payment ledger or export state. Existing invoice.tax_exemption JSON never changes.
Effective exemption for summary/receipts comes from latest adjustment, falling
back to original audit. Old endpoint cannot apply after adjustment history exists.
No invoice column addition; empty adjustment history preserves prior review hashes,
nonempty history is bound to ancestry digests. Profile default remains independent.
The card-fee extension uses existing migration145 evidence JSON only: no migration
or invoice column, no rewrite of applied migrations or existing audit rows.

Gate: on/off roundtrips for legacy/manual/profile exemptions and supplies,
original-rate restore despite tenant drift, receipt labels, idempotency/stale and
role/tenant negatives, current/ancestor payment/export blockers, concurrency with
payment/another adjustment, immutable original audit and retained review holds.
