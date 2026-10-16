# DB133 / C1 customer pricing defaults

Accountable: Backend & Integrations. Status: **Accepted contract; implementation handoff**. Selected after completed P1 in the [parity tracker](../ETS_PARITY_TRACKER.md). Branch: `codex/customer-pricing-defaults`, from P1 release-record195c7f3a (application70530bda).

## Acceptance before implementation

- Owner/admin can set, clear and reload a customer agreed labor rate and parts pricing default within Business settings; blank inherits shop settings. Preserve the existing tax-exemption workflow and permissions.
- New external repair orders use the customer agreed labor rate, otherwise the shop billing rate, including external fleet/PM creation. This fallback was explicitly approved by the user. Internal work retains its existing internal cost rules.
- Pin terms and their source on new orders. Later customer/shop/matrix edits do not silently rewrite existing orders or saved lines. Preserve manual labor/parts overrides and P1 price review semantics across direct, service, recommendation and fleet writers.
- Customer configuration uses dedicated tenant-scoped owner/admin contracts, optimistic concurrency and audit; generic self-service customer updates cannot mutate pricing. Foreign or deleted resources, archived matrices, stale writes and restricted roles are covered by negative tests.
- Compact accessible settings and readable pricing origin preserve customer search, cancel/back navigation, desktop density, one mobile scroll area and complete Light/Night desktop/portrait/landscape journeys.
- Additive migration, focused automated checks, independent QA/Security, protected CI, merge/deploy and permitted production acceptance are required before Done. Production QA must not activate invented account agreements or reprice real work.

## Runtime alignment — 2026-10-15 local / 2026-10-16 UTC

Mandatory runtime skill reapplied on branch switch. Frontend5174 was already the owned checkout; only its verified PID52183 was gracefully stopped to refresh its branch stamp. New PID39898 serves this checkout/frontend with explicit API origin127.0.0.1:8001 and stamp `codex/customer-pricing-defaults@195c7f3`.

Backend container `dieselbridge_api_ets-workflow-parity` remains9d8774b7, imagebde2e27b, bound to this checkout/backend on8001; it was not restarted. Database remains `postgres/truckpitstop_ets_workflow_parity_20261012`, schema174. Direct and proxied readiness pass. Actual signed-in Performance Owner customer/settings UI shows the new branch stamp. http://127.0.0.1:5174 is aligned and browser-verified for the existing baseline. No C1 functionality exists yet; no database, flags, provider configuration or production values changed.

## Handoff

Architecture owns the contract before parallel frontend/backend work. [Readiness notes](DB133_CUSTOMER_PRICING_READINESS.md) preserve the inspected writer inventory and approved fallback. Root owns this receipt, board and release coordination. Independent QA/Security remains separate from implementation.

Before any C1 migration: preserved local schema174 custom-format backup at `/Users/sergio_m1_promax/Documents/Codex/ets-priority-preparation-20261015/db133-local-schema174-before-c1-20261016T0241.dump`, mode0600,4012909bytes; pg_restore lists1755 archive entries. This is a local backup only and is not committed/uploaded. No migration has been applied; disposable upgrade/downgrade and legacy preservation proof must precede any preview upgrade.


## Accepted contract and ownership handoff

Product accepted [Architecture contract](../contracts/db133-customer-pricing-defaults.md) after narrowing it to account defaults, frozen new-order terms, existing manual-rate controls and current P1 counter behavior. No compulsory labor-edit reason or new labor CAS protocol; no payment/import/financial-merge rewrite. The conservative C1 merge guard requires retaining identities with C1 pricing history/references, rather than deleting their provenance. The pre-existing generic financial-merge concern remains separately recorded in readiness notes and is not claimed fixed.

Backend owns all backend models/migration/services/endpoints/serializers/tests as one contract integration; Frontend owns customer settings/types/hooks and narrow order/fleet/counter/source adapters/tests. They must not edit each other's files, reset unrelated changes, commit/push or migrate the preserved preview without coordination. Independent QA/Security begins after the integrated source and focused evidence are ready; root owns browser QA and release.
