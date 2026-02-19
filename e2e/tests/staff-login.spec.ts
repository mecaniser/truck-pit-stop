import { test, expect } from '@playwright/test'

test.describe('Staff login → dashboard', () => {
  test('shows login form', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByRole('heading', { name: /sign in/i })).toBeVisible()
    await expect(page.locator('#email')).toBeVisible()
    await expect(page.locator('#password')).toBeVisible()
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible()
  })

  test('rejects invalid credentials', async ({ page }) => {
    await page.goto('/login')
    await page.locator('#email').fill('nobody@example.com')
    await page.locator('#password').fill('Wrong@Pass1')
    await page.getByRole('button', { name: /sign in/i }).click()

    await expect(page.getByText(/incorrect|invalid|not found/i)).toBeVisible({
      timeout: 5000,
    })
    // Should stay on login page
    expect(page.url()).toContain('/login')
  })

  test('redirects unauthenticated users to login', async ({ page }) => {
    await page.goto('/dashboard')
    await page.waitForURL('**/login**', { timeout: 5000 })
    expect(page.url()).toContain('/login')
  })
})
