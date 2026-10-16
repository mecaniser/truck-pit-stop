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
