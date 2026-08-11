import { expect, test, type Page, type Route } from '@playwright/test'

type DecisionMode = 'approve' | 'decline' | 'conflict' | 'forbidden'

const quote = (overrides: Record<string, unknown> = {}) => ({
  id: 'quote-db003',
  tenant_id: 'tenant-db003',
  repair_order_id: 'order-db003',
  quote_number: 'Q-DB003-2',
  total_amount: '1450.00',
  notes: null,
  expires_at: null,
  is_approved: false,
  is_declined: false,
  decline_notes: null,
  sent_to_customer: true,
  sent_at: '2026-08-11T14:00:00Z',
  created_at: '2026-08-11T13:55:00Z',
  updated_at: '2026-08-11T14:00:00Z',
  revision: 2,
  authorization_type: 'additional_work',
  previously_authorized_amount: '1000.00',
  delta_amount: '450.00',
  ...overrides,
})

const detail = (quoteOverrides: Record<string, unknown> = {}) => ({
  quote: quote(quoteOverrides),
  order_number: 'RO-DB003',
  order_description: 'Additional electrical diagnosis',
  vehicle_year: 2022,
  vehicle_make: 'Freightliner',
  vehicle_model: 'Cascadia',
  vehicle_vin: 'DB003MASKED123456',
  customer_first_name: 'Casey',
  services: [{ name: 'Electrical diagnosis', base_price: '450.00' }],
  parts: [],
  labor_total: '1450.00',
  parts_total: '0.00',
  labor_discount_amount: '0.00',
  order_discount_amount: '0.00',
  shop_supplies_amount: '0.00',
  service_fee_amount: '0.00',
  tax_amount: '0.00',
  estimated_card_total: '1450.00',
  estimated_zelle_total: '1450.00',
  zelle_savings_amount: '0.00',
  shop_name: 'DieselBridge Test Shop',
  shop_logo_url: null,
  shop_phone: null,
  shop_email: null,
  has_portal_account: true,
  requires_password_setup: false,
  revision: 2,
  authorization_type: 'additional_work',
  previously_authorized_amount: '1000.00',
  additional_amount: '450.00',
  resulting_authorized_amount: '1450.00',
})

async function fulfillJson(route: Route, status: number, body: unknown) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

async function mockAuthorization(page: Page, token: string, mode: DecisionMode) {
  let decisionCount = 0
  let decided: 'approved' | 'declined' | null = null
  let decisionHeaders: Record<string, string> = {}

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const pathname = new URL(request.url()).pathname

    if (pathname.endsWith('/auth/platform-contact')) {
      await fulfillJson(route, 200, {
        support_name: 'DieselBridge Support',
        support_email: null,
        support_phone: null,
      })
      return
    }

    const tokenPath = `/api/v1/quotes/token/${token}`
    if (pathname === tokenPath && request.method() === 'GET') {
      await fulfillJson(route, 200, detail(
        decided === 'approved'
          ? { is_approved: true }
          : decided === 'declined'
            ? { is_declined: true, decline_notes: 'Please defer this work.' }
            : {},
      ))
      return
    }

    const isDecision = pathname === `${tokenPath}/approve` || pathname === `${tokenPath}/decline`
    if (isDecision && request.method() === 'POST') {
      decisionCount += 1
      decisionHeaders = request.headers()
      if (mode === 'conflict') {
        await fulfillJson(route, 409, { detail: 'Authorization revision changed.' })
        return
      }
      if (mode === 'forbidden') {
        await fulfillJson(route, 403, { detail: 'This customer cannot decide this authorization.' })
        return
      }
      decided = mode === 'decline' ? 'declined' : 'approved'
      await fulfillJson(route, 200, quote({
        is_approved: decided === 'approved',
        is_declined: decided === 'declined',
      }))
      return
    }

    await fulfillJson(route, 404, { detail: 'Not found in DB-003 browser fixture.' })
  })

  return {
    get decisionCount() { return decisionCount },
    get decisionHeaders() { return decisionHeaders },
  }
}

test('mobile customer authorizes only the additional-work delta through the exact token', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const requests = await mockAuthorization(page, 'db003-approve', 'approve')

  await page.goto('/quote/db003-approve')
  await expect(page.getByText('Additional Work Authorization', { exact: true })).toBeVisible()
  await expect(page.getByText('$1,000.00', { exact: true })).toBeVisible()
  await expect(page.getByText('+$450.00', { exact: true })).toBeVisible()
  await expect(page.getByText('$1,450.00', { exact: true }).first()).toBeVisible()
  await expect(page.locator('body')).toHaveJSProperty('scrollWidth', 390)

  const authorize = page.getByRole('button', { name: 'Authorize Additional Work' })
  const box = await authorize.boundingBox()
  expect(box?.height).toBeGreaterThanOrEqual(44)
  await authorize.click()

  await expect(page.getByRole('heading', { name: 'Additional Work Approved!' })).toBeVisible()
  expect(requests.decisionCount).toBe(1)
  expect(requests.decisionHeaders.authorization).toBeUndefined()
})

test('customer decline preserves the earlier approval and cannot be reversed in place', async ({ page }) => {
  const requests = await mockAuthorization(page, 'db003-decline', 'decline')
  await page.goto('/quote/db003-decline')

  await page.getByRole('button', { name: 'Decline' }).click()
  await page.getByPlaceholder(/price too high/i).fill('Please defer this work.')
  await page.getByRole('button', { name: 'Confirm Decline' }).click()

  await expect(page.getByRole('heading', { name: 'Additional Work Declined' })).toBeVisible()
  await expect(page.getByText(/earlier approved amount remains valid/i)).toBeVisible()
  await expect(page.getByRole('button', { name: /changed my mind/i })).toHaveCount(0)
  expect(requests.decisionCount).toBe(1)
})

test('409 refreshes the latest revision and never retries the decision blindly', async ({ page }) => {
  const requests = await mockAuthorization(page, 'db003-conflict', 'conflict')
  await page.goto('/quote/db003-conflict')

  await page.getByRole('button', { name: 'Authorize Additional Work' }).click()
  await expect(page.getByText(/already decided or replaced.*refreshed/i)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Authorize Additional Work' })).toBeVisible()
  await page.waitForTimeout(250)
  expect(requests.decisionCount).toBe(1)
})

test('403 is surfaced without retrying or implying a staff decision', async ({ page }) => {
  const requests = await mockAuthorization(page, 'db003-forbidden', 'forbidden')
  await page.goto('/quote/db003-forbidden')

  await page.getByRole('button', { name: 'Authorize Additional Work' }).click()
  await expect(page.getByText('This customer cannot decide this authorization.')).toBeVisible()
  await page.waitForTimeout(250)
  expect(requests.decisionCount).toBe(1)
})
