# DB132 backend implementation handoff

Date: 2026-10-15. Owner: Backend & Integrations (`r1_schedule_backend`).
Branch: `codex/ets-parts-pricing-matrix-implementation`.
Contract: `docs/contracts/db132-parts-pricing-matrix.md`.

The corrected implementation is undergoing independent final review and integration. This is not
QA/security approval, merge evidence, or production acceptance. The implementing
agent did not commit, push, deploy, change provider flags, restart servers, or
activate any preserved-preview/production pricing default.

## Delivered surface

- Additive migration174, versioned matrix revisions, default-generation CAS,
  inventory floor/minimum/fixed-price/version fields, immutable line origins,
  append-only audit, and composite tenant foreign keys. Historical PartsUsage
  audit identity deliberately has no live FK, preserving physical removal.
- Owner/admin matrix CRUD/archive/restore, draft sample/inventory evaluation,
  default selection, inventory pricing policy and bounded private history.
  Configuration uses durable idempotency and private/no-store responses.
- Canonical Decimal resolver and typed whole-work preview with separate pricing
  and stock-scope fingerprints; downward-only shop/fleet projection, private
  management details, and original cost/default/charge retention.
- Integrated catalog and true-new-SKU ad-hoc attachments; explicit saved price
  edits, quantity CAS and bulk presets; shop service reapply; deprecated fleet
  append, fleet staged creation, PM replacement/scheduled PM; counter drafts.
- Preserves retained component/counter-line identity, origin and actual stock
  reservation; blocks ambiguous identities and unknown legacy bundle stock
  changes. Receipt WAC changes increment pricing version without a tenant lock.
- Current authorization is applied before direct-part retries. Counter retries
  rederive current capabilities. GET price-build and detail support explicit
  `pricing_presentation=fleet`; fleet roles cannot upgrade their projection.
- Notes constant restored after a caught adjacent-definition regression; notes,
  operation notes, existing invoice/quote and pricing regressions pass.

## Automated evidence

Interpreter: `/tmp/db128-backend-venv/bin/python`.
All commands run from this implementation checkout, using isolated SQLite or the
explicit disposable local PostgreSQL database; no production tests mutated data.

| Check | Result | Evidence |
| --- | --- | --- |
| Combined writer, managed pricing, financial, invoice/quote, inventory, fleet, notes and operation-note suite | 264 passed, 39 existing warnings, 87.69s | `/tmp/db132-backend-evidence/combined-final.log` |
| Final Fleet detail projection, null unit fallback, counter ambiguity and bounded catalog delta | 27 passed, 39 warnings, 12.45s | `/tmp/db132-backend-evidence/final-delta.log` |
| Real PostgreSQL constraint/concurrency suite | 6 passed, 9 warnings, 2.58s | `/tmp/db132-backend-evidence/postgres-tests.log` |
| Dependency-free Python `symtable` undefined-global check, all31 changed/new Python files | 0 findings | command described below |
| `git diff --check` | pass | current checkout |

Combined command:

```sh
/tmp/db128-backend-venv/bin/python -m pytest \
 backend/tests/test_parts_pricing.py \
 backend/tests/test_price_build_service.py \
 backend/tests/test_repair_order_ad_hoc_parts.py \
 backend/tests/test_db045_inventory_lifecycle.py \
 backend/tests/test_fleet_workflows.py \
 backend/tests/test_ro_pricing_discounts.py \
 backend/tests/test_discount_cost_floor.py \
 backend/tests/test_price_locking_rules.py \
 backend/tests/test_fleet_manager_price_build_access.py \
 backend/tests/test_db003_price_mutation_tenant_boundary.py \
 backend/tests/test_inventory_catalog_activity.py \
 backend/tests/test_parts_operations.py \
 backend/tests/test_invoice_discount_create.py \
 backend/tests/test_invoice_snapshot_totals.py \
 backend/tests/test_invoice_line_snapshot.py \
 backend/tests/test_db003_quote_read_role_boundary.py \
 backend/tests/test_repair_order_notes.py \
 backend/tests/test_repair_order_shop_notes.py \
 backend/tests/test_operation_notes.py -q --disable-warnings
```

Final delta command:

```sh
/tmp/db128-backend-venv/bin/python -m pytest \
 backend/tests/test_parts_pricing.py \
 backend/tests/test_inventory_catalog_activity.py -q --disable-warnings
```

The undefined-name check recursively examines Python symbol tables, flags any
referenced global absent from module assignments/imports/namespaces and builtins,
and covers changed/untracked backend Python files. No pyflakes/ruff/pylint is
installed; no dependency was added. This catches the missing global names found
during development, but does not claim to replace every lint rule.

The three pricing performance fixtures retain bounded reads: the prior six-query
budget gains one batched overlay read and one immutable audit insert (maximum8),
not per-line policy lookups. Existing tests only gained explicit CAS/confirmation
when the approved contract requires it: generic catalog financial edits, bulk
presets, explicit counter overrides and disclosed partial bundles. Ordinary
unmanaged attachments remain direct.

## PostgreSQL and migration evidence

Isolated database: `localhost:5432/db132_test_pricing` only. Test file validates
that host/name before connecting; it never defaults to the application DB.
No credentials are printed or saved in the evidence receipt.

- `/tmp/db132-backend-evidence/upgrade.log`: fresh full migration chain to174.
- `/tmp/db132-backend-evidence/downgrade174-173.log` and
  `upgrade173-174.log`: empty additive rollback/reapply.
- Migration compatibility runner seeded a173 inventory row; cost12.34,
  sale24.68 and stock7 survived, new policy fields were unset and no default or
  matrix was created. Receipt files are in the same evidence directory.
- `backend/tests/test_parts_pricing_postgres.py` covers immutable revision,
  audit and origin guards; physical usage deletion preserving audit evidence;
  composite tenant FK rejection; one winning matrix CAS; receipt inventory lock
  versus stale attachment; concurrent idempotent attachment with one stock/audit
  effect; template change rejecting a stale service preview.
- Existing tenant NOWAIT serialization can give a busy409 to a simultaneous
  loser; the same stale matrix version is rejected after the winning commit.

Re-run using the established local-only runner:

```sh
/tmp/db128-backend-venv/bin/python /tmp/db132_pg_tests.py
```

That runner sets `DB132_POSTGRES_TEST_URL` in memory and invokes the isolated test
file; audit fixtures remain in the disposable DB because deleting append-only
rows would weaken the assertion. Never point this test at the preserved preview.

Root already backed up and upgraded the preserved preview173→174. Migration174
has remained unchanged since that coordinated application. No schema backfill or
policy activation is required. Downgrade intentionally refuses after immutable
revision/audit data exists; release rollback should prefer restoring the approved
backup or a forward fix, with root coordination.

## Remaining gates owned by other roles

Independent QA/security final delta review, Light/Night desktop/mobile browser
acceptance, exact-head CI, PR/merge, deployment and production verification remain
with Product & Delivery Lead and the designated independent reviewer. All newly reproduced backend findings below are corrected locally; final independent
verification and actual UI acceptance remain required.


## Independent boundary corrections (2026-10-15, later checkpoint)

The earlier frozen checkpoint was not release-ready. Independent and actual UI
review found four missing adapter/bundle cases plus a production-session mismatch:

- Service search `operation_id="service:<UUID>"` now delegates to the canonical
  flat-service transaction with optional `pricing_preview_fingerprint` and
  `pricing_presentation`. Both paths share the same normalized command receipt;
  retry reauthorizes current permissions and cannot attach twice. Ordinary labor
  operations also own a durable receipt after removing the Redis short circuit.
- New ad-hoc attachments accept the downward Fleet presentation and reapply it to
  first and retried responses; no safe-price/private-cost fields escape to Fleet.
- Canonical reapply retains a legacy bundle's recorded zero stock reservation,
  including when its quantity increases; it never silently converts the old route
  into a reserving attachment.
- Expected unrecovered core obligations follow changed quantity and increment
  version while retaining original core value. Recovered/settled or vendor-return
  linked core quantities require review before a bundle or direct part change.
- Production sessions use `autoflush=False`. Recalculation in an enclosing
  transaction now flushes computed totals before a `populate_existing` reread;
  previously that reread discarded the new total and caused a false409.

The P1 test module now overrides only its own direct/HTTP fixtures to match
production `autoflush=False`. The isolated PostgreSQL factory uses the same mode.
Unrelated shared fixtures and app/database configuration were not changed.

Additional evidence:

| Check | Result | Evidence |
| --- | --- | --- |
| P1 rules, configuration, direct/HTTP writers, alias/replay, retained stock/core with production session mode |31 passed,39 warnings,10.90s|`/tmp/db132-backend-evidence/production-session-delta.log`|
| Expanded actual PostgreSQL suite with production session mode |12 passed,9 warnings,4.36s|`/tmp/db132-backend-evidence/postgres-production-mode-run.log`|
| Undefined-global scan across31 changed/new Python files |0 findings|local symtable scan|
| Current backend manifest |`0579ed3005b5aaf3861d243151ee7003f77a10d2866ff784b777fdef8cac883a`|`/tmp/db132-backend-evidence/boundary-frozen-manifest.json`|

The expanded PostgreSQL cases add default switch/clear-and-archive versus
attachment, old read-only quote during a pending policy transaction, recreated
component retention, actual removal/re-add with a new origin, ambiguous legacy
mapping rejection, and an injected second-component failure proving rollback of
labor, parts, stock, audit and receipt. The same command retries successfully after
that rollback. A quarter-hour service plus existing standalone parts specifically
asserts the exact preview, response and persisted total under `autoflush=False`.
Migration174 remains unchanged. Full affected regression is being rerun on this
correction checkpoint; its final result is recorded below when complete.
