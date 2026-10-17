import { validDay } from '@/components/calendarGrid'
import { hours, whole, type Attestation, type Meter, type ServiceReading } from './contract'

export const emptyAttestation = (): AttestationDraft => ({ date: '', miles: '', hours: '', basis: 'staff_observed', confirmed: false, sources: {} })
export type AttestationDraft = { date: string; miles: string; hours: string; basis: 'staff_observed' | 'staff_reported'; confirmed: boolean; sources: Partial<Record<Meter, ServiceReading>> }
export function toAttestation(draft: AttestationDraft): Attestation {
  if (!validDay(draft.date) || !draft.confirmed) throw new Error('Confirm the actual service date and readings.')
  const miles = whole(draft.miles, 'service mileage'); const engineHours = hours(draft.hours)
  return { performed_on: draft.date, confirm_actual_service_readings: true, readings: {
    odometer_miles: draft.sources.odometer_miles ?? (miles === null ? null : { kind: 'manual', value: String(miles), basis: draft.basis, note: null }),
    engine_hours: draft.sources.engine_hours ?? (engineHours === null ? null : { kind: 'manual', value: engineHours, basis: draft.basis, note: null }),
  } }
}
