import { deepFreeze } from './appearance'
export const myShopFixture = deepFreeze({
  management: [{ id: 'staff-1', name: 'Alex Rivera', role: 'Shop Owner' }],
  mechanics: [{ id: 'mechanic-1', name: 'M. Reyes', availability: 'active' }],
  sections: ['Team', 'Services', 'Labor Book Time', 'Inventory', 'Suppliers', 'Fleet', 'Analytics'],
})
