import { expect, test, type Page } from '@playwright/test'
import { presentationFixture } from '../../frontend/src/test-fixtures/db035/appearance'
import { dashboardActionQueueFixture } from '../../frontend/src/test-fixtures/db035/dashboard'
import { garageOwnerSession } from '../../frontend/src/test-fixtures/db035/staffSession'

const runtimeFailures = new WeakMap<Page, string[]>()

function assertNoRuntimeFailures(page: Page) {
  expect(runtimeFailures.get(page) ?? []).toEqual([])
}

const managerUser = (variant: 'legacy' | 'new') => ({
  ...garageOwnerSession,
  can_access_messaging: true,
  messaging_enabled: true,
  presentation: presentationFixture(variant),
})

const dailyWorksetFixture = {
  timezone: 'America/New_York',
  business_date: '2026-08-14',
  next_reset_at: '2026-08-15T04:00:00Z',
  needs_attention: { items: dashboardActionQueueFixture.orders_needing_action, has_more: false },
  on_floor: { items: dashboardActionQueueFixture.orders_on_floor, has_more: false },
  ready_to_close: { items: dashboardActionQueueFixture.orders_ready_to_close, has_more: false },
  closed_today: { items: [], has_more: false },
}

const selectedWorkspaceFixture = {
  id: 'ro-needs-action', tenant_id: 'tenant-garage', customer_id: 'customer-1', vehicle_id: 'vehicle-1',
  vehicle_make: 'Freightliner', vehicle_model: 'Cascadia 126', vehicle_year: 2021, vehicle_unit_number: 'NSL-1047', vehicle_vin: 'VIN1047',
  customer_company_name: 'NorthStar Logistics', order_number: 'RO-2025-0417', status: 'draft',
  description: 'Source-grounded dashboard fixture', customer_notes: null, internal_notes: null,
  assigned_mechanic_id: null, total_parts_cost: '2875.42', total_labor_cost: '1250.00', total_cost: '4494.62',
  created_at: '2026-08-11T12:00:00Z', updated_at: '2026-08-11T12:30:00Z',
}

async function installSession(page: Page, variant: 'legacy' | 'new') {
  const failures: string[] = []
  runtimeFailures.set(page, failures)
  page.on('console', message => {
    if (message.type() === 'error') failures.push(`console: ${message.text()}`)
  })
  page.on('pageerror', error => failures.push(`pageerror: ${error.message}`))
  page.on('requestfailed', request => {
    const failure = request.failure()?.errorText ?? 'unknown failure'
    if (request.url().includes('/api/v1/') && failure !== 'net::ERR_ABORTED') {
      failures.push(`requestfailed: ${request.method()} ${request.url()} (${failure})`)
    }
  })
  await page.addInitScript(() => {
    window.localStorage.clear()
    window.sessionStorage.clear()

    class FixtureWebSocket extends EventTarget {
      static readonly CONNECTING = 0
      static readonly OPEN = 1
      static readonly CLOSING = 2
      static readonly CLOSED = 3

      readonly url: string
      readyState = FixtureWebSocket.CONNECTING
      onopen: ((event: Event) => void) | null = null
      onmessage: ((event: MessageEvent) => void) | null = null
      onerror: ((event: Event) => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null

      constructor(url: string | URL) {
        super()
        this.url = String(url)
        queueMicrotask(() => {
          this.readyState = FixtureWebSocket.OPEN
          const event = new Event('open')
          this.onopen?.(event)
          this.dispatchEvent(event)
        })
      }

      send() {}

      close() {
        this.readyState = FixtureWebSocket.CLOSED
        const event = new CloseEvent('close', { code: 1000, wasClean: true })
        this.onclose?.(event)
        this.dispatchEvent(event)
      }
    }

    Object.defineProperty(window, 'WebSocket', {
      configurable: true,
      value: FixtureWebSocket,
    })
  })

  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/auth/workos/me')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(managerUser(variant)) })
      return
    }
    if (url.pathname.endsWith('/auth/workos/session/refresh')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
      return
    }
    if (url.pathname.endsWith('/auth/me/appearance')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(presentationFixture(variant)) })
      return
    }
    if (url.pathname.endsWith('/auth/tenant-branding')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ name: 'Truck Pit Stop Wisconsin', slug: 'truck-pit-stop-wisconsin', state: 'WI', logo_url: null }),
      })
      return
    }
    if (url.pathname.endsWith('/admin/garage-profile')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ name: 'Truck Pit Stop Wisconsin', state: 'WI', logo_url: null }) })
      return
    }
    if (url.pathname.endsWith('/messages/unread-summary')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ unread_count: 0 }) })
      return
    }
    if (url.pathname.endsWith('/dashboard/action-queue')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(dashboardActionQueueFixture) })
      return
    }
    if (url.pathname.endsWith('/dashboard/daily-workset')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(dailyWorksetFixture) })
      return
    }
    if (url.pathname.endsWith('/repair-orders/ro-needs-action/workspace')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(selectedWorkspaceFixture) })
      return
    }
    if (url.pathname.endsWith('/repair-orders/ro-needs-action/price-build')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          order_id: 'ro-needs-action', labor_total: '0.00', parts_total: '0.00', total_cost: '1250.00',
          pricing_locked: false, can_edit_work: true, can_assign_technician: true, can_start_work: true,
          can_finalize: false, lines: [], parts: [], warnings: [],
        }),
      })
      return
    }
    if (url.pathname.endsWith('/quotes')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
      return
    }
    if (url.pathname.endsWith('/customers') || url.pathname.endsWith('/repair-orders')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], total: 0, has_more: false }) })
      return
    }
    if (url.pathname.endsWith('/messages/threads')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], next_cursor: null, has_more: false }) })
      return
    }
    if (url.pathname.endsWith('/mechanics') || url.pathname.endsWith('/mechanics/pto-requests/pending') || url.pathname.endsWith('/admin/staff')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
      return
    }
    // /dashboard/garage now resolves to Inventory rather than Team, so the
    // My Shop surface pulls the parts-operations reads on entry.
    if (url.pathname.endsWith('/parts-operations/summary')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ needs_reorder_count: 0, low_stock_count: 0, open_purchase_order_count: 0 }),
      })
      return
    }
    if (url.pathname.endsWith('/parts-operations/parts')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0, skip: 0, limit: 50, has_more: false }),
      })
      return
    }
    if (url.pathname.endsWith('/parts-operations/activity')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0, skip: 0, limit: 1, has_more: false }),
      })
      return
    }
    throw new Error(`Unhandled DB-035 fixture route: ${route.request().method()} ${url.pathname}`)
  })
}

test('Harden preserves the canonical Shop Cockpit queues and repair-order deep links in both presentations', async ({ browser }) => {
  for (const variant of ['legacy', 'new'] as const) {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } })
    const page = await context.newPage()
    await installSession(page, variant)
    await page.goto('/dashboard')

    if (variant === 'new') {
      await expect(page.getByRole('heading', { name: 'Action Ledger' })).toBeVisible()
      await expect(page.getByRole('tab', { name: /Needs Action 1/ })).toBeVisible()
      await expect(page.getByRole('tab', { name: /On the Floor 1/ })).toBeVisible()
      await expect(page.getByRole('tab', { name: /Ready to Close 1/ })).toBeVisible()
    } else {
      await expect(page.getByText('Work Queue', { exact: true })).toBeVisible()
      await expect(page.getByRole('heading', { name: 'Needs Action' })).toBeVisible()
      await expect(page.getByRole('heading', { name: 'On the Floor' })).toBeVisible()
      await expect(page.getByRole('heading', { name: 'Ready to Close' })).toBeVisible()
    }
    await expect(page.getByText('Today’s work', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Follow-through', { exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Lightning Order' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Full Order' })).toBeVisible()

    await page.getByRole('button', { name: /RO-2025-0417/ }).click()
    if (variant === 'new') {
      await expect(page).toHaveURL(/\/dashboard\?selected=ro-needs-action&queue=needs_action$/)
    } else {
      await expect(page).toHaveURL(/\/dashboard\/repair-orders\?selected=ro-needs-action&queue=needs_action$/)
    }
    assertNoRuntimeFailures(page)
    await context.close()
  }
})

async function openAppearance(page: Page, variant: 'legacy' | 'new') {
  await installSession(page, variant)
  await page.goto('/dashboard/settings')
  const compactSectionPicker = page.getByRole('button', { name: /^Settings section:/ })
  if (variant === 'new' && page.viewportSize()!.width < 960) {
    await expect(compactSectionPicker).toBeVisible()
    await compactSectionPicker.click()
    await page.getByRole('group', { name: 'Settings sections' }).getByRole('button', { name: 'Appearance' }).click()
  } else {
    await page.getByRole('button', { name: /Appearance|Theme/ }).click()
  }
}

test('new staff presentation preserves product/shop hierarchy and responsive appearance controls', async ({ page }) => {
  await openAppearance(page, 'new')
  await expect(page.locator('.db-staff-shell')).toHaveAttribute('data-presentation', 'new')
  await expect(page.getByLabel('DieselBridge Shop Work')).toBeVisible()
  await expect(page.getByLabel('Active shop: Truck Pit Stop Wisconsin')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Appearance' })).toBeVisible()
  await expect(page.getByText('Ready to close')).toHaveCSS('color', 'rgb(16, 185, 129)')

  await page.setViewportSize({ width: 1366, height: 900 })
  await page.screenshot({ path: '/tmp/db035-new-appearance-1366.png', fullPage: true })

  for (const width of [1440, 1366, 1280, 1120, 1024, 960, 390, 320]) {
    await page.setViewportSize({ width, height: width <= 390 ? 844 : 900 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
    const controls = page.locator('.db-appearance button:visible')
    const count = await controls.count()
    for (let index = 0; index < count; index += 1) {
      const box = await controls.nth(index).boundingBox()
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(44)
      expect(box?.width ?? 0).toBeGreaterThanOrEqual(44)
    }
  }

  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: '/tmp/db035-new-appearance-390.png', fullPage: true })
  await page.getByRole('button', { name: /Rose/i }).click()
  await expect(page.getByRole('status')).toContainText('Previewing changes')
  await page.getByRole('button', { name: /Cancel/i }).click()
  await expect(page.getByRole('status')).toContainText('Up to date')
  assertNoRuntimeFailures(page)
})

test('new shell uses a full desktop rail, compact iPad rail, and source-grounded mobile navigation', async ({ page }) => {
  await installSession(page, 'new')
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/\/dashboard$/)
  await expect(page.locator('.db-staff-shell')).toHaveAttribute('data-surface', 'dashboard')
  await expect(page.getByLabel('DieselBridge Shop Work')).toBeVisible()

  for (const [width, expectedRail] of [[1280, 224], [1024, 84]] as const) {
    await page.setViewportSize({ width, height: 900 })
    await expect(page.locator('.db-staff-shell')).toHaveAttribute('data-rail-expanded', String(width >= 1280))
    const rail = await page.locator('.db-staff-nav').boundingBox()
    expect(rail?.width ?? 0).toBeGreaterThanOrEqual(expectedRail - 1)
    expect(rail?.width ?? 0).toBeLessThanOrEqual(expectedRail + 1)
    await expect(page.locator('.db-mobile-nav')).toBeHidden()
    if (width < 1280) await expect(page.getByRole('button', { name: /navigation rail/i })).toHaveCount(0)
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
  }
  assertNoRuntimeFailures(page)

  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 844 })
    await expect(page.locator('.db-mobile-nav')).toBeVisible()
    await expect(page.locator('.db-staff-primary-nav')).toBeHidden()
    const links = page.locator('.db-mobile-nav a:visible')
    for (let index = 0; index < await links.count(); index += 1) {
      const box = await links.nth(index).boundingBox()
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(44)
      expect(box?.width ?? 0).toBeGreaterThanOrEqual(44)
    }
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
  }
})

test('legacy and new resolve from bootstrap without changing the staff route', async ({ browser }) => {
  const results: Array<{ variant: string; path: string; requests: string[] }> = []
  for (const variant of ['legacy', 'new'] as const) {
    const context = await browser.newContext({ viewport: { width: 1366, height: 900 } })
    const page = await context.newPage()
    const requests: string[] = []
    page.on('request', request => {
      const url = new URL(request.url())
      if (url.pathname.includes('/api/v1/')) requests.push(`${request.method()} ${url.pathname}`)
    })
    await openAppearance(page, variant)
    await expect(page.locator('.db-staff-shell')).toHaveAttribute('data-presentation', variant)
    if (variant === 'legacy') {
      await expect(page.getByLabel('Truck Pit Stop Wisconsin dashboard')).toBeVisible()
      await expect(page.getByText('Theme Preview')).toBeVisible()
      await page.screenshot({ path: '/tmp/db035-legacy-appearance-1366.png', fullPage: true })
    }
    else {
      await expect(page.getByLabel('DieselBridge Shop Work')).toBeVisible()
      await expect(page.getByRole('heading', { name: 'Appearance' })).toBeVisible()
    }
    results.push({ variant, path: new URL(page.url()).pathname, requests: [...new Set(requests)].sort() })
    assertNoRuntimeFailures(page)
    await context.close()
  }
  expect(results[0].path).toBe('/dashboard/settings')
  expect(results[1].path).toBe(results[0].path)
  expect(results[1].requests).toEqual(results[0].requests)
})

test('both presentations cover all six staff surfaces across the contracted viewport boundaries', async ({ browser }) => {
  test.setTimeout(120_000)
  const surfaces = [
    ['/dashboard', 'dashboard'],
    ['/dashboard/customers', 'customers'],
    ['/dashboard/repair-orders', 'repair-orders'],
    ['/dashboard/messages', 'messages'],
    ['/dashboard/garage', 'my-shop'],
    ['/dashboard/settings', 'profile-settings'],
  ] as const
  for (const variant of ['legacy', 'new'] as const) {
    const context = await browser.newContext()
    const page = await context.newPage()
    await installSession(page, variant)
    for (const width of [1440, 1366, 1280, 1120, 1024, 960, 390, 320]) {
      await page.setViewportSize({ width, height: width <= 390 ? 844 : 900 })
      for (const [path, surface] of surfaces) {
        await page.goto(path)
        await expect(page.locator('.db-staff-shell'), `${variant} ${width}px ${path}`).toHaveAttribute('data-surface', surface)
        await expect(page.locator('.db-staff-shell')).toHaveAttribute('data-presentation', variant)
        await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
      }
    }
    assertNoRuntimeFailures(page)
    await context.close()
  }
})

test('both presentations remain operable with reduced motion, forced colors, coarse input, and 200 percent zoom', async ({ browser }) => {
  test.setTimeout(90_000)
  for (const variant of ['legacy', 'new'] as const) {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      forcedColors: 'active',
      reducedMotion: 'reduce',
      hasTouch: true,
    })
    const page = await context.newPage()
    await openAppearance(page, variant)
    await page.evaluate(() => { document.documentElement.style.fontSize = '200%' })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
    if (variant === 'new') {
      await page.getByRole('button', { name: /Amber/i }).click()
      await expect(page.getByRole('status')).toContainText('Previewing changes')
      await expect(page.getByRole('button', { name: /Apply appearance/i })).toBeVisible()
    } else {
      await expect(page.getByText('Theme Preview')).toBeVisible()
    }
    assertNoRuntimeFailures(page)
    await context.close()
  }
})
