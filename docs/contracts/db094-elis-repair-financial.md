# DB-094 current repair financial manifest and wakeups

Development implementation; no deployment, production grants, credentials or financial changes. This extends the operational-history contract without turning current RO ownership into invoice authorization.

## Complete current-invoice manifest

`GET /api/v1/fleet-invoice-exports/repair-orders/financial` requires the existing active customer-scoped `X-API-Key`. Same-shop active customer, tenant, RO and vehicle boundaries apply. Eligible operational ROs are completed/invoiced/paid, not internal/deleted. Unknown query parameters fail422. The single joined snapshot is bounded at1000; oversized or ambiguous current rows fail409, never partial success.

Envelope exact fields: `version` (`db094-repair-financial-v1`), `shop_id`, `customer_id`, `complete:true`, `count`, `snapshot_id`, `items`.

Row exact fields: `repair_order_id`, `order_number`, `vehicle_id`, `vin`, `unit_number`, `description`, `work_completed_at` (UTC or null), `service_date` (UTC completion date only or null), `authorization`, `invoice`, `revision`.

The unique noncancelled invoice is current, including a draft. Draft yields `not_finalized`; absent/internal/deleted/voided current invoice yields `unavailable`. Do not choose an older visible invoice or cancelled predecessor. Missing immutable bill-to or owner-reviewed historical grant yields `attribution_required`. These blocked rows have `invoice:null`: no financial invoice ID, number, date, amount, line or document metadata is disclosed.

An `authorized` row uses the same invoice/PDF bill-to rule: immutable billed_customer_id matches, or it is null and a same-tenant existing historical mapping matches the target customer. No new grant or ETS exception is implemented here.

Authorized invoice fields: `invoice_id`, `revision`, `invoice_number`, `status:'current_finalized'`, `invoice_date`, `invoice_date_basis`, `currency:'USD'`, `total_amount` decimal string, `line_items` retail labor/parts, `pdf_sha256` nullable. Native issuance uses invoice creation timestamp; an ETS import uses preserved ets_invoiced_at only, otherwise unknown/null. Import timestamps never fabricate an original ETS issue date. Completion date remains preferred by EDG. The manifest does not render PDFs or mutate snapshots. No preserved PDF binder currently exists, so pdf_sha256 is null. The existing scoped PDF route remains the document-access boundary.

Line projection excludes internal unit costs, mechanic/supplier IDs, notes, contact fields and arbitrary snapshot keys. Financial invoice revision hashes only canonical invoice fields, excluding itself. Source payment workflow status, paid_at and updated_at cannot change that financial revision or imply an EDG payment. Row revision excludes itself. Snapshot hash covers exactly version/shop_id/customer_id/items, including row revisions. All SHA256 use sorted compact ASCII-escaped JSON encoded UTF-8.

## Durable notification

Invoice manual/automatic finalization, patch, void, audited tax/charge changes, supported RO description/status changes and completion workflow enqueue `ProviderOutboxEvent` type `fleet.financial.wakeup.v1` in the same outer transaction. Existing provider_outbox table/string event type requires no migration. Capture requires an explicit exact shop/customer destination and an active scoped customer key. Attribution-required invoices do not enqueue. Outbox idempotency includes invoice, customer, kind and source revision; one customer cannot reuse another customer's event identity.

Body exact fields: `{version:'db094-financial-wakeup-v1',event_id,shop_id,customer_id,repair_order_id,kind,occurred_at}`. Kind is invoice_finalized/invoice_changed/invoice_cancelled. No invoice amount, invoice ID, payment status, contact, description or credential is sent. It only wakes EDG to refetch the complete authorized manifest.

Server-managed `DIESELBRIDGE_FLEET_WEBHOOKS` is a JSON array of exact `{shop_id,customer_id,url,secret_env}`. URL must be HTTPS with no credentials/query/fragment and exact receiver route `/api/v1/accounting/dieselbridge/webhooks/{slug}`. `secret_env` references a separately approved signing secret of at least32 characters, never the fleet read key. No configuration/secret has been generated or installed.

A dedicated `process_fleet_financial_wakeups` Celery task runs every10seconds, separately from email delivery, and is a no-op unless `DIESELBRIDGE_FLEET_WEBHOOK_DELIVERY_ENABLED=true`. It processes at most one delivery per task (25second network budget within45second soft limit), leases/commits before I/O, verifies active source scope and configuration before sending, pins vetted public DNS addresses while retaining Host/TLS SNI, disables redirects/proxy environment, bounds time/body and checks lease tokens before completion. Signature headers: X-DBN-Event-Id equals bodyID; X-DBN-Timestamp Unix seconds; X-DBN-Signature `v1=` + HMAC-SHA256(secret, timestamp + '.' + rawbody). Canonical body remains byte-identical across retries; timestamps/signatures are fresh.

Missing configuration/secret/active scope pauses without spending attempts. Paused rows back off60seconds so they do not starve configured customers. Receiver503 is retained pending, also without spending attempts. Other retryable429/5xx/network failures use exponential retry up to12 attempts, then retain a dead event for operator review. Redirects and forbidden/private DNS fail closed. Worker crashes recover via60second lease; stale completions cannot acknowledge a newer lease. No network request or invoice mutation occurs on manifest reads.

## Verification

TDD observed404 RED before source manifest implementation; real invoice-patch outbox count0 RED before capture; existing provider worker succeeded0 RED before signed delivery; cross-tenant mapping and cross-customer idempotency regressions separately RED then GREEN. Focused tests cover15RO/7authorized/8blocked, draft/hidden current nofallback, hashes/privacy/paid-status neutrality, missing dates, revocation, atomic capture/rollback, finalization/void, charge changes, signatures, public DNS pinning/private DNS denial, redirects,503pause, retries, disabled config, lease races and scoped idempotency. Independent gates and any production rollout remain outstanding.

RO correction identity includes completion date/description/status and invoice financial facts, not only invoice.updated_at, so RO-only or same-clock-tick charge changes produce a new wakeup. The existing RepairOrderUpdate API does not expose a work_completed_at edit field; no new date-edit API was added. Completion workflow changes and supported RO edits notify transactionally. Direct administrative database date correction outside these application paths requires a manual complete-manifest sync; consumer must compare rowrevision as well as invoice revision and preserve accepted cost/date for review.
