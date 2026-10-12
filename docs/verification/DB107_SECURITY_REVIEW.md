# DB107 independent Security & Identity review

**Gate: GO for the reviewed local implementation.** Reviewed commit
`9a633b5bb14acf8e3a82d60fb8cc23cb9b6934a4` on 2026-10-12.
Reviewer: independent `conversion_security` agent, with no implementation or
contract authorship. The reviewer changed only this report. This is not merge,
deployment, production migration, or browser acceptance evidence.

## Findings returned and independently rechecked

| Finding | Reproduction before correction | Verified correction |
| --- | --- | --- |
| Cross-order metadata in resolution errors | A mechanic assigned only to the source order PATCHed `is_resolved:true`. The409 response disclosed the target order ID, number, status and labor ID. | Converted resolution fields now require the three staff roles. The mechanic gets a safe403 with no conversion data; reactivation errors also gate projections by actor role. |
| Completed resolution link could be erased | After resolving against a completed target, PATCHing only `resolved_by_repair_order_id:null` returned200 while leaving `is_resolved:true`. | Inconsistent resolution updates return409. Explicit reopening clears the reference while preserving conversion history. |
| Stale start could revive superseded work | Pause override-start after its initial draft-order read; cancel the order; create replacement on another order; resume the stale start. Both work records became actionable. This was reproduced with isolated API fixtures and a deterministic suspended read. | Activation paths acquire the same transaction-scoped tenant financial lock before discovery. PostgreSQL tests show customer override and fleet start return `invoice_busy` during cancellation, then reject the committed cancelled state. Guarded restore/reactivation rejects superseded labor. |
| Shared history exposed the source order | A mechanic assigned only to the target fetched `/detail`; the conversion history text included the inaccessible source order number even though labor provenance was null. | Shared history records the newly added work without source identity. Staff-only provenance retains the source link. Actual API transport regressions cover mechanic, fleet-manager and customer roles. |

All four findings were reported to the implementing owner; fixes were made by
that owner and reviewed again by Security.

## Independent verification

- **55 passed:** `tests/test_db107_recommendation_conversion.py` and
  `tests/test_db099_recommended_work.py`, using the existing backend Python
  environment and isolated in-memory API fixtures. Includes role denial,
  minimized projections, replay/payload conflict, source preservation after
  rename, explicit resolution, removal/replacement, cancellation/deletion,
  superseded restoration, pricing/ETS restrictions and malformed inputs.
- **5 passed on PostgreSQL:**
  `backend/tests/test_db107_recommendation_conversion_postgres.py`, using the
  separately provisioned disposable DB107 database. Same request UUID,
  different UUIDs on one target, and competing targets each leave one conversion,
  labor row and history event. Customer/fleet activation tests exercise real
  PostgreSQL advisory-lock contention rather than SQLite locking assumptions.
- **6 additional independent API probes passed:** foreign recommendation,
  foreign source order, foreign source truck, foreign source payer, foreign
  target truck and foreign target payer. Each returned404 without foreign data;
  the isolated database retained zero labor/conversion rows after all probes.
- Fault-injected replacement totals failure returns503, leaves the original
  conversion current, and leaves no replacement labor/history residue. Retrying
  the exact request after restoring totals succeeds once.
- Reviewed strict request fields, server-generated provenance, tenant-scoped
  lookups and read projections, canonical pricing, one-commit write flow,
  session rollback on failure, partial unique current-conversion index, retained
  deleted-line UUIDs, source deletion protection, and staff-only UI controls.

Commands used `PYTHONDONTWRITEBYTECODE=1` and `pytest -p no:cacheprovider`.
Existing SQLAlchemy/Pydantic deprecation warnings were the only test warnings.
No production/customer data, preview database, browser session, server lifecycle
or migration was changed by this reviewer. PostgreSQL tests used uniquely named
synthetic tenants in the disposable test database.

## Remaining delivery boundaries

No unresolved security blocker remains in the reviewed change. QA owns actual
desktop/mobile rendering and workflow acceptance. Protected CI and parent
integration still apply. The additive166 migration and the preview-only merge
with165 must follow the recorded migration graph; production downgrade after
adoption would destroy provenance and remains outside this approval. Retain the
conversion table on application rollback. Any later change to role projections,
tenant joins, lifecycle locks or replay/replacement semantics requires recheck.
