import type { DriverRecordDetail, DriverRecordResponse } from '../driverRecordTypes'
import type { BoardTruck } from '../types'

export const driverRecord: DriverRecordDetail = {
  capture_id: 'synthetic-capture', provider_driver_id: 'synthetic-driver', driver_name: 'Example Driver',
  safety_score: 82, safety_band: 'red', safety_band_label: 'Fair (50–84)', safety_period_text: 'Sep 28 – Oct 4, 2026',
  last_checked_at: '2026-10-09T16:00:00Z', coverage: 'partial', stale: false,
  safety: { score: 82, band: 'red', band_label: 'Fair (50–84)', period_text: 'Sep 28 – Oct 4, 2026', coaching_label: 'Coaching', top_behaviors: [{ behavior: 'Close following', score_impact: -9 }, { behavior: 'Stop sign violation', score_impact: -4.7 }, { behavior: 'Speeding', score_impact: -4 }], history: [{ period_text: 'Sep 21 – 27, 2026', score: 78 }] },
  fuel: { period_text: 'Last 30 days', utilization_percent: 41.4, active_time_text: '68h 14m', idle_time_text: '96h 26m', metrics: [{ label: 'Fuel efficiency', value: '6.2', unit: 'mpg' }] },
  coaching: { status_label: 'Driver needs coaching', open_count: 4, last_coached_text: 'Never coached' },
  recent_events: [{ occurred_at_text: 'Oct 9, 2026, 2:29 PM', behavior: 'Stop sign violation', severity: 'N/A', status: 'Pending review', vehicle_label: 'TEST-1', location: null }, { occurred_at_text: 'Oct 9, 2026, 1:43 PM', behavior: 'Close following', severity: 'N/A', status: 'Pending review', vehicle_label: 'TEST-1', location: 'Example County, SC' }],
  sections: { safety: 'available', fuel: 'available', coaching: 'available', recent_events: 'available' },
  unavailable_reasons: ['Recent events cover the visible rows only.'], source_timezone: null,
}
export const driverTruck = {
  id: 'synthetic-truck', unit_number: 'TEST-1', year: 2020, make: 'VOLVO', model: 'VNR', body_type: 'Truck-Tractor',
  driver_name: 'Example Driver', driver_phone: '(704) 555-0123', driver_record: driverRecord,
  board_membership_customer_id: 'synthetic-company', board_membership_company_name: 'Example Fleet', owner_company_name: 'Example Fleet',
  status: 'active', moving: false, odometer: 120000, pm_interval_miles: 25000, pm_remaining: 20433, next_pm_miles: 145000, open_work_order_count: 0, open_incident_count: 0,
} satisfies BoardTruck
export const driverResponse: DriverRecordResponse = { vehicle_id: driverTruck.id, source: 'motive_dashboard', availability: 'available', record: driverRecord }
