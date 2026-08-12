import { deepFreeze } from './appearance'
export const customersFixture = deepFreeze([
  { id: 'customer-1', name: 'NorthStar Logistics', vehicles: 8, balance: '0.00' },
  { id: 'customer-2', name: 'Long Customer Name That Must Wrap Without Breaking The Workspace', vehicles: 14, balance: '-2500.75' },
])
export const emptyCustomersFixture = deepFreeze([])
