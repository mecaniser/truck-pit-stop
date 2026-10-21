export type CostStatus = 'complete' | 'partial' | 'unavailable' | 'not_applicable'
export interface Expense { status: CostStatus; known_cost: string | null; line_count: number; missing_cost_line_count: number }
export interface Coverage { recorded_seconds: number; costed_seconds: number; unrated_seconds: number; pre_activation_seconds: number; held_seconds: number; open_session_count: number }
export interface ContributionRow {
  order_id: string; order_number: string; customer_name: string; type: string; status: string; cohort_at: string; date_basis: string
  business_classification: 'real' | 'test' | 'unknown'; source_owner: 'native' | 'ets_history' | 'review_required'; review_status: 'none' | 'current' | 'stale'; review_version: number; cost_status: CostStatus
  revenue: { status: string; basis: string; net_direct_revenue: string | null; issued_discount: string | null; tax: string | null; fees: string | null; supplies: string | null; hold_reasons: string[] }
  labor: Coverage & { status: CostStatus; known_cost: string | null; operation_attributed_seconds: number; general_ro_seconds: number; hold_reasons: string[] }
  parts: Expense; sublet: Expense; direct_contribution: string | null; margin_pct: string | null; hold_reasons: string[]; drilldown: string
}
export interface ContributionReport {
  contract_version: 1; calculation_version: string; generated_at: string; shop_timezone: string; activation_at: string; activation_local_date: string; from: string; to: string; next_cursor: string | null
  summary: Coverage & { order_count: number; real_count: number; test_count: number; unknown_count: number; history_count: number; complete_row_count: number; partial_row_count: number; unavailable_row_count: number; incomplete_row_count: number; reviewed_complete_contribution: string | null; known_recorded_direct_cost: string | null; is_complete: boolean }
  rows: ContributionRow[]
}
export interface CostSegment { effective_from: string; effective_to: string | null; hourly_cost: string; inclusions: string }
export interface TechnicianPolicy { mechanic_id: string; mechanic_name: string; is_active: boolean; version: number; revision_id: string | null; history?: Array<{ version: number; revision_id: string; approved_at: string }>; next_cursor?: string | null; policy: null | { activation_at: string; activation_local_date: string; shop_timezone: string; segments: CostSegment[]; reason: string } }
export interface PolicyList { items: TechnicianPolicy[]; next_cursor: string | null }
export interface ContributionDetail {
  row: ContributionRow; source_fingerprint: string; policy_heads_digest: string
  review: null | { version: number; time_capture: string; reviewed_exception_ids?: string[] }
  sessions: Array<{ id: string; mechanic_id: string; mechanic_name: string; started_at: string; ended_at: string | null; recorded_seconds: number; costed_seconds: number; known_cost: string | null; hold_reasons: string[] }>
  separate_shop_time: { scope: 'selected_job_timer_window'; scope_windows: Array<{ mechanic_id: string; started_at: string; ended_at: string }>; time_status: 'complete' | 'partial' | 'unavailable'; misc_seconds: number | null; idle_seconds: number | null; break_seconds: number | null; cost_status: 'unavailable' }
}
