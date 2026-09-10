import { expect, test, type Page } from '@playwright/test'

import { presentationFixture } from '../../frontend/src/test-fixtures/db035/appearance'
import { garageOwnerSession } from '../../frontend/src/test-fixtures/db035/staffSession'
import {
  DB048_PROVIDER_READINESS,
  DB048_SETTLEMENT_FIXTURES,
} from '../../frontend/src/test-fixtures/db048/settlements'

const token = 'db048-guest-token'
const invoice = {
  invoice_id: 'invoice-834',
  invoice_number: 'INV-0048',
  order_number: 'RO-0048',
  customer_name: 'North Star Logistics',
  vehicle_info: '2021 Freightliner Cascadia',
  shop_name: 'Truck Pit Stop Wisconsin',
  shop_logo_url: null,
  amount_due: '834.00',
  subtotal: '780.00',
  shop_supplies_amount: '20.00',
  service_fee_amount: '24.00',
  tax_amount: '34.00',
  discount_amount: '0.00',
  total_amount: '858.00',
  zelle_amount: '834.00',
  status: 'sent',
  due_date: '2026-09-15T00:00:00Z',
  paid_at: null,
  is_paid: false,
  pending_zelle_confirmation: true,
  zelle_email: 'pay@truckpitstop.example',
  zelle_phone: null,
  zelle_qr_image: null,
  has_portal_account: false,
  requires_password_setup: false,
  stripe_payments_available: true,
}

const authenticatedInvoice = {
  id: 'invoice-834',
  tenant_id: 'tenant-wisconsin',
  repair_order_id: 'ro-db048',
  invoice_number: 'INV-0048',
  order_number: 'RO-0048',
  customer_name: 'North Star Logistics',
  vehicle_info: '2021 Freightliner Cascadia',
  status: 'sent',
  subtotal: '780.00',
  shop_supplies_amount: '20.00',
  service_fee_amount: '24.00',
  tax_amount: '34.00',
  discount_amount: '0.00',
  total_amount: '858.00',
  due_date: '2026-09-15T00:00:00Z',
  paid_at: null,
  notes: null,
  pending_zelle_confirmation: true,
  payment: null,
  created_at: '2026-08-30T12:00:00Z',
  updated_at: '2026-08-30T12:00:00Z',
}

const repairOrder = {
  id: 'ro-db048',
  tenant_id: 'tenant-wisconsin',
  customer_id: 'customer-db048',
  vehicle_id: 'vehicle-db048',
  vehicle_make: 'Freightliner',
  vehicle_model: 'Cascadia',
  vehicle_year: 2021,
  vehicle_unit_number: 'NS-48',
  vehicle_vin: '•••••••••••••0048',
  customer_first_name: 'Casey',
  customer_last_name: 'Customer',
  customer_company_name: 'North Star Logistics',
  customer_email: 'customer@example.test',
  customer_phone: '7045550048',
  order_number: 'RO-0048',
  status: 'invoiced',
  description: 'Brake and suspension service',
  customer_notes: null,
  internal_notes: null,
  assigned_mechanic_id: null,
  total_parts_cost: '480.00',
  total_labor_cost: '300.00',
  total_cost: '780.00',
  created_at: '2026-08-30T11:00:00Z',
  updated_at: '2026-08-30T12:00:00Z',
  quote_sent: true,
  quote_approved: true,
  pending_zelle_confirmation: true,
  is_internal: false,
}

const staffInvoice = {
  ...authenticatedInvoice,
  pending_zelle_confirmation: true,
}

const priceBuild = {
  order_id: repairOrder.id,
  labor_total: '300.00',
  parts_total: '480.00',
  total_cost: '780.00',
  pricing_locked: true,
  can_edit_work: false,
  can_assign_technician: false,
  can_start_work: false,
  can_finalize: false,
  lines: [],
  parts: [],
  warnings: [],
}

const pendingStaffSummary = {
  ...structuredClone(DB048_SETTLEMENT_FIXTURES.pendingZelle500.summary),
  allowed_actions: {
    create_attempt: true,
    confirm_manual: true,
    retry_accounting: true,
    rails: ['card', 'zelle', 'check', 'ach'] as const,
  },
}

const pendingStaffAllocation = {
  ...structuredClone(DB048_SETTLEMENT_FIXTURES.pendingZelle500.allocations[0]),
  attempt_version: 7,
  reference_number: null,
}

function authenticatedUser(role: 'customer' | 'garage_owner') {
  return role === 'customer'
    ? {
        id: 'customer-user-db048',
        email: 'customer@example.test',
        first_name: 'Casey',
        last_name: 'Customer',
        phone: '7045550048',
        role,
        is_active: true,
        tenant_id: 'tenant-wisconsin',
        tenant_name: 'Truck Pit Stop Wisconsin',
        tenant_slug: 'wisconsin',
        tenant_logo_url: null,
        customer_id: 'customer-db048',
      }
    : { ...garageOwnerSession, presentation: presentationFixture('new') }
}

async function installAuthenticatedSession(page: Page, role: 'customer' | 'garage_owner') {
  await page.addInitScript(({ user }) => {
    window.localStorage.setItem('auth-storage', JSON.stringify({
      state: {
        user,
        token: null,
        refreshToken: null,
        isAuthenticated: true,
        authProvider: 'legacy',
      },
      version: 0,
    }))
  }, { user: authenticatedUser(role) })
}

function captureRuntimeFailures(page: Page) {
  const failures: string[] = []
  page.on('console', message => { if (message.type() === 'error') failures.push(`console: ${message.text()}`) })
  page.on('pageerror', error => failures.push(`pageerror: ${error.message}`))
  page.on('requestfailed', request => failures.push(`requestfailed: ${request.method()} ${request.url()}`))
  return failures
}

async function installExternalAssetStubs(page: Page) {
  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ status: 200, contentType: 'text/css', body: '' }))
  await page.route('https://fonts.gstatic.com/**', route => route.fulfill({ status: 204, body: '' }))
  await page.route('https://cdn.jsdelivr.net/npm/geist@*/**', route => route.fulfill({ status: 200, contentType: 'text/css', body: '' }))
}

async function installFixture(page: Page) {
  const failures: string[] = []
  const attempts: Array<{ body: Record<string, unknown>; idempotency: string | undefined }> = []
  let settlement = structuredClone(DB048_SETTLEMENT_FIXTURES.pendingZelle500.summary)

  page.on('console', message => { if (message.type() === 'error') failures.push(`console: ${message.text()}`) })
  page.on('pageerror', error => failures.push(`pageerror: ${error.message}`))
  page.on('requestfailed', request => failures.push(`requestfailed: ${request.method()} ${request.url()}`))

  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ status: 200, contentType: 'text/css', body: '' }))
  await page.route('https://fonts.gstatic.com/**', route => route.fulfill({ status: 204, body: '' }))
  await page.route('https://cdn.jsdelivr.net/npm/geist@*/**', route => route.fulfill({ status: 200, contentType: 'text/css', body: '' }))
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    const method = route.request().method()
    const body = route.request().postDataJSON?.() as Record<string, unknown> | undefined
    const json = (data: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) })

    if (url.pathname.endsWith('/invoice-access/resolve') && method === 'POST') return json(invoice)
    if (url.pathname.endsWith('/invoice-access/settlement') && method === 'POST') return json(settlement)
    if (url.pathname.endsWith('/invoice-access/allocations') && method === 'POST') return json({ items: DB048_SETTLEMENT_FIXTURES.pendingZelle500.allocations, next_cursor: null })
    if (url.pathname.endsWith('/invoice-access/attempts') && method === 'POST') {
      attempts.push({ body: body || {}, idempotency: route.request().headers()['idempotency-key'] })
      settlement = {
        ...settlement,
        active_pending_principal: '600.00',
        outstanding_balance: '834.00',
        allocatable_balance: '234.00',
        state: 'payment_pending',
        version: 3,
      }
      return json({
        attempt_id: 'attempt-zelle-100',
        invoice_id: invoice.invoice_id,
        principal_amount: '100.00',
        card_fee_amount: '0.00',
        card_fee_tax_amount: '0.00',
        provider_charge_amount: '100.00',
        state: 'pending',
        expires_at: '2026-08-31T15:00:00Z',
        rail: 'zelle',
        provider: 'manual',
        provider_configuration_version: 2,
        attempt_version: 1,
        settlement,
      })
    }
    failures.push(`unhandled: ${method} ${url.pathname}`)
    return json({ error: { code: 'fixture_unhandled', message: 'Unhandled fixture route', retryable: false } }, 500)
  })

  return { attempts, failures }
}

for (const viewport of [
  { width: 1440, height: 900, label: 'desktop' },
  { width: 390, height: 844, label: 'mobile' },
]) {
  test(`DB-048 guest partial Zelle journey stays exact and contained on ${viewport.label}`, async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height } })
    const page = await context.newPage()
    const fixture = await installFixture(page)

    await page.goto(`/invoice/${token}`)
    await expect(page.getByRole('heading', { name: 'Invoice INV-0048' })).toBeVisible()
    await expect(page.getByText('Payment pending')).toBeVisible()
    await expect(page.getByText('$334.00').first()).toBeVisible()
    await expect(page.getByRole('radio', { name: /Stripe/ })).toBeVisible()
    await expect(page.getByRole('radio', { name: /Zelle/ })).toBeVisible()
    await expect(page.getByRole('radio', { name: /Check/ })).toHaveCount(0)
    await expect(page.getByRole('radio', { name: /ACH/ })).toHaveCount(0)

    const amount = page.getByLabel('Amount applied to invoice')
    await amount.fill('100')
    await page.getByRole('radio', { name: /Zelle/ }).click()
    await page.getByRole('button', { name: 'Reserve Zelle amount' }).click()
    await expect(page.getByRole('heading', { name: 'Zelle amount reserved' })).toBeVisible()
    await expect(page.getByText('$100.00')).toBeVisible()
    expect(fixture.attempts).toHaveLength(1)
    expect(fixture.attempts[0].body).toMatchObject({
      token,
      amount: '100.00',
      rail: 'zelle',
      expected_settlement_version: 2,
    })
    expect(fixture.attempts[0].idempotency).toBeTruthy()

    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
    expect(fixture.failures).toEqual([])
    await context.close()
  })
}

async function installCustomerFixture(page: Page) {
  const failures = captureRuntimeFailures(page)
  await installAuthenticatedSession(page, 'customer')
  await installExternalAssetStubs(page)
  await page.routeWebSocket(/\/api\/v1\/ws(?:$|\?)/, socket => {
    socket.onMessage(message => { if (message === 'ping') socket.send('pong') })
  })
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/api\/v1/, '')
    const json = (data: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) })

    if (path === '/auth/tenant-branding') return json({ name: 'Truck Pit Stop Wisconsin', slug: 'wisconsin', logo_url: null, state: 'WI' })
    if (path === '/auth/me/appearance') return json(presentationFixture('new'))
    if (path === '/messages/unread-summary') return json({ unread_count_customer: 0 })
    if (path === `/invoices/${authenticatedInvoice.id}`) return json(authenticatedInvoice)
    if (path === `/repair-orders/${repairOrder.id}/detail`) return json({ ...repairOrder, parts_usage: [], labor_items: [], history_events: [] })
    if (path === `/payments/invoices/${authenticatedInvoice.id}/settlement`) {
      return json(DB048_SETTLEMENT_FIXTURES.pendingZelle500.summary)
    }
    if (path === `/payments/invoices/${authenticatedInvoice.id}/allocations`) {
      return json({ items: [pendingStaffAllocation], next_cursor: null })
    }
    if (path === `/payments/zelle-info/${authenticatedInvoice.id}`) {
      return json({
        zelle_email: 'pay@truckpitstop.example',
        zelle_phone: null,
        zelle_qr_image: null,
        garage_name: 'Truck Pit Stop Wisconsin',
        stripe_payments_available: true,
      })
    }
    failures.push(`unhandled: ${route.request().method()} ${path}`)
    return json({ error: { code: 'fixture_unhandled', message: 'Unhandled fixture route', retryable: false } }, 500)
  })
  return failures
}

for (const viewport of [
  { width: 1440, height: 900, label: 'desktop' },
  { width: 390, height: 844, label: 'mobile' },
]) {
  test(`DB-048 customer sees the same reserved remainder and rails on ${viewport.label}`, async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height } })
    const page = await context.newPage()
    const failures = await installCustomerFixture(page)

    await page.goto(`/portal/invoices/${authenticatedInvoice.id}`)
    await expect(page.getByText('RO-0048', { exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Payment pending' })).toBeVisible()
    await expect(page.getByText('Pending').locator('..').getByText('$500.00')).toBeVisible()
    await expect(page.getByText('Available to pay').locator('..').getByText('$334.00')).toBeVisible()
    await expect(page.getByRole('radio', { name: /Stripe Connect/ })).toBeVisible()
    await expect(page.getByRole('radio', { name: /Zelle/ })).toBeVisible()
    await expect(page.getByRole('radio', { name: /Check/ })).toHaveCount(0)
    await expect(page.getByRole('radio', { name: /ACH/ })).toHaveCount(0)
    await expect(page.getByText(/cash|external terminal|pay later/i)).toHaveCount(0)

    const card = page.getByRole('radio', { name: /Stripe Connect/ })
    await card.focus()
    await page.keyboard.press('ArrowRight')
    await expect(page.getByRole('radio', { name: /Zelle/ })).toBeFocused()
    await expect(page.getByRole('radio', { name: /Zelle/ })).toHaveAttribute('aria-checked', 'true')
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
    expect(failures, failures.join('\n')).toEqual([])
    await context.close()
  })
}

async function installProviderSettingsFixture(page: Page) {
  const failures = captureRuntimeFailures(page)
  await installAuthenticatedSession(page, 'garage_owner')
  await installExternalAssetStubs(page)
  await page.routeWebSocket(/\/api\/v1\/ws(?:$|\?)/, socket => {
    socket.onMessage(message => { if (message === 'ping') socket.send('pong') })
  })
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/api\/v1/, '')
    const json = (data: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) })

    if (path === '/auth/tenant-branding') return json({ name: 'Truck Pit Stop Wisconsin', slug: 'wisconsin', logo_url: null, state: 'WI' })
    if (path === '/auth/me/appearance') return json(presentationFixture('new'))
    if (path === '/messages/unread-summary') return json({ unread_count_staff: 0 })
    if (path === '/payments/settings/card-provider/readiness') return json(DB048_PROVIDER_READINESS)
    if (path === '/payments/settings/card-provider') return json({ selected_provider: 'stripe_connect', version: 2 })
    if (path === '/payments/customer-credits/aging') return json([])
    if (path === '/stripe/connect/status') return json({
      configured: true,
      is_connected: true,
      connection_type: 'stripe_connect',
      onboarding_complete: true,
      charges_enabled: true,
      payouts_enabled: true,
      verification_status: 'verified',
      requirements: [],
      account_id: 'acct_db048stripe',
      mode: 'test',
      available_balance: '0.00',
      pending_balance: '0.00',
      last_payout_amount: null,
      last_payout_status: null,
      recent_payments: [],
    })
    if (path === '/quickbooks/status') return json({ configured: true, is_connected: false })
    if (path === '/admin/zelle-settings') return json({ zelle_email: 'pay@truckpitstop.example', zelle_phone: null, zelle_qr_image: null })
    if (path === '/admin/garage-profile') return json({ name: 'Truck Pit Stop Wisconsin', email: 'shop@example.test', phone: '7045550000' })
    failures.push(`unhandled: ${route.request().method()} ${path}`)
    return json({ error: { code: 'fixture_unhandled', message: 'Unhandled fixture route', retryable: false } }, 500)
  })
  return failures
}

test('DB-048 settings exposes one usable Stripe provider and keeps QuickBooks Payments unavailable', async ({ page }) => {
  const failures = await installProviderSettingsFixture(page)
  await page.goto('/dashboard/settings?quickbooks=connected')
  await expect(page.getByRole('heading', { name: 'One provider for every customer' })).toBeVisible()
  await expect(page.getByRole('radio', { name: /Stripe Connect/ })).toHaveAttribute('aria-checked', 'true')
  const quickBooksPayments = page.getByRole('radio', { name: /QuickBooks Payments/ })
  await expect(quickBooksPayments).toBeDisabled()
  await expect(quickBooksPayments).toContainText('External Intuit approval pending')
  await expect(page.getByRole('radio', { name: /Stripe Connect|QuickBooks Payments/ })).toHaveCount(2)
  expect(failures, failures.join('\n')).toEqual([])
})

async function installStaffFixture(page: Page) {
  const failures = captureRuntimeFailures(page)
  const confirmations: Array<{ body: Record<string, unknown>; idempotency: string | undefined }> = []
  let summary = structuredClone(pendingStaffSummary)
  let allocations = [structuredClone(pendingStaffAllocation)]
  await installAuthenticatedSession(page, 'garage_owner')
  await installExternalAssetStubs(page)
  await page.routeWebSocket(/\/api\/v1\/ws(?:$|\?)/, socket => {
    socket.onMessage(message => { if (message === 'ping') socket.send('pong') })
  })
  await page.route('**/api/v1/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname.replace(/^\/api\/v1/, '')
    const method = request.method()
    const json = (data: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) })

    if (path === '/auth/tenant-branding') return json({ name: 'Truck Pit Stop Wisconsin', slug: 'wisconsin', logo_url: null, state: 'WI' })
    if (path === '/auth/me/appearance') return json(presentationFixture('new'))
    if (path === '/auth/platform-contact') return json({ support_name: 'DieselBridge Support', support_email: null, support_phone: null })
    if (path === '/messages/unread-summary') return json({ unread_count_staff: 0 })
    if (path === '/dashboard/mechanics/options') return json([])
    if (path === '/repair-orders/status-counts' && method === 'GET') {
      return json({ all: 1, invoiced: 1 })
    }
    if (path === '/repair-orders/value-summary' && method === 'GET') {
      return json({
        order_count: 1,
        order_value: repairOrder.total_cost,
        currency: 'USD',
        amount_basis: 'repair_order_net',
      })
    }
    if (path === '/repair-orders' && method === 'GET') return json({ items: [repairOrder], total: 1, has_more: false })
    if (path === `/repair-orders/${repairOrder.id}/workspace`) return json(repairOrder)
    if (path === `/repair-orders/${repairOrder.id}/notes` && method === 'GET') return json([])
    if (path === `/repair-orders/${repairOrder.id}/detail`) return json({ ...repairOrder, parts_usage: [], labor_items: [], history_events: [] })
    if (path === `/repair-orders/${repairOrder.id}/price-build`) return json(priceBuild)
    if (path === `/repair-orders/${repairOrder.id}/recommended-services`) return json([])
    if (path === `/repair-orders/${repairOrder.id}/photos`) return json([])
    if (path === '/admin/tax-fee-settings') return json({ labor_rate: 100 })
    if (path === '/quotes' && method === 'GET') return json(null)
    if (path === `/quotes/repair-order/${repairOrder.id}/history`) return json({ revisions: [], events: [] })
    if (path === '/invoices' && method === 'GET') return json([staffInvoice])
    if (path === `/payments/invoices/${staffInvoice.id}/settlement` && method === 'GET') return json(summary)
    if (path === `/payments/invoices/${staffInvoice.id}/allocations` && method === 'GET') return json({ items: allocations, next_cursor: null })
    if (path === `/payments/invoices/${staffInvoice.id}/accounting-reconciliation` && method === 'GET') {
      return json({
        invoice_id: staffInvoice.id,
        state: 'pending',
        pending_operations: 1,
        failed_operations: 0,
        synced_operations: 0,
        links: [{ id: 'accounting-db048', type: 'payment', state: 'pending' }],
      })
    }
    if (path === `/payments/invoices/${staffInvoice.id}/eligible-credits` && method === 'GET') return json([])
    if (path === `/payments/attempts/${pendingStaffAllocation.attempt_id}/confirm` && method === 'POST') {
      const body = (request.postDataJSON() ?? {}) as Record<string, unknown>
      confirmations.push({ body, idempotency: request.headers()['idempotency-key'] })
      summary = {
        ...summary,
        confirmed_principal: '500.00',
        active_pending_principal: '0.00',
        outstanding_balance: '334.00',
        allocatable_balance: '334.00',
        unapplied_credit: '50.00',
        state: 'overpayment_resolution',
        version: 3,
        accounting_sync_status: 'pending',
        allowed_actions: { resolve_overpayment: true, retry_accounting: true, rails: [] },
      }
      allocations = [{
        ...pendingStaffAllocation,
        attempt_version: 8,
        state: 'confirmed',
        received_amount: '550.00',
        provider_charge_amount: '550.00',
        applied_principal_amount: '500.00',
        unapplied_amount: '50.00',
        confirmed_at: '2026-08-30T12:15:00Z',
        reference_number: 'ZELLE-ACTUAL-550',
        accounting_sync_status: 'pending',
        overpayment_id: 'overpayment-zelle-50',
        overpayment_state: 'refund_required',
        refund_id: 'refund-zelle-50',
        refund_state: 'manual_action_required',
      }]
      return json({
        attempt_id: pendingStaffAllocation.attempt_id,
        invoice_id: staffInvoice.id,
        principal_amount: '500.00',
        card_fee_amount: '0.00',
        card_fee_tax_amount: '0.00',
        provider_charge_amount: '550.00',
        rail: 'zelle',
        provider: 'manual',
        state: 'confirmed',
        expires_at: null,
        provider_configuration_version: 2,
        attempt_version: 8,
        settlement: summary,
      })
    }
    failures.push(`unhandled: ${method} ${path}`)
    return json({ error: { code: 'fixture_unhandled', message: 'Unhandled fixture route', retryable: false } }, 500)
  })
  return { confirmations, failures }
}

for (const viewport of [
  { width: 1440, height: 900, label: 'desktop' },
  { width: 390, height: 844, label: 'mobile' },
]) {
  test(`DB-048 staff confirms actual Zelle overpayment with trapped focus on ${viewport.label}`, async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height } })
    const page = await context.newPage()
    const fixture = await installStaffFixture(page)

    await page.goto(`/dashboard/repair-orders?selected=${repairOrder.id}`)
    const trigger = page.getByRole('button', { name: 'Confirm Zelle payment' })
    // The first desktop repair-order workspace load performs more route
    // composition than the already-warm mobile run; wait for the actual
    // invoice action instead of treating Vite transform latency as a defect.
    await expect(trigger).toBeVisible({ timeout: 25_000 })
    await trigger.focus()
    await page.keyboard.press('Enter')

    const dialog = page.getByRole('dialog', { name: 'Record or review payment' })
    await expect(dialog).toBeVisible()
    const close = dialog.getByRole('button', { name: 'Close invoice settlement' })
    await expect(close).toBeFocused()
    await page.keyboard.press('Shift+Tab')
    await expect(dialog.locator(':focus')).not.toHaveCount(0)
    await expect(page.locator(':focus')).toBeAttached()
    expect(await dialog.evaluate((element, active) => element.contains(active as Node), await page.evaluateHandle(() => document.activeElement))).toBe(true)

    await expect(dialog.getByText('$500.00 is reserved until confirmation or expiry.')).toBeVisible()
    await dialog.getByLabel('Amount actually received').fill('550')
    await dialog.getByLabel('Transaction reference').fill('ZELLE-ACTUAL-550')
    await dialog.getByLabel(/Verification note/).fill('Verified against bank settlement')
    await dialog.getByRole('button', { name: 'Confirm Zelle received' }).click()

    await expect(dialog.getByText('$50.00 is unapplied')).toBeVisible()
    await expect(dialog.getByText(/QuickBooks accounting sync is pending/).first()).toBeVisible()
    await expect(dialog.getByText(/accounting operation queued.*Do not record the payment again/i)).toBeVisible()
    await expect(dialog.getByText(/cash|external terminal|pay later/i)).toHaveCount(0)
    expect(fixture.confirmations).toHaveLength(1)
    expect(fixture.confirmations[0].body).toEqual({
      expected_attempt_version: 7,
      received_amount: '550.00',
      reference: 'ZELLE-ACTUAL-550',
      note: 'Verified against bank settlement',
    })
    expect(fixture.confirmations[0].idempotency).toBeTruthy()

    await close.click()
    await expect(dialog).toBeHidden()
    await expect(trigger).toBeFocused()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
    expect(fixture.failures, fixture.failures.join('\n')).toEqual([])
    await context.close()
  })
}
