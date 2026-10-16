# DB132 / P1 independent QA and Security review

Reviewer: independent `r1_independent_gate`; no implementation or corrective test
edits, runtime changes, browser actions, deployment or production mutation.
Accountable implementation owner: Backend & Integrations. This reviewer owns only
this receipt. Delivery owner handles remediation and final gate assignment.

## Current gate: production QA GO / Security GO — P1 closure supported

Base PR542 and focused feedback correction PR544 passed protected CI and deployed.
The final signed-in Light/Night desktop/mobile acceptance is complete. Independent
review confirmed release identity, the supplied runtime evidence, inactive pricing
and preserved historical financial values. A later inventory fingerprint change
is attributable to the existing ETS import, with exact evidentiary limits recorded
below. No unresolved P1 release blocker remains; Product & Delivery may close the
tracker item after recording this receipt. No production pricing was activated.

Review baseline: branch `codex/ets-parts-pricing-matrix-implementation`, HEAD
`4d6d5b133116b9960675b211e03b91d31fe95dbf` plus the evolving owner diff. Read the
accepted `docs/contracts/db132-parts-pricing-matrix.md`, delivery constitution and
skill, local-runtime skill and the local alignment/migration receipt. This
read-only review does not require starting services. The focused tests use fresh
in-memory SQLite, not the preserved preview or production database.

## Findings returned to implementation

1. **Closed — fleet retry fails after a successful attachment.** Direct/ad-hoc attachment
   persists `response.model_dump(mode='json')` as its durable response. Fleet
   serialization omits required `unit_price` and `total_price`, then the replay
   path reconstructs `PartsUsageResponse` from that already projected body.
   `model_validate` raises `ValidationError` for those missing fields. Reproduce:
   serialize a valid PartsUsageResponse with `pricing_audience='fleet'`, then pass
   it through the same replay validation at
   `backend/app/api/v1/endpoints/repair_orders.py:4133` or `:4432`.
   Expected: identical authorized retry succeeds without another attachment or
   audit; actual: required-field validation fails. The schema-level reproduction
   was run independently; whole-route replay regression remains required.
2. **Closed — downward role replay retains prohibited line pricing.** The same replay path
   changes `pricing_audience` to fleet but keeps an earlier shop `pricing` object.
   `PartsUsageResponse.serialize_audience` removes top-level amounts, but does not
   remove nested SafePrice for fleet. Reproduce: an owner creates a priced line on
   an accessible fleet order, then the same user becomes fleet manager and retries
   the same body/key. The fingerprint still matches actor ID; current fleet scope
   authorizes the order. Schema-level replay independently retains
   `default_unit_price`, `charged_unit_price`, `line_total` and stale
   `can_override=true` inside `pricing`. Expected: current fleet projection has
   no line-price object or override affordance. Relevant serializer:
   `backend/app/schemas/repair_order.py:153–162`. Reauthorization is necessary but
   does not itself safely reproject a previously serialized response. Review the
   service/fleet/counter replay adapters for the same class of issue as they land.
3. **Closed — safe-price line amount differs from the canonical saved amount.**
   `backend/app/services/parts_pricing_rules.py:209` uses `cents(price * quantity)`,
   which rounds HALF_UP. Authoritative `line_total` at `:43–52` retains canonical
   existing line rounding. Independent reproduction: price `0.10`, quantity `0.25`
   produces persisted total `0.02` and SafePrice `line_total='0.03'`. Expected:
   preview/saved projection and writer total agree; matrix unit-price HALF_UP
   remains a separate rule. Add a fractional tie regression.
4. **Closed — matrix name bound differs from the approved contract.** Contract line161
   specifies a trimmed name of 1–100 characters, while MatrixCreate accepts120
   and database/model columns are120. Reconcile the accepted bound; this is a
   contract mismatch, not a demonstrated tenant/privacy exposure.

5. **Closed — counter replay retains stale override/actions after role reduction.**
   An owner creates a draft, becomes receptionist, and retries the same key/body.
   The original response retained `pricing.can_override=true` and `cancel`, while
   fresh GET returned false and omitted cancel. This was a stale capability
   affordance, not a newly demonstrated raw-cost disclosure. Both create/update
   replay now rederive current permissions through `_project_counter_replay`.
   Independent route reproduction returns the same actions and override flag as
   fresh GET after the role change.
6. **Closed — unknown-cost quantity edit fails in activity serialization.** The
   newly added regression for saved unknown cost and an unreserved legacy bundle
   failed because quantity update passed `str(None)` as its activity cost. The
   strict activity serializer raised `ValueError`. The owner added null guards to
   all four affected repair-order activity writes; the full focused suite then
   passed, including this case. The test also confirms catalog cost changes do not
   invent saved actual cost, and a formerly unreserved bundle does not consume
   stock during a quantity edit.

7. **Closed — ad-hoc owner-requested fleet projection is discarded.**
   `AdHocPartCreate` has no `pricing_presentation`, while the actual fleet hook
   sends that field. Parsing drops it, and the endpoint/replay builds its response
   without a requested audience. Independent disposable endpoint reproduction
   with an owner and `pricing_presentation=fleet` returns nested `pricing`,
   `unit_cost` and `unit_price`. Current role-based fleet masking works, but the
   approved explicit downward projection does not. Forward the accepted field
   through both first response and durable replay; add an owner-in-fleet test.
8. **Closed — retained zero-reservation bundle begins reserving stock on reapply.**
   `parts_pricing_planner.py` derives retained `p.reserves` from the new canonical
   adapter. Independent actual legacy fleet-service add followed by canonical
   quantity2 reapply preserves the usage ID but changes recorded reservation0→2
   and inventory50→48. Direct quantity editing correctly preserves this recorded
   zero. Contract requires retained actual reservation behavior, including a
   deliberate zero, rather than a stock-accounting rewrite on reapply.
9. **Closed — retained core quantity is stale after bundle quantity change.**
   A canonical service with core charge15 creates usage/reservation/core quantity1.
   Reapply at quantity2 changes reservation to2 but leaves
   `CoreObligation.quantity=1`. `apply_plan_parts` handles core insertion/removal
   but not retained changes. Reconcile safely or reject changes that cannot be
   reconciled once downstream core work exists; quantity/stock/core state must
   remain one atomic command.
10. **Closed — service-operation alias bypasses pricing confirmation plumbing.**
    Root's actual Operation search→Apply uses
    `/price-build/repair-ops/apply` and receives an unhandled409. Independent
    source review confirms `service:<UUID>` delegates to `add_flat_service_line`
    without fingerprint/presentation, with no domain receipt on this alias and
    generic Redis replay still enabled. Canonical frontend routing must be fixed,
    and the still-callable alias must either handle the complete confirmed command
    or reject it explicitly without mutation. Forwarding a token only in UI cannot
    make this backend schema accept it.

11. **Closed — receptionist cannot retain a saved counter override while editing quantity/buyer.**
    Source review at `CounterSalesWorkspace.tsx` shows initial `overridePrice` is
    populated for a saved manager override. `payloadLines` correctly treats its
    unchanged value as default intent, but `quoteReady` and `submit` reject every
    nonempty override for a receptionist. Reproduce with an owner-created manual
    price draft: sign in as receptionist, edit only quantity/buyer, then save. The
    UI refuses before any write. This is a source-derived reproduction; the
    owner-only retained test does not cover it. Returned to Frontend for a focused
    receptionist unchanged-price regression and intent-based validation.

12. **Closed — service totals reread discards pending values in production session mode.**
    Root's actual confirmed quarter-hour bundle returned409, despite the preview
    total being correct and the earlier tests passing. Application sessions use
    `autoflush=False`; earlier test factories used the default automatic flush.
    `PriceBuildService.recalculate_order(commit=False)` computed new totals then
    performed a `populate_existing` reread without flushing, restoring the old
    persisted totals. An independent fresh in-memory session with
    `autoflush=False` reproduced `pricing_preview_changed` / “Labor changed while
    applying this service.” Log `/tmp/db132-independent-no-autoflush.log`.
    The corrected enclosing-transaction branch explicitly flushes before reread.
    P1 direct/HTTP and actual PostgreSQL fixtures now use production session mode;
    independent PostgreSQL acceptance includes exact preview, response and
    persisted totals for a quarter-hour service plus existing standalone parts.

13. **Closed — new-order recovery banner pushes the phone workspace footer out of view.**
    Independent visual review of committed `db132/light-new-order-recovery-390.png`
    shows the recovery banner at0–123px, then the repair-order workspace extending
    below the844px viewport with no visible order-total/action footer. The ordinary
    `light-bundle-390.png` has its footer at788–844px. Source corroborates the
    geometry: `RepairOrdersPage.tsx:3209` inserts the banner as a direct sibling
    before the workspace; `index.css:4288` changes the parent to `display:block`
    on narrow screens while `:4292` and `:7024` keep the child at100% height.
    Desktop also auto-places the unassigned banner in the ledger/workspace grid.
    Returned to root for actual banner/panel/footer bounds at390 and desktop;
    keep footer reachable within one workspace and prevent extra page scroll.
    This finding is based on supplied rendered pixels plus source, not an
    independently driven browser session.

14. **Closed — part-add pre-replay authorization leaks a domain exception as500.**
    Full CI `test_db003_additive_tenant_boundary.py` reproduces a cross-tenant
    mechanic catalog attachment raising unhandled `PriceBuildNotFoundError`,
    rather than the established generic404. Independent source review also finds
    the same raw `price_build_service.load_order` pattern in ad-hoc attachment
    (`repair_orders.py:4156`), in addition to catalog attachment at:4459. The
    query remains tenant-scoped and no foreign order is returned, but an expected
    authorization/not-found response becomes an unhandled server failure.
    Missing and soft-deleted orders use the same failing read. Require consistent
    generic404 for both endpoints before any receipt/planning/stock mutation,
    retaining same-tenant assignment403. Source review confirms planner context
    already maps its own read and service/operation endpoints retain their error
    mapping. The existing HTTP additive fixture does not cover ad-hoc and must
    gain the analogous negative cases. CI log:
    `/tmp/db132-final-full-backend-ci.log`. Source at review start:
    `ad99dff0ed6f05c456a0ae60225d1e92eb80830b`.

15. **Closed — stock confirmation changes the legacy shortage contract.**
    With the corrected dependency arguments, the original fractional stock tests
    reproduce two real regressions: an unmanaged direct add without enough stock
    returns pricing409 before the established insufficient-stock400; an explicit
    `allow_stock_shortage=true` still demands an additional pricing token. The
    accepted contract preserves the existing stock guard and explicit override
    for unmanaged/default direct additions. This is an application defect exposed
    by restoring the tests, not a reason to weaken their stock assertions.
    The owner moved the existing stock guard before confirmation and introduced a
    narrow stock-only acknowledgment; new managed/manual prices and every supplied
    fingerprint still require their established validation. Initial owner failure
    log: `/tmp/db132-backend-evidence/ci-correction-initial.log`.

The descriptions above retain the initial failures for traceability. Closure is
based on the independent delta checks below, not an assumption that later owner
edits fixed them. Source is still changing; these closures do not approve all P1
writer integration or unrelated notes/financial behavior.

## Independent correction and integration delta

- Latest focused command, in backend: `/tmp/db128-backend-venv/bin/python -m pytest
  tests/test_parts_pricing.py -q --disable-warnings --maxfail=3`.
  **24 passed**, 39 warnings, 8.27 seconds. Log:
  `/tmp/db132-independent-foundation-delta-tests.log`. This includes actual HTTP
  direct-part fleet-first replay, owner-to-fleet replay, denied retry after fleet
  scope removal, owner-requested fleet GET projection, and counter role reduction.
  An immediately preceding run was **23 passed / 1 failed** on finding6; the
  successful rerun followed the null-cost correction.
- Canonical direct/ad-hoc receipts now retain audience-neutral private facts;
  replay reconstructs the response using current role, requested downward
  presentation and lifecycle. Independent actual endpoint probes confirmed
  fleet-first direct/ad-hoc retries succeed with the same identity, ad-hoc body is
  identical, and owner-to-fleet direct retry omits all line pricing and nested
  SafePrice. Two logical direct requests create exactly two usages. Logs:
  `/tmp/db132-independent-replay-delta.log` and
  `/tmp/db132-independent-counter-fixed.log`.
- Flat-service replay rebuilds the current authorized summary. Independent
  fleet-first and owner-to-fleet retries expose identity/quantity/version only,
  without nested pricing or part money; one usage and one labor row remain after
  reapply/replay. Log: `/tmp/db132-independent-service-replay.log`.
- A retained service component was created at actual cost10 and charged/list15,
  then the matrix and catalog were revised to materially different values. A
  quantity2 reapply preserved usage ID, original JSON snapshot, revision FK,
  cost10 and charged/list15; reservation became2. Contextual preview and saved
  order total both equaled230.00. Log:
  `/tmp/db132-independent-retained-service.log`.
- Counter buyer/quantity edits preserved original line ID, actual cost30 and
  charged/list50 after catalog cost/sale changed to80/100. Independent downward
  replay recheck returned `can_override=false` and actions `edit_draft,checkout`,
  matching fresh GET. Logs: `/tmp/db132-independent-counter-delta.log` and
  `/tmp/db132-independent-counter-fixed.log`.
- Fractional price0.10 × quantity0.25 now returns canonical and SafePrice total
  **0.02**. Name length101 is rejected. The unit-price matrix HALF_UP rule remains
  distinct from existing canonical line rounding.
- Owner explicitly requesting `pricing_presentation=fleet` on saved price-build
  GET receives no `parts_pricing_fingerprint`, no nested `pricing` and no
  `unit_cost`; saved `pricing_version` remains available for authorized CAS.
- All independent probes used disposable in-memory SQLite and synthetic fixtures.
  No preview or production data, feature flags, browser sessions, runtime services
  or application/test source were changed by this reviewer.

## Final-surface pass, before corrections7–10

- Independently ran the exact backend owner's combined19-file command recorded
  in `DB132_BACKEND_HANDOFF.md`: **264 passed**,39warnings,120.17seconds.
  Log `/tmp/db132-independent-final-combined.log`.
- Independently inspected and ran `/tmp/db132_pg_tests.py` only after the backend
  owner released its disposable database. The runner resolves credentials only
  in memory and fixes the target to `127.0.0.1/db132_test_pricing`; it does not
  upgrade or mutate the preserved preview. **6 passed**,9warnings,2.35seconds.
  Independent log `/tmp/db132-independent-postgres-tests.log`. Covers immutable
  evidence/origin, physical removal retaining audits, composite tenant FKs,
  simultaneous matrix CAS, receipt WAC lock versus stale attachment, attachment
  retry with one stock/audit effect, and stale template preview rejection.
- The extra independent disposable script
  `/tmp/db132-independent-boundary-probes.py` reproduces findings7–9; results in
  `/tmp/db132-independent-bundle-boundaries.log`. Passing existing suites do not
  override these concrete failures. No app/test source edits were made.
- Asked the backend owner to identify or add accepted-contract coverage for
  default-switch/archive-resolution races, retained remove/re-add and ambiguous
  identity, and late bundle rollback. Those boundaries are not all proven by the
  six PostgreSQL tests above.

## Corrections7–10 independently verified

- Re-ran the original disposable boundary probes: retained legacy reservation
  remains0 and inventory50 after quantity2 reapply; core quantity and reservation
  both become2; owner-requested fleet ad-hoc response omits `pricing`, `unit_cost`
  and `unit_price`. Log `/tmp/db132-independent-bundle-corrected.log`.
- Independently ran the five added tests selected by
  `ad_hoc_downward or search_service_alias or plain_operation or zero_reservation
  or core_quantity`: **5 passed**,26deselected,39warnings,6.63seconds. Log
  `/tmp/db132-independent-boundary-tests.log`.
- Alias HTTP test proves missing managed confirmation is non-mutating; confirmed
  alias and canonical retry share one service command, one labor/part and one stock
  effect; role reduction projects safely and removed fleet scope denies retry.
  Ordinary labor-operation retries also remain durable after Redis bypass.
- Core test proves expected-core quantity/version advances, original value stays15,
  and an on-hand core blocks another quantity change with persisted usage/core/
  inventory unchanged after rollback. Remaining requested race/retention cases and
  final frozen-candidate reruns are still pending.

## Foundation checks and evidence

- Independent command, in backend: `/tmp/db128-backend-venv/bin/python -m pytest
  tests/test_parts_pricing.py -q --disable-warnings --maxfail=3`.
  **18 passed**, 9 warnings, 2.11 seconds.
  Log: `/tmp/db132-independent-foundation-tests.log`.
- The existing suite covers band edges, distinct floor/minimum/fixed/internal
  behavior, unknown cost, invalid money and overflow, configuration replay,
  default ABA, archive/default constraints, basic tenant/role/CAS, direct managed
  attachment and downward preview. It does not prove the failing durable response
  replay cases above or PostgreSQL locking/trigger enforcement.
- Configuration commands authorize active tenant and current owner/admin role
  before the durable receipt lookup. Fingerprints include route, actor and tenant
  plus validated payload; tenant financial serialization precedes receipt lookup.
  Raw Redis idempotency bypass is present for the new parts-pricing namespace and
  the direct/ad-hoc/flat-service repair-order routes. HTTP-level coverage must
  verify no other final P1 writer can bypass current authorization via Redis.
- Default policy uses a monotonic generation with tenant lock and row lock;
  unchanged selection is a no-op, and NULL/A/NULL and A/B/A transitions cannot
  reuse an old generation. Rule/name updates append a revision. Archive cannot
  remove the current default. No default or matrix is seeded by migration.
- Preview and policy/config readers require owner/admin; sample requests are
  bounded and extra-forbidden, inventory IDs are exact tenant/nondeleted lookups,
  foreign/missing IDs fail the whole request, and sample resolution performs no
  persistence. Cursor signatures bind the tenant/view/entity. Date/rule/internal
  private details are not exposed by the ordinary SafePrice definition.
- Migration174 has same-tenant composite references for matrix/revision/policy
  and durable audit references. Historical PartsUsage audit identity deliberately
  has no live usage FK. Revisions/events have UPDATE/DELETE rejection triggers;
  attachment origin snapshots are immutable once present. Existing nullable
  snapshots/floors, false fixed flag and pricing version0 preserve legacy rows.
  Review of these definitions is not independent PostgreSQL execution. Owner
  migration/compatibility receipts are recorded in the main P1 receipt; final
  independent PostgreSQL tests remain required.

## Reviewed source snapshot

Git blob hashes captured after the early review/reproductions. Files may change
as the owner fixes findings and completes integration; HEAD alone does not identify
this uncommitted candidate.

| File | Git blob |
| --- | --- |
| backend/alembic/versions/174_parts_pricing_matrix.py | `50c941d915b4d95d73e14b09040f7c3407aa0d26` |
| backend/app/db/models/parts_pricing.py | `5e424deaced8f50a95571585ff9fa07584bfe9a8` |
| backend/app/services/parts_pricing.py | `2fe668467416163cc45229fd029e26a17c849cb6` |
| backend/app/services/parts_pricing_rules.py | `a4933505a91d2eac661334187c9055c359978233` |
| backend/app/api/v1/endpoints/parts_pricing.py | `86e42270e0d66dcac2ab78087f3e5fc6900091b6` |
| backend/app/schemas/parts_pricing.py | `295b862633c157d6bbd8c57ba1ddb257ac8bc460` |
| backend/app/middleware/idempotency.py | `a9dbfe4fa2b13fea115751dc0005f5e5a1af42b4` |
| backend/app/schemas/repair_order.py | `729ce495cc520dd2cbd4bd0967a9fe9a210eb8cc` |
| backend/app/api/v1/endpoints/repair_orders.py | `de8bb901f95fcef027ed69c458434b3036162743` |
| backend/tests/test_parts_pricing.py | `5684e688368c3fa7cef77ac30a91d4eb6f2486ed` |

## Delta source snapshot

Git blob hashes captured during the bounded correction check; source is not frozen.
The initial snapshot above describes the original findings, not this corrected
candidate. The backend owner is still correcting broad-writer regressions and
running wider notes/financial coverage, so final review must identify the stable
commit and rerun its changed surface.

| File | Git blob |
| --- | --- |
| backend/app/services/parts_pricing.py | `d310bd15dbf4329a1ea1f51ff79a9feb9d76d09e` |
| backend/app/services/parts_pricing_rules.py | `06104a2e311c4a091c0f99d1735257b83d598933` |
| backend/app/schemas/parts_pricing.py | `9199baf3f7553864274d5103a58663b7ae9d9204` |
| backend/app/api/v1/endpoints/repair_orders.py | `b7f8987a330bbc272d828fc2fd0f91aa55d04b19` |
| backend/app/api/v1/endpoints/inventory_lifecycle.py | `b74621c633eabfc3aae3f650c8756bc4d74991d8` |
| backend/app/services/counter_sale_service.py | `bfa46be6c0e21e71d339aaaca1c7f0d36ab18a9a` |
| backend/app/api/v1/endpoints/fleet.py | `fb0b3e82d5787f4d1ad9d79fa926c273986e1688` |
| backend/app/services/parts_pricing_planner.py | `1fe6c9a17d65663d8c67d8a464cd0ee848d9873b` |
| backend/app/middleware/idempotency.py | `aea31895c725b33e7da4bd86bf563bf38616619b` |
| backend/tests/test_parts_pricing.py | `b442ffe8b3d131cfb0358380e009ee5d8fac10ca` |

## Remaining gate work

Review the stable writer/serializer delta and run the accepted contract's shared-path, retained-line,
privacy, stale preview, no-op/idempotency, deletion/audit and real PostgreSQL race
cases. Confirm deployment remains inactive by default and that only authorized
synthetic scope is used for policy activation during QA. Parent owns actual
Light/Night desktop/mobile acceptance, protected CI, release and production reads.
No implementation-complete, final QA/Security, merge or production claim is made
by this early receipt.

## Final correction verification — 2026-10-15, 22:18–22:23 UTC

Reviewed committed application candidate
`23c3f9a0474b665dbaff67f6ae8585bb845532a3`. Root subsequently synchronized main at
`f04c318d1999c05cffe0a546f2dc7435d284d216`; independently verified its only application
delta is the already-merged unrelated ETS cancelled-import source/test. All P1
frontend files are unchanged and all31 backend manifest hashes still match.
The board conflict was resolved by root and left untouched by this reviewer. The
backend owner's final application manifest is
`0579ed3005b5aaf3861d243151ee7003f77a10d2866ff784b777fdef8cac883a` in
`/tmp/db132-backend-evidence/boundary-frozen-manifest.json`; earlier hashes in this
receipt are historical finding snapshots, not final source identity.

- Independently ran `/tmp/db128-backend-venv/bin/python /tmp/db132_pg_tests.py`:
  **12 passed**,9warnings,3.85seconds. Log
  `/tmp/db132-independent-postgres-final.log`. Runner and tests restrict writes to
  disposable `localhost:5432/db132_test_pricing`; no preview/production writes.
  In addition to immutable/composite constraints and original lock races, this
  proves default switch/clear-and-archive versus attachment, actual component
  recreation/removal/re-add, ambiguous legacy rejection, and late second-part
  failure rolling back labor, parts, stock, audit and durable receipt. The exact
  production-session total regression passes with `autoflush=False`.
- Independently reran all12 files from the final frontend handoff with Node22:
  **223 passed,0failed**. JSON
  `/tmp/db132-independent-frontend-final.json`, output
  `/tmp/db132-independent-frontend-final.log`. This includes the new receptionist
  retained-manual-line test and “Keep my draft” current comparison baseline,
  canonical service-operation confirmation, missing-conflict-preview refresh
  followed by explicit acceptance, refresh failure/retry, role/tenant/session/
  context cancellation, and no write after Escape. Finding11 is closed.
- Independently reran the full19-file backend command from
  [the backend handoff](DB132_BACKEND_HANDOFF.md): **269 passed**,39warnings,
  92.93seconds. Log `/tmp/db132-independent-combined-final.log`. Coverage includes
  P1 production-session direct/HTTP tests, shared writer/fleet paths, financial
  floors/discounts/locking, inventory lifecycle, quote/invoice snapshot reads and
  notes/operation notes. No skipped test is presented as passing coverage.
- Source review confirms the raw service-operation alias now shares the canonical
  normalized service command, current audience and durable receipt; ordinary
  labor-operation retry has its own domain receipt after the Redis bypass.
  The shared frontend conflict handler never writes merely because its recovery
  read succeeds. It retains an inline error if recovery fails.
- Independently inspected the committed screenshots
  `db132/local-light-review-desktop.png`, `local-light-review-390.png`,
  `local-night-review-320.png`, `local-light-matrix-final-320.png`,
  `local-night-matrix-landscape.png` and `local-night-policy-320.png`.
  Supplied images show readable values, visible review actions and no horizontal
  clipping in those captured states. They do not by themselves prove persistence,
  keyboard/focus behavior, all viewports or full workflow acceptance; root owns
  the actual browser journey and cleanup receipt.

No new unresolved source finding is identified in this correction delta. Final
completed local runtime receipt remains necessary before the final independent
gate. No merge, deployment or
production acceptance is claimed here.

## Responsive and CI delta — 2026-10-15, 22:35 UTC

Reviewed stable application `1c6e3c983f7a9d86cf8d87fe97ef8cee6c9e6619`. Its application
delta fromf04c318d adds only PartRow class hooks and scoped≤680px layout rules;
desktop declarations and all31 frozen backend files are unchanged. The
void-revision test correction now reads the active actor/session-scoped cache and
requires an actual post-void server read, preserving assertions that rejected
voiding stays locked and server-denied editing never shows work controls.

Independent three-file rerun (void-revision, force-void and FleetPriceBuilderPanel):
**22 passed,0failed**, JSON `/tmp/db132-independent-responsive-delta.json`, output
`/tmp/db132-independent-responsive-delta.log`. No application logic was changed
to make the stale tests pass. Protected full CI must still pass on the final SHA.

Independently viewed final `db132/night-fleet-final-390.png`,
`night-fleet-final-320.png` and `fleet-final-desktop.png`: complete part name/SKU,
readable separated quantity/remove controls and preserved single-row desktop.
Also inspected final Light mobile bundle/new-order recovery and Night320/Light740
matrix images. The new-order recovery image exposed finding13 above, so this
visual review does not yet grant final QA approval.

Read the backend owner's read-only [cleanup data](db132/local-cleanup.json) and
independently derived its invariants rather than relying on `all_checks_passed`:
four synthetic orders soft-deleted in draft with no completion/release/price lock;
zero active reservations; seven stock-movement groups exactly balanced; zero
linked quote/invoice/payment/settlement/ledger/completed-operation artifacts;
defaultNULL, matrix archived and service inactive. All six original inventory
stock/cost/catalog/core values match the recorded pre-migration backup extraction,
stock values recompute correctly, and temporary policies are cleared. One
recoverable zero-stock ad-hoc placeholder retains unknown actual cost and12.50
saved charge on its deleted parent; this residue is explicit, not silently
removed. This verifies the supplied readback and baseline comparison; the reviewer
did not itself run a query against the preserved preview or mutate its data.
This is the22:34 cleanup checkpoint only. Root subsequently reactivated the
synthetic service and part0004 fixed policy to reproduce finding13; final teardown
and refreshed readback are required, and the earlier JSON is not final cleanup.

Local workflow receipt distinguishes owner-in-fleet UI from unavailable restricted
accounts and an unavailable counter-sale entry. Those unavailable browser cells
are covered by automated authorization/retention tests and are not claimed as
browser passes. At this checkpoint finding13 remained the sole open local QA
blocker; the correction evidence follows. CI and production acceptance remain
separate.

## Finding13 correction review

Source now renders recovery notices and inline pricing errors through
`PriceBuilderPanel.workspaceNotice` inside `.db-workspace-scroll`. When the order
is closed, the same notice is inside the ledger section. Neither occupies an
unassigned outer grid cell or precedes a100%-height phone panel. Portalled pricing
confirmation remains unchanged, and Retry/Keep current work reopen the same saved
order. No data contract or backend source changed in this delta.

Independent final14-file frontend rerun: **269 passed,0failed**, JSON
`/tmp/db132-independent-recovery-final.json`, output
`/tmp/db132-independent-recovery-final.log`. This includes notice/inline-error
placement, footer outside the work scroller, close→ledger→Retry/Keep flow, unchanged
created-order identity, uncertain-write identity, actor-change cancellation, and
the corrected void/revise lock tests. No test edits were made by this reviewer.

Independently viewed `/tmp/db137-qa/p1-night-recovery-final-{desktop,390,320}.png`:
normal two-column desktop; recovery visible in the work area; phone order-total/
action footer visible at the viewport bottom. Root's actual DOM evidence places
the390 footer at794–838 in844 and the320 footer at690–734 in740, with matching
document/viewport widths and the notice's nearest work scroller confirmed. The
supplied320 capture includes a transient toast; it does not obscure footer actions.
Finding13 is closed against this correction. Final application commit is
`facf1482356d556e85d20cc19639518c0fe29a71`; independently verified it contains exactly
the reviewed recovery delta and unchanged frozen backend. Independently inspected
committed `db132/light-recovery-final-320.png` and
`light-recovery-final-desktop.png`: visible mobile footer, contained recovery
notice and normal desktop columns. Root confirms Retry/Confirm persisted95.25 on
the same000011 order. Refreshed teardown covering the two added recovery fixtures
is the remaining local closure evidence; protected CI and release are separate.

## Final independent pre-merge closure — 2026-10-15, 22:42 UTC

**QA GO / Security GO.** Final candidate
`d94133a05acddde4a4d05c7859fd5028a12bcc8b` synchronizes main13d5c867 afterfacf1482.
Independently checked the delta: only unrelated ETS completed-outcome source/test
and board changes. P1 frontend is identical to the independently tested recovery
candidate, and all31 backend file hashes still match the frozen manifest. A later
receipt-only commit does not change this application review; any subsequent P1
source change requires a scoped delta review.

Independent verification totals are **269 backend tests**, **269 frontend tests**
and **12 actual PostgreSQL tests**, all passing. Earlier223/22 frontend checkpoints
are historical, not additional unique tests to add to the final269. The final
source review covers tenant/role boundaries, authorization before durable replay,
current-audience projections, immutable pricing origin/audit and physical removal,
Decimal/canonical-total consistency, retained versus newly resolved parts,
reservation/core consistency, atomic rollback, genuine PostgreSQL races, current
actor/session cache boundaries, explicit conflict acceptance and create-once
recovery. Known implementation and rendering findings1–13 were returned to owners,
corrected by owners, and independently rechecked.

Root supplied the actual aligned local Light/Night desktop/mobile journey receipt;
this reviewer separately inspected its screenshots and source/DOM evidence, caught
the recovery footer defect, and verified the corrected final images. Local tests
prove saved/reloaded prices, original-price retention after revision, new-line
resolution, fixed/floor/minimum guards, manual/List/Stock, unknown-cost behavior,
service reapply, internal fleet quantity and create-once cancellation/retry. The
counter-sale feature and restricted-role/external-fleet browser sessions were not
available and are explicitly covered by automated tests, not claimed as browser
passes. Mobile is browser viewport/touch emulation, not physical-device testing.

Final [cleanup readback](db132/local-cleanup.json) is timestamped
`2026-10-15T22:41:42.411857+00:00`. Independently recomputed its invariants:
all **six** QA orders000006–000011 soft-deleted in draft, no completion/release/
price lock, zero active reservations, **13 reserved /13 released**, every movement
group netzero, all linked financial/completion artifact counts zero, matrix
archived/defaultNULL, part policies cleared and synthetic service inactive. All
six original inventory stock/cost/catalog/core values match the preserved backup
extraction and stock valuations recompute correctly. The documented recoverable
zero-stock placeholder keeps unknown actual cost. Root also confirmed original
Night appearance restored. This supersedes the four-order22:34 checkpoint.

No production mutation, deployment or browser operation was performed by this
reviewer. Release must retain the accepted no-guessed-policy-activation boundary,
verify migration174 and exact service SHAs/health, and complete the permitted
production Light/Night desktop/mobile read/preview/cancel checks before marking
DB132/P1 Done. Earlier failed CI is not a pass; the final protected run remains
mandatory. This receipt is frozen for the delivery owner's final docs commit.


## Final-CI correction: independent delta closure — 2026-10-15 23:48 UTC

**Local QA GO / Security GO on the corrected source.** Reviewed baseline HEAD is
`ad99dff0ed6f05c456a0ae60225d1e92eb80830b` plus the frozen six-file backend delta.
Only two application files change; the four test files expand negative coverage
or repair dependency arguments without weakening existing assertions. All other
previously reviewed backend application files and all frontend files are unchanged.
The owner may commit this receipt and the matching delta for one fresh protected
CI run. This is not merge/deployment approval before those checks pass.

Exact application SHA256 values independently matched both before and after tests:

| File | SHA256 |
| --- | --- |
| `backend/app/api/v1/endpoints/repair_orders.py` | `c44989fe6c75bb3bac1cb4e544a90d426aa1dc20e2f97cda1d466ec037719f49` |
| `backend/app/services/parts_pricing_planner.py` | `2fffabdb7f5d274a0a56773c4d8152024eadeb8d23fa393ef02d9a31e2af9e1c` |

The complete six-file manifest is
`/tmp/db132-backend-evidence/ci-correction-manifest.json`; the SHA256 of that
manifest file's bytes is
`1883e1afc6fefab74abe7e74dfaee6b91c4f0db8cbc91e1ab92be82ca64b568d`.

Finding 14: both catalog and ad-hoc attachment now map the tenant-qualified
pre-replay order lookup through the existing generic 404 error mapper. Assignment
checks remain before replay/planning. The expanded real HTTP matrix covers
foreign-tenant, missing and soft-deleted orders (404) and same-tenant unassigned
mechanics (403), while asserting no placeholder, usage, stock movement, pricing
history or durable receipt is created. Existing order/financial/outbox/websocket
no-op assertions remain. Source review also reconfirmed planner context and
service/operation entry-point error mapping; no analogous unhandled read was
found among those changed writer paths.

Finding 15: the existing insufficient-stock 400 guard executes before pricing
confirmation. Without a submitted pricing fingerprint, explicit shortage consent
can satisfy the stock-only review for a direct `parts_add` whose newly resolved
lines are all unmanaged/default and whose scope omits no component. It cannot
approve managed or manual/stock pricing. Every supplied fingerprint still follows
exact validation, even for an unmanaged line. Canonical prices, fractional package
reservation and shortage metadata remain unchanged. HTTP same-key replay returns
one usage and one reservation, without another stock decrement.

Independent execution on the final files:

- **339 passed**, 39 warnings, 93.59 seconds: the prior 19-file affected pricing,
  financial, fleet, notes and writer suite plus
  `test_db003_additive_tenant_boundary.py`, `test_fractional_part_quantity.py` and
  `test_service_checklists.py`. This includes all 33 P1 tests and the corrected
  101-test affected matrix. Log: `/tmp/db132-independent-ci-correction.log`.
- **12 actual PostgreSQL tests passed**, 9 warnings, 3.65 seconds, using only
  localhost `db132_test_pricing`, production `autoflush=False`, and the existing
  isolated runner. Log: `/tmp/db132-independent-ci-correction-postgres.log`.
- **3 additional independent HTTP probes passed**, 37 warnings, 4.98 seconds,
  stored only under `/tmp/db132-independent-stock/`. Explicit shortage consent
  cannot approve a new manual price, a Stock-intent price, or an invalid supplied
  unmanaged fingerprint. Each rejection retains stock and creates zero usages.
  Log: `/tmp/db132-independent-stock-intent.log`. These probes are separate from
  the 339 repository tests and did not edit application or repository test files.

The prior **269 frontend tests**, supplied actual Light/Night desktop/mobile
journeys and six-fixture cleanup readback are unchanged evidence, not rerun or
newly claimed browser acceptance in this backend-only correction. This reviewer
performed no browser operation, preserved-preview mutation or production action.
The final protected run must pass on the committed correction; migration 174,
exact release identity, permitted production acceptance and rollback evidence
remain the delivery owner's release gate. This receipt is frozen for that commit.


## Independent production closure — 2026-10-16 02:31 UTC

**Production QA GO / Security GO.** This decision covers DB132/P1 and the focused
production feedback correction. It does not activate a pricing policy or approve
future customer-pricing work. The reviewer made no browser, application, inventory
or financial writes; the only new production operation in this review was the
explicitly assigned aggregate SQL read inside a repeatable-read, read-only
transaction with a 10-second statement timeout.

Release identity was independently checked against Git and GitHub. PR542's tested
`060bba1bd9842404e56c6225b3e0196a21e5301f` and merge
`53eb98031d9247629e8300f14d0447c6d8b0d046` have identical trees; all six jobs in
run38825768055 succeeded. Captured Web and Worker deployments both identify that
merge and SUCCESS. PR544's tested `9441edf054136fa4f08ad12497e0310f53320819`
and merge `70530bda5705b30e27c3f222421b77e9e7ce6341` have identical tree
`d72da02d56ec7fa5671d5e784a6781190c00fb91`; all six jobs in run38830933939 succeeded.
The [corrected deployment receipt](db132/feedback-release.json) identifies Web
`ebc872be-cee4-4598-8165-79406459d9cf`, exact public build70530bda, and successful
database/Redis readiness. Schema is174. The final correction changes UI only;
the previously reviewed backend and migration remain the deployed foundation.
Recorded Web/Worker startup samples contain no schema/fatal errors or 5xx; the
worker connected to Redis, became ready and completed normal scheduled tasks.

Root performed the authenticated production journey from02:20:12 to02:24:38UTC.
Independently reviewed [measured evidence](db132/production-ui-evidence.json) and
representative final screenshots for Night390 error, Light320 success and
Night320 policy. Both themes cover1280 desktop,390/320 portrait and740 landscape.
Successful and repeated invalid previews are fully visible and focused inside the
existing scroller, with matching document/viewport widths. Error390 bounds797–836
fit844; success320 bounds683–732 fit740; landscape343–392 fits400. Policy actions
remain44px high and within the viewport. Actual action contrast is7.58:1 in Light
and5.36:1 in Night. Close/Escape focus return, draft cancellation/reopen, readable
saved-price text, unchanged historical order75+35.73=110.73/invoice112.98, empty
bounded console log and original Day appearance restoration are recorded by Root.
These are browser viewport/touch checks, not physical-device certification.

Production matrix/sample and policy work remained read/unsaved-preview/cancel.
The [post-journey state](db132/production-ui-state.json) still has zero pricing
matrices, revisions, events, defaults and configured inventory policies. The
synthetic zero order remains deleted with the same timestamp and totals.
No quote, invoice, counter-sale or pricing mutation was used for acceptance.

### Inventory fingerprint attribution and limits

At01:10UTC, after both deployments, all three fixed-cutoff fingerprints still
matched the pre-release baseline:1612 inventory rows,2934 saved usages and2424
invoices. At02:23UTC the saved-usage and invoice fingerprints still match exactly;
inventory is now `dd03d7523c7ba3b097412f8a13553008` instead of
`9e3027f6ebea64d2bf4d2ebb70ecc2ff`. Therefore **inventory is not claimed unchanged
throughout the later acceptance window**.

Independent review of the raw inventory delta finds798 unique pre-cutoff IDs,
all updated at exactly `2026-10-16T02:13:49.062899+00:00`, all pricing_version0.
The existing sync log records `import_to_truckpitstop.py --parts` committing at
that time, with795 update operations,17 inserts and4 newly retired entries.
The independently executed production aggregate at02:29:26UTC confirms:

| Group at the exact sync timestamp | Rows | Source | Pricing version |
| --- | ---: | --- | --- |
| Existing before cutoff, refreshed import stamp | 794 | easy_truck_shop_import | all0 |
| Existing before cutoff, new retirement stamp and older import stamp | 4 | easy_truck_shop_import | all0 |
| Created during this import | 17 | easy_truck_shop_import | all0 |

Aggregate evidence: `/tmp/db132-independent-inventory-attribution.json`; query
source: `/tmp/db132-independent-inventory-attribution.py`. No item values or
customer identities are emitted by this final aggregate read.

Railway identifies the sync's separate deployment10764d7a at older code
`9fe12abacd04722e4afbf4c2c6476160a18eca96`. Its `resync_parts` function is byte-identical
to the P1 merge and current source, SHA256
`5933b9c8ae4c49531088241f2eef06c5972f78a31731ce20aceb019b62ee545d`.
That pre-existing writer directly sets cost, selling price, stock, updated_at and
ets_imported_at; its retirement update changes only retirement/updated stamps.
It emits neither P1 pricing events nor inventory activity entries. This explains
why the concurrent changes are not represented by those empty event tables.
All observed old-row writes have the same importer stamp and source behavior.

The795 log value counts loop/update operations, not distinct rows; the observed
794 distinct refreshed old rows are consistent with a repeated canonical SKU in
the input. No post-cutoff existing updated row was found, so none is invented to
reconcile that difference. The exact repeated input cannot be identified from the
available log. Railway reports the sync container EXITED/deploymentStopped; it
was not restarted or SSHed into. Its retained `data_bak_*` snapshots are therefore
unavailable for this bounded review. There is no retained row-level pre-change
inventory image in the release receipts, so the earlier inventory fingerprint
cannot be reconstructed from exact prior values. We do not claim that stronger
proof or certify the sync's individual values from aggregate counts alone.

The timing, exact row stamps/source, unchanged independently deployed importer,
pre-sync fingerprint equality, inactive P1 configuration and preserved historical
financial hashes support attribution to normal concurrent ETS sync, with no
remaining evidence of a P1 release regression. This closes the inventory
attribution hold with the limits above. No further production writes, restarts,
unrelated test reruns or pricing activation are required for P1 closure.
