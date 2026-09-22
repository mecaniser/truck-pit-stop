# DB-063 discount cost floors — release candidate

Owner: Backend & Integrations. Architecture contract approved; independent
QA/Security code review passed after corrections. Not merged or deployed.

## Current release evidence, 2026-09-22

Integrated application candidate:46df56a8628098e77c05e626db465183fb01bbd4,
including current main7934d96d without reverting its DB067 changes. Scoped
implementation commit8bc0cf19. Independent QA/Security re-review GO; independent
plan/coverage audit estimates90% requirement evidence (not measured line coverage),
with no remaining implementation blocker. Global pre-landing checklist used by
explicit user authorization. This repository does not use a VERSION/CHANGELOG
release scheme; retain its existing focused PR and merge-SHA deployment convention.

- User approved current shop costs at publication: quote recalculation/send and
  completion refresh cost settings and reject invalid discounts before writes.
- Explicit FOR UPDATE OF repair_orders excludes the tenant row. PostgreSQL
  tests prove lock independence and both discount-versus-stock execution orders.
- Integer-cent frontend comparisons accept187.50+11.39 and reject187.50+11.40.
- Backend focused SQLite20/20; PostgreSQL new/existing race suites14/14;
  frontend critical123/123 including37 panel tests; production build and source
  lint pass. New regression suites are included in protected critical CI.
- Broader PG test initially failed on a pre-existing history==0 assertion;
  reproduced unchanged on pristine83880452. Its successful setup intentionally
  writes history. Now assert the exact initial history ID set remains unchanged.
- Signed-in API8002/preview5181 verifies loaded caps, both modes, exact/over-cent,
  unchanged Apply and1280x720 popover. Drafts reset, original stock retained,
  no browser save or customer financial mutation. Viewport restored.
- Local migration147→148 (already on main/production) applied transparently;
  schema preflight and direct/proxied readiness pass. API backend mount remains
  compact-workspace, frontend PID89153 serves the integrated SHA; shared API8000
  process unchanged. Database identity remains the approved local development DB.
- Optional further hardening: explicit limits GET role matrix, discount-specific
  removal/recalculation cases, and mixed missing-cost part stock-switch fixtures.

Release target: Railway Diesel Bridge Network App / Diesel Bridge Network
Production / diesel-bridge-network, servingwww.dieselbridge.com and
api.dieselbridge.com with one backend Docker image bundling the frontend. Last
observed production deployment8f89afb2-e9d4-45a8-808c-26bd01b45df7 runs main7934d96d.
Rollback trigger: new pricing500s/deadlocks, publication below cost, or broken RO
surface. Rollback via a reviewed revert PR or redeploy the recorded prior image;
do not roll back unrelated upstream migration148 or mutate customer records.
PR, protected CI, merge and production acceptance remain pending.

## Historical investigation and runtime receipts

## Release recheck, 2026-09-22: NO-GO

- Global pre-landing checklist used with explicit user approval. Independent
  rereview found the joined Tenant eager load plus unqualified FOR UPDATE locks
  the tenant as well as the repair order, introducing tenant/inventory lock-order
  inversion with fleet staged creation. Source/compiled-SQL evidence; concurrent
  deadlock not yet reproduced. Restrict the intended lock and add PostgreSQL proof.
- Quote publication and repair completion call canonical totals without current
  discount-floor validation. A later internal rate increase can invalidate an
  existing draft discount. Confirm current-cost publication semantics versus
  grandfathering before altering these publication boundaries.
- Signed-in local browser now renders limits successfully from API8002. Labor
  187.51 is rejected against187.50. List mode with labor187.50 and order11.39
  incorrectly disables Apply while showing11.39 remaining: binary floating-point
  subtraction leaves a slightly smaller capacity. Add integer-cent validation
  and a non-whole-dollar exact-boundary regression.
- Restored both draft discounts to empty and mode to original stock, verified
  unchanged Apply disabled, dismissed without saving. No customer prices changed.
- Fresh origin/main is7934d96d, with upstream migration148/DB067 changes absent
  from candidate HEAD83880452. Fast-forward was safely refused because local edits
  overlap; no merge or stash occurred. Preserve upstream work during integration.
- Remaining test gaps: PostgreSQL serialization, fresh-session rollback after
  rejected work edits and atomic repricing, failed frontend save/draft retention,
  and permitted/denied limits-role cases. No release sign-off yet.

## Policy and API contract

- All ordinary labor uses tenant internal fleet labor rate × billed hours.
- Sublet labor protects vendor cost. Missing rate/hours/vendor basis blocks
  labor and order-level discounts; zero-price ordinary lines have zero floor.
- Parts protect recorded unit cost × quantity, falling back only to inventory
  cost from the same tenant. Unknown part costs block order discounts, not an
  independently valid labor-only discount. An explicit zero part cost is valid.
- Labor discount cannot exceed labor markup. Labor plus order discount cannot
  exceed combined markup. Exact cost boundary is allowed, below cost is not.
- Existing no-discount orders are not repriced by reading limits. Price/work
  changes with retained discounts must revalidate rather than silently clamp.

`GET /api/v1/repair-orders/{id}/discount-limits` uses the existing discount editor
roles and tenant/order access checks. It returns `current`, `stock`, `list`, each
with `labor_discount_max`, `combined_discount_max`,
`labor_discount_block_reason`, `order_discount_block_reason`. No raw internal
labor rates/cost fields are added to the mechanic-readable price summary.

`PATCH /api/v1/repair-orders/{id}/discounts` accepts the existing optional labor
and order amounts plus optional `parts_pricing_mode: stock|list`. All are saved
atomically under the order row lock; omitted amounts participate from current
state. Invalid precision/nonfinite/negative values return422. Cost violations
return400. Existing frozen/access/missing-order errors retain their semantics.
The existing pricing-mode POST remains supported and validates retained discounts.

Frontend uses prospective mode limits, subtracts the draft labor discount from
combined headroom, disables Apply for invalid/unavailable/unchanged drafts, and
uses the atomic PATCH. Failed saves retain the draft and refresh limits.

## Verification, 2026-09-22

- Backend15 tests pass: cost-floor, existing pricing/discount, and DB003
  foreign/missing/deleted tenant boundary suites. Run in transient Docker using
  current backend mount and isolated in-memory SQLite, not the live local DB.
- Frontend36 tests pass, including exact/over-limit combined drafts, stock
  repricing, unavailable limits, atomic payload, money formatting and unchanged
  Apply behavior. Changed lint and production build pass.
- Independent review caught and verified repairs for sub-cent rounding bypass,
  missing-order error mapping, and legacy null-list-price restoration.
- Remaining: signed-in aligned-backend browser acceptance and PostgreSQL
  concurrency verification. Existing order locking is preserved; SQLite tests
  are not concurrency proof. No customer price mutations performed.

## Runtime boundary

User approved separate API8002 on2026-09-22. Frontend5181 (PID45410) now proxies
to8002; both serve `truck-pit-stop-compact-workspace` on
`codex/repair-order-compact-workspace`, HEAD83880452 with uncommitted candidate
changes. Container `dieselbridge_api_compact_8002` publishes only127.0.0.1:8002
and mounts this worktree's backend at/app. Shared API8000 is untouched.

Runtime receipt2026-09-22: copied existing container environment directly into
the new runtime without writing secrets to the worktree. Effective auth/session/
database/Redis setting fingerprints match the shared development API. Local DB
is `postgres:5432/truckpitstop_db048_local_e2e_20260912`; Redis is `redis:6379/0`.
Alembic current reports147_credit_link_identity(head); no migration/reseed done.
Direct8002 and proxied5181 `/health/ready` pass DB/Redis checks. New limits route
through5181 returns401 without authentication (present and protected).

Status: aligned but signed-in browser acceptance blocked by expired browser
session. Login is displayed; user asked to sign in again. Do not claim rendered
cost-limit acceptance yet. No customer price mutations performed.
