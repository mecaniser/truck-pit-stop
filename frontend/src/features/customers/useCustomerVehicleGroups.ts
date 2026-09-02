import { Building2, Route } from 'lucide-react'

import { customerDisplayName } from '@/lib/customerName'
import { vehicleDisplayLabel } from '@/lib/vehicleName'
import type { Customer, Vehicle } from '@/types'

/**
 * How a customer's trucks group: the ones they own, and the ones that merely
 * run under their authority. Both screens that show a customer need the same
 * split, the same search behaviour, and the same "which columns are worth
 * showing" answer — duplicating ~55 lines of it was the drift waiting to
 * happen.
 */
export function useCustomerVehicleGroups({
  selectedCustomer,
  customerVehicles,
  vehicleRelationshipSearch,
  vehicleRelationshipFilter,
}: {
  selectedCustomer: Customer | null | undefined
  customerVehicles: Vehicle[] | undefined
  vehicleRelationshipSearch: string
  vehicleRelationshipFilter: 'all' | 'owned' | 'authority'
}) {
const vehicleCount = customerVehicles?.length || 0
const ownedVehicles = customerVehicles?.filter((vehicle) =>
  vehicle.customer_relationship_types?.includes('owner') || vehicle.customer_id === selectedCustomer?.id
) || []
const authorityVehicles = customerVehicles?.filter((vehicle) =>
  vehicle.customer_relationship_types?.includes('operator')
  && !vehicle.customer_relationship_types?.includes('owner')
  && vehicle.customer_id !== selectedCustomer?.id
) || []
const shouldShowVehicleSearch = vehicleCount > 3
const normalizedVehicleSearch = shouldShowVehicleSearch ? vehicleRelationshipSearch.trim().toLowerCase() : ''
const matchesVehicleSearch = (vehicle: Vehicle) => {
  if (!normalizedVehicleSearch) return true
  const searchable = [
    vehicleDisplayLabel(vehicle), vehicle.unit_number, vehicle.vin, vehicle.license_plate,
    vehicle.make, vehicle.model, vehicle.owner_company_name, vehicle.operating_authority_company_name,
  ].filter(Boolean).join(' ').toLowerCase()
  return normalizedVehicleSearch.split(/\s+/).every((term) => searchable.includes(term))
}
const customerVehicleGroups = [
  {
    key: 'owned',
    title: `Owned by ${selectedCustomer ? customerDisplayName(selectedCustomer) : 'this company'}`,
    description: 'Trucks this company owns or leases to another operating authority.',
    vehicles: ownedVehicles,
    visibleVehicles: ownedVehicles.filter(matchesVehicleSearch),
    icon: Building2,
  },
  {
    key: 'authority',
    title: `Runs under ${selectedCustomer ? customerDisplayName(selectedCustomer) : 'this company'} authority`,
    description: 'Trucks owned by another company that run under this company’s authority.',
    vehicles: authorityVehicles,
    visibleVehicles: authorityVehicles.filter(matchesVehicleSearch),
    icon: Route,
  },
].filter((group) => group.vehicles.length > 0 && (vehicleRelationshipFilter === 'all' || vehicleRelationshipFilter === group.key))
const visibleCustomerVehicleGroups = customerVehicleGroups.filter((group) => group.visibleVehicles.length > 0)
const visibleVehicleCount = visibleCustomerVehicleGroups.reduce((count, group) => count + group.visibleVehicles.length, 0)
const showVehicleUnitColumn = customerVehicles?.some((vehicle) => !!vehicle.unit_number?.trim()) ?? false
const showVehicleVinColumn = customerVehicles?.some((vehicle) => !!vehicle.vin?.trim()) ?? false
const showVehiclePlateColumn = customerVehicles?.some((vehicle) => !!vehicle.license_plate?.trim()) ?? false
const vehicleTableColumnCount = 2 + Number(showVehicleUnitColumn) + Number(showVehicleVinColumn) + Number(showVehiclePlateColumn)

const vehicleRelationshipNote = (vehicle: Vehicle, groupKey: string) => {
  if (groupKey === 'authority') {
    return vehicle.owner_company_name ? `Owned by ${vehicle.owner_company_name}` : 'Owner / lessor not assigned'
  }
  if (
    vehicle.operating_authority_company_name
    && vehicle.operating_authority_customer_id !== selectedCustomer?.id
  ) {
    return `Runs under ${vehicle.operating_authority_company_name}`
  }
  if (vehicle.customer_relationship_types?.includes('operator')) return 'Owner + operating authority'
  return 'Operating authority not assigned'
}

  return {
    vehicleCount,
    ownedVehicles,
    authorityVehicles,
    shouldShowVehicleSearch,
    visibleCustomerVehicleGroups,
    visibleVehicleCount,
    showVehicleUnitColumn,
    showVehicleVinColumn,
    showVehiclePlateColumn,
    vehicleTableColumnCount,
    vehicleRelationshipNote,
  }
}
