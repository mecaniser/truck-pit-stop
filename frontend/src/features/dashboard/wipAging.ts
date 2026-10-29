import { shortDuration } from '@/lib/elapsed'

export const WIP_CATEGORIES = ['approval', 'parts', 'technician', 'review', 'other_hold', 'active', 'preparation'] as const
export type WipCategory = typeof WIP_CATEGORIES[number]
export interface WipClock {
  state: 'known' | 'unknown' | 'not_applicable'
  since: string | null
  seconds: number | null
  issue: 'missing_timestamp' | 'future_timestamp' | 'inconsistent_evidence' | null
}
export interface WipAgingRow {
  id: string
  order_number: string
  status: string
  customer_name: string
  vehicle_info: string
  vehicle_unit_number: string | null
  category: WipCategory
  reason: 'waiting_for_parts' | 'approval_hold' | 'awaiting_customer_decision'
    | 'awaiting_acknowledgment' | 'ready_to_start' | 'technician_timing_unknown'
    | 'awaiting_quality_review' | 'need_more_info' | 'technician_switched'
    | 'other_hold' | 'work_in_progress' | 'prepare_estimate' | 'revise_estimate'
    | 'quote_not_sent' | 'quote_expired' | 'quote_evidence_unknown'
  hold_reason: string | null
  assignment: 'assigned' | 'unassigned' | 'unknown'
  technician_names: string[]
  order_age: WipClock
  current_wait: WipClock
  promised_finish_at: string | null
  overdue_seconds: number | null
  is_overdue: boolean
  action_lane: 'needs_action' | 'on_floor'
}
export interface WipFilters {
  search: string
  category: WipCategory | 'all'
  overdue_only: boolean
  timing: 'all' | 'known' | 'unknown'
  sort: 'priority' | 'oldest_wait' | 'oldest_order'
  offset: number
}
export const DEFAULT_WIP_FILTERS: WipFilters = {
  search: '', category: 'all', overdue_only: false, timing: 'all', sort: 'priority', offset: 0,
}
export interface WipAgingResponse {
  as_of: string
  timezone: string | null
  scope: 'shop' | 'assigned'
  filters: Omit<WipFilters, 'offset'>
  summary: {
    total_jobs: number
    category_counts: Record<WipCategory, number>
    overdue_jobs: number
    unknown_wait_jobs: number
  }
  filtered_total: number
  offset: number
  limit: number
  has_more: boolean
  items: WipAgingRow[]
}
export const WIP_LABELS: Record<WipCategory, string> = {
  approval: 'Approval', parts: 'Parts', technician: 'Technician', review: 'Quality review',
  other_hold: 'Other holds', active: 'In progress', preparation: 'Preparation',
}
export const WIP_REASONS: Record<WipAgingRow['reason'], string> = {
  waiting_for_parts: 'Waiting for parts', approval_hold: 'Approval hold',
  awaiting_customer_decision: 'Awaiting approval', awaiting_acknowledgment: 'Awaiting acknowledgment',
  ready_to_start: 'Ready to start', technician_timing_unknown: 'Awaiting technician',
  awaiting_quality_review: 'Awaiting review', need_more_info: 'Needs information',
  technician_switched: 'Technician switched jobs', other_hold: 'On hold', work_in_progress: 'Work in progress',
  prepare_estimate: 'Prepare estimate', revise_estimate: 'Revise estimate', quote_not_sent: 'Estimate not sent',
  quote_expired: 'Estimate expired', quote_evidence_unknown: 'Review estimate',
}

export function clockLabel(clock: WipClock): string {
  if (clock.state === 'not_applicable') return '—'
  if (clock.state !== 'known' || clock.seconds == null || !Number.isFinite(clock.seconds) || clock.seconds < 0) return 'Unknown'
  return clock.seconds < 60 ? '<1m' : shortDuration(clock.seconds * 1000)
}
