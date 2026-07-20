# QuickBooks Online integration

DieselBridge owns the Intuit developer application and secure deployment
configuration. TruckPitStop remains each garage's system of record for
appointments, repair orders, and customer-facing booking. QuickBooks Online
(QBO) is connected independently by each garage for financial records and, in
a later rollout, payment processing.

## Integration boundaries

| Capability | System of record | Planned interaction |
| --- | --- | --- |
| Booking, dispatch, repair order lifecycle | TruckPitStop | Never created from QBO data |
| Customer accounting identity | Both | Upsert TruckPitStop customers into QBO `Customer` records |
| Invoices and balances | TruckPitStop first | Sync finalized invoices to QBO, retaining both IDs |
| Card / ACH collection | QuickBooks Payments | Browser tokenization and provider-hosted collection only; no PAN or CVV enters TruckPitStop |
| Accounting settlement | QBO | Link a QBO `Payment` to its QBO `Invoice`, then reconcile through webhooks and daily CDC |

QuickBooks Accounting and QuickBooks Payments are separate APIs. A shop that
will collect payments through Intuit must grant both scopes to the same QBO
company (`realmId`):

```text
com.intuit.quickbooks.accounting
com.intuit.quickbooks.payment
```

Do not route a payment through one QBO company and account for it in another.

## Implemented foundation

This release adds a secure, tenant-scoped OAuth connection at
`/api/v1/quickbooks`:

- Shop owners and admins with the existing `payments` permission can start,
  inspect, and disconnect a QBO connection.
- OAuth state is random, stored only as a SHA-256 digest, expires after ten
  minutes by default, and is consumed before the authorization-code exchange.
- Access and refresh tokens are encrypted with a dedicated Fernet key; plaintext
  tokens are not returned by the API or logged.
- A QBO company can be connected to only one TruckPitStop tenant at a time.
- DieselBridge super admins see platform readiness in the platform control
  panel. Garage owners/admins only see their own `Connect My QuickBooks` flow:
  sign into Intuit, choose their company, approve consent, and return.
- `Connected` means that garage's consent succeeded; it does **not** yet mean
  invoices or payments are being synced or charged.

## Deployment configuration

Register the following callback URL in the Intuit Developer Portal exactly as
deployed, then configure these backend environment variables:

```dotenv
QUICKBOOKS_CLIENT_ID=...
QUICKBOOKS_CLIENT_SECRET=...
QUICKBOOKS_REDIRECT_URI=https://api.example.com/api/v1/quickbooks/oauth/callback
QUICKBOOKS_TOKEN_ENCRYPTION_KEY=... # `Fernet.generate_key().decode()`
```

Keep the encryption key in a managed secret store. It is intentionally separate
from `SECRET_KEY`; losing it makes existing QuickBooks credentials unreadable,
which requires each shop to reconnect. Use separate Intuit apps and callback
URLs for sandbox and production.

## Required next milestones

1. In Intuit sandbox, implement idempotent customer and finalized-invoice sync.
2. Add a serialized token-refresh path before the one-hour access token expires;
   Intuit rotates refresh tokens, so concurrent refreshes must be prevented.
3. Validate a complete deposit and balance-due workflow: tokenization, payment
   approval/decline, QBO `Payment` linked to `Invoice`, refund/void, duplicate
   submission, and reconciliation.
4. Add signed QBO webhooks for `Customer`, `Invoice`, `Payment`, `SalesReceipt`,
   `Deposit`, and `RefundReceipt`; acknowledge quickly, deduplicate, and queue
   sync work. Run Change Data Capture daily and after any outage as a backfill.
5. Complete the Intuit production assessment and the applicable PCI/payment
   compliance work before enabling QuickBooks Payments for customers.

The authoritative QBO references are Intuit’s [OAuth 2.0 guide](https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/oauth-2.0), [Payments OAuth guide](https://developer.intuit.com/app/developer/qbpayments/docs/develop/authentication-and-authorization/oauth-2.0), [payment-processing workflow](https://developer.intuit.com/app/developer/qbpayments/docs/workflows/process-a-payment), and [webhook guidance](https://developer.intuit.com/app/developer/qbo/docs/develop/webhooks).
