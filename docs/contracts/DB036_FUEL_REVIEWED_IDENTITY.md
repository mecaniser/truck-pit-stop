# DB-036 fuel reviewed-identity reconciliation contract

Architecture decision: **GO for the narrowly scoped fuel extension below.** Existing fuel rows remain immutable. This contract does not approve implementation, migration execution, deployment, or production imports; independent QA/Security and runtime gates remain mandatory.

Backend & Integrations owns this extension; Release & Reliability owns the migration and release. This is within the user's request to resolve source-backed fuel exceptions without invented VINs, membership backdating, duplicates or verified-row overwrites. It is not permission to create a new binding, generalize placeholder matching, or promote a changed source reading.

## Grounded candidates and exclusions

The existing reviewed binding identifies provider `5981300`, company `KT8934277` / `77 CARGO LLC`, local truck 26 / placeholder `PENDING-26`, current fleet and membership. Read-only evidence shows it is unrevoked/undeleted, reviewed and effective from October 16, 2026 21:42:51.108657 UTC, with no end; current membership begins October 7. Revalidate these facts under the importer lock at write time; this note is not a substitute.

October 26 and 27 have saved reported fuel and are candidate repair dates. Their entire conservative report intervals and original/new source-read instants must be after the binding and membership start and before any ends. August 15/17/18 reported readings predate the binding and remain excluded. August 16 and October 25 explicit no-results observations do not justify a row or zero.

The retained legacy fuel captures contain `vin:null` but lack the trip collector's explicit reviewed source-VIN before/after evidence. **Do not manufacture that evidence retrospectively or rewrite their source/normalized intent.** Use fresh complete source capture with the reviewed identity proof below after any uncertain old receipts are reconciled.

## Additive database identity

Keep the existing unique source key `(tenant_id, provider_company_id, provider_vehicle_id, report_date, source)` and all membership/tenant foreign keys. Do not backfill, alter or delete existing values.

Add nullable `dashboard_binding_id`, `source_company_label`, and `source_vin_state`; allow `verified_vin` to be null only under a strict identity XOR:

- Existing path: verified VIN non-null; all new binding/provenance fields null.
- Reviewed path: verified VIN null, binding ID non-null, company ID exactly KT8934277, label exactly 77 CARGO LLC, provider exactly 5981300, and source VIN state exactly `not_displayed` or `explicitly_empty`.

Add the same composite binding foreign key shape used by trips: tenant, vehicle, membership and binding ID. Application/import/read validation must also match fleet, provider/company/label, placeholder and the actual binding row. No `PENDING-26` value is ever stored in `verified_vin`.

Migrate from the current sole head using the next available revision, preserving existing rows. A downgrade must fail safely if bound fuel rows exist rather than deleting data or coercing a fake VIN. Record schema compatibility and rollback limits; old VIN-only workers cannot recover new bound intents and must fail closed rather than reinterpret them.

Migration integrity must freeze the pre-migration projection. PostgreSQL `to_jsonb(row)` gains null keys when columns are added, so compare an explicit original-column projection, or subtract exactly the three new identity keys, for the full original 716-row cohort and original 675-row subset. Preserve IDs, values, created/updated/captured timestamps and digests. Do not call JSON-shape changes a data mutation or compare incompatible whole-row digests.

## Private import and digest compatibility

Keep `FuelDailyImport` and public/manual import genuine-VIN-only, including their current serialized shape and digest. Use a separate private reviewed import type and an explicit `allow_binding=False` default guard, mirroring trips. Do not add null default fields to the base VIN model if that changes old serialized payloads/digests or receipt recovery. Direct importer callers must revalidate the entire typed batch with the same private guard.

The bound branch resolves the exact existing binding through the reviewed binding service under the current tenant/actor authorization and import locks. Validate current vehicle/member/customer, no deletion or revocation, exact fleet/company/provider/label/binding, placeholder unchanged, uniqueness and full coverage of:

- conservative report interval (unverified timezone remains null, with existing midnight UTC minus 14 hours through next date noon UTC semantics);
- source read time; and
- current read/import time, as required by existing binding and membership visibility rules.

Never extend binding or membership intervals. Reject a foreign tenant/company/fleet/provider, inactive actor, changed/revoked binding, deleted vehicle, ambiguous membership, genuine VIN appearing on a formerly missing-VIN provider, or pre-binding date. Existing trip and fuel identity history must not contradict the reviewed binding; the bound branch must not run the VIN-only history comparison against a null VIN.

Keep exact replay unchanged with original saved IDs. Identity/provenance changes and changed measurements conflict; never update an existing fuel source key or redirect it to a different vehicle/member/binding.

## Source and durable worker proof

Reuse the existing reviewed rendered identity reader for provider5981300 only. Require exact source summary URL/provider, unique matching rendered unit, explicit missing/empty VIN state, and stable identity before and after that provider/day's report, plus the existing complete directory/company/filter/report proof. A timeout, missing content or `vin:null` alone is not explicit no-VIN proof. Do not guess a provider from a unit label.

Retain normal genuine-VIN collection and legacy receipt validation. New proof fields are additive/version-bound and may not silently certify old null-VIN sources. Private normalized intent and receipt must carry exact binding/provenance with source/normalized hashes. Current mapping fingerprint must include reviewed binding identity, intervals, revocation and source VIN state so changed mapping reopens old observations. Do not erase old receipts or mutate their hashes.

Recover legacy and new receipts before capture under the exclusive worker lock. Orphan/ambiguous intents stop capture. Existing 0–30 minute private-plan freshness, per-day finalize, 30-minute collection budget, maximum-seven automatic planning and fairness behavior remain. New capture or two-date explicit reconciliation is permitted only for closed dates; manual windows do not reset automatic fairness.

## Read model and API

Retain the VIN path's existing visibility rules. Add an explicit reviewed-binding branch: exact tenant/vehicle/fleet/member/binding/company/provider/state, current unrevoked binding and unchanged placeholder, full report interval and source-read coverage. Binding revocation or identity/membership change removes the bound row from current authorized projection without deleting immutable history.

Return additive `vehicle_identity_basis` (`verified_vin` or `reviewed_provider_binding`) and nullable `vehicle_identity_binding_id` so the API never represents a bound placeholder as a genuine VIN. Preserve measurement meanings, date basis and partial coverage. No unrelated frontend redesign or general binding-management endpoint.

## Conflict 01 / October 26

The original stored semantic digest is valid. The later source changes idle fuel 0.7 to 9.4 gallons, total 19.4 to 28.2 gallons, and idle seconds 3660 to 50340, with no non-measurement identity change. Preserve the canonical row and both exact source observations. A deterministic append-only quarantined revision note/ledger may link tenant/company/provider/date, original row/request digest, later source/record hash and safe field differences, deduplicated by that identity and observed digest. Its status is quarantined/provider-source revision, never approved or canonical. Existing retained source files already satisfy preservation; a new database revision product/API is not required for the minimum repair and must not be invented merely to clear a count. Automatic promotion or replacement of the later measurements is NO-GO under this contract.

## Gates

Before write: independently review source proof, binding interval/current identity, exact dry plan and zero existing source keys for candidate rows. Tests cover default public guard, legacy VIN digest/receipt compatibility, positive scoped binding, cross-tenant/company/provider/fleet, revoked/changed/deleted/ambiguous identity, full interval boundaries, pre-binding August dates, genuine VIN transition, wrong/missing source proof, duplicate/replay exact IDs, conflict retention, and revoked read visibility. Migration round-trip/schema tests must preserve old row projections; downgrade with bound rows rejects safely.

Release sequence: protected exact-head CI and independent QA/Security; merged-tree parity; migration and backend/read deployment before the bound worker; exact worker modules/manifest/config proof; one legitimate fresh controlled capture/reconciliation; exact daily source/intent/receipt hashes, persisted saved-ID readback and unchanged replay; all original cohorts unchanged and total unique keys increase only by independently accepted new rows. Restore any temporary manual range to normal defaults and record it; preserve schedules/restarts/credentials. Codex automations stay off. Architecture is not the independent QA approver of this implementation.
