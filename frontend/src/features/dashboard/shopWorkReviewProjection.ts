import type { StaffVisitRequest } from '@/features/appointments/visit-requests'
import { arrivalDateLabel, requestVehicleLabel } from '@/features/appointments/visit-requests'
import type { StaffBooking } from '@/features/appointments/booking-fulfillment'
import { formatMoney, moneyToCents } from '@/features/payments/money'
import type { OverviewSource, OverviewSourceStatus, ShopWorkItem, ShopWorkOverviewData } from './ShopWorkOverview'
import type { ZelleReviewRow } from './useZelleReviewQueue'

export interface ReviewSource<T> {
  allowed: boolean
  rows: T[]
  loading: boolean
  failed: boolean
}
const sourceStatus = <T,>(id: OverviewSource, source: ReviewSource<T>): OverviewSourceStatus => ({
  id, state: !source.allowed ? 'restricted' : source.failed ? 'unavailable' : source.loading ? 'loading' : 'ready',
  reason: source.loading ? 'checking' : null, checked_at: null, total: null, shown: 0, has_more: false,
})
const baseItem = (id: string, source: OverviewSource): ShopWorkItem => ({
  id, source, destination: { kind: 'visit_request', id, view: null }, title: '', reason: '', action_label: '',
  status: '', created_at: null, due_at: null, due_kind: null, evidence: 'verified', quantity: null, related_repair_order_ids: [],
})

/** Compose existing authorized reads. A failed source never becomes an empty success. */
export function projectShopWorkReviews(base: ShopWorkOverviewData | undefined, baseFailed: boolean, visits: ReviewSource<StaffVisitRequest>, reservations: ReviewSource<StaffBooking>, payments: ReviewSource<ZelleReviewRow>): ShopWorkOverviewData {
  const result: ShopWorkOverviewData = base ? { ...base, actions: [...base.actions], upcoming: [...base.upcoming], sources: [...base.sources] } : {
    as_of: '', timezone: null, scope: 'shop', active_jobs: null, actions_total: null, upcoming_total: null,
    actions: [], upcoming: [], sources: [{ ...sourceStatus('repairs', { allowed: true, rows: [], failed: baseFailed, loading: !baseFailed }) }], has_more_actions: false, has_more_upcoming: false,
  }
  result.sources.push(sourceStatus('visits', visits), sourceStatus('reservations', reservations), sourceStatus('payments', payments))
  const added: ShopWorkItem[] = []
  if (visits.allowed && !visits.failed && !visits.loading) for (const row of visits.rows) {
    const item: ShopWorkItem = {
      ...baseItem(`visit:${row.id}`, 'visits'), destination: { kind: 'visit_request', id: row.id, view: null },
      title: row.customer.company_name || row.customer.display_name,
      reason: `${row.service.name} · ${requestVehicleLabel(row.vehicle)}`, status: row.status, created_at: row.created_at,
      action_label: 'Review visit request',
    }
    if (['requested', 'availability_review'].includes(row.status)) {
      item.reason += ` · ${row.preferred_date ? `Requested ${arrivalDateLabel(row.preferred_date)}` : 'No date preference'}`
      added.push(item)
    } else if (row.status === 'accepted' && row.accepted_arrival_date) {
      result.upcoming.push({ ...item, action_label: 'Open accepted visit', due_at: row.accepted_arrival_date, due_kind: 'visit_arrival' })
    }
  }
  if (reservations.allowed && !reservations.failed && !reservations.loading) for (const row of reservations.rows) {
    // A hold, pending payment or cancelled reservation is not a confirmed commitment.
    if (row.status !== 'confirmed' || (row.booking_payment_state && row.booking_payment_state !== 'paid')) continue
    result.upcoming.push({ ...baseItem(`reservation:${row.id}`, 'reservations'),
      destination: { kind: 'reservation', id: row.id, view: null },
      title: row.prepayment?.customer.company_name || row.prepayment?.customer.display_name || row.service_name,
      reason: `${row.service_name} · ${row.confirmation_number}`, action_label: 'Open reservation',
      status: row.status, created_at: row.created_at, due_at: row.scheduled_at, due_kind: 'reservation_start',
    })
  }
  if (payments.allowed && !payments.failed && !payments.loading) for (const row of payments.rows) {
    const canonical = row.kind === 'canonical_zelle_attempt' && row.review_mode === 'canonical_attempt' && !!row.attempt_id
    const legacy = row.kind === 'legacy_zelle_submission' && row.review_mode === 'legacy_invoice' && !!row.repair_order_id
    const cents = moneyToCents(row.principal_amount)
    const actionable = row.can_confirm && (canonical ? cents !== null && cents > 0n : legacy)
    const provenance = row.report_status === 'explicit_report' ? 'Customer reported transfer sent' : row.report_status === 'legacy_report' ? 'Reported transfer' : 'Request awaiting verification'
    added.push({ ...baseItem(`payment:${row.attempt_id || row.invoice_id}`, 'payments'),
      destination: legacy ? { kind: 'repair_order', id: row.repair_order_id!, view: 'needs_action' } : { kind: 'payment_review', id: row.attempt_id || row.invoice_id, view: null },
      title: row.customer_display_name, action_label: 'Review Zelle payment', actionable,
      reason: `Invoice ${row.display_invoice_number} · ${cents !== null && cents > 0n ? formatMoney(row.principal_amount) : 'Amount unavailable'} · ${provenance}`,
      status: row.report_status, created_at: row.reported_at || row.created_at,
    })
  }
  // Preserve the server's urgent repair ordering; new customer reviews precede routine stock work.
  const urgent = result.actions.filter(item => item.source === 'repairs')
  const routine = result.actions.filter(item => item.source !== 'repairs')
  added.sort((a, b) => (a.created_at || '').localeCompare(b.created_at || '') || a.id.localeCompare(b.id))
  result.actions = [...urgent, ...added, ...routine]
  result.upcoming.sort((a, b) => (a.due_at || '').localeCompare(b.due_at || '') || a.id.localeCompare(b.id))
  const incomplete = [visits, reservations, payments].some(source => source.allowed && (source.failed || source.loading))
  result.actions_total = incomplete || base?.actions_total == null ? null : base.actions_total + added.length
  result.upcoming_total = incomplete || base?.upcoming_total == null ? null : base.upcoming_total + result.upcoming.length - base.upcoming.length
  return result
}
