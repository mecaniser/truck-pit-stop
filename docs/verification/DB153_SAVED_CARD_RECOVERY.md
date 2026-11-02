# DB-153 customer saved-card recovery

Owner: Backend & Integrations. Payment/high-risk lane. Prepared November 2, 2026.
Branch: `codex/customer-saved-card-recovery`, base `60b0be8d`.
The initial read-only investigation used DB-152, which current main already reserves for shared controls; this work is DB-153.

## Problem and contract

Stripe rejected the reported setup request with `resource_missing`, parameter `customer`. The portal trusted its stored Stripe customer reference and translated this into “Invalid payment request.” List failures also appeared as an empty wallet. The reason the prior Stripe customer disappeared is unverified.

- Authenticated saved-card routes resolve the principal's selected customer and tenant, exclude deleted customers/inactive shops, and require completed Stripe onboarding. No platform-account fallback.
- New `GET /api/v1/payments/methods/config` returns `{stripe_account_id}` without provider writes. Existing setup response adds `stripe_account_id`; browser refuses confirmation if it differs from its Elements account. Deploy frontend/backend together.
- Setup, list, default, delete and Elements use the selected connected account. Default/delete retain exact Stripe customer ownership checks.
- Explicit Add Card submission invokes the existing connected-customer recovery helper. All helper callers now lock/reload the active customer row before inspecting its reference, including invoice requests carrying stale ORM instances. Only `resource_missing` triggers replacement; other provider errors propagate. Existing valid references remain. The prior helper's commit behavior is retained; no migration or financial-record change.
- GET never creates/replaces a customer. Missing references return a safe409 with guidance; other retrieval failures remain errors, never successful empty lists. No reference returns a successful empty list for a ready shop.
- Payments and Contact Details share user/tenant/customer-scoped query keys. Contact Details distinguishes pending/error/empty. Payments offers list/form retries and displays mutation errors. Rejected/null Stripe loader promises are evicted for retry.
- This saves a card; it does not charge an invoice. Customers need no Stripe login. Raw card data stays in Stripe Elements; the application stores provider references.

## Verification

- **70 backend tests passed**, independently rerun by QA: saved-card endpoint cases, helper tests, real PostgreSQL concurrency cases and existing DB-048 adapter authorization regressions. Provider methods mocked. Includes staff/wrong customer/wrong tenant/deleted customer/inactive or unconfigured shop, valid/missing/null references, account scoping and card ownership.
- **15 frontend tests passed**, independently rerun: Payments error/retry/add lifecycle, setup/confirmation errors, account-change guard, shop/customer switch, readiness, mutation failures, Contact Details loading/error/empty and loader retry/cache scoping.
- Original endpoint mounted into the new focused regressions: **4 failures**. Original shared helper mounted into PostgreSQL concurrency regressions: **2 failures** (duplicate customer creation). Fixed code passes both groups.
- PostgreSQL18 used an isolated internal Docker network and disposable test database, no host port or production data. Two sessions preload the same stale/null customer; parallel invoice/setup helper calls return one recovered reference and create exactly one mocked Stripe customer. Each test drops its isolated schema.
- Production frontend build/typecheck/shared-control guard pass. Direct lint is clean on the new component/tests/loader; ProfileSettingsPage has two pre-existing `no-explicit-any` diagnostics at unchanged lines110/290. Baseline-aware changed-source lint must show no introduced diagnostics.
- Independent Security re-review: **GO for PR preparation**, previous soft-delete/concurrency findings corrected; no new lock-order cycle found. Independent QA: **GO for PR readiness**, prior Contact Details gap corrected. These are PR gates, not production acceptance.

## Local runtime receipt and browser scope

Preflight: main checkout has unrelated edits, so implementation uses an isolated worktree. Existing frontend5173 serves another task; API8000 mounts another checkout. Controller dry-run refused this checkout because approved `backend/.env` is absent. Those servers/configuration/databases were preserved. No credentials copied, migrations applied, local live rails enabled or provider calls made.

Synthetic actual-component preview only: `http://127.0.0.1:5253/`, Vite PID45797, source `/private/tmp/db152-saved-cards/frontend`, base HEAD `60b0be8d`, uncommitted feature source verified through rendered error text. API/auth/Stripe modules mocked; no backend/database for this preview. Browser Playwright verified desktop1440x900 failed-list -> explicit Add -> synthetic success -> refreshed card, and mobile390x844 form-load failure -> retry -> enabled Add. Mobile document width390, viewport390; no overflow. Visual screenshots inspected locally under `output/playwright/db153/`; browser fresh-page console has zero errors. The initial harness CSS working-directory mismatch was corrected before final captures.

**Full-stack runtime status: blocked/unverified.** Synthetic component rendering is verified, but it is not authenticated full-stack or Stripe iframe acceptance. Before merge/release, complete signed-in test-mode end-to-end card confirmation against the configured sandbox, protected PR CI, and normal payment release gates. No real card/provider/customer writes, merge, deployment or production repair performed.
