import { expect, test, type Page } from '@playwright/test'
import path from 'node:path'

import {
  appearanceCompactContrast,
  appearanceDefaults,
  appearanceLargeLight,
  presentationFixture,
} from '../../frontend/src/test-fixtures/db035/appearance'
import { garageOwnerSession } from '../../frontend/src/test-fixtures/db035/staffSession'
import type { AppearancePreferences } from '../../frontend/src/types/presentation'

const captureRoot = path.resolve(__dirname, '../test-results')
const operationalHrefs = [
  '/dashboard/garage/services',
  '/dashboard/garage/labor-book-time',
  '/dashboard/garage/inventory',
  '/dashboard/garage/purchasing',
]
const secondaryHrefs = ['/dashboard/garage/mechanics', '/dashboard/garage/analytics']

const scenarios: Array<{ width: number; height: number; appearance: AppearancePreferences }> = [
  { width: 1920, height: 1080, appearance: appearanceDefaults },
  { width: 1440, height: 900, appearance: appearanceDefaults },
  { width: 1280, height: 900, appearance: appearanceDefaults },
  { width: 960, height: 900, appearance: appearanceLargeLight },
  { width: 390, height: 844, appearance: appearanceDefaults },
  { width: 320, height: 760, appearance: appearanceCompactContrast },
]

async function installSession(page: Page, appearance: AppearancePreferences) {
  const failures: string[] = []
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

    Object.defineProperty(window, 'WebSocket', { configurable: true, value: FixtureWebSocket })
  })

  const user = {
    ...garageOwnerSession,
    can_access_messaging: true,
    messaging_enabled: true,
    presentation: presentationFixture('new', appearance),
  }

  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/auth/workos/me')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(user) })
      return
    }
    if (url.pathname.endsWith('/auth/workos/session/refresh')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
      return
    }
    if (url.pathname.endsWith('/auth/me/appearance')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(presentationFixture('new', appearance)) })
      return
    }
    if (url.pathname.endsWith('/auth/tenant-branding') || url.pathname.endsWith('/admin/garage-profile')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ name: 'Truck Pit Stop Wisconsin', slug: 'truck-pit-stop-wisconsin', state: 'WI', logo_url: null }),
      })
      return
    }
    if (url.pathname.endsWith('/messages/unread-summary')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ unread_count: 0 }) })
      return
    }
    if (
      url.pathname.endsWith('/mechanics')
      || url.pathname.endsWith('/mechanics/pto-requests/pending')
      || url.pathname.endsWith('/admin/staff')
      || url.pathname.endsWith('/services')
      || url.pathname.endsWith('/services/categories')
      || url.pathname.endsWith('/inventory')
    ) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
      return
    }
    throw new Error(`Unhandled DB-039 fixture route: ${route.request().method()} ${url.pathname}`)
  })

  return failures
}

test('Shop navigation adapts to its workspace while keeping Team then Analytics separated and reachable', async ({ browser }) => {
  for (const scenario of scenarios) {
    const context = await browser.newContext({ viewport: { width: scenario.width, height: scenario.height } })
    const page = await context.newPage()
    const failures = await installSession(page, scenario.appearance)

    await page.goto('/dashboard/garage/mechanics')
    await expect(page.locator('.db-staff-shell')).toHaveAttribute('data-presentation', 'new')

    const navigation = page.locator('nav[aria-label="Shop sections"]:visible')
    const operations = navigation.getByRole('group', { name: 'Shop operations' })
    const secondary = navigation.getByRole('group', { name: 'Shop administration and insights' })
    const operationalLinks = operations.getByRole('link')
    const secondaryLinks = secondary.getByRole('link')
    const allLinks = navigation.getByRole('link')

    await expect(navigation).toHaveCount(1)
    await expect(operationalLinks).toHaveCount(4)
    await expect(secondaryLinks).toHaveCount(2)
    expect(await operationalLinks.evaluateAll(links => links.map(link => link.getAttribute('href')))).toEqual(operationalHrefs)
    expect(await secondaryLinks.evaluateAll(links => links.map(link => link.getAttribute('href')))).toEqual(secondaryHrefs)
    await expect(secondaryLinks.nth(0)).toHaveAttribute('aria-label', 'Team')
    await expect(secondaryLinks.nth(1)).toHaveAttribute('aria-label', 'Analytics')
    await expect(secondaryLinks.nth(0)).toHaveAttribute('aria-current', 'page')

    const navigationBox = await navigation.boundingBox()
    const operationsBox = await operations.boundingBox()
    const secondaryBox = await secondary.boundingBox()
    expect(navigationBox).not.toBeNull()
    expect(operationsBox).not.toBeNull()
    expect(secondaryBox).not.toBeNull()
    const workspaceWidth = await page.locator('.db-my-shop-workspace').evaluate(element => element.clientWidth)
    const usesHorizontalSubnav = workspaceWidth >= 672 && workspaceWidth < 1600
    if (usesHorizontalSubnav) {
      expect(Math.abs(secondaryBox!.y - operationsBox!.y)).toBeLessThanOrEqual(2)
      expect(secondaryBox!.x).toBeGreaterThanOrEqual(operationsBox!.x + operationsBox!.width + 8)
    } else {
      expect(secondaryBox!.y).toBeGreaterThanOrEqual(operationsBox!.y + operationsBox!.height + 8)
    }
    expect(secondaryBox!.x).toBeGreaterThanOrEqual(navigationBox!.x - 1)
    expect(secondaryBox!.x + secondaryBox!.width).toBeLessThanOrEqual(navigationBox!.x + navigationBox!.width + 1)
    expect(secondaryBox!.y + secondaryBox!.height).toBeLessThanOrEqual(navigationBox!.y + navigationBox!.height + 1)

    const heading = navigation.getByRole('heading', { name: 'Shop' })
    const shortLabel = navigation.locator('.db-my-shop-nav-label-short').first()
    const fullLabel = navigation.locator('.db-my-shop-nav-label-full').first()
    if (workspaceWidth >= 1600) {
      await expect(heading).toBeVisible()
      await expect(shortLabel).toBeHidden()
      await expect(fullLabel).toBeVisible()
      expect(Math.round(navigationBox!.width)).toBe(208)
    } else {
      await expect(heading).toBeHidden()
      await expect(shortLabel).toBeVisible()
      await expect(fullLabel).toBeHidden()
    }

    for (let index = 0; index < await allLinks.count(); index += 1) {
      const link = allLinks.nth(index)
      const box = await link.boundingBox()
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(44)
      expect(box?.width ?? 0).toBeGreaterThanOrEqual(44)
      await expect(link.locator('svg').first()).toBeVisible()
    }

    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
    await expect.poll(() => navigation.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)

    const mobileShellNavigation = page.locator('.db-mobile-nav:visible')
    if (await mobileShellNavigation.count()) {
      const mobileShellBox = await mobileShellNavigation.boundingBox()
      expect(secondaryBox!.y + secondaryBox!.height).toBeLessThanOrEqual(mobileShellBox!.y)
    }

    if (scenario.width === 1440) {
      await operationalLinks.nth(0).focus()
      for (let index = 1; index < 6; index += 1) {
        await page.keyboard.press('Tab')
        await expect(allLinks.nth(index)).toBeFocused()
      }
      await operationalLinks.nth(0).focus()
      await page.keyboard.press('Enter')
      await expect(page).toHaveURL(/\/dashboard\/garage\/services$/)
      await expect(operationalLinks.nth(0)).toHaveAttribute('aria-current', 'page')
    }

    await expect(navigation.locator('a[aria-current="page"]')).toHaveCount(1)
    await expect.poll(async () => allLinks.evaluateAll(links =>
      links.every(link => Number.parseFloat(getComputedStyle(link).opacity) === 1),
    )).toBe(true)
    await page.waitForTimeout(250)

    await page.screenshot({
      path: path.join(captureRoot, `db039-shop-menu-${scenario.width}.png`),
      fullPage: true,
    })
    expect(failures).toEqual([])
    await context.close()
  }
})
