# DB-156: Processor-aware saved cards

Accountable owner: Backend & Integrations. Payment/high-risk lane.

## Acceptance contract

The customer sees Add Card, masked saved cards, Set default, and Remove. The tenant's active payment-provider configuration determines the vault. No customer processor selector or Stripe fallback. Stripe Connect and QuickBooks Payments are the implemented adapters; Square is not integrated.

- Resolve the authenticated customer, tenant, selected provider, merchant account and environment on every request. Bind mutations and list reads to an opaque context version; reject stale contexts before provider writes.
- PAN/CVC travel directly from browser to the selected processor. DieselBridge receives only the opaque token and stores provider references plus masked metadata, never raw card details. Invalid request bodies must not be reflected in validation responses.
- QuickBooks vault customer references are separate from accounting customers. Saving a card must not create a QBO customer, invoice, charge or payment.
- For QuickBooks token saves, persist a stable wallet identity and operation receipt before creating a provider card. An uncertain QuickBooks save outcome blocks further saves pending reconciliation; an empty list cannot clear that hold. Stripe continues to use its existing SetupIntent confirmation with a stable request key per form; this change does not add durable cross-form Stripe uncertainty holds.
- List failures are errors, not an empty wallet. Unavailable shops get one neutral message, never a Stripe onboarding instruction for a QuickBooks shop.
- Existing provider-specific wallets remain isolated when provider/account/environment changes. Default/removal requires ownership in the selected wallet.

## API

`GET /payments/cards/config`: internal provider, opaque context_key, available, save_pending, neutral message and either Stripe account or an allowlisted Intuit token URL.

`GET /payments/cards?expected_context=...`: masked card array. `POST /payments/cards/prepare`: Stripe setup only, expected_context and stable idempotency_key. `POST /payments/cards/save`: QuickBooks token, expected_context and stable idempotency_key. `POST /payments/cards/{id}/default` and `DELETE /payments/cards/{id}` require expected_context.

## Evidence (2026-11-04)

- Read-only live shop settings: Truck Pit Stop selects QuickBooks, active for card payments, production connected; Stripe not set up. Read-only backend checks confirm active selection, matching merchant snapshots, payment scope and valid tokens. No production/provider mutations performed during investigation.
- Route contract tests:29 passed, including rejected sensitive input returning only a generic validation message.
- Genuine sandbox preparation: one normal OAuth refresh succeeded against the existing approved local sandbox connection; rotated credentials were durably preserved at their source. No production token or payment changes.
- Frontend exact-lock build/typecheck and25 focused tests pass. The earlier typecheck failure came from a stale shared dependency directory; isolated exact-lock dependencies resolved it without unrelated source changes.
- Full application and actual Intuit sandbox acceptance are separate required evidence. Neither is implied by mocked unit tests.
- Local5173 serves another worktree;8000 serves the existing db761 sandbox. Both preserved. Isolated DB156 runtime planned on5216/8216 using synthetic fixtures.

## Release gates

Completed locally:181 focused backend tests,27 frontend tests, exact-lock production build/typecheck, isolated PostgreSQL migration up/down/up and constraints, and independent Security GO. Signed-in simulated-provider desktop tests cover save/list/default/remove/read failure and durable unknown QuickBooks save hold. Independent QA reproduced181 backend,27 frontend and1 PostgreSQL check; its known-rejection same-form retry finding is corrected and independently verified with30 frontend tests.

Pending: PR exact-head CI, merge, successful deployment and affected-tenant acceptance.

Rollback triggers: incorrect merchant routing, unauthorized wallet access, unexpected provider mutation or inability to load saved cards. Roll back application release; preserve additive vault tables and operation receipts for reconciliation. Do not delete vault data or retry uncertain saves automatically.

## Genuine Intuit sandbox acceptance

On November4, source55e3d5e8 passed the real browser flow against actual `app.main:app`, authentication and PostgreSQL. The simulated adapter was removed and browser token interception cleared before testing. Browser card fields went to the official Intuit sandbox token endpoint; DieselBridge received only the token. Save returned success and the UI showed masked Visa4369 exp12/2026 with “Card saved”. Hard reload retained the card, Set default survived reload, and normal Remove confirmation returned an empty wallet.

Direct Intuit Cards list/get calls independently agreed with the saved masked card under the exact server-owned `dbv1_<profile UUID hex>` namespace. After removal, Intuit list returned an empty array. The local save receipt is confirmed; repair order, invoice and payment counts remained zero. No QBO accounting customer or charge was created. Exactly one normal sandbox OAuth refresh occurred before acceptance, with rotated credentials durably preserved in the original approved sandbox connection.

Runtime: frontend `http://127.0.0.1:5216`, PID73723, `/private/tmp/db156-provider-cards/frontend`; API `http://127.0.0.1:8216`, `db156-acceptance-api` mounted from this checkout/backend, actual app.main, disposable `db156_acceptance` PostgreSQL and private Redis. Canonical approved external configuration supplies sandbox credentials; none are copied into the worktree. Database/Redis readiness and frontend proxy verified. Existing5173/8000 runtimes preserved. Desktop and390px mobile rendering checked; mobile document width390 and Add Card target44px. This local runtime is aligned and browser-verified.

[Saved card, desktop](db156/genuine-card-saved.png) · [Saved card, mobile](db156/genuine-card-saved-mobile.png) · [After removal](db156/genuine-empty.png).

Full PostgreSQL evidence additionally passed migrations001 through200, then201 upgrade/downgrade/re-upgrade, preserving all prior table column definitions including booking applications. Four explicit PostgreSQL tests passed with zero skips. Independent Security and implementation/runtime QA GO at55e3d5e8. QA independently reran30 frontend tests, inspected real saved/default screenshots and executed the read-only Intuit verifier after removal, confirming an empty provider vault, confirmed receipt and zero financial rows. [PR776](https://github.com/mecaniser/truck-pit-stop/pull/776) remains draft until final gates finish.

## CI test compatibility correction

The first integrated critical CI run found one test-only failure on FastAPI0.162: an endpoint-registration assertion assumed the framework flattened its internal route list. The corrected test dispatches real HTTP requests through the full API router for config/save/delete.33 route tests pass on both the existing local framework and an isolated FastAPI0.162/Pydantic2.14 installation matching CI; independent QA accepts the correction. No application source changed, so genuine provider/runtime evidence remains applicable. A fresh exact-head CI run is required.
