# Paid repair-order conversion export

DieselBridge provides a supported, tenant-isolated path for sending verified
paid repair revenue to CallRail or another attribution service. Google Ads
credentials and offline-import logic remain outside DieselBridge.

## Attribution capture

Repair-order create/update APIs and the normal repair-order UI support optional
`lead_source_channel`, `external_lead_id`, `callrail_call_id`,
`google_click_id`, `gbraid`, `wbraid`, `landing_page_url`, and all five UTM
fields. They do not modify the legacy `source`, customer notes, or internal
notes. Attribution is locked when an order becomes invoiced or paid.

## Webhook configuration

Owners/admins configure the HTTPS destination using
`PUT /api/v1/admin/integrations/paid-invoice-webhook`. The `signing_secret` is
write-only and encrypted using `PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY`.

Paid invoices over $0 produce `repair_order.paid`. Deleted, unpaid, draft,
completed-only, and $0 orders do not. Correction event types are
`repair_order.payment_refunded`, `repair_order.payment_voided`, and
`repair_order.payment_adjusted`.

Every delivery includes:

- `Idempotency-Key`, stable per financial transition
- `X-DieselBridge-Event`
- `X-DieselBridge-Signature: sha256=<HMAC-SHA256(raw body)>`

Delivery is at-least-once with exponential retry. Consumers must deduplicate on
`event_id` or `Idempotency-Key`. After the configured maximum failures, the
webhook is disabled and the shop email receives a notification.

Admins inspect and replay deliveries through:

- `GET /api/v1/conversion-exports/deliveries`
- `POST /api/v1/conversion-exports/deliveries/{event_id}/replay`
- `POST /api/v1/conversion-exports/invoices/{invoice_id}/corrections`

Correction requests require an `Idempotency-Key` header; retries with the same
key return the original correction event instead of creating another reversal.

Delivery history records status, creation/completion/last-attempt timestamps,
HTTP response code, retry count, and a bounded non-PII error message.

## Export API and API keys

Owners/admins create, list, and revoke per-shop keys at
`/api/v1/conversion-exports/api-keys`. The raw key is returned only once; only
its SHA-256 hash is stored. Send it as `X-API-Key`.

`GET /api/v1/conversion-exports/paid-repair-orders` requires `paid_from` and
`paid_to` ISO-8601 values and supports `payment_status=paid`, `skip`, `limit`,
and `format=json|csv`. The key fixes the tenant scope; callers cannot request a
different shop. The response includes repair/invoice IDs, paid time, amount,
USD currency, immutable invoice service lines, customer contact when stored,
and all attribution fields.

## Privacy and consent

Customer phone and email are personal data. A shop must configure a destination
it is authorized to use, disclose marketing/measurement processing in its
privacy notice, honor opt-out/deletion obligations applicable to it, restrict
destination access, and set an appropriate retention period. DieselBridge logs
delivery metadata and bounded errors—not webhook bodies or customer contact.
