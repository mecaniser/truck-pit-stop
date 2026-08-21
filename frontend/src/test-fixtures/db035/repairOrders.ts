import { deepFreeze } from './appearance'
export const repairOrdersFixture = deepFreeze([
  { id: 'ro-1', number: 'RO-2025-0417', status: 'invoiced', customer: 'NorthStar Logistics', vehicle: '2021 Freightliner Cascadia 126', total: '4494.62' },
  { id: 'ro-2', number: 'RO-2025-0418', status: 'checked_in', customer: '77 Cargo LLC', vehicle: '2024 Volvo VNL', total: '0.00' },
])
export const emptyRepairOrdersFixture = deepFreeze([])
