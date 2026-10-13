import api from '@/lib/api'
import { customerDisplayName } from '@/lib/customerName'
import { vehicleDisplayLabel } from '@/lib/vehicleName'
import type { Customer, InventoryItem, RepairOrder, Vehicle } from '@/types'

export const SEARCH_LIMIT = 5
export const MIN_SEARCH_LENGTH = 2

export interface SearchResult {
  id: string
  title: string
  description: string
  href: string
}

export interface SearchSource {
  id: string
  label: string
  search: (query: string, signal: AbortSignal) => Promise<SearchResult[]>
}

export function canSearchShop(user: { role: string; tenant_id: string | null; is_active: boolean } | null) {
  return Boolean(user?.is_active && user.tenant_id && ['garage_owner', 'garage_admin', 'receptionist', 'mechanic'].includes(user.role))
}

const customers: SearchSource = {
  id: 'customers',
  label: 'Customers',
  async search(query, signal) {
    const { data } = await api.get<Pick<Customer, 'id' | 'first_name' | 'last_name' | 'company_name' | 'email' | 'phone'>[]>('/customers/typeahead', {
      params: { q: query, limit: SEARCH_LIMIT }, signal,
    })
    return data.map(customer => ({
      id: customer.id,
      title: customerDisplayName(customer),
      description: [customer.phone, customer.email].filter(Boolean).join(' · '),
      href: `/dashboard/customers?selected=${encodeURIComponent(customer.id)}`,
    }))
  },
}

const vehicles: SearchSource = {
  id: 'vehicles',
  label: 'Vehicles',
  async search(query, signal) {
    const { data } = await api.get<Pick<Vehicle, 'id' | 'customer_id' | 'make' | 'model' | 'year' | 'unit_number' | 'license_plate' | 'vin'>[]>('/vehicles/typeahead', {
      params: { q: query, limit: SEARCH_LIMIT }, signal,
    })
    return data.map(vehicle => ({
      id: vehicle.id,
      title: [vehicle.unit_number && `Unit ${vehicle.unit_number}`, vehicleDisplayLabel({ ...vehicle, unit_number: null })].filter(Boolean).join(' · '),
      description: [vehicle.license_plate && `Plate ${vehicle.license_plate}`, vehicle.vin && `VIN ${vehicle.vin}`].filter(Boolean).join(' · '),
      href: `/dashboard/customers?selected=${encodeURIComponent(vehicle.customer_id)}&vehicle=${encodeURIComponent(vehicle.id)}`,
    }))
  },
}

const repairOrders: SearchSource = {
  id: 'repair-orders',
  label: 'Repair orders',
  async search(query, signal) {
    const { data } = await api.get<RepairOrder[]>('/repair-orders', {
      params: { search: query, limit: SEARCH_LIMIT, skip: 0 }, signal,
    })
    return data.map(order => ({
      id: order.id,
      title: `RO ${order.order_number}`,
      description: [
        customerDisplayName({ first_name: order.customer_first_name, last_name: order.customer_last_name, company_name: order.customer_company_name }, ''),
        order.vehicle_unit_number && `Unit ${order.vehicle_unit_number}`,
        order.description,
      ].filter(Boolean).join(' · '),
      href: `/dashboard/repair-orders?selected=${encodeURIComponent(order.id)}`,
    }))
  },
}

const inventory: SearchSource = {
  id: 'inventory',
  label: 'Inventory',
  async search(query, signal) {
    const { data } = await api.get<Pick<InventoryItem, 'id' | 'sku' | 'name' | 'stock_quantity'>[]>('/inventory/typeahead', {
      params: { q: query, limit: SEARCH_LIMIT, in_stock: false }, signal,
    })
    return data.map(part => ({
      id: part.id,
      title: part.name,
      description: [part.sku, `${part.stock_quantity} in stock`].filter(Boolean).join(' · '),
      href: `/dashboard/garage/inventory?selected=${encodeURIComponent(part.id)}`,
    }))
  },
}

export function shopSearchSources(role: string): SearchSource[] {
  // These are the roles admitted by the parts workspace. The API remains the
  // authority for each record; never accept a tenant ID from the search input.
  return [customers, vehicles, repairOrders, ...(['garage_owner', 'garage_admin', 'receptionist'].includes(role) ? [inventory] : [])]
}
