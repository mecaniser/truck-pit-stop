# DB133 / C1 independent QA and Security review

Reviewer: `r1_independent_gate`, assigned by Product & Delivery Lead. This reviewer
has not implemented or directed C1 application or test changes. Ownership is
limited to this receipt. Backend & Integrations is accountable; Root owns the
board, runtime, browser acceptance and release record.

## Current gate: local QA/Security GO — protected CI and production release gates pending

Reviewed accepted contract commit `201e7935bef792260b819a412bdf32795dc2405a` on
`codex/customer-pricing-defaults`, plus the baseline source at that commit.
Read the delivery/local-runtime skills, constitution, delivery workflow, tracker,
contract and readiness/implementation receipts. This read-only stage does not
start services or independently establish current runtime alignment. The later
schema probes below use only the disposable PostgreSQL database. No browser
actions, preview migrations or production operations were performed by this reviewer.

The approved outcome remains optional customer labor/matrix defaults, captured
new external-order terms, retained line prices, existing counter behavior and a
narrow C1 merge guard. New external fleet work uses agreed customer labor rate,
otherwise shop billing rate. Internal behavior stays separate. Legacy finance,
import and full customer-identity merge remediation are outside this review.

## Contract clarification returned

1. **Resolved in accepted contract — walk-in counter snapshot identity.**
   Contract lines146 and160 require `customer_id: string` and say counter
   snapshots use the same identity/source fields. Lines470–471 require a new
   walk-in draft to capture shop/catalog policy, despite having no customer.
   The document does not define the absent-customer form for customer ID/name,
   version and policy-event evidence. Architecture should make that wire shape
   explicit without fabricating an account identity or event. Architecture has
   now supplied an explicit NULL identity/version0/eventNULL variant with actual
   shop generation, matrix revision or catalog mode. This resolves the contract
   clarification; integrated endpoint and counter tests remain required.

No implementation defect is asserted merely because owners are still building
the accepted feature. The source risks below are concrete acceptance targets.

## Independent PostgreSQL schema review — 2026-10-16 02:57 UTC

Reviewed migration175 SHA256
`e7a37d49cba996cddea83999d9f90d435a1952047ff0d6da27dc4d14edfa169d`
and the corresponding model declarations. Executed
`/tmp/db128-backend-venv/bin/python /tmp/db133-independent-schema-probes.py`
against explicitly guarded `localhost:5432/db133_test_pricing`, schema175.
Evidence: `/tmp/db133-independent-schema-probes.json`. Every probe, including
successful writes, ran inside a rolled-back transaction; the outer fixture
transaction was also rolled back. Original legacy order policy remains NULL and
the synthetic probe user is absent afterward.

**14/16 probes passed; two release-blocking schema defects were returned to Root
and Backend & Integrations.** Both are in
`backend/alembic/versions/175_customer_pricing_defaults.py:70–75`:

2. **Resolved below — policy could change in the UPDATE that finalizes a sale.**
   Given a draft with a non-NULL policy, update customer, policy, and status to
   `completed` together. Actual: PostgreSQL accepts it. Expected: replacement
   requires an editable draft before and after the change, per contract97–100
   and508–524. The trigger checks OLD status but not NEW status. A service guard
   is still required, but does not substitute for the stated schema guarantee.
3. **Resolved below — draft buyer change could erase the captured C1 policy.** Given that
   same draft, update customer plus both policy columns to SQL NULL. Actual:
   PostgreSQL accepts it. Expected: an eligible buyer change captures a new
   account or walk-in policy; it cannot turn previously captured work into a
   legacy-policy record. The counter trigger has no non-NULL replacement guard,
   and the generic shape check deliberately permits NULL legacy rows.

Passing probes: eligible draft-to-draft buyer replacement; unchanged-buyer and
already-completed policy replacement refusal; cross-tenant customer matrix,
order revision, counter revision and event revision refusal; order policy and
labor-origin replacement/clearing refusal; audit UPDATE/DELETE refusal; and the
real downgrade adoption guard raises before any schema drop. The downgrade
probe executes its exact initial DO guard only, not a destructive full downgrade.

Separately inspected owner evidence for the real174→175→174→175 migration,
six malformed policy shapes and NaN/zero/negative rate rejection. Compared all
seven table count/fingerprint pairs in Root's preserved-preview before/after
receipts at02:52:08/02:52:23 UTC: identical. These are reviewed owner receipts,
not independently executed preview operations. A trigger correction needs both
fresh migration proof and parent-coordinated alignment of the already-upgraded
preview; this reviewer will not modify its schema.

### Correction recheck — 2026-10-16 03:00:57 UTC

Backend corrected the counter guard to require both OLD and NEW status `draft`,
an actual buyer identity change, and a non-NULL replacement snapshot. Reviewed
corrected migration175 SHA256
`2dcf08c6b502917e303ac89f21d0e438338a5abef9c014dc4e962f0f302b5f66`.
Independently reran the identical sixteen PostgreSQL probes after the owner
repeated the disposable migration round trip: **16/16 passed**. Both prohibited
updates now raise the intended policy error, while legitimate draft buyer
replacement still succeeds. Audit immutability, tenant FKs, retained policy
immutability and downgrade refusal remain green. All probe writes were rolled
back; the original legacy policy and probe-user cleanup checks pass.

The latest `/tmp/db133-independent-schema-probes.json` records this corrected
run. Findings2/3 are closed for schema source and disposable PostgreSQL.
Parent-coordinated preserved-preview function alignment is still a distinct
runtime step. This is a **schema-only pass**, not integrated feature, QA,
Security, merge or release approval; application source is still evolving.

## Source-backed acceptance risks

| Boundary | Baseline evidence | Independent negative/retention case |
| --- | --- | --- |
| Authorization before replay | Generic Redis middleware caches standard/quick RO POST responses before route execution; `idempotency.py:78–85,196–215` | Actual HTTP same-key retry after role, tenant or scope change must reauthorize and project current permissions. Shop policy/source fields cannot survive a downward fleet projection. Configuration PUT has its own durable contract and must also reject unauthorized replay. |
| Saved labor remains saved | `price_build_service.py:314–315,685,691` and `fleet.py:3201` currently overwrite retained rates; service reapply enables auto recalculation | Saved default, explicit manual and unknown legacy rates survive reapply/recalculation, including `auto_recalc_enabled=true`. Hours may follow existing rules; source snapshots and permitted manual rates, including zero, do not silently reset. |
| Exact payer and internal classification | Standard constructor uses the selected customer as bill-to even when it is not the truck owner; fleet helper also creates external work | Exact payer terms, not vehicle owner or an unrelated selected account, are captured. House/internal classification follows the existing helper, with all internal preference combinations unchanged. |
| External reservation ordering | Standard intake reserves an originating-call order UUID before its existing-order lookup | Existing authorized retry returns its original policy. A changed agreement before reserve makes no provider reservation; a later conflict preserves the reserved UUID and creates no duplicate order/relationship or customer send. |
| Generic customer self-service | `customers.py:710–728` applies every accepted generic update field with `setattr` | Customer create/update and portal schemas cannot accept private pricing fields; dedicated manager configuration, history and projections remain separate from tax permissions. |
| Source versus current charge | Existing labor writers have independent manual/default behavior | Explicit default intent ignores a stale echoed rate; manual intent requires permitted amount/role. Hours-only or unchanged-rate edits do not invent a manual event, and later account changes do not relabel origin by comparing current numbers. |

Source inventory confirms three native RO constructors and seven genuine hourly
labor creation sites. The additional sublet constructor is amount-based and
excluded. Appointment/catalog estimates are not extra RO/labor creation paths and
are not pulled into this outcome. All ordinary attachments, recommendation,
service/book, fleet PM/deprecated/staged writers and their contextual previews
remain within the accepted coverage.

## Independent gate cases when the integrated candidate is stable

- **Configuration and privacy:** exact GET/PUT/history shapes; owner/admin only;
  role before tenant-qualified live lookup; foreign/deleted/internal subjects;
  omitted versus NULL, zero/nonfinite/precision/bounds, reason validation, unknown
  fields, foreign/archived matrix; atomic CAS/no-op/ABA and same-key payload
  conflict. History cursor is tenant/account bound. Role change before replay and
  frontend identity/presentation changes cannot expose stale private terms.
- **Captured policy integrity:** unset customer still captures the actual shop
  rate and revision or explicit catalog mode. Change/clear account, shop default,
  rate or matrix after creation: new additions to old C1 work keep captured terms;
  future orders use the new terms. Archived pinned revisions remain usable.
  Missing, cross-tenant, malformed or typed-column/JSON-inconsistent evidence
  fails closed rather than selecting current defaults. Configured policy version
  requires its matching event. Legacy/internal snapshots remain NULL.
- **All writers and atomicity:** shared fixture125/B2 versus inherited145/A1
  across standard, quick and external fleet/PM/staged intake, service/direct/book
  labor, recommendation and parts. Quick-create token must match the actual
  phone-resolved account and roll back staged identities on failure. P1 preview
  and commit agree; late failure rolls back order/work/stock/core/events/receipt.
  Sublet, time tracking, completion, taxes and financial finalization stay intact.
- **Counter drafts:** walk-in/account capture, same-buyer/contact edit retention,
  eligible buyer-change policy only for genuine future lines, existing prices and
  immutable origin retained, stale sale/preview rejected atomically. Completed
  receipts/returns never look up current agreements; feature activation is absent.
- **Narrow merge safety:** policy-bearing, previously cleared and snapshot-
  referenced loser is refused before mutation, including deleted/completed
  owning records. Configured winner does not unnecessarily block an untouched
  loser. First reference/configuration versus merge and reverse-pair merge are
  serialized, without claiming to fix unrelated financial identity races.
- **Real database evidence:** disposable PostgreSQL upgrade/legacy NULL/downgrade/
  upgrade; additive schema preserves money. Actual races cover account saves,
  shop/customer/matrix changes versus intake, staged fleet preview, first C1
  references versus merge, and manual rate edits versus reapply/completion.
  Application-mode `autoflush=False`, locked rereads and true rollback are used;
  no claim of a new labor stale-form CAS protocol.
- **Actual UI:** Root supplies Light/Night desktop1280+, portrait390/320 and
  landscape740 acceptance for settings, source-aware intake, old/new separation,
  manual edit/reload, conflicts, search/Back, merge guard and optional authorized
  counter flow. Drafts/focus/Escape, readable messages,44px targets, one scroller
  and compact desktop remain required. Unavailable role/flag cells must be named,
  not counted as browser passes. This reviewer may inspect supplied images and
  evidence; it does not operate the preserved preview or production browser.

Final QA/Security approval requires the stable source and exact test evidence,
resolved contract clarification and actual runtime acceptance. Completion also
requires protected final-revision CI, exact merge/deployment/schema, health and
the contract's rollback boundary: P1-only code must not silently ignore adopted
C1 snapshots/defaults. No invented production agreement or real financial write
is authorized for verification.

## Configuration and policy-helper review — bounded integration checkpoint

Reviewed dedicated configuration GET/PUT/history/intake endpoints, schema,
`customer_pricing` helpers, narrow `customer_merge_guard`, generic idempotency
bypasses and actual create/merge call sites. The configuration endpoint checks
current manager role and live tenant/account before durable response reuse;
required nullable fields, strict version, finite positive cents, reason trim and
extra-field rejection are present. Its writes lock tenant/account, compare CAS
before no-op and record the event and receipt in one transaction. History is
signed and scoped by tenant/account. The merge helper checks configured/cleared
history and original snapshot customer IDs, including deleted owning work, before
the existing merge moves rows. Application writers remain under active integration.

Independent owner-suite execution:
`python -m pytest backend/tests/test_customer_pricing.py -q --disable-warnings --maxfail=3`
returned **18 passed/1 failed**. The sole failure was the test's literal ordering
comparison of equivalent Cache-Control directives (`private, no-store` versus
`no-store, private`), not missing cache protection. Owner subsequently corrected
that assertion; this run alone is not a green rerun. Log:
`/tmp/db133-independent-foundation.log`.

Independent supplementary probes were written only under `/tmp`, and run with
the repository's disposable in-memory SQLite fixtures and `autoflush=False`:
`PYTHONPATH=backend:backend/tests python -m pytest -p conftest /tmp/test_db133_independent_foundation.py -q --disable-warnings --maxfail=6`.
Result: **15 passed/4 failed**, log `/tmp/db133-independent-negative.log`.
Fourteen passing HTTP cases cover configuration/history denial for receptionist,
mechanic, fleet manager, customer and driver, plus atomic rejection of zero,
sub-cent/bool rate, bool version, foreign matrix, blank reason, extra snapshot
and either omitted nullable field. The fifteenth passes malformed dict-rate
handling. No external calls were made; the signed provider response was stubbed.

4. **Open — malformed saved policy does not consistently fail closed.**
   `customer_pricing.py:97–114` accepts a partial catalog snapshot with only
   schema_version and parts mode/matrix, missing captured identity/source evidence.
   `labor_default` at174–185 lets `Decimal('broken')` escape as InvalidOperation,
   and accepts rate100000000.00 beyond NUMERIC(10,2). Contract requires malformed
   saved policy to return409 `account_pricing_unverified`, never adopt or calculate
   from unverifiable evidence. Reproductions are the final two parametrized tests
   in the supplementary probe. Returned to Backend & Integrations and Root.
5. **Known signed-call retry defect — amendment integration in progress.** An
   actual HTTP retry after account125→135 returned409 rather than the original
   order/policy125 because prevalidation preceded existing-order lookup. This run
   loaded the pre-correction source. Architecture/Root have since approved the
   `c1_call_reservation` receipt amendment and backend is integrating it. The
   observed failure remains a regression case, not a verdict on that unfinished
   replacement. Review targets include current authorization and exact bindings
   before reuse; complete validated receipt shape without raw token; original
   order visibility/deletion checks and original policy; reservation-only durable
   commit before final capture; per-key serialization without broad financial
   locks during provider I/O; no second reserve for known committed success; and
   the explicit network/crash/pre-commit ambiguity limitation. The early new
   source still stored only three provider fields and omitted the existing-order
   deletion check; both were returned as integration targets before freeze.

`/tmp/db133-independent-foundation-source.json` records observed file hashes and
HEAD after these tests. Since owner edits continued during this bounded review,
it is an observation manifest rather than an exact frozen-candidate test claim.
The final gate requires clean reruns on stable source, real PostgreSQL races and
the previously stated runtime/release evidence. No preview/production mutation
or repository application/test edit was performed by this reviewer.

## Correction and frozen frontend checkpoint — 2026-10-16 03:16–03:18 UTC

Independently reran all19 supplementary configuration/policy probes against the
strict-snapshot and canonical reservation receipt corrections: **19/19 passed**,
`/tmp/db133-independent-corrected-negative.log`. Finding4 is closed for its
reproductions: malformed/partial snapshots and invalid labor now return the domain
conflict. Finding5's original-policy HTTP retry now passes with one stubbed provider
call and one resulting order. Full reservation interruption/authorization/race
coverage remains part of the integrated gate. Read source confirms full canonical
receipt bindings/time, no raw token persistence, authorization before reuse and
soft-deleted-order refusal. No live provider calls occurred.

Independently ran the owner's exact17-file frontend command with Node22 and
`--maxWorkers=2`: **241/241 passed** in24.96s. Log:
`/tmp/db133-independent-frontend.log`. Independent observed frontend manifest:
`/tmp/db133-independent-frontend-manifest.json`,26 changed/new files, digest
`d1f8ee6fa16b323cd477a817e85bcb9c80172cb5ac405c9908b90c7494f46850`,
HEAD `328363697f8a185c0f3b5a2ecf5903466a3bb333` plus the frozen working diff.
Reviewed safe projection schemas, identity-scoped caches and completion guards,
exact account/vehicle token binding, explicit conflict acceptance, uncertain-save
UUID reuse, capability-aware labor rates, nested Escape and focus restoration,
search-return integration and retained new-order identity. No new frontend blocker
found at this checkpoint. Nonfatal existing React Router/act warnings are not
represented as a warning-free run.

Inspected Root's actual390px Light search-return screenshot
`/tmp/db133-light-390-search-return.png`: exact text `Performance Carrier 001`
remains visible after the reported cancellation/Back journey. This is independent
visual inspection of supplied evidence, not reviewer-operated browser QA or
acceptance of the still-pending full theme/viewport/save matrix.

6. **Open — valid zero shop rate commits an order then returns a failure.**
   Existing `admin.py:1668` accepts shop labor_rate0. With that valid setting and
   an unset customer agreement, intake preview returns200 and rate0.00. Posting
   its token creates and commits the order, then returns409
   `account_pricing_unverified` from the new strict snapshot validator. Independent
   HTTP probe confirms order count1→2 despite the failure response. Positive-only
   validation applies to configured customer agreements; it must not narrow the
   existing nonnegative shop default. Both `validated_snapshot` and
   `labor_default` currently require `0 < rate` for either source. Reproduction:
   `test_existing_zero_shop_rate_remains_valid_for_new_order` in the `/tmp`
   supplementary test; log `/tmp/db133-independent-zero-shop.log`. Returned to
   Backend & Integrations and Root. **Integrated gate remains NO-GO pending this
   correction and the remaining complete acceptance evidence.**

## Zero-rate, sublet, fleet and concurrency recheck — 2026-10-16 03:21–03:23 UTC

Finding6 is **resolved for its independent actual HTTP reproduction**. Snapshot
validation now accepts nonnegative shop defaults while keeping configured customer
rates positive. The full supplementary set is20/20 green, including the zero-rate
POST returning201; `/tmp/db133-independent-final-foundation.log`. Independently
ran four affected repository suites (`test_customer_pricing.py`,
`test_price_build_service.py`, `test_fleet_manager_price_build_access.py`,
`test_db107_recommendation_conversion.py`): **93 passed**,39warnings,66.59s;
`/tmp/db133-independent-writer-delta.log`. These include the new zero-rate
intake/line/same-key retry and owner-downward fleet mutation projection cases.

A separate reviewer HTTP sublet probe created an amount500 line, changed it via
price-build PATCH to550 and verified total550, no C1 pricing snapshot/source and
no C1 labor audit event: **1 passed**; `/tmp/db133-independent-sublet.log`.
Inspected source confirms SUBLET exclusion in both response projection and rate
mutation auditing. Fleet summaries suppress new recommendation default/provenance
when presentation is fleet; mutation response paths forward that presentation.

After explicit handoff of the idle disposable database, independently ran
`/tmp/db133_independent_pg_tests.py` (same guarded runner with a separate evidence
output): **11/11 real PostgreSQL tests passed**,9warnings,3.62s. Evidence:
`/tmp/db133-backend-evidence/independent-postgres-tests.log`. Covered competing
customer saves, account/shop/matrix change versus intake, first policy/order/counter
reference versus merge, reverse-pair locks, saved manual rate versus service
reapply, immutable evidence and same-token concurrent known-success call
reservation. All tests used the disposable `db133_test_pricing` database; no
preview/production data was touched. Owner was notified when the slot was idle.

Reviewed the subsequent recommendation Add-again correction and independently
ran its two affected files: **31/31 passed**, `/tmp/db133-independent-reconversion.log`.
Successful conversion now clears completed hours and manual-intent state so a
later Add again displays its current supplied default. Cancel/Escape with existing
hours preserves the unsaved manual draft. A source-backed adjacent case was sent
to Root for confirmation: entering a manual rate before hours, then cancelling,
still reaches the `!hours` reinitialization condition on reopen. That case is not
covered by the31-test claim and must not be described as verified retention.

Observed delta hashes at this checkpoint:

- customer_pricing.py: `8ddab979bdcf23bf1c57635b83a0639c19090c1f2ab24e1ebeaaf7e7ef2202f3`
- price_build_service.py: `fad3cbbeb657333d2490472085afda96b85f88a9741f4e96e7b3ccd9eecc6ef1`
- recommendation_conversion.py: `69682f77c2c45ddc938b1c8d5c62f064738aff580fb2c7efbea9068d813314cd`
- repair_orders.py: `9d482d6725d6d07e3d77640e7a5b3a9fb83ce06707ce208d37f05d3aa59b067b`
- RecommendationConversionAction.tsx: `2f46641ac249a16f92de784006fd1c84828f941e1571e842a71070ba7c259479`

No full C1 GO: safe counter-detail projection and complete saved runtime matrix
were still pending, with final candidate manifest/CI/release evidence also required.


## Final counter and recommendation delta — 2026-10-16 03:32 UTC

The blank-hours manual recommendation draft concern is **closed**. Root reproduced
it in the actual390px UI and implemented the additional `!rateEdited` reset guard.
Independent source review confirms that initial/default drafts still initialize
from the supplied current default, completed conversions clear draft state, and
unsaved manual drafts no longer reset merely because hours are blank. Independently
ran both recommendation files on the corrected source: **33/33 passed**;
`/tmp/db133-independent-reconversion-final.log`. Root's stated Cancel/Escape actual
UI recheck is recorded in the main runtime receipt; this reviewer did not operate
the browser.

The final counter-detail projection is **closed at the source/automated gate**.
`counter_view` returns only the contract's schema/snapshot identifier/mode/parts
source and mode; legacy NULL snapshots are explicit legacy, captured variants use
validated saved evidence, and labor/account identity/matrix/rule/cost/audit data
are not spread into the object. Full detail serialization uses the same helper;
list and public receipt paths have no new policy field. Independently ran the
four counter cases from the C1/P1 suites: **4/4 passed**,61deselected;
`/tmp/db133-independent-counter-final.log`.

A narrow frontend integration concern was also returned and corrected: the former
same-buyer message claimed that every existing draft had saved defaults, including
legacy NULL-policy drafts. The final type models captured versus legacy explicitly,
and the notice reads only that safe saved projection: legacy uses current quoted
pricing, captured shows saved Account/Shop matrix/catalog, and a different buyer
shows the proposed future defaults. Keep my draft adopts the newly fetched saved
baseline. Existing line prices remain identified as retained. No current customer
configuration is fetched merely to render the notice. Independently ran
CounterSalesWorkspace on this final correction: **16/16 passed**;
`/tmp/db133-independent-counter-frontend.log`.

Verified every entry of the final backend manifest independently: **30/30 match**,
zero mismatches. `/tmp/db133-backend-evidence/final-source-manifest.json` normalized
sorted-JSON aggregate SHA256 is
`cafa79e290dafe731b92da3b26c8c2b775be4f5df6ac99344c89015e84349a0e`.
The owner's335 affected and89 final-delta pass reports are separate from the
reviewer's executed93 writer,20 supplemental HTTP,1 sublet,11 real-PG and4 final
counter checks above; overlapping cases are not summed as unique coverage.

Latest independently observed frontend delta hashes:

- RecommendationConversionAction.tsx: `22b6a11fb85a8672453d3753e6848674fec18c848b7ace2bf08b818187089390`
- RecommendationConversionAction.test.tsx: `684f6ab01d0e2704a156ce8102a14d296c25dfec028fa3c51b058562ce45dcc1`
- CounterSalesWorkspace.tsx: `2f7ae15dd9aabc53c4a4c8429b0ff4ed27f340342162a6f665d94c9d6b4ec705`
- inventoryLifecycleTypes.ts: `e2a27b38e277e073ccf60ab516784111d444b92608f290205ba9249ecf4177c1`
- CounterSalesWorkspace.test.tsx: `235bcb83df27cc3df1b4cafe8eb5fb11ee7a44964e64b7d0042a01370b3f1097`

All concrete source/security findings raised so far have corrected-source evidence.
This is **not full C1/release approval**: final saved Light/Night desktop/mobile
acceptance, synthetic local cleanup, exact committed candidate with protected CI,
and the required production migration/deployment/read-only acceptance still remain.
No preview or production mutation was performed by this reviewer.


## Actual Night settings finding — 2026-10-16 03:40 UTC

7. **Open — pricing input values and existing Tax copy are unreadable in Night.**
   Root's actual320px capture `/tmp/db133-night-320-settings.png` visibly shows
   blank-looking labor/parts/reason controls and almost invisible tax text. Root's
   DOM measurement reports input foreground/background both rgb246,248,251
   (1:1); independently inspected the image and source. The pricing stylesheet
   combines `--surface-overlay` with inherited foreground, while the Tax section
   retains fixed slate900/slate600 text. Focused errors passing previously did
   not establish field-value legibility. Returned to Frontend through Root.
   **Local UI gate is NO-GO** until the scoped contrast correction and final
   actual Light/Night values, selected option and tax text are reviewed. Backend
   source/security checks are unchanged.

Committed candidate identity before that correction: application commit
`a5cd369b` matches all30 backend manifest entries exactly; merge ancestry
`0deba3ed808642d63061c31b6778cf4f05a16e76` has no tree delta from it. The original
order-B screenshot was withdrawn by Root as an uncertain compositor capture and
is not counted as Night evidence. Its refreshed replacement is supported by
Root's current dark-mode DOM receipt; independently verified the pre-existing
`index.css`582–596 rule deliberately retains a light Price Builder working sheet
under dark/high-contrast mode. That does not excuse the separate customer-settings
legibility defect above.


## Final scoped frontend rerun — 2026-10-16 03:47 UTC

Frontend reports the final contrast and intake-error delta frozen. Independently
ran the three customer-pricing suites plus CustomerTaxExemptionControl and
RepairOrdersPage.customer: **83/83 passed across five files**,14.09s;
`/tmp/db133-independent-final-ui-delta.log`. Existing Router/Browserslist/Tailwind
warnings remain; passing JSDOM tests do not establish actual color contrast.

Source review of the narrow recovery callback confirms that explicit acceptance
clears only the matching generic pricing-conflict message, leaves unrelated errors
intact, performs no order submission, and rechecks current actor/context identity.
The changed field styles now pair scoped workspace foreground with overlay
background, including caret and placeholder colors, and adjust Tax copy inside
Business settings only. No Tax permission/persistence logic changed. Finding7
remains open until actual final theme measurements and readable screenshots arrive.

The six-file corrected UI manifest is
`/tmp/db133-independent-final-ui-manifest.json`; its sorted-JSON aggregate is
`fa2a829c1b6676eb5eb81b89bf588f635747d41acbf2b4bdd12d8ff090d5fef1`. Backend manifest remains unchanged.


## Night readability correction closed — 2026-10-16 03:51 UTC

Finding7 is **resolved** on corrected source and final actual UI evidence.
Independently inspected all five Root-supplied captures:
`/tmp/db133-night-desktop-settings-fixed.png`,
`/tmp/db133-night-320-settings-fixed.png`,
`/tmp/db133-night-landscape-settings-fixed.png`,
`/tmp/db133-light-desktop-settings-fixed.png`, and
`/tmp/db133-light-mobile-settings-fixed.png`. Typed137.50, the reason draft,
selected Use shop default option and Tax label/help are legible. Desktop remains
compact;320px fields/buttons fit; landscape Save is inside the scroller above the
fixed footer. Root reports no horizontal document overflow.

Root's actual computed input colors are Night rgb246,248,251 on17,31,51 and Light
rgb20,36,58 on255,255,255. Independently calculated WCAG text contrast from those
reported values: **15.57:1 Night and15.63:1 Light**. These are the actual-input
pairs, not an unmeasured claim for every component. Readability comes from supplied
browser images/measurements, not JSDOM. The earlier failure capture remains
failure evidence only. Corrected final intake-error acceptance, fresh synthetic
cleanup and exact committed candidate/release gates are still pending.


## Independent local candidate GO — 2026-10-16 03:54 UTC

**GO for the local QA and Security gates on candidate `929f2d4e55e220f09aedfbb28e4bae41eb12f99b`.**
This is approval to proceed through protected CI and the existing release process,
not a claim that C1 is merged, deployed, production verified or Done.

Independently verified the committed candidate against all30 final backend manifest
entries and all6 final UI-correction manifest entries: zero mismatches. Earlier
reviewed recommendation/counter changes are included in application commit
a5cd369b; the main ancestry merge added no tree delta. All seven numbered findings
and the subsequent bounded counter/recommendation/recovery concerns have corrected
source and relevant independent verification; no known local release-blocking
finding remains.

The main receipt's final local acceptance covers saved agreement/history,
new-order capture, retained earlier terms after account changes, manual labor,
recommendation source linkage, customer-matrix review/confirmation, assigned-matrix
archive refusal, retained archived revision, explicit stale-intake acceptance,
Cancel/Escape and customer-return behavior. Independently inspected final supplied
Light/Night settings and order captures. The final390px accepted-conflict image
shows the selected customer/truck and typed work retained with Account137.50,
without the stale warnings. Root's actual browser journey establishes no automatic
submission and Cancel returning to the customer; this reviewer did not operate the
browser. No optional counter-flag or restricted-role automated case is relabeled
as an actual browser pass. Viewport emulation is not physical-device testing.

Reviewed the fresh committed `db133/local-cleanup.json` checked at03:52:13UTC:
active customer rate/matrix NULL, tax false, version6; both synthetic orders
soft-deleted; no remaining part usages; test matrix archived. Independently
computed seven assertions across those fields and the stock events: all pass.
For each of the two affected parts, orderB's reservation102→101 and release101→102
balance to zero and match final stock102. This is recorded-event evidence, not a
claim that an independent pre-test per-row database snapshot existed. Immutable
agreement/order/line audit evidence remains intentionally retained. Root records
original Night appearance restoration and removal of device/touch overrides.
No invoice, payment, estimate or real-work completion was performed for this QA.

Release must still prove all required CI contexts on the exact final head, merge
tree identity, Web/Worker deployment identity, additive schema175/health/readiness,
legacy/pricing defaults unchanged by migration, and the agreed read-only/unsaved
production desktop/mobile Light/Night acceptance. Existing signed-call reservation
recovery has the documented crash/network/pre-durable-commit uncertainty boundary;
this GO does not claim provider-level exactly-once semantics or unrelated legacy
financial-merge remediation. Any substantive post-gate source change requires a
bounded delta review; a documentation-only receipt commit does not invalidate the
reviewed application identity.

## Production comparison preparation — 2026-10-16 04:07 UTC

Read-only review found two gaps in the initial release-evidence script: existing
counter header/line money was not fingerprinted, and late-visible pre-cutoff rows
or global pre-cutoff C1 activity could still return a green comparison. The script
owner corrected both in receiptversion2; these were evidence-only findings and
did not alter the approved application. Independent connection-free probes6/6 and
the script self-test pass. The corrected script SHA256 is
`b84f531769b6020380b663f761fef5faadfd241930ad448143b9cbbf20687c89`.
Changed financial hashes require review even when updated_at advances; late rows,
missing/changed original rows, source/config changes and global pre-cutoff C1
snapshots/events also require review. The incomplete version1 baseline is rejected.

Independently validated the new private0600 version2 baseline at fixed cutoff
`2026-10-16T04:07:03.781201+00:00`, schema174, read-only repeatable-read, readiness
ready. Counts:3671 repair orders,4670 labor,2934 part usages,2443 invoices,
765 customers,1 counter sale and1 counter line. Counter money hashes and all opaque
references validate. Canonical receipt digest:
`059f5b1f2192c3d9bd4b6db138451c3ed6ca6f02cc5aa70bf0009e49d5937620`.
No row manifest was printed; this reviewer opened no database/browser connection.
Original-cohort equivalence must not be described as all-production equivalence:
post-cutoff new work/adoption needs its own audit attribution, and a later timestamp
alone never proves a changed charge was authorized. Final175 comparison and
production UI acceptance remain pending.


## Narrow main-ancestry recheck — 2026-10-16 04:25 UTC

Reviewed integration of main PR548 (`e3ff99e0`) via `892f9420` and the subsequent
board-history relocation. Exact candidate
`0c531ad872051d5d46a53f3230cfc2db288a42cb` still matches all30 backend and all6
final UI manifest entries, with zero mismatches. The latter commit changes only
PROJECT_BOARD.md; incoming app changes concern the separately released Motive
telemetry work. The local C1 QA/Security GO therefore remains valid; no unrelated
broad suites were repeated. Fresh protected CI must pass on the integrated final
head. Earlier incomplete/superseded runs are not passes. The version2 schema174
production baseline remains the required comparison input; production175 and
browser release acceptance are still pending.

The board move also carried one preserved DB-036 history paragraph under the C1
heading. This documentation-only placement was returned to Root for normal final
docs cleanup; it does not change the application gate or justify rerunning tests.


## Dual175 lineage integration — 2026-10-16 05:08 UTC

**GO for the backed-up preview upgrade sequence**, not yet a final merged-source
or production-release GO. Main PR549 introduced the independently released nullable
contact snapshot and a second175 child of174. Source inspection confirms contact
migration SHA256 `591a7ffa2c503aa158544508497a5cbbeb08dfa5c3385e5cb0e83f2073309d67`
is byte-identical to main d5cb6628; the applied C1 migration remains unchanged at
`2dcf08c6b502917e303ac89f21d0e438338a5abef9c014dc4e962f0f302b5f66`.
The new no-op join SHA256
`f7c753ea7c120e6aa0f8720bc23cfa948579c38695e8b1c164f4f6ea6026f916`
has both exact175 parents. Independently invoked Alembic ScriptDirectory without a
DB connection and confirmed the single head `176_merge_contact_pricing`.

Reviewed the disposable runner and its completed9-case result at
`/tmp/db133-merge-evidence/result.json`: upgrades from174/contact175/pricing175,
repeat upgrades, empty-C1-evidence downgrade/upgrade and refusal of populated-C1
downgrade all pass. Normalized full-row hashes across10 tables match in every
comparison, including non-NULL contact JSON, pricing snapshots,2 immutable audit
events and1 durable command receipt. The owner executed these disposable database
cases; the independent reviewer inspected their source/results and hashes. No
reviewer preview/production connection or mutation occurred.

Root's sequence preserves compatibility: back up populated pricing175, apply only
the missing contact branch and176 via Alembic while the old Customer model remains
active, verify exact-row retention and schema, then integrate main/model. No stamp,
revision rewrite or populated downgrade is authorized by this gate. The v2
production baseline is historical; after main's contact175 deployment, the release
must use fresh version3 evidence with exact contact-only pre and merged176 post.
One bounded v3 reader gap was returned: internally inconsistent receipts could
claim compatible despite pre-existing C1 columns/events. Capture SQL already
checks them; receipt validation must also check its recorded fields before final
production-evidence approval.

The v3 reader finding is now closed. Corrected verifier SHA256
`03eea7a2f0dccd3a0f0b4100483112c1d0621fa9f0756b55160e19eac1eeee73`
recomputes exact recorded C1-column/event/contact/revision invariants. Independent
connection-free boundary tests13/13 and self-test pass; evidence
`/tmp/db133-independent-production-v3-probes.json`. Reviewed the owner's seven
actual disposable SQL selector/capture cases in
`/tmp/db133-merge-evidence/v3-capture-result.json`:174/contact-only pre, both176
post comparisons, wrong pre/post rejection and global pre-cutoff adoption review
all pass. Those database captures are owner-executed, not reviewer-executed.
Fresh production v3 baseline and post176 comparison remain release requirements.


## Final integrated local QA/Security GO — 2026-10-16 05:13 UTC

**GO on exact integrated application candidate
`4cbdc3e84ee0ebb04fdb675f389367f16901c39f`.** The prior local QA/Security gate
extends to this bounded migration/main integration. Independent manifest comparison
finds29/30 original backend entries unchanged and all6 final UI entries unchanged.
The sole backend difference is Customer's JSON/JSONB imports plus main's nullable
contact snapshot. An AST comparison removing only that new field proves the entire
existing Customer class, including all C1 columns/constraints/relationships,
unchanged. The two added migration identities and one-head graph were verified
above. C1 financial logic is unchanged; separately released main behavior remains
subject to the combined protected CI gate.

Independently ran the connection-free comparison of Root's preserved-preview
before/after receipts: pricing175→176, all10 normalized table hashes identical,
changed_tables[]. Root then activated the merged Customer model and reports direct
and proxied readiness plus an actual signed-in reload of customer pricing showing
145/hr Shop and Catalog Shop with no error. Reviewed the owner's exact-head
PostgreSQL rerun: **11/11 pass**,9warnings,3.38s on disposable schema176; evidence
`/tmp/db133-merge-evidence/merged-source-postgres-result.json` and matching log.
This reviewer did not perform the preview upgrade or operate its browser.

Explicit read-only production-capture GO also remains valid for frozen v3 verifier
`03eea7a2f0dccd3a0f0b4100483112c1d0621fa9f0756b55160e19eac1eeee73`.
Independently validated the fresh private0600 v3 pre receipt at cutoff
`2026-10-16T05:12:44.974006+00:00`: exact contact175, contact column present,
all C1 columns/event table absent, read-only repeatable-read, readiness ready and
all7 cohorts including1 counter header/line. Canonical digest:
`717b8646238f1d36d18c075eaf610f2dc99f6543813eb0ac0330c59e01c018de`.
This v3 baseline supersedes prior174/v2 release-comparison inputs. Final deployment
must prove exact merged176 with both schemas, compare against this fixed cohort,
review any real concurrent business changes, and complete production Light/Night
desktop/mobile acceptance. Earlier canceled/incomplete CI runs are not passes;
fresh protected CI on the final integrated head is still mandatory. No production
release/Done claim follows from this local integration GO.

## Resumed integration and Worker startup gate — 2026-10-16 16:30 UTC

**Local QA/Security GO retained, including the frozen read-only Worker gate.**
Reviewed baseline HEAD is `e56904603dfa27086d6f3f7bda2d50c62b5c1de0` plus the
four gate files identified by aggregate SHA256
`102174f86d7d052cecfce0d3ffcdf6a8786ed3b06239ca2b6007606a1a00783f`.
This approves the exact reviewed working-tree delta; the release owner must bind
it to the final committed candidate and protected CI before release.

Prior bounded identity checks retained the C1 gate through `4c85e71e` and
`8d67c4bb`: pricing code and Alembic tree were unchanged, the customer-return test
kept its C1 `base(url, options)` forwarding and all original assertions, and the
only backend integration was the five independently approved PR551 helper,
import and test files. Incoming fleet changes matched main exactly. The customer
test now covers immediate and delayed responses, refuses paging while the search
response is pending, and waits for enabled Next before continuing. Its recorded
40/40 focused result and lint were reviewed. Superseded or canceled CI runs are
not final release evidence.

The proposed private controlled migration runner was **not approved**: its DDL
connection lacked the guard connection's timeouts, and an upgrade exception
could misreport an uncertain commit as false. Root abandoned that path without
production execution. It remains prohibited by this gate. Web's normal Alembic
deployment remains the sole migration owner; the Worker only waits and reads.

Independently inspected the installed Celery 5.3.4 lifecycle: `worker_init` fires
before pool/blueprint initialization, and its dispatcher catches `Exception`
but permits `SystemExit` to propagate. The receiver is limited to this app and
fails closed with exit78, including unexpected gate failures. Importing tasks
from Web does not invoke the wait. The probe imports no application settings,
task or provider modules. Its PostgreSQL transaction is read-only, uses a
non-pooled disposed connection, and applies connect/query/lock limits to the
actual probe session. The supervised child bounds driver/DNS stalls; its secret
URL is supplied through stdin, never argv or emitted errors. The monotonic120s
deadline rejects even a successful result arriving too late. No worker task or
embedded Beat starts before the gate passes.

Independently reran the exact frozen sources:

- **28 focused tests passed**,2.70s: readiness, existing schema preflight and
  conversion-worker registration. Actual Celery signal dispatch, a killed/reaped
  hung child, late success, malformed/sensitive child output and Web import
  safety are covered. Log: `/tmp/db133-independent-worker-gate-focused.log`.
- **4 PostgreSQL tests passed**,5.17s, solely on disposable
  `db133_test_merge_worker_gate_7b63b002`: effective read-only mode rejects writes;
  statement2s/lock1s limits apply; missing physical C1 columns do not unlock the
  Worker; a real lock and slow query are bounded. Log:
  `/tmp/db133-independent-worker-gate-postgres.log`.
- Captured full normalized10-table fingerprints independently before and after
  those tests: all identical. All four source hashes also matched before/after.
  Receipt: `/tmp/db133-independent-worker-gate-result.json`.

Separately reviewed the owner's disposable normal-migration lifecycle evidence:
contact175 produced `schema_not_ready` with no bootsteps; an independent normal
Alembic upgrade to176 then produced `ready` and exactly one `bootsteps` event.
The blueprint is a spy, so this proves startup ordering without consuming real
tasks or starting Beat. Its ten-table retention checks also passed. That
transition run was owner-executed; the focused and four PG reruns above were
reviewer-executed. No reviewer preview/production database connection or browser
action occurred.

**Remaining release gates:** exact final-source protected CI; normal Web-owned
migration176 and readiness; exact Web/Worker deployment identity plus actual
Worker readiness-pass/startup evidence; fresh private v3 pre receipt immediately
before release and fixed-cohort post comparison; production Light/Night desktop
and mobile acceptance. Preserve the original05:12 pre receipt and separately
report changes to a fresh pre baseline; a timestamp never proves authorization.
The independently reviewed pre-to-pre comparison passed six pure-local cases;
use a new output path to avoid overwriting either receipt. Worker timeout/exit is
a failed startup requiring investigation of Web's migration, never permission
to stamp, bypass the gate, or migrate from Worker. C1 remains not Done.

### Worker startup visibility correction — 2026-10-16

**Local QA/Security GO retained** for final four-file aggregate SHA256
`43dc8184197cee421ff37025774f72a7102edc37f2c48573ab57cb1e646e1432`.
The owner reproduced that default WARNING logging hides the two INFO readiness
messages because `worker_init` precedes Celery's logging setup. The narrow fix
emits those same fixed, secret-free messages through flushed stderr. It does not
configure global logging or change the probe, PostgreSQL session, deadline,
signal registration, task schedules or startup ordering.

Independently inspected the two-line behavior change and actual
`celery.apps.worker.Worker` regression, then reran the focused suite:
**29 passed**, 2.72 seconds, with two existing deprecation warnings. The test
requires exactly one waiting and one passed message before Celery logging setup,
unchanged global logger settings until that setup, and no synthetic credential
in output. Log: `/tmp/db133-independent-worker-gate-logging.log`. Source manifest
matched before and after. The earlier four real-PG passes and ten-table retention
remain applicable because their probe and connection code is byte-identical;
those database checks were not repeated. Exact final-source CI and production
readiness-pass/deployment evidence remain required.
