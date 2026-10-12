# DB107 tracked recommendation conversion

Accountable owner: Backend & Integrations. Product & Delivery Lead coordinates;
Frontend owns the interaction. Local acceptance on 2026-10-12. This record is not
merge, deployment or production-migration evidence.

## Delivered behavior

Staff can add an open recommendation to an editable order for the same truck,
enter decimal hours or `hours:minutes`, review the rate and exact labor amount,
and open the resulting operation. The operation retains its original description
and source-order/recommendation link even after a staff member renames the work.
The source recommendation links back to the exact operation.

Conversion does not resolve the recommendation. Once the target work is complete,
staff explicitly resolve it on its original order; the source and target links
remain available. Removing an operation or deleting/cancelling its order permits
an explicit replacement, retaining the earlier conversion records. Restoring or
reactivating superseded work is rejected to avoid a second actionable operation.

A logical request retains its UUID and payload after an uncertain network result.
Both same-request and competing-request duplicates are prevented transactionally.
Known validation failures can be corrected; uncertain outcomes offer a safe retry.
Role, tenant, truck, source, target lifecycle, imported-work and canonical internal
pricing checks run on the server. Reduced-role history does not disclose source
order identity. See the [approved contract](../contracts/DB107_RECOMMENDATION_CONVERSION.md).

## Runtime receipt

- Source: `codex/recommendation-conversion`, based on PR505 commit `e22e9b0d`;
  final product-code commit `2075ccfc`. Documentation commits follow.
- Intentional combined runtime: `codex/ets-parity-preview`, product integration
  `ff7ee477`, test-only integration correction `b25bafc1`.
- Frontend: `http://127.0.0.1:5174`, Vite PID68993, cwd
  `/Users/sergio_m1_promax/.codex/worktrees/ets-parity-preview/truck-pit-stop/frontend`.
  Effective proxy is `http://127.0.0.1:8001`.
- API: container `dieselbridge_api_ets-workflow-parity`, preview/backend bind
  mounted at `/app`, loopback8001 mapped to8000; uvicorn reload enabled.
- Database: local PostgreSQL host `postgres`, database
  `truckpitstop_ets_workflow_parity_20261012`; local Redis DB9. Existing sandbox
  configuration retained; no provider flags or live rails changed.
- `/health/ready` through5174 returned ready with database and Redis healthy.
  Feature-specific UI, source mount and listener were corroborated. Vite's
  startup build badge still displays `07275e9`; that stale badge was not used as
  proof of served code. Rendered conversion controls and corrected320px form
  are current HMR source evidence.
- Root dirty checkout and the other5173 runtime were left untouched. User tabs
  were preserved; QA used a separate background IAB tab.

## Automated and independent evidence

- Frontend:126 focused tests passed:21 conversion actions,35 continuity/panel,
  five exact-row navigation/capability,65 pending-feedback tests. Includes unknown
  network retry payload identity, conflict refresh, manual time entry, half-even
  monetary preview and fresh completion confirmation when switching orders.
- Source production build passed after final changes. Combined production build
  and126 focused frontend tests passed after the integration correction.
- Changed product TypeScript lint: zero errors, two pre-existing hooks warnings
  in RepairOrdersPage. No warning suppression or dependency changes.
- Independent Security:55 API tests, five real PostgreSQL concurrency/lifecycle
  tests and six additional cross-tenant probes passed. Independent QA also ran
  the affected fleet/hold regression group (84 passed).
- Combined preview:82 conversion/checklist/notification tests passed after
  teaching an existing notification mock the checklist aggregate query. Both
  product completion guards remain in place. Correction is preview-only.
- [Independent Security review](DB107_SECURITY_REVIEW.md) and
  [independent QA review](DB107_QA_REVIEW.md) record findings, corrections and gates.
  The reviewer agents did not implement the feature.

Local logs: `/tmp/db107-final-frontend.log`, `/tmp/db107-final-lint.log`,
`/tmp/db107-source-final-build.log`, `/tmp/db107-preview-final-build.log`,
`/tmp/db107-preview-integration-fix.log`. DB107 API regressions are included in
the required Quality gates backend job.

## Actual signed-in browser journeys

Executed in the Codex in-app browser at1280×720,390×844 and320×740. These are
real browser interactions at mobile viewport sizes, not physical-phone or Safari
device certification. All mutations used newly created local `QA107-*` fixtures.

1. Desktop: add the steering recommendation with0.50h×145.01. Both preview and
   saved amount are72.50. One operation is created and focused. Rename the
   operation; original recommendation text/source remain. Follow the source
   link to the completed source order, then return to the exact operation.
   Reload confirms persistence and no second Add action.
2. Mobile390: manually enter1:30×145.00. Block only the conversion request through
   the documented browser network control. A readable error retains the values
   and offers Retry safely. Unblock and retry; the observed POSTs reuse the same
   UUID and exact payload. One217.50 operation results. Network block removed.
3. Mobile320: remove that operation, choose Add again, inspect the explicit
   replacement warning, and add its replacement. Two successive removal/recovery
   checks retain three historical conversions with one current operation. The
   corrected form displays both44px inputs and whole action buttons above the
   footer; document width equals scroll width320. Warning/error contrast checked
   from computed styles. Reload and both source/target navigation links pass.
4. Resolution: actual Mark Completed moved QA107-DESKTOP to pending_review.
   For the final Resolve check only, its exact synthetic order was prepared as
   completed in the local fixture script. This avoids the separate outbound
   Finalize & Send Invoice action. Totals, invoice, payment and provider-outbox
   fingerprints were unchanged. Resolve was then performed in the UI, persisted
   after reload, removed the item from open recommendations and retained its
   readable historical record and operation link.
5. Recovery: add the wheel-seal recommendation toQA107-RECOVERY; soft-delete that
   order through its UI confirmation. QA107-MOBILE shows Order deleted and Add
   again. Explicit replacement creates one36.25 operation there. Deleted filter
   → old order → Restore order is rejected with the reason that its recommended
   work moved to another operation. Old order remains deleted. Cancellation
   races/reactivation are additionally covered by API and PostgreSQL tests;
   this customer UI exposes recoverable Delete/Restore instead of Cancel.

Evidence under this worktree's `output/db107/` (local, not committed):

- `desktop-linked-operation-final.png`, `desktop-resolved-readable.png`
- `mobile-390-form.png`, `mobile-390-retry-fixed.png`
- `mobile-320-replacement-fixed.png`, `mobile-320-converted.png`
- `desktop-deleted-target-replacement.png`, `desktop-restore-blocked.png`
- `fixture-completion-receipt.json`, `final-database-receipt.json`

Earlier screenshots named `mobile-320-replacement.png` and `desktop-resolved.png`
document defects before correction; they are not acceptance evidence.

## Migration, rollback and release handoff

Source adds migration166 from164. Disposable PostgreSQL upgrade→downgrade→upgrade
passed. Combined preview already includes checklist165, so integration-only167
merges165/166 without schema operations. Its actual head is167. Before local
migration, a custom-format backup was saved at
`/tmp/db107-preview-before-migration.dump` (3.7MB). Populated volumes were retained.

On release, reconcile the final migration graph with the checklist branch and
run the one-head gate before applying schema changes. Application rollback must
retain the additive conversion table and history; do not downgrade a populated
database merely to revert the UI. Restore a backup only under a separate,
explicit recovery decision.

Release owner must confirm merged SHA/deployed assets, readiness, applied head,
signed-in conversion/retry/source-link smoke checks and tenant-safe denial. Watch
conversion5xx, unexpected409s, duplicate-current index conflicts and changed
order totals through the first operational usage period. Roll back application
code on duplicate actionable work, lost provenance, cross-tenant disclosure or
unexplained totals drift; preserve conversion records for reconciliation.

The feature stays in Review until PR/CI and required merge/deployment evidence
exist. No merge, production migration, invoice delivery or deployment was performed.

Independent QA recorded one nonblocking existing-shell issue: a deleted order
still requests the optional recommendations panel with a deleted context, so it
can display a refresh error and cached rows above its restoration controls.
Conversion remains disabled. Hiding that unavailable panel is a separate shell
cleanup; this does not prevent or weaken the verified restoration guard.

Draft [PR506](https://github.com/mecaniser/truck-pit-stop/pull/506) is stacked on PR505. Final-head Quality gates are dispatched explicitly because the workflow automatic PR filter targets main.

## CI pricing correction

Initial run38321070670 oncc8ab0f0 passed the migration graph, both frontend jobs
and Playwright smoke, but the required backend job caught an added pricing
projection query (7, existing budget6). Source2bfcabb5 corrects response graph
loading rather than relaxing the budget: inventory is joined within the existing
parts load, and reduced labor provenance is loaded by one tenant-scoped query.

Owner107 focused tests, independent QA98 focused tests and independent Security42
focused tests passed. New regressions cover ordinary and1/3-conversion query
budgets and10 projection lifecycle/tenant cases. PostgreSQL concurrency and
projection equivalence were independently rechecked. Combined preview6fbd1a64
includes this backend-only correction; readiness remains healthy. The earlier
actual UI acceptance remains valid evidence for unchanged interactions. A final
browser recheck encountered an expired login session; this is recorded separately
from the successful prior signed-in desktop/mobile workflows.

Final synthetic database receipt: six historical conversions, three current,
one per source recommendation. The steering recommendation explicitly resolves
against QA107-DESKTOP; the air-line and wheel-seal recommendations remain open.
QA107-MOBILE has two distinct current operations totaling253.75; DESKTOP72.50.
The superseded RECOVERY target remains deleted. Immutable source snapshots and
invoice/payment/provider fingerprints match the baseline.
