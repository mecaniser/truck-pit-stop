import type { BoardTruck } from './types'
import type { DriverRecordSummary } from './driverRecordTypes'

export type DriverTruck = Pick<BoardTruck, 'id' | 'driver_name' | 'driver_phone' | 'driver_record' | 'board_membership_customer_id'>

/** The API verifies provider assignment; a local alias is only a contact snapshot. */
export function currentDriverRecord(truck: DriverTruck): DriverRecordSummary | null {
  const record = truck.driver_record
  if (!record || record.identity_basis !== 'motive_current_assignment'
    || !record.capture_id || !record.source_company_id || !record.provider_vehicle_id || !record.provider_driver_id
    || !record.driver_name?.trim() || !record.assignment_verified_at
    || !Number.isInteger(record.local_assignment_revision) || record.local_assignment_revision < 0
    || (record.local_driver_name ?? null) !== (truck.driver_name ?? null)) return null
  return record
}

export function currentDriverName(truck: DriverTruck): string | null {
  return currentDriverRecord(truck)?.driver_name ?? truck.driver_name ?? null
}

export function sameDriverContext(summary: DriverRecordSummary, detail: DriverRecordSummary): boolean {
  return (['identity_basis', 'capture_id', 'source_company_id', 'provider_vehicle_id', 'provider_driver_id', 'driver_name', 'local_driver_name', 'local_assignment_revision', 'assignment_verified_at'] as const)
    .every(key => summary[key] === detail[key])
}
