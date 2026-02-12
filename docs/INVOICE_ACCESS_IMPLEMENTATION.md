# Invoice Access Implementation

**Last Updated:** 2026-02-11  
**Status:** Implemented in current working tree (pre-merge)  
**Scope:** Phase 1 (core invoice deep-link enrollment + hardening fixes)

## Purpose
Track the exact implementation shipped for invoice deep-link enrollment, guest checkout, and portal bootstrap, including follow-up hardening fixes completed during review.

For deferred work, see `docs/INVOICE_ACCESS_PHASE2.md`.

## What Was Implemented

### 1. Public Invoice Access Flow (Backend)

Added new public endpoints under `/api/v1/invoice-access` in `backend/app/api/v1/endpoints/invoice_access.py`:

- `POST /resolve`
- `POST /create-payment-intent`
- `POST /confirm-payment`
- `POST /create-portal`

Router registration:

- `backend/app/api/v1/router.py` includes `invoice_access` router.

Behavior implemented:

- Token-based invoice resolve with safe error semantics (`400` invalid/expired, `410` consumed).
- Guest Stripe PaymentIntent creation.
- Guest payment confirmation with server-side PaymentIntent verification.
- Optional portal creation/login from invoice link.
- Existing user auto-login path for customer account linked to token.
- New user creation path with password requirement.

### 2. Token Service + Token Lifecycle

Invoice token helpers added in `backend/app/core/redis.py` and issuance helpers in `backend/app/services/invoice_access_service.py`.

Token TTLs:

- Invoice access token: 7 days.
- Portal enrollment token (issued after guest payment): 24 hours.

Token payload fields:

- `invoice_id`
- `repair_order_id`
- `customer_id`
- `tenant_id`
- `email`
- `issued_at`

Consumption model:

- Invoice access token is consumed after successful guest payment confirmation.
- After successful guest payment, backend attempts to issue a one-time portal enrollment token so portal creation can still happen after payment.
- Portal creation accepts either:
  - active invoice access token, or
  - portal enrollment token.
- Portal creation consumes whichever token type is used.

### 3. Email Deep Link Switch

Invoice CTA links were switched from generic portal links to tokenized invoice links in:

- `backend/app/api/v1/endpoints/invoices.py` (create + resend email flows)
- `backend/app/tasks/invoice_reminders.py` (reminder emails)

Link format:

- `${FRONTEND_URL}/invoice/{token}`

### 4. Frontend Public Entry + Portal Invoice View

New public route:

- `/invoice/:token` in `frontend/src/App.tsx`

New public page:

- `frontend/src/features/invoice-access/InvoiceAccessPage.tsx`

Implemented UI flow:

- Resolve token and render invoice summary + fee breakdown.
- Start guest checkout via Stripe `PaymentElement`.
- Confirm payment and show paid state.
- Offer optional portal open/create CTA.
- If payment consumed invoice token, use returned `portal_enrollment_token` for post-payment portal creation.

New portal route:

- `/portal/invoices/:invoiceId` in `frontend/src/features/customer-portal/CustomerPortalPage.tsx`

New page:

- `frontend/src/features/customer-portal/CustomerInvoicePage.tsx`

### 5. Stripe Frontend Hardening (Connect Account Context)

Centralized Stripe instance initialization/cache:

- `frontend/src/lib/stripe.ts` (`getStripeForAccount`)

Replaced duplicated local Stripe caches in:

- `frontend/src/features/invoice-access/InvoiceAccessPage.tsx`
- `frontend/src/features/customer-portal/CustomerInvoicePage.tsx`
- `frontend/src/features/customer-portal/CustomerPortalPage.tsx`
- `frontend/src/features/customer-portal/PaymentMethodsCard.tsx`

Cache key includes both publishable key and `stripe_account_id`, preventing account-context mixups in multi-tenant sessions.

### 6. Payment Number Concurrency Fix

Implemented tenant-scoped payment number allocation service:

- `backend/app/services/payment_number_service.py`
- `backend/app/db/models/payment_number_counter.py`
- `backend/alembic/versions/027_add_payment_number_counters.py`

Applied to payment record creation in:

- `backend/app/api/v1/endpoints/payments.py`
- `backend/app/api/v1/endpoints/invoice_access.py`

Concurrency design:

- `SELECT ... FOR UPDATE` row lock on tenant counter.
- Savepoint-protected first-write race handling.
- Counter increment and payment insert happen in same transaction.

Migration adds:

- `payment_number_counters` table.
- Index safety net for `payments.payment_number` unique index if missing.
- Composite index `payments(tenant_id, payment_number)` if missing.
- Backfill counter rows for all tenants (including zero-payment tenants with `last_number = 0`).

## Security + Reliability Hardening Implemented

### Token/subject validation

- `customer_id` match enforcement.
- `tenant_id` match enforcement.

### Atomic token consumption race fix

- Redis Lua script in `_consume_one_time_token` ensures atomic check+consume.
- Prevents concurrent double-consume on same token.

### Password validation guard

- `invoice_access` adds `_validate_new_password_or_400`.
- Unexpected validator exceptions are normalized to `400` instead of leaking `500`.

### Stripe Connect product decision

Intentionally **not** implementing connected-account customer cloning/mapping yet.

Current behavior:

- In connected-account mode, PaymentIntent uses `stripe_account` but omits `customer`.
- Customer/invoice context is carried in metadata (`customer_id`, `customer_name`, `customer_email`, `order_number`, invoice fields).

Tradeoff:

- Simpler one-time invoice checkout now.
- No connected-account customer object history/saved-card reuse yet.

## Frontend UX Hardening Implemented

### Password client-side validation

`InvoiceAccessPage` now validates password before submit with same policy as backend:

- min length 8
- uppercase
- lowercase
- digit
- special character
- reject common weak passwords

Behavior:

- Inline validation message.
- Submit button disabled when invalid.
- Additional submission guard prevents bad payload call.

### DRY cleanup

Duplicated portal CTA UI in `InvoiceAccessPage` extracted to shared `PortalEnrollmentSection`.

## Tests Added

- `backend/tests/test_invoice_access_portal_race.py`
  - concurrent portal token consume behavior (`200` + `410` split)
  - password validator wrapper behavior (HTTP passthrough + unexpected exception normalization)
- `backend/tests/test_payment_number_service.py`
  - rollback does not advance payment counter
  - monotonic increment behavior

## API / Route Inventory (Current)

### Backend endpoints

- `POST /api/v1/invoice-access/resolve`
- `POST /api/v1/invoice-access/create-payment-intent`
- `POST /api/v1/invoice-access/confirm-payment`
- `POST /api/v1/invoice-access/create-portal`

### Frontend routes

- `/invoice/:token`
- `/portal/invoices/:invoiceId`

## Deferred / Not Included in Phase 1

See `docs/INVOICE_ACCESS_PHASE2.md` for deferred contracts:

- pay-at-shop intent persistence and endpoint
- staff notification workflow + cooldown
- tenant toggle for guest Zelle exposure
- Zelle self-report intent path (without auto-marking paid)

## Known Follow-Ups

- Invoice resend currently issues a new access token; previous unexpired links are not explicitly invalidated.
- Full test execution depends on optional local deps (for example `stripe`, `slowapi`, `aiosqlite` in some suites).
