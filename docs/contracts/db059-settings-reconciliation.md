# DB-059 settings reconciliation

Owner: Frontend & UX. Backend owns the bounded card-provider step-up adapter.
User authorizes reconciliation, ship and signed-in verification; no provider,
payment, accounting data or rollout flag mutation during acceptance.

## Contract

- Preserve current main payment routing/credits; combine the prior fee-settings
  presentation and local per-action verification changes without overwriting
  unrelated Fleet/UI work or original source worktrees.
- Taxes & Fees belongs inside Payments & Accounting. Existing fees navigation,
  role permissions and unsaved fee drafts remain functional.
- Remove global password panel. Each source mutation requests its existing scoped
  grant, then retains destructive confirmation where relevant. Cancel, incorrect
  password, expiry and duplicate submit cannot execute a mutation.
- Existing PUT /payments/settings/card-provider is a payment-source mutation:
  require the existing X-Step-Up-Authorization header and MANAGE scope via the
  normal PaymentStepUpContext/authorize_step_up mechanism before configuration
  writes or replay. Preserve tenant/role, provider gate, expected_version and
  idempotency semantics; no new schema or scope. Missing/invalid grant uses
  existing step-up HTTP errors. Frontend provider Save requests the shared
  per-action manage modal and forwards its grant header alongside Idempotency-Key.
  Preserve all current configuration mappings, including gross fee item/tax-code.
- Readiness remains server-derived. Do not change enabled shops, provider
  connections or fee rates. Published QuickBooks reference rates remain concise
  and linked to their official page, not a guarantee of a merchant's actual fee.

## Acceptance

Focused UI navigation/permission/draft/grant/cancel/duplicate tests; backend
missing/expired/wrong-tenant/wrong-session/wrong-scope and authorized control for
provider update; independent Security/QA review. Protected CI and exact deployment
followed by signed-in NC desktop/compact verification: nested fees, no global
panel, QBP Ready selected, Stripe unavailable, per-action prompt cancels safely.
No actual connection/disconnection, source switch, payment or fee save in live UI.
