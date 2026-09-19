import { describe, expect, it } from 'vitest'
import type { RepairOrder } from '@/types'
import { retainRepairOrderPresentation, seedRepairOrderPresentation } from '../repairOrdersPresentation'

const selectedOrder = {
  id: 'order-1',
  tenant_id: 'tenant-1',
  customer_id: 'customer-1',
  vehicle_id: 'vehicle-1',
  order_number: 'TPS-1',
  status: 'draft',
  description: null,
  customer_notes: null,
  internal_notes: null,
  assigned_mechanic_id: null,
  total_parts_cost: '0.00',
  total_labor_cost: '0.00',
  total_cost: '0.00',
  created_at: '2026-09-18T09:00:00Z',
  updated_at: '2026-09-18T09:00:00Z',
  vehicle_make: 'Volvo',
  vehicle_model: 'VNR',
  vehicle_year: 2020,
  vehicle_unit_number: '609',
  vehicle_vin: '4V4WC9EG2LN250024',
  customer_first_name: 'Sergio',
  customer_last_name: '',
  customer_company_name: 'Elis Logistics LLC (DBN)',
  customer_email: 'sergio@example.test',
  customer_phone: '7047050486',
  customer_fleet_enabled: false,
} satisfies RepairOrder

describe('retainRepairOrderPresentation', () => {
  it('uses the selected customer and vehicle immediately after creating an order', () => {
    const sparseCreatedOrder = {
      ...selectedOrder,
      vehicle_make: '', vehicle_model: '', vehicle_year: null, vehicle_unit_number: null, vehicle_vin: null,
      customer_first_name: '', customer_last_name: '', customer_company_name: null, customer_email: null, customer_phone: null,
    }

    expect(seedRepairOrderPresentation(
      sparseCreatedOrder,
      { customer_company_name: 'ELIS LOGISTICS LLC', customer_fleet_enabled: true },
      { vehicle_unit_number: '609' },
    )).toMatchObject({
      customer_company_name: 'ELIS LOGISTICS LLC',
      customer_fleet_enabled: true,
      vehicle_unit_number: '609',
    })
  })

  it('keeps the current customer and equipment labels when a status response omits their summaries', () => {
    const updated = {
      ...selectedOrder,
      status: 'in_progress' as const,
      vehicle_make: '', vehicle_model: '', vehicle_year: null, vehicle_unit_number: null, vehicle_vin: null,
      customer_first_name: '', customer_last_name: '', customer_company_name: null, customer_email: null, customer_phone: null,
    }

    expect(retainRepairOrderPresentation(selectedOrder, updated)).toMatchObject({
      status: 'in_progress',
      customer_company_name: 'Elis Logistics LLC (DBN)',
      vehicle_unit_number: '609',
      vehicle_make: 'Volvo',
    })
  })
})
