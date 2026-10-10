export type DriverSafetyBand = 'red' | 'yellow' | 'green' | 'unknown'
export type DriverRecordSection = 'available' | 'unavailable' | 'empty'

export interface DriverRecordSummary {
  capture_id: string
  provider_driver_id: string
  driver_name: string
  identity_basis: 'motive_current_assignment'
  source_company_id: string
  provider_vehicle_id: string
  local_driver_name: string | null
  local_assignment_revision: number
  assignment_verified_at: string
  safety_score: number | null
  safety_band: DriverSafetyBand
  safety_band_label: string | null
  safety_period_text: string | null
  last_checked_at: string
  coverage: 'partial' | 'complete'
  stale: boolean
}

export interface DriverRecordDetail extends DriverRecordSummary {
  safety: {
    score: number | null
    band: DriverSafetyBand
    band_label: string | null
    period_text: string | null
    coaching_label: string | null
    top_behaviors: { behavior: string; score_impact: number | null }[]
    history: { period_text: string; score: number }[]
  }
  fuel: {
    period_text: string | null
    utilization_percent: number | null
    active_time_text: string | null
    idle_time_text: string | null
    metrics: { label: string; value: string; unit: string | null }[]
  }
  coaching: { status_label: string | null; open_count: number | null; last_coached_text: string | null }
  recent_events: { occurred_at_text: string | null; behavior: string; severity: string | null; status: string | null; vehicle_label: string | null; location: string | null }[]
  sections: Record<'safety' | 'fuel' | 'coaching' | 'recent_events', DriverRecordSection>
  unavailable_reasons: string[]
  source_timezone: string | null
}

export interface DriverRecordResponse {
  vehicle_id: string
  source: 'motive_dashboard'
  availability: 'unknown' | 'available' | 'assignment_unverified'
  unavailable_reason: 'no_capture' | 'directory_missing' | 'provider_assignment_unverified' | 'local_assignment_changed' | 'vehicle_identity_changed' | null
  record: DriverRecordDetail | null
}
