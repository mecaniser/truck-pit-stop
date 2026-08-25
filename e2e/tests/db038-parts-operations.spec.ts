import { expect, test, type Locator, type Page, type TestInfo } from '@playwright/test'
import fixture from '../../backend/tests/fixtures/db038_parts_operations.json'
import { garageOwnerSession, receptionistSession } from '../../frontend/src/test-fixtures/db035/staffSession'

const errors = new WeakMap<Page, string[]>()

type InventoryFixtureRow = {
  [key: string]: unknown
  id: string
  sku: string
  name: string
  stock_quantity: number
  reorder_level: number
  cost: string
  unit_type?: string | null
  supplier_name: string | null
  location: string | null
  image_url: string | null
  is_placeholder: boolean
  ets_retired_at: string | null
}

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

const inventoryItems: InventoryFixtureRow[] = Array.from({ length: 100 }, (_, index): InventoryFixtureRow => {
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
    preferred_source: item.is_placeholder || archived || index === 1 ? null : supplierSource,
    supplier_sources: item.is_placeholder || archived || index === 1 ? [] : [supplierSource],
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

async function expectWorkbenchEditorContrast(field: Locator) {
  const styles = await field.evaluate((node) => {
    const style = getComputedStyle(node)
    const placeholderStyle = getComputedStyle(node, '::placeholder')
    return {
      background: style.backgroundColor,
      color: style.color,
      caret: style.caretColor,
      placeholder: placeholderStyle.color,
      colorScheme: style.colorScheme,
    }
  })
  expect(contrastRatio(styles.color, styles.background)).toBeGreaterThanOrEqual(4.5)
  expect(styles.caret).toBe(styles.color)
  expect(styles.colorScheme).not.toBe('light')
  if (await field.getAttribute('placeholder')) {
    expect(contrastRatio(styles.placeholder, styles.background)).toBeGreaterThanOrEqual(4.5)
  }
}

async function expectPartsStepperFocus(input: Locator, mode: 'pointer' | 'keyboard') {
  await expect(input).toBeFocused()
  const form = input.locator('xpath=ancestor::form[1]')
  const stepper = input.locator('xpath=../..')
  const pill = input.locator('..')
  await expect(form).toHaveAttribute('data-focus-mode', mode)
  const presentation = await stepper.evaluate((node) => {
    const elements = [...node.querySelectorAll(':scope > span'), ...node.querySelectorAll(':scope > span:first-child > button, :scope > span:first-child > input')]
    return elements.map((element) => {
      const style = getComputedStyle(element)
      const outlineWidth = Number.parseFloat(style.outlineWidth)
      return {
        tag: element.tagName,
        outlineStyle: style.outlineStyle,
        outlineWidth,
        outlineColor: style.outlineColor,
        boxShadow: style.boxShadow,
        hasIndicator: (style.outlineStyle !== 'none' && outlineWidth > 0) || style.boxShadow !== 'none',
      }
    })
  })
  expect(presentation.filter((part) => part.hasIndicator)).toHaveLength(mode === 'keyboard' ? 1 : 0)
  expect(presentation.slice(1).every((part) => !part.hasIndicator)).toBe(true)
  if (mode === 'keyboard') {
    const pillStyle = await pill.evaluate((node) => {
      const style = getComputedStyle(node)
      return { outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth, boxShadow: style.boxShadow }
    })
    expect(pillStyle.outlineStyle).toBe('solid')
    expect(Number.parseFloat(pillStyle.outlineWidth)).toBeGreaterThanOrEqual(2)
    expect(pillStyle.boxShadow).toBe('none')
  }
}

async function expectCompactStockStepperLine(input: Locator) {
  const stepper = input.locator('xpath=ancestor::span[contains(concat(" ", normalize-space(@class), " "), " db-parts-workbench__quantity-stepper ")][1]')
  const geometry = await stepper.evaluate((node) => {
    const directSpans = Array.from(node.children).filter((child): child is HTMLElement => child instanceof HTMLElement && child.tagName === 'SPAN')
    const pill = directSpans[0]
    const unit = directSpans[1]
    const bounds = (element: Element) => {
      const rect = element.getBoundingClientRect()
      return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom, width: rect.width, height: rect.height }
    }
    const unitStyle = unit ? getComputedStyle(unit) : null
    return {
      childCount: directSpans.length,
      stepper: bounds(node),
      pill: pill ? bounds(pill) : null,
      unit: unit ? bounds(unit) : null,
      controls: pill ? Array.from(pill.children).map(bounds) : [],
      unitText: unit?.textContent?.trim() ?? '',
      unitWhiteSpace: unitStyle?.whiteSpace ?? '',
      unitOverflowWrap: unitStyle?.overflowWrap ?? '',
      unitWordBreak: unitStyle?.wordBreak ?? '',
      unitFits: unit ? unit.scrollWidth <= unit.clientWidth + 1 && unit.scrollHeight <= unit.clientHeight + 1 : false,
      stepperFits: node.scrollWidth <= node.clientWidth + 1 && node.scrollHeight <= node.clientHeight + 1,
    }
  })
  expect(geometry.childCount).toBe(2)
  expect(geometry.unitText).toBe('units')
  expect(geometry.unitWhiteSpace).toBe('nowrap')
  expect(geometry.unitOverflowWrap).toBe('normal')
  expect(geometry.unitWordBreak).toBe('normal')
  expect(geometry.unitFits).toBe(true)
  expect(geometry.stepperFits).toBe(true)
  expect(geometry.pill).not.toBeNull()
  expect(geometry.unit).not.toBeNull()
  expect(geometry.controls).toHaveLength(3)
  expect(geometry.unit!.left).toBeGreaterThanOrEqual(geometry.pill!.right - 1)
  expect(Math.abs((geometry.unit!.top + geometry.unit!.bottom) / 2 - (geometry.pill!.top + geometry.pill!.bottom) / 2)).toBeLessThanOrEqual(1)
  for (const control of geometry.controls) {
    expect(control.top).toBeGreaterThanOrEqual(geometry.pill!.top - 1)
    expect(control.bottom).toBeLessThanOrEqual(geometry.pill!.bottom + 1)
  }
}

async function expectToolbarOptionsContrast(page: Page, mode: 'dark' | 'high_contrast') {
  await expect(page.locator('.db-staff-shell')).toHaveAttribute('data-appearance-mode', mode)
  const options = page.getByRole('button', { name: 'Ledger options' })
  await expect(options).toBeVisible()
  await options.click()
  await expect(options).toHaveAttribute('aria-expanded', 'true')
  await expect(page.locator('.db-parts-workbench__options-popover select')).toHaveCount(0)
  const sortTrigger = page.getByRole('button', { name: 'Sort Catalog order' })
  await expect(sortTrigger).toBeVisible()
  expect(await sortTrigger.evaluate((node) => node.matches(':focus-visible'))).toBe(false)
  const styles = await sortTrigger.evaluate((node) => {
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
  await sortTrigger.click()
  const selectedSort = page.getByRole('option', { name: 'Catalog order' })
  await expect(selectedSort).toHaveAttribute('aria-selected', 'true')
  const optionStyles = await selectedSort.evaluate((node) => {
    const style = getComputedStyle(node)
    return { background: style.backgroundColor, color: style.color, outline: style.outlineStyle, boxShadow: style.boxShadow }
  })
  expect(contrastRatio(optionStyles.color, optionStyles.background)).toBeGreaterThanOrEqual(4.5)
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog', { name: 'Ledger options' })).toBeHidden()
  await expect(options).toBeFocused()
}

async function expectPurchasingQuantityStepper(page: Page, appearanceMode: 'light' | 'dark' | 'high_contrast') {
  const input = page.getByRole('textbox', { name: 'Quantity for Air filter' })
  const decrease = page.getByRole('button', { name: 'Decrease Quantity for Air filter' })
  const increase = page.getByRole('button', { name: 'Increase Quantity for Air filter' })
  const stepper = input.locator('xpath=ancestor::*[contains(@class,"db-purchasing__quantity-stepper")]')
  await expect(input).toHaveAttribute('type', 'text')
  await expect(page.getByRole('spinbutton', { name: 'Quantity for Air filter' })).toHaveCount(0)
  await expect(input).toHaveValue('3')

  await page.emulateMedia({ forcedColors: 'none' })
  const normalStyles = await input.evaluate((node) => {
    const style = getComputedStyle(node)
    const pill = getComputedStyle(node.parentElement!)
    return {
      background: style.backgroundColor,
      color: style.color,
      pillBackground: pill.backgroundColor,
      colorScheme: style.colorScheme,
    }
  })
  expect(normalStyles.background).toMatch(/,\s*0\)$/)
  expect(contrastRatio(normalStyles.color, normalStyles.pillBackground)).toBeGreaterThanOrEqual(4.5)
  if (appearanceMode !== 'light') expect(normalStyles.colorScheme).not.toBe('light')

  for (const control of [decrease, input, increase]) {
    const box = await control.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.width).toBeGreaterThanOrEqual(44)
    expect(box!.height).toBeGreaterThanOrEqual(44)
  }
  const stepperBox = await stepper.boundingBox()
  const costBox = await page.locator('.db-purchasing__line-cost').first().boundingBox()
  const lineBox = await page.locator('.db-purchasing__line').first().boundingBox()
  expect(stepperBox).not.toBeNull()
  expect(costBox).not.toBeNull()
  expect(lineBox).not.toBeNull()
  expect(stepperBox!.x).toBeGreaterThanOrEqual(0)
  expect(stepperBox!.x + stepperBox!.width).toBeLessThanOrEqual(await page.evaluate(() => window.innerWidth))
  const overlapsCost = !(
    stepperBox!.x + stepperBox!.width <= costBox!.x
    || costBox!.x + costBox!.width <= stepperBox!.x
    || stepperBox!.y + stepperBox!.height <= costBox!.y
    || costBox!.y + costBox!.height <= stepperBox!.y
  )
  expect(overlapsCost).toBe(false)
  expect(stepperBox!.x).toBeGreaterThanOrEqual(lineBox!.x)
  expect(stepperBox!.x + stepperBox!.width).toBeLessThanOrEqual(lineBox!.x + lineBox!.width)

  await page.emulateMedia({ forcedColors: 'active' })
  const forcedStyles = await input.evaluate((node) => {
    const style = getComputedStyle(node)
    return { background: style.backgroundColor, color: style.color }
  })
  expect(contrastRatio(forcedStyles.color, forcedStyles.background)).toBeGreaterThanOrEqual(4.5)
  await page.emulateMedia({ forcedColors: 'none' })

  await increase.click()
  await expect(input).toHaveValue('4')
  await expect(page.getByText('1 line · $80.00')).toBeVisible()
}

async function expectRuntimeIdentityGeometry(page: Page, width: number) {
  const identityRow = page.locator('.db-staff-nav__brand-row')
  const productIdentity = identityRow.locator('.db-brand-attribution')
  const runtimeIdentity = identityRow.locator('[aria-label^="Local development runtime:"]')
  const viewportWidth = await page.evaluate(() => window.innerWidth)

  if (width === 960) {
    await expect(runtimeIdentity).toBeHidden()
    const hiddenGeometry = await runtimeIdentity.evaluate((node) => ({
      display: getComputedStyle(node).display,
      clientRects: node.getClientRects().length,
      offsetWidth: (node as HTMLElement).offsetWidth,
    }))
    expect(hiddenGeometry).toEqual({ display: 'none', clientRects: 0, offsetWidth: 0 })
    expect(await identityRow.evaluate((node) => node.scrollWidth <= node.clientWidth + 1)).toBe(true)
    expect(await page.locator('body').evaluate((node) => node.scrollWidth <= window.innerWidth)).toBe(true)
    return
  }

  await expect(productIdentity).toContainText('DieselBridge')
  await expect(runtimeIdentity).toBeVisible()

  const [rowBox, productBox, runtimeBox] = await Promise.all([
    identityRow.boundingBox(),
    productIdentity.boundingBox(),
    runtimeIdentity.boundingBox(),
  ])
  expect(rowBox).not.toBeNull()
  expect(productBox).not.toBeNull()
  expect(runtimeBox).not.toBeNull()

  if (width === 320) {
    const intersects = !(
      productBox!.x + productBox!.width <= runtimeBox!.x
      || runtimeBox!.x + runtimeBox!.width <= productBox!.x
      || productBox!.y + productBox!.height <= runtimeBox!.y
      || runtimeBox!.y + runtimeBox!.height <= productBox!.y
    )
    expect(intersects).toBe(false)
  }

  for (const box of [productBox!, runtimeBox!]) {
    expect(box.x).toBeGreaterThanOrEqual(rowBox!.x - 1)
    expect(box.x + box.width).toBeLessThanOrEqual(rowBox!.x + rowBox!.width + 1)
    expect(box.y).toBeGreaterThanOrEqual(rowBox!.y - 1)
    expect(box.y + box.height).toBeLessThanOrEqual(rowBox!.y + rowBox!.height + 1)
    expect(box.x).toBeGreaterThanOrEqual(-1)
    expect(box.x + box.width).toBeLessThanOrEqual(viewportWidth + 1)
  }

  if (width === 320) {
    for (const label of [productIdentity, runtimeIdentity]) {
      expect(await label.evaluate((node) => node.scrollWidth <= node.clientWidth + 1)).toBe(true)
    }
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
  await page.getByRole('tab', { name: 'Stock' }).click()
  const stockSection = page.getByRole('tabpanel', { name: 'Stock' })
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
    const displayedValue = label === 'Available' || label === 'Reorder at'
      ? description.locator(':scope > span')
      : description
    await fact.scrollIntoViewIfNeeded()
    await expect(term).toBeVisible()
    await expect(displayedValue).toHaveText(value)
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

async function expectServiceManualHierarchy(page: Page, width: number) {
  const selectedRow = page.locator('.db-parts-workbench__row.is-selected')
  const actionBlock = page.locator('.db-parts-workbench__selected-action')
  const [rowStyle, actionStyle, frameStyle, headingStyle] = await Promise.all([
    selectedRow.evaluate((node) => ({ background: getComputedStyle(node).backgroundColor, color: getComputedStyle(node).color })),
    actionBlock.evaluate((node) => ({ background: getComputedStyle(node).backgroundColor, color: getComputedStyle(node).color })),
    page.locator('.db-parts-workbench').evaluate((node) => ({ radius: getComputedStyle(node).borderRadius })),
    page.locator('.db-parts-workbench__table-head').evaluate((node) => ({ style: getComputedStyle(node).borderBottomStyle, width: getComputedStyle(node).borderBottomWidth })),
  ])
  expect(rowStyle).toEqual(actionStyle)
  expect(frameStyle.radius).toBe(width <= 420 ? '0px' : '5px')
  expect(headingStyle.style).toBe('double')
  expect(Number.parseFloat(headingStyle.width)).toBeGreaterThanOrEqual(3)

  const primary = page.getByRole('button', { name: 'Add to purchase list' })
  const secondary = page.getByRole('button', { name: 'Adjust on-hand quantity' })
  const [primaryStyle, secondaryStyle] = await Promise.all([
    primary.evaluate((node) => ({ background: getComputedStyle(node).backgroundColor, color: getComputedStyle(node).color })),
    secondary.evaluate((node) => ({ background: getComputedStyle(node).backgroundColor, color: getComputedStyle(node).color, border: getComputedStyle(node).borderTopColor })),
  ])
  expect(primaryStyle.background).not.toBe(secondaryStyle.background)
  expect(primaryStyle.background).not.toBe('rgba(0, 0, 0, 0)')
  expect(contrastRatio(primaryStyle.color, primaryStyle.background)).toBeGreaterThanOrEqual(4.5)
  expect(contrastRatio(secondaryStyle.color, actionStyle.background)).toBeGreaterThanOrEqual(4.5)
  expect(secondaryStyle.border).toBe(secondaryStyle.color)

  const inspectorTabs = page.getByRole('tablist', { name: 'Selected part details' })
  await expect(inspectorTabs.getByRole('tab')).toHaveCount(4)
  await expect(inspectorTabs.locator('[aria-selected="true"]')).toHaveCount(1)
  const overviewTab = inspectorTabs.getByRole('tab', { name: 'Overview' })
  await overviewTab.focus()
  await overviewTab.press('End')
  await expect(inspectorTabs.getByRole('tab', { name: 'History' })).toHaveAttribute('aria-selected', 'true')
  await inspectorTabs.getByRole('tab', { name: 'History' }).press('Home')
  await expect(overviewTab).toHaveAttribute('aria-selected', 'true')
  const figureFamily = await page.getByRole('tabpanel', { name: 'Overview' }).locator('dd').first().evaluate((node) => getComputedStyle(node).fontFamily)
  expect(figureFamily.toLowerCase()).toMatch(/mono|menlo|consolas/)
}

async function expectSupplierRelationshipHierarchy(page: Page) {
  const section = page.locator('.db-parts-workbench__supplier-section')
  const relationship = section.locator('.db-parts-workbench__supplier-relationship')
  const identity = relationship.locator('.db-parts-workbench__supplier-identity')
  const details = relationship.locator('dl')
  const detailRows = details.locator(':scope > div')
  const supplierName = relationship.locator('.db-parts-workbench__supplier-name')
  const supplierMeta = relationship.locator('.db-parts-workbench__supplier-meta')
  const reliability = relationship.locator('.db-parts-workbench__supplier-reliability')

  await expect(section.getByRole('heading', { name: 'Supplied by' })).toBeVisible()
  await expect(section.getByRole('button', { name: 'Change preferred supplier' })).toBeVisible()
  await expect(section.getByRole('button', { name: 'Change preferred supplier' })).toHaveCSS('min-height', '44px')
  await expect(supplierName).toHaveText('Fleet Parts Co')
  await expect(supplierMeta).toContainText('NET 30 · Lead 2 days · Min 1 units · Pack size 1')
  await expect(reliability.getByLabel('90% on-time delivery reliability')).toHaveText('90%')
  await expect(detailRows).toHaveCount(3)
  await expect(details.getByText('Last receipt / purchase', { exact: true })).toBeVisible()

  const separatorGeometry = await relationship.evaluate((node) => {
    const identityNode = node.querySelector<HTMLElement>('.db-parts-workbench__supplier-identity')!
    const detailsNode = node.querySelector<HTMLElement>('dl')!
    const rows = [...detailsNode.querySelectorAll<HTMLElement>(':scope > div')]
    return {
      identityBottom: getComputedStyle(identityNode).borderBottomWidth,
      detailsTop: getComputedStyle(detailsNode).borderTopWidth,
      rowTops: rows.map((row) => getComputedStyle(row).borderTopWidth),
    }
  })
  expect(separatorGeometry).toEqual({ identityBottom: '0px', detailsTop: '1px', rowTops: ['0px', '1px', '1px'] })

  const typeHierarchy = await Promise.all([
    supplierName.evaluate((node) => ({ size: Number.parseFloat(getComputedStyle(node).fontSize), weight: Number(getComputedStyle(node).fontWeight) })),
    supplierMeta.evaluate((node) => ({ size: Number.parseFloat(getComputedStyle(node).fontSize), weight: Number(getComputedStyle(node).fontWeight) })),
    reliability.locator('strong').evaluate((node) => ({ size: Number.parseFloat(getComputedStyle(node).fontSize), weight: Number(getComputedStyle(node).fontWeight) })),
  ])
  expect(typeHierarchy[0].size).toBeGreaterThan(typeHierarchy[1].size)
  expect(typeHierarchy[0].weight).toBeGreaterThan(typeHierarchy[1].weight)
  expect(typeHierarchy[2].size).toBeGreaterThanOrEqual(typeHierarchy[0].size)
  expect(typeHierarchy[2].weight).toBeGreaterThanOrEqual(typeHierarchy[0].weight)
}

async function expectSupplierSourceInteraction(page: Page, width: number, testInfo: TestInfo) {
  await page.getByRole('tab', { name: 'Ordering' }).click()
  const sourceList = page.locator('.db-parts-workbench__sources-list')
  const sourceTrigger = page.getByRole('button', { name: 'Edit Fleet Parts Co supplier source' })
  const editCue = sourceList.getByText('Edit source', { exact: true })
  await sourceList.scrollIntoViewIfNeeded()
  await expect(sourceTrigger).toBeVisible()
  await expect(editCue).toBeVisible()
  await expect(sourceTrigger).toContainText('Last received cost')
  const [triggerBox, inspectorBox, cueBox] = await Promise.all([
    sourceTrigger.boundingBox(),
    page.locator('.db-parts-workbench__inspector').boundingBox(),
    editCue.boundingBox(),
  ])
  expect(triggerBox).not.toBeNull()
  expect(inspectorBox).not.toBeNull()
  expect(cueBox).not.toBeNull()
  expect(triggerBox!.height).toBeGreaterThanOrEqual(44)
  expect(triggerBox!.x).toBeGreaterThanOrEqual(inspectorBox!.x - 1)
  expect(triggerBox!.x + triggerBox!.width).toBeLessThanOrEqual(inspectorBox!.x + inspectorBox!.width + 1)
  expect(cueBox!.x).toBeGreaterThanOrEqual(triggerBox!.x - 1)
  expect(cueBox!.x + cueBox!.width).toBeLessThanOrEqual(triggerBox!.x + triggerBox!.width + 1)
  if (width === 1280 || width === 390) await page.screenshot({ path: testInfo.outputPath(`db038-ordering-source-row-${width}.png`), fullPage: false })

  await sourceTrigger.click()
  const existingForm = page.getByRole('form', { name: 'Edit Fleet Parts Co supplier source' })
  const partNumber = existingForm.getByRole('textbox', { name: 'Supplier part number' })
  await expect(existingForm).toHaveAttribute('data-focus-mode', 'pointer')
  await expect(partNumber).toBeFocused()
  await expect(page.getByRole('button', { name: 'Edit Fleet Parts Co supplier source' })).toHaveCount(0)
  await expect(sourceList.getByText('Edit source', { exact: true })).toHaveCount(0)
  const pointerStyle = await partNumber.evaluate((node) => {
    const style = getComputedStyle(node)
    const workbench = node.closest<HTMLElement>('.db-parts-workbench')!
    return {
      outlineWidth: style.outlineWidth,
      outlineStyle: style.outlineStyle,
      outlineColor: style.outlineColor,
      boxShadow: style.boxShadow,
      caretColor: style.caretColor,
      backgroundColor: style.backgroundColor,
      color: style.color,
      oxide: getComputedStyle(workbench).getPropertyValue('--parts-oxide').trim(),
    }
  })
  expect(Number.parseFloat(pointerStyle.outlineWidth)).toBe(0)
  expect(pointerStyle.outlineStyle).toBe('none')
  expect(pointerStyle.boxShadow).toBe('none')
  expect(pointerStyle.outlineColor).not.toBe(pointerStyle.oxide)
  expect(pointerStyle.caretColor).not.toBe('rgba(0, 0, 0, 0)')
  expect(contrastRatio(pointerStyle.color, pointerStyle.backgroundColor)).toBeGreaterThanOrEqual(4.5)
  if (width === 1280 || width === 390) await page.screenshot({ path: testInfo.outputPath(`db038-ordering-source-editor-pointer-${width}.png`), fullPage: false })

  await partNumber.press('Tab')
  await expect(existingForm).toHaveAttribute('data-focus-mode', 'keyboard')
  const minimum = existingForm.getByRole('spinbutton', { name: 'Minimum order' })
  await expect(minimum).toBeFocused()
  const keyboardStyle = await minimum.evaluate((node) => {
    const style = getComputedStyle(node)
    const workbench = node.closest<HTMLElement>('.db-parts-workbench')!
    return {
      outlineWidth: style.outlineWidth,
      outlineStyle: style.outlineStyle,
      outlineColor: style.outlineColor,
      boxShadow: style.boxShadow,
      oxide: getComputedStyle(workbench).getPropertyValue('--parts-oxide').trim(),
    }
  })
  expect(keyboardStyle.outlineStyle).toBe('solid')
  expect(Number.parseFloat(keyboardStyle.outlineWidth)).toBeGreaterThanOrEqual(2)
  expect(keyboardStyle.boxShadow).toBe('none')
  expect(keyboardStyle.outlineColor).not.toBe(keyboardStyle.oxide)
  await page.keyboard.press('Tab')
  await page.keyboard.press('Tab')
  await page.keyboard.press('Tab')
  await expect(existingForm.getByRole('checkbox', { name: 'Use as preferred source for this part' })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(existingForm.getByRole('button', { name: 'Remove source' })).toBeFocused()

  await page.emulateMedia({ forcedColors: 'active' })
  const forcedStyle = await existingForm.getByRole('button', { name: 'Remove source' }).evaluate((node) => {
    const style = getComputedStyle(node)
    return { outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth, boxShadow: style.boxShadow, forcedColorAdjust: style.forcedColorAdjust }
  })
  expect(forcedStyle.outlineStyle).toBe('solid')
  expect(Number.parseFloat(forcedStyle.outlineWidth)).toBeGreaterThanOrEqual(2)
  expect(forcedStyle.boxShadow).toBe('none')
  expect(forcedStyle.forcedColorAdjust).toBe('auto')
  await page.emulateMedia({ forcedColors: 'none' })
  await existingForm.getByRole('button', { name: 'Cancel' }).click()
  await expect(sourceTrigger).toBeFocused()

  await sourceTrigger.focus()
  await sourceTrigger.press('Enter')
  const keyboardForm = page.getByRole('form', { name: 'Edit Fleet Parts Co supplier source' })
  await expect(keyboardForm).toHaveAttribute('data-focus-mode', 'keyboard')
  await expect(keyboardForm.getByRole('textbox', { name: 'Supplier part number' })).toBeFocused()
  expect(await keyboardForm.locator(':focus-visible').count()).toBe(1)
  await keyboardForm.getByRole('button', { name: 'Cancel' }).click()
  await expect(sourceTrigger).toBeFocused()

  const addSource = page.getByRole('button', { name: 'Add supplier source' })
  await addSource.click()
  const newForm = page.getByRole('form', { name: 'Add supplier source' })
  const supplierSelect = newForm.getByRole('combobox', { name: 'Supplier' })
  await expect(newForm).toHaveAttribute('data-focus-mode', 'pointer')
  await expect(supplierSelect).toBeFocused()
  const newPointerStyle = await supplierSelect.evaluate((node) => {
    const style = getComputedStyle(node)
    return { outlineWidth: style.outlineWidth, outlineStyle: style.outlineStyle, boxShadow: style.boxShadow }
  })
  expect(Number.parseFloat(newPointerStyle.outlineWidth)).toBe(0)
  expect(newPointerStyle.outlineStyle).toBe('none')
  expect(newPointerStyle.boxShadow).toBe('none')
  await newForm.getByRole('button', { name: 'Cancel' }).click()
  await expect(addSource).toBeFocused()

  await addSource.focus()
  await addSource.press('Enter')
  const keyboardNewForm = page.getByRole('form', { name: 'Add supplier source' })
  await expect(keyboardNewForm).toHaveAttribute('data-focus-mode', 'keyboard')
  await expect(keyboardNewForm.getByRole('combobox', { name: 'Supplier' })).toBeFocused()
  expect(await keyboardNewForm.locator(':focus-visible').count()).toBe(1)
  await keyboardNewForm.getByRole('button', { name: 'Cancel' }).click()
  await expect(addSource).toBeFocused()
}

async function expectStockFactRules(page: Page) {
  const stockPanel = page.getByRole('tabpanel', { name: 'Stock' })
  const facts = stockPanel.locator('.db-parts-workbench__facts')
  const factRows = facts.locator(':scope > div')
  await expect(factRows).toHaveCount(4)
  await expect(facts.getByText('Needed for open repairs', { exact: true })).toBeVisible()
  await expect(facts.getByText('Incoming', { exact: true })).toBeVisible()
  await expect(stockPanel.getByLabel('Needed for open repairs', { exact: true })).toHaveCount(0)
  await expect(stockPanel.getByLabel('Incoming', { exact: true })).toHaveCount(0)

  const geometry = await facts.evaluate((node) => {
    const style = getComputedStyle(node)
    const rows = [...node.querySelectorAll<HTMLElement>(':scope > div')]
    return {
      top: { width: Number.parseFloat(style.borderTopWidth), style: style.borderTopStyle },
      bottom: { width: Number.parseFloat(style.borderBottomWidth), style: style.borderBottomStyle },
      columns: style.gridTemplateColumns.trim().split(/\s+/).length,
      inlineEnds: rows.map((row) => Number.parseFloat(getComputedStyle(row).borderInlineEndWidth)),
    }
  })
  expect(geometry.top).toEqual({ width: 1, style: 'solid' })
  expect(geometry.bottom).toEqual({ width: 1, style: 'solid' })
  if (geometry.columns === 1) expect(geometry.inlineEnds).toEqual([0, 0, 0, 0])
  else expect(geometry.inlineEnds).toEqual([1, 0, 1, 0])
}

async function expectExpandedStockFact(stockPanel: Locator, editor: Locator, cancelName: string) {
  const facts = stockPanel.locator('.db-parts-workbench__facts')
  const activeFact = editor.locator('xpath=ancestor::*[contains(concat(" ", normalize-space(@class), " "), " db-parts-workbench__fact ")][1]')
  const cancel = editor.getByRole('button', { name: cancelName })
  const save = editor.getByRole('button', { name: 'Save' })
  const [factsBox, activeBox, cancelBox, saveBox] = await Promise.all([
    facts.boundingBox(),
    activeFact.boundingBox(),
    cancel.boundingBox(),
    save.boundingBox(),
  ])
  for (const box of [factsBox, activeBox, cancelBox, saveBox]) expect(box).not.toBeNull()
  expect(activeBox!.x).toBeCloseTo(factsBox!.x, 0)
  expect(activeBox!.width).toBeCloseTo(factsBox!.width, 0)
  expect(cancelBox!.width).toBeGreaterThanOrEqual(44)
  expect(cancelBox!.height).toBeGreaterThanOrEqual(44)
  expect(cancelBox!.y + cancelBox!.height).toBeLessThanOrEqual(saveBox!.y + 1)
  const derivedPositions = await facts.evaluate((node) => {
    const active = node.querySelector<HTMLElement>('.db-parts-workbench__fact.is-editing')!.getBoundingClientRect()
    return ['Needed for open repairs', 'Incoming'].map((label) => {
      const term = [...node.querySelectorAll<HTMLElement>('dt')].find((candidate) => candidate.textContent === label)!
      return { top: term.closest('div')!.getBoundingClientRect().top, activeBottom: active.bottom }
    })
  })
  for (const position of derivedPositions) expect(position.top).toBeGreaterThanOrEqual(position.activeBottom - 1)
  expect(await save.evaluate((node) => getComputedStyle(node).whiteSpace)).toBe('nowrap')
  expect(await save.evaluate((node) => node.scrollWidth <= node.clientWidth + 1)).toBe(true)
}

async function expectSingleWorkbenchSelection(page: Page, expected: Locator) {
  await expect(page.locator('.db-parts-workbench__row-select[aria-current="true"]')).toHaveCount(1)
  await expect(expected).toHaveAttribute('aria-current', 'true')
}

async function expectSingleOperationsSelection(rows: Locator, expected: Locator) {
  await expect(rows.locator(':scope > button[aria-current="true"]')).toHaveCount(1)
  await expect(expected).toHaveAttribute('aria-current', 'true')
}

async function expectCompactLedgerHitTargets(page: Page) {
  const ledger = page.locator('.db-parts-workbench__ledger')
  const rowTarget = page.locator('.db-parts-workbench__row-select').first()
  const checkTarget = page.getByRole('checkbox', { name: /purchase preparation/ }).first()
  await expect(ledger).toBeVisible()
  await expect(rowTarget).toBeVisible()
  await expect(checkTarget).toBeVisible()
  for (const target of [rowTarget, checkTarget]) {
    expect(await target.evaluate((node) => {
      const rect = node.getBoundingClientRect()
      const hit = document.elementFromPoint(rect.left + (rect.width / 2), rect.top + (rect.height / 2))
      return rect.width >= 18
        && rect.height >= 18
        && Boolean(hit)
        && (hit === node || node.contains(hit))
    })).toBe(true)
  }
  expect(await ledger.evaluate((node) => node.scrollLeft)).toBe(0)
}

async function expectNaturalLoadMoreFlow(page: Page) {
  const ledger = page.locator('.db-parts-workbench__ledger')
  const loadMore = ledger.locator('.db-parts-workbench__load-more')
  await expect(loadMore).toBeAttached()
  await ledger.evaluate((node) => { node.scrollTop = 0 })
  const before = await ledger.evaluate((node) => {
    const load = node.querySelector<HTMLElement>('.db-parts-workbench__load-more')
    const lastRow = node.querySelector<HTMLElement>('.db-parts-workbench__row:last-child')
    if (!load || !lastRow) return null
    const owner = node.getBoundingClientRect()
    const control = load.getBoundingClientRect()
    const row = lastRow.getBoundingClientRect()
    return {
      position: getComputedStyle(load).position,
      isLastChild: node.lastElementChild === load,
      beginsBelowLastRow: control.top >= row.bottom - 1,
      outsideViewportAtTop: control.top >= owner.bottom - 1,
    }
  })
  expect(before).toEqual({
    position: 'static',
    isLastChild: true,
    beginsBelowLastRow: true,
    outsideViewportAtTop: true,
  })

  await ledger.evaluate((node) => { node.scrollTop = node.scrollHeight })
  await expect.poll(() => ledger.evaluate((node) => {
    const load = node.querySelector<HTMLElement>('.db-parts-workbench__load-more')
    if (!load) return false
    const owner = node.getBoundingClientRect()
    const control = load.getBoundingClientRect()
    return node.scrollTop > 0 && control.top >= owner.top - 1 && control.bottom <= owner.bottom + 1
  })).toBe(true)
}

async function expectLedgerLineTreatment(page: Page, width: number) {
  const firstRow = page.locator('.db-parts-workbench__row').first()
  const rowBorders = await firstRow.evaluate((node) => {
    const style = getComputedStyle(node)
    return [style.borderTopWidth, style.borderBottomWidth].map(Number.parseFloat)
  })
  expect(rowBorders).toEqual([0, 0])
  if (width > 760) {
    const tableHead = page.locator('.db-parts-workbench__table-head')
    const [headerTemplate, rowTemplate, asymmetricGuides] = await Promise.all([
      tableHead.evaluate((node) => getComputedStyle(node).gridTemplateColumns),
      firstRow.evaluate((node) => getComputedStyle(node).gridTemplateColumns),
      Promise.all(['is-cost', 'is-remarks'].map(async (column) => ({
        header: await tableHead.locator(`.${column}`).evaluate((node) => Number.parseFloat(getComputedStyle(node).borderInlineStartWidth)),
        row: await firstRow.locator(`.${column}`).evaluate((node) => Number.parseFloat(getComputedStyle(node).borderInlineStartWidth)),
      }))),
    ])
    expect(headerTemplate).toBe(rowTemplate)
    expect(asymmetricGuides).toEqual([{ header: 1, row: 0 }, { header: 1, row: 0 }])
    const divider = await page.locator('.db-parts-workbench__ledger-workspace').evaluate((node) => Number.parseFloat(getComputedStyle(node).borderInlineEndWidth))
    expect(divider).toBeGreaterThanOrEqual(1)
  }
}

async function expectAvailableDividerState(page: Page, present: boolean) {
  const availableHead = page.getByRole('columnheader', { name: 'Available', exact: true })
  const availableCell = page.locator('.db-parts-workbench__row').first().locator('.is-available')
  const [headWidth, cellWidth, headBox, cellBox] = await Promise.all([
    availableHead.evaluate((node) => Number.parseFloat(getComputedStyle(node).borderInlineStartWidth)),
    availableCell.evaluate((node) => Number.parseFloat(getComputedStyle(node).borderInlineStartWidth)),
    availableHead.boundingBox(),
    availableCell.boundingBox(),
  ])
  expect(headWidth).toBe(present ? 1 : 0)
  expect(cellWidth).toBe(present ? 1 : 0)
  expect(headBox).not.toBeNull()
  expect(cellBox).not.toBeNull()
  expect(Math.abs(headBox!.x - cellBox!.x)).toBeLessThanOrEqual(1)

  for (const column of ['is-bin', 'is-cost', 'is-supplier', 'is-remarks']) {
    const [headerDivider, rowDivider] = await Promise.all([
      page.locator(`.db-parts-workbench__table-head > .${column}`).evaluate((node) => Number.parseFloat(getComputedStyle(node).borderInlineStartWidth)),
      page.locator(`.db-parts-workbench__row`).first().locator(`.${column}`).evaluate((node) => Number.parseFloat(getComputedStyle(node).borderInlineStartWidth)),
    ])
    expect(headerDivider).toBeGreaterThanOrEqual(1)
    if (column === 'is-cost' || column === 'is-remarks') expect(rowDivider).toBe(0)
    else expect(rowDivider).toBeGreaterThanOrEqual(1)
  }
}

async function expectResponsiveAvailableDivider(page: Page) {
  const ledgerWorkspace = page.locator('.db-parts-workbench__ledger-workspace')
  const threshold = await page.evaluate(() => Number.parseFloat(getComputedStyle(document.documentElement).fontSize) * 50)

  await page.setViewportSize({ width: 1920, height: 900 })
  await expect.poll(() => ledgerWorkspace.evaluate((node) => node.clientWidth)).toBeGreaterThan(threshold)
  await expectAvailableDividerState(page, false)
  await expectPriorityLedgerColumnsContained(page, 1920)
  expect(await page.locator('body').evaluate((node) => node.scrollWidth <= window.innerWidth)).toBe(true)

  await page.setViewportSize({ width: 1280, height: 900 })
  await expect.poll(() => ledgerWorkspace.evaluate((node) => node.clientWidth)).toBeLessThanOrEqual(threshold)
  await expectAvailableDividerState(page, true)
  await expectPriorityLedgerColumnsContained(page, 1280)
  expect(await page.locator('body').evaluate((node) => node.scrollWidth <= window.innerWidth)).toBe(true)
}

async function expectPriorityLedgerColumnsContained(page: Page, width: number) {
  if (width <= 760) return
  const ledger = page.locator('.db-parts-workbench__ledger')
  const tableHead = page.locator('.db-parts-workbench__table-head')
  const headBox = await tableHead.boundingBox()
  const headScrollWidth = await tableHead.evaluate((node) => node.scrollWidth)
  expect(headBox).not.toBeNull()
  const visibleLabels = ['Description', 'Available', 'Bin location', 'Average cost', 'Preferred supplier', 'Remarks'] as const
  const boxes = []
  for (const label of visibleLabels) {
    const header = page.getByRole('columnheader', { name: label, exact: true })
    const box = await header.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.x).toBeGreaterThanOrEqual(headBox!.x - 1)
    expect(box!.x + box!.width).toBeLessThanOrEqual(headBox!.x + headScrollWidth + 1)
    expect(await header.evaluate((node) => {
      const style = getComputedStyle(node)
      return {
        contained: node.scrollWidth <= node.clientWidth + 1 && node.scrollHeight <= node.clientHeight + 1,
        overflowWrap: style.overflowWrap,
        whiteSpace: style.whiteSpace,
        wordBreak: style.wordBreak,
      }
    }), `${label} header must remain single-line and unclipped`).toEqual({ contained: true, overflowWrap: 'normal', whiteSpace: 'nowrap', wordBreak: 'normal' })
    boxes.push(box!)
  }
  for (let index = 1; index < boxes.length; index += 1) {
    expect(boxes[index - 1].x + boxes[index - 1].width).toBeLessThanOrEqual(boxes[index].x + 1)
  }
  for (const label of ['Needed', 'Reorder', 'Incoming']) {
    await expect(page.getByRole('columnheader', { name: label, exact: true })).toHaveCount(0)
  }

  expect(await tableHead.getByRole('columnheader').evaluateAll((nodes) => nodes.map((node) => node.getAttribute('aria-label') || node.textContent?.trim()))).toEqual([
    'Select part',
    'Description',
    'Available',
    'Bin location',
    'Average cost',
    'Preferred supplier',
    'Remarks',
  ])

  const [headerTemplate, rowTemplate] = await Promise.all([
    tableHead.evaluate((node) => getComputedStyle(node).gridTemplateColumns),
    page.locator('.db-parts-workbench__row').first().evaluate((node) => getComputedStyle(node).gridTemplateColumns),
  ])
  expect(headerTemplate).toBe(rowTemplate)
  expect(headerTemplate.trim().split(/\s+/)).toHaveLength(7)

  const [descriptionTextX, identityTextX] = await Promise.all([
    page.getByRole('columnheader', { name: 'Description', exact: true }).evaluate((node) => {
      const range = document.createRange()
      range.selectNodeContents(node)
      return range.getBoundingClientRect().x
    }),
    page.locator('.db-parts-workbench__row').first().locator('.db-parts-workbench__identity strong').evaluate((node) => node.getBoundingClientRect().x),
  ])
  expect(Math.abs(descriptionTextX - identityTextX)).toBeLessThanOrEqual(2)
}

async function expectLedgerControlOwnership(page: Page, width: number) {
  const toolbar = page.locator('.db-parts-workbench__toolbar')
  const ledgerWorkspace = page.locator('.db-parts-workbench__ledger-workspace')
  await expect(toolbar).toBeVisible()
  if (width > 760) {
    const [toolbarBox, ledgerBox, inspectorBox, searchBox] = await Promise.all([
      toolbar.boundingBox(),
      ledgerWorkspace.boundingBox(),
      page.locator('.db-parts-workbench__inspector').boundingBox(),
      page.getByRole('searchbox', { name: 'Search parts' }).locator('..').boundingBox(),
    ])
    expect(toolbarBox).not.toBeNull()
    expect(ledgerBox).not.toBeNull()
    expect(inspectorBox).not.toBeNull()
    expect(searchBox).not.toBeNull()
    expect(toolbarBox!.x).toBeGreaterThanOrEqual(ledgerBox!.x - 1)
    expect(toolbarBox!.x + toolbarBox!.width).toBeLessThanOrEqual(ledgerBox!.x + ledgerBox!.width + 1)
    expect(toolbarBox!.x + toolbarBox!.width).toBeLessThanOrEqual(inspectorBox!.x + 1)
    expect(searchBox!.width).toBeLessThanOrEqual(338)
  }
  await expect(page.getByRole('dialog', { name: 'Ledger options' })).toBeHidden()
  const options = page.getByRole('button', { name: 'Ledger options' })
  await expect(options).toHaveAttribute('aria-expanded', 'false')
  await expect(options).toHaveAttribute('aria-controls', 'parts-ledger-options-popover')
  await options.focus()
  await options.press('Enter')
  await expect(page.getByRole('dialog', { name: 'Ledger options' })).toBeVisible()
  const sortTrigger = page.getByRole('button', { name: /^Sort / })
  await expect(sortTrigger).toBeFocused()
  await expect(page.locator('.db-parts-workbench__options-popover select')).toHaveCount(0)
  const density = page.getByRole('group', { name: 'Density' })
  await expect(density).toBeVisible()
  const optionRows = page.locator('.db-parts-workbench__options-row')
  const [sortLabelBox, densityLabelBox, sortControlBox, densityControlBox] = await Promise.all([
    optionRows.nth(0).locator(':scope > span').boundingBox(),
    optionRows.nth(1).locator(':scope > span').boundingBox(),
    sortTrigger.boundingBox(),
    density.boundingBox(),
  ])
  expect(sortLabelBox).not.toBeNull()
  expect(densityLabelBox).not.toBeNull()
  expect(sortControlBox).not.toBeNull()
  expect(densityControlBox).not.toBeNull()
  expect(Math.abs(sortLabelBox!.x - densityLabelBox!.x)).toBeLessThanOrEqual(1)
  expect(Math.abs(sortControlBox!.x - densityControlBox!.x)).toBeLessThanOrEqual(1)
  expect(Math.abs(sortControlBox!.width - densityControlBox!.width)).toBeLessThanOrEqual(1)
  expect(sortControlBox!.height).toBeGreaterThanOrEqual(44)
  expect(densityControlBox!.height).toBeGreaterThanOrEqual(44)
  const keyboardFocus = await sortTrigger.evaluate((node) => {
    const style = getComputedStyle(node)
    return { visible: node.matches(':focus-visible'), outline: style.outlineStyle, shadow: style.boxShadow }
  })
  expect(keyboardFocus.visible).toBe(true)
  expect(keyboardFocus.outline === 'none' || keyboardFocus.outline === 'solid').toBe(true)
  expect(keyboardFocus.outline === 'solid' || keyboardFocus.shadow.includes('inset')).toBe(true)
  await sortTrigger.press('Enter')
  await expect(page.getByRole('listbox', { name: 'Sort' })).toBeVisible()
  await expect(page.getByRole('option', { name: 'Catalog order' })).toBeFocused()
  await page.keyboard.press('End')
  await expect(page.getByRole('option', { name: 'Reorder urgency' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog', { name: 'Ledger options' })).toBeHidden()
  await expect(options).toBeFocused()
  await options.click()
  await expect(page.getByRole('dialog', { name: 'Ledger options' })).toBeVisible()
  await page.getByRole('heading', { name: 'Parts', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Ledger options' })).toBeHidden()
}

type InventoryUpdate = { id: string; body: Record<string, unknown> }
type InventoryCreate = Record<string, unknown>
type PurchaseBatch = { body: Record<string, unknown>; idempotencyKey: string | null }

async function installFixture(page: Page, {
  tenantLogoUrl = '/db038-tenant-logo.svg',
  readOnly = false,
  appearanceMode = 'dark',
  inventoryUpdateStatus = 200,
  inventoryUpdates = [],
  inventoryCreates = [],
  purchaseBatches = [],
}: {
  tenantLogoUrl?: string
  readOnly?: boolean
  appearanceMode?: 'light' | 'dark' | 'high_contrast'
  inventoryUpdateStatus?: number
  inventoryUpdates?: InventoryUpdate[]
  inventoryCreates?: InventoryCreate[]
  purchaseBatches?: PurchaseBatch[]
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
    if (url.pathname.endsWith('/parts-operations/summary')) return json({ needs_reorder_count: 2, low_stock_count: 695, open_purchase_order_count: 4 })
    if (url.pathname.endsWith('/parts-operations/demand')) return json({ items: demandItems, total: demandItems.length, skip: 0, limit: 100, has_more: false })
    if (url.pathname.endsWith('/suppliers') && route.request().method() === 'GET') return json({ items: [{ id: 'supplier-secondary', name: 'AutoZone' }], total: 1, skip: 0, limit: 100, has_more: false })
    if (/\/parts-operations\/suppliers\/[^/]+\/purchasing$/.test(url.pathname)) return json({ id: fixture.ids.supplier, name: 'Fleet Parts Co', payment_terms: 'NET 30', default_lead_time_days: 7, minimum_order_amount: null, purchasing_notes: null, active_part_source_count: 98, open_purchase_order_count: 1, open_purchase_order_value: '60.00', last_receipt_at: fixture.frozen_at, on_time_order_count: 9, timed_order_count: 10, on_time_rate: '90' })
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
      if (attention === 'out_of_stock') items = items.filter((item) => !item.is_placeholder && item.available_packages === 0)
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
    if (url.pathname.endsWith('/inventory') && route.request().method() === 'POST') {
      const body = route.request().postDataJSON() as InventoryCreate
      inventoryCreates.push(body)
      return json({ ...fixture.inventory[0], id: `inventory-created-${inventoryCreates.length}`, ...body })
    }
    if (url.pathname.endsWith('/parts-operations/purchase-orders/batch') && route.request().method() === 'POST') {
      purchaseBatches.push({ body: route.request().postDataJSON() as Record<string, unknown>, idempotencyKey: route.request().headers()['idempotency-key'] || null })
      return json({ count: 1, purchase_orders: [{ id: 'po-created', po_number: 'PO-DB038-NEW' }] })
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
    const appearanceMode = width === 960 ? 'light' : width === 320 ? 'high_contrast' : 'dark'
    const inventoryCreates: InventoryCreate[] = []
    const purchaseBatches: PurchaseBatch[] = []
    const fixtureRuntime = await installFixture(page, { appearanceMode, inventoryCreates, purchaseBatches })
    await page.goto('/dashboard/garage/inventory')
    await expect(page.getByRole('heading', { name: 'Parts' })).toBeVisible()
    await expectIntegratedSearch(page.getByRole('searchbox', { name: 'Search parts' }))
    await expect(page.getByRole('list', { name: 'Parts operations workflow' })).toHaveCount(0)
    const workspaceViews = page.getByRole('navigation', { name: 'Parts and inventory views' })
    await expect(workspaceViews.locator('button[aria-current="page"]')).toHaveCount(1)
    await expect(workspaceViews.getByRole('button', { name: /^All parts\b/ })).toHaveAttribute('aria-current', 'page')
    await expect(workspaceViews.getByRole('button', { name: /^Needs reorder 2$/ })).toBeVisible()
    await expect(page.locator('.db-parts-workbench__header .db-parts-workbench__technical-line')).toContainText('2 NEEDS REORDER')
    await expect(page.getByText('695', { exact: true })).toHaveCount(0)
    for (const label of ['All parts', 'Needs reorder', 'Movement']) {
      await expect(workspaceViews.getByRole('button', { name: new RegExp(`^${label}\\b`) })).toHaveCSS('min-height', '48px')
    }
    await expect(page.locator('.db-parts-workbench__ledger[aria-label="99 matching parts"]')).toBeVisible()
    const partRows = page.locator('.db-parts-workbench__row')
    const partButtons = page.locator('.db-parts-workbench__row-select')
    await expect(partRows).toHaveCount(50)
    await expect(page.getByText('Showing 50 of 99')).toBeVisible()
    await expectLedgerLineTreatment(page, width)
    await expectLedgerControlOwnership(page, width)
    await expectPriorityLedgerColumnsContained(page, width)
    if (width === 1280) await expectResponsiveAvailableDivider(page)
    if (width === 1280) {
      await page.emulateMedia({ forcedColors: 'none' })
      const ledger = page.locator('.db-parts-workbench__ledger')
      await ledger.evaluate((node) => { node.scrollLeft = Math.min(280, node.scrollWidth - node.clientWidth) })
      await page.screenshot({ path: testInfo.outputPath('db038-ledger-guide-bin-cost-1280.png'), fullPage: false })
      await ledger.evaluate((node) => { node.scrollLeft = node.scrollWidth })
      await page.screenshot({ path: testInfo.outputPath('db038-ledger-guide-supplier-remarks-1280.png'), fullPage: false })
      await ledger.evaluate((node) => { node.scrollLeft = 0 })
      await page.getByRole('button', { name: 'Ledger options' }).click()
      await page.screenshot({ path: testInfo.outputPath('db038-ledger-options-1280.png'), fullPage: false })
      await page.getByRole('button', { name: /^Sort / }).click()
      await page.screenshot({ path: testInfo.outputPath('db038-ledger-sort-options-1280.png'), fullPage: false })
      await page.keyboard.press('Escape')
      await page.emulateMedia({ forcedColors: 'active' })
    }
    if (width === 1280 || width === 390) {
      await expectNaturalLoadMoreFlow(page)
      await page.screenshot({ path: testInfo.outputPath(`db038-load-more-natural-${width}.png`), fullPage: false })
      await page.locator('.db-parts-workbench__ledger').evaluate((node) => { node.scrollTop = 0 })
    }
    await expect(page.getByRole('columnheader', { name: 'No', exact: true })).toHaveCount(0)
    await expect(page.locator('.db-parts-workbench__line-number')).toHaveCount(0)
    if (width <= 760) await expectCompactLedgerHitTargets(page)
    await expectSingleWorkbenchSelection(page, partButtons.first())
    await expect(partRows.first().locator('img[src$="/db038-part-image.svg"]')).toBeVisible()
    for (const label of ['Description', 'Available', 'Bin location', 'Average cost', 'Preferred supplier', 'Remarks']) {
      const header = page.getByRole('columnheader', { name: label, exact: true })
      if (width > 760) await expect(header).toHaveCount(1)
      else await expect(header).toBeHidden()
    }
    await expect(page.getByRole('columnheader', { name: /Needed|Reorder|Incoming|Free|Committed/i })).toHaveCount(0)
    await expect(partRows.first().locator('[data-label="Available"]')).toBeVisible()
    await expect(partRows.first().locator('[data-label="Bin location"]')).toHaveText('Bin A-01')
    await expect(partRows.first().locator('[data-label="Bin location"]')).toBeVisible()
    const stockFilters = page.getByRole('group', { name: 'Stock filter' })
    const secondCheckbox = page.getByRole('checkbox', { name: 'Select Brake shoe for purchase preparation' })
    await secondCheckbox.check()
    await expect(secondCheckbox).toBeChecked()
    await expectSingleWorkbenchSelection(page, partButtons.first())
    await secondCheckbox.uncheck()
    const nonReorderCheckbox = page.getByRole('checkbox', { name: 'Select Coolant for purchase preparation' })
    await nonReorderCheckbox.check()
    await expect(nonReorderCheckbox).toBeChecked()
    await expectSingleWorkbenchSelection(page, partButtons.first())
    await nonReorderCheckbox.uncheck()
    if (width === 1280) {
      const retainedCheckbox = page.getByRole('checkbox', { name: 'Select Air filter for purchase preparation' })
      await retainedCheckbox.check()
      for (const sortName of ['Name', 'Available', 'Reorder urgency', 'Catalog order']) {
        const options = page.getByRole('button', { name: 'Ledger options' })
        await options.click()
        const sortTrigger = page.getByRole('button', { name: /^Sort / })
        await sortTrigger.click()
        const sortOption = page.getByRole('option', { name: sortName })
        await sortOption.click()
        await expect(page.getByRole('dialog', { name: 'Ledger options' })).toBeHidden()
        await expect(options).toBeFocused()
        await expect(page.getByText('1 part selected')).toBeVisible()
        await expect(page.getByRole('button', { name: /^All parts/ })).toHaveAttribute('aria-current', 'page')
        await expect(stockFilters.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'true')
        await expect(page.getByRole('checkbox', { name: 'Select Air filter for purchase preparation' })).toBeChecked()
        expect(await page.getByRole('checkbox', { name: /purchase preparation/ }).count()).toBeGreaterThan(0)
      }
      await retainedCheckbox.uncheck()
    }
    const options = page.getByRole('button', { name: 'Ledger options' })
    await options.click()
    await page.getByRole('button', { name: 'Compact' }).click()
    await expect(page.getByRole('dialog', { name: 'Ledger options' })).toBeHidden()
    await expect(page.locator('.db-parts-workbench__ledger')).toHaveClass(/is-compact/)
    await options.click()
    await page.getByRole('button', { name: 'Comfortable' }).click()
    await expect(page.getByRole('dialog', { name: 'Ledger options' })).toBeHidden()
    await stockFilters.getByRole('button', { name: 'Needs reorder' }).click()
    await expect(page.locator('.db-parts-workbench__ledger[aria-label="2 matching parts"]')).toBeVisible()
    await stockFilters.getByRole('button', { name: 'Out of stock' }).click()
    await expect(page.locator('.db-parts-workbench__ledger[aria-label="1 matching parts"]')).toBeVisible()
    await stockFilters.getByRole('button', { name: 'All' }).click()
    await expect(page.locator('.db-parts-workbench__ledger[aria-label="99 matching parts"]')).toBeVisible()

    if (width === 1280) {
      await page.getByRole('button', { name: 'Add Part' }).click()
      const addPart = page.getByRole('dialog', { name: /Add part/i })
      await expect(addPart.getByLabel(/Part name/)).toHaveAttribute('required', '')
      await expect(addPart.getByLabel(/SKU/)).toHaveAttribute('required', '')
      await addPart.getByLabel(/Part name/).fill('Air dryer cartridge')
      await addPart.getByLabel(/SKU/).fill('AIR-DRY-01')
      await addPart.getByRole('button', { name: 'Add Part' }).click()
      await expect.poll(() => inventoryCreates.length).toBe(1)
      expect(inventoryCreates[0]).toMatchObject({ name: 'Air dryer cartridge', sku: 'AIR-DRY-01', stock_quantity: 0, reorder_level: 0, unit_type: 'each' })
    }

    if (width === 960) {
      await expectRuntimeIdentityGeometry(page, width)
      await page.screenshot({ path: testInfo.outputPath('db038-runtime-identity-960-forced-colors.png'), fullPage: false })
    }
    await page.screenshot({ path: testInfo.outputPath(`db038-first-selection-${width}.png`), fullPage: false })
    await partButtons.first().click()
    const partPhoto = page.getByRole('img', { name: 'Air filter part photo' })
    await expect(partPhoto).toBeVisible()
    await expectSelectedPartImage(partPhoto, width)
    await page.emulateMedia({ forcedColors: 'none' })
    await expectRuntimeIdentityGeometry(page, width)
    if (width === 960) {
      await page.screenshot({ path: testInfo.outputPath('db038-runtime-identity-960-light.png'), fullPage: false })
    }
    await page.screenshot({ path: testInfo.outputPath(`db038-service-manual-${width}.png`), fullPage: false })
    await expectServiceManualHierarchy(page, width)
    await expectSupplierRelationshipHierarchy(page)
    if (width === 1280 || width === 390) {
      const suppliedBy = page.locator('.db-parts-workbench__supplier-section')
      await suppliedBy.scrollIntoViewIfNeeded()
      await page.screenshot({ path: testInfo.outputPath(`db038-supplied-by-${width}.png`), fullPage: false })
      if (width <= 760) await page.evaluate(() => window.scrollTo(0, 0))
      else await page.locator('.db-parts-workbench__inspector').evaluate((node) => { node.scrollTop = 0 })
    }
    await expectSupplierSourceInteraction(page, width, testInfo)
    await page.emulateMedia({ forcedColors: 'active' })
    await expectStockFactsFullyVisible(page)
    if (width <= 760) await page.getByRole('button', { name: 'Back to parts' }).click()
    await expect(partRows.nth(1).locator('img[src$="/db038-tenant-logo.svg"]')).toBeVisible()
    await partButtons.nth(1).click()
    const logoPlaceholder = page.getByRole('img', { name: 'Truck Pit Stop Wisconsin logo placeholder for Brake shoe' })
    await expect(logoPlaceholder).toBeVisible()
    await expectSelectedPartImage(logoPlaceholder, width)
    expect([...fixtureRuntime.expectedImageFailureResponses].some(url => new URL(url).pathname === '/db038-broken-image.svg')).toBe(true)
    if (width === 390) await page.screenshot({ path: testInfo.outputPath('db038-all-parts-mobile-390.png'), fullPage: false })
    if (width <= 760) await page.getByRole('button', { name: 'Back to parts' }).click()

    await page.getByRole('button', { name: 'Archived parts' }).click()
    await expect(page.locator('.db-parts-workbench__ledger[aria-label="1 matching parts"]')).toBeVisible()
    await expect(page.getByRole('checkbox', { name: /purchase preparation/ })).toHaveCount(0)
    await page.locator('.db-parts-workbench__row-select').first().click()
    await expect(page.getByRole('status')).toContainText('Archived part')
    await expect(page.getByRole('button', { name: 'Adjust on-hand quantity' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Add to purchase list' })).toHaveCount(0)
    await page.getByRole('tab', { name: 'Stock' }).click()
    await expect(page.getByRole('button', { name: 'Edit available quantity' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Edit reorder point' })).toHaveCount(0)
    await page.getByRole('tab', { name: 'Ordering' }).click()
    await expect(page.getByRole('button', { name: /supplier source/i })).toHaveCount(0)
    await expect(page.getByText('Edit source', { exact: true })).toHaveCount(0)
    if (width <= 760) await page.getByRole('button', { name: 'Back to parts' }).click()

    await workspaceViews.getByRole('button', { name: /^Movement\b/ }).click()
    await expect(workspaceViews.locator('button[aria-current="page"]')).toHaveCount(1)
    await expect(workspaceViews.getByRole('button', { name: /^Movement\b/ })).toHaveAttribute('aria-current', 'page')
    await expect(page.getByText(/Reserved for a repair · 0 on hand after change/)).toBeVisible()
    await expect(page.getByRole('button', { name: 'TPS-000301' })).toBeVisible()

    await workspaceViews.getByRole('button', { name: /^Needs reorder\b/ }).click()
    await expect(workspaceViews.locator('button[aria-current="page"]')).toHaveCount(1)
    await expect(workspaceViews.getByRole('button', { name: /^Needs reorder 2$/ })).toHaveAttribute('aria-current', 'page')
    await expect(page.locator('.db-parts-workbench__header .db-parts-workbench__technical-line')).toContainText('2 NEEDS REORDER')
    await expect(page.locator('.db-parts-workbench__ledger[aria-label="2 matching parts"]')).toBeVisible()
    await expect(page.locator('.db-parts-workbench__row')).toHaveCount(2)
    await expectSingleWorkbenchSelection(page, page.locator('.db-parts-workbench__row-select').first())
    const reorderCheckboxes = page.getByRole('checkbox', { name: /purchase preparation/ })
    await expect(reorderCheckboxes).toHaveCount(2)
    for (const checkbox of await reorderCheckboxes.all()) await expect(checkbox).toBeChecked()
    const bulkActions = page.getByRole('region', { name: 'Selected parts actions' })
    await expect(bulkActions).toContainText('2 parts selected')
    if (width === 1280) {
      const options = page.getByRole('button', { name: 'Ledger options' })
      await options.click()
      await page.getByRole('button', { name: /^Sort / }).click()
      await page.getByRole('option', { name: 'Name' }).click()
      await expect(bulkActions).toContainText('2 parts selected')
      await expect(reorderCheckboxes).toHaveCount(2)
      for (const checkbox of await reorderCheckboxes.all()) await expect(checkbox).toBeChecked()
      await expect(workspaceViews.getByRole('button', { name: /^Needs reorder 2$/ })).toHaveAttribute('aria-current', 'page')
    }
    await bulkActions.getByRole('button', { name: /Add to purchase list/ }).click()
    await expect(page).toHaveURL(/\/dashboard\/garage\/purchasing/)
    await expect(page.getByRole('heading', { name: 'Purchasing' })).toBeVisible()
    const purchasingAreas = page.getByRole('navigation', { name: 'Purchasing areas' })
    await expect(purchasingAreas.locator('button[aria-current="page"]')).toHaveCount(1)
    await expect(purchasingAreas.getByRole('button', { name: /Purchase orders/ })).toHaveAttribute('aria-current', 'page')
    await expect(page.getByRole('heading', { name: 'Fleet Parts Co' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Supplier required' })).toBeVisible()
    await expect(page.getByText('Excluded from this batch')).toBeVisible()
    await expectPurchasingQuantityStepper(page, appearanceMode)
    if (width === 1280 || width === 390) await page.screenshot({ path: testInfo.outputPath(`db038-purchase-quantity-${width}.png`), fullPage: false })
    await expect(page.getByRole('button', { name: 'Create 1 draft order' })).toBeEnabled()
    await page.getByRole('button', { name: 'Create 1 draft order' }).click()
    await expect.poll(() => purchaseBatches.length).toBe(1)
    expect(JSON.stringify(purchaseBatches[0].body)).toContain('inventory-1')
    expect(JSON.stringify(purchaseBatches[0].body)).not.toContain('inventory-2')
    expect(JSON.stringify(purchaseBatches[0].body)).toContain('"ordered_quantity":4')
    expect(purchaseBatches[0].idempotencyKey).toMatch(/^po-batch-/)
    await expect(page.getByRole('status', { name: 'Purchase preparation result' })).toContainText('1 blocked part remains in preparation')
    if (width === 1280 || width === 390) await page.screenshot({ path: testInfo.outputPath(`db038-purchase-preparation-${width}.png`), fullPage: false })
    expect(await page.locator('.db-parts-operations').innerText()).not.toMatch(/\b(?:packages|pkg)\b/i)
    expect(await page.locator('body').evaluate(node => node.scrollWidth <= window.innerWidth)).toBe(true)
    expect(errors.get(page)).toEqual([])
    await context.close()
  }
})

test('DB-038 preserves photo fallbacks, incremental loading, and repair, PO, and receipt provenance', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 900 })
  const fixtureRuntime = await installFixture(page, { tenantLogoUrl: '/db038-broken-logo.svg' })
  await page.goto('/dashboard/garage/inventory')
  const ledger = page.locator('.db-parts-workbench__ledger[aria-label="99 matching parts"]')
  await expect(ledger).toBeVisible()
  await expectIntegratedSearch(page.getByRole('searchbox', { name: 'Search parts' }))
  const partRows = page.locator('.db-parts-workbench__row')
  const partButtons = page.locator('.db-parts-workbench__row-select')
  await expect(partRows).toHaveCount(50)
  await expect(page.getByText('Showing 50 of 99')).toBeVisible()
  await expectNaturalLoadMoreFlow(page)
  await page.getByRole('button', { name: 'Load 50 more' }).click()
  await expect(partRows).toHaveCount(99)
  await expect(page.getByText('Showing 99 of 99')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Load 50 more' })).toHaveCount(0)
  await expectNaturalLoadMoreFlow(page)
  await ledger.evaluate((node) => { node.scrollTop = 0 })
  const partsSearch = page.getByRole('searchbox', { name: 'Search parts' })
  await partsSearch.fill('Fleet filter 99')
  await expect(page.locator('.db-parts-workbench__ledger[aria-label="1 matching parts"]')).toBeVisible()
  await expect(page.getByText('Showing 1 of 1')).toBeVisible()
  await partsSearch.fill('')
  await expect(partRows).toHaveCount(50)
  await expect(page.getByText('Showing 50 of 99')).toBeVisible()
  expect(await ledger.evaluate(node => getComputedStyle(node).overflowY)).toMatch(/auto|scroll/)
  expect(await ledger.evaluate(node => node.scrollHeight > node.clientHeight)).toBe(true)
  await expect(partRows.nth(1).locator('.db-parts-workbench__photo svg')).toBeVisible()
  await expect(partRows.nth(2).locator('.db-parts-workbench__photo svg')).toBeVisible()
  await partButtons.nth(1).click()
  await expect(page.getByRole('img', { name: 'No image available for Brake shoe' })).toBeVisible()
  await partButtons.nth(2).click()
  await expect(page.getByRole('img', { name: 'No image available for Coolant' })).toBeVisible()
  expect([...fixtureRuntime.expectedImageFailureResponses].some(url => new URL(url).pathname === '/db038-broken-image.svg')).toBe(true)
  expect([...fixtureRuntime.expectedImageFailureResponses].some(url => new URL(url).pathname === '/db038-broken-logo.svg')).toBe(true)

  await partButtons.first().click()
  await expect(page.getByRole('button', { name: /TPS-000301.*2 units needed/i })).toBeVisible()
  await page.getByRole('tab', { name: 'Ordering' }).click()
  await expect(page.getByRole('button', { name: /PO-DB038-001.*1 units incoming/i })).toBeVisible()
  await expect(page.getByRole('button', { name: /RCV-DB038-001.*1 at \$20\.00/i })).toBeVisible()
  await page.getByRole('button', { name: /PO-DB038-001.*1 units incoming/i }).click()
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
    await expectToolbarOptionsContrast(page, appearanceMode)
    if (width === 1280) await page.screenshot({ path: testInfo.outputPath('db038-toolbar-dark-1280.png'), fullPage: false })
    const rows = page.locator('.db-parts-workbench__row-select')
    await expectSingleWorkbenchSelection(page, rows.first())
    if (width <= 760) await expectCompactLedgerHitTargets(page)
    await rows.first().click()
    const workbench = page.locator('.db-parts-workbench')
    const containment = await workbench.evaluate((node) => ({
      clientWidth: node.clientWidth,
      scrollWidth: node.scrollWidth,
      scrollLeft: node.scrollLeft,
    }))
    expect(containment.scrollWidth).toBeLessThanOrEqual(containment.clientWidth + 1)
    expect(containment.scrollLeft).toBe(0)
    if (width <= 760) {
      expect(await page.locator('.db-parts-workbench__ledger').evaluate((node) => node.scrollLeft)).toBe(0)
    }
    if (width === 1280) {
      for (const region of [page.locator('.db-parts-workbench__toolbar'), page.locator('.db-parts-workbench__body'), page.locator('.db-parts-workbench__inspector')]) {
        const [ownerBox, regionBox] = await Promise.all([workbench.boundingBox(), region.boundingBox()])
        expect(ownerBox).not.toBeNull()
        expect(regionBox).not.toBeNull()
        expect(regionBox!.x).toBeGreaterThanOrEqual(ownerBox!.x - 1)
        expect(regionBox!.x + regionBox!.width).toBeLessThanOrEqual(ownerBox!.x + ownerBox!.width + 1)
      }
    }
    const selectedHeader = page.locator('.db-parts-workbench__selected-action')
    await expect(selectedHeader).toContainText('DB-INVENTORY-001 · Bin A-01 · No unit specified')
    await expect(selectedHeader).not.toContainText('undefined')
    await page.getByRole('tab', { name: 'Stock' }).click()
    await expectStockFactRules(page)
    const stockPanel = page.getByRole('tabpanel', { name: 'Stock' })
    await expect(stockPanel.locator('.db-parts-workbench__actions')).toHaveCount(0)
    await expect(stockPanel.getByText('Adjust available', { exact: true })).toHaveCount(0)
    await expect(stockPanel.getByText('Change reorder point', { exact: true })).toHaveCount(0)
    const availableFactTrigger = stockPanel.getByRole('button', { name: 'Edit available quantity' })
    const reorderFactTrigger = stockPanel.getByRole('button', { name: 'Edit reorder point' })
    for (const factTrigger of [availableFactTrigger, reorderFactTrigger]) {
      await expect(factTrigger).toBeVisible()
      const factTriggerBox = await factTrigger.boundingBox()
      expect(factTriggerBox).not.toBeNull()
      expect(factTriggerBox!.width).toBeGreaterThanOrEqual(44)
      expect(factTriggerBox!.height).toBeGreaterThanOrEqual(44)
    }
    if (width === 1280) {
      await availableFactTrigger.hover()
      const factTooltip = stockPanel.getByRole('tooltip', { name: 'Edit available quantity' })
      await expect(factTooltip).toBeVisible()
      const [tooltipBox, inspectorBox] = await Promise.all([
        factTooltip.boundingBox(),
        page.locator('.db-parts-workbench__inspector').boundingBox(),
      ])
      expect(tooltipBox).not.toBeNull()
      expect(inspectorBox).not.toBeNull()
      expect(tooltipBox!.x).toBeGreaterThanOrEqual(inspectorBox!.x - 1)
      expect(tooltipBox!.x + tooltipBox!.width).toBeLessThanOrEqual(inspectorBox!.x + inspectorBox!.width + 1)
    }
    if (width === 1280 || width === 390) await page.screenshot({ path: testInfo.outputPath(`db038-stock-tab-${width}.png`), fullPage: false })
    const edit = width === 1280
      ? availableFactTrigger
      : page.getByRole('button', { name: 'Adjust on-hand quantity' })
    await expect(edit).toBeVisible()
    expect((await edit.boundingBox())!.height).toBeGreaterThanOrEqual(44)
    await edit.click()
    const controls = stockPanel
    const availableEditor = controls.getByRole('form', { name: 'Edit available quantity' })
    await expect(availableEditor).toHaveCount(1)
    await expect(controls.getByRole('form')).toHaveCount(1)
    await expect(stockPanel.getByRole('tooltip')).toHaveCount(0)
    const activeFact = availableEditor.locator('xpath=ancestor::*[contains(concat(" ", normalize-space(@class), " "), " db-parts-workbench__fact ")][1]')
    await expect(activeFact).toContainText('Available')
    await expect(activeFact).toHaveClass(/is-editing/)
    await expect(availableEditor.getByText('Cancel', { exact: true })).toHaveCount(0)
    await expect(availableEditor.getByText('Save change', { exact: true })).toHaveCount(0)
    const cancelAvailable = availableEditor.getByRole('button', { name: 'Cancel available quantity edit' })
    const cancelTooltip = availableEditor.locator('.db-parts-workbench__edit-cancel .db-parts-workbench__fact-tooltip')
    const saveButton = availableEditor.getByRole('button', { name: 'Save' })
    await expect(cancelAvailable).toBeVisible()
    await expect(cancelTooltip).toBeHidden()
    await expect(saveButton).toHaveCount(1)
    const [factsBox, activeFactBox, cancelBox, saveBox] = await Promise.all([
      stockPanel.locator('.db-parts-workbench__facts').boundingBox(),
      activeFact.boundingBox(),
      cancelAvailable.boundingBox(),
      saveButton.boundingBox(),
    ])
    for (const box of [factsBox, activeFactBox, cancelBox, saveBox]) expect(box).not.toBeNull()
    expect(activeFactBox!.x).toBeCloseTo(factsBox!.x, 0)
    expect(activeFactBox!.width).toBeCloseTo(factsBox!.width, 0)
    expect(cancelBox!.width).toBeGreaterThanOrEqual(44)
    expect(cancelBox!.height).toBeGreaterThanOrEqual(44)
    expect(cancelBox!.x + cancelBox!.width).toBeLessThanOrEqual(activeFactBox!.x + activeFactBox!.width + 1)
    expect(cancelBox!.y + cancelBox!.height).toBeLessThanOrEqual(saveBox!.y + 1)
    const derivedFactGeometry = await stockPanel.locator('.db-parts-workbench__facts').evaluate((node) => {
      const active = node.querySelector<HTMLElement>('.db-parts-workbench__fact.is-editing')!
      const activeBox = active.getBoundingClientRect()
      return ['Needed for open repairs', 'Incoming'].map((label) => {
        const term = [...node.querySelectorAll<HTMLElement>('dt')].find((candidate) => candidate.textContent === label)!
        const box = term.closest('div')!.getBoundingClientRect()
        return { label, top: box.top, activeBottom: activeBox.bottom }
      })
    })
    for (const fact of derivedFactGeometry) expect(fact.top).toBeGreaterThanOrEqual(fact.activeBottom - 1)
    const savePresentation = await saveButton.evaluate((node) => {
      const style = getComputedStyle(node)
      return { whiteSpace: style.whiteSpace, fits: node.scrollWidth <= node.clientWidth + 1 }
    })
    expect(savePresentation).toEqual({ whiteSpace: 'nowrap', fits: true })
    const editorSurface = await availableEditor.evaluate((node) => {
      const style = getComputedStyle(node)
      return {
        borderTopWidth: Number.parseFloat(style.borderTopWidth),
        borderRightWidth: Number.parseFloat(style.borderRightWidth),
        backgroundColor: style.backgroundColor,
      }
    })
    expect(editorSurface.borderTopWidth).toBe(0)
    expect(editorSurface.borderRightWidth).toBe(0)
    expect(editorSurface.backgroundColor).toBe('rgba(0, 0, 0, 0)')
    for (const label of ['On-hand quantity', 'Adjustment reason']) {
      const field = controls.getByLabel(label, { exact: true })
      await expect(field).toBeVisible()
      expect((await field.boundingBox())!.height).toBeGreaterThanOrEqual(44)
    }
    const onHandField = controls.getByRole('textbox', { name: 'On-hand quantity' })
    const reasonField = controls.locator('.db-parts-workbench__edit textarea')
    await expectPartsStepperFocus(onHandField, 'pointer')
    if (width === 390 || width === 320) await expectCompactStockStepperLine(onHandField)
    if (width === 1280 || width === 390 || width === 320) {
      await page.screenshot({ path: testInfo.outputPath(`db038-stock-stepper-pointer-${width}.png`), fullPage: false })
      await page.screenshot({ path: testInfo.outputPath(`db038-stock-available-edit-${width}.png`), fullPage: false })
    }
    const startingOnHand = Number(await onHandField.inputValue())
    const decreaseOnHand = controls.getByRole('button', { name: 'Decrease On-hand quantity' })
    const increaseOnHand = controls.getByRole('button', { name: 'Increase On-hand quantity' })
    for (const stepControl of [decreaseOnHand, increaseOnHand]) {
      expect((await stepControl.boundingBox())!.width).toBeGreaterThanOrEqual(44)
      expect((await stepControl.boundingBox())!.height).toBeGreaterThanOrEqual(44)
    }
    await increaseOnHand.click()
    await expect(onHandField).toHaveValue(String(startingOnHand + 1))
    await decreaseOnHand.click()
    await expect(onHandField).toHaveValue(String(startingOnHand))
    await reasonField.fill('Cycle count contrast check')
    await expectWorkbenchEditorContrast(onHandField)
    await expectWorkbenchEditorContrast(reasonField)
    expect(await page.locator('.db-parts-workbench').innerText()).not.toMatch(/\b(?:packages|pkg)\b/i)
    if (width === 320) {
      await page.emulateMedia({ forcedColors: 'active' })
      await expectWorkbenchEditorContrast(onHandField)
      await expectWorkbenchEditorContrast(reasonField)
      await page.emulateMedia({ forcedColors: 'none' })
    }
    expect(await page.locator('body').evaluate(node => node.scrollWidth <= window.innerWidth)).toBe(true)
    const controlsBox = await controls.boundingBox()
    expect(controlsBox).not.toBeNull()
    expect(controlsBox!.x + controlsBox!.width).toBeLessThanOrEqual(width + 1)
    if (width === 1280 || width === 390) await page.screenshot({ path: testInfo.outputPath(`db038-inventory-controls-${width}.png`), fullPage: false })

    if (width === 1280) {
      await reasonField.fill('')
      await controls.getByLabel('On-hand quantity', { exact: true }).fill('8')
      await controls.getByRole('button', { name: 'Save' }).click()
      await expect(controls.getByRole('alert')).toHaveText('Explain why the on-hand quantity is changing.')
      expect(updates).toHaveLength(0)
      await controls.getByLabel('Adjustment reason', { exact: true }).fill('Cycle count correction')
      await controls.getByRole('button', { name: 'Save' }).click()
      await expect(page.getByRole('status')).toContainText('Air filter stock setting saved.')
      expect(updates).toEqual([{ id: 'inventory-1', body: { stock_quantity: 8, stock_adjustment_reason: 'Cycle count correction' } }])
      await expectSingleWorkbenchSelection(page, rows.first())
      await expect(controls).toContainText('8')
      await expect(controls.getByRole('button', { name: 'Edit available quantity' })).toBeFocused()
      const reorderTrigger = controls.getByRole('button', { name: 'Edit reorder point' })
      await reorderTrigger.focus()
      await reorderTrigger.press('Enter')
      const reorderField = controls.getByRole('textbox', { name: 'Reorder at' })
      await expectExpandedStockFact(controls, controls.getByRole('form', { name: 'Edit reorder point' }), 'Cancel reorder point edit')
      await expectPartsStepperFocus(reorderField, 'keyboard')
      await page.screenshot({ path: testInfo.outputPath('db038-stock-stepper-keyboard-1280.png'), fullPage: false })
      await page.screenshot({ path: testInfo.outputPath('db038-stock-reorder-edit-1280.png'), fullPage: false })
      const startingReorder = Number(await reorderField.inputValue())
      await controls.getByRole('button', { name: 'Decrease Reorder at' }).click()
      await expect(reorderField).toHaveValue(String(startingReorder - 1))
      await controls.getByRole('button', { name: 'Increase Reorder at' }).click()
      await expect(reorderField).toHaveValue(String(startingReorder))
      await reorderField.fill('6')
      await controls.getByRole('button', { name: 'Save' }).click()
      expect(updates[1]).toEqual({ id: 'inventory-1', body: { reorder_level: 6 } })

      await page.getByRole('button', { name: 'Adjust on-hand quantity' }).click()
      await controls.getByLabel('On-hand quantity', { exact: true }).fill('77')
      await controls.getByLabel('Adjustment reason', { exact: true }).fill('Must not cross records')
      await rows.nth(1).click()
      await expect(page.getByRole('heading', { name: 'Brake shoe' })).toBeVisible()
      await page.getByRole('button', { name: 'Adjust on-hand quantity' }).click()
      const nextControls = page.getByRole('tabpanel', { name: 'Stock' })
      await expect(nextControls.getByLabel('On-hand quantity', { exact: true })).toHaveValue('2')
      await expect(nextControls.getByLabel('Adjustment reason', { exact: true })).toHaveValue('')
    } else {
      await controls.getByRole('button', { name: 'Cancel available quantity edit' }).click()
      await expect(page.getByRole('button', { name: 'Adjust on-hand quantity' })).toBeFocused()
      const reorderTrigger = controls.getByRole('button', { name: 'Edit reorder point' })
      await reorderTrigger.focus()
      await reorderTrigger.press('Enter')
      const reorderField = controls.getByRole('textbox', { name: 'Reorder at' })
      await expectExpandedStockFact(controls, controls.getByRole('form', { name: 'Edit reorder point' }), 'Cancel reorder point edit')
      if (width === 320) await page.emulateMedia({ forcedColors: 'active' })
      await expectPartsStepperFocus(reorderField, 'keyboard')
      await expectCompactStockStepperLine(reorderField)
      if (width === 320) {
        const pill = reorderField.locator('..')
        const forcedFocus = await pill.evaluate((node) => {
          const style = getComputedStyle(node)
          return { outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth, boxShadow: style.boxShadow, forcedColorAdjust: style.forcedColorAdjust }
        })
        expect(forcedFocus.outlineStyle).toBe('solid')
        expect(Number.parseFloat(forcedFocus.outlineWidth)).toBeGreaterThanOrEqual(2)
        expect(forcedFocus.boxShadow).toBe('none')
        expect(forcedFocus.forcedColorAdjust).toBe('auto')
        await page.emulateMedia({ forcedColors: 'none' })
      }
      await page.screenshot({ path: testInfo.outputPath(`db038-stock-stepper-keyboard-${width}.png`), fullPage: false })
      if (width === 390 || width === 320) await page.screenshot({ path: testInfo.outputPath(`db038-stock-reorder-edit-${width}.png`), fullPage: false })
      await page.keyboard.press('Escape')
      await expect(reorderTrigger).toBeFocused()
    }
    expect(errors.get(page)).toEqual([])
    await context.close()
  }

  const failureContext = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const failurePage = await failureContext.newPage()
  await installFixture(failurePage, { inventoryUpdateStatus: 422 })
  await failurePage.goto('/dashboard/garage/inventory')
  await failurePage.locator('.db-parts-workbench__row-select').first().click()
  await failurePage.getByRole('tab', { name: 'Stock' }).click()
  const failureControls = failurePage.getByRole('tabpanel', { name: 'Stock' })
  await failureControls.getByRole('button', { name: 'Edit reorder point' }).click()
  await failureControls.getByLabel('Reorder at', { exact: true }).fill('9')
  await failureControls.getByRole('button', { name: 'Save' }).click()
  await expect(failurePage.getByRole('alert')).toContainText('Inventory update could not be saved.')
  await expect(failureControls.getByLabel('Reorder at', { exact: true })).toHaveValue('9')
  expect(errors.get(failurePage)).toEqual([])
  await failureContext.close()

  const readOnlyContext = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const readOnlyPage = await readOnlyContext.newPage()
  await installFixture(readOnlyPage, { readOnly: true })
  await readOnlyPage.goto('/dashboard/garage/inventory')
  await expect(readOnlyPage.getByRole('columnheader', { name: 'Select part' })).toHaveCount(0)
  const [readOnlyHeaderTemplate, readOnlyRowTemplate] = await Promise.all([
    readOnlyPage.locator('.db-parts-workbench__table-head').evaluate((node) => getComputedStyle(node).gridTemplateColumns),
    readOnlyPage.locator('.db-parts-workbench__row').first().evaluate((node) => getComputedStyle(node).gridTemplateColumns),
  ])
  expect(readOnlyHeaderTemplate).toBe(readOnlyRowTemplate)
  expect(readOnlyHeaderTemplate.trim().split(/\s+/)).toHaveLength(6)
  await expect(readOnlyPage.getByRole('columnheader', { name: /Needed|Reorder|Incoming/i })).toHaveCount(0)
  await expect(readOnlyPage.getByRole('checkbox', { name: /purchase preparation/ })).toHaveCount(0)
  await expect(readOnlyPage.getByRole('region', { name: 'Selected parts actions' })).toHaveCount(0)
  await readOnlyPage.locator('.db-parts-workbench__row-select').first().click()
  await expect(readOnlyPage.getByRole('button', { name: 'Add Part' })).toHaveCount(0)
  const readOnlyInspector = readOnlyPage.locator('.db-parts-workbench__inspector')
  await expect(readOnlyInspector).toContainText('You can view stock. Owners and admins can make changes.')
  await expect(readOnlyInspector.getByRole('button', { name: 'Adjust on-hand quantity' })).toHaveCount(0)
  await readOnlyPage.getByRole('tab', { name: 'Stock' }).click()
  await expect(readOnlyInspector.getByRole('button', { name: 'Edit available quantity' })).toHaveCount(0)
  await expect(readOnlyInspector.getByRole('button', { name: 'Edit reorder point' })).toHaveCount(0)
  await readOnlyPage.getByRole('tab', { name: 'Ordering' }).click()
  await expect(readOnlyInspector.getByText('Fleet Parts Co · Preferred')).toBeVisible()
  await expect(readOnlyInspector.getByRole('button', { name: 'Edit Fleet Parts Co supplier source' })).toHaveCount(0)
  await expect(readOnlyInspector.getByText('Edit source', { exact: true })).toHaveCount(0)
  await expect(readOnlyInspector.locator('.db-parts-workbench__source-row')).toHaveJSProperty('tagName', 'DIV')
  expect(errors.get(readOnlyPage)).toEqual([])
  await readOnlyContext.close()
})

test('DB-040 renders one connected Parts operating surface across supported widths', async ({ browser }, testInfo) => {
  const viewports = [
    { width: 1440, height: 960, mode: 'dark' as const },
    { width: 1280, height: 900, mode: 'high_contrast' as const },
    { width: 1100, height: 900, mode: 'dark' as const },
    { width: 960, height: 900, mode: 'light' as const },
    { width: 390, height: 844, mode: 'dark' as const },
    { width: 320, height: 720, mode: 'high_contrast' as const },
  ]

  for (const { width, height, mode } of viewports) {
    const context = await browser.newContext({
      viewport: { width, height },
      reducedMotion: 'reduce',
      forcedColors: width === 320 ? 'active' : 'none',
    })
    const page = await context.newPage()
    await installFixture(page, { appearanceMode: mode })
    await page.goto('/dashboard/garage/inventory')

    const workbench = page.locator('.db-parts-workbench')
    const body = page.locator('.db-parts-workbench__body')
    const ledgerWorkspace = page.locator('.db-parts-workbench__ledger-workspace')
    const inspector = page.locator('.db-parts-workbench__inspector')
    const toolbar = page.locator('.db-parts-workbench__toolbar')
    const viewCounts = page.locator('.db-parts-workbench__view-count')

    await expect(workbench).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Parts', exact: true })).toBeVisible()
    await expect(page.locator('.db-parts-workbench__row-select').first()).toBeVisible()
    await expect(viewCounts).toHaveCount(3)

    const [workbenchStyle, bodyStyle, toolbarStyle, countStyles] = await Promise.all([
      workbench.evaluate((node) => {
        const style = getComputedStyle(node)
        return {
          borderTopWidth: style.borderTopWidth,
          borderRadius: style.borderRadius,
          backgroundIsTransparent: style.backgroundColor === 'transparent' || /,\s*0\)$/.test(style.backgroundColor),
        }
      }),
      body.evaluate((node) => {
        const style = getComputedStyle(node)
        return {
          borderTopWidth: style.borderTopWidth,
          borderRightWidth: style.borderRightWidth,
          borderBottomWidth: style.borderBottomWidth,
          borderLeftWidth: style.borderLeftWidth,
          borderRadius: style.borderRadius,
          backgroundIsTransparent: style.backgroundColor === 'transparent' || /,\s*0\)$/.test(style.backgroundColor),
        }
      }),
      toolbar.evaluate((node) => {
        const style = getComputedStyle(node)
        return {
          borderTopWidth: style.borderTopWidth,
          borderBottomWidth: style.borderBottomWidth,
          backgroundIsTransparent: style.backgroundColor === 'transparent' || /,\s*0\)$/.test(style.backgroundColor),
        }
      }),
      viewCounts.evaluateAll((nodes) => nodes.map((node) => {
        const style = getComputedStyle(node)
        return { borderTopWidth: style.borderTopWidth, borderRadius: style.borderRadius, backgroundIsTransparent: style.backgroundColor === 'transparent' || /,\s*0\)$/.test(style.backgroundColor) }
      })),
    ])

    expect(workbenchStyle).toEqual({ borderTopWidth: '0px', borderRadius: '0px', backgroundIsTransparent: true })
    expect(bodyStyle).toEqual({
      borderTopWidth: '0px',
      borderRightWidth: '0px',
      borderBottomWidth: '0px',
      borderLeftWidth: '0px',
      borderRadius: '0px',
      backgroundIsTransparent: true,
    })
    expect(toolbarStyle).toEqual({ borderTopWidth: '0px', borderBottomWidth: '0px', backgroundIsTransparent: true })
    expect(countStyles.every((style) => style.borderTopWidth === '0px' && style.borderRadius === '0px' && style.backgroundIsTransparent)).toBe(true)

    const search = page.getByRole('searchbox', { name: 'Search parts' }).locator('..')
    const filters = page.getByRole('group', { name: 'Stock filter' })
    const options = page.getByRole('button', { name: 'Ledger options' })
    for (const control of [search, filters, options]) {
      const box = await control.boundingBox()
      expect(box).not.toBeNull()
      expect(box!.height).toBeGreaterThanOrEqual(44)
    }
    const controlRadii = await Promise.all([search, filters, options].map((control) => control.evaluate((node) => Number.parseFloat(getComputedStyle(node).borderRadius))))
    expect(controlRadii.every((radius) => radius >= 8)).toBe(true)

    if (width > 760) {
      const ledger = page.locator('.db-parts-workbench__ledger')
      const divider = await ledgerWorkspace.evaluate((node) => {
        const style = getComputedStyle(node)
        return { width: style.borderInlineEndWidth, style: style.borderInlineEndStyle }
      })
      const inspectorEdges = await inspector.evaluate((node) => {
        const style = getComputedStyle(node)
        return { start: style.borderInlineStartWidth, end: style.borderInlineEndWidth }
      })
      expect(Number.parseFloat(divider.width)).toBeGreaterThanOrEqual(1)
      expect(divider.style).not.toBe('none')
      expect(inspectorEdges).toEqual({ start: '0px', end: '0px' })

      const [workspaceBox, toolbarBox, optionsBox, ledgerBox] = await Promise.all([
        ledgerWorkspace.boundingBox(),
        toolbar.boundingBox(),
        options.boundingBox(),
        ledger.boundingBox(),
      ])
      expect(workspaceBox).not.toBeNull()
      expect(toolbarBox).not.toBeNull()
      expect(optionsBox).not.toBeNull()
      expect(ledgerBox).not.toBeNull()
      for (const contentRight of [toolbarBox!.x + toolbarBox!.width, optionsBox!.x + optionsBox!.width, ledgerBox!.x + ledgerBox!.width]) {
        expect((workspaceBox!.x + workspaceBox!.width) - contentRight).toBeGreaterThanOrEqual(8)
      }
      await expect.poll(() => ledger.evaluate((node) => getComputedStyle(node).scrollbarGutter)).toContain('stable')

      await ledger.evaluate((node) => { node.scrollLeft = node.scrollWidth })
      const statusCells = page.locator('.db-parts-workbench__remark:not(.is-empty)')
      await expect(statusCells.filter({ hasText: 'Supplier needed' })).toHaveCount(1)
      const renderedStatusMetrics = await statusCells.evaluateAll((nodes) => nodes.map((node) => ({
        text: node.textContent?.trim(),
        clientWidth: node.clientWidth,
        scrollWidth: node.scrollWidth,
        right: node.getBoundingClientRect().right,
      })))
      expect(renderedStatusMetrics.map((metric) => metric.text)).toEqual(expect.arrayContaining(['Short 2', 'Supplier needed', 'Placeholder']))
      expect(renderedStatusMetrics.every((metric) => metric.scrollWidth <= metric.clientWidth + 1)).toBe(true)
      expect(renderedStatusMetrics.every((metric) => (workspaceBox!.x + workspaceBox!.width) - metric.right >= 8)).toBe(true)

      const commonStatusFit = await statusCells.first().evaluate((node, labels) => {
        const style = getComputedStyle(node)
        const context = document.createElement('canvas').getContext('2d')!
        context.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`
        const available = node.clientWidth - Number.parseFloat(style.paddingInlineStart) - Number.parseFloat(style.paddingInlineEnd)
        const marker = 7
        const gap = Number.parseFloat(style.columnGap) || 0
        return labels.map((label) => ({ label, required: context.measureText(label).width + marker + gap, available }))
      }, ['Needs reorder', 'Supplier needed', 'Placeholder', 'Incoming', 'Archived', 'Short 999'])
      expect(commonStatusFit.every((metric) => metric.required <= metric.available)).toBe(true)
      await page.screenshot({ path: testInfo.outputPath(`db040-ledger-right-edge-${width}.png`), fullPage: false })
      await ledger.evaluate((node) => { node.scrollLeft = 0 })
    }

    await options.focus()
    await options.press('Enter')
    await expect(page.getByRole('dialog', { name: 'Ledger options' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(options).toBeFocused()

    const needsReorder = page.getByRole('button', { name: /Needs reorder 2/ })
    await needsReorder.focus()
    await needsReorder.press('Enter')
    await expect(needsReorder).toHaveAttribute('aria-current', 'page')
    const allParts = page.getByRole('button', { name: /All parts 99/ })
    await allParts.focus()
    await allParts.press('Enter')
    await expect(allParts).toHaveAttribute('aria-current', 'page')

    if (width <= 760) {
      await page.screenshot({ path: testInfo.outputPath(`db040-parts-list-${width}.png`), fullPage: false })
    }
    await page.locator('.db-parts-workbench__row-select').first().click()
    await expect(page.locator('.db-parts-workbench__selected-action')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Air filter' })).toBeVisible()

    const selectedAction = page.locator('.db-parts-workbench__selected-action')
    const selectedActionStyle = await selectedAction.evaluate((node) => getComputedStyle(node).backgroundColor)
    expect(selectedActionStyle).not.toBe('rgba(0, 0, 0, 0)')
    const selectedButtons = selectedAction.getByRole('button')
    for (let index = 0; index < await selectedButtons.count(); index += 1) {
      const button = selectedButtons.nth(index)
      const box = await button.boundingBox()
      expect(box).not.toBeNull()
      expect(box!.height).toBeGreaterThanOrEqual(44)
      expect(await button.evaluate((node) => Number.parseFloat(getComputedStyle(node).borderRadius))).toBeGreaterThanOrEqual(8)
    }

    const overviewFacts = page.locator('.db-parts-workbench__facts.is-overview')
    const overviewStyle = await overviewFacts.evaluate((node) => {
      const style = getComputedStyle(node)
      return { top: style.borderTopWidth, bottom: style.borderBottomWidth }
    })
    expect(overviewStyle).toEqual({ top: '0px', bottom: '0px' })
    const overviewCellRules = await overviewFacts.locator(':scope > div').evaluateAll((nodes) => nodes.map((node) => getComputedStyle(node).borderInlineEndWidth))
    expect(overviewCellRules.every((widthValue) => widthValue === '0px')).toBe(true)

    const containment = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      document: document.documentElement.scrollWidth,
    }))
    expect(containment.document).toBeLessThanOrEqual(containment.viewport)
    await page.screenshot({ path: testInfo.outputPath(`db040-parts-connected-${width}.png`), fullPage: false })
    expect(errors.get(page)).toEqual([])
    await context.close()
  }
})
