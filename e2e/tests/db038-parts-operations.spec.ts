import { expect, test, type Locator, type Page } from '@playwright/test'
import fixture from '../../backend/tests/fixtures/db038_parts_operations.json'
import { garageOwnerSession } from '../../frontend/src/test-fixtures/db035/staffSession'

const errors = new WeakMap<Page, string[]>()

const specialInventoryRows = [
  { name: 'Air filter', stock_quantity: 0, reorder_level: 2, supplier_name: 'Alpha Supply', location: 'A-01', image_url: '/db038-part-image.svg', is_placeholder: false, ets_retired_at: null },
  { name: 'Brake shoe', stock_quantity: 2, reorder_level: 5, supplier_name: 'Beta Supply', location: 'B-02', image_url: '/db038-broken-image.svg', is_placeholder: false, ets_retired_at: null },
  { name: 'Coolant', stock_quantity: 10, reorder_level: 3, supplier_name: 'Gamma Supply', location: 'C-03', image_url: null, is_placeholder: false, ets_retired_at: null },
  { name: 'Temporary catalog item', stock_quantity: 1, reorder_level: 8, supplier_name: null, location: null, image_url: null, is_placeholder: true, ets_retired_at: null },
  { name: 'Retired empty item', stock_quantity: 0, reorder_level: 4, supplier_name: 'Archive Supply', location: 'R-01', image_url: null, is_placeholder: false, ets_retired_at: fixture.frozen_at },
] as const

const demandItems = Array.from({ length: 100 }, (_, index) => ({
  ...fixture.read_contract.expected_oil_filter_demand,
  inventory_id: `inventory-${index + 1}`,
  sku: `DB-FILTER-${String(index + 1).padStart(3, '0')}`,
  name: specialInventoryRows[index]?.name || `Fleet filter ${index + 1}`,
  state: index === 99 ? 'unlinked' : 'open',
  repair_shortage_packages: index % 2 === 0 ? 2 : 0,
  shelf_replenishment_packages: index % 2 === 0 ? 0 : 1,
  preferred_supplier: index === 99 ? null : fixture.read_contract.expected_oil_filter_demand.preferred_supplier,
}))

const inventoryItems = Array.from({ length: 100 }, (_, index) => {
  const special = specialInventoryRows[index]
  return {
    ...fixture.inventory[0],
    id: `inventory-${index + 1}`,
    sku: `DB-INVENTORY-${String(index + 1).padStart(3, '0')}`,
    name: special?.name || `Fleet filter ${index + 1}`,
    stock_quantity: special?.stock_quantity ?? index + 1,
    reorder_level: special?.reorder_level ?? 3,
    supplier_name: special?.supplier_name ?? `Supplier ${index + 1}`,
    location: special?.location ?? `BIN-${index + 1}`,
    image_url: special?.image_url ?? null,
    is_placeholder: special?.is_placeholder ?? false,
    ets_retired_at: special?.ets_retired_at ?? null,
  }
})

const purchaseOrder = {
  id: 'po-visual-audit',
  po_number: 'PO-DB038-001',
  supplier_id: fixture.ids.supplier,
  supplier: fixture.read_contract.expected_oil_filter_demand.preferred_supplier,
  status: 'submitted',
  version: 1,
  expected_at: null,
  line_count: 1,
  ordered_quantity: 3,
  received_quantity: 0,
  remaining_quantity: 3,
  created_at: fixture.frozen_at,
} as const

const purchaseOrderDetail = {
  ...purchaseOrder,
  notes: null,
  lines: [{
    id: 'po-line-visual-audit',
    inventory_id: fixture.ids.oil_filter,
    sku: fixture.read_contract.expected_oil_filter_demand.sku,
    description: fixture.read_contract.expected_oil_filter_demand.name,
    unit_type: fixture.read_contract.expected_oil_filter_demand.unit_type,
    unit_cost: '20.00',
    ordered_quantity: 3,
    received_quantity: 0,
  }],
} as const

function rgbChannels(value: string) {
  const channels = value.match(/[\d.]+/g)?.slice(0, 3).map(Number)
  if (!channels || channels.length !== 3) throw new Error(`Expected an rgb color, received ${value}`)
  return channels
}

function contrastRatio(foreground: string, background: string) {
  const luminance = (color: string) => {
    const [red, green, blue] = rgbChannels(color).map((channel) => {
      const normalized = channel / 255
      return normalized <= 0.03928 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4
    })
    return (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
  }
  const lighter = Math.max(luminance(foreground), luminance(background))
  const darker = Math.min(luminance(foreground), luminance(background))
  return (lighter + 0.05) / (darker + 0.05)
}

async function expectIntegratedSearch(input: Locator) {
  const shell = input.locator('..')
  const styles = await input.evaluate((node) => {
    const inputStyle = getComputedStyle(node)
    const shellStyle = getComputedStyle(node.parentElement!)
    const placeholderStyle = getComputedStyle(node, '::placeholder')
    return {
      background: inputStyle.backgroundColor,
      borderWidths: [inputStyle.borderTopWidth, inputStyle.borderRightWidth, inputStyle.borderBottomWidth, inputStyle.borderLeftWidth],
      borderRadius: inputStyle.borderRadius,
      boxShadow: inputStyle.boxShadow,
      color: inputStyle.color,
      placeholder: placeholderStyle.color,
      caret: inputStyle.caretColor,
      shellBackground: shellStyle.backgroundColor,
    }
  })
  expect(styles.background).toMatch(/,\s*0\)$/)
  expect(styles.borderWidths).toEqual(['0px', '0px', '0px', '0px'])
  expect(styles.borderRadius).toBe('0px')
  expect(styles.boxShadow).toBe('none')
  expect(contrastRatio(styles.color, styles.shellBackground)).toBeGreaterThanOrEqual(4.5)
  expect(contrastRatio(styles.placeholder, styles.shellBackground)).toBeGreaterThanOrEqual(4.5)
  expect(styles.caret).toBe(styles.color)

  await input.focus()
  const focus = await shell.evaluate((node) => {
    const style = getComputedStyle(node)
    return { outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth }
  })
  expect(focus.outlineStyle).not.toBe('none')
  expect(focus.outlineWidth).not.toBe('0px')
}

async function expectStandaloneField(input: Locator) {
  const styles = await input.evaluate((node) => {
    const style = getComputedStyle(node)
    return { background: style.backgroundColor, color: style.color, borderWidth: style.borderTopWidth }
  })
  expect(styles.background).not.toBe('rgba(0, 0, 0, 0)')
  expect(styles.borderWidth).not.toBe('0px')
  expect(contrastRatio(styles.color, styles.background)).toBeGreaterThanOrEqual(4.5)
}

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
  await page.route('**/db038-part-image.svg', route => route.fulfill({ status: 200, contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 44 44"><rect width="44" height="44" rx="8" fill="#d7e4f4"/><path d="M13 15h18v14H13z" fill="#254b73"/></svg>' }))
  await page.route('**/db038-broken-image.svg', route => route.fulfill({ status: 404, body: '' }))
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
    if (url.pathname.endsWith('/parts-operations/purchase-orders') && route.request().method() === 'GET') return json({ items: [purchaseOrder], total: 1, skip: 0, limit: 100, has_more: false })
    if (url.pathname.endsWith(`/parts-operations/purchase-orders/${purchaseOrder.id}`)) return json(purchaseOrderDetail)
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
    await expectIntegratedSearch(page.getByRole('searchbox', { name: 'Search demand' }))
    await expect(page.getByRole('list', { name: 'Parts operations workflow' })).toHaveCount(0)
    const primaryTabs = page.getByRole('tablist', { name: 'Parts Operations areas' })
    await expect(primaryTabs.locator('[role="tab"][aria-selected="true"]')).toHaveCount(1)
    if (width === 390) await page.screenshot({ path: testInfo.outputPath('db038-demand-mobile-390.png'), fullPage: false })
    const demand = page.getByRole('tab', { name: 'Demand' })
    await expect(demand).toHaveCSS('min-height', '44px')
    await demand.focus()
    await page.keyboard.press('ArrowRight')
    await expect(page.getByRole('tab', { name: 'Inventory' })).toHaveAttribute('aria-selected', 'true')
    await expectIntegratedSearch(page.getByRole('searchbox', { name: 'Search inventory' }))
    await expect(primaryTabs.locator('[role="tab"][aria-selected="true"]')).toHaveCount(1)
    await expect(page.getByRole('region', { name: 'Inventory results, 100 shown of 100', exact: true })).toHaveAttribute('tabindex', '0')
    const inventoryRows = page.locator('[data-parts-row]')
    await expect(inventoryRows.first().locator('.db-parts-operations__thumbnail img')).toBeVisible()
    await expect(inventoryRows.nth(1).locator('.db-parts-operations__thumbnail svg')).toBeVisible()
    await expect(inventoryRows.nth(2).locator('.db-parts-operations__thumbnail svg')).toBeVisible()
    for (const label of ['All stock', 'Needs reorder', 'Out of stock', 'In stock']) await expect(page.getByRole('button', { name: label })).toHaveCSS('min-height', '44px')
    await page.getByRole('button', { name: 'Needs reorder' }).click()
    await expect(page.getByText('2 of 100 inventory items')).toBeVisible()
    await page.getByRole('button', { name: 'Out of stock' }).click()
    await expect(page.getByText('2 of 100 inventory items')).toBeVisible()
    await page.getByRole('button', { name: 'In stock' }).click()
    await expect(page.getByText('96 of 100 inventory items')).toBeVisible()
    await page.getByRole('button', { name: 'All stock' }).click()
    const sort = page.getByLabel('Sort inventory')
    await expect(sort).toHaveCSS('min-height', '44px')
    await sort.selectOption('low-stock')
    await expect(inventoryRows.first()).toContainText('Air filter')
    await sort.selectOption('high-stock')
    await expect(inventoryRows.first()).toContainText('Fleet filter 100')
    await sort.selectOption('name-desc')
    await expect(inventoryRows.first()).toContainText('Temporary catalog item')
    await sort.selectOption('name-asc')
    await expect(inventoryRows.first()).toContainText('Air filter')
    await inventoryRows.getByText('Brake shoe', { exact: true }).click()
    await expect(page.getByTestId('parts-selection-status')).toContainText('Needs reorder')
    await page.getByRole('button', { name: 'In stock' }).click()
    await expect(page.getByText('Select an inventory item to review stock and activity.')).toBeVisible()
    await page.getByLabel('Search inventory').fill('Alpha Supply')
    await expect(page.getByText('0 of 100 inventory items')).toBeVisible()
    await page.getByRole('button', { name: 'Reset inventory view' }).click()
    await expect(page.getByText('100 inventory items')).toBeVisible()
    await expect(page.getByLabel('Sort inventory')).toHaveValue('catalog')
    await inventoryRows.first().focus()
    await page.keyboard.press('ArrowDown')
    await expect(inventoryRows.first()).toHaveAttribute('tabindex', '-1')
    await expect(inventoryRows.nth(1)).toHaveAttribute('tabindex', '0')
    await expect(inventoryRows.nth(1)).toBeFocused()
    await page.getByLabel('Search inventory').fill('Supplier 100')
    await expect(page.getByText('1 of 100 inventory items')).toBeVisible()
    await expect(inventoryRows.first()).toContainText('Fleet filter 100')
    if (width === 1280 || width === 390) await page.screenshot({ path: testInfo.outputPath(`db038-inventory-operate-${width}.png`), fullPage: false })
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
  await expectIntegratedSearch(page.getByRole('searchbox', { name: 'Search demand' }))
  await page.getByRole('button', { name: /Fleet filter 1/i, exact: false }).first().click()
  await expectStandaloneField(page.getByLabel('PO number'))
  await expectStandaloneField(page.getByLabel('Packages'))
  await page.getByRole('tab', { name: 'Inventory' }).click()
  await expectIntegratedSearch(page.getByRole('searchbox', { name: 'Search inventory' }))
  await page.getByRole('tab', { name: 'Purchase orders' }).click()
  await page.getByRole('button', { name: /PO-DB038-001/i }).click()
  await expectStandaloneField(page.getByLabel(`Receive quantity for ${purchaseOrderDetail.lines[0].sku}`))
  await expectStandaloneField(page.getByLabel(`Receipt unit cost for ${purchaseOrderDetail.lines[0].sku}`))
  await page.screenshot({ path: testInfo.outputPath('db038-controls-audit-1280.png'), fullPage: false })
  await page.getByRole('tab', { name: 'Demand' }).click()
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
