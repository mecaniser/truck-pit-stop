# DB-050 — Payment-source step-up authorization contract

Status: frozen for implementation on 2026-08-31
Accountable owner: Backend & Integrations
Architecture owner: Architecture & API Contracts

## Objective

Payment-source settings must not rely on a browser-only `isUnlocked` flag. Every
Stripe, QuickBooks, and Zelle configuration mutation is authorized again by the
server using the signed-in user's own current password and a short-lived,
server-stored grant. Step-up supplements existing roles and permissions; it
never replaces them.

## Grant interface

`POST /auth/step-up-grants`

Request:

```json
{
  "password": "current-user-password",
  "scope": "payment_sources.manage",
  "target_tenant_id": null
}
```

Response returns an opaque 256-bit token exactly once, its server-selected
scope, expiry, and whether it is one-time. The browser sends it only in
`X-Step-Up-Authorization`. The raw token stays in React memory and must never be
written to cookies, local storage, session storage, URLs, logs, or analytics.
Only a SHA-256 digest is persisted.

Each grant binds user, effective tenant, current access-token JTI, token
version, scope, expiry, and optional platform target tenant. A grant becomes
invalid on expiry, consumption, explicit revocation, password/token-version
change, session-JTI change, tenant switch, permission loss, user/tenant
deactivation, or scope/target mismatch.

## Scopes

- `payment_sources.manage`: reusable for ten minutes; non-empty Zelle contact
  updates, QR upload/replace, Stripe connect/onboard, and QuickBooks connect.
- `payment_sources.zelle.disable`: one-time for two minutes; clearing both
  Zelle contact fields.
- `payment_sources.zelle.qr.remove`: one-time for two minutes; setting the QR
  image to null.
- `payment_sources.stripe.disconnect`: one-time for two minutes.
- `payment_sources.quickbooks.disconnect`: one-time for two minutes.
- `platform.payment_sources.stripe.reset`: one-time for two minutes and bound
  to one target tenant.
- `platform.payment_sources.quickbooks.reset`: one-time for two minutes and
  bound to one target tenant.

## Protected mutations

| Mutation | Scope |
|---|---|
| `PUT /admin/zelle-settings` | manage, or Zelle disable when both contacts are empty |
| `PUT /admin/zelle-qr-image` | manage, or QR remove when the value is null |
| `POST /stripe/connect/connect` | manage |
| `POST /stripe/connect/onboard` | manage; deprecated alias cannot bypass |
| `POST /stripe/connect/disconnect` | Stripe disconnect |
| `POST /quickbooks/connect` | manage |
| `POST /quickbooks/disconnect` | QuickBooks disconnect |
| Platform tenant Stripe/QuickBooks reset endpoints | matching target-bound platform reset |

Stripe dashboard links, provider health/status, QuickBooks invoice sync,
charges, refunds, reconciliation, signed callbacks/webhooks, and workers are not
payment-source configuration mutations and retain their existing contracts.

QuickBooks connect stores the grant identity, initiating user, tenant, scope,
and verification time on the one-time OAuth state. The callback does not carry
the browser grant; it may persist authorization only from an unexpired,
unconsumed, tenant-bound OAuth state containing that attestation. Pre-deployment
OAuth states remain callback-compatible.

## Request and error rules

Cookie-authenticated issuance and mutations require an exact configured browser
Origin or Referer. Header-authenticated API clients remain supported. The step-up
header is added to the CORS allowlist and is attached only to the protected API
call.

- `401`: missing or invalid primary authentication.
- `403`: wrong password, role/permission denial, or scope mismatch.
- `409`: the signed-in identity has no local password; no shared/master-password
  fallback is permitted.
- `428`: missing, expired, consumed, revoked, foreign-session, or otherwise
  unusable grant; response identifies the required scope, not secret state.
- `429`: failed-verification throttling with `Retry-After`.

Failed verification is limited to five attempts per fifteen minutes by
user/IP and twenty attempts per hour by user. Passwords and raw grant material
are never logged.

## Audit and verification

Append-only audit events cover issued, denied, used, expired, and revoked grant
outcomes with tenant, user, target tenant, grant ID, scope, provider,
correlation ID, timestamp, and minimized metadata. Protected mutations record
redacted configuration results; QR contents, OAuth codes/tokens, provider
secrets, passwords, and raw grants are prohibited.

Focused evidence must cover role and tenant boundaries, SSO-only identities,
password success/failure and throttling, TTL/session/token-version invalidation,
scope mismatch, one-time replay and concurrency, Zelle body classification,
every provider mutation with zero side effects on missing/invalid grants,
QuickBooks state attestation, deprecated alias and platform reset coverage,
cookie-origin enforcement, in-memory frontend handling, and independent
Security and QA review on one exact candidate.
