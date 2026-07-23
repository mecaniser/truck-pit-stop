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
- `Connected` means that garage's consent succeeded. Finalized customer
  invoices are then queued for an idempotent QBO accounting mirror.

## Implemented accounting and payment lifecycle

- Finalized invoices enqueue a durable `quickbooks.invoice.sync.v1` outbox
  event. The worker upserts a tenant-scoped QBO `Customer`, creates the QBO
  `Invoice`, and retains both provider IDs. Existing finalized invoices are
  backfilled when a garage first connects.
- Customer card data is posted from the browser directly to Intuit's token
  endpoint. DieselBridge receives only the single-use opaque token and captures
  the exact outstanding invoice balance.
- A captured charge creates a local payment and an idempotent QBO `Payment`
  whose `Line.LinkedTxn` points at the synchronized QBO `Invoice`.
- Full and partial refunds use the Payments
  `/charges/{id}/refunds` operation, create a negative local ledger entry, reopen
  only the refunded invoice balance, and create a QBO `RefundReceipt`.
- Unpaid local invoice voids are mirrored with QBO's invoice void operation.
- Signed webhooks are deduplicated in `quickbooks_webhook_events`. A daily
  Change Data Capture sweep backfills missed `Invoice`, `Payment`,
  `RefundReceipt`, and `Deposit` changes. A separate daily Payments sweep
  retrieves charge state and retries missing accounting links.
- Garage managers can retry an invoice sync or payment reconciliation through
  tenant-scoped endpoints. QuickBooks payments can be refunded from the paid
  repair-order invoice panel.

## Deployment configuration

Register the following callback URL in the Intuit Developer Portal exactly as
deployed, then configure these backend environment variables:

```dotenv
QUICKBOOKS_CLIENT_ID=...
QUICKBOOKS_CLIENT_SECRET=...
QUICKBOOKS_REDIRECT_URI=https://api.example.com/api/v1/quickbooks/oauth/callback
QUICKBOOKS_TOKEN_ENCRYPTION_KEY=... # `Fernet.generate_key().decode()`
QUICKBOOKS_WEBHOOK_VERIFIER_TOKEN=...
QUICKBOOKS_ACCOUNTING_ENVIRONMENT=sandbox
QUICKBOOKS_PAYMENTS_ENVIRONMENT=sandbox
```

Keep the encryption key in a managed secret store. It is intentionally separate
from `SECRET_KEY`; losing it makes existing QuickBooks credentials unreadable,
which requires each shop to reconnect. Use separate Intuit apps and callback
URLs for sandbox and production.

## Sandbox acceptance and production gate

Keep both environments set to `sandbox` until all of the following pass against
a disposable US QBO sandbox:

1. Customer and finalized invoice appear once after worker retries.
2. Test-card success, decline, duplicate submission, and token expiry.
3. Partial refund, full refund/void, reopened balance, and repayment.
4. QBO Payment is linked to the correct QBO Invoice in the same `realmId`.
5. Webhook replay creates one audit row and CDC recovers a deliberately missed
   delivery.
6. Worker and beat are deployed from `railway.worker.json`.

Before either environment is changed to `production`, complete Intuit's
production assessment, merchant onboarding, fraud controls (including the
required CAPTCHA control), PCI review, and live low-value settlement/refund
reconciliation. Sandbox capture must never be treated as real money.

The authoritative QBO references are Intuit’s [OAuth 2.0 guide](https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/oauth-2.0), [Payments OAuth guide](https://developer.intuit.com/app/developer/qbpayments/docs/develop/authentication-and-authorization/oauth-2.0), [payment-processing workflow](https://developer.intuit.com/app/developer/qbpayments/docs/workflows/process-a-payment), and [webhook guidance](https://developer.intuit.com/app/developer/qbo/docs/develop/webhooks).
