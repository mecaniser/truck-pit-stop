import { z } from 'zod'
import type { BoardTruck } from './types'

const text = (max: number) => z.string().trim().min(1).max(max).refine(v => !v.includes(String.fromCharCode(0)) && !/[\uD800-\uDFFF]/u.test(v), 'Invalid text')
const vin = z.string().regex(/^[A-HJ-NPR-Z0-9]{17}$/)
const confirmation = z.object({ company_name: text(120), company_id: text(100), vin }).strict()
const timestamp = z.string().datetime({ offset: true }).refine(v => Date.parse(v) <= Date.now() + 300000, 'Observation is in the future')
export const observationSchema = z.object({
  expected_tenant_id: z.string().uuid(), vin, lat: z.number().finite().min(-90).max(90), lng: z.number().finite().min(-180).max(180),
  observed_at: timestamp.nullable(), source_age_text: text(120).nullable(), source_read_time: text(180),
  provider_company_name: text(120), provider_company_id: text(100), provider_vehicle_number: text(120),
  evidence_note: text(450), before: confirmation, after: confirmation,
}).strict().superRefine((v, ctx) => {
  for (const side of [v.before, v.after]) if (side.vin !== v.vin || side.company_name !== v.provider_company_name || side.company_id !== v.provider_company_id) ctx.addIssue({ code: 'custom', message: 'Company and VIN must match before and after collection.' })
})
export type Observation = z.infer<typeof observationSchema>
export type Actor = { id: string; tenant_id: string | null; role: string; is_active: boolean }
export function verifyActor(actual: Actor, expected: Actor, tenant: string) {
  if (!actual.is_active || !expected.is_active || !['garage_owner', 'garage_admin'].includes(actual.role) || actual.role !== expected.role || actual.id !== expected.id || actual.tenant_id !== tenant || expected.tenant_id !== tenant) throw Error('Session or tenant changed. No import allowed.')
}
export function matchTruck(trucks: BoardTruck[], source: Observation) {
  const matches = trucks.filter(t => t.vin?.trim().toUpperCase() === source.vin)
  if (matches.length !== 1 || !matches[0].board_membership_customer_id) throw Error('VIN must match exactly one active fleet membership.')
  return matches[0]
}
export function checkFreshness(truck: BoardTruck, source: Observation) {
  const previous = truck.telemetry?.location
  if (previous?.lat === source.lat && previous?.lng === source.lng) throw Error('Coordinates unchanged. Previous position retained.')
  if (previous?.observed_at && (!source.observed_at || !Number.isFinite(Date.parse(previous.observed_at)) || Date.parse(source.observed_at) <= Date.parse(previous.observed_at))) throw Error('Observation is older, or recency cannot be verified. Previous position retained.')
}
const payloadSchema = z.object({ client_request_id: z.string().uuid(), fleet_customer_id: z.string().uuid(), vin, lat: z.number().finite(), lng: z.number().finite(), observed_at: z.string().nullable(), source_age_text: z.string().nullable(), provider_company_label: z.string(), provider_vehicle_number: z.string(), evidence_note: z.string() }).strict()
const receiptSchema = z.object({ id: z.string().uuid(), vehicle_id: z.string().uuid(), fleet_customer_id: z.string().uuid(), captured_by_user_id: z.string().uuid(), captured_at: z.string().datetime({ offset: true }), observed_at: z.string().datetime({ offset: true }).nullable(), source: z.literal('motive_dashboard_manual') }).passthrough()
export type Receipt = z.infer<typeof receiptSchema>
export function locationFingerprint(truck: BoardTruck): string {
  const location = truck.telemetry?.location
  return JSON.stringify(location ? [location.snapshot_id ?? null, location.lat ?? null, location.lng ?? null, location.observed_at ?? null, location.captured_at ?? null] : null)
}
const checkpointSchema = z.object({ version: z.literal(1), actor_id: z.string().uuid(), tenant_id: z.string().uuid(), vehicle_id: z.string().uuid(), source: observationSchema, baseline_location: z.string(), payload: payloadSchema, receipt: receiptSchema.optional(), response_status: z.union([z.literal(200), z.literal(201)]).optional() }).strict()
export type Checkpoint = z.infer<typeof checkpointSchema>
export const checkpointKey = (actor: Actor) => `coordinate-import-v1:${actor.tenant_id}:${actor.id}`
export function makeCheckpoint(source: Observation, actor: Actor, truck: BoardTruck, id: string = crypto.randomUUID()): Checkpoint {
  return { version: 1, actor_id: actor.id, tenant_id: source.expected_tenant_id, vehicle_id: truck.id, source, baseline_location: locationFingerprint(truck), payload: {
    client_request_id: id, fleet_customer_id: truck.board_membership_customer_id!, vin: source.vin, lat: source.lat, lng: source.lng, observed_at: source.observed_at,
    source_age_text: source.source_age_text, provider_company_label: `${source.provider_company_name} / ${source.provider_company_id}`, provider_vehicle_number: source.provider_vehicle_number,
    evidence_note: `Source read: ${source.source_read_time}. Before/after company and VIN verified. ${source.evidence_note}`,
  } }
}
export function readCheckpoint(storage: Pick<Storage, 'getItem'>, actor: Actor): Checkpoint | null {
  const raw = storage.getItem(checkpointKey(actor)); if (raw === null) return null
  const value = checkpointSchema.parse(JSON.parse(raw))
  const rebuilt = makeCheckpoint(value.source, actor, { id: value.vehicle_id, board_membership_customer_id: value.payload.fleet_customer_id } as BoardTruck, value.payload.client_request_id)
  if (value.actor_id !== actor.id || value.tenant_id !== actor.tenant_id || JSON.stringify(value.payload) !== JSON.stringify(rebuilt.payload)) throw Error('Checkpoint is invalid. Do not retry or create another request; reconcile the saved request first.')
  if (value.receipt) verifyReceipt(value.receipt, value)
  return value
}
export function persistCheckpoint(storage: Pick<Storage, 'getItem' | 'setItem'>, actor: Actor, checkpoint: Checkpoint) {
  const raw = JSON.stringify(checkpoint)
  storage.setItem(checkpointKey(actor), raw)
  if (storage.getItem(checkpointKey(actor)) !== raw) throw Error('Checkpoint could not be saved. Preserve the current request.')
}
export function verifyReceipt(data: unknown, checkpoint: Checkpoint): Receipt {
  const receipt = receiptSchema.parse(data)
  if (receipt.vehicle_id !== checkpoint.vehicle_id || receipt.fleet_customer_id !== checkpoint.payload.fleet_customer_id || receipt.captured_by_user_id !== checkpoint.actor_id || receipt.observed_at !== checkpoint.payload.observed_at && !(receipt.observed_at && checkpoint.payload.observed_at && Date.parse(receipt.observed_at) === Date.parse(checkpoint.payload.observed_at))) throw Error('Receipt identity mismatch. Keep this request for reconciliation.')
  return receipt
}
export function verifyProjection(trucks: BoardTruck[], checkpoint: Checkpoint, receipt: Receipt) {
  const truck = matchTruck(trucks, checkpoint.source)
  const location = truck.telemetry?.location
  return truck.id === checkpoint.vehicle_id && truck.board_membership_customer_id === checkpoint.payload.fleet_customer_id && location?.snapshot_id === receipt.id && location.lat === checkpoint.payload.lat && location.lng === checkpoint.payload.lng
}
export const exampleObservation = { expected_tenant_id: '11111111-1111-4111-8111-111111111111', vin: '1FUJGLDR0CSBP0001', lat: 35.1, lng: -80.7, observed_at: null, source_age_text: '2s', source_read_time: '2026-10-06 11:53 AM, timezone unknown', provider_company_name: 'EXAMPLE FLEET', provider_company_id: 'EXAMPLE001', provider_vehicle_number: '01', evidence_note: 'Synthetic example. Replace every field with current source evidence.', before: { company_name: 'EXAMPLE FLEET', company_id: 'EXAMPLE001', vin: '1FUJGLDR0CSBP0001' }, after: { company_name: 'EXAMPLE FLEET', company_id: 'EXAMPLE001', vin: '1FUJGLDR0CSBP0001' } }
