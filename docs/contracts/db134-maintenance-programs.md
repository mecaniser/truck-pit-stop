# DB134 / M1 — multiple recurring maintenance programs

Architecture API/data contract v1, 2026-10-16. Accountable owner: Backend & Integrations.
Product & Delivery owns scope, tracking and release. User-approved sequence: R1 → P1 → C1 → M1 → B1 → A1.

Prepared by Architecture against C1 candidate `0a193dc0e3595ec51ec3a21d7f2b15e9d36dd19a`, whose application tree equals released main `c42009e08b10003ddc2ab54e96c39a6a61be5bbd`. C1 is Done with independent production QA/Security GO. Local runtime is aligned on `codex/maintenance-programs`; schema `176_merge_contact_pricing`. Architecture completed the bounded source/schema recheck and accepted v1 with the source-reading and complete legacy-package corrections below. Product & Delivery accepts this contract for implementation; independent QA/Security and release gates remain open. Migration number is selected by Backend after checking current ancestry.

The conservative implementation choices below express the approved M1 outcome; they do not claim additional user decisions or authorize invented production maintenance/financial writes. See [tracking](../ETS_PARITY_TRACKER.md) and [acceptance/runtime receipt](../verification/DB134_MAINTENANCE_PROGRAMS.md).

## 1. Outcome, exclusions and compatibility

A vehicle can have multiple named maintenance programs, each with independent elapsed-day, mileage and engine-hour intervals. The earliest known threshold reached governs due state. Explicitly selected programs can share one service operation and one parts bundle, while keeping separate cycles, targets and completion history. Staff may use an existing eligible draft or explicitly create new work. Managers confirm actual service evidence; missing evidence never invents a reading or silently advances a target.

No automatic orders, notification/scheduling engine, calendar-month/quarter/year arithmetic, new provider integration, customer fees, persistent vehicle-specific parts override system, charge allocation, payroll, financial merge or new access grants. R1 schedule/promised dates remain separate. Existing explicitly requested finalization retains its existing invoice and notification behavior.

P1/C1 remain authoritative: saved rates, charges, cost/pricing origins, matrix revisions, checklist/execution identity and actual stock/core reservations survive attachment/reapply/lifecycle changes. Customer work stays external unless the existing payer classification says otherwise. Imported history stays source-owned and gets no invented C1 policy. All new M1 preview/evidence APIs never edit the source order's dates, mileage, is_pm flag, financial ownership or outside-service cost. The pre-existing explicitly requested legacy recognize-pm reclassification action has only the narrow compatibility exception in section9.

## 2. Wire conventions and authorization

All routes below are under `/api/v1`. Inputs forbid unknown fields; UUIDs, strict booleans and strict integers reject coercion. Decimal quantities travel as plain decimal strings and use Decimal arithmetic. UTC timestamps require offsets; service/due dates are ISO `YYYY-MM-DD` in the shop's persisted IANA timezone. No client tenant or actor fields. Reads and previews use `Cache-Control: private, no-store`.

Common types:

```ts
type UUID = string;
type Instant = string; // timezone-bearing RFC3339
// Miles: integer 0..99,999,999; service/current hours: decimal string 0..10,000,000, <=2 decimals.
type Miles = number;
type Hours = string;
type DateOnly = string;
type Version = number; // integer >=1
// Existing PartsPricing SafePrice/line availability/repair totals are reused, not redefined.
type Projection = 'shop' | 'fleet';
type ProgramRef = { program_id: UUID; expected_version: Version };
type Warning = { code: string; message: string; program_id: UUID | null };
type Page<T> = { schema_version: 1; items: T[]; total: number; has_more: boolean };
```

Route ownership: one new `api/v1/endpoints/maintenance.py` delegates to one transaction-owned maintenance service. Shared request/response types live in `schemas/maintenance.py`; existing fleet/RO/source endpoints call its narrow hooks rather than duplicating the state machine.

Permissions reuse current boundaries:

| Operation | Allowed role and exact resource scope |
|---|---|
| Customer-vehicle program read, planning/configuration, current readings | garage_owner, garage_admin, receptionist; same live tenant vehicle, using the private staff vehicle scope already used by `external_service.load_vehicle`/customer workspace. |
| Fleet program read, planning/configuration, current readings | fleet_manager plus owner/admin; same tenant **current membership** predicate from `_get_fleet_vehicle`. House-account ownership alone is not membership. |
| Manager service evidence, correction, rebaseline and historical recognition | owner/admin; fleet_manager only for its existing vehicle/RO membership scope and accessible native RO sources. No new receptionist finalization power. |
| Outside-service recognition/details | owner/admin only for M1 acceptance; current outside-record scope/version checked. Do not give fleet roles private provider/cost/receipt access. |
| Linked operation summary | mechanic only through its existing authorized order/operation scope. No program configuration or independent history API. |
| Customer, driver, super_admin without a permitted tenant role, unknown roles | No new management access. Public quote/PDF/customer events gain no maintenance evidence. |

Owner/admin may request either UI channel. Receptionist uses shop. Fleet manager uses fleet; asking for shop is403. Channel chooses authorized workflow/projection, not pricing classification. Check both vehicle and target/source-order scope, including on replay; customer_id in a URL/filter never grants access. Wrong tenant, inaccessible/deleted source or inaccessible vehicle returns404 without identifying the hidden object. A safe summary may say “Outside service” without a private source link. No money, provider documents, private notes or actor identities in fleet/mechanic summaries unless an existing endpoint already authorizes them.

## 3. Minimal persisted state

Names are proposed; responsibilities and constraints are binding on promotion. Use six small data roles, not separate workflow subsystems.

1. **maintenance_programs**: id/tenant/vehicle; name (trimmed1–120); version; mode `independent|legacy`; intervals; absolute targets and their provenance; optional service identity plus immutable display snapshot; current_cycle (>=1); baseline generation/source; controlling completion ID; review state; archived_at; created/updated actor/time. Independent mode has at least one enabled interval. Initial due targets may be unknown; no guessed zero or current+interval. Names need not be unique; UUID identity is authoritative. Legacy configuration snapshots additionally retain the full ordered service-ID/display-snapshot package.
2. **maintenance_program_events**: append-only tenant/program/version/action/actor/time/reason and before/after snapshots. Unique `(tenant,program,version)`; one event per program mutation, including lifecycle hooks. No generic configuration revision engine.
3. **maintenance_work_links**: tenant/program/cycle/exact RO; immutable captured configuration/targets/program version; mutable state/version; timestamps. States `active|pending_evidence|review_required|completed|detached`. Partial unique `(tenant,program,cycle)` for the first three states. Completed links retain durable source uniqueness and are never reused as a new cycle. Any unresolved controlling review blocks new claims/advancement, not operating on or paying an already linked order. Legacy configuration snapshots additionally retain the full ordered service-ID/display-snapshot package. The one legacy program/cycle work link can map to several distinct operations.
4. **maintenance_operation_links**: tenant/work_link/operation UUID, immutable operation/service/checklist identity snapshot; active/detached lifecycle projection with events. Unique `(tenant,work_link,operation_id)`. No global unique operation constraint: explicit shared coverage is supported. IDs/snapshots do not change when a source operation is physically deleted.
5. **maintenance_completions**: append-only evidence/action/result, tenant/program/cycle/work_link when applicable, actual performed date, actual readings/provenance, source kind/UUID/fingerprint, captured configuration, old/new targets, supersedes ID, actor/time/request identity. Immutable evidence; corrections append. Durable uniqueness for source+program recognition and link finalization prevents double advance independently of receipt retention. A correction refers to the original evidence chain, not a second recognition identity.
6. **maintenance_readings**: append-only current manual observation, tenant/vehicle, observed/captured time, miles/hours, `staff_observed|staff_reported`, optional note<=500, actor and request identity. At least one reading. Does not mutate Vehicle.mileage or provider data. No meter registry; a program's confirmed rebaseline generation establishes the comparison boundary.

Use composite same-tenant FKs among durable M1 rows and retained vehicle/order identities; preserve existing soft-delete semantics. **No restrictive FK from historical operation/template/telemetry pointers to physically removable rows.** At append, server loads and validates exact scoped source, records immutable UUID/snapshot, and later historical IDs never authorize a lookup. Events/completions/readings reject UPDATE/DELETE at the database layer, following existing P1 evidence patterns. Live link state may change only with a corresponding event; its captured identity/configuration cannot.

Reuse `PartsOperationIdempotency` storage (`m1_program`, `m1_reading`, `m1_work`, `m1_evidence`, `m1_detach` families) and existing fingerprint/advisory-key helpers. Store outcome identities and reconstruct a currently authorized projection; don't cache private response bodies for later weaker roles. No new queue, receipt service, retention daemon or automatic action task.

## 4. Reading and due semantics

```ts
type Intervals = { days: number | null; miles: number | null; engine_hours: Hours | null };
// days1..36,500; miles1..99,999,999; hours0.01..10,000,000; >=1 non-null.
type Targets = { due_on: DateOnly | null; odometer_miles: Miles | null; engine_hours: Hours | null };
type Meter = 'odometer_miles' | 'engine_hours';
type MeterObservation = {
  value: string; comparison_value: string | null; unit: 'mi' | 'h';
  source: 'motive_api' | 'motive_dashboard_manual' | 'maintenance_manual' | 'service_evidence';
  basis: 'calibrated' | 'virtual' | 'dashboard_unspecified' | 'staff_observed' | 'staff_reported' | 'service_confirmed';
  observed_at: Instant | null; observed_on: DateOnly | null;
  observed_precision: 'second' | 'minute' | 'date' | 'unknown'; captured_at: Instant | null;
  source_id: string | null; freshness: 'fresh' | 'delayed' | 'stale' | 'unknown';
  admission: 'accepted' | 'stale' | 'unverified_basis' | 'regression' | 'identity_mismatch' | 'missing_time';
};
type TriggerState = 'disabled' | 'current' | 'due' | 'overdue' | 'unknown';
type DueState = 'current' | 'due' | 'overdue' | 'unknown';
type DueProjection = {
  state: DueState; // independent of work state
  date: { state: TriggerState; target: DateOnly | null; remaining_days: number | null };
  miles: { state: TriggerState; target: Miles | null; remaining: number | null; reading: MeterObservation | null };
  engine_hours: { state: TriggerState; target: Hours | null; remaining: string | null; reading: MeterObservation | null };
  needs_reading: Meter[]; needs_baseline: ('date' | Meter)[];
};
```

Take one server `as_of` per response. Date remaining is target minus shop-local date, not elapsed seconds/24h; DST changes cannot turn one calendar date into two days. Independent next date = confirmed performed_on + elapsed calendar days, without Saturday rounding. Miles/hours use matching units and confirmed actual service values. No conversion from miles/hours into a date. Arithmetic overflow returns422.

Retain the original source value as value. DBN's whole-mile domain uses floor(value) as comparison_value, matching current apply_pm_mileage; hours use Decimal truncated downward to0.01h. Display the normalized service value in target preview before actual-service confirmation and retain both values/provenance in evidence; do not silently describe a normalized value as the exact provider reading. Manual values already use those supported precisions. This is deterministic display/domain precision, not a forecast or invented reading.

Zero remaining is due; negative is overdue. Any known overdue trigger wins, then known due; otherwise any enabled unknown trigger makes aggregate unknown, and only all enabled known positive triggers are current. Display overdue and current-work state together. Active work never masks an overdue threshold. A stale accepted reading already beyond a target may establish that the threshold was crossed, absent a meter reset/review; it cannot establish that a program is still current.

Preserve existing `NumericReading` source, basis, observed/captured times, membership/VIN mapping and source age. Current automatic mileage may admit the existing dashboard-unspecified manual mileage or calibrated API mileage under the current30day/future5minute/regression rules. Automatic hours admit only true/calibrated API hours with trustworthy observation time; virtual and unspecified dashboard hours are visible as unverified, not promoted. Staff can explicitly record a known actual observation with its own source. Missing/unknown is never0. Prefer the latest admissible observation per meter after the confirmed program baseline; capture time alone cannot establish an actual service-time reading. Never reset targets from telemetry.

A date-only service reading retains observed_on/performed_on with precision date and observed_at null; do not invent a midnight observation timestamp. Date-only actual service evidence is valid for an explicitly attested baseline, while telemetry without a known observation time cannot be promoted to that evidence.

A newly lower reading relative to a confirmed service baseline requires review, not guessed continuity. A reasoned manager rebaseline updates that program's comparison generation; older observations cannot be subtracted across it. No automatic meter-replacement detection. Stored completion snapshots remain valid evidence after telemetry purge.

## 5. Program, reading and history API

```ts
type ServiceRef = { id: UUID; name: string; availability: 'active' | 'archived' | 'missing' };
type SafeWork = { work_link_id: UUID; version: Version; cycle: number;
  repair_order_id: UUID | null; order_number: string | null;
  state: 'active' | 'pending_evidence' | 'review_required' | 'completed' | 'detached';
  operation_ids: UUID[]; can_open: boolean };
type Program = {
  id: UUID; vehicle_id: UUID; name: string; version: Version; mode: 'independent' | 'legacy';
  intervals: Intervals; targets: Targets;
  target_provenance: { kind: 'explicit' | 'baseline' | 'completion' | 'legacy'; evidence_id: UUID | null; confirmed_at: Instant | null };
  service: ServiceRef | null; legacy_package: ServiceRef[] | null; current_cycle: number; archived_at: Instant | null;
  due: DueProjection; work: SafeWork | null;
  review: { required: boolean; codes: string[]; completion_id: UUID | null };
  capabilities: { can_edit: boolean; can_plan: boolean; can_record_evidence: boolean; can_archive: boolean };
};
type ProgramPage = Page<Program> & { as_of: Instant; timezone: string;
  counts: { active: number; overdue: number; due: number; unknown: number; in_work: number; review_required: number } };
type ProgramMutation = { schema_version: 1; program: Program; replayed: boolean };
type Config = { name: string; intervals: Intervals; service_id: UUID | null };
type ProgramHistoryItem = { id: UUID; version: Version; action: string; occurred_at: Instant;
  reason: string | null; summary: string; completion: Completion | null };
```

Independent mode uses service and legacy_package=null. Legacy mode uses service=null and legacy_package containing the complete ordered saved package, possibly empty. Preserve every original identity/name/availability in its immutable configuration snapshot; do not collapse multiple services into one or silently discard entries. A legacy package with no service cannot create template-dependent work until its existing legacy adapter supplies a package or the user explicitly converts it.

Program.work is the current-cycle occupying link, or the most recent pending/review link when no current-cycle link exists; full affected links appear in order/target-preview responses. A controlling review flag remains visible even when another current-cycle work link exists.

- GET `/vehicles/{vehicle_id}/maintenance-programs`: `include_archived=false, skip=0, limit=25` (max100), `channel=shop|fleet`; returns ProgramPage. Deterministic active before archived, urgency overdue/due/unknown/current, actual date target nulls last, name, id. No fictional hour/mile deadline for sorting.
- GET `/maintenance-programs`: same paging plus `vehicle_id?, customer_id?, state?` (`overdue|due|unknown|current|in_work|review_required`), search<=160, channel. Apply all resource authorization and filters before count/paging; escaped literal substring across program, unit and VIN. Customer filter uses current authorized owner/operator relationships, not billed-only historical identity. Counts describe the filtered accessible set, and may overlap (due+in_work). No new standalone dashboard required; this supports bounded existing summaries.
- POST `/vehicles/{vehicle_id}/maintenance-programs`: `{channel,config,targets:TargetChange}`; returns201 ProgramMutation (200 replay).
- PATCH `/vehicles/{vehicle_id}/maintenance-programs/{program_id}`: `{channel,expected_version,config,targets:TargetChange}`; full intended config, rather than ambiguous omitted/null updates; returns200 ProgramMutation. Normal edits use `{kind:'preserve'}` and no preview/token/reason. Adding/removing an enabled trigger requires explicit target review; changing interval length may preserve its target, affecting only the next eligible cycle.
- POST `.../{program_id}/archive` or `/restore`: `{channel,expected_version}`; returns ProgramMutation. Archive conflicts with any occupying claim or controlling review; restore keeps targets and history.
- GET `.../{program_id}/history`: channel, skip/limit; returns Page<ProgramHistoryItem>, version descending. Only authorized source links; no P1/C1 cost data.
- POST `/vehicles/{vehicle_id}/maintenance-readings`: `{channel,observed_at,odometer_miles: Miles|null,engine_hours:Hours|null,source:'staff_observed'|'staff_reported',note:string|null}`. At least one value, no future beyond5minutes; server captured_at. Returns201 `{schema_version:1,observation_id,observed_at,captured_at,replayed}`. Immutable append needs no fake CAS against Vehicle.updated_at; reread due projections after save. Historical service attestation uses section8 instead.

For legacy mode, config.service_id must remain null and preserve-target edits retain the full legacy package. Selecting an independent service through config.service_id requires the existing explicit convert_legacy action; it must not implicitly replace the package.

Config changes affecting intervals/template/targets are409 while an active/pending/review cycle is occupied; rename alone is allowed. Archived template makes new template-dependent work unavailable; it does not hide the program or prevent an already captured operation from completing. Program may have no service until staff chooses one. It can still track due state and accept authorized actual historical service evidence.

## 6. Target preview — one calculation purpose

A single endpoint serves initial targets, explicit recalculation/rebaseline/legacy conversion and completion/correction. It computes, loads permitted evidence, and returns a signed deterministic comparison token; no writes/reservations, artificial expiry subsystem or stacked confirmation dialog. UI can call it inline while showing the intended save.

```ts
type ManualServiceReading = { kind:'manual'; value:string; basis:'staff_observed'|'staff_reported'; note:string|null };
type SelectedServiceReading = { kind:'source'; meter:Meter; source_kind:'telemetry'|'maintenance_reading'|'repair_order'|'external_service'; source_id:string };
type ServiceReadings = { odometer_miles: ManualServiceReading|SelectedServiceReading|null; engine_hours:ManualServiceReading|SelectedServiceReading|null };
type Attestation = { performed_on:DateOnly; readings:ServiceReadings; confirm_actual_service_readings:true };
type TargetSeed = { kind:'explicit'; targets:Targets } | { kind:'baseline'; attestation:Attestation };
type TargetChange = { kind:'preserve' } | {
  kind:'replace'|'recalculate'|'rebaseline'|'convert_legacy'; seed:TargetSeed;
  expected_target_fingerprint:string; reason:string|null
};
type TargetPreviewRequest =
  | { purpose:'configuration'; channel:Projection; program:ProgramRef|null; config:Config;
      action:'create'|'replace'|'recalculate'|'rebaseline'|'convert_legacy'; seed:TargetSeed; reason:string|null }
  | { purpose:'completion'; channel:Projection; repair_order_id:UUID;
      expected_review_fingerprint:string; entries:CompletionEntry[] }
  | { purpose:'evidence'; channel:Projection; program:ProgramRef; evidence:EvidenceIntent };
type TargetPreviewItem = { program_id:UUID|null; current_version:Version|null;
  outcome:'targets_updated'|'advanced'|'pending_evidence'|'history_only'|'reaffirmed'|'revoked'|'review_required';
  previous_targets:Targets; proposed_targets:Targets;
  resolved_attestation: { performed_on: DateOnly; readings: { odometer_miles: MeterObservation | null; engine_hours: MeterObservation | null } } | null;
  missing:('attestation'|'date'|Meter)[]; warnings:Warning[] };
type TargetPreview = { schema_version:1; as_of:Instant; timezone:string;
  purpose:TargetPreviewRequest['purpose']; expected_target_fingerprint:string;
  items:TargetPreviewItem[]; affected_work:SafeWork[]; warnings:Warning[] };
```

Every item with an attestation returns its server-resolved date and reading provenance, including original value, comparison_value and observation precision; configuration with explicit targets or an action without attestation returns null. This is the actual content displayed for confirmation and bound in expected_target_fingerprint. Source-selected values are never reconstructed by the client.

POST `/vehicles/{vehicle_id}/maintenance-target-preview` returns TargetPreview. A creation commit uses `kind:'replace'` with the create preview fingerprint; the create route normalizes that intent to preview action create before validating its token. `preserve` is invalid on creation. PATCH kinds map one-to-one to the same-named preview actions. Manual explicit targets require a non-null target for each enabled dimension at creation; baseline seed may leave required readings unknown and returns those targets null. Disabled dimensions must be null in submitted target seed. Reasons (trimmed3–500) are required only for rebaseline, legacy conversion, correction/revoke; ordinary target correction/recalculation is visibly confirmed but requires no narrative. Service dates cannot be future for the shop. Source-selected evidence is fetched by server; clients cannot submit fabricated source values, actor or timestamps. A source reading's observed shop-local date must agree with performed_on; missing time/virtual/regressing evidence cannot substitute for a manual actual attestation.

Fingerprint binds actor/tenant/channel/vehicle, normalized requested action/configuration, current program/version/cycle/baseline, relevant source fingerprint and proposed targets. Commit recomputes under locks; current source/policy/authorization always revalidated. Changing a source after preview returns409 with fresh TargetPreview. A pure name edit does not require this token. An active cycle uses captured config, not today's template/interval.

## 7. Work preview and atomic commit — one work purpose

```ts
type CoverageGroup = {
  key:string; // unique1..80 client key
  program_ids:UUID[]; // nonempty, distinct within this group; occurrence rules below
  service_id:UUID;
  operation: {kind:'new'} | {kind:'existing'; labor_id:UUID; expected_operation_version:number};
};
type WorkTarget = {kind:'existing'; repair_order_id:UUID}
  | {kind:'new'; bill_to_customer_id:UUID; description:string|null};
type WorkRequest = { channel:Projection; programs:ProgramRef[]; target:WorkTarget; coverage:CoverageGroup[] };
type CoveragePreview = {key:string; program_ids:UUID[]; service_id:UUID; service_name:string;
  operation_kind:'new'|'existing'; labor_id:UUID|null; hours:string;
  checklist_items:number; preserves_saved_operation:boolean };
// Same identity/quantity/availability/SafePrice as P1 previewSchema, without counter fields.
type ShopPartPreview = {line_key:string; inventory_id:UUID; parts_usage_id:UUID|null;
  source_service_id:UUID|null; source_line_id:UUID|null; source_component_id:UUID|null;
  disposition:'added'|'retained'|'omitted'; name:string; unit_type:string; quantity:string;
  availability:{state:'available'|'shortage'|'not_stocked'|'unknown';requested_packages:number|null;
    available_packages:number|null;reserved_packages:number|null;included:boolean}; pricing:SafePrice };
type FleetPartPreview = Omit<ShopPartPreview,'pricing'> & {pricing_version:number|null};
type WorkPreviewBase = { schema_version:1; as_of:Instant; vehicle_id:UUID;
  expected_work_fingerprint:string; confirmation_required:true;
  target:WorkTarget; coverage:CoveragePreview[];
  availability:{state:'ready'|'requires_stock_acknowledgement'|'partial_bundle';omitted_line_keys:string[]};
  warnings:{code:string;message:string;line_key:string|null;inventory_id:UUID|null}[];
  existing_work:SafeWork[] };
type WorkPreview =
  | (WorkPreviewBase & {projection:'shop';currency:'USD';lines:ShopPartPreview[];
      totals:{kind:'repair_order';parts_subtotal:string;labor_subtotal:string;labor_discount_amount:string;order_discount_amount:string;repair_total:string};
      account_policy:{snapshot_id:UUID|null;
        labor:{source:'customer'|'shop'|'legacy'|'internal';rate:string|null};
        parts:{source:'customer'|'shop'|'legacy'|'internal';mode:'matrix'|'catalog'|'legacy'|'internal'}};})
  | (WorkPreviewBase & {projection:'fleet';currency:'USD';lines:FleetPartPreview[];
      totals:{kind:'repair_order';repair_total:string};agreement_applies:boolean;});
type WorkCommit = WorkRequest & { expected_work_fingerprint:string };
type WorkMutation = {schema_version:1;repair_order_id:UUID;created:boolean;
  links:SafeWork[];programs:Program[];replayed:boolean};
```

POST `/vehicles/{vehicle_id}/maintenance-work-preview` accepts WorkRequest; POST `/vehicles/{vehicle_id}/maintenance-work` accepts WorkCommit and returns201 when creating an RO or200 otherwise/replay. Bounds: programs contains1–30 distinct program IDs/versions; coverage contains1–30 groups with distinct keys and service IDs, and each group's program_ids is nonempty and duplicate-free. An independent program appears exactly once, under its configured service. A legacy program appears in exactly one group for each distinct service in its captured legacy package, and no other group. Preserve stored package order in display/snapshots. Any extra, missing or repeated (program,service) pair is maintenance_invalid_coverage. Oversized saved packages remain retained/readable and return maintenance_scope_too_large before work mutation; they are never truncated. Multiple programs may deliberately share one group; distinct genuine services keep their distinct components. Existing target must be same-truck authorized draft, not deleted/held/price-locked/closed. If a program already has an occupying claim, return409 with only accessible existing work; never silently choose another order.

For existing operations, verify exact order/service identity, eligible unperformed execution state and expected operation version, then attach mappings only. Preserve hours/rates/parts/checklists; no service reapply. A new group cannot conceal an already existing same-service operation: return409 `maintenance_operation_exists` and offer exact authorized existing identity, rather than duplicating or changing it. Completed work belongs in explicit historical evidence, not new attachment.

For new groups, one service application per distinct group, one labor/parts bundle and independent program links. Create exactly one cycle work link per selected program, even when a legacy program occurs in several coverage groups. Map that link to every covered operation. Each distinct service group creates/applies at most one operation/bundle for all programs in that group, so a legacy package service shared with an independent program is still charged once. Reuse/refactor canonical P1 plan primitives into one internal aggregate maintenance-add plan; **do not pretend pm_replace or repeated service_apply previews are an additive aggregate**. pm_replace can remove unrelated PM services and both adapters can reapply hours. No new public P1 plan variant is necessary: the M1 service calls shared planning/application primitives and returns the exact M1 wrapper above. At commit, one tenant/order transaction validates every group before mutation, runs canonical totals once, and preserves unrelated retained lines. Stock adapter is server-derived and bound in the preview: new shop order uses normal shop service reservation/shortage semantics; new fleet work uses existing fleet-create no-reservation semantics and sets its ordinary fleet/PM classification while suppressing legacy scalar advancement for M1 links. For an existing fleet PM order (`is_pm` and `is_fleet_work` or `is_internal`), added components use its PM no-reservation adapter. Other existing orders use normal shop-flat-service reservation semantics, including a normal additive operation viewed from fleet. Presentation alone cannot change reservation or pricing. New standard shop M1 work does not acquire fleet/legacy is_pm semantics. Actual payer controls internal/external rates in every case. Fleet projection preserves its existing authorized aggregate repair_total, but has no per-line monetary values/private management details.

Aggregate token binds selected program versions/cycles/config, tenant/actor/channel, exact vehicle/payer/order state, coverage/op versions, template/checklist/component snapshots, retained line identities/versions, canonical prices/stock/core inputs and C1 captured or candidate policy. Retained-only mapping must not depend on today's catalog policy. The new-order account_policy.snapshot_id is null until a real policy is captured; existing orders expose only their saved snapshot ID. Labor and parts sources are independent, never collapsed into one misleading account source. No separate P1/C1 confirm buttons/tokens: changed account/prices/scope returns fresh **WorkPreview** and one explicit review. Reuse P1's admitted stock-scope confirmation semantics; displayed omission cannot become an undisclosed charge. Maximum100 projected part lines follows existing P1 UI bounds; overflow409 before mutation.

New order+all operations+claims+receipts commit atomically; failure leaves no new order, stock movement or claims. New external RO uses C1 capture and correct actor/payer; internal uses existing classification. If the user already created a truck/order in an upstream existing wizard, M1 target is `existing`; on cancel/conflict preserve that ID and retry attachment only. No automatic deletion or repeated creation as recovery.

## 8. Completion, pending readings and historical evidence

```ts
type CompletionEntry = {
  work_link_id:UUID; expected_link_version:Version; program:ProgramRef;
  attestation:Attestation|null; // null deliberately defers; no invented fallback
};
type MaintenanceReview = { request_id:UUID; expected_review_fingerprint:string;
  expected_target_fingerprint:string; entries:CompletionEntry[] };
type OrderMaintenance = {schema_version:1;repair_order_id:UUID;expected_review_fingerprint:string;
  links:SafeWork[];programs:Program[];required_readings:Meter[];can_record_evidence:boolean};
type SourceRef = {kind:'repair_order'|'external_service';id:UUID};
type EvidenceIntent =
  | {action:'resolve_pending';work_link_id:UUID;expected_link_version:Version;attestation:Attestation}
  | {action:'recognize';source:SourceRef;attestation:Attestation}
  | {action:'reaffirm';completion_id:UUID;reason:string;acknowledged_work_link_ids:UUID[]}
  | {action:'supersede';completion_id:UUID;attestation:Attestation;reason:string;acknowledged_work_link_ids:UUID[]}
  | {action:'revoke';completion_id:UUID;reason:string;acknowledged_work_link_ids:UUID[]};
type Completion = {id:UUID;program_id:UUID;cycle:number|null;work_link_id:UUID|null;
  action:EvidenceIntent['action']|'finalize'|'pending';
  result:'advanced'|'pending_evidence'|'history_only'|'reaffirmed'|'revoked'|'review_required';
  performed_on:DateOnly|null;readings:{odometer_miles:MeterObservation|null;engine_hours:MeterObservation|null};
  source:{kind:'repair_order'|'external_service'|'manual';id:UUID|null;can_open:boolean;label:string};
  previous_targets:Targets;next_targets:Targets;supersedes_id:UUID|null;recorded_at:Instant};
type EvidenceCommit = {channel:Projection;program:ProgramRef;evidence:EvidenceIntent;expected_target_fingerprint:string};
type EvidenceMutation = {schema_version:1;program:Program;completion:Completion;replayed:boolean};
type MaintenanceResult = {schema_version:1;items:{program_id:UUID;work_link_id:UUID;
  result:Completion['result'];missing:('attestation'|'date'|Meter)[]}[]};
```

GET `/repair-orders/{order_id}/maintenance` returns OrderMaintenance with current authorized safe scope. Existing manager endpoints `/repair-orders/{id}/approve-completion` and `/fleet/work-orders/{id}/complete` accept optional `maintenance_review:MaintenanceReview`; their existing response gets optional additive `maintenance:MaintenanceResult`. Existing absent clients are compatible. Hook runs after current checklist/operation/timer/lifecycle checks and before the same finalization commit. It never independently commits, creates an invoice or sends. Technician completion/pending review alone never advances maintenance.

A legacy package is one program/cycle: all of its captured mapped operations must remain in the approved scope and pass the existing manager completion/checklist/timer/execution guards before that program can advance. Do not advance once per component. One CompletionEntry/Attestation explicitly covers the displayed whole package; missing required readings or unresolved mapping retains all old targets and the one occupying link. Independent programs sharing a valid operation retain their own separate outcomes. A confirmed eligible removal detaches the affected legacy program's whole unperformed cycle claim, not just one component while pretending the package remains covered; other programs lose a mapping only when their own covered operation is removed. Existing surviving operations and their prices remain unchanged.

New UI calls the shared target-preview purpose `completion`, shows date/readings once with selected program applicability, then submits the block. Entries must cover each active linked program exactly once (null attestation allowed); omitted whole block creates pending attestation for each active link. Wrong/duplicate/missing link in an explicit block returns422; stale review/program/link/source returns409 before invoice/stock/completion mutation. Existing route-specific finalization authority/estimates/custody/payment semantics remain unchanged.

Program advancement is atomic: confirmed date plus **all** meters enabled in its captured cycle are needed. Otherwise retain every old target, cycle occupancy and immutable pending evidence, while normal finalization/invoicing succeeds. Valid independent program A may advance while B remains pending. A supplied invalid reading is422 rather than silently treated as missing. Next targets use actual performed date/miles/hours + captured intervals; advance cycle once and complete its link. Normal mileage_out fallback in current fleet completion is not attestation; an explicit maintenance reading remains required. M1 need not change ordinary order mileage behavior.

POST `/vehicles/{vehicle_id}/maintenance-programs/{program_id}/evidence` accepts EvidenceCommit, returns201 EvidenceMutation (200 replay). Its target preview uses purpose `evidence`; no recognize/review-specific preview endpoint. Resolve_pending accepts actual service evidence later for finalized work and advances once. Recognize accepts an accessible, nondeleted same-truck RO whose status is completed, invoiced or paid, or an active nonvoid outside-service record. Cancelled, draft, quoted, in-progress and pending-review orders are ineligible; generic TERMINAL_RO_STATUSES must not be reused; existing source+program recognition returns that identity or409 if new payload differs, never a new cycle. A source with no actual reading stays blank in preview; entering a manual reading records that attestation, not fictitious source provenance. Earlier service than the controlling completion is history_only; same-date different-source ambiguity is409 for explicit correction, not sorted by UUID/insertion time.

Review fingerprint includes current order lifecycle, mapped operations/configuration and their relevant versions; target fingerprint additionally binds fetched source lifecycle/version/identity and actual evidence. For native RO sources without an integer source version use a server HMAC over relevant identity/status/deleted/completion/mileage/operation state, not updated_at alone. Outside source uses its explicit version plus identity/void state. Token verifies pre-transition state under locks; accepted evidence snapshots the committed source identity/state. Do not expose raw private data in tokens/errors.

Reaffirm retains targets/cycle; supersede appends corrected actual evidence and explicitly reviewed targets; revoke restores the last valid explicit baseline/completion targets, or returns unresolved null targets with previous disputed values preserved as history. No current telemetry fallback. Review shows all later active links; acknowledged_work_link_ids must exactly match displayed accessible affected links, otherwise409. Resolution does not cancel or reprice those operations. Current cycle numbers are monotonic; corrections never decrement/reuse a completed cycle, and subsequent actual completion uses its own captured configuration. Ordinary operations/payments can continue during maintenance review.

For reaffirm/supersede/revoke, read-only target preview accepts `acknowledged_work_link_ids:[]` as discovery even when affected_work is nonempty. It performs normal authorization and returns the complete authorized affected set; [] is not acknowledgement. A nonempty submitted list must be unique and exactly match current affected work-link IDs, otherwise409 maintenance_preview_changed with a fresh authorized preview. The fingerprint binds both the normalized requested acknowledgement set and current affected IDs/versions/state. UI displays discovery, obtains explicit acknowledgement and requests a second preview with the exact displayed IDs; commit uses that second token and same IDs. Commit recomputes under locks and requires the complete current set. A first [] token cannot commit with affected work; adding IDs invalidates it. If affected_work is empty, [] may commit without another preview. Changed scope requires fresh review, not silent retry. If a relevant affected link is inaccessible, deny correction without leaking it or treating a filtered subset as complete. No new endpoint, type or dialog.

Maintenance idempotency does not claim to make the entire pre-existing finalization/invoice API idempotent: repeat finalize may retain its existing status rejection. The maintenance hook's durable link/source uniqueness guarantees no repeated target advance or extra evidence when it is invoked again. The optional review request_id binds only its maintenance semantic payload; no invented second invoice path.

## 9. Lifecycle, legacy and removal behavior

| Trigger | Atomic maintenance effect |
|---|---|
| Operation removal or PM replacement | Existing confirmation lists affected links. Explicit confirmed removal detaches eligible unperformed mappings/claims before stock mutation, in the same transaction. Shared operation removal affects every covered link. Completed/pending/disputed evidence cannot be silently detached. No second mandatory detach dialog. |
| Cancel/delete unperformed order | Detach/release claims, preserve events/targets. Existing restoration payload must remember detached identity. |
| Restore unperformed order | Reclaim original program/cycle only if still current/free and configuration compatible;409 before restore/stock mutation otherwise. Never steal a newer claim. |
| Finalized/pending-reading order delete, reopen or force-void | Retain evidence; mark controlling attribution review_required, freeze targets, no rewind or double advancement. Payments/operation permission rules unchanged. |
| Restore finalized order | Retain review, do not automatically reaccept or advance. Existing reopen semantics remain. |
| Recomplete after reopen | Use reaffirm/supersede for the existing evidence chain, not a new cycle merely because finalize ran again. |
| Outside source update/void/restore | Invalidate controlling attribution via exact source-version hook; immutable snapshots remain, restoration does not reaccept. Older noncontrolling source changes add history without rewinding newer valid targets. |
| Program archive | Reject occupying links/review; otherwise reversible, targets/history retained. |
| Template archive/physical delete | New template-dependent work blocked; existing operation snapshots/history usable. Explicit replacement only, no name matching. |

### Legacy recognition and native RO reading provenance (accepted Architecture clarification)

The existing POST `/fleet/trucks/{vehicle_id}/recognize-pm` remains an explicit legacy reclassification action with its existing source/Vehicle changes only when there is no independent program, exactly one eligible legacy adapter (or explicit atomic enrollment by this action), no occupying active/pending/review claim, no controlling review and no existing M1 evidence for that source requiring correction. Otherwise return409 `maintenance_review_required` before any source/scalar change, directing staff to M1 evidence review. This exception does not apply to new M1 APIs.

Its required submitted performed_on/odometer are explicit staff-reported historical attestation, never imported/source_confirmed evidence. No new token/header is required on the old route. Validate current scope, shop-local date, strict reading bounds and regression; preserve date-only observed_on with observed_at=null. Record one immutable legacy recognition/event and synchronize legacy scalars/adapter once in the same transaction as the old source changes. Preserve older-history protection and durable source/program uniqueness; do not independently advance and then call advance_vehicle_pm again. Existing is_pm duplicate conflict may remain. UI requires actual service input with no silent current-mileage,0,arrival or generic-history fallback; any historical reference stays explicitly unverified.

Native RO mileage_out has no persisted provenance and may have been copied from Vehicle.mileage; mileage_in is arrival and may be carried. work_completed_at does not establish a meter observation time. Consequently selected readings with source_kind=repair_order reject422 `maintenance_invalid_reading` for either raw meter field. The RO remains eligible source identity/date context; staff can explicitly confirm an actual manual service reading. Do not add a meter registry, provenance-column backfill, is_pm/status/equality heuristic, or implicit selection of another M1 completion. Raw RO fields remain in source fingerprints for invalidation. Trustworthy manual observations, telemetry and outside-service readings keep their existing rules.

Required regressions: one explicit legacy success/event/advance; duplicate/concurrent retry; independent/occupied/review refusal retaining source/scalars; future/invalid/regressing rollback; older history never rewinds; explicit0; raw fallback/manual-looking historical output and arrival readings rejected as selected evidence; confirmed manual reading succeeds with date precision; new M1 recognition never changes source or Vehicle.

### One-time legacy scheduled package (accepted Architecture amendment)

The existing POST `/fleet/trucks/{vehicle_id}/schedule-pm` retains its `service_ids` semantics: null selects the saved default; an explicit ordered selection is the package for this scheduled order. With `save_as_default=false`, leave `Program.legacy_package` and `VehiclePMService` defaults unchanged. This is a bounded legacy-route exception to the new M1 exact configured-package rule. Other explicit schedule/target changes still synchronize through the guarded versioned legacy adapter.

When `create_work_order=true`, create one legacy program/cycle WorkLink whose immutable `captured_config.legacy_package` contains the complete actual selected service identities/display snapshots in order, with captured program version, intervals and targets. Map every distinct selected service to its exact generated operation once and apply/charge each bundle once. The default package remains recoverable from the program version/event snapshot. When `save_as_default=true`, update the saved package through the guarded adapter before capturing the cycle. When `create_work_order=false`, create no cycle claim or operation mapping.

Completion/removal/cancellation/restoration use the cycle's captured scheduled package, never substitute today's saved default or reject the deliberate one-time selection merely for differing from it. All cycle, baseline, authorization, version, lifecycle and compatibility guards remain. Missing/ambiguous mappings retain review_required and cannot advance targets; empty/partial mappings never prove completion. Preserve P1/C1 review, pricing, reservations and atomic order/claim transaction. Replays cannot create another order/link. Ordinary new M1 work preview/commit continues to require the full exact configured legacy package.

Acceptance: default A+B with one-time A+C preserves defaults A+B, captures/maps A+C, and advances once only when both actual operations and evidence qualify; default-saving updates/captures A+C; schedule-only creates no link; replay/race, missing mapping, cancellation/restore, and new M1 rejection of unconfigured A+C remain covered.

### Removal confirmation carriers (accepted Architecture amendment)

```ts
type AffectedMaintenanceWork = SafeWork & { program_id: UUID; program_name: string };
// Both P1Preview role projections gain only this optional extension:
// maintenance?: { affected_work: AffectedMaintenanceWork[] }
```

Both DELETE `/repair-orders/{id}/price-build/lines/{line_id}` and DELETE `/repair-orders/{id}/labor/{labor_id}` accept optional query `expected_maintenance_fingerprint?: string`, with no new request body. When removal affects current M1 links, require equality with the freshly recomputed order-maintenance `expected_review_fingerprint`. Authorize the existing deletion/vehicle/order scope first, then lock/recompute and validate before bundled parts/core/stock mutation, checklist archival or link detach. Missing/stale token returns409 `maintenance_preview_changed` without writes. UI refreshes existing GET `/repair-orders/{id}/maintenance`, filters by the removed operation ID and renders all affected programs in the existing confirmation; retry only after confirmation. A valid token does not override completed/pending/disputed-link guards. Unaffected deletion retains tokenless compatibility. Tokens are opaque comparison digests, never permission or private source data.

For PM replacement only, both P1 preview projections optionally include `maintenance:{affected_work:AffectedMaintenanceWork[]}` when removed operations affect M1 links. Return the complete affected list, including a whole legacy cycle detached when one package component is removed. Exclude prices, actors, outside-source notes and extra customer data. Frontend strict parsers must explicitly accept this extension. Existing `PMServicesUpdate.pricing_preview_fingerprint` is the sole PM carrier; no new body field, token or dialog. Set confirmation_required=true and bind removed operation IDs, affected link/program/cycle versions and mapping state into the signed semantic pricing fingerprint, not just stock scope. Recompute under existing order locks before mutation; a new/changed affected link causes hard409 with the fresh normal P1 preview including maintenance. Retained-only service operations do not detach links. Omit the extension entirely when unaffected.

Old clients must fail closed for tokenless linked direct deletion and tokenless/stale PM replacement before stock/claim writes. Test both DELETE routes and P1 projections, shared legacy cycles, newly linked races, completed/pending guards, unlinked compatibility and authorization before metadata.

A small optional recovery command may detach an unperformed link without removing its operation: POST `/vehicles/{vehicle_id}/maintenance-programs/{program_id}/detach-work` with `{channel,expected_version,work_link_id,expected_link_version}` returns `{schema_version:1,program,link,replayed}`. It requires no reason narrative; confirms scope in the existing UI. It cannot detach accepted/pending evidence to escape review. This is the recovery for a stale restored order, not the normal removal flow.

Guard exact existing writers: fleet truck PATCH, recognize-pm, schedule-pm, vehicle PM-package PUT, work-order PM-package PUT, both manager completions, direct labor removal, PriceBuild removal, PM-reseed physical removal, order cancellation/delete/restore/reopen/force-void and source edits. New independent program linking must prevent old `advance_vehicle_pm` from running for that same program/order. Legacy-only paths use the explicit legacy adapter, never a hidden scalar minimum across programs.

Legacy admission is based on explicit next target, saved PM package or explicit PM work evidence; not25,000/70 column defaults, imported mileage, is_pmFalse or similar descriptions. Migration creates at most one deterministic legacy adapter per eligible tenant/vehicle and copies exact old target/package provenance. A saved package with no due target gets unknown. An existing unambiguous active PM order may be linked only with exact actual labor/source mapping; multiple open PM orders/ambiguous mapping/invalid intervals become review_required, not guessed claims/completion. Legacy date interpretation stays600mi/day plus Saturday until explicit conversion. Imported interval0 is not automatically changed to25,000. No historic completion or source baseline is invented.

### Explicit restoration of partially performed work

Delete/cancel of a previously active link with completed operations but no M1 evidence for its program/order retains the occupied claim and mappings as review_required. Capture an explicit resumable delete/cancel origin and immutable pre-transition configuration/baseline/targets/cycle, mapping identities/versions, and operation execution facts in restore_state/event metadata. This is neither completion evidence nor detachable unperformed work.

An explicitly authorized restore/reactivation may resume that same link only when the resulting order is live and operational; the only review cause is the recorded delete/cancel; no Completion exists for the link or program/native-source-order (including pending, correction, or historical evidence); and no independent program/source/baseline review exists. Under normal locks, require the original cycle, compatible config/targets/baseline, complete same-tenant/order/service mappings, and relevant monotonic versions/generations to match. Never steal or replace a claim. A changed/missing mapping, conflicting claim, intervening generation, or evidence returns409 maintenance_restore_conflict before order/stock writes. Compare one-time legacy work against its captured package. Preserve partial execution, checklist/timer history and review events, and append a versioned resumed event. Do not restart timers, reset operations, advance targets, create evidence, or rerun parts/service application. Only existing order restoration owns normal stock behavior. A deleted-but-still-cancelled order stays in review until explicit operational reactivation. Finalized/pending/source-disputed evidence, reopen/void and generic review states never qualify; ABA restoration cannot erase history.

Acceptance includes partial A-complete/B-pending cancel/reactivate and delete/restore, unchanged checks/time/targets and later normal finalization; still-cancelled, pending/finalized/source-review exclusions; atomic failure for changed cycle/config/baseline/mapping/service/execution generation, new evidence, competing claims, ABA and wrong tenant.

### Additive maintenance membership on PM orders

For a server-classified is_pm order, an additive M1 commit appends missing same-tenant RepairOrderPMService rows for distinct new service groups in the accepted plan, once, within the existing locked order/parts/mapping/receipt transaction. Preserve existing IDs/order and append in plan order after current max sort_order. Do not replace/reseed, reprice, rewrite description, change stock classification, or alter vehicle/program defaults. Existing-operation-only attachment remains mapping-only; non-PM shop work adds no PM membership. Existing authorization and P1/C1 review apply. Replays/concurrent writers cannot duplicate membership. Acceptance covers retained IDs/order/defaults/prices, shared group uniqueness, replay/race, mapping-only/non-PM exclusions, and PM-replacement preview showing linked removals.

### Manager evidence ordering and completion preview readiness

An explicitly supplied manager-completion service date earlier than the current controlling completion, or equal on the shop-local date but from a different native source, fails409 maintenance_review_required in preview and locked finalization before operations, source status/mileage, invoices, evidence or targets mutate. Message: This service predates or conflicts with the current maintenance record. Review the service evidence before advancing this program. Keep later valid completion and existing duplicate-source guards. Do not silently turn submitted conflicting evidence into pending or add manager history-only semantics. Finalization without a supplied maintenance attestation remains allowed with pending evidence; the existing finalized-work resolve_pending flow can later explicitly record an old-date history-only outcome without moving targets, cycle or controller.

After authorization and scope loading, completion preview runs existing read-only service_checklist.guard_completion, including its operation guard, before target calculation. Never run finish_order from preview: timers, completion dates and tracked minutes cannot change. Keep both finalizer guards and the locked maintenance recheck, including changes after preview. Tests cover earlier/equal-other-source rejection on both routes with atomic retention; valid later date; missing attestation followed by old history-only resolution; incomplete operations, checklist or hold in preview; no timer/date writes; and current authority before any eligibility disclosure.

### Date-only service evidence and current-reading chronology

A confirmed date-only service reading retains observed_on and observed_at:null. Its immutable actual-evidence acceptance time is only an admission boundary for observations on the same shop-local service date, never a fabricated observation timestamp. A same-day lower reading not proven later than acceptance is superseded in this program's post-baseline projection: retain its raw/source record, but neither choose it as current nor call it a regression against the new anchor. Proven later requires trustworthy observed_at and captured_at after acceptance. A same-day observation made before acceptance remains superseded even if delivered later. Otherwise admissible equal/higher same-day readings may remain eligible. Later local dates compare normally, including readings captured before retrospective evidence was entered; lower readings still require review. Earlier local dates remain outside the generation. Captured time alone cannot admit unknown-time observations.

Use the original immutable acceptance boundary for the actual reading, not now or program.updated_at. Reaffirm, rename, reload and revoke-to-prior retain that boundary through the original evidence chain. Explicit new actual evidence uses its own confirmation boundary under existing correction rules. Do not rewrite targets or raw observations. Derive reading_regression only for enabled dimensions using the same predicate as due calculation (enabled interval or legacy explicit target); optional mileage cannot put a date-only program into meter review. Preserve independent persisted source-review codes.

Acceptance covers the observed18:39 lower reading followed by19:03 date-only service evidence; late delivery of the earlier reading; genuinely later same-day regression; next-day regression predating retrospective evidence entry; same-day higher admission; missing time; reaffirm/rename/reload stability; shop-midnight/DST precision; disabled dimensions and legacy explicit targets.

### Native repair-order evidence through financial progression

The immutable native RO source snapshot retains the exact persisted status observed when evidence is appended. Compute its source fingerprint from a separate semantic copy: use lifecycle `finalized` for completed/invoiced/paid, and the exact status for every other state. Preserve all other bound source identity, deletion, completion time, raw-meter/carried flags, and deterministically ordered operation identity/execution facts. Never rewrite an immutable snapshot. Exclude generic `updated_at` and incidental invoicing, payment, settlement, `paid_at`, and pricing fields from this semantic fingerprint and derived M1 source dependencies. Every lookup still rechecks current finalized eligibility and scope; outside-service version semantics are unchanged.

Ordinary financial progression must not invalidate an evidence preview or completed cycle. Existing reopen/cancel/delete/force-void/source-edit hooks still record durable review, including reopen then re-complete returning to the same finalized category. Raw meter binding detects source changes; it does not establish actual reading evidence. No payment-writer changes are needed.

Acceptance: completed→invoiced→paid and incidental settlement/timestamp changes preserve digest, target-preview token, targets, and cycle state while the original snapshot remains exact. Nonfinal status, deletion, completion time, raw meters/carried flags, and operation identity/execution changes invalidate. Reopen→recomplete retains explicit review; wrong-tenant/vehicle sources remain inaccessible.

## 10. Concurrency, idempotency and errors

All new POST/PATCH mutations require UUID `Idempotency-Key`; preview/GET do not. Existing finalization retains its old header rules and uses optional review.request_id. Reuse strict current key validation and normalize canonical semantic requests (route/principal/channel/IDs/versions/intent; exclude refreshable preview token bytes). Same key+same semantic successful request returns same outcome IDs/replayed true after current authorization; changed semantic request409. Conflicted/failed transactions must not leave a completed receipt. Unique claim/source constraints remain authoritative if old receipts are ever removed.

New M1 commands touching work take existing tenant financial lock first, then canonical customer/policy locks via C1, target RO, vehicle, sorted program IDs/claims/operations, templates and canonical inventory/core locks. Config/reading/evidence commands may use that same tenant lock to keep v1 ordering simple. No inventory/program lock before tenant. Source-only mutation and vehicle-merge paths currently lock vehicles; add the narrow M1 source/merge hook under those existing locks and **never acquire tenant after a vehicle lock**. M1 source recognition takes tenant→vehicle→program→source; outside source mutation must use vehicle→program→source (pre-read scoped identity, then revalidate), avoiding inverse source→program acquisition. For RO sources, existing tenant→RO→vehicle→program order applies; pre-read scoped identities and lock every involved RO in sorted UUID order before vehicle/program locks, never fetch a locked source RO after locking its program. Test actual mixed transactions rather than only unit lock mocks.

Before vehicle merge mutates anything, fail409 if losing identity has any M1 program/reading/evidence, including archived history; also fail if winning M1 identity would acquire ambiguous explicit legacy PM evidence. No M1 transfer or financial consolidation. Guard current membership/vehicle mutation paths by revalidation; membership removal makes later fleet access404, not a new entitlement.

```ts
type MaintenanceError = { detail: {
  code:string; message:string;
  field?:string; current_version?:number;
  preview?:TargetPreview|WorkPreview;
  existing_work?:SafeWork[];
  affected_program_ids?:UUID[];
} };
```

Codes and HTTP status:

-403 `maintenance_forbidden`;404 `maintenance_not_found` for hidden/absent resource.
-422 `maintenance_invalid_input`, `maintenance_invalid_reading`, `maintenance_future_service`, `maintenance_invalid_coverage`.
-409 `maintenance_version_conflict`, `maintenance_preview_changed` (fresh preview only after scope authorization), `maintenance_cycle_claimed`, `maintenance_review_required`, `maintenance_operation_exists`, `maintenance_operation_linked`, `maintenance_template_unavailable`, `maintenance_source_changed`, `maintenance_restore_conflict`, `maintenance_vehicle_merge_requires_review`, `maintenance_scope_too_large`, `idempotency_conflict`.

C1/P1 policy/stock/core failures inside work commit return their existing safe code/message with **M1 WorkPreview** in detail.preview if retryable and authorized; never return a raw private P1 ManagementDetails payload. This endpoint's frontend parser discriminates the M1 preview, not generic P1 parser. A fresh preview must show the actual persisted truck/order identity, allowing retry attachment without re-creation. All errors retain user drafts.409 is not success and cannot leave partial order/financial/claim writes.

## 11. Migration, ownership and acceptance

Migration is additive after final C1 head. Preserve both175 branches and176 merge ancestry; choose next free revision at intake. Add schema, deterministic legacy adapters/events and indexes; do not backfill finances, stock, actual readings or unknown dates. Preserve fingerprints of existing orders/labor/parts/invoices/payments/customer policies and old scalar PM values. Test clean upgrade, real legacy variants, already enrolled retry and populated downgrade refusal. Once independent programs exist, rollback must retain maintenance writer guards or pause affected maintenance writes; old unguarded scalar completion cannot be deployed as a safe writer. The C1 Worker schema gate should discover the new expected head normally; no extra M1 task/scheduler.

Backend owns new model/schema/service/endpoint/migration and narrow integration edits in fleet.py, repair_orders.py, price_build_service.py, service_checklist.py, operation_execution.py, external_service.py, vehicle_merge.py and shared P1 planner primitives. One backend owner prevents shared-file collisions. Frontend owns one maintenance types/hooks/components feature reused by CustomerVehicleDetail and TruckDetail, existing completion forms and removal confirmation adapters. Reuse `useIntakePricing`/P1 review elements, but one M1 work confirmation controls aggregate commit. Root owns canonical contract/tracker/receipt; independent reviewers own QA/Security/release gates.

First build chunk: state/schema, pure due/reading projection, authorized CRUD/history and legacy guards with stable fixtures. Then atomic work/completion/lifecycle integration and shared UI in the same selected outcome. No partial Done or release of a create/complete control without its hooks.

Minimum acceptance matrix:

| Area | Required positive/negative proof |
|---|---|
| Independent programs | Three programs/date+miles+hours; due0/overduenegative; one known overdue plus another unknown; no guessed date for miles/hours; DST/midnight on one as_of. |
| Readings | Missing, stale, virtual, unspecified hours, captured-only, regression, wrong VIN/membership/time, valid explicit0 and false/NaN rejected; no telemetry target reset; completion survives purge. |
| Program edits | Rename direct/no preview; interval preserve; enable/disable requires target review; active config conflict; no blank/unavailable fetch mistaken for defaults; archived template existing work remains usable. |
| Shared operation | Two programs→one operation/parts bundle/checklist, two independent cycle claims; existing attachment changes no hours/prices/parts; duplicate/racing claims and same-service ambiguity fail without mutation. |
| Pricing/stock | External agreement→shop; internal unchanged; legacy saved rates; new/captured/archived matrices; retained line identity/cost/core reservation; changed price/policy/stock returns one M1 preview; complete rollback on failure. |
| Completion | Both manager routes, no technician advance; A valid/B missing; invoice allowed with pending; later source-backed resolution advances once; bad submitted evidence rolls back whole finalize. |
| History/corrections | Actual historical reading confirmation; no current odometer fallback; duplicate recognition; older history-only; equal-date conflict; source version change; reaffirm/supersede/revoke and affected later links. |
| Lifecycle | Shared remove, PM replacement, cancel/delete/restore/reopen/void/recomplete; direct alternate writers; no orphan active claim or double advance; narrow vehicle merge conflict. |
| Concurrency | Two-client claim; receipt replay after role loss; source edit vs recognition; config vs completion; order price edit vs attach/finalize; merge vs first program/reading; no deadlock/inverse lock path. |
| Privacy | Cross-tenant every ID/filter/token; fleet nonmember; receptionist escalation; mechanic scope; private outside evidence; forged actor/source/monetary fields; downward-only projection. |
| Migration | Defaults-only, explicit legacy target/package, imported0, unknown operation map, multiple active PM orders; exact legacy scalar+financial retention and populated downgrade refusal. |
| Actual UI | Light/Night desktop1280+,390/320 portrait and740×400 landscape: enroll, edit, inline target preview, add shared work, finalize/pending/resolve/history, cancel/back/reload; one scroll area, unwrapped action labels, drafts survive60s TruckDetail refetch. |

Local synthetic evidence may exercise writes after runtime alignment. Production acceptance uses only separately authorized real actions or existing safe records; no invented real schedules, financial issuance or provider activity just for QA. Browser emulation must be labelled as such.

## Source anchors rechecked

- `backend/app/db/models/vehicle.py:58`, `models/fleet.py:206`, `services/internal_fleet.py:69–118`: one scalar package, legacy600mi/day/Saturday and fallback pitfalls.
- `services/fleet_pm.py:6`, `services/fleet_telemetry.py:255,524,572,629`, `schemas/fleet_telemetry.py:118`: NumericReading admission/source/true-versus-virtual/purge.
- `services/parts_pricing_planner.py:167,335,477`, `schemas/parts_pricing.py`, `frontend/src/features/parts-pricing/contract.ts`: canonical source identities, projections, fingerprints, parts/stock and current wire parser.
- `services/customer_pricing.py:145–258,317`, `api/v1/endpoints/fleet.py:2953`: captured policies, correct actual payer/classification and identity receipts.
- `api/v1/endpoints/fleet.py:235,2445,2615,2814,3129,3408,3440,3757`, `api/v1/endpoints/repair_orders.py:3081,3206`: actual access, PM writers, completion and replacement seams.
- `services/service_checklist.py:335`, `services/operation_execution.py:238,270`, `services/price_build_service.py:278,573`: transaction-owned checklist/execution/removal; service application can update retained hours.
- `services/external_service.py:26–110`, `services/vehicle_merge.py:167,319`, `services/parts_operations_service.py:155–206`: exact source/vehicle locks, immutable source versions and reusable receipt primitives.
- `frontend/src/features/customers/CustomerVehicleDetail.tsx:79`, `features/fleet/TruckDetail.tsx:176,1264`, `FleetModals.tsx:657`, `priceBuild.ts:240,461`: shared UI locations, polling, unsafe historical-reading fallback and existing review adapters.
- `backend/scripts/easytruck_sync/import_to_truckpitstop.py:838,877`: imported interval0/is_pmFalse is not enrollment/evidence; no importer-policy expansion.

Intake recheck, not redesign: verify final C1 head/schema, the exact frozen Worker gate and incoming changes touching these anchors; resolve any concrete source contradiction before frontend/backend GO. Implementation may proceed only on the accepted intake and runtime receipt; this contract is not QA or release approval.
