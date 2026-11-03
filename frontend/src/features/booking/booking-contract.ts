import type { Appointment } from '@/types'

export interface BookingCapability {
  available: boolean
  provider: 'quickbooks_payments' | 'stripe_connect' | null
  message: string
  token_url?: string | null
  shop_timezone: string
  currency: string
}
export interface BookingReservation extends Appointment {
  booking_kind: 'reserve'
  version: number
  price_snapshot_sha256: string
  hold_expires_at: string
  booking_payment_state: string
  currency: string
  payment_attempt_id?: string | null
  payment_attempt_state?: string | null
  payment_provider?: 'quickbooks_payments' | 'stripe_connect' | null
  receipt?: { id?: string; amount?: string; refunded_amount?: string; currency?: string } | null
}
export interface BookingPaymentResult {
  attempt_id: string
  provider: 'quickbooks_payments' | 'stripe_connect'
  state: string
  booking_status: string
  payment_state?: string
  booking_payment_state?: string
  client_secret?: string
  stripe_account_id?: string
  appointment_version: number
  amount: string
  currency: string
  hold_expires_at: string
  receipt?: { id?: string; amount?: string; refunded_amount?: string; currency?: string } | null
}
export interface VisitRequestResult {
  id: string
  booking_kind: 'request'
  request_reference: string
  status: 'requested' | 'availability_review' | 'accepted' | 'declined' | 'withdrawn' | 'fulfilled'
  version?: number
  accepted_arrival_date?: string | null
  customer_notes?: string | null
  fulfilled_repair_order_id?: string | null
  preferred_date: string | null
  service_id?: string
  service_name?: string
  vehicle_id?: string | null
  created_at?: string
}
