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
  is_warning_light?: boolean
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
  repair_order_id?: string | null  // work order created to fix failed items
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
  raw_status?: string
  summary?: string | null
  mechanic?: string | null
  is_pm?: boolean
}

export interface PMServiceEntry {
  service_id: string
  name: string
  duration_minutes: number
  parts_cost?: number
  sort_order: number
}

// The garage service-catalog item, as returned by GET /services.
export interface CatalogService {
  id: string
  name: string
  duration_minutes: number
  is_active: boolean
  category?: { id: string; name: string } | null
}

export interface BoardTruck {
  id: string
  unit_number?: string | null
  display_unit_number?: string | null
  year?: number | null
  make: string
  model: string
  brand_short?: string | null
  body_type?: string | null
  vin?: string | null
  plate?: string | null
  status: TruckStatus
  driver_name?: string | null
  driver_phone?: string | null
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
  pm_work_order?: BoardWorkOrder | null
  pm_services?: PMServiceEntry[]
  open_work_order_count: number
  open_incident_count: number
  status_override?: string | null
  warning_lights?: string[]
  fleet_customer_id?: string | null
  fleet_company_name?: string | null
  owner_customer_id?: string | null
  owner_company_name?: string | null
}

export interface DriverProfile {
  id: string
  user_id?: string | null
  employer_customer_id?: string | null
  first_name: string
  last_name: string
  phone?: string | null
  email?: string | null
  employee_number?: string | null
  employment_status: 'active' | 'inactive'
}

export interface LegacyDriverContact {
  name: string
  phone?: string | null
  vehicle_count: number
}

export interface VehicleDriverAssignment {
  vehicle_id: string
  custody_session_id: string
  custody_status: 'assigned' | 'active'
  custody_starts_at: string
  custody_acknowledged_at?: string | null
  driver: DriverProfile
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

export interface VehicleMergeSummary {
  id: string
  customer_id: string
  customer_name: string
  vin: string
  unit_number?: string | null
  make: string
  model: string
  year?: number | null
  license_plate?: string | null
  mileage?: number | null
  source?: string | null
  repair_order_count: number
  appointment_count: number
  inspection_count: number
  incident_count: number
}

export interface VehicleMergePreview {
  canonical: VehicleMergeSummary
  duplicate: VehicleMergeSummary
  match_basis: 'vin' | 'unit_number'
  match_value: string
  recommended_canonical_id: string
  warnings: string[]
}

export interface VehicleMergeResult {
  canonical_vehicle: { id: string }
  archived_vehicle_id: string
  merge_record_id: string
  moved: Record<string, number>
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
  photos?: FleetPhoto[]
}

export interface FleetPhoto {
  id: string
  image_url: string
  caption?: string | null
  uploaded_at: string
  uploader_name: string
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
  fleet_account_customer_id?: string | null
  fleet_account_company_name?: string | null
  fleet_account_contact_name?: string | null
  fleet_account_email?: string | null
  fleet_account_phone?: string | null
  fleet_account_billing_address?: string | null
  bill_to_customer_id?: string | null
  bill_to_company_name?: string | null
  bill_to_first_name?: string | null
  bill_to_last_name?: string | null
  bill_to_contact_name?: string | null
  bill_to_email?: string | null
  bill_to_phone?: string | null
  bill_to_billing_address?: string | null
  bill_to_billing_address_line1?: string | null
  bill_to_billing_address_line2?: string | null
  bill_to_billing_city?: string | null
  bill_to_billing_state?: string | null
  bill_to_billing_zip?: string | null
  bill_to_billing_country?: string | null
  bill_to_is_internal?: boolean
  bill_to_relationship_type?: string | null
  billing_contact_name?: string | null
  billing_contact_email?: string | null
  billing_contact_phone?: string | null
  bill_labor_at_customer_rate: boolean
  lifetime_spend: number
  incidents_count: number
  crew: string[]
  history: HistoryEntry[]
  parts: PartEntry[]
  incidents: IncidentEntry[]
  nearest: NearestUnit[]
}
