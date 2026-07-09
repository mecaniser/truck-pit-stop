/**
 * Vehicle display label. Bulk imports sometimes have no make/model on file
 * (only a unit number), and the placeholder value for those fields is the
 * literal string "UNKNOWN" — never show that to a user. Falls back to
 * "Equipment" (optionally with the unit number) when make and/or model are
 * missing or the "UNKNOWN" placeholder — not "Truck", since a unit can just
 * as easily be a trailer or other equipment type.
 */
export interface VehicleNameFields {
  year?: number | null
  make?: string | null
  model?: string | null
  unit_number?: string | null
}

function isKnown(value?: string | null): value is string {
  return !!value && value.trim().toUpperCase() !== 'UNKNOWN'
}

/**
 * "2021 FREIGHTLINER Cascadia", "Hino", or "Equipment · Unit 05" when both
 * are unknown. Pass `includeYear: false` when the caller already renders the
 * year separately (e.g. its own label above this one) to avoid repeating it.
 */
export function vehicleDisplayLabel(vehicle: VehicleNameFields, options?: { includeYear?: boolean }): string {
  const includeYear = options?.includeYear ?? true
  const knownMake = isKnown(vehicle.make) ? vehicle.make!.trim() : null
  const knownModel = isKnown(vehicle.model) ? vehicle.model!.trim() : null

  if (!knownMake && !knownModel) {
    return vehicle.unit_number ? `Equipment · Unit ${vehicle.unit_number}` : 'Equipment'
  }

  const year = includeYear && vehicle.year ? `${vehicle.year} ` : ''
  return `${year}${[knownMake, knownModel].filter(Boolean).join(' ')}`.trim()
}
