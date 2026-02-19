import { test, expect } from '@playwright/test'

test.describe('Public invoice access', () => {
  test('invalid token shows error', async ({ page }) => {
    await page.goto('/invoice/invalid-token-abc')

    // Should show some error state (invalid/expired token)
    await expect(
      page.getByText(/invalid|expired|not found|error/i)
    ).toBeVisible({ timeout: 10000 })
  })

  test('invoice page is publicly accessible (no login required)', async ({ page }) => {
    const response = await page.goto('/invoice/some-token')
    // Page should load (200) — it's a public route
    expect(response?.status()).toBe(200)
  })
})
