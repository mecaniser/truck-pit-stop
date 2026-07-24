export interface DuplicateVinVehicle {
  id: string
  vin?: string | null
  unit_number?: string | null
  year?: number | null
  make?: string | null
  model?: string | null
  license_plate?: string | null
  owner_lessor_name?: string | null
  operating_authority_name?: string | null
  default_invoice_recipient_name?: string | null
}

export interface DuplicateVinConflict {
  code: 'duplicate_vin'
  message: string
  vehicle?: DuplicateVinVehicle | null
}

export function duplicateVinConflict(error: any): DuplicateVinConflict | null {
  const detail = error?.response?.data?.detail
  return detail?.code === 'duplicate_vin' ? detail as DuplicateVinConflict : null
}

export function duplicateVinTruckLabel(vehicle?: DuplicateVinVehicle | null): string {
  if (!vehicle) return 'an existing truck'
  return [
    vehicle.unit_number ? `Unit ${vehicle.unit_number}` : null,
    vehicle.year,
    vehicle.make,
    vehicle.model,
  ].filter(Boolean).join(' · ') || 'an existing truck'
}
