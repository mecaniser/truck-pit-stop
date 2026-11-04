# DB-156: Processor-aware saved cards

Accountable owner: Backend & Integrations. Payment/high-risk lane.

## Acceptance contract

The customer sees Add Card, masked saved cards, Set default, and Remove. The tenant's active payment-provider configuration determines the vault. No customer processor selector or Stripe fallback. Stripe Connect and QuickBooks Payments are the implemented adapters; Square is not integrated.

- Resolve the authenticated customer, tenant, selected provider, merchant account and environment on every request. Bind mutations and list reads to an opaque context version; reject stale contexts before provider writes.
- PAN/CVC travel directly from browser to the selected processor. DieselBridge receives only the opaque token and stores provider references plus masked metadata, never raw card details. Invalid request bodies must not be reflected in validation responses.
- QuickBooks vault customer references are separate from accounting customers. Saving a card must not create a QBO customer, invoice, charge or payment.
- Persist a stable wallet identity and operation receipt before creating a provider card. An uncertain outcome blocks further saves pending reconciliation; an empty list cannot clear that hold.
- List failures are errors, not an empty wallet. Unavailable shops get one neutral message, never a Stripe onboarding instruction for a QuickBooks shop.
- Existing provider-specific wallets remain isolated when provider/account/environment changes. Default/removal requires ownership in the selected wallet.

## API

`GET /payments/cards/config`: internal provider, opaque context_key, available, save_pending, neutral message and either Stripe account or an allowlisted Intuit token URL.

`GET /payments/cards?expected_context=...`: masked card array. `POST /payments/cards/prepare`: Stripe setup only, expected_context and stable idempotency_key. `POST /payments/cards/save`: QuickBooks token, expected_context and stable idempotency_key. `POST /payments/cards/{id}/default` and `DELETE /payments/cards/{id}` require expected_context.

## Evidence (2026-11-04)

- Read-only live shop settings: Truck Pit Stop selects QuickBooks, active for card payments, production connected; Stripe not set up. Read-only backend checks confirm active selection, matching merchant snapshots, payment scope and valid tokens. No production/provider mutations performed during investigation.
- Route contract tests:29 passed, including rejected sensitive input returning only a generic validation message.
- Full application and actual Intuit sandbox acceptance are separate required evidence. Neither is implied by mocked unit tests.
- Local5173 serves another worktree;8000 serves the existing db761 sandbox. Both preserved. Isolated DB156 runtime planned on5216/8216 using synthetic fixtures.

## Release gates

Pending: integrated backend/frontend checks, database migration validation, signed-in desktop/mobile acceptance, actual Intuit sandbox lifecycle, independent Security/QA, PR exact-head CI, merge, successful deployment and affected-tenant acceptance.

Rollback triggers: incorrect merchant routing, unauthorized wallet access, unexpected provider mutation or inability to load saved cards. Roll back application release; preserve additive vault tables and operation receipts for reconciliation. Do not delete vault data or retry uncertain saves automatically.
