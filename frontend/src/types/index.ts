export type UserRole = 'super_admin' | 'garage_admin' | 'mechanic' | 'receptionist' | 'customer'

export type RepairOrderStatus = 
  | 'draft'
  | 'quoted'
  | 'approved'
  | 'in_progress'
  | 'completed'
  | 'invoiced'
  | 'paid'
  | 'cancelled'

export interface User {
  id: string
  email: string
  first_name: string
  last_name: string
  phone: string | null
  role: UserRole
  is_active: boolean
  tenant_id: string | null
  customer_id: string | null
}

export interface Customer {
  id: string
  tenant_id: string
  first_name: string
  last_name: string
  email: string
  phone: string | null
  billing_address_line1: string | null
  billing_address_line2: string | null
  billing_city: string | null
  billing_state: string | null
  billing_zip: string | null
  billing_country: string
  notes: string | null
  created_at: string
  updated_at: string
}

export interface Vehicle {
  id: string
  tenant_id: string
  customer_id: string
  vin: string | null
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

export interface RepairOrder {
  id: string
  tenant_id: string
  customer_id: string
  vehicle_id: string
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
}

export interface InventoryItem {
  id: string
  tenant_id: string
  sku: string
  name: string
  description: string | null
  category: string | null
  stock_quantity: number
  reorder_level: number
  cost: string
  selling_price: string
  supplier_name: string | null
  supplier_contact: string | null
  created_at: string
  updated_at: string
}

export interface ServiceCategory {
  id: string
  name: string
  description: string | null
  icon: string | null
  sort_order: number
  is_active: boolean
}

export interface Service {
  id: string
  category_id: string | null
  name: string
  description: string | null
  duration_minutes: number
  base_price: string
  icon: string | null
  sort_order: number
  is_active: boolean
  requires_vehicle: boolean
  category?: ServiceCategory
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
