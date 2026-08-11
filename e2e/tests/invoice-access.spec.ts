import { test, expect } from '@playwright/test'

test.describe('Public invoice access', () => {
  test('invalid token shows error', async ({ page }) => {
    await page.goto('/invoice/invalid-token-abc')

    await expect(
      page.getByRole('heading', { name: /invoice link expired/i })
    ).toBeVisible({ timeout: 10000 })
  })

  test('invalid token reaches the invoice API without browser credentials', async ({ page }) => {
    const resolveResponse = page.waitForResponse((response) =>
      response.url().endsWith('/api/v1/invoice-access/resolve')
      && response.request().method() === 'POST'
    )

    await page.goto('/invoice/some-token')

    const response = await resolveResponse
    const requestHeaders = response.request().headers()
    expect(requestHeaders.authorization).toBeUndefined()
    expect(requestHeaders.cookie).toBeUndefined()
    expect(response.status()).toBe(400)
    const responseBody = await response.json()
    expect(responseBody.detail).toBe('Invalid or expired invoice link.')
  })
})
