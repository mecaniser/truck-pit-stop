import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const homepageUrl = process.env.DB029_BASE_URL || process.env.DB028_BASE_URL || process.env.DB027_BASE_URL || '/'

async function stubPublicHomepage(page: Page) {
  await page.route('**/api/v1/auth/landing-partners', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/api/v1/auth/platform-contact', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ support_name: 'Support', support_email: 'support@example.com', support_phone: null }),
  }))
}

async function layoutEvidence(page: Page) {
  return page.evaluate(() => {
    const visibleControls = [...document.querySelectorAll<HTMLElement>('.repair-preview button, .landing-primary-cta')]
      .filter((element) => element.offsetParent !== null)
    const undersized = visibleControls.map((element) => {
      const bounds = element.getBoundingClientRect()
      return { label: element.textContent?.trim(), width: bounds.width, height: bounds.height }
    }).filter((target) => target.width < 44 || target.height < 44)
    const workspace = document.querySelector<HTMLElement>('.repair-preview__workspace')?.getBoundingClientRect()
    const context = document.querySelector<HTMLElement>('[data-sheet-kind="context"]')?.getBoundingClientRect()
    const event = document.querySelector<HTMLElement>('[data-sheet-kind="event"]')?.getBoundingClientRect()
    return {
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      undersized,
      routeCount: document.querySelectorAll('.repair-preview__routes path').length,
      readingOrder: workspace && context && event ? [workspace.top, context.top, event.top] : [],
      moduleRows: new Set([...document.querySelectorAll<HTMLElement>('.repair-preview__module-list > button')].map((button) => Math.round(button.getBoundingClientRect().top))).size,
    }
  })
}

test.describe('Public repair-shop homepage', () => {
  test('operates five source-grounded product previews without side effects', async ({ page }) => {
    await stubPublicHomepage(page)
    const previewRequests: Array<{ method: string; url: string }> = []
    page.on('request', (request) => {
      if (request.url().includes('/api/v1/')) previewRequests.push({ method: request.method(), url: request.url() })
    })
    await page.setViewportSize({ width: 1366, height: 1000 })
    await page.goto(homepageUrl)

    await expect(page.getByText(/illustrative|fictional/i)).toHaveCount(0)
    const ctas = page.getByRole('link', { name: 'Bring DieselBridge to my shop' })
    await expect(ctas).toHaveCount(2)
    await expect(ctas.first()).toHaveAttribute('href', '/enroll')

    const moduleLabels = ['Repair Orders', 'Customers', 'Shop Work', 'Invoices', 'Vehicle History']
    await expect(page.getByRole('tablist', { name: 'Product areas' }).getByRole('tab')).toHaveText(moduleLabels)
    await expect(page.getByText('Work Requested')).toBeVisible()
    await expect(page.getByText('Work & Labor')).toBeVisible()
    await expect(page.getByText('$4,494.62').first()).toBeVisible()

    await page.getByRole('tab', { name: 'Customers' }).click()
    await expect(page.getByRole('heading', { name: 'Customers' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'DOT / MC' })).toBeVisible()
    await page.getByRole('button', { name: 'Riverbend Freight' }).click()
    await page.getByRole('tab', { name: 'History', exact: true }).click()
    await expect(page.getByText('Invoice awaiting payment · INV-2025-0412').first()).toBeVisible()

    await page.getByRole('tab', { name: 'Shop Work' }).click()
    await expect(page.getByText('Shop Cockpit').first()).toBeVisible()
    await expect(page.getByText('Needs Action')).toBeVisible()
    await expect(page.getByText('Ready to Close')).toBeVisible()

    await page.getByRole('tab', { name: 'Invoices' }).click()
    await expect(page.getByText('Pending Zelle confirmation').first()).toBeVisible()
    await expect(page.getByText('Awaiting payment').first()).toBeVisible()

    await page.getByRole('tab', { name: 'Vehicle History' }).click()
    await expect(page.getByText('Owner').first()).toBeVisible()
    await expect(page.getByText('Key Details')).toBeVisible()
    await expect(page.getByText('…1234').first()).toBeVisible()
    await expect(page.getByText('Repair History', { exact: true })).toBeVisible()

    await page.getByRole('tab', { name: 'Customers' }).click()
    await expect(page.getByRole('tab', { name: 'History', exact: true })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByRole('heading', { name: 'Riverbend Freight' }).first()).toBeVisible()

    const unexpected = previewRequests.filter(({ method, url }) =>
      method !== 'GET' || (!url.includes('/auth/landing-partners') && !url.includes('/auth/platform-contact')),
    )
    expect(unexpected).toEqual([])
    await page.screenshot({ path: 'test-results/db029-homepage-customers-1366.png', fullPage: true })
  })

  test('adapts without overflow, undersized targets, or compact connectors', async ({ page }) => {
    await stubPublicHomepage(page)
    await page.goto(homepageUrl)

    for (const width of [1440, 1366, 1280, 1120, 960, 390, 320]) {
      await page.setViewportSize({ width, height: width <= 390 ? 844 : 1000 })
      await page.getByRole('tab', { name: width % 2 ? 'Customers' : 'Repair Orders' }).click()
      const layout = await layoutEvidence(page)
      expect(layout.scrollWidth, `body overflow at ${width}px`).toBe(layout.clientWidth)
      expect(layout.undersized, `touch targets at ${width}px`).toEqual([])
      if (width < 1200) {
        expect(layout.routeCount, `compact routes at ${width}px`).toBe(0)
        expect(layout.readingOrder[0]).toBeLessThanOrEqual(layout.readingOrder[1])
        expect(layout.readingOrder[1]).toBeLessThanOrEqual(layout.readingOrder[2])
      }
      if (width <= 390) expect(layout.moduleRows).toBeGreaterThan(1)
      if (width === 1280 || width === 390 || width === 320) {
        await page.screenshot({ path: `test-results/db029-homepage-${width}.png`, fullPage: true })
      }
    }
  })

  test('keeps reduced-motion and touch interaction fully functional', async ({ page }) => {
    await stubPublicHomepage(page)
    await page.emulateMedia({ reducedMotion: 'reduce', forcedColors: 'active' })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto(homepageUrl)

    await page.getByRole('tab', { name: 'Invoices' }).tap()
    await expect(page.getByRole('heading', { name: 'Invoices' })).toBeVisible()
    await expect(page.locator('.repair-preview__routes path')).toHaveCount(0)
    await expect(page.getByRole('button', { name: /Invoice INV-2025-0419/i })).toBeVisible()
    await page.screenshot({ path: 'test-results/db029-homepage-forced-colors-390.png', fullPage: true })

    await expect(page.locator('link[rel="icon"][type="image/svg+xml"]')).toHaveAttribute('href', '/dieselbridge-mark.svg')
    await expect(page.locator('link[type="image/png"]')).toHaveCount(0)
  })
})
