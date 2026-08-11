import { expect, test, type Locator, type Page } from '@playwright/test'

const customer = {
  id: 'customer-safe-1',
  first_name: 'Jordan',
  last_name: 'Lee',
  email: 'jordan@example.test',
  phone: '(704) 555-0100',
  company_name: 'NorthStar Logistics',
  created_at: '2026-01-01T12:00:00Z',
  updated_at: '2026-08-11T12:00:00Z',
}

const vehicle = {
  id: 'vehicle-safe-1',
  customer_id: customer.id,
  year: 2021,
  make: 'Freightliner',
  model: 'Cascadia 126',
  unit_number: 'NSL-1047',
  vin: '•••••••••••••1234',
  license_plate: 'TEST-1047',
  color: 'White',
  mileage: 412358,
  updated_at: '2026-08-11T12:00:00Z',
}

const baseOrder = {
  customer_id: customer.id,
  vehicle_id: vehicle.id,
  vehicle_year: vehicle.year,
  vehicle_make: vehicle.make,
  vehicle_model: vehicle.model,
  vehicle_unit_number: vehicle.unit_number,
  total_cost: '4494.62',
  total_labor_cost: '1250.00',
  total_parts_cost: '2875.42',
  labor_discount_amount: '0.00',
  order_discount_amount: '0.00',
  customer_notes: null,
  internal_notes: JSON.stringify({ selected_services: [] }),
  created_at: '2026-08-11T08:52:00Z',
  updated_at: '2026-08-11T10:32:00Z',
}

const orders = [
  {
    ...baseOrder,
    id: 'order-active-1',
    order_number: 'RO-2026-0811',
    status: 'quoted',
    description: 'DEF dosing system diagnosis',
    quote_sent: true,
    quote_approved: false,
    quote_sent_at: '2026-08-11T09:47:00Z',
  },
  {
    ...baseOrder,
    id: 'order-active-2',
    order_number: 'RO-2026-0812',
    status: 'in_progress',
    description: 'PM service and inspection',
    quote_sent: false,
    quote_approved: false,
  },
  {
    ...baseOrder,
    id: 'order-invoiced-1',
    order_number: 'RO-2026-0813',
    status: 'invoiced',
    description: 'Air system repair ready for payment',
    quote_sent: true,
    quote_approved: true,
    invoice_created_at: '2026-08-11T10:15:00Z',
  },
  {
    ...baseOrder,
    id: 'order-paid-1',
    order_number: 'RO-2026-0804',
    status: 'paid',
    description: 'Completed DEF dosing unit replacement',
    quote_sent: true,
    quote_approved: true,
    invoice_created_at: '2026-08-11T10:15:00Z',
  },
]

const invoices = [
  {
    id: 'invoice-unpaid-1',
    repair_order_id: 'order-invoiced-1',
    invoice_number: 'INV-2026-0813',
    status: 'sent',
    subtotal: '4210.42',
    shop_supplies_amount: '85.00',
    tax_amount: '284.20',
    service_fee_amount: '0.00',
    discount_amount: '0.00',
    total_amount: '4494.62',
    amount_paid: '0.00',
    due_date: '2026-08-11',
    paid_at: null,
    created_at: '2026-08-11T10:15:00Z',
    updated_at: '2026-08-11T10:15:00Z',
  },
  {
    id: 'invoice-safe-1',
    repair_order_id: 'order-paid-1',
    invoice_number: 'INV-2026-0804',
    status: 'paid',
    subtotal: '4210.42',
    shop_supplies_amount: '85.00',
    tax_amount: '284.20',
    service_fee_amount: '0.00',
    discount_amount: '0.00',
    total_amount: '4494.62',
    amount_paid: '4494.62',
    due_date: '2026-08-11',
    paid_at: '2026-08-11T10:32:00Z',
    created_at: '2026-08-11T10:15:00Z',
    updated_at: '2026-08-11T10:32:00Z',
  },
]

async function installSafePortalFixture(page: Page) {
  await page.addInitScript(({ fixtureCustomer }) => {
    window.localStorage.setItem('theme-font-size', 'compact')
    window.localStorage.setItem('auth-storage', JSON.stringify({
      state: {
        user: {
          id: 'user-safe-1',
          email: fixtureCustomer.email,
          first_name: fixtureCustomer.first_name,
          last_name: fixtureCustomer.last_name,
          phone: fixtureCustomer.phone,
          role: 'customer',
          is_active: true,
          tenant_id: 'tenant-safe-1',
          tenant_name: 'NorthStar Shop',
          tenant_slug: 'northstar-safe',
          tenant_logo_url: null,
          customer_id: fixtureCustomer.id,
        },
        token: null,
        refreshToken: null,
        isAuthenticated: true,
        authProvider: 'legacy',
      },
      version: 0,
    }))
  }, { fixtureCustomer: customer })

  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ status: 200, contentType: 'text/css', body: '' }))
  await page.route('https://fonts.gstatic.com/**', route => route.fulfill({ status: 204, body: '' }))
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/api\/v1/, '')
    const json = (body: unknown) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

    if (path === '/auth/tenant-branding') return json({ name: 'NorthStar Shop', slug: 'northstar-safe', logo_url: null, state: 'NC' })
    if (path === `/customers/${customer.id}`) return json(customer)
    if (path === '/vehicles') return json({ items: [vehicle], has_more: false, skip: 0, limit: 100 })
    if (path === '/repair-orders') return json({ items: orders, has_more: false, skip: 0, limit: 100 })
    if (path === '/invoices') {
      const repairOrderId = url.searchParams.get('repair_order_id')
      return json(repairOrderId ? invoices.filter(item => item.repair_order_id === repairOrderId) : invoices)
    }
    if (path === '/repair-orders/order-paid-1/detail') return json({ ...orders.find(order => order.id === 'order-paid-1'), parts_usage: [] })
    if (path === '/repair-orders/order-active-1/detail') return json({ ...orders.find(order => order.id === 'order-active-1'), parts_usage: [] })
    if (path === '/repair-orders/order-invoiced-1/detail') return json({ ...orders.find(order => order.id === 'order-invoiced-1'), parts_usage: [] })
    if (path === '/repair-orders/order-paid-1/photos' || path === '/repair-orders/order-invoiced-1/photos') return json([])
    if (path === '/payments/zelle-info/invoice-unpaid-1') {
      return json({ zelle_email: null, zelle_phone: null, zelle_qr_image: null, garage_name: 'NorthStar Shop', stripe_payments_available: false })
    }
    if (path === '/quickbooks/payments/availability/invoice-unpaid-1') {
      return json({ available: false, token_url: null, message: 'Unavailable in safe fixture' })
    }
    if (path === '/quotes') return json(null)
    if (path.startsWith('/quotes/repair-order/') && path.endsWith('/history')) {
      return json({ revisions: [], events: [] })
    }
    if (path === '/auth/platform-contact') return json({ support_name: 'Diesel Bridge Support', support_email: 'support@example.test', support_phone: null })

    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: `Unhandled safe fixture route: ${path}` }) })
  })
}

async function expectContainedPortalGeometry(page: Page, viewportWidth: number) {
  const geometry = await page.evaluate(() => {
    const nav = document.querySelector('nav')
    const main = document.querySelector('main')
    const root = main?.parentElement
    return {
      documentClient: document.documentElement.clientWidth,
      documentScroll: document.documentElement.scrollWidth,
      rootClient: root?.clientWidth ?? 0,
      rootScroll: root?.scrollWidth ?? 0,
      navClient: nav?.clientWidth ?? 0,
      navScroll: nav?.scrollWidth ?? 0,
      mainClient: main?.clientWidth ?? 0,
      mainScroll: main?.scrollWidth ?? 0,
    }
  })

  expect(geometry.documentClient).toBe(viewportWidth)
  expect(geometry.documentScroll).toBe(viewportWidth)
  expect(geometry.rootClient).toBe(viewportWidth)
  expect(geometry.rootScroll).toBe(viewportWidth)
  expect(geometry.navClient).toBe(viewportWidth)
  expect(geometry.navScroll).toBe(viewportWidth)
  expect(geometry.mainClient).toBe(viewportWidth)
  expect(geometry.mainScroll).toBe(viewportWidth)
}

async function expectVisibleTargetsAtLeast44(page: Page) {
  const undersized = await page.locator('a[href], button, input, select, textarea, [role="button"]').evaluateAll(elements =>
    elements.flatMap(element => {
      const node = element as HTMLElement
      const rect = node.getBoundingClientRect()
      const style = getComputedStyle(node)
      const visible = style.display !== 'none'
        && style.visibility !== 'hidden'
        && Number(style.opacity) > 0
        && rect.width > 0
        && rect.height > 0
        && rect.bottom > 0
        && rect.top < window.innerHeight
        && rect.right > 0
        && rect.left < window.innerWidth
      if (!visible || (rect.width >= 44 && rect.height >= 44)) return []
      return [{
        label: node.getAttribute('aria-label') || node.textContent?.trim().replace(/\s+/g, ' ').slice(0, 80) || node.tagName,
        width: rect.width,
        height: rect.height,
      }]
    }),
  )
  expect(undersized).toEqual([])
}

async function expectTargetAtLeast44(target: Locator, label: string) {
  await target.scrollIntoViewIfNeeded()
  await expect(target, `${label} should be visible`).toBeVisible()
  const box = await target.boundingBox()
  expect(box, `${label} should have a rendered box`).not.toBeNull()
  expect(box!.width, `${label} width`).toBeGreaterThanOrEqual(44)
  expect(box!.height, `${label} height`).toBeGreaterThanOrEqual(44)
}

async function expectFullPortalSurfaceTargetsAtLeast44(page: Page) {
  const main = page.locator('main')
  const dimensions = await main.evaluate(element => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
  }))
  const lastTop = Math.max(0, dimensions.scrollHeight - dimensions.clientHeight)
  const step = Math.max(1, Math.floor(dimensions.clientHeight * 0.75))
  const stops = Array.from(
    { length: Math.ceil(lastTop / step) + 1 },
    (_, index) => Math.min(lastTop, index * step),
  )
  if (stops.at(-1) !== lastTop) stops.push(lastTop)

  for (const top of stops) {
    await main.evaluate((element, scrollTop) => { element.scrollTop = scrollTop }, top)
    await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => resolve())))
    await expectVisibleTargetsAtLeast44(page)
  }
}

for (const width of [390, 320]) {
  test(`customer portal contains mobile geometry and touch targets at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 780 })
    await installSafePortalFixture(page)

    const browserErrors: string[] = []
    page.on('pageerror', error => browserErrors.push(`page: ${error.message}`))
    page.on('console', message => {
      if (message.type() === 'error') browserErrors.push(`console: ${message.text()}`)
    })

    await page.goto('/portal')
    await expect(page.getByText('Action required')).toBeVisible()
    await expect(page).toHaveTitle('Dashboard | NorthStar Shop Customer Portal')
    await expectContainedPortalGeometry(page, width)
    await expectTargetAtLeast44(page.getByRole('button', { name: 'Select & pay' }), 'Select & pay')
    await expectTargetAtLeast44(page.getByRole('link', { name: 'Pay', exact: true }), 'Pay')
    await expectFullPortalSurfaceTargetsAtLeast44(page)

    await page.getByRole('button', { name: 'More' }).click()
    await page.getByRole('link', { name: 'Repairs', exact: true }).click()
    await expect(page).toHaveURL(/\/portal\/repairs\?view=active$/)
    await expect(page).toHaveTitle('Active Repairs | NorthStar Shop Customer Portal')
    await expect(page.getByRole('heading', { name: 'Active repairs' })).toBeVisible()
    await expectContainedPortalGeometry(page, width)
    await expectVisibleTargetsAtLeast44(page)

    await page.getByRole('button', { name: /Air system repair ready for payment/ }).click()
    await expect(page.getByRole('heading', { name: 'RO-2026-0813' })).toBeVisible()
    await expectTargetAtLeast44(page.getByRole('button', { name: 'Download PDF' }), 'Download PDF')
    await expectTargetAtLeast44(page.getByRole('link', { name: 'Review payment options' }), 'Review payment options')
    await expectContainedPortalGeometry(page, width)
    await expectFullPortalSurfaceTargetsAtLeast44(page)
    await page.getByRole('button', { name: 'Repairs', exact: true }).click()

    await page.getByRole('button', { name: /DEF dosing system diagnosis/ }).click()
    await expect(page.getByRole('button', { name: 'Repairs', exact: true })).toBeVisible()
    await expectContainedPortalGeometry(page, width)
    await expectVisibleTargetsAtLeast44(page)
    await page.getByRole('button', { name: 'Repairs', exact: true }).click()

    await page.getByRole('link', { name: 'History', exact: true }).click()
    await expect(page).toHaveURL(/\/portal\/repairs$/)
    await expect(page).toHaveTitle('Repair History | NorthStar Shop Customer Portal')
    await expect(page.getByRole('heading', { name: 'Repair history' })).toBeVisible()
    await expectContainedPortalGeometry(page, width)
    await expectVisibleTargetsAtLeast44(page)

    await page.getByRole('button', { name: /Completed DEF dosing unit replacement/ }).click()
    await expect(page.getByRole('button', { name: 'History' })).toBeVisible()
    await expectContainedPortalGeometry(page, width)
    await expectVisibleTargetsAtLeast44(page)

    expect(browserErrors).toEqual([])
  })
}
