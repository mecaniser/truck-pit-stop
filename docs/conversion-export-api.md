# Paid repair-order conversion export

DieselBridge provides a supported, tenant-isolated path for sending verified
paid repair revenue to CallRail or another attribution service. Google Ads
credentials and offline-import logic remain outside DieselBridge.

## Attribution capture

Repair-order create/update APIs and the normal repair-order UI support optional
`lead_source_channel`, `external_lead_id`, `callrail_call_id`,
`google_click_id`, `gbraid`, `wbraid`, `landing_page_url`, and all five UTM
fields. They do not modify the legacy `source`, customer notes, or internal
notes. `landing_page_url` is normalized and accepts only valid HTTP(S) URLs;
other schemes and control characters are rejected. Attribution is locked when
an order becomes invoiced or paid.

## Webhook configuration

Shop owners, and only admins explicitly granted the `conversion_exports`
permission, configure the HTTPS destination using
`PUT /api/v1/admin/integrations/paid-invoice-webhook`. The `signing_secret` is
write-only and encrypted using `PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY`.
Destinations must resolve only to public Internet addresses. Credentials,
localhost/private/link-local destinations, and redirects are rejected. The
destination is checked both when it is saved and immediately before delivery.
Delivery resolves once, rejects the full DNS answer if any address is
non-public, then connects only to a vetted literal address while retaining the
original TLS SNI/certificate hostname and HTTP `Host` authority. HTTPX/httpcore
are pinned because that transport contract is security-sensitive. Every DNS
answer is validated, after which at most four deterministically sorted public
addresses may be attempted. DNS has its own three-second deadline, and DNS plus
all address attempts share a 35-second wall-clock budget, below the worker's
45-second soft limit. Operators may lower these with
`PAID_INVOICE_WEBHOOK_DNS_TIMEOUT_SECONDS` and
`PAID_INVOICE_WEBHOOK_TOTAL_TIMEOUT_SECONDS`.

Paid invoices over $0 produce `repair_order.paid`. Deleted, unpaid, draft,
completed-only, and $0 orders do not. Correction event types are
`repair_order.payment_refunded`, `repair_order.payment_voided`, and
`repair_order.payment_adjusted`.

Every delivery includes:

- `Idempotency-Key`, stable per financial transition
- `X-DieselBridge-Event`
- `X-DieselBridge-Timestamp`, Unix seconds
- `X-DieselBridge-Signature: sha256=<HMAC-SHA256(timestamp + "." + raw body)>`

Receivers must reject timestamps more than five minutes from their trusted
clock, verify the signature before parsing the body, and deduplicate the event.
This timestamp window prevents a captured signed request from being replayed
indefinitely.

Delivery is at-least-once with exponential retry. Consumers must deduplicate on
`event_id` or `Idempotency-Key`. After the configured maximum failures, the
webhook is disabled and the shop email receives a notification.

Admins inspect and replay deliveries through:

- `GET /api/v1/conversion-exports/deliveries`
- `POST /api/v1/conversion-exports/deliveries/{event_id}/replay`
- `POST /api/v1/conversion-exports/invoices/{invoice_id}/corrections`

Correction requests require an `Idempotency-Key` header; retries with the same
key return the original correction event instead of creating another reversal.
The key is tenant-wide for corrections and cannot be reused with a different
invoice, event type, or amount. Refund and void amounts are negative; a void
must exclusively reverse the authoritative completed-payment amount. The
invoice and repair order must still be paid, cumulative refunds cannot exceed
completed positive payments, no correction may follow a void, and adjustments
must keep recognized payment between zero and the authoritative paid amount.
The invoice row is locked while all existing correction keys are evaluated, so
concurrent keys cannot independently exceed those bounds.

This release intentionally exposes webhook settings and conversion API-key
administration through the API only. A settings screen is outside DB-002 and
must be tracked as a separate product/UI outcome rather than implied here.

Webhook configuration, API-key creation/revocation, conversion exports,
delivery replay, and correction creation are recorded in the append-only
`conversion_export_audits` table. Audit metadata excludes customer contact,
webhook bodies, raw API keys, and signing secrets.

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
All outbox payloads are automatically reduced to non-contact event metadata at
the absolute `created_at + CONVERSION_OUTBOX_PII_RETENTION_DAYS` ceiling (30
days by default), regardless of whether they are pending, processing,
configuration-blocked, succeeded, or dead. Old nonterminal events atomically
become terminal `expired` records, have leases cleared, and cannot be delivered
or replayed. Claiming applies the full delivery-time budget as a safety margin,
so an event that could cross its retention deadline during an attempt is
redacted and expired instead of sent. Delivery preflight rejects already
redacted/expired rows, and completion is conditioned on the same processing
lease token so concurrent retention or erasure cannot be overwritten. The
customer-erasure service removes contact, attribution URLs, and free-form
service lines immediately for a tenant/customer privacy request; queued or
processing events for that customer become terminal `expired` records. Operators
dry-run `python -m app.commands.erase_conversion_event_pii --tenant-id ...
--customer-id ...` and repeat with `--apply` after verifying the exact scope.
Redacted dead-letter and expired events remain visible as delivery metadata but
cannot be replayed because their original signed payload no longer exists.

## Deployment gate

Before enabling the first shop webhook, store a JSON versioned Fernet keyring
as `PAID_INVOICE_WEBHOOK_ENCRYPTION_KEYS` and name the write key with
`PAID_INVOICE_WEBHOOK_ACTIVE_KEY_VERSION` on every backend/worker environment.
The single `PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY` remains a legacy bootstrap
fallback only. Losing an old key before re-encryption makes its stored signing
secrets unreadable.

Rotation order: deploy the old+new keyring everywhere, switch the active
version, dry-run `python -m app.commands.rotate_conversion_webhook_secrets`,
then apply with `--apply`. Remove an old key only after the apply run and a
delivery canary succeed. Crypto/keyring failures leave events pending without
consuming receiver retries or disabling the shop. Confirm the Celery
worker registers `process_paid_invoice_webhooks`, Celery beat schedules
`process-paid-invoice-webhooks` and daily `process_conversion_pii_retention`,
and a non-production signed delivery reaches a public test receiver.
Application validation and connection pinning block non-public destinations
and redirects; the production network must also deny backend egress to private,
link-local, and metadata address ranges as defense in depth.
