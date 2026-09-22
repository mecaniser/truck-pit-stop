# DB-067: ELIS outcome source contract

Contract owner: ELIS integration lead. Implementer: DieselBridge Backend & Integrations.
Status: implemented locally; independent QA/Security PASS; PR/CI and deployment pending.

## Compatibility and activation

The current `repair_order.paid` event and HMAC envelope remain unchanged for
existing consumers. Existing and newly created tenants default to payload v1.
V2 requires native creation proof: both invoice/order `source` are null and an
`InvoiceSettlement` matches tenant, invoice and customer with
`legacy_reconciliation_status=native`. Current invoice creators persist that
projection atomically. Imported or legacy records with missing proof are not
upgraded into native facts. Imported customer/vehicle history alone does not
exclude a genuinely native invoice/order.

An authorized shop operator opts in through the existing conversion settings
endpoint with `payload_version: 2`. Omission preserves the saved version. Only
newly captured events use the selected version: existing queued/delivered event
bodies are immutable and are never rewritten when configuration changes.

The signed native receiver implemented in ELIS is `/events/shop-outcome`; the
existing ELIS canonical receiver remains separate. Activation requires an exact
source-tenant/destination/signing-secret preview and a synthetic signed canary.
No production tenant is enabled by this migration or code release.

## V2 wire contract

See the executable synthetic fixture at
`backend/tests/fixtures/elis-shop-outcome-v2-paid.json`. The source test generates
that fixture through the real payload builder and verifies the actual canonical
wire bytes and HMAC used by delivery. The ELIS receiver suite should consume the
same fixture; independent producer/consumer mocks are insufficient.

V2 retains all v1 fields and adds:

| Field | Semantics |
|---|---|
| `schema_version` | Integer `2` |
| `source_system` | Literal `dieselbridge` |
| `source_revision` | Same UUID as `event_id`, immutable across retries |
| `repair_order_uuid` | Immutable source repair-order UUID |
| `repair_order_number` | Display order number; legacy `repair_order_id` retains this same label |
| `value_basis` | `invoice_settled` for paid; `measurement_adjustment` for corrections |
| `amount_semantics` | `snapshot` for paid; `delta` for corrections |
| `attribution.elis_opportunity_id` | Optional UUID, explicit external reference |

`invoice_id` and `shop_id` remain immutable source UUIDs. `total_amount` remains
a JSON number with two-decimal money precision and currency `USD`. `paid_at` is
the source invoice's paid timestamp; `occurred_at` is event capture time. A
receiver must use the outcome timestamp appropriate to the event, not the
webhook retry time. A reconstructed recovery envelope may have a new capture time: exclude envelope
`occurred_at` from paid-invoice semantic deduplication and use `paid_at` as the
paid outcome effective time. Paid-event identity is `(source shop, invoice_id,
repair_order.paid)`; retries reuse `event_id` and
`Idempotency-Key: repair-order-paid:<invoice UUID>`. Duplicate enqueue returns
the original event, protected by database uniqueness and a savepoint; an outer
financial transaction is not rolled back merely because a notification exists.
Native full-cash confirmation now captures the same durable event in its
financial transaction; rollback removes both payment and event, and confirmation
replay emits no duplicate. This does not create an accounting export. Existing
manual/card and credit-settlement closure hooks already enqueue the event.
The source RO UUID determines job identity, so two invoices on one job are not
automatically two converted jobs.

Attribution is optional, including for organic or unlinked shop jobs. The typed
ELIS reference is accepted by the existing authorized repair-order create/update
APIs and is locked together with other attribution fields after any invoice
exists, even if order status regresses or the invoice is cancelled/soft-deleted. It
is not an authorization grant or proof of ad consent, and ELIS must resolve it
inside its credential-derived tenant. No phone-only automatic job matching is
introduced. The free-text `external_lead_id` remains independent legacy data;
no implicit mapping or conflicting reference rewriting is performed.

### Value and corrections

A paid event's snapshot is the settled invoice face value. It may include
customer credit and is **not proof of cash collected, profit, or a processor
settlement**. Paid status also does not independently attest technician work
completion. Use an explicitly labeled settled-invoice outcome until the separate
job/ledger evidence chain is proven.

Supported correction types remain `repair_order.payment_refunded`,
`repair_order.payment_voided`, and `repair_order.payment_adjusted`. Their amounts
are signed **deltas**, not replacement invoice totals. Refund and void deltas
are negative; a void must equal the negative authoritative completed-payment
amount and is exclusive with other corrections. Adjustments keep the recognized
amount between zero and that authority amount. Authority here is the lower of
invoice face value and the sum of positive completed payments. A correction is
an operator-issued measurement correction; the endpoint does not execute a
refund, void, bank movement or ledger reversal. Paid snapshot and correction
payment-basis amounts may differ for a credit-settled invoice. Receivers must
retain that distinction and must not infer net cash by subtracting these deltas
from invoice face value.

Correction identity is its stable `event_id`/`source_revision`, scoped to shop
and invoice UUID. `Idempotency-Key` reuse with different invoice/type/amount
fails 409. No original-paid-event UUID is required because disabled historical
capture may not have a prior event. A receiver receiving a correction before the
paid snapshot must retain the correction unresolved rather than invent a job or
silently discard it.

## Capture, pause, rollback and retention

`enabled` retains the existing integration/capture control. Setting it false
stops new capture, so it is not the routine delivery rollback mechanism.
`delivery_paused: true` suppresses new worker claims while continuing durable
capture. Claim-to-delivery preflight rechecks pause; already in-flight network
requests may finish and must still be reconciled. Paused claims retain their
retry budget and leases are cleared. Resume with `delivery_paused: false`.

A terminal receiver failure now pauses delivery without disabling capture. The
failed event remains dead and requires existing explicit replay after repair;
new events remain pending. Notification text explains this behavior. An old
client changing only `enabled` does not clear a pause or change payload version.

Existing absolute PII retention still applies to paused events. A pause is not an
indefinite data-retention exemption. Daily retention expires/redacts old work;
metadata retains v2 IDs/value semantics, contact/attribution/service lines are
erased. If source capture is disabled or retention expires, record the affected
interval and reconcile via the tenant-bound export before resuming. Never
rewrite event IDs, clear delivery evidence, or resend unknown submissions as
rollback.

## Read-only recovery export

`GET /api/v1/conversion-exports/paid-repair-orders?schema_version=2` adds the v2
stable IDs and value semantics to JSON and CSV. Default v1 shape remains intact.
V2 JSON returns `coverage` with `paid_invoice_count`, `eligible_native_count`,
and `excluded_native_authority_count` for the full requested window. CSV returns
the same counts in `X-Paid-Invoice-Count`, `X-Eligible-Native-Count`, and
`X-Excluded-Native-Authority-Count` headers. Missing native authority is visible
coverage, not an assertion of zero actual shop jobs.

This is a snapshot export, not a newly created webhook event: it does not invent
`event_id`, `source_revision`, or `occurred_at`. ELIS's reconciliation adapter must
record export provenance and dedupe by source shop/invoice identity, retaining
historical delivery holds. The existing API key binds the tenant; invoice, order
and customer tenant IDs must all agree. Time filtering still uses invoice
`paid_at`, so acquisition-cohort recovery must join to the relevant calls rather
than treating a paid-date filter as a call cohort.

## Migration and local verification

Additive migration `148_elis_outcome_source` follows 147: tenant pause defaults
false, payload version defaults 1 with database constraint 1/2; repair orders gain
nullable external opportunity UUID. No financial rows or feature gates change.
Deploy migration before application/worker code, keep v2 disabled, then perform
the coordinated canary. Routine rollback uses delivery pause, not downgrade;
downgrading removes the new source reference and settings, so requires a
separate data-preservation decision.

Local runtime uses dedicated frontend 5175 / API 8002 from the implementation
checkout with isolated empty PostgreSQL database, migrated 147→148. Direct and
proxied readiness passed. Existing shared sandbox and listeners remain intact.
The integration adds no browser interaction; authenticated production settings
and actual receiver canary remain separate release acceptance.

## Source verification receipt (2026-09-22)

The independent source review reproduced two failures: imported source snapshots
could be labeled native, and regressing an invoiced order's display status could
reopen attribution. The candidate now requires matching native creation proof
and retains an attribution lock whenever a tenant-scoped invoice exists. Missing
proof remains an explicit export coverage count. The native cash closure path
now captures its outcome in the same transaction; rollback and replay are tested.

- Focused source, export, cash and other payment regressions: **193 passed,
  1 skipped** (the optional PostgreSQL check runs separately).
- Dedicated PostgreSQL concurrency: **2 passed** (duplicate enqueue and
  concurrent worker claims).
- Alembic graph has one linear head, `148_elis_outcome_source`; additive migration
  applied to the isolated local database; compile and diff integrity passed.
- Final full backend suite: **1994 passed, 90 skipped, 77 warnings** in
  579.70 seconds, using a clean minimal environment in the isolated API container.
  Optional external/PostgreSQL suites are skipped by the ordinary full run; the
  two new PostgreSQL concurrency cases passed separately as noted above.
- Independent Security retesting: **121 passed, 1 optional PostgreSQL skip**,
  plus direct imported-source, regressed/cancelled-invoice and cash-replay
  reproductions. Independent Security disposition: **PASS**.
- Independent source QA: **193 passed, 1 skipped**, dedicated PostgreSQL
  **2 passed**, and deployed-local migration revision/default/constraint checks.
  Independent QA disposition: **PASS**.
- Cross-repository QA exercised all four source event types through the actual
  sender `_deliver` HMAC wire into the ELIS receiver: all returned 202, duplicate
  receipts returned 202 without duplicate durable events/jobs. QA caught the
  receiver correction-vocabulary mismatch; the ELIS integration lead corrected
  the receiver, preserving the existing source event names.
- Both independent gates bind the frozen backend content fingerprint
  `36963c48e9fea2e86c56c0141a1a11dab65d12764148f04c0ff1bcaaeee8587e`
  (sorted changed backend path + NUL + file bytes + NUL); later edits changed
  only this verification documentation and the board.

Implementation stays local pending parent-coordinated PR and release. No
production tenant is opted in and no production financial record is mutated.
The signed producer/consumer fixture and eventual real held canary are separate
claims from Google acceptance.
