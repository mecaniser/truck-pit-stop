import { expect, test, type Page } from '@playwright/test'
import { garageOwnerSession } from '../../frontend/src/test-fixtures/db035/staffSession'

// DB-095: the Parts technical line mirrors Easy Truck Shop figures, so it must
// say how old the mirror is. Signed-in synthetic fixture: no real tenant data,
// no mutation, every API response served from this file.

// Shape mirrors the DB-038 parts fixture so the inspector renders; only the
// sync freshness is under test here.
const part = {
  id: 'part-sync-1',
  sku: 'ALT-42',
  name: 'Alternator',
  description: null,
  image_url: null,
  unit_type: 'each',
  location: 'A-12',
  available_packages: 3,
  needed_for_open_repairs: 0,
  reorder_level: 1,
  incoming_packages: 0,
  recommended_order_packages: 0,
  average_unit_cost: '120.00',
  is_archived: false,
  is_placeholder: false,
  preferred_source: null,
  supplier_sources: [],
  repair_sources: [],
  incoming_sources: [],
}

const partDetail = { ...part, recent_receipts: [], recent_movements: [] }

const page$ = (items: unknown[]) => ({ items, total: items.length, skip: 0, limit: 50, has_more: false })

async function install(page: Page, syncedAt: string | null) {
  const failures: string[] = []
  page.on('console', message => { if (message.type() === 'error') failures.push(`console: ${message.text()}`) })
  page.on('pageerror', error => failures.push(`pageerror: ${error.message}`))

  await page.addInitScript(session => {
    // The workspace reads auth from the store's persisted state.
    window.localStorage.setItem('auth-storage', JSON.stringify({
      state: { user: session, token: 'fixture-token', isAuthenticated: true }, version: 0,
    }))
    class FixtureWebSocket extends EventTarget {
      readyState = 1
      onopen: ((event: Event) => void) | null = null
      constructor(_url: string | URL) { super(); queueMicrotask(() => this.onopen?.(new Event('open'))) }
      send() {}
      close() {}
    }
    Object.defineProperty(window, 'WebSocket', { configurable: true, value: FixtureWebSocket })
  }, garageOwnerSession)

  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ status: 200, contentType: 'text/css', body: '' }))
  await page.route('https://fonts.gstatic.com/**', route => route.fulfill({ status: 204, body: '' }))

  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    const json = (body: unknown) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    const p = url.pathname

    if (p.endsWith('/auth/workos/me') || p.endsWith('/auth/me')) return json(garageOwnerSession)
    if (p.endsWith('/auth/me/appearance')) return json({})
    if (p.endsWith('/auth/tenant-branding') || p.endsWith('/admin/garage-profile')) return json({ name: 'Truck Pit Stop Wisconsin', state: 'WI', logo_url: null })
    if (p.endsWith('/messages/unread-summary')) return json({ unread_count: 0 })
    if (p.endsWith('/inventory/sync-status')) return json({ ets_last_synced_at: syncedAt })
    if (p.endsWith('/parts-operations/summary')) return json({ needs_reorder_count: 30, low_stock_count: 30, open_purchase_order_count: 0, total_stock_value: '110865.95' })
    if (p.endsWith('/parts-operations/parts')) return json(page$([part]))
    if (p.includes('/parts-operations/parts/')) return json(partDetail)
    if (p.endsWith('/parts-operations/activity')) return json(page$([]))
    if (p.endsWith('/inventory/category-suggestions')) return json([])
    if (p.endsWith('/suppliers')) return json(page$([]))
    return json({})
  })

  return failures
}

async function openParts(page: Page) {
  await page.goto('/dashboard/garage/inventory')
  await expect(page.getByRole('heading', { name: 'Parts', level: 1 })).toBeVisible({ timeout: 20_000 })
}

test.describe('DB-095 parts sync freshness', () => {
  test('desktop: a fresh sync reads quietly beside the figures it qualifies', async ({ page }) => {
    const failures = await install(page, new Date(Date.now() - 16 * 60 * 60 * 1000).toISOString())
    await page.setViewportSize({ width: 1280, height: 900 })
    await openParts(page)

    const freshness = page.getByTestId('parts-sync-freshness')
    await expect(freshness).toBeVisible()
    await expect(freshness).toHaveText(/SYNCED 16H AGO/)
    await expect(freshness).not.toHaveAttribute('data-stale', 'true')

    // It belongs to the technical line, not floating elsewhere in the header.
    // The class is reused by the part inspector, so scope to the header line.
    const line = page.locator('.db-parts-workbench__header .db-parts-workbench__technical-line')
    await expect(line).toContainText('110,865.95 STOCK VALUE')
    await expect(line).toContainText('SYNCED 16H AGO')

    await page.screenshot({ path: '../output/playwright/db095/desktop-fresh.png', fullPage: false })
    expect(failures, failures.join('\n')).toEqual([])
  })

  test('desktop: a stale sync is visually escalated', async ({ page }) => {
    const failures = await install(page, new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString())
    await page.setViewportSize({ width: 1280, height: 900 })
    await openParts(page)

    const freshness = page.getByTestId('parts-sync-freshness')
    await expect(freshness).toHaveText(/SYNCED 3D AGO/)
    await expect(freshness).toHaveAttribute('data-stale', 'true')

    // Stale must not merely restate the text — it has to change colour, and to
    // a different colour than the healthy state.
    const stale = await freshness.evaluate(el => getComputedStyle(el).color)
    const neighbour = await page.locator('.db-parts-workbench__stat').first().evaluate(el => getComputedStyle(el).color)
    expect(stale).not.toBe(neighbour)

    await page.screenshot({ path: '../output/playwright/db095/desktop-stale.png', fullPage: false })
    expect(failures, failures.join('\n')).toEqual([])
  })

  test('never synced states it plainly', async ({ page }) => {
    const failures = await install(page, null)
    await page.setViewportSize({ width: 1280, height: 900 })
    await openParts(page)

    const freshness = page.getByTestId('parts-sync-freshness')
    await expect(freshness).toHaveText(/NEVER SYNCED/)
    await expect(freshness).toHaveAttribute('data-stale', 'true')
    expect(failures, failures.join('\n')).toEqual([])
  })

  test('compact 390px keeps the sync stat readable and inside the viewport', async ({ page }) => {
    const failures = await install(page, new Date(Date.now() - 16 * 60 * 60 * 1000).toISOString())
    await page.setViewportSize({ width: 390, height: 844 })
    await openParts(page)

    const freshness = page.getByTestId('parts-sync-freshness')
    await expect(freshness).toBeVisible()
    await expect(freshness).toHaveText(/SYNCED 16H AGO/)

    const box = await freshness.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.x).toBeGreaterThanOrEqual(0)
    expect(box!.x + box!.width).toBeLessThanOrEqual(390)

    // No horizontal page scroll introduced by the extra stat.
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(overflow).toBeLessThanOrEqual(0)

    await page.screenshot({ path: '../output/playwright/db095/mobile-390.png', fullPage: false })
    expect(failures, failures.join('\n')).toEqual([])
  })
})
