import type { RepairOrder } from '@/types'

export type RepairOrdersQueueOrigin = 'needs_action' | 'on_floor' | 'ready_to_close' | 'closed_today'

export const REPAIR_ORDERS_QUEUE_LABEL: Record<RepairOrdersQueueOrigin, string> = {
  needs_action: 'Needs Action',
  on_floor: 'On the Floor',
  ready_to_close: 'Ready to Close',
  closed_today: 'Closed Today',
}

// Workflow endpoints intentionally return the canonical order fields, but some
// older responses do not hydrate the denormalized customer/vehicle display
// fields. A status change must never make an already-open order lose its
// identity while the filtered ledger refreshes around it.
const presentationFields: (keyof RepairOrder)[] = [
  'vehicle_make',
  'vehicle_model',
  'vehicle_year',
  'vehicle_unit_number',
  'vehicle_vin',
  'customer_first_name',
  'customer_last_name',
  'customer_company_name',
  'customer_email',
  'customer_phone',
  'customer_fleet_enabled',
]

type CustomerPresentation = Pick<RepairOrder,
  'customer_first_name' | 'customer_last_name' | 'customer_company_name' | 'customer_email' | 'customer_phone' | 'customer_fleet_enabled'
>
type VehiclePresentation = Pick<RepairOrder,
  'vehicle_make' | 'vehicle_model' | 'vehicle_year' | 'vehicle_unit_number' | 'vehicle_vin'
>

export function seedRepairOrderPresentation(
  order: RepairOrder,
  customer?: Partial<CustomerPresentation> | null,
  vehicle?: Partial<VehiclePresentation> | null,
): RepairOrder {
  return { ...order, ...customer, ...vehicle }
}

export function retainRepairOrderPresentation(current: RepairOrder | null, updated: RepairOrder): RepairOrder {
  if (!current || current.id !== updated.id) return updated

  const merged = { ...current, ...updated }
  const mergedRecord = merged as Record<keyof RepairOrder, unknown>
  for (const field of presentationFields) {
    const value = updated[field]
    if (value == null || value === '') {
      mergedRecord[field] = current[field]
    }
  }
  return merged
}
