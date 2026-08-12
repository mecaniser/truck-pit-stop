import { deepFreeze } from './appearance'
export const settingsFixture = deepFreeze({
  account: ['Profile', 'Security', 'Appearance'],
  shop: ['Shop Profile', 'Payments & Accounting', 'Notifications', 'Tax & Fees', 'Fleet', 'Workforce'],
  loading: false,
})
export const settingsErrorFixture = deepFreeze({ error: 'Settings could not be loaded. Try again.' })
