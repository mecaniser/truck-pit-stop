import { format, isValid } from 'date-fns'
export type VisitRequestStatus = 'requested' | 'availability_review' | 'accepted' | 'declined' | 'withdrawn' | 'fulfilled'
export const visitRequestLabels: Record<VisitRequestStatus, string> = { requested: 'Awaiting shop review', availability_review: 'Shop is reviewing', accepted: 'Visit accepted', declined: 'Request declined', withdrawn: 'Request withdrawn', fulfilled: 'Visit checked in' }
export function arrivalDateLabel(value?: string | null) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return 'Date unavailable'
  const date = new Date(`${value}T12:00:00`)
  return isValid(date) ? format(date, 'MMM d, yyyy') : 'Date unavailable'
}
export interface StaffVisitRequest {
  id: string
  request_reference: string
  status: VisitRequestStatus
  version: number
  customer: { id: string; display_name: string; company_name: string | null; email: string | null; phone: string | null }
  service: { id: string; name: string }
  vehicle: { id: string; unit_number: string | null; year: number | null; make: string; model: string; license_plate: string | null } | null
  preferred_date: string | null
  accepted_arrival_date: string | null
  customer_notes: string | null
  internal_review_note: string | null
  created_at: string
  reviewed_at: string | null
  can_review: boolean
  can_accept?: boolean
  can_decline?: boolean
  can_fulfill?: boolean
  can_withdraw?: boolean
}
export function requestVehicleLabel(vehicle: StaffVisitRequest['vehicle']) {
  if (!vehicle) return 'Vehicle not specified'
  return [vehicle.unit_number ? `Unit #${vehicle.unit_number}` : null, [vehicle.year, vehicle.make].filter(Boolean).join(' ') || 'Vehicle', vehicle.license_plate].filter(Boolean).join(' · ')
}
