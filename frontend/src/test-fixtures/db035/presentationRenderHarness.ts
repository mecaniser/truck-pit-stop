import { appearanceTokenRecord } from '../../contexts/appearanceTokens'
import type { AppearancePreferences } from '../../types/presentation'
import { customersFixture } from './customers'
import { dashboardFixture } from './dashboard'
import { messagesFixture } from './messages'
import { myShopFixture } from './myShop'
import { repairOrdersFixture } from './repairOrders'
import { settingsFixture } from './settings'

export const STAFF_SURFACES = ['dashboard', 'customers', 'repair-orders', 'messages', 'my-shop', 'profile-settings'] as const
export type StaffSurface = typeof STAFF_SURFACES[number]

const fixtureFor = (surface: StaffSurface) => ({
  dashboard: dashboardFixture,
  customers: customersFixture,
  'repair-orders': repairOrdersFixture,
  messages: messagesFixture,
  'my-shop': myShopFixture,
  'profile-settings': settingsFixture,
})[surface]

export function renderPresentationSurface(surface: StaffSurface, appearance: AppearancePreferences) {
  const tokens = appearanceTokenRecord(appearance)
  const fixture = fixtureFor(surface)
  const serialized = JSON.stringify(fixture)
  if (!serialized || serialized === '{}' || serialized === '[]') throw new Error(`${surface} fixture is empty`)
  return {
    surface,
    tokens,
    minTarget: Number.parseInt(tokens['--density-control-min'], 10),
    // Semantic status families are deliberately fixed and never interpolate a personal accent.
    html: `<section data-surface="${surface}" data-mode="${appearance.mode}"><h1>${surface}</h1><button style="min-height:${tokens['--density-control-min']}">Open</button><output class="semantic-success">Ready</output><data value="0.00">$0.00</data></section>`,
  }
}
