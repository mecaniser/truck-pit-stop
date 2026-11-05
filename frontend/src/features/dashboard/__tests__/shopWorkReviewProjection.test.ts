import { describe, expect, it } from 'vitest'
import { projectShopWorkReviews, type ReviewSource } from '../shopWorkReviewProjection'
import { shopWorkBoardUrl, shopWorkDestinationUrl, shopWorkReturnUrl } from '../shopWorkNavigation'
import type { ShopWorkOverviewData } from '../ShopWorkOverview'
import type { StaffVisitRequest } from '@/features/appointments/visit-requests'
import type { StaffBooking } from '@/features/appointments/booking-fulfillment'
import type { ZelleReviewRow } from '../useZelleReviewQueue'
const source = <T,>(rows: T[] = [], overrides: Partial<ReviewSource<T>> = {}): ReviewSource<T> => ({ rows, allowed: true, loading: false, failed: false, ...overrides })
const base: ShopWorkOverviewData = { as_of: '2026-11-04T16:00:00Z', timezone: 'America/New_York', scope: 'shop', active_jobs: 0, sources: [], actions: [], upcoming: [], actions_total: 0, upcoming_total: 0, has_more_actions: false, has_more_upcoming: false }
const visit = (overrides: Partial<StaffVisitRequest> = {}): StaffVisitRequest => ({ id: 'visit-a', request_reference: 'VR-A', version: 1, status: 'requested', customer: { id: 'customer-a', company_name: 'North Fleet', display_name: 'Alex Driver', email: null, phone: null }, service: { id: 'service-a', name: 'Inspection' }, vehicle: { id: 'vehicle-a', unit_number: '12', year: 2020, make: 'Volvo', model: 'VNR', license_plate: null }, preferred_date: '2026-11-05', accepted_arrival_date: null, customer_notes: null, internal_review_note: null, created_at: '2026-11-04T12:00:00Z', reviewed_at: null, can_review: true, ...overrides })
const payment = (overrides: Partial<ZelleReviewRow> = {}): ZelleReviewRow => {
 const row: ZelleReviewRow = { kind: 'canonical_zelle_attempt', rail: 'zelle', resolution: null, invoice_id: 'invoice-a', repair_order_id: 'source-order', display_invoice_number: 'INV-7', customer_id: 'customer-b', customer_display_name: 'West Fleet', principal_amount: '168.44', attempt_id: 'attempt-a', settlement_id: 'settlement-a', settlement_version: 3, created_at: '2026-11-04T11:00:00Z', reported_at: null, report_status: 'unverified_request', review_mode: 'canonical_attempt', can_confirm: true, ...overrides }
 if (row.kind !== 'legacy_zelle_submission' && overrides.resolution === undefined) row.resolution = { attempt_id: row.attempt_id!, invoice_id: row.invoice_id, attempt_version: 2, settlement_version: 3, rail: row.rail, requested_principal: row.principal_amount, currency: 'USD', attempt_state: 'pending', checkout_status: row.rail === 'card' ? 'review_required' : 'transfer_reported', reservation_amount: row.principal_amount, can_retry: false, actions: { cancel_unsent: false, check_provider_status: false, request_review: false, release_with_terminal_evidence: false, record_late_receipt: false }, block_reason: null, resolution_notice: null, review_status: 'none' }
 return row
}
const project = (visits = source<StaffVisitRequest>(), payments = source<ZelleReviewRow>(), reservations = source<StaffBooking>()) => projectShopWorkReviews(base, false, visits, reservations, payments)
describe('Shop Work review composition', () => {
  it('retains visit and exact invoice review tasks with zero active jobs', () => {
    const result = project(source([visit()]), source([payment()]))
    expect(result.active_jobs).toBe(0)
    expect(result.actions_total).toBe(2)
    expect(result.actions.map(item => item.id)).toEqual(['payment:attempt-a', 'visit:visit-a'])
    expect(result.actions[0]).toMatchObject({ title: 'West Fleet', destination: { kind: 'payment_review', id: 'attempt-a' } })
    expect(result.actions[0].reason).toContain('$168.44')
    expect(result.actions[0].reason).toContain('Request awaiting verification')
    expect(result.actions[1].reason).toContain('Requested Nov 5, 2026')
    expect(result.actions[1].reason).toContain('Unit #12')
    expect(result.upcoming).toEqual([])
  })
  it('adds no task or banner surrogate when both queues are empty', () => {
    const result = project()
    expect(result.actions).toEqual([]); expect(result.upcoming).toEqual([]); expect(result.actions_total).toBe(0)
    expect(result.sources.every(item => item.state === 'ready')).toBe(true)
  })
  it('keeps accepted arrival dates in Coming up without fabricating a start time', () => {
    const result = project(source([visit({ status: 'accepted', accepted_arrival_date: '2026-11-06' })]))
    expect(result.actions).toEqual([])
    expect(result.upcoming[0]).toMatchObject({ due_at: '2026-11-06', due_kind: 'visit_arrival', action_label: 'Open accepted visit' })
  })
  it.each(['declined', 'withdrawn', 'fulfilled'] as const)('removes %s requests from actionable and upcoming work', status => {
    const result = project(source([visit({ status })])); expect(result.actions).toEqual([]); expect(result.upcoming).toEqual([])
  })
  it('includes confirmed reservations and excludes unpaid, cancelled and review-only bookings', () => {
    const booking = { id: 'booking-a', service_name: 'Inspection', confirmation_number: 'BK-1', scheduled_at: '2026-11-06T15:00:00Z', status: 'confirmed', booking_payment_state: 'paid' } as StaffBooking
    const result = project(source(), source(), source([booking, { ...booking, id: 'hold', booking_payment_state: 'unpaid_hold' }, { ...booking, id: 'review', booking_payment_state: 'payment_received_review' }, { ...booking, id: 'cancelled', status: 'cancelled' }]))
    expect(result.upcoming.map(item => item.id)).toEqual(['reservation:booking-a'])
    expect(result.upcoming[0].destination).toEqual({ kind: 'reservation', id: 'booking-a', view: null })
  })
  it('ignores warm rows when a source is failed or permission is lost', () => {
    for (const state of [{ failed: true }, { allowed: false }, { loading: true }]) {
      const result = project(source([visit()], state), source([payment()], state))
      expect(result.actions).toEqual([]); expect(result.sources.slice(0, 1).every(s => s.state !== 'ready')).toBe(true)
    }
  })
  it('retains available reviews even if the original overview read fails', () => {
    const result = projectShopWorkReviews(undefined, true, source([visit()]), source(), source([payment()]))
    expect(result.actions).toHaveLength(2); expect(result.sources[0].state).toBe('unavailable'); expect(result.active_jobs).toBeNull()
  })
  it('does not turn a nonconfirmable request into a live review action', () => {
    expect(project(source(), source([payment({ can_confirm: false })])).actions[0].actionable).toBe(false)
    expect(project(source(), source([payment({ principal_amount: 'invalid' })])).actions[0].actionable).toBe(false)
  })
  it('preserves the separate legacy repair-order review path', () => {
    const result = project(source(), source([payment({ kind: 'legacy_zelle_submission', review_mode: 'legacy_invoice', attempt_id: null, report_status: 'legacy_report' })]))
    expect(result.actions[0].destination).toEqual({ kind: 'repair_order', id: 'source-order', view: 'needs_action' })
  })
  it('preserves exact record and return marker through request and reservation links', () => {
    for (const kind of ['visit_request', 'reservation'] as const) {
      const task = `attention:visit:request-a`
      const url = new URL(shopWorkDestinationUrl({ kind, id: 'request-a', view: null }, task), 'https://example.test')
      expect(url.searchParams.get(kind === 'visit_request' ? 'request' : 'appointment_id')).toBe('request-a')
      expect(shopWorkReturnUrl(url.searchParams)).toBe(shopWorkBoardUrl(task))
    }
    expect(shopWorkDestinationUrl({ kind: 'payment_review', id: 'attempt-a', view: null }, 'attention:payment:attempt-a')).toBe('/dashboard?task=attention%3Apayment%3Aattempt-a&work_view=overview&payment_review=attempt-a')
  })
})

describe('combined payment review board integration', () => {
 it('makes a bound card review actionable without manual confirmation authority', () => {
  const result = project(source(), source([payment({ kind: 'canonical_card_attempt', rail: 'card', can_confirm: false })]))
  expect(result.actions[0]).toMatchObject({ actionable: true, action_label: 'Review card payment', destination: { kind: 'payment_review', id: 'attempt-a' } })
  expect(result.actions[0].reason).toContain('Card payment needs review')
 })
 it.each(['missing', 'wrong invoice', 'wrong attempt', 'wrong rail'] as const)('does not authorize card review from %s projection', invalid => {
  const row = payment({ kind: 'canonical_card_attempt', rail: 'card', can_confirm: false })
  if (invalid === 'missing') row.resolution = null
  else if (row.resolution) row.resolution = { ...row.resolution, ...(invalid === 'wrong invoice' ? { invoice_id: 'foreign' } : invalid === 'wrong attempt' ? { attempt_id: 'other' } : { rail: 'zelle' }) }
  expect(project(source(), source([row])).actions[0].actionable).toBe(false)
 })
})
