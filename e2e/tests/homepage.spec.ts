import { test, expect } from '@playwright/test'

test.describe('Public repair-shop homepage', () => {
  test('renders the illustrative repair proof with external routed evidence', async ({ page }) => {
    await page.route('**/api/v1/auth/landing-partners', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    })
    await page.route('**/api/v1/auth/platform-contact', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ support_name: 'Support', support_email: 'support@example.com', support_phone: null }),
      })
    })

    await page.setViewportSize({ width: 1366, height: 1000 })
    await page.goto(process.env.DB028_BASE_URL || process.env.DB027_BASE_URL || '/')

    await expect(page.getByText('Illustrative sample')).toBeVisible()
    await expect(page.getByText('Fictional repair-order data')).toBeVisible()
    await expect(page.getByText('RO-2025-0417')).toBeVisible()
    await expect(page.getByText('412,358 mi')).toBeVisible()
    await expect(page.getByText('$284.20')).toBeVisible()
    await expect(page.getByText('$4,494.62').first()).toBeVisible()
    await expect(page.locator('.landing-workflow-connectors path')).toHaveCount(3)
    await expect(page.locator('.landing-connector-node')).toHaveCount(6)
    await expect.poll(async () => page.locator('.landing-context-sheet--approval').evaluate((element) => {
      return new DOMMatrixReadOnly(getComputedStyle(element).transform).a
    })).toBeGreaterThan(1.01)

    const geometry = await page.evaluate(() => {
      const workspace = document.querySelector<HTMLElement>('.landing-workspace-frame')!.getBoundingClientRect()
      const approval = document.querySelector<HTMLElement>('.landing-context-sheet--approval')!.getBoundingClientRect()
      const invoice = document.querySelector<HTMLElement>('.landing-context-sheet--invoice')!.getBoundingClientRect()
      const history = document.querySelector<HTMLElement>('.landing-context-sheet--history')!.getBoundingClientRect()
      return {
        approvalOutside: approval.right <= workspace.left,
        invoiceOutside: invoice.left >= workspace.right,
        historyOutside: history.left >= workspace.right,
        completeInFirstViewport: Math.max(workspace.bottom, approval.bottom, invoice.bottom, history.bottom) <= window.innerHeight,
      }
    })

    expect(geometry).toEqual({
      approvalOutside: true,
      invoiceOutside: true,
      historyOutside: true,
      completeInFirstViewport: true,
    })

    await page.getByRole('button', { name: 'Payment & history' }).click()
    await expect(page.locator('.landing-context-sheet--history')).toHaveClass(/is-active/)
    await expect(page.locator('.landing-connector--history')).toHaveClass(/is-active/)
    await expect(page.locator('.landing-context-sheet--history')).toHaveCSS('border-top-width', '1px')
    await expect.poll(async () => page.locator('.landing-context-sheet--history').evaluate((element) => {
      return new DOMMatrixReadOnly(getComputedStyle(element).transform).a
    })).toBeGreaterThan(1.01)
    await expect.poll(async () => page.evaluate(() => {
      const workspace = document.querySelector<HTMLElement>('.landing-workspace-frame')!.getBoundingClientRect()
      const history = document.querySelector<HTMLElement>('.landing-context-sheet--history')!.getBoundingClientRect()
      return history.left >= workspace.right
    })).toBe(true)
    await expect(page.getByText('ACH •••• 5521').first()).toBeVisible()

    for (const width of [1440, 1366, 1280, 1120, 960]) {
      await page.setViewportSize({ width, height: 900 })
      const layout = await page.evaluate(() => {
        const targetSelector = [
          '.landing-brand-link',
          '.landing-sign-in',
          '.landing-nav-links a',
          '.landing-nav-cta',
          '.landing-primary-cta',
          '.landing-stage-tabs button',
          '.landing-partner-state button',
          '.landing-footer a',
        ].join(',')
        const undersized = [...document.querySelectorAll<HTMLElement>(targetSelector)]
          .filter((element) => element.offsetParent !== null)
          .map((element) => {
            const bounds = element.getBoundingClientRect()
            return { label: element.textContent?.trim(), width: bounds.width, height: bounds.height }
          })
          .filter((target) => target.width < 44 || target.height < 44)

        return {
          viewportWidth: document.documentElement.clientWidth,
          scrollWidth: document.documentElement.scrollWidth,
          undersized,
        }
      })

      expect(layout.scrollWidth).toBe(layout.viewportWidth)
      expect(layout.undersized).toEqual([])
    }
  })

  test('keeps compact mobile navigation and workflow controls tappable', async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem('theme-font-size', 'compact')
    })
    await page.route('**/api/v1/auth/landing-partners', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    })
    await page.route('**/api/v1/auth/platform-contact', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ support_name: 'Support', support_email: 'support@example.com', support_phone: null }),
      })
    })

    await page.setViewportSize({ width: 320, height: 760 })
    await page.goto(process.env.DB028_BASE_URL || process.env.DB027_BASE_URL || '/')
    await expect(page.getByRole('heading', { name: 'Every repair, moving in one clear flow.' })).toBeVisible()

    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 844 })
      const layout = await page.evaluate(() => {
        const targetSelector = [
          '.landing-brand-link',
          '.landing-sign-in',
          '.landing-primary-cta',
          '.landing-stage-tabs button',
          '.landing-partner-state button',
          '.landing-footer a',
        ].join(',')
        const undersized = [...document.querySelectorAll<HTMLElement>(targetSelector)]
          .filter((element) => element.offsetParent !== null)
          .map((element) => {
            const bounds = element.getBoundingClientRect()
            return { label: element.textContent?.trim(), width: bounds.width, height: bounds.height }
          })
          .filter((target) => target.width < 44 || target.height < 44)

        return {
          viewportWidth: document.documentElement.clientWidth,
          scrollWidth: document.documentElement.scrollWidth,
          undersized,
        }
      })

      expect(layout.scrollWidth).toBe(layout.viewportWidth)
      expect(layout.undersized).toEqual([])
    }

    await page.getByRole('button', { name: 'Invoice' }).click()
    await expect(page.getByRole('button', { name: 'Invoice' })).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByRole('heading', { name: 'Carry completed work into the invoice.' })).toBeVisible()

    await expect(page.locator('link[rel="icon"][type="image/svg+xml"]')).toHaveAttribute('href', '/dieselbridge-mark.svg')
    await expect(page.locator('link[type="image/png"]')).toHaveCount(0)
  })
})
