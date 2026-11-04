import { moneyToCents } from '@/features/payments/money'
import type { Appointment, InvoicePaymentPresentation } from '@/types'
import type { StaffVisitRequest } from './visit-requests'
export interface BookingAccountingTask {
  id: string
  object_kind: 'booking_receipt_liability' | 'booking_receipt_application'
  state: 'awaiting_manual_ack' | 'externally_reconciled' | 'needs_review'
  version: number
  amount_minor: number
  currency: string
  evidence_snapshot_sha256: string
}
export interface BookingInvoicePreview {
  currency: string
  invoice_total_minor: number
  allocatable_principal_minor: number
  suggested_apply_minor: number
  remaining_minor: number
  invoice_economics_sha256: string
  block_reason?: { code: string; message: string } | null
}
export interface BookingPrepaymentView {
  appointment_id: string
  repair_order_id: string | null
  invoice_id?: string | null
  application_id?: string | null
  booking_version: number
  settlement_version?: number | null
  receipt: { id: string; version: number; provider?: 'quickbooks_payments' | 'stripe_connect'; currency: string; received_minor: number; refunded_minor: number; applied_minor: number; unapplied_minor: number | null }
  invoice_payment_summary?: InvoicePaymentPresentation | null
  invoice_preview?: BookingInvoicePreview | null
  accounting: { mode: string; state: string; review_task_id?: string | null; export_hold: boolean; tasks: BookingAccountingTask[] }
  shop_timezone: string
  customer: { id: string; display_name: string; company_name: string | null }
  vehicle: StaffVisitRequest['vehicle']
  refund_verification_pending?: boolean
  can_apply?: boolean
  application_block_reason?: { code: string; message: string } | null
}
export interface StaffBooking extends Appointment { prepayment?: BookingPrepaymentView | null }
export function minorLabel(value: unknown, currency = 'usd'): string {
  return Number.isSafeInteger(value) && Number(value) >= 0 && currency === 'usd'
    ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(value) / 100)
    : 'Unavailable'
}
export function validPrepayment(view: BookingPrepaymentView | null | undefined): view is BookingPrepaymentView {
  return !!view?.receipt?.id && !!view.accounting && Array.isArray(view.accounting.tasks) && view.receipt.currency === 'usd' && Number.isInteger(view.booking_version) && view.booking_version > 0 && Number.isInteger(view.receipt.version) && view.receipt.version > 0 && [view.receipt.received_minor, view.receipt.refunded_minor, view.receipt.applied_minor].every(amount => Number.isSafeInteger(amount) && amount >= 0) && (view.receipt.unapplied_minor === null || (Number.isSafeInteger(view.receipt.unapplied_minor) && view.receipt.unapplied_minor >= 0))
}
export function canApplyPrepayment(view: BookingPrepaymentView | null | undefined): boolean {
  const preview = view?.invoice_preview
  return validPrepayment(view) && view.receipt.unapplied_minor !== null && !view.refund_verification_pending && view.can_apply === true && view.accounting.mode === 'external_manual' && view.accounting.export_hold === true && !view.invoice_id && !view.application_id && !!view.repair_order_id && !!preview && preview.currency === 'usd' && !!preview.invoice_economics_sha256 && [preview.invoice_total_minor, preview.allocatable_principal_minor, preview.suggested_apply_minor, preview.remaining_minor].every(value => Number.isSafeInteger(value) && value >= 0) && preview.suggested_apply_minor > 0 && preview.suggested_apply_minor <= view.receipt.unapplied_minor && preview.suggested_apply_minor <= preview.allocatable_principal_minor
}
export function reservationLabel(appointment: Appointment): string {
  const states: Record<string, string> = { unpaid_hold: 'Checkout awaiting payment', payment_processing: 'Payment verification pending', expired_unpaid: 'Checkout expired', payment_received_review: 'Payment received · shop review needed', refund_pending: 'Refund review pending', refunded: 'Refund recorded', paid: appointment.status === 'cancelled' ? 'Cancelled · payment on record' : 'Verified prepayment' }
  return appointment.booking_payment_state ? states[appointment.booking_payment_state] || 'Reservation needs review' : appointment.status === 'confirmed' ? 'Scheduled visit' : appointment.status === 'cancelled' ? 'Cancelled' : 'Recorded visit'
}

export function decimalLabel(value: unknown): string {
  if (typeof value !== 'string' && typeof value !== 'number' && value !== null && value !== undefined) return 'Unavailable'
  const cents = moneyToCents(value)
  return cents === null ? 'Unavailable' : minorLabel(Number(cents))
}
export function bookingTimeLabel(value: string, timezone: string): string | null {
  try { return new Intl.DateTimeFormat('en-US', { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short', timeZone: timezone }).format(new Date(value)) } catch { return null }
}
