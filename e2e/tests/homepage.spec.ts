import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const homepageUrl = process.env.DB029_BASE_URL || process.env.DB028_BASE_URL || process.env.DB027_BASE_URL || '/'
const knownOrbBlockedFontStylesheet = 'https://cdn.jsdelivr.net/npm/geist@1.3.1/dist/fonts/geist-sans/style.min.css'

interface RuntimeFailures {
  consoleErrors: string[]
  pageErrors: string[]
  requestFailures: string[]
}

const runtimeFailuresByPage = new WeakMap<Page, RuntimeFailures>()

function observeRuntimeFailures(page: Page): RuntimeFailures {
  const failures: RuntimeFailures = { consoleErrors: [], pageErrors: [], requestFailures: [] }
  page.on('console', (message) => {
    if (message.type() === 'error') failures.consoleErrors.push(message.text())
  })
  page.on('pageerror', (error) => failures.pageErrors.push(error.stack || error.message))
  page.on('requestfailed', (request) => {
    const errorText = request.failure()?.errorText || 'unknown failure'
    // Chromium's local harness blocks this exact external font stylesheet via ORB.
    if (request.url() === knownOrbBlockedFontStylesheet && errorText === 'net::ERR_BLOCKED_BY_ORB') return
    failures.requestFailures.push(
      `${request.method()} ${request.url()}: ${errorText}`,
    )
  })
  return failures
}

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
  test.beforeEach(({ page }) => {
    runtimeFailuresByPage.set(page, observeRuntimeFailures(page))
  })

  test.afterEach(({ page }) => {
    const failures = runtimeFailuresByPage.get(page)
    expect(failures?.consoleErrors ?? [], 'browser console errors').toEqual([])
    expect(failures?.pageErrors ?? [], 'uncaught page errors').toEqual([])
    expect(failures?.requestFailures ?? [], 'failed browser requests').toEqual([])
  })

  test('drives the header wordmark over the bridge once and respects reduced motion', async ({ page }) => {
    await stubPublicHomepage(page)
    await page.setViewportSize({ width: 1366, height: 900 })
    await page.goto(homepageUrl)

    const headerWordmark = page.locator('.landing-brand-link .landing-wordmark--animated')
    const name = headerWordmark.locator('.landing-wordmark__name')
    const letters = headerWordmark.locator('.landing-wordmark__letter')
    const footerWordmark = page.locator('.landing-footer .landing-wordmark')

    await expect(headerWordmark).toHaveAccessibleName('Diesel Bridge Network')
    await expect(footerWordmark).not.toHaveClass(/landing-wordmark--animated/)
    await expect(name).toHaveCSS('animation-name', 'none')
    await expect(letters).toHaveCount(12)
    await expect(letters.first()).toHaveCSS('animation-name', 'landing-wordmark-letter-wave')
    await expect(letters.first()).toHaveCSS('animation-duration', '0.62s')
    await expect(letters.last()).toHaveCSS('animation-delay', '0.308s')

    await letters.evaluateAll((elements) => {
      elements.forEach((element) => {
        element.getAnimations().forEach((animation) => {
          animation.pause()
          animation.currentTime = 360
        })
      })
    })
    const crossingFrame = await headerWordmark.evaluate((element) => {
      const movingLetters = [...element.querySelectorAll<HTMLElement>('.landing-wordmark__letter')]
      return {
        letterTransforms: movingLetters.map((letter) => getComputedStyle(letter).transform),
        letterOpacities: movingLetters.map((letter) => getComputedStyle(letter).opacity),
      }
    })
    expect(new Set(crossingFrame.letterTransforms).size).toBeGreaterThan(1)
    expect(crossingFrame.letterOpacities.some((opacity) => Number(opacity) > 0)).toBe(true)
    await page.screenshot({ path: 'test-results/db032-wordmark-crossing-1366.png' })

    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.reload()
    await expect(name).toHaveCSS('animation-name', 'landing-wordmark-fade')
    await expect(name).toHaveCSS('animation-duration', '0.12s')
    await expect(letters.first()).toHaveCSS('animation-name', 'none')

    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 })
      const geometry = await page.evaluate(() => ({
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
      }))
      expect(geometry.scrollWidth, `wordmark overflow at ${width}px`).toBe(geometry.clientWidth)
    }
  })

  test('operates five source-grounded product previews without side effects', async ({ page }) => {
    await stubPublicHomepage(page)
    const previewRequests: Array<{ method: string; url: string }> = []
    page.on('request', (request) => {
      if (request.url().includes('/api/v1/')) previewRequests.push({ method: request.method(), url: request.url() })
    })
    await page.setViewportSize({ width: 1366, height: 1000 })
    await page.goto(homepageUrl)

    await expect(page.getByText(/illustrative|fictional/i)).toHaveCount(0)
    await expect(page.getByText('One repair order. Five connected outcomes.')).toHaveCount(0)
    const ctas = page.getByRole('link', { name: 'Bring DieselBridge to my shop' })
    await expect(ctas).toHaveCount(2)
    await expect(ctas.first()).toHaveAttribute('href', '/enroll')

    const moduleLabels = ['Repair Orders', 'Customers', 'Shop Work', 'Invoices', 'Vehicle History']
    await expect(page.getByRole('tablist', { name: 'Product areas' }).getByRole('tab')).toHaveText(moduleLabels)
    await expect(page.getByText('Work Requested')).toBeVisible()
    await expect(page.getByText('Work & Labor')).toBeVisible()
    await expect(page.getByText('$4,494.62').first()).toBeVisible()
    await expect(page.locator('[data-route-valid="module"]')).toHaveCount(1)
    await expect(page.locator('[data-route-valid="event"]')).toHaveCount(1)

    await page.getByRole('tab', { name: 'Customers' }).click()
    await expect(page.getByRole('heading', { name: 'Customers' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'DOT / MC' })).toBeVisible()
    const overviewTab = page.getByRole('tab', { name: 'Overview' })
    const historyTab = page.getByRole('tab', { name: 'History', exact: true })
    await expect(overviewTab).toHaveAttribute('tabindex', '0')
    await expect(historyTab).toHaveAttribute('tabindex', '-1')
    await overviewTab.focus()
    await overviewTab.press('ArrowRight')
    await expect(historyTab).toBeFocused()
    await expect(historyTab).toHaveAttribute('aria-selected', 'true')
    await historyTab.press('Home')
    await expect(overviewTab).toBeFocused()
    await expect(overviewTab).toHaveAttribute('aria-selected', 'true')
    await page.getByRole('button', { name: 'Riverbend Freight' }).click()
    await historyTab.focus()
    await historyTab.press('Enter')
    await expect(historyTab).toBeFocused()
    await expect(historyTab).toHaveAttribute('tabindex', '0')
    await expect(page.getByText('Invoice awaiting payment · INV-2025-0412').first()).toBeVisible()

    await page.getByRole('tab', { name: 'Shop Work' }).click()
    await expect(page.getByText('Shop Cockpit').first()).toBeVisible()
    await expect(page.getByText('Needs Action')).toBeVisible()
    await expect(page.getByText('Ready to Close')).toBeVisible()
    const queueTab = page.getByRole('tab', { name: 'Queue' })
    const activityTab = page.getByRole('tab', { name: 'Activity' })
    await queueTab.focus()
    await queueTab.press('End')
    await expect(activityTab).toBeFocused()
    await expect(activityTab).toHaveAttribute('aria-selected', 'true')
    await activityTab.press('Home')
    await expect(queueTab).toBeFocused()
    await activityTab.focus()
    await activityTab.press('Space')
    await expect(activityTab).toBeFocused()
    await expect(activityTab).toHaveAttribute('tabindex', '0')

    await page.getByRole('tab', { name: 'Invoices' }).click()
    await expect(page.getByText('Pending Zelle confirmation').first()).toBeVisible()
    await expect(page.getByText('Awaiting payment').first()).toBeVisible()
    const invoiceDisclosure = page.getByRole('button', { name: /Invoice INV-2025-0417/i })
    await expect(invoiceDisclosure).toHaveAttribute('aria-expanded', 'true')
    await expect(invoiceDisclosure).toHaveAttribute('aria-controls', 'repair-preview-invoice-0417-details')
    await expect(page.locator('#repair-preview-invoice-0417-details')).toBeVisible()
    const invoiceControlIds = await page.locator('.mini-invoice-record .preview-evidence-control').evaluateAll((buttons) =>
      buttons.map((button) => button.getAttribute('aria-controls')),
    )
    expect(new Set(invoiceControlIds).size).toBe(invoiceControlIds.length)
    for (const controlId of invoiceControlIds) {
      expect(controlId).not.toBeNull()
      await expect(page.locator(`#${controlId}`)).toHaveCount(1)
    }
    await invoiceDisclosure.click()
    await expect(invoiceDisclosure).toHaveAttribute('aria-expanded', 'false')
    await expect(page.locator('#repair-preview-invoice-0417-details')).toBeHidden()
    await invoiceDisclosure.click()
    await expect(invoiceDisclosure).toHaveAttribute('aria-expanded', 'true')
    await expect(page.locator('[data-route-valid="event"]')).toHaveCount(1)

    await page.getByRole('tab', { name: 'Vehicle History' }).click()
    await expect(page.getByText('Owner').first()).toBeVisible()
    await expect(page.getByText('Key Details')).toBeVisible()
    await expect(page.getByText('…1234').first()).toBeVisible()
    await expect(page.getByText('Repair History', { exact: true })).toBeVisible()
    await expect(page.locator('[data-sheet-kind="event"]')).toHaveCount(0)
    await expect(page.locator('[data-route-valid="event"]')).toHaveCount(0)
    const vehicleRepairDisclosure = page.getByRole('button', { name: /RO-2025-0417/i })
    await expect(vehicleRepairDisclosure).toHaveAttribute('aria-expanded', 'false')
    await expect(vehicleRepairDisclosure).toHaveAttribute('aria-controls', 'repair-preview-repair-0417-details')
    await expect(page.locator('#repair-preview-repair-0417-details')).toHaveCount(1)
    await expect(page.locator('#repair-preview-repair-0417-details')).toBeHidden()
    await vehicleRepairDisclosure.click()
    await expect(vehicleRepairDisclosure).toHaveAttribute('aria-expanded', 'true')
    await expect(page.locator('#repair-preview-repair-0417-details')).toBeVisible()
    await expect(page.locator('[data-sheet-kind="event"]')).toHaveCount(1)

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

    const widths = [1440, 1366, 1280, 1120, 960, 390, 320]
    for (const [index, width] of widths.entries()) {
      await page.setViewportSize({ width, height: width <= 390 ? 844 : 1000 })
      await page.getByRole('tab', { name: index % 2 === 0 ? 'Repair Orders' : 'Customers' }).click()
      const layout = await layoutEvidence(page)
      expect(layout.scrollWidth, `body overflow at ${width}px`).toBe(layout.clientWidth)
      expect(layout.undersized, `touch targets at ${width}px`).toEqual([])
      if (width < 1200) {
        expect(layout.routeCount, `compact routes at ${width}px`).toBe(0)
        expect(layout.readingOrder[0]).toBeLessThanOrEqual(layout.readingOrder[1])
        expect(layout.readingOrder[1]).toBeLessThanOrEqual(layout.readingOrder[2])
      }
      if (width === 390) {
        const mobileSheetMetadata = await page.locator('.repair-preview__sheet').evaluateAll((sheets) =>
          sheets.map((sheet) => ({
            kind: sheet.getAttribute('data-sheet-kind'),
            sizes: [...sheet.querySelectorAll<HTMLElement>('.repair-preview__eyebrow, p, dt, dd, .repair-preview__sheet-status')]
              .map((element) => Number.parseFloat(getComputedStyle(element).fontSize)),
          })),
        )
        expect(mobileSheetMetadata.map(({ kind }) => kind)).toEqual(['context', 'event'])
        expect(
          mobileSheetMetadata.flatMap(({ kind, sizes }) =>
            sizes.filter((size) => size < 11).map((size) => ({ kind, size })),
          ),
          'mobile sheet supporting metadata must stay at or above 11px',
        ).toEqual([])
        expect(layout.scrollWidth, 'mobile typography must not introduce page overflow').toBe(layout.clientWidth)
      }
      if (width <= 390) expect(layout.moduleRows).toBeGreaterThan(1)
      if (width === 1280 || width === 390 || width === 320) {
        await page.screenshot({ path: `test-results/db029-homepage-${width}.png`, fullPage: true })
      }
    }

    await page.setViewportSize({ width: 1120, height: 1000 })
    for (let iteration = 0; iteration < 5; iteration += 1) {
      await page.getByRole('tab', { name: 'Invoices' }).click()
      await page.getByRole('tab', { name: 'Repair Orders' }).click()
    }
    await page.waitForTimeout(800)
    const settledModules = await page.getByRole('tablist', { name: 'Product areas' }).getByRole('tab').evaluateAll((tabs) =>
      tabs.map((tab) => ({
        label: tab.textContent?.trim(),
        height: tab.getBoundingClientRect().height,
        transform: getComputedStyle(tab).transform,
      })),
    )
    expect(settledModules.filter(({ height }) => height < 44), 'rapid retarget module heights').toEqual([])
    expect(settledModules.filter(({ transform }) => transform !== 'none'), 'rapid retarget module transforms').toEqual([])
    await expect(page.getByRole('tab', { name: 'Repair Orders' })).toHaveAttribute('aria-selected', 'true')
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
