import { expect, test, type Page, type Route } from '@playwright/test'
import { presentationFixture } from '../../frontend/src/test-fixtures/db035/appearance'

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

function captureStrictRuntimeIssues(page: Page) {
  const issues: string[] = []

  page.on('pageerror', (error) => {
    issues.push(`pageerror: ${error.message}`)
  })
  page.on('console', (message) => {
    if (message.type() === 'error') issues.push(`console.error: ${message.text()}`)
  })
  page.on('requestfailed', (request) => {
    issues.push(`requestfailed: ${request.method()} ${request.url()} ${request.failure()?.errorText || ''}`.trim())
  })
  page.on('response', (response) => {
    const pathname = new URL(response.url()).pathname
    if (pathname.startsWith('/api/v1/') && response.status() >= 400) {
      issues.push(`api ${response.status()}: ${response.request().method()} ${pathname}`)
    }
  })

  return issues
}

const staffOrder = {
  id: 'order-db003-staff',
  tenant_id: 'tenant-db003',
  customer_id: 'customer-db003',
  vehicle_id: 'vehicle-db003',
  vehicle_make: 'Freightliner',
  vehicle_model: 'Cascadia',
  vehicle_year: 2022,
  vehicle_unit_number: 'DB-1047',
  vehicle_vin: '•••••••••••••1234',
  order_number: 'RO-DB003-STAFF',
  status: 'draft',
  description: 'Initial electrical inspection',
  customer_notes: null,
  internal_notes: null,
  assigned_mechanic_id: null,
  total_parts_cost: '0.00',
  total_labor_cost: '100.00',
  total_cost: '100.00',
  created_at: '2026-08-11T12:00:00Z',
  updated_at: '2026-08-11T12:00:00Z',
  quote_sent: false,
  quote_approved: false,
  is_internal: false,
}

const staffDraftQuote = {
  ...quote({
    id: 'quote-db003-staff',
    repair_order_id: staffOrder.id,
    quote_number: 'Q-DB003-STAFF',
    total_amount: '100.00',
    sent_to_customer: false,
    sent_at: null,
    revision: 1,
    authorization_type: 'initial_estimate',
    previously_authorized_amount: '0.00',
    delta_amount: '100.00',
  }),
}

const staffApprovedQuote = {
  ...staffDraftQuote,
  id: 'quote-db003-approved',
  quote_number: 'Q-DB003-APPROVED',
  total_amount: '80.00',
  is_approved: true,
  sent_to_customer: true,
  sent_at: '2026-08-11T13:00:00Z',
  previously_authorized_amount: '80.00',
  delta_amount: '0.00',
}

const staffAdditionalDraftQuote = {
  ...staffDraftQuote,
  id: 'quote-db003-additional',
  quote_number: 'Q-DB003-ADDITIONAL',
  revision: 2,
  authorization_type: 'additional_work',
  previously_authorized_amount: '80.00',
  delta_amount: '20.00',
}

const staffDeclinedAdditionalQuote = {
  ...staffAdditionalDraftQuote,
  id: 'quote-db003-declined-additional',
  quote_number: 'Q-DB003-DECLINED',
  is_declined: true,
  decline_notes: 'Please revise the added work.',
  sent_to_customer: true,
  sent_at: '2026-08-11T14:00:00Z',
}

const staffRevisedAdditionalDraftQuote = {
  ...staffAdditionalDraftQuote,
  id: 'quote-db003-revised-additional',
  quote_number: 'Q-DB003-REVISED',
  revision: 3,
}

const staffPriceBuild = {
  order_id: staffOrder.id,
  labor_total: '100.00',
  parts_total: '0.00',
  total_cost: '100.00',
  pricing_locked: false,
  can_edit_work: true,
  can_assign_technician: true,
  can_start_work: false,
  can_finalize: false,
  lines: [{
    id: 'labor-db003',
    repair_order_id: staffOrder.id,
    description: 'Initial electrical inspection',
    hours: '1.00',
    hourly_rate: '100.00',
    total_cost: '100.00',
    mechanic_id: null,
    service_code: null,
    line_type: 'manual',
    provider: null,
    provider_operation_id: null,
    auto_recalc_enabled: false,
    source_service_id: null,
    vendor_name: null,
    vendor_cost: null,
    created_at: '2026-08-11T12:00:00Z',
  }],
  parts: [],
  warnings: [],
}

async function mockStaffAuthorizationWorkspace(page: Page, mode: 'initial' | 'additional' | 'declined' = 'initial') {
  let currentQuote: typeof staffDraftQuote | typeof staffDeclinedAdditionalQuote | null = mode === 'initial'
    ? null
    : mode === 'declined'
      ? staffDeclinedAdditionalQuote
      : staffApprovedQuote
  let quoteRevisions: typeof staffDraftQuote[] = currentQuote ? [currentQuote] : []
  const authorizationEvents: Array<Record<string, unknown>> = mode !== 'initial'
    ? [
      {
        id: 'event-db003-approved-published',
        event_type: 'authorization_published',
        label: 'Estimate published',
        detail: JSON.stringify({ revision: 1, authorization_type: 'initial_estimate', resulting_total: '80.00' }),
        entity_id: staffApprovedQuote.id,
        actor_name: 'Olivia Owner',
        created_at: '2026-08-11T12:55:00Z',
      },
      {
        id: 'event-db003-approved-customer',
        event_type: 'authorization_customer_approved',
        label: 'Estimate approved',
        detail: JSON.stringify({ revision: 1, authorization_type: 'initial_estimate', resulting_total: '80.00' }),
        entity_id: staffApprovedQuote.id,
        actor_name: 'Casey Customer',
        created_at: '2026-08-11T13:00:00Z',
      },
    ]
    : []
  if (mode === 'declined') {
    authorizationEvents.push({
      id: 'event-db003-declined-customer',
      event_type: 'authorization_customer_declined',
      label: 'Additional work declined',
      detail: JSON.stringify({ revision: 2, authorization_type: 'additional_work', resulting_total: '100.00' }),
      entity_id: staffDeclinedAdditionalQuote.id,
      actor_name: 'Casey Customer',
      created_at: '2026-08-11T14:05:00Z',
    })
  }
  let createCount = 0
  let updateCount = 0
  let sendCount = 0
  const webSocketRegistrations: Array<{ pathname: string; hasQuery: boolean }> = []
  const runtimeIssues = captureStrictRuntimeIssues(page)
  const projectedOrder = () => ({
    ...staffOrder,
    status: mode === 'initial' ? staffOrder.status : 'approved',
    quote_sent: !!currentQuote?.sent_to_customer,
    quote_approved: !!currentQuote?.is_approved,
  })
  const projectedDetail = () => ({
    ...projectedOrder(),
    parts_usage: [],
    labor_items: staffPriceBuild.lines,
    history_events: authorizationEvents,
  })

  await page.routeWebSocket(/\/api\/v1\/ws(?:$|\?)/, socket => {
    const socketUrl = new URL(socket.url())
    webSocketRegistrations.push({
      pathname: socketUrl.pathname,
      hasQuery: socketUrl.search.length > 0,
    })
    socket.onMessage(message => {
      if (message === 'ping') socket.send('pong')
    })
  })

  await page.addInitScript(() => {
    window.localStorage.setItem('auth-storage', JSON.stringify({
      state: {
        user: {
          id: 'owner-db003',
          email: 'owner@example.test',
          first_name: 'Olivia',
          last_name: 'Owner',
          role: 'garage_owner',
          is_active: true,
          tenant_id: 'tenant-db003',
          tenant_name: 'DieselBridge Test Shop',
          tenant_slug: 'db003-test',
          tenant_logo_url: null,
          customer_id: null,
        },
        token: null,
        refreshToken: null,
        isAuthenticated: true,
        authProvider: 'legacy',
      },
      version: 0,
    }))
  })

  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ status: 200, contentType: 'text/css', body: '' }))
  await page.route('https://fonts.gstatic.com/**', route => route.fulfill({ status: 204, body: '' }))
  await page.route('https://cdn.jsdelivr.net/npm/geist@1.3.1/dist/fonts/geist-sans/style.min.css', route => (
    route.fulfill({ status: 200, contentType: 'text/css', body: '' })
  ))
  await page.route('**/api/v1/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname.replace(/^\/api\/v1/, '')

    if (path === '/auth/me/appearance') return fulfillJson(route, 200, presentationFixture('new'))
    if (path === '/auth/tenant-branding') return fulfillJson(route, 200, { name: 'DieselBridge Test Shop', slug: 'db003-test', logo_url: null, state: 'NC' })
    if (path === '/auth/platform-contact') return fulfillJson(route, 200, { support_name: 'DieselBridge Support', support_email: null, support_phone: null })
    if (path === '/messages/unread-summary') return fulfillJson(route, 200, { unread_count_staff: 0 })
    if (path === '/dashboard/mechanics/options') return fulfillJson(route, 200, [])
    if (path === '/repair-orders' && request.method() === 'GET') {
      return fulfillJson(route, 200, { items: [projectedOrder()], total: 1, has_more: false })
    }
    if (path === `/repair-orders/${staffOrder.id}/workspace`) return fulfillJson(route, 200, projectedOrder())
    if (path === `/repair-orders/${staffOrder.id}/detail`) return fulfillJson(route, 200, projectedDetail())
    if (path === `/repair-orders/${staffOrder.id}/price-build`) return fulfillJson(route, 200, staffPriceBuild)
    if (path === `/repair-orders/${staffOrder.id}/recommended-services`) return fulfillJson(route, 200, [])
    if (path === `/repair-orders/${staffOrder.id}/photos`) return fulfillJson(route, 200, [])
    if (path === '/admin/tax-fee-settings') return fulfillJson(route, 200, { labor_rate: 100 })
    if (path === '/quotes' && request.method() === 'GET') return fulfillJson(route, 200, currentQuote)
    if (path === `/quotes/repair-order/${staffOrder.id}/history` && request.method() === 'GET') {
      return fulfillJson(route, 200, { revisions: quoteRevisions, events: authorizationEvents })
    }
    if (path === '/quotes' && request.method() === 'POST') {
      createCount += 1
      currentQuote = mode === 'initial'
        ? staffDraftQuote
        : mode === 'declined'
          ? staffRevisedAdditionalDraftQuote
          : staffAdditionalDraftQuote
      quoteRevisions = [...quoteRevisions.filter((revision) => revision.id !== currentQuote?.id), currentQuote]
      return fulfillJson(route, 200, currentQuote)
    }
    if (currentQuote && path === `/quotes/${currentQuote.id}` && request.method() === 'PUT') {
      updateCount += 1
      quoteRevisions = quoteRevisions.map((revision) => revision.id === currentQuote?.id ? currentQuote : revision)
      return fulfillJson(route, 200, currentQuote)
    }
    if (currentQuote && path === `/quotes/${currentQuote.id}/send` && request.method() === 'POST') {
      sendCount += 1
      currentQuote = { ...currentQuote, sent_to_customer: true, sent_at: '2026-08-11T14:00:00Z' }
      quoteRevisions = quoteRevisions.map((revision) => revision.id === currentQuote?.id ? currentQuote : revision)
      authorizationEvents.push({
        id: `event-${currentQuote.id}-published`,
        event_type: 'authorization_published',
        label: currentQuote.authorization_type === 'additional_work' ? 'Additional work published' : 'Estimate published',
        detail: JSON.stringify({
          revision: currentQuote.revision,
          authorization_type: currentQuote.authorization_type,
          previous_amount: currentQuote.previously_authorized_amount,
          delta_amount: currentQuote.delta_amount,
          resulting_total: currentQuote.total_amount,
        }),
        entity_id: currentQuote.id,
        actor_name: 'Olivia Owner',
        created_at: currentQuote.sent_at,
      })
      return fulfillJson(route, 200, currentQuote)
    }

    runtimeIssues.push(`unhandled fixture request: ${request.method()} ${path}`)
    return fulfillJson(route, 404, { detail: `Unhandled DB-003 staff fixture route: ${path}` })
  })

  return {
    get createCount() { return createCount },
    get updateCount() { return updateCount },
    get sendCount() { return sendCount },
    get webSocketRegistrations() { return [...webSocketRegistrations] },
    get runtimeIssues() { return [...runtimeIssues] },
  }
}

async function expectMobileQuoteAction(
  page: Page,
  label: 'Create estimate' | 'Send estimate' | 'Authorize +$20.00' | 'Create revised authorization' | 'Send additional work',
  viewportHeight: number,
) {
  const action = page.getByRole('button', { name: label })
  await expect(action).toBeVisible()
  const box = await action.boundingBox()
  expect(box?.height).toBeGreaterThanOrEqual(44)
  expect(box?.y).toBeGreaterThanOrEqual(0)
  expect((box?.y || 0) + (box?.height || 0)).toBeLessThanOrEqual(viewportHeight)
  return action
}

async function mockFinalizedDeclinePortal(page: Page) {
  let draftQuoteRequests = 0
  const runtimeIssues: string[] = []
  const webSocketRegistrations: Array<{ pathname: string; hasQuery: boolean }> = []
  const customerId = 'customer-db003-declined'
  const orderId = 'order-db003-declined'
  const finalizedOrder = {
    ...staffOrder,
    id: orderId,
    customer_id: customerId,
    order_number: 'RO-DB003-DECLINED',
    status: 'invoiced',
    description: 'Finalized additional work repair',
    total_labor_cost: '1000.00',
    total_cost: '1000.00',
    quote_sent: true,
    quote_approved: false,
    updated_at: '2026-08-11T15:00:00Z',
  }
  const declinedQuote = quote({
    id: 'quote-db003-declined',
    repair_order_id: orderId,
    is_declined: true,
    decline_notes: 'Please defer this work.',
  })
  const newerUnsentDraft = quote({
    id: 'quote-db003-unsent-draft',
    repair_order_id: orderId,
    revision: declinedQuote.revision + 1,
    sent_to_customer: false,
    sent_at: null,
    is_declined: false,
    decline_notes: null,
  })

  page.on('pageerror', error => runtimeIssues.push(`page: ${error.message}`))
  page.on('console', message => {
    if (message.type() === 'error') runtimeIssues.push(`console: ${message.text()}`)
  })
  await page.routeWebSocket(/\/api\/v1\/ws(?:$|\?)/, socket => {
    const socketUrl = new URL(socket.url())
    webSocketRegistrations.push({
      pathname: socketUrl.pathname,
      hasQuery: socketUrl.search.length > 0,
    })
    socket.onMessage(message => {
      if (message === 'ping') socket.send('pong')
    })
  })

  await page.addInitScript(({ fixtureCustomerId }) => {
    window.localStorage.setItem('auth-storage', JSON.stringify({
      state: {
        user: {
          id: 'customer-user-db003',
          email: 'casey@example.test',
          first_name: 'Casey',
          last_name: 'Customer',
          role: 'customer',
          is_active: true,
          tenant_id: 'tenant-db003',
          tenant_name: 'DieselBridge Test Shop',
          tenant_slug: 'db003-test',
          tenant_logo_url: null,
          customer_id: fixtureCustomerId,
        },
        token: null,
        refreshToken: null,
        isAuthenticated: true,
        authProvider: 'legacy',
      },
      version: 0,
    }))
  }, { fixtureCustomerId: customerId })

  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ status: 200, contentType: 'text/css', body: '' }))
  await page.route('https://fonts.gstatic.com/**', route => route.fulfill({ status: 204, body: '' }))
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/api\/v1/, '')
    if (path === '/auth/tenant-branding') return fulfillJson(route, 200, { name: 'DieselBridge Test Shop', slug: 'db003-test', logo_url: null, state: 'NC' })
    if (path === '/auth/platform-contact') return fulfillJson(route, 200, { support_name: 'DieselBridge Support', support_email: null, support_phone: null })
    if (path === `/customers/${customerId}`) return fulfillJson(route, 200, { id: customerId, first_name: 'Casey', last_name: 'Customer' })
    if (path === '/vehicles') return fulfillJson(route, 200, { items: [], has_more: false, skip: 0, limit: 100 })
    if (path === '/repair-orders') return fulfillJson(route, 200, { items: [finalizedOrder], has_more: false, skip: 0, limit: 100 })
    if (path === `/repair-orders/${orderId}/detail`) return fulfillJson(route, 200, { ...finalizedOrder, parts_usage: [], labor_items: [], history_events: [] })
    if (path === `/repair-orders/${orderId}/photos`) return fulfillJson(route, 200, [])
    if (path === '/invoices') return fulfillJson(route, 200, [])
    if (path === '/quotes') {
      draftQuoteRequests += 1
      return fulfillJson(route, 403, { detail: 'Insufficient permissions' })
    }
    if (path === `/quotes/repair-order/${orderId}/history`) {
      return fulfillJson(route, 200, { revisions: [declinedQuote, newerUnsentDraft], events: [] })
    }
    runtimeIssues.push(`unhandled fixture request: ${route.request().method()} ${path}`)
    return fulfillJson(route, 404, { detail: `Unhandled DB-003 declined fixture route: ${path}` })
  })

  return {
    get draftQuoteRequests() { return draftQuoteRequests },
    get runtimeIssues() { return [...runtimeIssues] },
    get webSocketRegistrations() { return [...webSocketRegistrations] },
  }
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

for (const scenario of [
  {
    width: 320,
    mode: 'initial' as const,
    firstAction: 'Create estimate' as const,
    sendAction: 'Send estimate' as const,
    dialogTitle: 'Send estimate carefully',
    publishAction: 'Send estimate',
  },
  {
    width: 390,
    mode: 'additional' as const,
    firstAction: 'Authorize +$20.00' as const,
    sendAction: 'Send additional work' as const,
    dialogTitle: 'Send additional work?',
    publishAction: 'Send authorization',
  },
]) {
  test(`staff ${scenario.mode} authorization keeps focus through the ${scenario.width}px confirmation flow`, async ({ page }) => {
    const viewportHeight = 780
    await page.setViewportSize({ width: scenario.width, height: viewportHeight })
    const fixture = await mockStaffAuthorizationWorkspace(page, scenario.mode)

    await page.goto(`/dashboard/repair-orders?selected=${staffOrder.id}`)
    const firstAction = await expectMobileQuoteAction(page, scenario.firstAction, viewportHeight)
    await firstAction.focus()
    await expect(firstAction).toBeFocused()
    await page.keyboard.press('Enter')

    const sendAction = await expectMobileQuoteAction(page, scenario.sendAction, viewportHeight)
    await expect(sendAction).toBeFocused()
    await page.keyboard.press('Enter')

    const dialog = page.getByRole('dialog', { name: scenario.dialogTitle })
    await expect(dialog).toBeVisible()
    await expect(dialog).toHaveAttribute('aria-modal', 'true')
    const keepEditing = dialog.getByRole('button', { name: 'Keep editing' })
    const publishAction = dialog.getByRole('button', { name: scenario.publishAction })
    await expect(keepEditing).toBeFocused()

    await page.keyboard.press('Shift+Tab')
    await expect(publishAction).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(keepEditing).toBeFocused()

    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(page).toHaveURL(new RegExp(`/dashboard/repair-orders\\?selected=${staffOrder.id}$`))
    await expect(page.getByText('Initial electrical inspection').first()).toBeVisible()
    await expect(sendAction).toBeFocused()

    await page.keyboard.press('Enter')
    await expect(dialog).toBeVisible()
    await expect(keepEditing).toBeFocused()

    for (let attempt = 0; attempt < 20; attempt += 1) {
      await keepEditing.click()
      await sendAction.click()
      await expect(dialog).toBeVisible()
      await page.evaluate(() => new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve())))
      await expect(keepEditing).toBeFocused()
    }

    await page.keyboard.press('Tab')
    await expect(publishAction).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(dialog).toBeHidden()
    expect(fixture.sendCount).toBe(1)

    await page.getByRole('button', { name: 'History', exact: true }).click()
    await page.getByRole('button', { name: /Repair order history/ }).click()
    await expect(page.getByText(
      scenario.mode === 'additional' ? 'Additional work published' : 'Estimate published',
      { exact: true },
    )).toBeVisible()
    expect(fixture.webSocketRegistrations.length).toBeGreaterThanOrEqual(1)
    expect(fixture.webSocketRegistrations.length).toBeLessThanOrEqual(2)
    expect(fixture.webSocketRegistrations.every(registration => (
      registration.pathname === '/api/v1/ws' && registration.hasQuery === false
    ))).toBe(true)
    expect(fixture.runtimeIssues, fixture.runtimeIssues.join('\n')).toEqual([])
  })
}

for (const width of [390, 320]) {
  test(`publisher creates a replacement after a declined unchanged revision at ${width}px`, async ({ page }) => {
    const viewportHeight = 780
    await page.setViewportSize({ width, height: viewportHeight })
    const fixture = await mockStaffAuthorizationWorkspace(page, 'declined')

    await page.goto(`/dashboard/repair-orders?selected=${staffOrder.id}`)
    await expect(page.getByRole('button', { name: 'Awaiting authorization' })).toHaveCount(0)
    const createRevision = await expectMobileQuoteAction(page, 'Create revised authorization', viewportHeight)
    await createRevision.focus()
    await page.keyboard.press('Enter')

    const sendRevision = await expectMobileQuoteAction(page, 'Send additional work', viewportHeight)
    await expect(sendRevision).toBeFocused()
    expect(fixture.createCount).toBe(1)
    await page.keyboard.press('Enter')

    const dialog = page.getByRole('dialog', { name: 'Send additional work?' })
    await expect(dialog).toBeVisible()
    await expect(dialog).toHaveAttribute('aria-modal', 'true')
    const keepEditing = dialog.getByRole('button', { name: 'Keep editing' })
    const publish = dialog.getByRole('button', { name: 'Send authorization' })
    await expect(keepEditing).toBeFocused()
    await page.keyboard.press('Shift+Tab')
    await expect(publish).toBeFocused()
    await page.keyboard.press('Enter')

    await expect(dialog).toBeHidden()
    expect(fixture.updateCount).toBe(1)
    expect(fixture.sendCount).toBe(1)
    expect(fixture.webSocketRegistrations.length).toBeGreaterThanOrEqual(1)
    expect(fixture.webSocketRegistrations.length).toBeLessThanOrEqual(2)
    expect(fixture.webSocketRegistrations.every(registration => (
      registration.pathname === '/api/v1/ws' && registration.hasQuery === false
    ))).toBe(true)
    expect(fixture.runtimeIssues, fixture.runtimeIssues.join('\n')).toEqual([])
  })
}

test('declined additional work stays non-actionable after removal and finalization', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const fixture = await mockFinalizedDeclinePortal(page)

  await page.goto('/portal')
  await expect(page.getByText('All paid up')).toBeVisible()
  await expect(page.getByText('Action required')).toHaveCount(0)
  await expect(page.getByText('Review authorization')).toHaveCount(0)

  await page.getByRole('link', { name: /Finalized additional work repair/ }).click()
  await expect(page.getByRole('heading', { name: 'Additional work declined' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Authorize/ })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Decline this revision' })).toHaveCount(0)
  expect(fixture.draftQuoteRequests).toBe(0)
  expect(fixture.webSocketRegistrations.length).toBeGreaterThanOrEqual(1)
  expect(fixture.webSocketRegistrations.length).toBeLessThanOrEqual(2)
  expect(fixture.webSocketRegistrations.every(registration => (
    registration.pathname === '/api/v1/ws' && registration.hasQuery === false
  ))).toBe(true)
  expect(fixture.runtimeIssues).toEqual([])
})
