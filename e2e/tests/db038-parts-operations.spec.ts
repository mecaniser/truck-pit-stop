import { expect, test, type Locator, type Page } from '@playwright/test'
import fixture from '../../backend/tests/fixtures/db038_parts_operations.json'
import { garageOwnerSession, receptionistSession } from '../../frontend/src/test-fixtures/db035/staffSession'

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

const vendorReturn = {
  id: 'return-visual-audit',
  return_number: 'RET-DB038-001',
  supplier_id: fixture.ids.supplier,
  supplier: fixture.read_contract.expected_oil_filter_demand.preferred_supplier,
  kind: 'stock',
  status: 'submitted',
  version: 1,
  line_count: 1,
  total_quantity: 1,
  expected_credit_total: '20.00',
  reverses_return_id: null,
  created_at: fixture.frozen_at,
} as const

const vendorReturnDetail = {
  ...vendorReturn,
  reason: 'Supplier return',
  notes: null,
  lines: [{
    id: 'return-line-visual-audit',
    inventory: { id: fixture.ids.oil_filter, sku: fixture.read_contract.expected_oil_filter_demand.sku, name: fixture.read_contract.expected_oil_filter_demand.name },
    quantity: 1,
    expected_credit: '20.00',
    actual_credit: null,
    source: { type: 'receipt', id: 'receipt-visual-audit' },
  }],
} as const

const coreObligation = {
  id: 'core-visual-audit',
  inventory_id: fixture.ids.oil_filter,
  inventory: { id: fixture.ids.oil_filter, sku: fixture.read_contract.expected_oil_filter_demand.sku, name: 'Oil filter core' },
  supplier_id: fixture.ids.supplier,
  supplier: fixture.read_contract.expected_oil_filter_demand.preferred_supplier,
  quantity: 1,
  status: 'on_hand',
  version: 1,
  unit_core_value: '20.00',
  source: { repair_order_id: fixture.ids.repair_order, order_number: 'TPS-000301' },
  created_at: fixture.frozen_at,
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

async function expectSelectedPartImage(image: Locator, width: number) {
  const media = image.locator('..')
  const box = await media.boundingBox()
  expect(box).not.toBeNull()
  expect(Math.abs(box!.width - box!.height)).toBeLessThanOrEqual(1)
  if (width <= 760) {
    expect(box!.width).toBeGreaterThanOrEqual(96)
    expect(box!.width).toBeLessThanOrEqual(120)
  } else {
    expect(box!.width).toBeGreaterThanOrEqual(144)
    expect(box!.width).toBeLessThanOrEqual(176)
  }
}

async function expectSingleMasterSelection(page: Page, expected: Locator) {
  await expect(page.locator('[data-parts-row][aria-current="true"]')).toHaveCount(1)
  await expect(page.locator('[data-parts-row][tabindex="0"]')).toHaveCount(1)
  await expect(expected).toHaveAttribute('aria-current', 'true')
  await expect(expected).toHaveAttribute('tabindex', '0')
}

type InventoryUpdate = { id: string; body: Record<string, unknown> }

async function installFixture(page: Page, {
  tenantLogoUrl = '/db038-tenant-logo.svg',
  readOnly = false,
  inventoryUpdateStatus = 200,
  inventoryUpdates = [],
}: {
  tenantLogoUrl?: string
  readOnly?: boolean
  inventoryUpdateStatus?: number
  inventoryUpdates?: InventoryUpdate[]
} = {}) {
  const failures: string[] = []
  const scopedInventoryItems = inventoryItems.map((item) => ({ ...item }))
  const expectedImageFailureResponses = new Set<string>()
  const expectedApiFailureResponses = new Set<string>()
  const intentionalImageFailurePaths = new Set(['/db038-broken-image.svg', '/db038-broken-logo.svg'])
  errors.set(page, failures)
  page.on('response', response => {
    const url = new URL(response.url())
    if (intentionalImageFailurePaths.has(url.pathname) && response.status() === 404) {
      expectedImageFailureResponses.add(response.url())
    }
    if (/\/inventory\/[^/]+$/.test(url.pathname) && response.request().method() === 'PUT' && response.status() === inventoryUpdateStatus && inventoryUpdateStatus !== 200) {
      expectedApiFailureResponses.add(response.url())
    }
  })
  page.on('console', message => {
    if (message.type() !== 'error') return
    const locationUrl = message.location().url
    const isExpectedImageFailure = message.text().startsWith('Failed to load resource:')
      && expectedImageFailureResponses.has(locationUrl)
    const isExpectedApiFailure = message.text().startsWith('Failed to load resource:')
      && expectedApiFailureResponses.has(locationUrl)
    if (!isExpectedImageFailure && !isExpectedApiFailure) failures.push(`console: ${message.text()}`)
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
  await page.route('**/db038-tenant-logo.svg', route => route.fulfill({ status: 200, contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96"><rect width="96" height="96" rx="16" fill="#0d2036"/><path d="M20 50h56M30 50c4-22 32-22 36 0" fill="none" stroke="#30d6a0" stroke-width="6"/></svg>' }))
  await page.route('**/db038-broken-image.svg', route => route.fulfill({ status: 404, body: '' }))
  await page.route('**/db038-broken-logo.svg', route => route.fulfill({ status: 404, body: '' }))
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    const json = (body: unknown) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    if (url.pathname.endsWith('/auth/workos/me')) return json(readOnly ? receptionistSession : garageOwnerSession)
    if (url.pathname.endsWith('/auth/me/appearance')) return json((readOnly ? receptionistSession : garageOwnerSession).presentation)
    if (url.pathname.endsWith('/auth/tenant-branding') || url.pathname.endsWith('/admin/garage-profile')) return json({ name: 'Truck Pit Stop Wisconsin', state: 'WI', logo_url: tenantLogoUrl })
    if (url.pathname.endsWith('/messages/unread-summary')) return json({ unread_count: 0 })
    if (url.pathname.endsWith('/parts-operations/summary')) return json({ low_stock_count: 50, open_purchase_order_count: 4 })
    if (url.pathname.endsWith('/parts-operations/demand')) return json({ items: demandItems, total: demandItems.length, skip: 0, limit: 100, has_more: false })
    if (/\/inventory\/[^/]+$/.test(url.pathname) && route.request().method() === 'PUT') {
      const id = url.pathname.split('/').at(-1)!
      const body = route.request().postDataJSON() as Record<string, unknown>
      inventoryUpdates.push({ id, body })
      if (inventoryUpdateStatus !== 200) return route.fulfill({ status: inventoryUpdateStatus, contentType: 'application/json', body: JSON.stringify({ detail: 'Inventory update could not be saved.' }) })
      const index = scopedInventoryItems.findIndex((item) => item.id === id)
      if (index < 0) return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'Inventory item not found.' }) })
      const updated = {
        ...scopedInventoryItems[index],
        ...body,
        cost: body.cost === undefined ? scopedInventoryItems[index].cost : Number(body.cost).toFixed(2),
      }
      scopedInventoryItems[index] = updated
      return json(updated)
    }
    if (url.pathname.endsWith('/inventory')) return json({ items: scopedInventoryItems, total: scopedInventoryItems.length, skip: 0, limit: 100, has_more: false })
    if (url.pathname.endsWith('/parts-operations/purchase-orders') && route.request().method() === 'GET') return json({ items: [purchaseOrder], total: 1, skip: 0, limit: 100, has_more: false })
    if (url.pathname.endsWith(`/parts-operations/purchase-orders/${purchaseOrder.id}`)) return json(purchaseOrderDetail)
    if (url.pathname.endsWith(`/parts-operations/returns/${vendorReturn.id}`)) return json(vendorReturnDetail)
    if (url.pathname.endsWith('/parts-operations/returns')) return json({ items: [vendorReturn], total: 1, skip: 0, limit: 100, has_more: false })
    if (url.pathname.endsWith('/parts-operations/cores')) return json({ items: [coreObligation], total: 1, skip: 0, limit: 100, has_more: false })
    if (url.pathname.endsWith('/parts-operations/activity')) return json({ items: [], total: 0, skip: 0, limit: 100, has_more: false })
    if (url.pathname.endsWith('/messages/threads')) return json({ items: [], next_cursor: null, has_more: false })
    if (url.pathname.endsWith('/mechanics') || url.pathname.endsWith('/admin/staff') || url.pathname.endsWith('/mechanics/pto-requests/pending')) return json([])
    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: `Unhandled DB-038 fixture route: ${route.request().method()} ${url.pathname}` }) })
  })
  return { expectedImageFailureResponses }
}

test('DB-038 contains a 100-row master/detail workstation across responsive views without unhandled errors', async ({ browser }, testInfo) => {
  for (const [width, height] of [[1280, 900], [960, 900], [390, 844], [320, 720]]) {
    const context = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce', forcedColors: 'active' })
    const page = await context.newPage()
    const fixtureRuntime = await installFixture(page)
    await page.goto('/dashboard/garage/inventory')
    await expect(page.getByRole('heading', { name: 'Supply, stock & custody' })).toBeVisible()
    await expectIntegratedSearch(page.getByRole('searchbox', { name: 'Search demand' }))
    await expect(page.getByRole('list', { name: 'Parts operations workflow' })).toHaveCount(0)
    const primaryTabs = page.getByRole('tablist', { name: 'Parts Operations areas' })
    await expect(primaryTabs.locator('[role="tab"][aria-selected="true"]')).toHaveCount(1)
    const demandRows = page.locator('[data-parts-row]')
    await expectSingleMasterSelection(page, demandRows.first())
    await expect(page.getByRole('img', { name: 'Air filter part photo' })).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath(`db038-first-selection-${width}.png`), fullPage: false })
    await expect(demandRows.first().locator('[data-image-source="part"] img')).toBeVisible()
    await demandRows.first().click()
    const demandPartPhoto = page.getByRole('img', { name: 'Air filter part photo' })
    await expect(demandPartPhoto).toBeVisible()
    await expectSelectedPartImage(demandPartPhoto, width)
    await expect(demandRows.nth(1).locator('[data-image-source="logo"] img')).toBeVisible()
    await demandRows.nth(1).click()
    const demandLogoPlaceholder = page.getByRole('img', { name: 'Truck Pit Stop Wisconsin logo placeholder for Brake shoe' })
    await expect(demandLogoPlaceholder).toBeVisible()
    await expectSelectedPartImage(demandLogoPlaceholder, width)
    await expect(demandRows.nth(2).locator('[data-image-source="logo"] img')).toBeVisible()
    expect([...fixtureRuntime.expectedImageFailureResponses].some(url => new URL(url).pathname === '/db038-broken-image.svg')).toBe(true)
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
    await expectSingleMasterSelection(page, inventoryRows.first())
    await expect(inventoryRows.first().locator('[data-image-source="part"] img')).toBeVisible()
    await expect(inventoryRows.nth(1).locator('[data-image-source="logo"] img')).toBeVisible()
    await expect(inventoryRows.nth(2).locator('[data-image-source="logo"] img')).toBeVisible()
    await inventoryRows.nth(2).click()
    const inventoryLogoPlaceholder = page.getByRole('img', { name: 'Truck Pit Stop Wisconsin logo placeholder for Coolant' })
    await expect(inventoryLogoPlaceholder).toBeVisible()
    await expectSelectedPartImage(inventoryLogoPlaceholder, width)
    if (width === 1280 || width === 390) await page.screenshot({ path: testInfo.outputPath(`db038-inventory-image-detail-${width}.png`), fullPage: false })
    const stockFilters = page.getByRole('group', { name: 'Inventory stock filter' })
    for (const label of ['All stock', 'Needs reorder', 'Out of stock', 'In stock']) await expect(stockFilters.getByRole('button', { name: label, exact: true })).toHaveCSS('min-height', '44px')
    await stockFilters.getByRole('button', { name: 'Needs reorder', exact: true }).click()
    await expect(page.getByText('2 of 100 inventory items')).toBeVisible()
    await stockFilters.getByRole('button', { name: 'Out of stock', exact: true }).click()
    await expect(page.getByText('2 of 100 inventory items')).toBeVisible()
    await stockFilters.getByRole('button', { name: 'In stock', exact: true }).click()
    await expect(page.getByText('96 of 100 inventory items')).toBeVisible()
    await stockFilters.getByRole('button', { name: 'All stock', exact: true }).click()
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
    await stockFilters.getByRole('button', { name: 'In stock', exact: true }).click()
    await expectSingleMasterSelection(page, page.getByRole('button', { name: /Coolant/i }))
    await expect(page.getByRole('heading', { name: 'Coolant' })).toBeVisible()
    await page.getByLabel('Search inventory').fill('Alpha Supply')
    await expect(page.getByText('0 of 100 inventory items')).toBeVisible()
    await expect(page.locator('[data-parts-row][aria-current="true"]')).toHaveCount(0)
    await expect(page.locator('[data-parts-row][tabindex="0"]')).toHaveCount(0)
    await page.getByRole('button', { name: 'Reset inventory view' }).click()
    await expect(page.getByText('100 inventory items')).toBeVisible()
    await expect(page.getByLabel('Sort inventory')).toHaveValue('catalog')
    await expectSingleMasterSelection(page, inventoryRows.first())
    await inventoryRows.first().focus()
    await page.keyboard.press('ArrowDown')
    await expect(inventoryRows.first()).toHaveAttribute('tabindex', '-1')
    await expect(inventoryRows.nth(1)).toHaveAttribute('tabindex', '0')
    await expect(inventoryRows.nth(1)).toBeFocused()
    await page.getByLabel('Search inventory').fill('Supplier 100')
    await expect(page.getByText('1 of 100 inventory items')).toBeVisible()
    await expect(inventoryRows.first()).toContainText('Fleet filter 100')
    await expectSingleMasterSelection(page, inventoryRows.first())
    if (width === 1280 || width === 390) await page.screenshot({ path: testInfo.outputPath(`db038-inventory-operate-${width}.png`), fullPage: false })
    await primaryTabs.getByRole('tab', { name: 'Purchase orders' }).click()
    await expectSingleMasterSelection(page, page.getByRole('button', { name: /PO-DB038-001/i }))
    await expect(page.getByRole('heading', { name: 'PO-DB038-001' })).toBeVisible()
    await primaryTabs.getByRole('tab', { name: 'Returns & cores' }).click()
    await expect(primaryTabs.locator('[role="tab"][aria-selected="true"]')).toHaveCount(1)
    const custodyTabs = page.getByRole('tablist', { name: 'Return and core custody view' })
    await expect(custodyTabs.locator('[role="tab"][aria-selected="true"]')).toHaveCount(1)
    await expectSingleMasterSelection(page, page.getByRole('button', { name: /RET-DB038-001/i }))
    await expect(page.getByRole('heading', { name: 'RET-DB038-001' })).toBeVisible()
    await custodyTabs.getByRole('tab', { name: 'Cores' }).click()
    await expectSingleMasterSelection(page, page.getByRole('button', { name: /Oil filter core/i }))
    await expect(page.getByRole('heading', { name: 'Oil filter core' })).toBeVisible()
    await custodyTabs.getByRole('tab', { name: 'Returns' }).click()
    await expectSingleMasterSelection(page, page.getByRole('button', { name: /RET-DB038-001/i }))
    await primaryTabs.getByRole('tab', { name: 'Activity' }).click()
    await expect(page.locator('[data-parts-row]')).toHaveCount(0)
    expect(await page.locator('body').evaluate(node => node.scrollWidth <= window.innerWidth)).toBe(true)
    expect(errors.get(page)).toEqual([])
    await context.close()
  }
})

test('DB-038 captures initial and scrolled demand/detail states with real owned scroll regions', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 900 })
  const fixtureRuntime = await installFixture(page, { tenantLogoUrl: '/db038-broken-logo.svg' })
  await page.goto('/dashboard/garage/inventory')
  const demandList = page.getByRole('region', { name: 'Demand results, 100 shown of 100', exact: true })
  const detail = page.getByRole('region', { name: 'Demand results, 100 shown of 100 detail', exact: true })
  await expect(demandList).toBeVisible()
  await expect(detail).toBeVisible()
  await expect(page.getByText('100 demand items')).toBeVisible()
  await expectIntegratedSearch(page.getByRole('searchbox', { name: 'Search demand' }))
  const demandRows = page.locator('[data-parts-row]')
  await expect(demandRows.nth(1).locator('[data-image-source="icon"] svg')).toBeVisible()
  await expect(demandRows.nth(2).locator('[data-image-source="icon"] svg')).toBeVisible()
  await demandRows.nth(1).click()
  await expect(page.getByRole('img', { name: 'No image available for Brake shoe' })).toBeVisible()
  await page.getByRole('button', { name: /Fleet filter 1/i, exact: false }).first().click()
  await expectStandaloneField(page.getByLabel('PO number'))
  await expectStandaloneField(page.getByLabel('Packages'))
  await page.getByRole('tab', { name: 'Inventory' }).click()
  await expectIntegratedSearch(page.getByRole('searchbox', { name: 'Search inventory' }))
  const inventoryRows = page.locator('[data-parts-row]')
  await expect(inventoryRows.nth(1).locator('[data-image-source="icon"] svg')).toBeVisible()
  await expect(inventoryRows.nth(2).locator('[data-image-source="icon"] svg')).toBeVisible()
  await inventoryRows.nth(2).click()
  await expect(page.getByRole('img', { name: 'No image available for Coolant' })).toBeVisible()
  expect([...fixtureRuntime.expectedImageFailureResponses].some(url => new URL(url).pathname === '/db038-broken-image.svg')).toBe(true)
  expect([...fixtureRuntime.expectedImageFailureResponses].some(url => new URL(url).pathname === '/db038-broken-logo.svg')).toBe(true)
  await page.getByRole('tab', { name: 'Purchase orders' }).click()
  await expectSingleMasterSelection(page, page.getByRole('button', { name: /PO-DB038-001/i }))
  await expect(page.getByRole('heading', { name: 'PO-DB038-001' })).toBeVisible()
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

test('DB-038 inventory controls preserve item ownership, permissions, validation, and responsive containment', async ({ browser }, testInfo) => {
  for (const [width, height] of [[1280, 900], [960, 900], [390, 844], [320, 720]]) {
    const context = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce' })
    const page = await context.newPage()
    const updates: InventoryUpdate[] = []
    await installFixture(page, { inventoryUpdates: updates })
    await page.goto('/dashboard/garage/inventory')
    await page.getByRole('tab', { name: 'Inventory' }).click()
    const rows = page.locator('[data-parts-row]')
    await expectSingleMasterSelection(page, rows.first())
    const controls = page.locator('.db-parts-operations__inventory-controls')
    await expect(controls.getByRole('heading', { name: 'Inventory controls' })).toBeVisible()
    const edit = controls.getByRole('button', { name: 'Edit inventory controls' })
    await expect(edit).toBeVisible()
    expect((await edit.boundingBox())!.height).toBeGreaterThanOrEqual(44)
    await edit.click()
    for (const label of ['On hand', 'On order', 'Reorder level', 'Current WAC', 'Adjustment reason']) {
      const field = controls.getByLabel(label, { exact: true })
      await expect(field).toBeVisible()
      expect((await field.boundingBox())!.height).toBeGreaterThanOrEqual(44)
    }
    expect(await page.locator('body').evaluate(node => node.scrollWidth <= window.innerWidth)).toBe(true)
    const controlsBox = await controls.boundingBox()
    expect(controlsBox).not.toBeNull()
    expect(controlsBox!.x + controlsBox!.width).toBeLessThanOrEqual(width + 1)
    if (width === 1280 || width === 390) await page.screenshot({ path: testInfo.outputPath(`db038-inventory-controls-${width}.png`), fullPage: false })

    if (width === 1280) {
      await controls.getByLabel('On hand', { exact: true }).fill('8')
      await controls.getByLabel('On order', { exact: true }).fill('4')
      await controls.getByLabel('Reorder level', { exact: true }).fill('6')
      await controls.getByLabel('Current WAC', { exact: true }).fill('12.75')
      await controls.getByRole('button', { name: 'Save inventory controls' }).click()
      await expect(controls.getByRole('alert')).toHaveText('Adjustment reason is required when On hand changes.')
      expect(updates).toHaveLength(0)
      await controls.getByLabel('Adjustment reason', { exact: true }).fill('Cycle count correction')
      await controls.getByRole('button', { name: 'Save inventory controls' }).click()
      await expect(page.getByTestId('parts-selection-status')).toContainText('Air filter inventory controls saved. 8 on hand.')
      expect(updates).toEqual([{ id: 'inventory-1', body: { stock_quantity: 8, stock_adjustment_reason: 'Cycle count correction', on_order_quantity: 4, reorder_level: 6, cost: 12.75 } }])
      await expectSingleMasterSelection(page, rows.first())
      await expect(controls).toContainText('8')
      await expect(controls).toContainText('$12.75')

      await controls.getByRole('button', { name: 'Edit inventory controls' }).click()
      await controls.getByLabel('On order', { exact: true }).fill('5')
      await controls.getByRole('button', { name: 'Save inventory controls' }).click()
      expect(updates[1]).toEqual({ id: 'inventory-1', body: { on_order_quantity: 5 } })
      await controls.getByRole('button', { name: 'Edit inventory controls' }).click()
      await controls.getByLabel('On hand', { exact: true }).fill('77')
      await controls.getByLabel('Adjustment reason', { exact: true }).fill('Must not cross records')
      await rows.nth(1).click()
      await expect(page.getByRole('heading', { name: 'Brake shoe' })).toBeVisible()
      const nextControls = page.locator('.db-parts-operations__inventory-controls')
      await nextControls.getByRole('button', { name: 'Edit inventory controls' }).click()
      await expect(nextControls.getByLabel('On hand', { exact: true })).toHaveValue('2')
      await expect(nextControls.getByLabel('Adjustment reason', { exact: true })).toHaveValue('')
    }
    expect(errors.get(page)).toEqual([])
    await context.close()
  }

  const failureContext = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const failurePage = await failureContext.newPage()
  await installFixture(failurePage, { inventoryUpdateStatus: 422 })
  await failurePage.goto('/dashboard/garage/inventory')
  await failurePage.getByRole('tab', { name: 'Inventory' }).click()
  const failureControls = failurePage.locator('.db-parts-operations__inventory-controls')
  await failureControls.getByRole('button', { name: 'Edit inventory controls' }).click()
  await failureControls.getByLabel('On order', { exact: true }).fill('9')
  await failureControls.getByRole('button', { name: 'Save inventory controls' }).click()
  await expect(failureControls.getByRole('alert')).toHaveText('Inventory update could not be saved.')
  await expect(failureControls.getByLabel('On order', { exact: true })).toHaveValue('9')
  expect(errors.get(failurePage)).toEqual([])
  await failureContext.close()

  const readOnlyContext = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const readOnlyPage = await readOnlyContext.newPage()
  await installFixture(readOnlyPage, { readOnly: true })
  await readOnlyPage.goto('/dashboard/garage/inventory')
  await readOnlyPage.getByRole('tab', { name: 'Inventory' }).click()
  const readOnlyControls = readOnlyPage.locator('.db-parts-operations__inventory-controls')
  await expect(readOnlyControls).toContainText('Read-only access. A shop owner or admin can edit inventory controls.')
  await expect(readOnlyControls.getByRole('button', { name: 'Edit inventory controls' })).toHaveCount(0)
  expect(errors.get(readOnlyPage)).toEqual([])
  await readOnlyContext.close()
})
