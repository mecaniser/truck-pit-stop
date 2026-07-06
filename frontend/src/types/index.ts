export type UserRole = 'super_admin' | 'garage_owner' | 'garage_admin' | 'mechanic' | 'receptionist' | 'fleet_manager' | 'customer'

export type RepairOrderStatus = 
  | 'draft'
  | 'quoted'
  | 'approved'
  | 'declined'
  | 'assigned'
  | 'acknowledged'
  | 'in_progress'
  | 'pending_review'
  | 'completed'
  | 'invoiced'
  | 'paid'
  | 'cancelled'

export type SuggestedNextAction =
  | 'clock_in'
  | 'end_break'
  | 'continue_ro'
  | 'stop_misc_pick_ro'
  | 'start_assigned_ro'
  | 'start_misc'
  | 'clock_out'

export type AttentionPriority = 'red' | 'yellow' | 'green'

export const ATTENTION_REASON_LABELS: Record<string, string> = {
  idle_extended: 'Idle over 15 min — no active timer',
  untimed_in_progress: 'In-progress RO has no timer running',
  clocked_out_during_shift: 'Clocked out during shift window',
  misc_with_ro_waiting: 'On misc timer with assigned RO waiting',
  break_extended: 'On break over 20 min',
  low_coverage: 'Work coverage below 60%',
  ro_on_hold: 'Repair order on hold',
}

export interface User {
  id: string
  email: string
  first_name: string
  last_name: string
  phone: string | null
  address?: string | null
  role: UserRole
  is_active: boolean
  tenant_id: string | null
  tenant_name?: string | null
  tenant_slug?: string | null
  tenant_logo_url?: string | null
  customer_id: string | null
  core_hours_target_minutes_override?: number | null
  shift_start_local_override?: string | null
  shift_end_local_override?: string | null
}

export interface TenantBranding {
  name: string | null
  slug: string | null
  logo_url: string | null
}

export interface Customer {
  id: string
  tenant_id: string
  first_name: string
  last_name: string
  company_name: string | null
  email: string
  phone: string | null
  billing_address_line1: string | null
  billing_address_line2: string | null
  billing_city: string | null
  billing_state: string | null
  billing_zip: string | null
  billing_country: string
  notes: string | null
  source?: string | null
  sms_opt_out?: boolean
  sms_opted_out_at?: string | null
  sms_opt_out_source?: string | null
  auto_approval_threshold: string | null
  created_at: string
  updated_at: string
}

export type SMSDirection = 'inbound' | 'outbound'
export type SMSMessageSource = 'inbound' | 'manual' | 'automated'
export type SMSDeliveryStatus = 'pending' | 'queued' | 'sent' | 'delivered' | 'undelivered' | 'failed'

export interface MessageThread {
  id: string
  tenant_id: string
  customer_id: string
  customer_phone: string | null
  unread_count_staff: number
  last_message_at: string | null
  last_message_preview: string | null
  archived_at?: string | null
  archived_by_user_id?: string | null
  created_at: string
  updated_at: string
  customer: {
    id: string
    first_name: string
    last_name: string
    email: string
    phone: string | null
    sms_opt_out: boolean
  }
}

export interface SmsMessage {
  id: string
  tenant_id: string
  thread_id: string
  customer_id: string
  created_by_user_id: string | null
  direction: SMSDirection
  source: SMSMessageSource
  body: string
  from_number: string | null
  to_number: string | null
  twilio_message_sid: string | null
  delivery_status: SMSDeliveryStatus
  error_code: string | null
  error_message: string | null
  sent_at: string | null
  delivered_at: string | null
  failed_at: string | null
  created_at: string
  updated_at: string
}

export interface SendSmsRequest {
  customer_id: string
  body: string
  thread_id?: string | null
}

export interface CursorPageMessageThreads {
  items: MessageThread[]
  next_cursor: string | null
  has_more: boolean
}

export interface CursorPageSmsMessages {
  items: SmsMessage[]
  next_cursor: string | null
  has_more: boolean
}

export interface MessagesUnreadSummary {
  unread_count_staff: number
}

export interface Vehicle {
  id: string
  tenant_id: string
  customer_id: string
  vin: string | null
  unit_number: string | null
  make: string
  model: string
  year: number | null
  license_plate: string | null
  color: string | null
  mileage: number | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface VINDecodeResult {
  vin: string
  make: string | null
  model: string | null
  year: number | null
  vehicle_type: string | null
  body_class: string | null
  drive_type: string | null
  fuel_type: string | null
  engine_cylinders: number | null
  engine_displacement_l: number | null
  engine_hp: number | null
  transmission: string | null
  gvwr: string | null
  error_code: string | null
  error_text: string | null
}

export interface CustomerWithVehicles extends Customer {
  vehicles: Vehicle[]
}

export interface PartsUsage {
  id: string
  repair_order_id: string
  inventory_id: string
  inventory_sku: string
  inventory_name: string
  quantity: number
  unit_price: string
  unit_cost: string | null
  list_price: string | null
  savings: string
  total_price: string
  source_service_id: string | null
  created_at: string
}

export interface Labor {
  id: string
  repair_order_id: string
  description: string
  hours: string
  hourly_rate: string
  total_cost: string
  mechanic_id: string | null
  service_code: string | null
  line_type: 'flat_service' | 'repair_operation' | 'manual' | 'sublet'
  provider: string | null
  provider_operation_id: string | null
  auto_recalc_enabled: boolean
  source_service_id: string | null
  vendor_name: string | null
  vendor_cost: string | null
  created_at: string
}

export interface RepairOrder {
  id: string
  tenant_id: string
  customer_id: string
  vehicle_id: string
  vehicle_make: string
  vehicle_model: string
  vehicle_year: number | null
  vehicle_unit_number: string | null
  vehicle_vin: string | null
  order_number: string
  status: RepairOrderStatus
  description: string | null
  customer_notes: string | null
  internal_notes: string | null
  assigned_mechanic_id: string | null
  total_parts_cost: string
  total_labor_cost: string
  total_cost: string
  created_at: string
  updated_at: string
  quote_sent?: boolean | null
  pending_zelle_confirmation?: boolean
  hold_reason?: string | null
  held_at?: string | null
  // Time tracking fields (V1.4)
  estimated_labor_minutes?: number | null
  actual_tracked_minutes?: number | null
  total_hold_minutes?: number | null
  assigned_at?: string | null
  acknowledged_at?: string | null
  work_started_at?: string | null
  work_completed_at?: string | null
  pricing_locked_at?: string | null
  pricing_lock_reason?: string | null
  mileage_in?: number | null
  mileage_out?: number | null
  po_number?: string | null
  parent_repair_order_id?: string | null
  is_warranty_repair?: boolean
  is_internal?: boolean
}

export interface RepairOrderPMService {
  service_id: string
  name: string
  duration_minutes: number
}

export interface RepairOrderDetail extends RepairOrder {
  parts_usage: PartsUsage[]
  labor_items: Labor[]
  is_pm?: boolean
  pm_services?: RepairOrderPMService[]
}

export interface PriceBuildWarning {
  code: string
  message: string
}

export interface RepairOperationCandidate {
  operation_id: string
  name: string
  description?: string | null
  estimated_hours: string
  provider: string
}

export interface PriceBuildLine extends Labor {}

export interface PriceBuildSummary {
  order_id: string
  labor_total: string
  parts_total: string
  labor_discount_amount?: string
  order_discount_amount?: string
  total_cost: string
  pricing_locked: boolean
  pricing_locked_at?: string | null
  pricing_lock_reason?: string | null
  lines: PriceBuildLine[]
  warnings: PriceBuildWarning[]
}

export interface Quote {
  id: string
  tenant_id: string
  repair_order_id: string
  quote_number: string
  total_amount: string
  notes: string | null
  expires_at: string | null
  is_approved: boolean
  is_declined: boolean
  decline_notes: string | null
  sent_to_customer: boolean
  sent_at: string | null
  created_at: string
  updated_at: string
}

export interface MechanicWorkItem {
  id: string
  order_number: string
  status: RepairOrderStatus
  vehicle_info: string
  updated_at: string
}

export interface InventoryItem {
  id: string
  tenant_id: string
  sku: string
  name: string
  description: string | null
  category: string | null
  stock_quantity: number
  on_order_quantity: number
  reorder_level: number
  cost: string
  selling_price: string
  supplier_name: string | null
  supplier_contact: string | null
  created_at: string
  updated_at: string
}

export type RecommendedServicePriority = 'urgent' | 'soon' | 'monitor'

export interface RecommendedService {
  id: string
  repair_order_id: string
  tenant_id: string
  description: string
  estimated_cost: string | null
  priority: RecommendedServicePriority
  notes: string | null
  is_resolved: boolean
  resolved_by_repair_order_id: string | null
  created_at: string
}

export interface ServiceCategory {
  id: string
  name: string
  description: string | null
  icon: string | null
  sort_order: number
  is_active: boolean
}

export interface ServicePart {
  id: string
  inventory_id: string
  sku: string
  name: string
  quantity: number
  unit_price: string
  line_total: string
  stock_quantity: number
}

export interface Service {
  id: string
  category_id: string | null
  name: string
  description: string | null
  duration_minutes: number
  /** Flat-rate override. Null means "compute as labor + parts". */
  base_price: string | null
  icon: string | null
  sort_order: number
  is_active: boolean
  requires_vehicle: boolean
  category?: ServiceCategory
  parts: ServicePart[]
  labor_cost: string
  parts_cost: string
  /** Always-populated display price (matches base_price if set, else labor+parts). */
  computed_total_price: string
}

export type AppointmentStatus = 
  | 'pending'
  | 'confirmed'
  | 'in_progress'
  | 'completed'
  | 'cancelled'
  | 'no_show'

export interface Appointment {
  id: string
  confirmation_number: string
  customer_id: string
  vehicle_id: string | null
  service_id: string
  service_name: string
  scheduled_at: string
  duration_minutes: number
  status: AppointmentStatus
  price: string
  customer_notes: string | null
  paid_at: string | null
  created_at: string
}

export interface TimeSlot {
  time: string
  available: boolean
}

export interface Supplier {
  id: string
  tenant_id: string
  name: string
  address: string | null
  phone: string | null
  contact_name: string | null
  notes: string | null
  created_at?: string
  updated_at?: string
}

export type InvoiceStatus = 'draft' | 'sent' | 'paid' | 'overdue' | 'cancelled'

export interface Invoice {
  id: string
  tenant_id: string
  repair_order_id: string
  invoice_number: string
  status: InvoiceStatus
  subtotal: string
  shop_supplies_amount: string
  service_fee_amount: string
  tax_amount: string
  discount_amount: string
  total_amount: string
  due_date: string | null
  paid_at: string | null
  notes: string | null
  pending_zelle_confirmation?: boolean
  zelle_pending_submitted_at?: string | null
  zelle_pending_sender_email?: string | null
  zelle_pending_sender_phone?: string | null
  zelle_pending_last_reminder_at?: string | null
  zelle_pending_reminder_count?: number
  created_at: string
  updated_at: string
}

export interface InvoiceDetail extends Invoice {
  order_number: string
  customer_name: string
  vehicle_info: string
}
