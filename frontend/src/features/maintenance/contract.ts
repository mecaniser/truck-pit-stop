import { z } from 'zod'
import { safePriceSchema } from '@/features/parts-pricing/contract'

const id = z.string().min(1)
const version = z.number().int().positive()
const decimal = z.string().regex(/^\d+(?:\.\d{1,2})?$/)
const date = z.string().regex(/^\d{4}-\d{2}-\d{2}$/)
const instant = z.string().datetime({ offset: true })
export const channelSchema = z.enum(['shop', 'fleet'])
export type Channel = z.infer<typeof channelSchema>
export const meterSchema = z.enum(['odometer_miles', 'engine_hours'])
export type Meter = z.infer<typeof meterSchema>
export const intervalsSchema = z.object({ days: z.number().int().min(1).max(36500).nullable(), miles: z.number().int().min(1).max(99999999).nullable(), engine_hours: decimal.nullable() }).strict()
export const targetsSchema = z.object({ due_on: date.nullable(), odometer_miles: z.number().int().min(0).max(99999999).nullable(), engine_hours: decimal.nullable() }).strict()
export type Targets = z.infer<typeof targetsSchema>
export type Config = { name: string; intervals: z.infer<typeof intervalsSchema>; service_id: string | null }
export const observationSchema = z.object({
  value: z.string(), comparison_value: z.string().nullable(), unit: z.enum(['mi', 'h']),
  source: z.enum(['motive_api', 'motive_dashboard_manual', 'maintenance_manual', 'service_evidence']),
  basis: z.enum(['calibrated', 'virtual', 'dashboard_unspecified', 'staff_observed', 'staff_reported', 'service_confirmed']),
  observed_at: instant.nullable(), observed_on: date.nullable(), observed_precision: z.enum(['second', 'minute', 'date', 'unknown']), captured_at: instant.nullable(),
  source_id: z.string().nullable(), freshness: z.enum(['fresh', 'delayed', 'stale', 'unknown']),
  admission: z.enum(['accepted', 'stale', 'unverified_basis', 'regression', 'identity_mismatch', 'missing_time']),
}).strict()
export type Observation = z.infer<typeof observationSchema>
const trigger = z.enum(['disabled', 'current', 'due', 'overdue', 'unknown'])
const dueSchema = z.object({ state: z.enum(['current', 'due', 'overdue', 'unknown']),
  date: z.object({ state: trigger, target: date.nullable(), remaining_days: z.number().int().nullable() }).strict(),
  miles: z.object({ state: trigger, target: z.number().int().nullable(), remaining: z.number().nullable(), reading: observationSchema.nullable() }).strict(),
  engine_hours: z.object({ state: trigger, target: decimal.nullable(), remaining: z.string().nullable(), reading: observationSchema.nullable() }).strict(),
  needs_reading: z.array(meterSchema), needs_baseline: z.array(z.enum(['date', 'odometer_miles', 'engine_hours'])),
}).strict()
export const safeWorkSchema = z.object({ work_link_id: id, version, cycle: version, repair_order_id: id.nullable(), order_number: z.string().nullable(), state: z.enum(['active', 'pending_evidence', 'review_required', 'completed', 'detached']), operation_ids: z.array(id), can_open: z.boolean() }).strict()
export type SafeWork = z.infer<typeof safeWorkSchema>
const serviceSchema = z.object({ id, name: z.string(), availability: z.enum(['active', 'archived', 'missing']) }).strict()
export const programSchema = z.object({ id, vehicle_id: id, name: z.string(), version, mode: z.enum(['independent', 'legacy']), intervals: intervalsSchema, targets: targetsSchema,
  target_provenance: z.object({ kind: z.enum(['explicit', 'baseline', 'completion', 'legacy']), evidence_id: id.nullable(), confirmed_at: instant.nullable() }).strict(),
  service: serviceSchema.nullable(), legacy_package: z.array(serviceSchema).nullable(), current_cycle: version, archived_at: instant.nullable(), due: dueSchema, work: safeWorkSchema.nullable(),
  review: z.object({ required: z.boolean(), codes: z.array(z.string()), completion_id: id.nullable() }).strict(),
  capabilities: z.object({ can_edit: z.boolean(), can_plan: z.boolean(), can_record_evidence: z.boolean(), can_archive: z.boolean() }).strict(),
}).strict()
export type Program = z.infer<typeof programSchema>
const page = { schema_version: z.literal(1), total: z.number().int().nonnegative(), has_more: z.boolean() }
export const programPageSchema = z.object({ ...page, items: z.array(programSchema), as_of: instant, timezone: z.string(), counts: z.object({ active: z.number(), overdue: z.number(), due: z.number(), unknown: z.number(), in_work: z.number(), review_required: z.number() }).strict() }).strict()
export const programMutationSchema = z.object({ schema_version: z.literal(1), program: programSchema, replayed: z.boolean() }).strict()
export type ProgramRef = { program_id: string; expected_version: number }
export const refFor = (program: Program): ProgramRef => ({ program_id: program.id, expected_version: program.version })
export type ServiceReading = { kind: 'manual'; value: string; basis: 'staff_observed' | 'staff_reported'; note: string | null } | { kind: 'source'; meter: Meter; source_kind: 'telemetry' | 'maintenance_reading' | 'repair_order' | 'external_service'; source_id: string }
export type Attestation = { performed_on: string; readings: Record<Meter, ServiceReading | null>; confirm_actual_service_readings: true }
export type TargetSeed = { kind: 'explicit'; targets: Targets } | { kind: 'baseline'; attestation: Attestation }
export type TargetChange = { kind: 'preserve' } | { kind: 'replace' | 'recalculate' | 'rebaseline' | 'convert_legacy'; seed: TargetSeed; expected_target_fingerprint: string; reason: string | null }
export type CompletionEntry = { work_link_id: string; expected_link_version: number; program: ProgramRef; attestation: Attestation | null }
export type EvidenceIntent = { action: 'resolve_pending'; work_link_id: string; expected_link_version: number; attestation: Attestation }
  | { action: 'recognize'; source: { kind: 'repair_order' | 'external_service'; id: string }; attestation: Attestation }
  | { action: 'reaffirm' | 'revoke'; completion_id: string; reason: string; acknowledged_work_link_ids: string[] }
  | { action: 'supersede'; completion_id: string; reason: string; acknowledged_work_link_ids: string[]; attestation: Attestation }
export type TargetRequest = { purpose: 'configuration'; channel: Channel; program: ProgramRef | null; config: Config; action: 'create' | 'replace' | 'recalculate' | 'rebaseline' | 'convert_legacy'; seed: TargetSeed; reason: string | null }
  | { purpose: 'completion'; channel: Channel; repair_order_id: string; expected_review_fingerprint: string; entries: CompletionEntry[] }
  | { purpose: 'evidence'; channel: Channel; program: ProgramRef; evidence: EvidenceIntent }
const warning = z.object({ code: z.string(), message: z.string(), program_id: id.nullable() }).strict()
export const targetPreviewSchema = z.object({ schema_version: z.literal(1), as_of: instant, timezone: z.string(), purpose: z.enum(['configuration', 'completion', 'evidence']), expected_target_fingerprint: id,
  items: z.array(z.object({ program_id: id.nullable(), current_version: version.nullable(), outcome: z.enum(['targets_updated', 'advanced', 'pending_evidence', 'history_only', 'reaffirmed', 'revoked', 'review_required']), previous_targets: targetsSchema, proposed_targets: targetsSchema,
    resolved_attestation: z.object({ performed_on: date, readings: z.object({ odometer_miles: observationSchema.nullable(), engine_hours: observationSchema.nullable() }).strict() }).strict().nullable(),
    missing: z.array(z.enum(['attestation', 'date', 'odometer_miles', 'engine_hours'])), warnings: z.array(warning) }).strict()), affected_work: z.array(safeWorkSchema), warnings: z.array(warning),
}).strict()
export type TargetPreview = z.infer<typeof targetPreviewSchema>
export function parseTargetPreview(raw: unknown, request: TargetRequest) {
  const result = targetPreviewSchema.parse(raw)
  const ids = request.purpose === 'completion' ? request.entries.map(entry => entry.program.program_id) : [request.program?.program_id ?? null]
  if (result.purpose !== request.purpose || result.items.length !== ids.length || new Set(result.items.map(item => item.program_id)).size !== ids.length || result.items.some(item => !ids.includes(item.program_id))) throw new Error('Maintenance preview does not match this request.')
  return result
}
export const completionSchema = z.object({ id, program_id: id, cycle: version.nullable(), work_link_id: id.nullable(), action: z.enum(['resolve_pending', 'recognize', 'reaffirm', 'supersede', 'revoke', 'finalize', 'pending']), result: z.enum(['advanced', 'pending_evidence', 'history_only', 'reaffirmed', 'revoked', 'review_required']), performed_on: date.nullable(),
  readings: z.object({ odometer_miles: observationSchema.nullable(), engine_hours: observationSchema.nullable() }).strict(), source: z.object({ kind: z.enum(['repair_order', 'external_service', 'manual']), id: id.nullable(), can_open: z.boolean(), label: z.string() }).strict(), previous_targets: targetsSchema, next_targets: targetsSchema, supersedes_id: id.nullable(), recorded_at: instant }).strict()
export type Completion = z.infer<typeof completionSchema>
export const historySchema = z.object({ ...page, items: z.array(z.object({ id, version, action: z.string(), occurred_at: instant, reason: z.string().nullable(), summary: z.string(), completion: completionSchema.nullable() }).strict()) }).strict()
export const evidenceMutationSchema = z.object({ schema_version: z.literal(1), program: programSchema, completion: completionSchema, replayed: z.boolean() }).strict()
export const readingMutationSchema = z.object({ schema_version: z.literal(1), observation_id: id, observed_at: instant, captured_at: instant, replayed: z.boolean() }).strict()
export const orderMaintenanceSchema = z.object({ schema_version: z.literal(1), repair_order_id: id, expected_review_fingerprint: id, links: z.array(safeWorkSchema), programs: z.array(programSchema), required_readings: z.array(meterSchema), can_record_evidence: z.boolean() }).strict()
export type OrderMaintenance = z.infer<typeof orderMaintenanceSchema>
export type MaintenanceReview = { request_id: string; expected_review_fingerprint: string; expected_target_fingerprint: string; entries: CompletionEntry[] }
export type CoverageGroup = { key: string; program_ids: string[]; service_id: string; operation: { kind: 'new' } | { kind: 'existing'; labor_id: string; expected_operation_version: number } }
export type WorkTarget = { kind: 'existing'; repair_order_id: string } | { kind: 'new'; bill_to_customer_id: string; description: string | null }
export type WorkRequest = { channel: Channel; programs: ProgramRef[]; target: WorkTarget; coverage: CoverageGroup[] }
const workTarget = z.discriminatedUnion('kind', [z.object({ kind: z.literal('existing'), repair_order_id: id }).strict(), z.object({ kind: z.literal('new'), bill_to_customer_id: id, description: z.string().nullable() }).strict()])
const part = { line_key: id, inventory_id: id, parts_usage_id: id.nullable(), source_service_id: id.nullable(), source_line_id: id.nullable(), source_component_id: id.nullable(), disposition: z.enum(['added', 'retained', 'omitted']), name: z.string(), unit_type: z.string(), quantity: z.string(), availability: z.object({ state: z.enum(['available', 'shortage', 'not_stocked', 'unknown']), requested_packages: z.number().nullable(), available_packages: z.number().nullable(), reserved_packages: z.number().nullable(), included: z.boolean() }).strict() }
const workBase = { schema_version: z.literal(1), as_of: instant, vehicle_id: id, expected_work_fingerprint: id, confirmation_required: z.literal(true), target: workTarget,
  coverage: z.array(z.object({ key: id, program_ids: z.array(id), service_id: id, service_name: z.string(), operation_kind: z.enum(['new', 'existing']), labor_id: id.nullable(), hours: z.string(), checklist_items: z.number().int().nonnegative(), preserves_saved_operation: z.boolean() }).strict()),
  availability: z.object({ state: z.enum(['ready', 'requires_stock_acknowledgement', 'partial_bundle']), omitted_line_keys: z.array(id) }).strict(), warnings: z.array(z.object({ code: z.string(), message: z.string(), line_key: id.nullable(), inventory_id: id.nullable() }).strict()), existing_work: z.array(safeWorkSchema), currency: z.literal('USD') }
export const workPreviewSchema = z.discriminatedUnion('projection', [
  z.object({ ...workBase, projection: z.literal('shop'), lines: z.array(z.object({ ...part, pricing: safePriceSchema }).strict()).max(100), totals: z.object({ kind: z.literal('repair_order'), parts_subtotal: decimal, labor_subtotal: decimal, labor_discount_amount: decimal, order_discount_amount: decimal, repair_total: decimal }).strict(), account_policy: z.object({ snapshot_id: id.nullable(), labor: z.object({ source: z.enum(['customer', 'shop', 'legacy', 'internal']), rate: decimal.nullable() }).strict(), parts: z.object({ source: z.enum(['customer', 'shop', 'legacy', 'internal']), mode: z.enum(['matrix', 'catalog', 'legacy', 'internal']) }).strict() }).strict() }).strict(),
  z.object({ ...workBase, projection: z.literal('fleet'), lines: z.array(z.object({ ...part, pricing_version: z.number().int().nonnegative().nullable() }).strict()).max(100), totals: z.object({ kind: z.literal('repair_order'), repair_total: decimal }).strict(), agreement_applies: z.boolean() }).strict(),
])
export type WorkPreview = z.infer<typeof workPreviewSchema>
export function parseWorkPreview(raw: unknown, vehicleId: string, request: WorkRequest) {
  const preview = workPreviewSchema.parse(raw)
  if (preview.target.kind === 'new' && preview.projection === 'shop' && preview.account_policy.snapshot_id !== null) throw new Error('A new order preview cannot claim a saved pricing policy.')
  const targetMatches = preview.target.kind === 'existing' ? request.target.kind === 'existing' && preview.target.repair_order_id === request.target.repair_order_id : request.target.kind === 'new' && preview.target.bill_to_customer_id === request.target.bill_to_customer_id && preview.target.description === request.target.description
  if (preview.vehicle_id !== vehicleId || preview.projection !== request.channel || !targetMatches || preview.coverage.length !== request.coverage.length || new Set(preview.coverage.map(group => group.key)).size !== preview.coverage.length) throw new Error('Maintenance work preview does not match this request.')
  if (preview.coverage.some(group => { const expected = request.coverage.find(item => item.key === group.key); return !expected || group.service_id !== expected.service_id || group.operation_kind !== expected.operation.kind || group.program_ids.length !== expected.program_ids.length || new Set(group.program_ids).size !== group.program_ids.length || group.program_ids.some(id => !expected.program_ids.includes(id)) || (expected.operation.kind === 'existing' && group.labor_id !== expected.operation.labor_id) })) throw new Error('Maintenance coverage changed.')
  return preview
}
export const workMutationSchema = z.object({ schema_version: z.literal(1), repair_order_id: id, created: z.boolean(), links: z.array(safeWorkSchema), programs: z.array(programSchema), replayed: z.boolean() }).strict()
export const detachMutationSchema = z.object({ schema_version: z.literal(1), program: programSchema, link: safeWorkSchema, replayed: z.boolean() }).strict()
export const programServices = (program: Program) => program.mode === 'legacy' ? program.legacy_package ?? [] : program.service ? [program.service] : []
export const label = (value: string) => value.replace(/_/g, ' ')
export function whole(value: string, name: string, maximum = 99999999): number | null { if (!value.trim()) return null; if (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)) || Number(value) > maximum) throw new Error(`Enter a whole ${name}.`); return Number(value) }
export function hours(value: string): string | null { if (!value.trim()) return null; if (!/^\d+(?:\.\d{1,2})?$/.test(value) || Number(value) > 10000000) throw new Error('Enter hours with at most 2 decimal places.'); return value }
