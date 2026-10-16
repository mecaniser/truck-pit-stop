import { describe, expect, it } from 'vitest'
import { currentDriverRecord, sameDriverContext } from '../driverIdentity'
import type { DriverTruck } from '../driverIdentity'
import type { DriverRecordSummary } from '../driverRecordTypes'

const record: DriverRecordSummary = {
  capture_id: 'capture', provider_driver_id: 'driver', driver_name: 'Provider driver',
  identity_basis: 'motive_current_assignment', vehicle_identity_basis: 'reviewed_provider_binding', vehicle_identity_binding_id: 'reviewed-binding',
  source_company_id: 'company', provider_vehicle_id: 'vehicle', local_driver_name: 'Local alias',
  local_assignment_revision: 3, assignment_verified_at: '2026-10-16T20:00:00Z',
  safety_score: 88, safety_band: 'yellow', last_checked_at: '2026-10-16T20:00:00Z', coverage: 'partial', stale: false,
}
const truck: DriverTruck = { id: 'truck', driver_name: 'Local alias', driver_phone: null, board_membership_customer_id: 'fleet', driver_record: record }

describe('reviewed source vehicle identity', () => {
  it('accepts a reviewed binding with unchanged current assignment', () => {
    expect(currentDriverRecord(truck)).toBe(record)
    expect(sameDriverContext(record, { ...record })).toBe(true)
  })
  it('requires the binding proof and rejects stale local assignment', () => {
    expect(currentDriverRecord({ ...truck, driver_record: { ...record, vehicle_identity_binding_id: null } })).toBeNull()
    expect(currentDriverRecord({ ...truck, driver_name: 'Another driver' })).toBeNull()
    expect(currentDriverRecord({ ...truck, driver_record: { ...record, vehicle_identity_basis: 'verified_vin' } })).toBeNull()
  })
  it('rejects a detail from a different binding, source vehicle or assignment', () => {
    expect(sameDriverContext(record, { ...record, vehicle_identity_binding_id: 'different' })).toBe(false)
    expect(sameDriverContext(record, { ...record, provider_vehicle_id: 'different' })).toBe(false)
    expect(sameDriverContext(record, { ...record, local_assignment_revision: 4 })).toBe(false)
  })
  it('keeps genuine-VIN summaries compatible across an additive nullable field', () => {
    const genuine = { ...record, vehicle_identity_basis: 'verified_vin' as const, vehicle_identity_binding_id: undefined }
    expect(currentDriverRecord({ ...truck, driver_record: genuine })).toBe(genuine)
    expect(sameDriverContext(genuine, { ...genuine, vehicle_identity_binding_id: null })).toBe(true)
  })
})
