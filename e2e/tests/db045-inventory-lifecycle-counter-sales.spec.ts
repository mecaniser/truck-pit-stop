import { expect, test, type Page } from '@playwright/test'

import {
  appearanceCompactContrast,
  appearanceDefaults,
  appearanceLargeLight,
  presentationFixture,
} from '../../frontend/src/test-fixtures/db035/appearance'
import { garageOwnerSession } from '../../frontend/src/test-fixtures/db035/staffSession'
import type { AppearancePreferences } from '../../frontend/src/types/presentation'

const part = {
  id: 'part-db045-filter',
  sku: 'DB045-FLTR-001',
  name: 'Cabin Air Filter',
  description: 'Cab filter for counter-sale acceptance',
  image_url: null,
  unit_type: 'each',
  location: 'A-12',
  available_packages: 15,
  physical_on_hand_packages: 17,
  held_for_checkout_packages: 2,
  available_to_sell_packages: 15,
  needed_for_open_repairs: 1,
  reorder_level: 4,
  incoming_packages: 3,
  recommended_order_packages: 0,
  average_unit_cost: '8.75',
  selling_price: '22.00',
  is_archived: false,
  is_placeholder: false,
  preferred_source: null,
  supplier_sources: [],
  repair_sources: [],
  incoming_sources: [],
  recent_receipts: [],
  recent_movements: [],
}

const activityEvent = {
  id: 'activity-db045-sale',
  inventory_id: part.id,
  category: 'sales',
  event_type: 'counter_sale.completed',
  occurred_at: '2026-08-27T14:15:00Z',
  correlation_id: 'corr-db045',
  origin: 'live',
  part: { id: part.id, sku: part.sku, name: part.name },
  actor: { id: garageOwnerSession.id, name: 'Alex Rivera' },
  reason: { code: 'counter_sale', note: 'Walk-in sale' },
  before: { available_to_sell: 16 },
  after: { available_to_sell: 15 },
  stock: { physical_on_hand: 17, held_for_checkout: 2, available_to_sell: 15, delta: -1, balance_after: 17, wac: '8.75' },
  money: { list_price: '22.00', charged_price: '22.00', tax: '1.65', fee: '0.00' },
  payment: { tender: 'cash', status: 'succeeded' },
  source: { type: 'counter_sale', id: 'sale-db045', number: 'CS-0045', href: '/dashboard/garage/inventory/sales?sale=sale-db045' },
}

const lifecycleSummary = {
  inventory_id: part.id,
  as_of: '2026-08-27T14:30:00Z',
  repairs: { units_used: '8', repair_order_count: 4, last_used_at: '2026-08-26T10:00:00Z' },
  purchasing: { units_received: 25, receipt_count: 3, units_returned_to_vendor: 1, open_core_obligations: 0 },
  sales: { units_sold: 6, units_returned: 1, net_units: 5, gross_item_revenue: '132.00', discounts: '0.00', refunds: '22.00', net_item_revenue: '110.00', last_sold_at: '2026-08-27T14:15:00Z' },
  activity: { event_count: 19, last_event_at: '2026-08-27T14:15:00Z' },
}

const saleLine = {
  id: 'sale-line-db045',
  inventory_id: part.id,
  sku: part.sku,
  name: part.name,
  unit_type: 'each',
  quantity: 1,
  returned_quantity: 0,
  remaining_returnable_quantity: 1,
  unit_cost: '8.75',
  list_unit_price: '22.00',
  charged_unit_price: '22.00',
  discount_amount: '0.00',
  item_subtotal: '22.00',
  tax_amount: '1.65',
  fee_amount: '0.00',
  total_amount: '23.65',
  price_override_reason: null,
  physical_on_hand: 17,
  held_for_checkout: 1,
  available_to_sell: 15,
}

type SaleState = 'draft' | 'awaiting_payment' | 'completed' | 'partially_returned'

function saleFixture(status: SaleState, overrides: Record<string, unknown> = {}) {
  const completed = status === 'completed' || status === 'partially_returned'
  return {
    id: 'sale-db045',
    sale_number: 'CS-0045',
    status,
    version: status === 'draft' ? 1 : status === 'awaiting_payment' ? 2 : status === 'completed' ? 3 : 4,
    customer_id: null,
    buyer_name: 'Walk-in buyer',
    buyer_email: 'buyer@example.test',
    buyer_phone: null,
    currency: 'USD',
    list_subtotal: '22.00',
    charged_subtotal: '22.00',
    discount_amount: '0.00',
    tax_amount: '1.65',
    service_fee_amount: '0.00',
    total_amount: '23.65',
    lines: [{ ...saleLine, ...(status === 'partially_returned' ? { returned_quantity: 1, remaining_returnable_quantity: 0 } : {}) }],
    payment_attempts: status === 'draft' ? [] : [{ id: 'attempt-db045', tender: 'cash', state: status === 'awaiting_payment' ? 'pending' : 'succeeded', amount: '23.65', created_at: '2026-08-27T14:14:00Z' }],
    returns: status === 'partially_returned' ? [{ id: 'return-db045', sale_id: 'sale-db045', version: 1, state: 'completed', refund_amount: '23.65', lines: [{ id: 'return-line-db045', sale_line_id: saleLine.id, quantity: 1, reason: 'Damaged package', disposition: 'damaged', refund_amount: '23.65' }], created_at: '2026-08-27T14:20:00Z', completed_at: '2026-08-27T14:21:00Z' }] : [],
    allowed_actions: status === 'draft'
      ? ['edit_draft', 'checkout', 'cancel']
      : status === 'awaiting_payment'
        ? ['reconcile_payment']
        : status === 'completed'
          ? ['download_receipt', 'email_receipt', 'create_return']
          : ['download_receipt', 'email_receipt'],
    created_at: '2026-08-27T14:10:00Z',
    updated_at: '2026-08-27T14:15:00Z',
    completed_at: completed ? '2026-08-27T14:15:00Z' : null,
    cancelled_at: null,
    accounting_sync_status: completed ? 'queued' : null,
    receipt_email_status: null,
    ...overrides,
  }
}

async function installFixture(page: Page, appearance: AppearancePreferences) {
  const failures: string[] = []
  let sale = saleFixture('draft')
  const user = { ...garageOwnerSession, presentation: presentationFixture('new', appearance), can_access_messaging: true, messaging_enabled: true }

  page.on('console', (message) => { if (message.type() === 'error') failures.push(`console: ${message.text()}`) })
  page.on('pageerror', (error) => failures.push(`pageerror: ${error.message}`))
  page.on('requestfailed', (request) => {
    if (request.url().includes('/api/v1/') && request.failure()?.errorText !== 'net::ERR_ABORTED') failures.push(`requestfailed: ${request.method()} ${request.url()}`)
  })

  await page.addInitScript(() => {
    window.localStorage.clear()
    window.sessionStorage.clear()
    class FixtureWebSocket extends EventTarget {
      static readonly CONNECTING = 0
      static readonly OPEN = 1
      static readonly CLOSING = 2
      static readonly CLOSED = 3
      readyState = FixtureWebSocket.CONNECTING
      onopen: ((event: Event) => void) | null = null
      constructor(_url: string | URL) {
        super()
        queueMicrotask(() => { this.readyState = FixtureWebSocket.OPEN; this.onopen?.(new Event('open')) })
      }
      send() {}
      close() { this.readyState = FixtureWebSocket.CLOSED }
    }
    Object.defineProperty(window, 'WebSocket', { configurable: true, value: FixtureWebSocket })
  })

  await page.route('https://fonts.googleapis.com/**', (route) => route.fulfill({ status: 200, contentType: 'text/css', body: '' }))
  await page.route('https://fonts.gstatic.com/**', (route) => route.fulfill({ status: 204, body: '' }))
  await page.route('https://payments.api.intuit.com/**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ value: 'opaque-db045-token' }) }))
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    const method = route.request().method()
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (url.pathname.endsWith('/auth/workos/me')) return json(user)
    if (url.pathname.endsWith('/auth/workos/session/refresh')) return json({})
    if (url.pathname.endsWith('/auth/me/appearance')) return json(user.presentation)
    if (url.pathname.endsWith('/auth/tenant-branding') || url.pathname.endsWith('/admin/garage-profile')) return json({ name: 'Truck Pit Stop Wisconsin', slug: 'truck-pit-stop-wisconsin', state: 'WI', logo_url: null })
    if (url.pathname.endsWith('/messages/unread-summary')) return json({ unread_count: 0 })
    if (url.pathname.endsWith('/parts-operations/summary')) return json({
      needs_reorder_count: 0,
      low_stock_count: 0,
      open_purchase_order_count: 0,
      capabilities: {
        counter_sales: true,
        counter_sale_tenders: ['cash', 'check', 'ach', 'zelle', 'external_terminal', 'fleet_reference', 'other', 'stripe', 'quickbooks_payments'],
        counter_sale_providers: {
          stripe: { available: true, stripe_account_id: 'acct_db045' },
          quickbooks_payments: { available: true, token_url: 'https://payments.api.intuit.com/db045/tokens' },
        },
      },
    })
    if (url.pathname.endsWith('/parts-operations/parts') && method === 'GET') return json({ items: [part], total: 1, skip: 0, limit: Number(url.searchParams.get('limit') || 50), has_more: false })
    if (url.pathname.endsWith(`/parts-operations/parts/${part.id}`) && method === 'GET') return json(part)
    if (url.pathname.endsWith(`/parts-operations/parts/${part.id}/lifecycle-summary`)) return json(lifecycleSummary)
    if (url.pathname.endsWith(`/inventory/${part.id}`) && method === 'GET') return json({ id: part.id, sku: part.sku, name: part.name, description: part.description, category: 'Filters', unit_type: part.unit_type, location: part.location, image_url: null })
    if (url.pathname.endsWith('/parts-operations/activity-events/export.csv')) return route.fulfill({ status: 200, contentType: 'text/csv', body: 'event_type,sku\ncounter_sale.completed,DB045-FLTR-001\n' })
    if (url.pathname.endsWith('/parts-operations/activity-events')) return json({ items: [activityEvent], next_cursor: null })
    if (url.pathname.endsWith('/customers/typeahead')) return json([])
    if (url.pathname.endsWith('/parts-operations/counter-sales') && method === 'GET') return json({ items: [{ id: sale.id, sale_number: sale.sale_number, status: sale.status, buyer_name: sale.buyer_name, buyer_email: sale.buyer_email, total_amount: sale.total_amount, created_at: sale.created_at, completed_at: sale.completed_at, line_count: sale.lines.length, tender: sale.payment_attempts.at(-1)?.tender || null }], next_cursor: null })
    if (url.pathname.endsWith('/parts-operations/counter-sales') && method === 'POST') { sale = saleFixture('draft'); return json(sale) }
    if (url.pathname.endsWith(`/parts-operations/counter-sales/${sale.id}`) && method === 'GET') return json(sale)
    if (url.pathname.endsWith(`/parts-operations/counter-sales/${sale.id}`) && method === 'PATCH') { sale = { ...sale, version: sale.version + 1 }; return json(sale) }
    if (url.pathname.endsWith(`/parts-operations/counter-sales/${sale.id}/checkout`) && method === 'POST') {
      sale = saleFixture('completed')
      return json({ sale, payment: { attempt_id: 'attempt-db045', tender: 'cash', state: 'succeeded', client_secret: null, stripe_account_id: null, reconcile_url: `/api/v1/parts-operations/counter-sales/${sale.id}/payment-attempts/attempt-db045/reconcile` } })
    }
    if (url.pathname.endsWith(`/parts-operations/counter-sales/${sale.id}/payment-attempts/attempt-db045/reconcile`) && method === 'POST') { sale = saleFixture('completed'); return json(sale) }
    if (url.pathname.endsWith(`/parts-operations/counter-sales/${sale.id}/receipt/email`) && method === 'POST') return json({ queued: true })
    if (url.pathname.endsWith(`/parts-operations/counter-sales/${sale.id}/receipt.pdf`) && method === 'GET') return route.fulfill({ status: 200, contentType: 'application/pdf', body: '%PDF-1.4 DB045 fixture' })
    if (url.pathname.endsWith(`/parts-operations/counter-sales/${sale.id}/returns`) && method === 'POST') { sale = saleFixture('partially_returned'); return json(sale.returns[0]) }
    if (url.pathname.endsWith(`/parts-operations/counter-sales/${sale.id}/cancel`) && method === 'POST') return json({ ...sale, status: 'cancelled' })
    if (method === 'GET' && (url.pathname.endsWith('/mechanics') || url.pathname.endsWith('/mechanics/pto-requests/pending') || url.pathname.endsWith('/admin/staff') || url.pathname.endsWith('/services') || url.pathname.endsWith('/services/categories') || url.pathname.endsWith('/inventory'))) return json([])
    failures.push(`unhandled: ${method} ${url.pathname}`)
    return json({ detail: 'Unhandled DB-045 fixture route' }, 500)
  })

  return {
    failures,
    setPending: () => { sale = saleFixture('awaiting_payment') },
  }
}

async function expectContained(page: Page) {
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
  const sales = page.locator('.db-counter-sales')
  if (await sales.count()) await expect.poll(() => sales.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
}

test('DB-045 Activity and repair-first counter sale journey stay recoverable, accessible, and contained', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await context.newPage()
  const fixture = await installFixture(page, appearanceDefaults)

  await page.goto('/dashboard/garage/inventory')
  await expect(page.getByRole('heading', { name: 'Parts' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Parts sales/ })).toBeVisible()

  await page.getByRole('button', { name: /^Activity$/ }).click()
  await expect(page.getByRole('heading', { name: 'Inventory activity' })).toBeVisible()
  await page.getByRole('combobox', { name: 'Category' }).selectOption('sales')
  await page.getByPlaceholder('Search part, actor, reason, or source').fill('walk-in')
  await page.getByRole('button', { name: 'Apply filters' }).click()
  await expect(page.getByText('counter sale · completed')).toBeVisible()
  await expect(page.getByRole('link', { name: /CS-0045/ })).toHaveAttribute('href', '/dashboard/garage/inventory/sales?sale=sale-db045')

  await page.getByRole('button', { name: /All parts/ }).click()
  const actionTrigger = page.getByRole('button', { name: `More actions for ${part.name}` })
  await actionTrigger.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('menuitem', { name: 'Sell part' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(actionTrigger).toBeFocused()
  await actionTrigger.click()
  await page.getByRole('menuitem', { name: 'Sell part' }).click()
  await expect(page).toHaveURL(new RegExp(`/dashboard/garage/inventory/sales\\?new=1&part=${part.id}`))
  await expect(page.getByRole('heading', { name: 'New counter sale' })).toBeVisible()
  await expect(page.getByText('17 physical · 2 held · 15 available to sell')).toBeVisible()
  await page.getByLabel('Buyer name').fill('Walk-in buyer')
  await page.getByLabel('Email').fill('buyer@example.test')
  await page.getByRole('button', { name: /Review checkout/ }).click()

  await expect(page.getByRole('heading', { name: 'CS-0045' })).toBeVisible()
  const tender = page.getByLabel('Tender')
  for (const value of ['cash', 'check', 'ach', 'zelle', 'external_terminal', 'fleet_reference', 'other', 'stripe', 'quickbooks_payments']) {
    await tender.selectOption(value)
    await expect(tender).toHaveValue(value)
  }
  await expect(page.getByText(/Card data goes directly to Intuit/)).toBeVisible()
  await tender.selectOption('cash')
  await page.getByLabel('Reference', { exact: true }).fill('Till 2')
  await page.getByRole('button', { name: /Checkout \$23\.65/ }).click()
  await expect(page.getByRole('heading', { name: 'Receipt and returns' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Download receipt' })).toBeVisible()
  await page.getByRole('button', { name: 'Email receipt' }).click()
  await expect(page.getByRole('status')).toContainText('Receipt email queued')

  await page.getByRole('button', { name: 'Return items' }).click()
  await expect(page.getByRole('dialog', { name: /Return items from CS-0045/ })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Close return' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog', { name: /Return items from CS-0045/ })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Return items' })).toBeFocused()
  await page.getByRole('button', { name: 'Return items' }).click()
  await page.getByRole('button', { name: `Increase Return quantity for ${part.name}` }).click()
  await page.getByLabel('Reason').fill('Damaged package')
  await page.getByRole('radio', { name: 'Damaged', exact: true }).check()
  await page.getByRole('button', { name: 'Submit return and refund' }).click()
  await expect(page.getByRole('heading', { name: 'Returns and refunds' })).toBeVisible()
  await expect(page.getByText('partially returned')).toBeVisible()

  fixture.setPending()
  await page.goto('/dashboard/garage/inventory/sales?sale=sale-db045')
  await expect(page.getByRole('heading', { name: 'Payment pending' })).toBeVisible()
  await expect(page.getByText(/Stock remains held/)).toBeVisible()
  await page.getByRole('button', { name: /Reconcile payment/ }).click()
  await expect(page.getByRole('heading', { name: 'Receipt and returns' })).toBeVisible()
  await expectContained(page)
  expect(fixture.failures).toEqual([])
  await context.close()
})

test('DB-045 Activity and sales surfaces preserve theme and containment at target widths', async ({ browser }) => {
  const scenarios: Array<{ width: number; height: number; appearance: AppearancePreferences }> = [
    { width: 1280, height: 820, appearance: appearanceDefaults },
    { width: 960, height: 820, appearance: appearanceLargeLight },
    { width: 390, height: 844, appearance: appearanceDefaults },
    { width: 320, height: 760, appearance: appearanceCompactContrast },
  ]
  for (const scenario of scenarios) {
    const context = await browser.newContext({ viewport: { width: scenario.width, height: scenario.height } })
    const page = await context.newPage()
    const fixture = await installFixture(page, scenario.appearance)
    await page.goto('/dashboard/garage/inventory/sales')
    await expect(page.getByRole('heading', { name: 'Parts sales' })).toBeVisible()
    await expect(page.locator('.db-staff-shell')).toHaveAttribute('data-presentation', 'new')
    await expect(page.getByRole('button', { name: 'New counter sale' })).toHaveCSS('min-height', '44px')
    await expectContained(page)
    await page.goto('/dashboard/garage/inventory')
    await page.getByRole('button', { name: /^Activity$/ }).click()
    await expect(page.getByRole('heading', { name: 'Inventory activity' })).toBeVisible()
    await expectContained(page)
    expect(fixture.failures).toEqual([])
    await context.close()
  }
})
