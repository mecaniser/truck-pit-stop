export type InspectionStatus = 'scheduled' | 'completed' | 'cancelled' | 'missed'
export type InspectionResult = 'pass' | 'attention' | 'fail'
export type InspectionItemResult = 'pending' | 'pass' | 'fail' | 'na'
export type IncidentSeverity = 'low' | 'medium' | 'high' | 'critical'
export type IncidentStatus = 'open' | 'in_progress' | 'resolved'

export interface FleetVehicle {
  id: string
  make: string
  model: string
  year?: number | null
  unit_number?: string | null
  vin?: string | null
  license_plate?: string | null
  mileage?: number | null
  last_inspection_at?: string | null
  last_inspection_result?: InspectionResult | null
  next_inspection_due?: string | null
  inspection_overdue: boolean
  open_incident_count: number
}

export interface FleetSummary {
  total_vehicles: number
  inspections_due: number
  inspections_overdue: number
  open_incidents: number
}

export interface InspectionItem {
  id: string
  category: string
  label: string
  result: InspectionItemResult
  note?: string | null
}

export interface Inspection {
  id: string
  vehicle_id: string
  inspector_id?: string | null
  status: InspectionStatus
  result?: InspectionResult | null
  scheduled_for: string
  performed_at?: string | null
  odometer?: number | null
  notes?: string | null
  created_at: string
  vehicle_make: string
  vehicle_model: string
  vehicle_year?: number | null
  vehicle_unit_number?: string | null
}

export interface InspectionDetail extends Inspection {
  items: InspectionItem[]
}

export interface Incident {
  id: string
  vehicle_id: string
  reported_by_id?: string | null
  occurred_at: string
  location?: string | null
  severity: IncidentSeverity
  status: IncidentStatus
  description: string
  resolution_notes?: string | null
  resolved_at?: string | null
  repair_order_id?: string | null
  created_at: string
  vehicle_make: string
  vehicle_model: string
  vehicle_year?: number | null
  vehicle_unit_number?: string | null
}

// ---- Fleet board (design) ----
export type TruckStatus = 'active' | 'shop' | 'pm' | 'parts' | 'draft' | 'yard' | 'available' | 'out_of_service'

export interface BoardWorkOrder {
  id: string
  repair_order_id: string
  status: string
  summary?: string | null
  mechanic?: string | null
}

export interface BoardTruck {
  id: string
  unit_number?: string | null
  year?: number | null
  make: string
  model: string
  brand_short?: string | null
  body_type?: string | null
  vin?: string | null
  plate?: string | null
  status: TruckStatus
  driver_name?: string | null
  odometer?: number | null
  pm_interval_miles: number
  next_pm_miles?: number | null
  pm_remaining?: number | null
  pm_interval_days?: number
  pm_due_date?: string | null
  pm_days_remaining?: number | null
  location_label?: string | null
  location_city?: string | null
  lat?: number | null
  lng?: number | null
  moving: boolean
  speed_mph?: number | null
  heading?: string | null
  assigned_mechanic?: string | null
  work_order?: BoardWorkOrder | null
  open_work_order_count: number
  open_incident_count: number
  status_override?: string | null
}

export interface FleetStats {
  total: number
  active: number
  shop: number
  pm: number
  parts: number
  open_wo: number
  incidents_total: number
}

export interface FleetBoard {
  trucks: BoardTruck[]
  stats: FleetStats
}

export interface HistoryEntry {
  id: string
  date?: string | null
  kind: 'PM' | 'Repair' | 'Inspection'
  odometer?: number | null
  summary?: string | null
  mechanic?: string | null
  cost?: number | null
}

export interface PartEntry {
  id: string
  name: string
  date?: string | null
  odometer?: number | null
  mechanic?: string | null
  warranty_until?: string | null
  warranty_miles?: number | null
  active: boolean
}

export interface IncidentEntry {
  id: string
  date: string
  type: string
  severity: IncidentSeverity
  status: IncidentStatus
  location?: string | null
  note?: string | null
  repair_order_id?: string | null
}

export interface NearestUnit {
  id: string
  unit_number?: string | null
  city?: string | null
  status: TruckStatus
  miles: number
}

export interface TruckDetail {
  truck: BoardTruck
  open_work_orders: BoardWorkOrder[]
  driver_phone?: string | null
  lifetime_spend: number
  incidents_count: number
  crew: string[]
  history: HistoryEntry[]
  parts: PartEntry[]
  incidents: IncidentEntry[]
  nearest: NearestUnit[]
}
