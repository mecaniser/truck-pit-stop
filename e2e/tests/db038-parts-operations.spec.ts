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

const supplierSource = {
  source_id: 'source-db038-primary',
  supplier_id: fixture.ids.supplier,
  supplier_name: fixture.read_contract.expected_oil_filter_demand.preferred_supplier.name,
  supplier_part_number: 'FLEET-DB038',
  is_preferred: true,
  minimum_order_quantity: 1,
  pack_quantity: 1,
  last_unit_cost: '20.00',
  lead_time_days: 2,
  is_active: true,
  updated_at: fixture.frozen_at,
} as const

const partsItems = inventoryItems.map((item, index) => {
  const archived = Boolean(item.ets_retired_at)
  const needsReorder = !archived && !item.is_placeholder && item.stock_quantity <= item.reorder_level
  return {
    id: item.id,
    sku: item.sku,
    name: item.name,
    description: null,
    image_url: item.image_url,
    unit_type: item.unit_type || null,
    location: item.location,
    available_packages: item.stock_quantity,
    needed_for_open_repairs: index === 0 ? 2 : 0,
    reorder_level: item.reorder_level,
    incoming_packages: needsReorder ? 1 : 0,
    recommended_order_packages: needsReorder ? Math.max(1, item.reorder_level - item.stock_quantity + 1) : 0,
    average_unit_cost: String(item.cost),
    is_archived: archived,
    is_placeholder: item.is_placeholder,
    preferred_source: item.is_placeholder || archived ? null : supplierSource,
    supplier_sources: item.is_placeholder || archived ? [] : [supplierSource],
    repair_sources: index === 0 ? [{ repair_order_id: fixture.ids.repair_order, order_number: 'TPS-000301', vehicle_display: '2020 Freightliner Cascadia', unit_number: '144', packages: 2 }] : [],
    incoming_sources: needsReorder ? [{ purchase_order_id: 'po-visual-audit', po_number: 'PO-DB038-001', packages: 1, expected_at: null }] : [],
  }
})

function partDetail(part: (typeof partsItems)[number]) {
  return {
    ...part,
    recent_receipts: [{ receipt_id: `receipt-${part.id}`, receipt_number: 'RCV-DB038-001', purchase_order_id: 'po-visual-audit', po_number: 'PO-DB038-001', quantity: 1, unit_cost: '20.00', received_at: fixture.frozen_at }],
    recent_movements: [{ id: `movement-${part.id}`, movement_type: 'manual_adjustment', quantity_delta: 1, balance_after: part.available_packages, wac_after: part.average_unit_cost, occurred_at: fixture.frozen_at }],
  }
}

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

const repairMovement = {
  id: 'movement-visual-audit',
  inventory: { id: 'inventory-1', sku: 'DB-INVENTORY-001', name: 'Air filter' },
  movement_type: 'repair_reservation',
  quantity_delta: -2,
  balance_after: 0,
  wac_after: '20.00',
  source: { type: 'repair_order', id: fixture.ids.repair_order, order_number: 'TPS-000301' },
  occurred_at: fixture.frozen_at,
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

async function expectToolbarSelectContrast(page: Page, mode: 'dark' | 'high_contrast') {
  await expect(page.locator('.db-staff-shell')).toHaveAttribute('data-appearance-mode', mode)

  for (const [label, value, selectedText] of [
    ['Catalog', 'active', 'Active parts'],
    ['Sort', 'catalog', 'Catalog order'],
  ] as const) {
    const select = page.getByRole('combobox', { name: label })
    await expect(select).toBeVisible()
    await expect(select).toHaveValue(value)
    await expect(select.locator('option:checked')).toHaveText(selectedText)
    const styles = await select.evaluate((node) => {
      const style = getComputedStyle(node)
      return {
        background: style.backgroundColor,
        color: style.color,
        border: style.borderTopColor,
      }
    })
    expect(contrastRatio(styles.color, styles.background)).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(styles.border, styles.background)).toBeGreaterThanOrEqual(mode === 'high_contrast' ? 3 : 1.25)
    expect(styles.background).not.toBe('rgb(246, 248, 251)')
  }
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
    expect(box!.width).toBeGreaterThanOrEqual(104)
    expect(box!.width).toBeLessThanOrEqual(128)
  }
}

async function expectStockFactsFullyVisible(page: Page) {
  const body = page.locator('.db-parts-workbench__body')
  const inspector = page.locator('.db-parts-workbench__inspector')
  const stockSection = page.getByRole('heading', { name: 'Stock', exact: true }).locator('..')
  const facts = [
    ['Available', '0'],
    ['Needed for open repairs', '2'],
    ['Reorder at', '2'],
    ['Incoming', '1'],
  ] as const

  const [bodyBox, inspectorBox] = await Promise.all([body.boundingBox(), inspector.boundingBox()])
  expect(bodyBox).not.toBeNull()
  expect(inspectorBox).not.toBeNull()
  expect(inspectorBox!.x).toBeGreaterThanOrEqual(bodyBox!.x - 1)
  expect(inspectorBox!.x + inspectorBox!.width).toBeLessThanOrEqual(bodyBox!.x + bodyBox!.width + 1)

  for (const [label, value] of facts) {
    const term = stockSection.getByText(label, { exact: true })
    const fact = term.locator('..')
    const description = fact.locator('dd')
    await fact.scrollIntoViewIfNeeded()
    await expect(term).toBeVisible()
    await expect(description).toHaveText(value)
    for (const element of [term, description]) {
      expect(await element.evaluate((node) => {
        const scrollport = node.closest('.db-parts-workbench__inspector')
        if (!scrollport) return false
        const rect = node.getBoundingClientRect()
        const scrollportRect = scrollport.getBoundingClientRect()
        return rect.left >= scrollportRect.left - 1
          && rect.right <= scrollportRect.right + 1
          && rect.top >= scrollportRect.top - 1
          && rect.bottom <= scrollportRect.bottom + 1
          && node.scrollWidth <= node.clientWidth + 1
          && node.scrollHeight <= node.clientHeight + 1
      })).toBe(true)
    }
  }
}

async function expectSingleWorkbenchSelection(page: Page, expected: Locator) {
  await expect(page.locator('.db-parts-workbench__rows > button[aria-current="true"]')).toHaveCount(1)
  await expect(expected).toHaveAttribute('aria-current', 'true')
}

async function expectSingleOperationsSelection(rows: Locator, expected: Locator) {
  await expect(rows.locator(':scope > button[aria-current="true"]')).toHaveCount(1)
  await expect(expected).toHaveAttribute('aria-current', 'true')
}

type InventoryUpdate = { id: string; body: Record<string, unknown> }

async function installFixture(page: Page, {
  tenantLogoUrl = '/db038-tenant-logo.svg',
  readOnly = false,
  appearanceMode = 'dark',
  inventoryUpdateStatus = 200,
  inventoryUpdates = [],
}: {
  tenantLogoUrl?: string
  readOnly?: boolean
  appearanceMode?: 'dark' | 'high_contrast'
  inventoryUpdateStatus?: number
  inventoryUpdates?: InventoryUpdate[]
} = {}) {
  const failures: string[] = []
  const scopedInventoryItems = inventoryItems.map((item) => ({ ...item }))
  const scopedPartsItems = partsItems.map((item) => ({ ...item }))
  const expectedImageFailureResponses = new Set<string>()
  const expectedApiFailureResponses = new Set<string>()
  const intentionalImageFailurePaths = new Set(['/db038-broken-image.svg', '/db038-broken-logo.svg'])
  const fixtureSession = readOnly ? receptionistSession : garageOwnerSession
  const fixturePresentation = {
    ...fixtureSession.presentation,
    appearance: { ...fixtureSession.presentation.appearance, mode: appearanceMode },
  }
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
    if (url.pathname.endsWith('/auth/workos/me')) return json({ ...fixtureSession, presentation: fixturePresentation })
    if (url.pathname.endsWith('/auth/me/appearance')) return json(fixturePresentation)
    if (url.pathname.endsWith('/auth/tenant-branding') || url.pathname.endsWith('/admin/garage-profile')) return json({ name: 'Truck Pit Stop Wisconsin', state: 'WI', logo_url: tenantLogoUrl })
    if (url.pathname.endsWith('/messages/unread-summary')) return json({ unread_count: 0 })
    if (url.pathname.endsWith('/parts-operations/summary')) return json({ low_stock_count: 50, open_purchase_order_count: 4 })
    if (url.pathname.endsWith('/parts-operations/demand')) return json({ items: demandItems, total: demandItems.length, skip: 0, limit: 100, has_more: false })
    const partDetailMatch = url.pathname.match(/\/parts-operations\/parts\/([^/]+)$/)
    if (partDetailMatch && route.request().method() === 'GET') {
      const part = scopedPartsItems.find((item) => item.id === partDetailMatch[1])
      if (!part) return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'Part not found.' }) })
      return json(partDetail(part))
    }
    if (url.pathname.endsWith('/parts-operations/parts') && route.request().method() === 'GET') {
      const view = url.searchParams.get('view') || 'active'
      const attention = url.searchParams.get('attention')
      const search = (url.searchParams.get('search') || '').toLocaleLowerCase()
      const sort = url.searchParams.get('sort') || 'catalog'
      const skip = Number(url.searchParams.get('skip') || 0)
      const limit = Number(url.searchParams.get('limit') || 50)
      let items = scopedPartsItems.filter((item) => view === 'archived' ? item.is_archived : view === 'all' ? true : !item.is_archived)
      if (attention === 'needs_reorder') items = items.filter((item) => !item.is_placeholder && item.available_packages <= item.reorder_level)
      if (search) items = items.filter((item) => `${item.name} ${item.sku} ${item.location || ''} ${item.preferred_source?.supplier_name || ''} ${item.preferred_source?.supplier_part_number || ''}`.toLocaleLowerCase().includes(search))
      items = [...items].sort((left, right) => {
        if (sort === 'name') return left.name.localeCompare(right.name) || left.id.localeCompare(right.id)
        if (sort === 'available') return left.available_packages - right.available_packages || left.name.localeCompare(right.name)
        if (sort === 'reorder') return (left.available_packages - left.reorder_level) - (right.available_packages - right.reorder_level) || left.name.localeCompare(right.name)
        return Number(left.id.split('-').at(-1)) - Number(right.id.split('-').at(-1))
      })
      return json({ items: items.slice(skip, skip + limit), total: items.length, skip, limit, has_more: skip + limit < items.length })
    }
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
      const partIndex = scopedPartsItems.findIndex((item) => item.id === id)
      if (partIndex >= 0) {
        scopedPartsItems[partIndex] = {
          ...scopedPartsItems[partIndex],
          available_packages: body.stock_quantity === undefined ? scopedPartsItems[partIndex].available_packages : Number(body.stock_quantity),
          reorder_level: body.reorder_level === undefined ? scopedPartsItems[partIndex].reorder_level : Number(body.reorder_level),
        }
      }
      return json(updated)
    }
    if (url.pathname.endsWith('/inventory')) return json({ items: scopedInventoryItems, total: scopedInventoryItems.length, skip: 0, limit: 100, has_more: false })
    if (url.pathname.endsWith('/parts-operations/purchase-orders') && route.request().method() === 'GET') return json({ items: [purchaseOrder], total: 1, skip: 0, limit: 100, has_more: false })
    if (url.pathname.endsWith(`/parts-operations/purchase-orders/${purchaseOrder.id}`)) return json(purchaseOrderDetail)
    if (url.pathname.endsWith(`/parts-operations/returns/${vendorReturn.id}`)) return json(vendorReturnDetail)
    if (url.pathname.endsWith('/parts-operations/returns')) return json({ items: [vendorReturn], total: 1, skip: 0, limit: 100, has_more: false })
    if (url.pathname.endsWith('/parts-operations/cores')) return json({ items: [coreObligation], total: 1, skip: 0, limit: 100, has_more: false })
    if (url.pathname.endsWith('/parts-operations/activity')) return json({ items: [repairMovement], total: 1, skip: 0, limit: 100, has_more: false })
    if (url.pathname.endsWith('/messages/threads')) return json({ items: [], next_cursor: null, has_more: false })
    if (url.pathname.endsWith('/mechanics') || url.pathname.endsWith('/admin/staff') || url.pathname.endsWith('/mechanics/pto-requests/pending')) return json([])
    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: `Unhandled DB-038 fixture route: ${route.request().method()} ${url.pathname}` }) })
  })
  return { expectedImageFailureResponses }
}

test('DB-038 covers All parts, Needs reorder, Movement, and Purchasing across responsive views', async ({ browser }, testInfo) => {
  for (const [width, height] of [[1280, 900], [960, 900], [390, 844], [320, 720]]) {
    const context = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce', forcedColors: 'active' })
    const page = await context.newPage()
    const fixtureRuntime = await installFixture(page)
    await page.goto('/dashboard/garage/inventory')
    await expect(page.getByRole('heading', { name: 'Parts & inventory' })).toBeVisible()
    await expectIntegratedSearch(page.getByRole('searchbox', { name: 'Search parts' }))
    await expect(page.getByRole('list', { name: 'Parts operations workflow' })).toHaveCount(0)
    const workspaceViews = page.getByRole('navigation', { name: 'Parts and inventory views' })
    await expect(workspaceViews.locator('button[aria-current="page"]')).toHaveCount(1)
    await expect(workspaceViews.getByRole('button', { name: 'All parts' })).toHaveAttribute('aria-current', 'page')
    for (const label of ['All parts', 'Needs reorder', 'Movement']) {
      await expect(workspaceViews.getByRole('button', { name: label })).toHaveCSS('min-height', '48px')
    }
    await expect(page.locator('.db-parts-workbench__ledger[aria-label="99 matching parts"]')).toBeVisible()
    const partRows = page.locator('.db-parts-workbench__rows > button')
    await expect(partRows).toHaveCount(50)
    await expectSingleWorkbenchSelection(page, partRows.first())
    await expect(partRows.first().locator('img[src$="/db038-part-image.svg"]')).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath(`db038-first-selection-${width}.png`), fullPage: false })
    await partRows.first().click()
    const partPhoto = page.getByRole('img', { name: 'Air filter part photo' })
    await expect(partPhoto).toBeVisible()
    await expectSelectedPartImage(partPhoto, width)
    await expectStockFactsFullyVisible(page)
    if (width <= 760) await page.getByRole('button', { name: 'Back to parts' }).click()
    await expect(partRows.nth(1).locator('img[src$="/db038-tenant-logo.svg"]')).toBeVisible()
    await partRows.nth(1).click()
    const logoPlaceholder = page.getByRole('img', { name: 'Truck Pit Stop Wisconsin logo placeholder for Brake shoe' })
    await expect(logoPlaceholder).toBeVisible()
    await expectSelectedPartImage(logoPlaceholder, width)
    expect([...fixtureRuntime.expectedImageFailureResponses].some(url => new URL(url).pathname === '/db038-broken-image.svg')).toBe(true)
    if (width === 390) await page.screenshot({ path: testInfo.outputPath('db038-all-parts-mobile-390.png'), fullPage: false })

    await workspaceViews.getByRole('button', { name: 'Needs reorder' }).click()
    await expect(workspaceViews.locator('button[aria-current="page"]')).toHaveCount(1)
    await expect(workspaceViews.getByRole('button', { name: 'Needs reorder' })).toHaveAttribute('aria-current', 'page')
    await expect(page.locator('.db-parts-workbench__ledger[aria-label="2 matching parts"]')).toBeVisible()
    await expect(page.locator('.db-parts-workbench__rows > button')).toHaveCount(2)
    await expectSingleWorkbenchSelection(page, page.locator('.db-parts-workbench__rows > button').first())

    await workspaceViews.getByRole('button', { name: 'All parts' }).click()
    await page.getByRole('combobox', { name: 'Catalog' }).selectOption('archived')
    await expect(page.locator('.db-parts-workbench__ledger[aria-label="1 matching parts"]')).toBeVisible()
    const archivedRow = page.locator('.db-parts-workbench__rows > button').first()
    await archivedRow.click()
    await expect(page.getByRole('status')).toContainText('Archived part')
    await expect(page.getByRole('button', { name: 'Adjust available stock' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Add to purchase list' })).toHaveCount(0)

    await workspaceViews.getByRole('button', { name: 'Movement' }).click()
    await expect(workspaceViews.locator('button[aria-current="page"]')).toHaveCount(1)
    await expect(workspaceViews.getByRole('button', { name: 'Movement' })).toHaveAttribute('aria-current', 'page')
    await expect(page.getByText(/Reserved for a repair · 0 available after change/)).toBeVisible()
    await expect(page.getByRole('button', { name: 'TPS-000301' })).toBeVisible()

    await page.getByRole('button', { name: /Open purchase orders/ }).click()
    await expect(page).toHaveURL(/\/dashboard\/garage\/purchasing/)
    await expect(page.getByRole('heading', { name: 'Purchasing' })).toBeVisible()
    const purchasingAreas = page.getByRole('navigation', { name: 'Purchasing areas' })
    await expect(purchasingAreas.locator('button[aria-current="page"]')).toHaveCount(1)
    await expect(purchasingAreas.getByRole('button', { name: /Purchase orders/ })).toHaveAttribute('aria-current', 'page')
    const purchaseOrderRows = page.getByRole('group', { name: 'Purchase orders rows' })
    const purchaseOrderRow = purchaseOrderRows.getByRole('button', { name: /PO-DB038-001/i })
    await expectSingleOperationsSelection(purchaseOrderRows, purchaseOrderRow)
    await expect(page.getByRole('heading', { name: 'PO-DB038-001' })).toBeVisible()
    expect(await page.locator('body').evaluate(node => node.scrollWidth <= window.innerWidth)).toBe(true)
    expect(errors.get(page)).toEqual([])
    await context.close()
  }
})

test('DB-038 preserves photo fallbacks, bounded paging, and repair, PO, and receipt provenance', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 900 })
  const fixtureRuntime = await installFixture(page, { tenantLogoUrl: '/db038-broken-logo.svg' })
  await page.goto('/dashboard/garage/inventory')
  const ledger = page.locator('.db-parts-workbench__ledger[aria-label="99 matching parts"]')
  await expect(ledger).toBeVisible()
  await expectIntegratedSearch(page.getByRole('searchbox', { name: 'Search parts' }))
  const partRows = page.locator('.db-parts-workbench__rows > button')
  await expect(partRows).toHaveCount(50)
  await expect(page.getByText('1–50 of 99')).toBeVisible()
  expect(await ledger.evaluate(node => getComputedStyle(node).overflowY)).toMatch(/auto|scroll/)
  expect(await ledger.evaluate(node => node.scrollHeight > node.clientHeight)).toBe(true)
  await expect(partRows.nth(1).locator('.db-parts-workbench__photo svg')).toBeVisible()
  await expect(partRows.nth(2).locator('.db-parts-workbench__photo svg')).toBeVisible()
  await partRows.nth(1).click()
  await expect(page.getByRole('img', { name: 'No image available for Brake shoe' })).toBeVisible()
  await partRows.nth(2).click()
  await expect(page.getByRole('img', { name: 'No image available for Coolant' })).toBeVisible()
  expect([...fixtureRuntime.expectedImageFailureResponses].some(url => new URL(url).pathname === '/db038-broken-image.svg')).toBe(true)
  expect([...fixtureRuntime.expectedImageFailureResponses].some(url => new URL(url).pathname === '/db038-broken-logo.svg')).toBe(true)

  await partRows.first().click()
  await expect(page.getByRole('button', { name: /TPS-000301.*2 needed/i })).toBeVisible()
  await expect(page.getByRole('button', { name: /PO-DB038-001.*1 incoming/i })).toBeVisible()
  await expect(page.getByRole('button', { name: /RCV-DB038-001.*1 at \$20\.00/i })).toBeVisible()
  await page.getByRole('button', { name: /PO-DB038-001.*1 incoming/i }).click()
  await expect(page).toHaveURL(/\/dashboard\/garage\/purchasing\?view=orders&purchase_order=po-visual-audit/)
  const purchaseOrderRows = page.getByRole('group', { name: 'Purchase orders rows' })
  const purchaseOrderRow = purchaseOrderRows.getByRole('button', { name: /PO-DB038-001/i })
  await expectSingleOperationsSelection(purchaseOrderRows, purchaseOrderRow)
  await expect(page.getByRole('heading', { name: 'PO-DB038-001' })).toBeVisible()
  await expectStandaloneField(page.getByLabel(`Receive quantity for ${purchaseOrderDetail.lines[0].sku}`))
  await expectStandaloneField(page.getByLabel(`Receipt unit cost for ${purchaseOrderDetail.lines[0].sku}`))
  await page.screenshot({ path: testInfo.outputPath('db038-controls-audit-1280.png'), fullPage: false })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('heading', { name: 'PO-DB038-001' })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('db038-purchasing-mobile-390.png'), fullPage: false })
  expect(await page.locator('body').evaluate(node => node.scrollWidth <= window.innerWidth)).toBe(true)
  expect(errors.get(page)).toEqual([])
})

test('DB-038 stock changes preserve item ownership, permissions, validation, and responsive containment', async ({ browser }, testInfo) => {
  for (const [width, height] of [[1280, 900], [960, 900], [390, 844], [320, 720]]) {
    const context = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce' })
    const page = await context.newPage()
    const updates: InventoryUpdate[] = []
    const appearanceMode = width === 960 || width === 320 ? 'high_contrast' : 'dark'
    await installFixture(page, { inventoryUpdates: updates, appearanceMode })
    await page.goto('/dashboard/garage/inventory')
    await expectToolbarSelectContrast(page, appearanceMode)
    if (width === 1280) await page.screenshot({ path: testInfo.outputPath('db038-toolbar-dark-1280.png'), fullPage: false })
    const rows = page.locator('.db-parts-workbench__rows > button')
    await expectSingleWorkbenchSelection(page, rows.first())
    await rows.first().click()
    const selectedHeader = page.locator('.db-parts-workbench__part-head')
    await expect(selectedHeader).toContainText('DB-INVENTORY-001 · Bin A-01 · Unit not set')
    await expect(selectedHeader).not.toContainText('undefined')
    const controls = page.getByRole('heading', { name: 'Stock', exact: true }).locator('..')
    const edit = controls.getByRole('button', { name: 'Adjust available stock' })
    await expect(edit).toBeVisible()
    expect((await edit.boundingBox())!.height).toBeGreaterThanOrEqual(44)
    await edit.click()
    for (const label of ['Available packages', 'Adjustment reason']) {
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
      await controls.getByLabel('Available packages', { exact: true }).fill('8')
      await controls.getByRole('button', { name: 'Save change' }).click()
      await expect(controls.getByRole('alert')).toHaveText('Explain why available stock is changing.')
      expect(updates).toHaveLength(0)
      await controls.getByLabel('Adjustment reason', { exact: true }).fill('Cycle count correction')
      await controls.getByRole('button', { name: 'Save change' }).click()
      await expect(page.getByRole('status')).toContainText('Air filter stock setting saved.')
      expect(updates).toEqual([{ id: 'inventory-1', body: { stock_quantity: 8, stock_adjustment_reason: 'Cycle count correction' } }])
      await expectSingleWorkbenchSelection(page, rows.first())
      await expect(controls).toContainText('8')
      await controls.getByRole('button', { name: 'Change reorder point' }).click()
      await controls.getByLabel('Reorder at', { exact: true }).fill('6')
      await controls.getByRole('button', { name: 'Save change' }).click()
      expect(updates[1]).toEqual({ id: 'inventory-1', body: { reorder_level: 6 } })

      await controls.getByRole('button', { name: 'Adjust available stock' }).click()
      await controls.getByLabel('Available packages', { exact: true }).fill('77')
      await controls.getByLabel('Adjustment reason', { exact: true }).fill('Must not cross records')
      await rows.nth(1).click()
      await expect(page.getByRole('heading', { name: 'Brake shoe' })).toBeVisible()
      const nextControls = page.getByRole('heading', { name: 'Stock', exact: true }).locator('..')
      await nextControls.getByRole('button', { name: 'Adjust available stock' }).click()
      await expect(nextControls.getByLabel('Available packages', { exact: true })).toHaveValue('2')
      await expect(nextControls.getByLabel('Adjustment reason', { exact: true })).toHaveValue('')
    }
    expect(errors.get(page)).toEqual([])
    await context.close()
  }

  const failureContext = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const failurePage = await failureContext.newPage()
  await installFixture(failurePage, { inventoryUpdateStatus: 422 })
  await failurePage.goto('/dashboard/garage/inventory')
  await failurePage.locator('.db-parts-workbench__rows > button').first().click()
  const failureControls = failurePage.getByRole('heading', { name: 'Stock', exact: true }).locator('..')
  await failureControls.getByRole('button', { name: 'Change reorder point' }).click()
  await failureControls.getByLabel('Reorder at', { exact: true }).fill('9')
  await failureControls.getByRole('button', { name: 'Save change' }).click()
  await expect(failurePage.getByRole('alert')).toContainText('Inventory update could not be saved.')
  await expect(failureControls.getByLabel('Reorder at', { exact: true })).toHaveValue('9')
  expect(errors.get(failurePage)).toEqual([])
  await failureContext.close()

  const readOnlyContext = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const readOnlyPage = await readOnlyContext.newPage()
  await installFixture(readOnlyPage, { readOnly: true })
  await readOnlyPage.goto('/dashboard/garage/inventory')
  await readOnlyPage.locator('.db-parts-workbench__rows > button').first().click()
  const readOnlyControls = readOnlyPage.getByRole('heading', { name: 'Stock', exact: true }).locator('..')
  await expect(readOnlyControls).toContainText('You can view stock. Owners and admins can make changes.')
  await expect(readOnlyControls.getByRole('button', { name: 'Adjust available stock' })).toHaveCount(0)
  expect(errors.get(readOnlyPage)).toEqual([])
  await readOnlyContext.close()
})
