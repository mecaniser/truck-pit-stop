# Invoice Access Phase 2 Contracts

Phase 1 implemented scope and hardening notes are documented in `docs/INVOICE_ACCESS_IMPLEMENTATION.md`.

This document defines the deferred phase 2 work after core invoice deep-link enrollment.

## Scope
- Pay-at-shop intent capture for public invoice links.
- Tenant toggle for guest Zelle visibility.
- Staff notifications for pay-at-shop intents.

## Data Model Additions
- `invoices.pay_at_shop_requested_at TIMESTAMPTZ NULL`
- `invoices.pay_at_shop_note TEXT NULL`
- `invoices.pay_at_shop_requested_channel VARCHAR(32) NULL` (enum-like values: `email_link`, `sms_link`, `portal`, `phone_call`)
- `tenants.guest_zelle_enabled BOOLEAN NOT NULL DEFAULT FALSE`

## API Contracts

### `POST /api/v1/invoice-access/pay-at-shop`
Request:
```json
{
  "token": "string",
  "note": "optional string"
}
```

Response:
```json
{
  "status": "success",
  "message": "The shop has been notified. Please pay in person.",
  "invoice_id": "uuid"
}
```

Behavior:
- Validates invoice link token.
- Stores pay-at-shop intent fields on invoice.
- Keeps invoice status unchanged (`sent`/`overdue`).
- Triggers staff notification (email).

### Existing endpoint interaction
- `POST /api/v1/payments/record-manual` remains the only path that marks cash/check/Zelle/ACH as paid.
- Guest-facing phase 2 endpoints must never auto-set invoice status to `paid`.

## Guest Zelle Rules
- Show guest Zelle instructions only when `tenants.guest_zelle_enabled = true`.
- Display read-only tenant Zelle details/QR in invoice access UI.
- Optional "I sent Zelle" action should create pay-at-shop intent; no payment finalization.

## Staff Notification Contract
- Notify active users in roles:
  - `garage_owner`
  - `garage_admin`
  - `receptionist`
- Include invoice number, customer name, amount, and submitted note.
- Apply idempotency/cooldown to avoid repeated notifications for repeated clicks.

## Validation Scenarios To Keep
- Token for paid invoice resolves to a receipt-style view and must not expose payment form.
- Consumed token returns `410` and must show "already used" messaging.
- Expired/invalid token returns safe error prompting customer to request resend.

## Non-Goals
- No automated Zelle reconciliation.
- No automatic invoice status transition based on guest self-reporting.
