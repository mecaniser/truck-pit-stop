import api from '@/lib/api'
import type { Customer, Vehicle } from '@/types'

export type RepairOrderEntry = { customer: Customer; vehicle?: Vehicle }
export type RepairOrderReturn = { pathname: '/dashboard/customers'; search: string; customerId: string; vehicleId?: string }

export const canStartCustomerOrder = (role?: string) => ['garage_owner', 'garage_admin', 'receptionist'].includes(role ?? '')

export function repairOrderEntrySearch(customerId: string, vehicleId?: string) {
  const params = new URLSearchParams({ newCustomer: customerId })
  if (vehicleId) params.set('newVehicle', vehicleId)
  return `?${params}`
}

export function readRepairOrderReturn(state: unknown): RepairOrderReturn | null {
  const value = (state as { repairOrderReturn?: Partial<RepairOrderReturn> } | null)?.repairOrderReturn
  return value?.pathname === '/dashboard/customers' && typeof value.search === 'string'
    && typeof value.customerId === 'string' && (!value.vehicleId || typeof value.vehicleId === 'string')
    ? value as RepairOrderReturn : null
}

export async function loadRepairOrderEntry(customerId: string, vehicleId: string | null, signal?: AbortSignal): Promise<RepairOrderEntry> {
  // These existing endpoints enforce the tenant and return active relationships.
  // Never substitute the truck owner for the selected bill-to company.
  const customer = (await api.get<Customer>(`/customers/${encodeURIComponent(customerId)}`, { signal })).data
  if (customer?.id !== customerId) throw new Error('Customer is unavailable')
  if (!vehicleId) return { customer }
  const vehicle = (await api.get<Vehicle>(`/customers/${encodeURIComponent(customerId)}/vehicles/${encodeURIComponent(vehicleId)}`, { signal })).data
  if (vehicle?.id !== vehicleId) throw new Error('Truck is no longer linked to this customer')
  return { customer, vehicle }
}
