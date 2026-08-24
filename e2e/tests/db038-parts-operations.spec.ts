import { expect, test, type Page } from '@playwright/test'
import fixture from '../../backend/tests/fixtures/db038_parts_operations.json'
import { garageOwnerSession } from '../../frontend/src/test-fixtures/db035/staffSession'

const errors = new WeakMap<Page, string[]>()

const demandItems = Array.from({ length: 100 }, (_, index) => ({
  ...fixture.read_contract.expected_oil_filter_demand,
  inventory_id: `demand-${index + 1}`,
  sku: `DB-FILTER-${String(index + 1).padStart(3, '0')}`,
  name: `Fleet filter ${index + 1}`,
  state: index === 99 ? 'unlinked' : 'open',
  repair_shortage_packages: index % 2 === 0 ? 2 : 0,
  shelf_replenishment_packages: index % 2 === 0 ? 0 : 1,
  preferred_supplier: index === 99 ? null : fixture.read_contract.expected_oil_filter_demand.preferred_supplier,
}))

const inventoryItems = Array.from({ length: 100 }, (_, index) => ({
  ...fixture.inventory[0],
  id: `inventory-${index + 1}`,
  sku: `DB-INVENTORY-${String(index + 1).padStart(3, '0')}`,
  name: `Fleet filter ${index + 1}`,
}))

async function installFixture(page: Page) {
  const failures: string[] = []
  errors.set(page, failures)
  page.on('console', message => {
    if (message.type() === 'error') failures.push(`console: ${message.text()}`)
  })
  page.on('pageerror', error => failures.push(`pageerror: ${error.message}`))
  page.on('requestfailed', request => {
    if (request.url().includes('/api/v1/') && request.failure()?.errorText !== 'net::ERR_ABORTED') {
      failures.push(`requestfailed: ${request.method()} ${request.url()}`)
    }
  })

  await page.addInitScript(() => {
    class FixtureWebSocket extends EventTarget {
      static readonly CONNECTING = 0
      static readonly OPEN = 1
      static readonly CLOSING = 2
      static readonly CLOSED = 3
      readyState = FixtureWebSocket.CONNECTING
      onopen: ((event: Event) => void) | null = null
      constructor(_url: string | URL) {
        super()
        queueMicrotask(() => {
          this.readyState = FixtureWebSocket.OPEN
          this.onopen?.(new Event('open'))
        })
      }
      send() {}
      close() { this.readyState = FixtureWebSocket.CLOSED }
    }
    Object.defineProperty(window, 'WebSocket', { configurable: true, value: FixtureWebSocket })
  })

  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ status: 200, contentType: 'text/css', body: '' }))
  await page.route('https://fonts.gstatic.com/**', route => route.fulfill({ status: 204, body: '' }))
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    const json = (body: unknown) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    if (url.pathname.endsWith('/auth/workos/me')) return json(garageOwnerSession)
    if (url.pathname.endsWith('/auth/me/appearance')) return json(garageOwnerSession.presentation)
    if (url.pathname.endsWith('/auth/tenant-branding') || url.pathname.endsWith('/admin/garage-profile')) return json({ name: 'Truck Pit Stop Wisconsin', state: 'WI', logo_url: null })
    if (url.pathname.endsWith('/messages/unread-summary')) return json({ unread_count: 0 })
    if (url.pathname.endsWith('/parts-operations/summary')) return json({ low_stock_count: 50, open_purchase_order_count: 4 })
    if (url.pathname.endsWith('/parts-operations/demand')) return json({ items: demandItems, total: demandItems.length, skip: 0, limit: 100, has_more: false })
    if (url.pathname.endsWith('/inventory')) return json({ items: inventoryItems, total: inventoryItems.length, skip: 0, limit: 100, has_more: false })
    if (url.pathname.endsWith('/parts-operations/purchase-orders') && route.request().method() === 'GET') return json({ items: [], total: 0, skip: 0, limit: 100, has_more: false })
    if (url.pathname.endsWith('/parts-operations/returns')) return json({ items: [], total: 0, skip: 0, limit: 100, has_more: false })
    if (url.pathname.endsWith('/parts-operations/cores')) return json({ items: [], total: 0, skip: 0, limit: 100, has_more: false })
    if (url.pathname.endsWith('/parts-operations/activity')) return json({ items: [], total: 0, skip: 0, limit: 100, has_more: false })
    if (url.pathname.endsWith('/messages/threads')) return json({ items: [], next_cursor: null, has_more: false })
    if (url.pathname.endsWith('/mechanics') || url.pathname.endsWith('/admin/staff') || url.pathname.endsWith('/mechanics/pto-requests/pending')) return json([])
    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: `Unhandled DB-038 fixture route: ${route.request().method()} ${url.pathname}` }) })
  })
}

test('DB-038 contains a 100-row master/detail workstation across responsive views without unhandled errors', async ({ browser }, testInfo) => {
  for (const [width, height] of [[1280, 900], [960, 900], [390, 844], [320, 720]]) {
    const context = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce', forcedColors: 'active' })
    const page = await context.newPage()
    await installFixture(page)
    await page.goto('/dashboard/garage/inventory')
    await expect(page.getByRole('heading', { name: 'Supply, stock & custody' })).toBeVisible()
    await expect(page.getByRole('list', { name: 'Parts operations workflow' })).toHaveCount(0)
    const primaryTabs = page.getByRole('tablist', { name: 'Parts Operations areas' })
    await expect(primaryTabs.locator('[role="tab"][aria-selected="true"]')).toHaveCount(1)
    if (width === 390) await page.screenshot({ path: testInfo.outputPath('db038-demand-mobile-390.png'), fullPage: false })
    const demand = page.getByRole('tab', { name: 'Demand' })
    await expect(demand).toHaveCSS('min-height', '44px')
    await demand.focus()
    await page.keyboard.press('ArrowRight')
    await expect(page.getByRole('tab', { name: 'Inventory' })).toHaveAttribute('aria-selected', 'true')
    await expect(primaryTabs.locator('[role="tab"][aria-selected="true"]')).toHaveCount(1)
    await expect(page.getByRole('region', { name: 'Inventory results, 100 shown of 100', exact: true })).toHaveAttribute('tabindex', '0')
    await page.getByLabel('Search inventory').fill('Fleet filter 100')
    await expect(page.getByText('1 of 100 inventory items')).toBeVisible()
    await primaryTabs.getByRole('tab', { name: 'Returns & cores' }).click()
    await expect(primaryTabs.locator('[role="tab"][aria-selected="true"]')).toHaveCount(1)
    const custodyTabs = page.getByRole('tablist', { name: 'Return and core custody view' })
    await expect(custodyTabs.locator('[role="tab"][aria-selected="true"]')).toHaveCount(1)
    expect(await page.locator('body').evaluate(node => node.scrollWidth <= window.innerWidth)).toBe(true)
    expect(errors.get(page)).toEqual([])
    await context.close()
  }
})

test('DB-038 captures initial and scrolled demand/detail states with real owned scroll regions', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 900 })
  await installFixture(page)
  await page.goto('/dashboard/garage/inventory')
  const demandList = page.getByRole('region', { name: 'Demand results, 100 shown of 100', exact: true })
  const detail = page.getByRole('region', { name: 'Demand results, 100 shown of 100 detail', exact: true })
  await expect(demandList).toBeVisible()
  await expect(detail).toBeVisible()
  await expect(page.getByText('100 demand items')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('db038-demand-initial-1280.png'), fullPage: false })
  expect(await demandList.evaluate(node => getComputedStyle(node).overflowY)).toMatch(/auto|scroll/)
  expect(await detail.evaluate(node => getComputedStyle(node).overflowY)).toMatch(/auto|scroll/)
  expect(await demandList.evaluate(node => node.scrollHeight > node.clientHeight)).toBe(true)
  await demandList.evaluate(node => { node.scrollTop = node.scrollHeight })
  await expect(page.getByRole('button', { name: /Fleet filter 100/i })).toBeVisible()
  await page.getByRole('button', { name: /Fleet filter 100/i }).click()
  await expect(page.getByTestId('parts-selection-status')).toContainText('Fleet filter 100 selected.')
  await page.screenshot({ path: testInfo.outputPath('db038-demand-scrolled-detail-1280.png'), fullPage: false })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(demandList).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('db038-demand-detail-mobile-390.png'), fullPage: false })
  expect(await page.locator('body').evaluate(node => node.scrollWidth <= window.innerWidth)).toBe(true)
  expect(errors.get(page)).toEqual([])
})
