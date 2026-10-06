import { describe, expect, it } from 'vitest'
import type { BoardTruck } from './types'
import { checkFreshness, exampleObservation, makeCheckpoint, matchTruck, observationSchema, persistCheckpoint, readCheckpoint, verifyActor, verifyProjection, verifyReceipt } from './coordinateImportModel'
const actor = { id: '22222222-2222-4222-8222-222222222222', tenant_id: exampleObservation.expected_tenant_id, role: 'garage_owner', is_active: true }
const source = observationSchema.parse(exampleObservation)
const truck = { id: '33333333-3333-4333-8333-333333333333', vin: source.vin, board_membership_customer_id: '44444444-4444-4444-8444-444444444444' } as BoardTruck
const receiptFor = () => ({ id: '55555555-5555-4555-8555-555555555555', vehicle_id: truck.id, fleet_customer_id: truck.board_membership_customer_id!, captured_by_user_id: actor.id, captured_at: '2026-10-06T18:53:25Z', observed_at: null, source: 'motive_dashboard_manual' as const })
describe('coordinate import safety', () => {
 it('requires exact VIN and before/after company agreement', () => {
  expect(() => observationSchema.parse({ ...source, after: { ...source.after, company_id: 'OTHER' } })).toThrow()
  expect(() => matchTruck([{ ...truck, vin: '1FUJGLDR0CSBP0002' }], source)).toThrow()
  expect(() => matchTruck([truck, truck], source)).toThrow()
  expect(() => matchTruck([{ ...truck, board_membership_customer_id: null }], source)).toThrow()
 })
 it('rejects invalid coordinates and timezone-free timestamps', () => {
  for (const change of [{ lat: true }, { lng: null }, { lat: Infinity }, { observed_at: '2026-10-06T12:00:00' }]) expect(() => observationSchema.parse({ ...source, ...change })).toThrow()
 })
 it('preserves unknown time; rejects unchanged, older and uncertain recency', () => {
  expect(source.observed_at).toBeNull()
  expect(() => checkFreshness({ ...truck, telemetry: { location: { lat: source.lat, lng: source.lng } } } as BoardTruck, source)).toThrow(/unchanged/)
  const known = { ...truck, telemetry: { location: { observed_at: '2026-10-06T13:00:00Z' } } } as BoardTruck
  expect(() => checkFreshness(known, source)).toThrow(/recency/)
  expect(() => checkFreshness(known, { ...source, observed_at: '2026-10-06T12:00:00Z' })).toThrow(/older/)
 })
 it('rejects switched tenant, actor, inactive session and role', () => {
  for (const change of [{ tenant_id: 'other' }, { id: 'other' }, { is_active: false }, { role: 'fleet_manager' }]) expect(() => verifyActor({ ...actor, ...change }, actor, source.expected_tenant_id)).toThrow()
 })
 it('restores identical request after uncertain outcome and receipt replay; fails closed on quota or corruption', () => {
  const memory = new Map<string, string>(); const storage = { getItem: (k: string) => memory.get(k) ?? null, setItem: (k: string, v: string) => { memory.set(k, v) } }
  const checkpoint = makeCheckpoint(source, actor, truck)
  persistCheckpoint(storage, actor, checkpoint)
  expect(readCheckpoint(storage, actor)).toEqual(checkpoint)
  persistCheckpoint(storage, actor, { ...checkpoint, receipt: verifyReceipt(receiptFor(), checkpoint) })
  expect(readCheckpoint(storage, actor)?.payload).toEqual(checkpoint.payload)
  expect(() => persistCheckpoint({ ...storage, setItem: () => { throw Error('Quota') } }, actor, checkpoint)).toThrow('Quota')
  expect(() => readCheckpoint({ getItem: () => '{bad' }, actor)).toThrow()
  expect(() => readCheckpoint({ getItem: () => JSON.stringify({ ...checkpoint, payload: { ...checkpoint.payload, lat: 0 } }) }, actor)).toThrow()
 })
 it('distinguishes receipt identity and fleet projection failures', () => {
  const checkpoint = makeCheckpoint(source, actor, truck); const receipt = receiptFor()
  expect(() => verifyReceipt({ ...receipt, captured_by_user_id: '66666666-6666-4666-8666-666666666666' }, checkpoint)).toThrow()
  expect(verifyProjection([truck], checkpoint, receipt)).toBe(false)
  const projected = { ...truck, telemetry: { location: { lat: source.lat, lng: source.lng, snapshot_id: receipt.id } } } as BoardTruck
  expect(verifyProjection([projected], checkpoint, receipt)).toBe(true)
  expect(verifyProjection([{ ...projected, id: 'different' }], checkpoint, receipt)).toBe(false)
 })
})
