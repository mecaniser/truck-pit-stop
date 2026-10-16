# DB134 / M1 — independent QA and Security review

Status: **Review plan / no implementation or migration approval yet.**
Reviewer: independent QA/Security agent `/root/r1_independent_gate`.
Accountable implementation owner: Backend & Integrations; Frontend owns shared
UI. Product & Delivery owns browser/runtime/release and all other receipts.
Reviewer owns this file only and has not implemented or directed application or
test changes. No preview/production database connection, browser action or
provider dispatch was used for this review.

## Accepted basis and bounded stages

Read accepted contract `docs/contracts/db134-maintenance-programs.md` v1 and
DB134 receipt/board at `7024830bb71bff1e11e2a63933e016c896ee73aa`, branch
`codex/maintenance-programs`. Contract SHA256: `d1c97f862274e2d1457aef8f9fef0f75ad0ee465072f9398e1886c18695b73fa`.
The mandatory delivery/runtime skills were read. This is read-only source and
documentation work; no service startup is required. Product & Delivery's runtime
receipt is inherited context, not reviewer-performed browser verification.

No contradictory product/security requirement was identified in the accepted
contract at this stage. Concrete implementation gaps will be returned with a
reproduction, rather than broadening the agreed M1 outcome.

1. **Foundation gate:** additive migration/legacy admission, durable schema
   invariants, pure reading/due projection and authorized program/readings/history
   routes. Owner supplies a stable source manifest and a disposable PostgreSQL
   slot before reviewer probes. Root alone decides/apply preview migration after
   independent schema/retention evidence. Foundation approval cannot approve
   incomplete work/finalization/lifecycle integration or release.
2. **Integration gate:** inspect every actual work, finalization, removal,
   source-edit, vehicle-merge and restoration writer; independently rerun the
   narrow affected tests and real concurrency cases at a frozen manifest. Owner
   runtime evidence must cover complete shared customer/fleet journeys before
   a full local GO. No duplicate unrelated suites or simultaneous database resets.
3. **Release closure:** exact protected CI/tree, Web migration and dynamic Worker
   gate/deployment identity, fixed pre/post financial and legacy retention,
   authenticated Light/Night desktop/mobile evidence and cleanup. No fabricated
   production schedules, pricing activation, invoices or provider actions for QA.

## Independent acceptance plan

| Boundary | Bounded proof and negative cases |
|---|---|
| Schema and legacy admission | Upgrade from exact176 on disposable PostgreSQL; defaults-only vehicle remains unenrolled, explicit target/package admits one deterministic adapter, imported interval0 and ambiguous/multiple PM operations remain unresolved. Repeat upgrade does not duplicate adapters/events. Preserve all old scalar/package/financial rows. Populated downgrade refuses evidence loss. |
| Durable integrity | Cross-tenant composite FK rejection; event/version and occupying-cycle uniqueness; reject UPDATE/DELETE of event/completion/reading evidence and changes to captured link identity/configuration; historical operation/template deletion does not erase evidence or create a restrictive FK failure. State mutation must have its event. |
| Authorization and privacy | Exercise every ID/filter/token/source against wrong tenant; current fleet membership and correct order scope, including membership loss; receptionist cannot manager-attest/rebaseline/outside-recognize; mechanic only its existing linked-operation scope; denied roles gain no routes. Current authorization must precede replay. Owner-to-fleet response reduction and hidden outside source must not expose cost, provider, actor/private notes or cached private responses. |
| Validation and projections | Unknown/forged tenant, actor, price or source-value fields rejected; strict booleans/integers, finite bounded decimals and explicit0 accepted appropriately. No-store headers; filters/scope before total/count/paging and escaped search. Safe error tokens carry no private payload. |
| Readings and due | One server as_of; shop midnight/DST date arithmetic, due0/overdue-negative, known overdue outranks another unknown, active work does not mask due. Check missing/stale/captured-only/future/wrong-VIN/membership/regressing observations, virtual or unspecified hours, source date agreement and date-only precision. Manual readings do not mutate provider/Vehicle mileage; telemetry never resets targets. Completion snapshot survives source purge. |
| Program changes | Rename without target token; preserve interval targets; enabled-dimension changes require reviewed targets. Active/pending/review configuration conflicts; template archive blocks new work while retained history/completion remains usable. Program archival cannot discard unresolved claims/review. |
| Shared work and financial boundary | Two independent programs plus a multi-service legacy package share one selected service/operation where explicit, with exactly one bundle charge and one cycle claim per program. Existing attachment preserves hours/rates/parts/checklists/reservations; same-service ambiguity cannot create duplicates. Review aggregate P1/C1 token/recovery and correct payer, stock adapter and downward projection; injected late failure rolls back order, usages/movements/cores, claims and durable receipt. Retained-only mapping is independent of today's catalog policy. |
| Completion and evidence | Both manager routes; technician alone cannot advance. All enabled readings or none of that program's targets advance; A-valid/B-pending; old clients omitted block creates pending without blocking ordinary finalization. Explicit duplicate/missing/wrong link and stale source reject before invoice/stock writes. Resolve pending once; recognize only eligible same-truck completed/invoiced/paid or authorized active outside source, never infer actual reading from today's odometer. Older history-only, equal-date ambiguity and duplicate source identity stay deterministic. |
| Lifecycle and correction | Inventory actual callers for labor/PriceBuild removal, PM replacement, order cancel/delete/restore/reopen/void/recomplete, source update/void/restore and vehicle merge. Shared operation removal releases every affected unperformed claim atomically; whole legacy cycle mapping stays coherent. Restore cannot steal a newer claim. Controlling evidence invalidates to review, never silent rewind; reaffirm/supersede/revoke acknowledges exact later links without repricing or reusing cycle numbers. |
| Concurrency and receipts | Real transactions: competing claims, first-program/reading versus merge, source edit versus recognition, config versus completion and order-price edit versus attachment/finalization. Check canonical lock order, no deadlock/inverse path, no completed receipt on rollback, strict same-key semantic conflict and no double advance independent of receipt retention. Existing whole finalize API is not claimed idempotent. |
| Frontend/runtime | Root executes Light/Night1280+,390/320 and740×400: enroll/edit/inline preview/shared work/finalize-pending/resolve/history plus Cancel/Back/reload. Verify clear scope/actual readings, no duplicate P1/C1 confirmation, draft persistence after60s refresh, focus/Escape/named close, no overflow/unwrapped actions and one active mobile content scroll. Reviewer inspects representative actual captures and affected component tests. Browser emulation is labelled; no physical-device claim. |

The first independent test run will target foundation cases only after a stable
handoff. Full CI remains the repository integration gate; these checks do not
replace it. Existing correct financial or access behavior is an invariant, not
an invitation to redesign unrelated finance/import systems.

## Early evidence-helper review — 2026-10-16

`/tmp/db134-preview-retention.py`, SHA256
`0d13ce82969ea3526cefa5f24a0861664e81dbdb646eb1720c2349598c6f22b4`, was read
without executing its capture path. Capture is hard-bound to the named local
preview database in `dieselbridge_postgres`, uses repeatable-read/read-only,
static table identifiers, statement/lock timeouts and returns count/hash only.
The preserved receipt has exact schema176, read_only on and28 table entries.

**Finding1 — comparison metadata was not validated (closed below; release-evidence
helper only).** Using temporary local copies of that receipt, changed the post
metadata to `read_only='off'`, `receipt_version=999` and
`schema=['unexpected_revision']` without changing its table hashes. The helper
exited0 and reported `all_original_rows_unchanged`. This is correctly a row-hash
comparison, but it is insufficient by itself as proof of an authorized exact
migration/read-only receipt. Return condition: reject malformed receipt
version/read-only/schema and required count/hash shape, with explicit expected
before/after revisions, or independently and explicitly bind those checks into
the migration gate. Reproduction used zero database connections. Returned to
Product & Delivery; reviewer made no corrective helper/source edit.

No application finding or foundation GO is asserted from this early review.


### Finding1 closure / comparator-only GO

Root corrected the helper; reviewer did not edit it. Final SHA256
`7ed2dbb2d41b3738bbd1d50c57c511a96a47c8a3921954daab2ae8d2066dbd17` now
requires explicit before/after revisions and validates exact receipt keys,
version1 as an integer, read-only on, named database and exact schema, all28
tables with nonnegative integer counts and64-hex hashes, timezone-bearing
observation timestamps and monotonic capture order. Capture also invokes this
validator before emitting its receipt.

Independently ran16 connection-free CLI cases: valid receipt accepted; changed
hash returns requires_review/exit2; wrong or missing schema, read-write metadata,
wrong/Boolean version, wrong database, naive/backward timestamp, missing table,
Boolean/negative count, malformed hash, extra field and omitted expected
revisions rejected. Evidence: `/tmp/db134-independent-helper-validation.json`.
**GO for this bounded comparator use**, not for the pending migration or M1
application. Root must supply the actual reviewed post-migration revision; none
was invented or applied by this review. Foundation and all later gates remain
open. Review plan is frozen pending the implementation handoff.


## Production-retention helper draft — bounded review

Reviewed `/tmp/db134-production-retention-draft.py`, SHA256
`e01d0bb07e722b7dd7d4286c7c214dff7ddf4dde6e2abfe19abbf8cb4bcb22c8`.
No capture path or application imports were executed. Using the owner's local176
receipt and synthetic post metadata only, independently passed28 connection-free
comparison cases: valid matching cohorts; reject wrong revision/phase/read-only/
isolation/version/database/baseline/cutoff/timing, reduced field scope or row
bound, missing cohort/table/count, Boolean counts and malformed hashes; report
missing/late/changed original rows and nonzero independent-program/completion/
reading adoption. A recent updated_at does not excuse a changed protected hash;
a timestamp-only change is reported separately. Evidence:
`/tmp/db134-independent-production-helper-draft.json`.

**Finding2 — missing payment retention cohort (closed below).** The accepted migration
clause explicitly requires payment fingerprints. The draft protects ten cohorts
but omits `payments`; therefore a payment amount/status/invoice ownership or
refund/fee change is outside this comparator and can coexist with its green
result. Returned to Root to include the scoped payment fields or supply separate
reviewed payment-retention evidence. **No release-retention GO** until this scope
gap closes. The comparator's existing fixed-cutoff/original-row and metadata
checks passed the bounded tests; those passes do not validate eventual177
physical schema, deterministic legacy enrollment, or complete application/UI
behavior. Actual schema/content gates remain pending the Backend handoff.


### Finding2 closure / production-retention comparator-only GO

Root added payments, inventory and core-obligation protected fields. Final helper
SHA256 `592372ecfb5ad5694a2f371c50c389d48cc5c8ac23b95cb39ed567023d298c56`
now requires13 cohorts. Payment protection includes invoice/tenant identity,
amount/method/status, provider fee/refund and attempt linkage plus soft deletion;
inventory includes stock/cost/price/policy versions and core obligations retain
quantity/value/status and source linkage. These fields are hashed, not emitted as
raw financial/provider values. The fresh owner-captured LOCAL176 receipt contains
2,225 payments, 1,334 inventory rows and zero core obligations.

Independently passed15 narrow connection-free cases on that fresh receipt:
matching13 cohorts accepted; changed/deleted payments and inventory require
review; missing payments/core cohorts and tampered payment amount scope (including
both receipts) rejected; a late pre-cutoff core row requires review; wrong
baseline/cutoff/revision/read-write metadata rejected; independent adoption
requires review. Evidence: `/tmp/db134-independent-production-helper-v2.json`.
The earlier28-case mechanics review remains applicable to unchanged comparison
logic. **Finding2 closed; GO for bounded production-retention comparator use.**
This is not permission to capture production, apply177, or approve M1. Exact
schema/content/legacy conversion, deployed identity and application/runtime gates
remain open. No capture path, database connection or migration was executed by
the reviewer. Receipt frozen pending the foundation handoff.


## Frozen schema foundation review — initial candidate

**NO-GO for preview migration pending Finding3.** Reviewed only migration/model
scope, not the unfinished service/API/UI. Exact source hashes:

- `177_maintenance_programs.py`: `9785054d95cab4d80fc5e2b9d273d94eb0d1f8984021a3b057fcbc65c2dd360c`.
- `models/maintenance.py`: `353051f16350f0e3de9ddb7058096b41fdac85907c05c14b92015f0d2a88d6a5`.
- `models/repair_order.py`: `a1d8d8609fbc353ffc96bdc2f3adfd66177f17ddfb7a3872ac2a4dc50c8ed3cd`; bounded delta is the same-tenant identity index for work-link FKs.

Reviewed the owner's disposable migration runner/result: exact176→177 and
repeat upgrade, empty downgrade/upgrade and populated downgrade refusal;
28 original-table hashes retained; six explicitly admitted legacy variants,
one claim/two operation mappings/six events and zero readings/completions.
Defaults-only is unenrolled, package order is retained and imported0 is recorded
raw with null projected interval/review. Ambiguous/unmapped active work is held
for review rather than assigned invented evidence. These are owner-run migration
proofs; the independent run below tests the resulting schema without resetting
or re-running migrations.

Independently ran21 PostgreSQL probes on the coordinated, allowlisted disposable
`db134_test_m1_migration_2d09213f`: **20 passed / one failed**. Program/link/
operation identity, immutable evidence update/delete, missing corresponding
event, active-cycle uniqueness and cross-tenant FK checks reject as expected.
Explicit0 reading is accepted; NaN is rejected. Existing recognition-key
uniqueness rejects a duplicated nonnull key. All probe writes were rolled back;
full hashes of28 original plus six M1 tables are identical before/after. No
preview or production connection occurred. Evidence/script:
`/tmp/db134-independent-schema-probes.json` and
`/tmp/db134-independent-schema-probes.py`.

**Finding3 — durable completion uniqueness depended on an optional key (closed below).**
Migration `maintenance_completions` has only
`UNIQUE(tenant_id, program_id, recognition_key)` for source durability;
`recognition_key` is nullable. Two `finalize`/`advanced` rows with the exact same
program, cycle, work link and RO source, separate request IDs and null key both
succeed, including deferred-constraint validation. Contract section3/8 requires
link-finalization and source/program uniqueness independently of receipt
retention. This schema permits duplicates despite that invariant. Backend owns
the correction and has acknowledged it; no reviewer implementation edit was
made. Return condition: frozen corrected schema and disposable migration proof,
then repeat the relevant null/different-key link/source cases alongside valid
pending→resolution/correction evidence. No migration GO is implied by the20
other passes. Disposable slot released to Backend after rollback verification.


### Finding3 closure / bounded schema-foundation GO

**Independent GO for Root's backed-up local preview176→177 migration and
subsequent retention check only.** Corrected frozen migration SHA256
`ab8513967a6400cbe238cb83c1a67a7a4af78866202a32caf43034b319618432`, model
`9e7770b2cfb4f1a83ca31a3afb1fc4300843a681ba1b8645465c03f9f465738a`;
repair-order model remains
`a1d8d8609fbc353ffc96bdc2f3adfd66177f17ddfb7a3872ac2a4dc50c8ed3cd`.
The migration and model agree on explicit partial uniqueness for initial
finalize/pending evidence per work link, one pending resolution per link, and
initial source/program evidence across finalize/pending/recognize. Required
source/work/cycle checks prevent null identities from bypassing those indexes.
The optional recognition key is no longer their only enforcement mechanism.

Independently reran and expanded the schema probes on new disposable
`db134_test_m1_migration_40b35377`: **36/36 passed**. The original null-key
reproduction now fails with23505, as do changed-key duplicates, pending followed
by a second initial finalize, repeated pending resolution and recognition versus
finalization for the same source/program in either order. Missing work/source/
cycle and invalid recognition source are rejected. Initial pending followed by
one resolution is allowed; separate reaffirm/supersede/revoke evidence remains
insertable. These positive checks establish schema compatibility, not the
unfinished service's authorization or correction-chain behavior. Prior tenant,
identity, event-required, immutable evidence,0/NaN and active-claim cases also
pass. All writes were rolled back and all34 original+M1 table hashes remain
identical. Evidence: `/tmp/db134-independent-schema-corrected-probes.json` and
its corresponding `.py` script. Source hashes matched after the checks.

Reviewed the refreshed owner migration logs/result: actual176→177, repeated
upgrade, empty down/up and populated downgrade refusal; all28 old-table
fingerprints retained, six legacy programs/six admission events, one claim/two
mappings, no readings or completions. Root still owns the actual preserved
preview migration and exact pre/post28-table check; no reviewer preview or
production action occurred. The disposable slot is released.

This gate approves only the frozen additive schema/model foundation and closes
Finding3. It does **not** approve exposing incomplete maintenance controls,
application/API tenant behavior, work/completion/lifecycle writers, UI journeys,
CI, production migration or release. Those remain explicitly open until their
own coherent source/runtime handoff. Once independent programs exist, old
unguarded scalar writers are not a safe rollback; retain maintenance guards or
pause affected writes as required by the contract. Review receipt frozen pending
that later integration handoff.


## Reading/configuration source checkpoint — two returned defects

Reviewed the current pure rules plus program/readings/configuration preview,
CRUD/history and idempotency middleware. Work creation, finalization/evidence
commands and lifecycle integration remain unfinished and were not gated. This
is a non-frozen source checkpoint; manifest captured at review conclusion in
`/tmp/db134-independent-foundation-review-manifest.json`, not an exact final
candidate approval. No broad test suite was repeated.

**Finding4 — nested outside-service identity leaks to Fleet (closed below).**
`completion_view` correctly hides outer `source.id/can_open` for a Fleet manager,
but returns raw `row.readings`; `current_readings` also republishes the controlling
completion's reading provenance. After an owner-recorded outside-service
completion, Fleet history and program due both disclose that private source UUID
through `readings.*.source_id`. Reproduced with an authorized current Fleet member
and a synthetic completion: outer source.id is null yet the same hidden source
UUID remains in the serialized history/page. Contract requires safe outside
summary without private source link; projection must cover nested provenance,
not just the outer source object. Returned to Backend.

**Finding5 — same-day rebaseline does not isolate previous meter generation
(closed below).** Created a program at confirmed110,000, recorded a120,000 observation,
then performed a manager rebaseline on that same shop date to actual1,000 after
meter replacement. Save correctly sets target2,000, but the previously recorded
120,000 still wins the due projection. `current_readings`/`choose_observation`
filter by date, while the advanced baseline generation does not exclude that
prior observation. This can falsely mark the new meter overdue, contrary to the
contract's no subtraction across rebaseline generations. Returned to Backend
with the exact sequence and expected isolation of the older reading.

Independent reproducible evidence: `/tmp/test_db134_independent_foundation.py`
and `/tmp/db134-independent-foundation-probes.log`; two focused assertions fail
in5.03seconds using fresh in-memory SQLite fixtures and autoflush=False. Synthetic
setup writes affect only those disposable fixtures. No existing app/test file,
preview/production database, provider or browser was changed. Source-identity
redaction and same-day generation handling need owner correction and focused
regressions before a CRUD/configuration GO. Prior schema-foundation GO remains
limited to its frozen migration/model proof.

A separate source observation was passed to Root/Architecture, without claiming
an additional reproduced failure: native RO-selected mileage currently takes
mileage_out, which existing fleet finalization can populate from Vehicle.mileage.
The eventual source/attestation contract must preserve its explicit distinction
between actual service evidence and automatic odometer fallback. This review
will resume on the coherent corrected handoff.

### Findings4/5 closure — bounded correction GO

**Independent QA/Security GO for these two corrections only.** The reviewed
helpers are `safe_readings`, `current_readings`, `program_view`,
`program_command` and `completion_view`. Their source-segment hashes are recorded
in `/tmp/db134-independent-finding45-correction-manifest.json`; the aggregate
SHA256 of the sorted function-hash map is
`a048cff1ebb352936ffacc8bc7935f3f099416d3bd35249ee9b02dbc2a191d6d`.
This identifies the bounded correction while later service integration remains
under active development; it does not assert a frozen whole-file candidate.

Fleet projections now deep-copy the readings and remove nested service-evidence
source IDs in both history and current due data. The saved evidence and Shop
projection retain their provenance. Rebaseline and legacy conversion now record
a `comparison_reset_at` boundary; observations captured or observed before that
boundary are excluded before the separately confirmed baseline is considered.
Ordinary target changes preserve that boundary. A legitimate subsequent reading
is still selected, so the correction does not permanently suppress new data.

Independent verification:

- Original two reproductions now pass: **2 passed**, 3.08s;
  `/tmp/db134-independent-foundation-corrected.log`.
- Expanded independent cases also pass: **2 passed**, 3.61s; Fleet history/due
  redact the nested ID, stored evidence and Shop history retain it, and a new
  post-reset1,100 reading produces900 remaining against the2,000 target.
  `/tmp/db134-independent-foundation-expanded-correction.log` and
  `/tmp/test_db134_independent_foundation_corrected.py`.
- Independently ran the owner's two named regression cases for same-day
  generation isolation and nested Fleet projection: **2 passed**, 2.21s;
  `/tmp/db134-independent-foundation-owner-correction.log`.

These checks use fresh in-memory SQLite fixtures with autoflush=False. No
preview/production database, PostgreSQL fixture, browser, provider or app/test
source was changed by this reviewer. The owner's broader110-case result was
reported separately and is not represented here as an independent run.

Findings4/5 are closed. The legacy recognize-PM exception and the prohibition on
using raw RO arrival/mileage-out as actual service readings are now clarified in
contract section9, but their unfinished implementation is outside this gate.
The work/evidence/finalization paths, coherent full API integration, actual UI,
CI and release acceptance remain pending. Prior schema GO retains its original
scope. Review receipt frozen for handoff.

## Section9 legacy adapter review — returned for correction

**NO-GO for the current legacy recognition integration.** This review covers
the old recognize-PM adapter and native order reading selection only. Work,
finalization and new evidence routes remain outside the gate. Exact reviewed
function/class hashes and source lines are captured in
`/tmp/db134-independent-legacy-review-manifest.json`; the rest of the service is
still evolving. Prior migration and Findings4/5 gates retain their narrow scope.

**Finding6 — older legacy recognition can replace newer controlling M1 evidence
(closed below).** `api/v1/endpoints/fleet.py:2501–2513` decides whether to advance solely
from other native orders marked `is_pm`. New M1 recognition is explicitly
required to retain the source's original flag. With a newer controlling
completion at100,000 and its native source still `is_pm=False`, recognizing an
older order at90,000 returns `schedule_advanced=True`, changes target125,000 to
115,000, replaces the controlling completion and increments the cycle. The
program's newer controlling evidence is available but is not included in that
decision. This violates section9 older-history protection and section8
history-only semantics. Independent reproduction seeds valid newer evidence
through the existing adapter helpers without editing the native source, then
calls the public legacy route function for the older order. Expected: append
history-only evidence and retain the controlling identity/cycle/targets/scalars.
The separate case with a newer source already marked `is_pm=True` passes.

**Finding7 — server-day check rejects a valid shop-local date (closed below).**
`api/v1/endpoints/fleet.py:2460` still checks `date.today()` before the new
shop-timezone validation. At2026-10-16T22:00Z in Australia/Sydney, performed_on
2026-10-17 is the current shop day, but the route returns400 before reaching the
valid attestation. Expected: validate using the persisted shop timezone as
required by section9, while retaining actual future-date rejection. Reproduced
with explicit clock substitutions and a fresh synthetic tenant.

**Finding8 — legacy reading wire accepts coercions and overrange input (closed below).**
`schemas/fleet.py:351–355` still uses a permissive BaseModel and `int` with only
a lower bound. It accepts booleanTrue, string`"100"`, float100.0,100,000,000 and
unknown actor_id. Section9 requires strict reading bounds; section2 forbids
unknown fields/coercion. The overrange request passes the route schema and then
raises an uncaught Pydantic ValidationError in
`services/maintenance.py:767`, rather than returning request-validation422.
This is not an observed production500; the independently exercised handler
raises the unhandled exception. Expected: strict supported request input and
normal422 rejection before any mutation; explicit integer0 remains valid.

Evidence and controls:

- Independently reran the owner's five native-meter/legacy tests: **5 passed**,
  4.48s, `/tmp/db134-independent-legacy-owner-tests.log`. Raw arrival/fallback/
  apparently manual native output is rejected as selected actual evidence;
  manual0 with date precision succeeds without changing the native readings.
- Expanded independent probes: **12 passed / 8 failed**,7.09s, in
  `/tmp/db134-independent-legacy-review-final.log`; script
  `/tmp/test_db134_independent_legacy_review.py`. Eight failed assertions map to
  the three findings above. Passing cases cover active/pending/review claims,
  program review, receptionist/mechanic/driver denial, foreign/deleted source,
  ended membership, lower-reading refusal and existing flagged-PM older history.
  Refusals retain source/scalars and create no completion; successful
  history-only behavior retains the newer targets/cycle/controller.
- The first probe run had three temporary fixture-field errors; these were
  corrected only in `/tmp` and are not application findings. The final20-case
  run has no fixture errors. All writes used fresh in-memory SQLite with
  autoflush=False. No PostgreSQL fixture, preserved preview, production,
  provider, browser, application source or repository test was changed.

Returned all three findings with reproductions to Backend and Root. Corrected
frozen functions plus focused regression evidence are required before closing
this bounded gate. The owner's separate three PostgreSQL concurrency/CAS/
append-only tests are not represented as reviewer-run evidence. Full feature,
actual UI, protected CI and release gates remain open. Review receipt frozen
pending the correction handoff.

### Findings6–8 closure — bounded legacy correction GO

**Independent QA/Security GO for these corrections only.** The original20
independent probes now all pass in17.34s. Evidence:
`/tmp/db134-independent-legacy-corrected.log`, using the unchanged independent
reproduction file `/tmp/test_db134_independent_legacy_review.py`.

Reviewed the corrected source: existing legacy adapters are retained during
recognition instead of resynchronized over their controlling provenance;
advancement is suppressed when controlling M1 evidence is newer, and the
response/history message follows the recorded evidence result. The old server
date guard is removed, allowing the existing shop-timezone attestation check to
decide actual future dates. The legacy request now forbids unknown fields and
requires a strict integer odometer within0–99,999,999, so invalid types and the
previous uncaught overrange input fail request validation.

Four additional independent boundary cases and the five prior owner regression
cases also pass: **9 passed**,6.69s;
`/tmp/db134-independent-legacy-correction-boundaries.log` and
`/tmp/test_db134_independent_legacy_correction.py`. An actual shop-future date
returns422 without source/scalar changes and rolls back provisional enrollment.
Older evidence retains the controller, cycle and completion provenance; a
different source on the same date returns409 without changes; legitimate newer
service advances once to the expected target. Native order readings remain
ineligible as selected evidence; explicit manual0/date-only precision and
duplicate/independent-program guards continue to pass.

Seven reviewed function/class hashes are captured in
`/tmp/db134-independent-legacy-corrected-manifest.json`, aggregate SHA256
`bc35801c451d9cd86eb39d273f81b1071c8eacbf66384cb4f916ed856760460b`.
This is a scoped source identity, not a frozen whole-service or release SHA.
All independent writes used fresh in-memory SQLite with autoflush=False; no
PostgreSQL, preserved preview, production, browser, provider or application/test
source was changed. No duplicate schema/privacy suite was run.

Findings6–8 are closed. Full work/completion/evidence integration remains outside
this review and unapproved, as do complete actual-UI, protected-CI and release
acceptance. Receipt frozen for the next coherent integration handoff.
