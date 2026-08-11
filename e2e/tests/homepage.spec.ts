import { test, expect } from '@playwright/test'

test.describe('Public repair-shop homepage', () => {
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
    await page.goto(process.env.DB027_BASE_URL || '/')
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
