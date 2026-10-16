# DB133 backend implementation handoff

Backend owner: `/root/r1_schedule_backend`. Contract: `docs/contracts/db133-customer-pricing-defaults.md`. Application source frozen on branch `codex/customer-pricing-defaults`, documentation HEAD `328363697f8a185c0f3b5a2ecf5903466a3bb333`; backend changes were uncommitted at handoff. Independent QA/Security, CI, browser acceptance and release remain separate root-owned gates.

## Implemented behavior

- Dedicated owner/admin customer pricing configuration, version CAS, idempotent saves, reason and append-only history. Generic customer writes cannot set pricing fields. Internal accounts are ineligible.
- All three order constructors capture immutable account/shop labor and exact matrix revision or catalog policy. Quick intake uses the actual matched account. New external Fleet work uses agreed labor, then shop billing; existing internal and legacy route defaults are preserved. Legal zero shop rates remain valid; agreed customer rates must be positive.
- Seven labor writers use the shared saved default. Saved rates and explicit manual overrides survive service/PM reapply and automatic hours recalculation. Ordinary authorized manual editing retains its existing rules without new mandatory reasons or pricing CAS; sublets retain their old behavior.
- New parts on captured orders use their pinned revision, including an archived revision; retained lines preserve money and P1 provenance. Counter buyer changes repin only future additions, including linked account to/from walk-in. Safe full-detail counter policy shows captured or legacy source without account identity, matrix details or labor.
- Config and intake retries reauthorize. Shop projections expose bounded provenance; requested Fleet and fleet-manager responses omit the new account/labor/parts source fields. Public, receipt, generic history and invoice serializers are unchanged.
- Narrow merge guard preserves a losing customer's C1 configuration/history and original snapshot references, including deleted work. Sorted customer locks coordinate policy, intake and counter capture. Existing financial merge logic was not rewritten.
- Signed originating-call intake keeps a validated, tenant/actor/customer/vehicle-bound reservation receipt before the final local work transaction. A known successful reservation survives a later pricing conflict and retries reuse its UUID. Provider failure before a durable receipt remains ambiguous; this is not an exactly-once provider protocol.

## Migration and preserved runtime

Additive migration `175`, after `174`; SHA256 `2dcf08c6b502917e303ac89f21d0e438338a5abef9c014dc4e962f0f302b5f66`. Adds nullable snapshots, customer config/version, tenant-qualified matrix/revision references and immutable audit/snapshot guards. No historical rate, total, price or snapshot backfill. Downgrade fails closed once C1 evidence exists.

Disposable local PostgreSQL proof completed `174→175→174→175`, preserving a seeded legacy rate110 and totals with NULL snapshots. Negative shape and finite-rate constraints passed. Independent schema review proved16 rolled-back cases including counter policy retention and draft-only buyer change. Root applied175 to the backed-up named preview and aligned its corrected counter trigger; backend owner made no preview/production database mutations. The corrected migration must be deployed unchanged, not replaced by a down/up cycle on a database containing C1 evidence.

## Automated evidence

- **335 passed**: customer pricing, price builder, P1 pricing, recommendation conversion, service checklist, fractional parts, Fleet access/workflows/board, customer endpoints, originating-call intake, attribution lock and counter lifecycle. Log: `/tmp/db133-backend-evidence/affected-regression-final.log`.
- **89 passed** on the final delta: complete C1 suite, P1 suite and originating-call suite, including final safe counter projection and all seven labor writer paths. Log: `/tmp/db133-backend-evidence/final-projection-delta.log`. These overlap the335 and are not additive totals.
- **11 passed** real PostgreSQL cases: concurrent config CAS, policy/shop/matrix versus intake, merge versus policy/order/counter capture, sorted lock order, manual rate versus reapply, immutable evidence, concurrent known-success call reservation. Owner log `/tmp/db133-backend-evidence/postgres-tests.log`; independent rerun `/tmp/db133-backend-evidence/independent-postgres-tests.log`.
- Compileall and `git diff --check` passed. Dependency-free global-name check passed30 files; it is not a complete Python linter.
- Prior failures were fixed rather than waived: strict malformed-policy409 handling, existing zero shop rate, counter trigger mutation holes, and stale unit mocks updated to the new transaction boundary. The legacy service normalization test now asserts saved149×2=298 instead of silently adopting current100, while retaining hours/type checks.

All new writer tests use production `autoflush=False`. Tests mock provider calls and use disposable databases; no provider sends, feature activation or real account agreements were used by the backend owner.

## Reproduction

Interpreter: `/tmp/db128-backend-venv/bin/python`.

```sh
/tmp/db128-backend-venv/bin/python -m pytest backend/tests/test_customer_pricing.py backend/tests/test_price_build_service.py backend/tests/test_parts_pricing.py backend/tests/test_db107_recommendation_conversion.py backend/tests/test_service_checklists.py backend/tests/test_fractional_part_quantity.py backend/tests/test_fleet_manager_price_build_access.py backend/tests/test_fleet_workflows.py backend/tests/test_fleet_board.py backend/tests/test_customers_endpoints.py backend/tests/test_repair_intake_reference.py backend/tests/test_conversion_attribution_lock.py backend/tests/test_db045_inventory_lifecycle.py -q --disable-warnings
/tmp/db128-backend-venv/bin/python -m pytest backend/tests/test_customer_pricing.py backend/tests/test_parts_pricing.py backend/tests/test_repair_intake_reference.py -q --disable-warnings
```

For the disposable PostgreSQL suite, set `DB133_POSTGRES_TEST_URL` privately to a local `db133_test*` database at175, then run `backend/tests/test_customer_pricing_postgres.py`. `/tmp/db133_pg_tests.py` is the existing local redacting runner. Coordinate its database slot; do not rerun the migration downgrade runner against a fixture database after pricing evidence has been created.

Additional migration evidence: `/tmp/db133-backend-evidence/migration-compatibility.json`, `schema-negatives.json`, `rate-constraint.json`. Private environment values and database credentials are not in this receipt.

## Source identity and remaining gates

Frozen30-file manifest: `/tmp/db133-backend-evidence/final-source-manifest.json`. Normalized aggregate SHA256: `cafa79e290dafe731b92da3b26c8c2b775be4f5df6ac99344c89015e84349a0e`.

No known incomplete backend writer at handoff. Required independent final gate, exact-head CI, Light/Night desktop/mobile workflows, merge/deploy and production verification are not claimed by this handoff. Counter UI remains subject to existing global/tenant flags and verified inventory backfill; do not enable those for acceptance. Root owns any synthetic local UI settings and teardown.

Changed backend files:

- `backend/alembic/versions/175_customer_pricing_defaults.py`
- `backend/app/api/v1/endpoints/customer_pricing.py`
- `backend/app/api/v1/endpoints/customers.py`
- `backend/app/api/v1/endpoints/fleet.py`
- `backend/app/api/v1/endpoints/repair_orders.py`
- `backend/app/api/v1/router.py`
- `backend/app/db/models/__init__.py`
- `backend/app/db/models/customer.py`
- `backend/app/db/models/customer_pricing.py`
- `backend/app/db/models/inventory_lifecycle.py`
- `backend/app/db/models/labor.py`
- `backend/app/db/models/repair_order.py`
- `backend/app/middleware/idempotency.py`
- `backend/app/schemas/customer_pricing.py`
- `backend/app/schemas/fleet.py`
- `backend/app/schemas/parts_pricing.py`
- `backend/app/schemas/recommendation_conversion.py`
- `backend/app/schemas/repair_order.py`
- `backend/app/services/counter_sale_service.py`
- `backend/app/services/customer_merge_guard.py`
- `backend/app/services/customer_pricing.py`
- `backend/app/services/parts_pricing.py`
- `backend/app/services/parts_pricing_planner.py`
- `backend/app/services/parts_pricing_rules.py`
- `backend/app/services/price_build_service.py`
- `backend/app/services/recommendation_conversion.py`
- `backend/tests/test_customer_pricing.py`
- `backend/tests/test_customer_pricing_postgres.py`
- `backend/tests/test_price_build_service.py`
- `backend/tests/test_repair_intake_reference.py`
