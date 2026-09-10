import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { useAuthStore } from '../stores/authStore'
import { DB048_PROVIDER_READINESS } from '../test-fixtures/db048/settlements'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
}))

vi.mock('../lib/api', () => ({
  default: {
    get: apiMocks.get,
    post: apiMocks.post,
    put: apiMocks.put,
    defaults: { headers: { common: {} } },
  },
}))

vi.mock('react-hot-toast', () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

import UnifiedSettingsPage from '../features/dashboard/UnifiedSettingsPage'

const garageProfile = {
  name: 'Truck Pit Stop',
  slug: 'truck-pit-stop',
  address: '123 Service Rd',
  phone: '5551234567',
  email: 'garage@example.com',
  website: 'https://garage.example.com',
  logo_url: null,
}

const importedGarageProfile = {
  ...garageProfile,
  logo_url: 'https://cdn.example.com/imported-logo.png',
}

const stripeConnection = {
  configured: true,
  is_connected: true,
  onboarding_complete: true,
  charges_enabled: true,
  payouts_enabled: true,
  account_id: 'acct_123456789',
  connection_type: 'stripe_hosted',
  verification_status: 'active',
  requirements: [],
  mode: 'test',
  account_dashboard_url: 'https://dashboard.stripe.example.com',
  available_balance: '125.00',
  pending_balance: '0.00',
  last_payout_amount: null,
  last_payout_status: null,
  last_payout_at: null,
  recent_payments: [],
}

const quickBooksConnection = {
  configured: true,
  is_connected: false,
  realm_id: null,
  scopes: [],
  connected_at: null,
  token_health: 'not_connected',
  last_token_refresh_at: null,
  last_token_refresh_error: null,
  last_webhook_at: null,
  last_webhook_event: null,
  last_webhook_error: null,
}

function renderPage(initialEntry = '/dashboard/settings') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <UnifiedSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

async function verifyPaymentChange(user: ReturnType<typeof userEvent.setup>) {
  const dialog = await screen.findByRole('alertdialog', { name: /^Verify / })
  await user.type(within(dialog).getByLabelText('Your current password'), 'local-password')
  await user.click(within(dialog).getByRole('button', { name: 'Verify and continue' }))
}

describe('UnifiedSettingsPage garage logo import', () => {
  beforeEach(() => {
    apiMocks.get.mockReset()
    apiMocks.post.mockReset()
    apiMocks.put.mockReset()

    apiMocks.get.mockResolvedValue({ data: garageProfile })
    apiMocks.post.mockResolvedValue({ data: importedGarageProfile })

    useAuthStore.setState({
      user: {
        id: 'u-1',
        email: 'owner@example.com',
        first_name: 'Owner',
        last_name: 'User',
        phone: null,
        role: 'garage_owner',
        is_active: true,
        tenant_id: 't-1',
        customer_id: null,
        tenant_name: 'Truck Pit Stop',
        tenant_slug: 'truck-pit-stop',
      },
      token: 'token',
      refreshToken: 'refresh',
      isAuthenticated: true,
    })
  })

  it('imports a logo from the saved website and updates the form', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(screen.getByRole('button', { name: 'Shop Profile' }))

    expect(apiMocks.get).toHaveBeenCalledWith('/admin/garage-profile')

    const editButton = await screen.findByRole('button', { name: 'Edit Shop Profile' })
    expect(editButton.closest('.db-settings-shop-profile')).toBeInTheDocument()
    expect(screen.getByText('Shop Logo').closest('.db-settings-shop-profile__panel')).toBeInTheDocument()
    expect(screen.getByText(/use the website importer/i).closest('.db-settings-shop-profile__logo-canvas')).toBeInTheDocument()
    await user.click(editButton)

    const importButton = await screen.findByRole('button', { name: /import from website/i })
    await user.click(importButton)

    expect(apiMocks.post).toHaveBeenCalledWith('/admin/garage-profile/import-logo', {
      website: 'https://garage.example.com',
    })

    await waitFor(() => {
      expect(screen.getByDisplayValue('https://cdn.example.com/imported-logo.png')).toBeInTheDocument()
    })
  })
})

describe('UnifiedSettingsPage compact mobile section selector', () => {
  beforeEach(() => {
    apiMocks.get.mockReset()
    apiMocks.post.mockReset()
    apiMocks.put.mockReset()
    apiMocks.get.mockResolvedValue({ data: garageProfile })

    useAuthStore.setState({
      user: {
        id: 'u-1',
        email: 'owner@example.com',
        first_name: 'Owner',
        last_name: 'User',
        phone: null,
        role: 'garage_owner',
        is_active: true,
        tenant_id: 't-1',
        customer_id: null,
        tenant_name: 'Truck Pit Stop',
        tenant_slug: 'truck-pit-stop',
      },
      token: 'token',
      refreshToken: 'refresh',
      isAuthenticated: true,
    })
  })

  it('keeps every permitted section reachable through the grouped mobile switcher', async () => {
    const user = userEvent.setup()
    renderPage()

    const trigger = screen.getByRole('button', { name: 'Settings section: Profile' })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(document.querySelector('.db-settings-mobile-section-selector select')).toBeNull()

    await user.click(trigger)

    const menu = screen.getByRole('group', { name: 'Settings sections' })
    expect(within(menu).getByText('Additional services')).toBeInTheDocument()
    expect(within(menu).getByRole('button', { name: 'Fleet' })).toBeInTheDocument()
    expect(within(menu).getByRole('button', { name: 'Google Reviews' })).toBeInTheDocument()
    expect(document.querySelector('.db-settings-sidebar__additional')).toHaveAttribute('class', expect.stringContaining('db-settings-sidebar__additional'))

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('group', { name: 'Settings sections' })).not.toBeInTheDocument()

    await user.click(trigger)
    await user.click(within(screen.getByRole('group', { name: 'Settings sections' })).getByRole('button', { name: 'Payments & Accounting' }))
    expect(screen.getByRole('button', { name: 'Settings section: Payments & Accounting' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('restores the Fleet Settings section from the existing settings URL', async () => {
    apiMocks.get.mockImplementation((path: string) => {
      if (path === '/admin/tax-fee-settings') {
        return Promise.resolve({ data: {
          sales_tax_rate: 0,
          shop_supplies_rate: 0,
          service_fee_rate: 0,
          labor_rate: 100,
          internal_labor_rate: 0,
          fleet_company_name: null,
          default_fleet_authority_customer_id: null,
          default_fleet_authority_company_name: null,
        } })
      }
      if (path === '/fleet/settings') return Promise.resolve({ data: { fleet_managers: [] } })
      if (path === '/fleet/companies') return Promise.resolve({ data: [] })
      if (path === '/fleet/board') return Promise.resolve({ data: { trucks: [] } })
      return Promise.resolve({ data: garageProfile })
    })

    renderPage('/dashboard/settings?section=fleet')

    const heading = await screen.findByText('Fleet Configuration')
    const configuration = heading.closest<HTMLElement>('.db-settings-fleet-config')

    expect(configuration).not.toBeNull()
    expect(within(configuration!).getAllByText(/Fleet Company|Default Operating Authority/)).toHaveLength(2)
    expect(configuration!.querySelectorAll('.db-settings-fleet-config__summary')).toHaveLength(2)
    expect(within(configuration!).getByLabelText('Password')).toBeInTheDocument()
  })
})

describe('UnifiedSettingsPage payment disclosures', () => {
  beforeEach(() => {
    apiMocks.get.mockReset()
    apiMocks.post.mockReset()
    apiMocks.put.mockReset()
    apiMocks.get.mockImplementation((path: string) => {
      const dataByPath: Record<string, unknown> = {
        '/stripe/connect/status': stripeConnection,
        '/quickbooks/status': quickBooksConnection,
        '/admin/garage-profile': garageProfile,
        '/admin/zelle-settings': { zelle_email: 'payments@truckpitstop.com', zelle_phone: null, zelle_qr_image: null },
      }
      return Promise.resolve({ data: dataByPath[path] ?? garageProfile })
    })
    apiMocks.post.mockResolvedValue({
      data: {
        grant_token: 'opaque-step-up-grant',
        scope: 'payment_sources.manage',
        expires_at: new Date(Date.now() + 10 * 60 * 1000).toISOString(),
        one_time: false,
      },
    })
    apiMocks.put.mockResolvedValue({
      data: { zelle_email: 'updated@truckpitstop.com', zelle_phone: null, zelle_qr_image: null },
    })
    useAuthStore.setState({
      user: {
        id: 'u-1',
        email: 'owner@example.com',
        first_name: 'Owner',
        last_name: 'User',
        phone: null,
        role: 'garage_owner',
        is_active: true,
        tenant_id: 't-1',
        customer_id: null,
        tenant_name: 'Truck Pit Stop',
        tenant_slug: 'truck-pit-stop',
      },
      token: 'token',
      refreshToken: 'refresh',
      isAuthenticated: true,
    })
  })

  it('nests Taxes & Fees under Payments & Accounting without changing settings', async () => {
    const user = userEvent.setup()
    renderPage()
    expect(screen.queryByRole('button', { name: /Taxes? & Fees/ })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))
    await user.click(screen.getByRole('button', { name: 'Taxes & Fees' }))
    expect(screen.getByRole('button', { name: 'Taxes & Fees' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByText('Your customer’s card fee')).not.toBeInTheDocument()
    const help = await screen.findByText('About card fees')
    expect(help.closest('details')).not.toHaveAttribute('open')
    await user.click(help)
    expect(screen.queryByText('2.99%')).not.toBeInTheDocument()
    expect(screen.getByText(/A surcharge is optional/)).toBeVisible()
    expect(screen.getByRole('link', { name: 'Visa surcharge requirements' })).toHaveAttribute('href', expect.stringContaining('usa.visa.com'))
    expect(screen.getByPlaceholderText('Enter password')).toBeInTheDocument()
    expect(apiMocks.put).not.toHaveBeenCalled()
    expect(apiMocks.post).not.toHaveBeenCalled()
  })

  it('places processor rates inside the QuickBooks source, not Taxes & Fees', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))
    await user.click(screen.getByRole('button', { name: /QuickBooks Online/i }))
    const panel = screen.getByRole('region', { name: /QuickBooks Online/i })
    await user.click(within(panel).getByText('QuickBooks processing rates'))
    for (const rate of ['2.5%', '2.99%', '3.5%']) expect(within(panel).getByText(rate)).toBeVisible()
    expect(within(panel).queryByText(/not yet verified|DieselBridge customer portal/)).not.toBeInTheDocument()
    for (const method of ['Card reader / Tap to Pay', 'Online invoice payment', 'Staff manually enters card']) expect(within(panel).getByText(method)).toBeVisible()
    expect(panel.querySelector('details p')).toBeNull()
    expect(within(panel).getByRole('link', { name: 'QuickBooks published rates' })).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Taxes & Fees' }))
    expect(screen.getByText('QuickBooks processing rates')).not.toBeVisible()
    expect(screen.getByText('About card fees')).toBeVisible()
    expect(apiMocks.post).not.toHaveBeenCalled()
    expect(apiMocks.put).not.toHaveBeenCalled()
  })

  it('opens the legacy fees URL inside Payments & Accounting and preserves subview drafts', async () => {
    const user = userEvent.setup()
    renderPage('/dashboard/settings?section=fees')
    const password = await screen.findByPlaceholderText('Enter password')
    await user.type(password, 'unfinished-draft')
    await user.click(screen.getByRole('button', { name: 'Payment sources' }))
    await user.click(screen.getByRole('button', { name: 'Taxes & Fees' }))
    expect(screen.getByPlaceholderText('Enter password')).toHaveValue('unfinished-draft')
    expect(apiMocks.put).not.toHaveBeenCalled()
    expect(apiMocks.post).not.toHaveBeenCalled()
  })

  it('submits verification once and ignores a late grant after leaving settings', async () => {
    const user = userEvent.setup()
    let resolveGrant!: (value: unknown) => void
    apiMocks.post.mockImplementation(() => new Promise((resolve) => { resolveGrant = resolve }))
    const page = renderPage()
    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))
    await user.click(screen.getByRole('button', { name: 'Disconnect Stripe' }))
    const dialog = await screen.findByRole('alertdialog', { name: 'Verify Stripe disconnection' })
    await user.type(within(dialog).getByLabelText('Your current password'), 'password')
    const form = within(dialog).getByRole('button', { name: 'Verify and continue' }).closest('form')!
    fireEvent.submit(form)
    fireEvent.submit(form)
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledTimes(1))
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeDisabled()
    page.unmount()
    resolveGrant({ data: { grant_token: 'late-grant', scope: 'payment_sources.stripe.disconnect' } })
    await Promise.resolve()
    expect(apiMocks.post).toHaveBeenCalledTimes(1)
  })

  it('clears the verification dialog and drafts when the active tenant changes', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))
    await user.click(screen.getByRole('button', { name: 'Disconnect Stripe' }))
    await user.type(await screen.findByLabelText('Your current password'), 'tenant-one-password')
    act(() => useAuthStore.setState({ user: { ...useAuthStore.getState().user!, tenant_id: 'another-tenant' } }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(apiMocks.post).not.toHaveBeenCalled()
  })

  it('uses the shared scoped password dialog before saving invoice card routing', async () => {
    const user = userEvent.setup()
    const fallback = apiMocks.get.getMockImplementation()!
    apiMocks.get.mockImplementation((path: string) => path === '/payments/settings/card-provider/readiness'
      ? Promise.resolve({ data: {
        ...DB048_PROVIDER_READINESS,
        quickbooks_payments: { approved: true, tenant_ready: true, status: 'ready' },
      } }) : fallback(path))
    renderPage()
    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))
    await user.click(await screen.findByRole('radio', { name: /QuickBooks Payments/ }))
    await user.click(screen.getByRole('button', { name: 'Use QuickBooks for new attempts' }))
    expect(await screen.findByRole('alertdialog', { name: 'Verify invoice card routing' })).toBeInTheDocument()
    expect(apiMocks.put).not.toHaveBeenCalled()
    await verifyPaymentChange(user)
    await waitFor(() => expect(apiMocks.put).toHaveBeenCalledWith(
      '/payments/settings/card-provider',
      expect.objectContaining({ selected_provider: 'quickbooks_payments' }),
      { headers: { 'Idempotency-Key': expect.any(String), 'X-Step-Up-Authorization': 'opaque-step-up-grant' } },
    ))
  })

  it.each([
    { payments: true, taxes_fees: false },
    { payments: false, taxes_fees: true },
    { payments: true, taxes_fees: true },
    { payments: false, taxes_fees: false },
  ])('preserves separate admin permissions: %j', async (permissions) => {
    const user = userEvent.setup()
    useAuthStore.setState({ user: { ...useAuthStore.getState().user!, role: 'garage_admin', permissions } })
    renderPage()
    const entry = screen.queryByRole('button', { name: 'Payments & Accounting' })
    if (!permissions.payments && !permissions.taxes_fees) {
      expect(entry).not.toBeInTheDocument()
      return
    }
    await user.click(entry!)
    expect(!!screen.queryByRole('button', { name: 'Payment sources' })).toBe(permissions.payments)
    expect(!!screen.queryByRole('button', { name: 'Taxes & Fees' })).toBe(permissions.taxes_fees)
    if (!permissions.payments) {
      expect(await screen.findByText('About card fees')).toBeInTheDocument()
      expect(apiMocks.get).not.toHaveBeenCalledWith('/stripe/connect/status')
      expect(apiMocks.get).not.toHaveBeenCalledWith('/quickbooks/status')
      expect(apiMocks.get).not.toHaveBeenCalledWith('/admin/zelle-settings')
    }
    if (!permissions.taxes_fees) {
      expect(apiMocks.get).not.toHaveBeenCalledWith('/admin/tax-fee-settings')
    }
    expect(apiMocks.put).not.toHaveBeenCalled()
    expect(apiMocks.post).not.toHaveBeenCalled()
  })

  it('does not mount payment controls through an OAuth return without permission', async () => {
    useAuthStore.setState({ user: { ...useAuthStore.getState().user!, role: 'garage_admin', permissions: {} } })
    renderPage('/dashboard/settings?quickbooks=connected')
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Payment sources' })).not.toBeInTheDocument())
    expect(apiMocks.get).not.toHaveBeenCalledWith('/quickbooks/status')
  })

  it('links payment triggers to labelled disclosure regions', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))

    const stripeTrigger = await screen.findByRole('button', { name: /Stripe Payments/i })
    const stripePanelId = stripeTrigger.getAttribute('aria-controls')
    expect(screen.getByRole('heading', { name: 'Payments & Accounting' })).toBeInTheDocument()
    expect(stripePanelId).toBeTruthy()
    expect(screen.getByRole('region', { name: /Stripe Payments/i })).toHaveAttribute('id', stripePanelId)

    await user.click(stripeTrigger)
    expect(screen.queryByRole('region', { name: /Stripe Payments/i })).not.toBeInTheDocument()

    const zelleTrigger = screen.getByRole('button', { name: /Zelle Payments/i })
    await user.click(zelleTrigger)
    expect(zelleTrigger).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('region', { name: /Zelle Payments/i })).toBeInTheDocument()

    zelleTrigger.focus()
    await user.keyboard('{Enter}')
    expect(zelleTrigger).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('region', { name: /Zelle Payments/i })).not.toBeInTheDocument()
  })

  it('puts connected QuickBooks and configured Zelle before unused Stripe in DOM order', async () => {
    const user = userEvent.setup()
    const originalGet = apiMocks.get.getMockImplementation()!
    apiMocks.get.mockImplementation((path: string) => {
      if (path === '/stripe/connect/status') return Promise.resolve({ data: { ...stripeConnection, is_connected: false } })
      if (path === '/quickbooks/status') return Promise.resolve({ data: { ...quickBooksConnection, is_connected: true, token_health: 'healthy' } })
      return originalGet(path)
    })
    const page = renderPage()
    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))
    await screen.findByRole('button', { name: /QuickBooks Online.*ACTIVE/i })
    expect(Array.from(page.container.querySelectorAll('[data-payment-source]')).map(element => element.getAttribute('data-payment-source'))).toEqual(['quickbooks', 'zelle', 'stripe'])
    expect(screen.getByRole('button', { name: /Stripe Payments/i })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('button', { name: /QuickBooks Online/i })).toHaveAttribute('aria-expanded', 'true')
    await user.click(screen.getByRole('button', { name: /Stripe Payments/i }))
    expect(screen.getByRole('button', { name: 'Set Up Stripe Payments' })).toBeEnabled()
    expect(apiMocks.post).not.toHaveBeenCalled()
  })

  it('keeps connected Stripe above unused QuickBooks without changing provider settings', async () => {
    const user = userEvent.setup()
    const page = renderPage()
    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))
    await screen.findByRole('button', { name: /Stripe Payments/i })
    expect(Array.from(page.container.querySelectorAll('[data-payment-source]')).map(element => element.getAttribute('data-payment-source'))).toEqual(['stripe', 'zelle', 'quickbooks'])
    expect(apiMocks.put).not.toHaveBeenCalled()
    expect(apiMocks.post).not.toHaveBeenCalled()
  })

  it('blocks a failed password, supports cancellation, and verifies each later save again', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))
    await user.click(screen.getByRole('button', { name: /Zelle Payments/i }))
    const email = await screen.findByLabelText('Zelle Email')
    await user.clear(email)
    await user.type(email, 'new@example.com')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    apiMocks.post.mockRejectedValueOnce({ response: { data: { detail: 'Incorrect password' } } })
    await verifyPaymentChange(user)
    expect(await within(screen.getByRole('alertdialog')).findByRole('alert')).toHaveTextContent('Incorrect password')
    expect(apiMocks.put).not.toHaveBeenCalled()
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Cancel' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(screen.getByLabelText('Your current password')).toHaveValue('')
    await verifyPaymentChange(user)
    await waitFor(() => expect(apiMocks.put).toHaveBeenCalledTimes(1))
    await user.clear(screen.getByLabelText('Zelle Email'))
    await user.type(screen.getByLabelText('Zelle Email'), 'later@example.com')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alertdialog', { name: 'Verify Zelle contact changes' })).toBeInTheDocument()
    expect(apiMocks.put).toHaveBeenCalledTimes(1)
  })

  it('verifies Stripe setup before starting the provider redirect', async () => {
    const user = userEvent.setup()
    apiMocks.get.mockImplementation((path: string) => Promise.resolve({ data: {
      '/stripe/connect/status': { ...stripeConnection, is_connected: false },
      '/quickbooks/status': quickBooksConnection,
      '/admin/garage-profile': garageProfile,
      '/admin/zelle-settings': {},
    }[path] ?? garageProfile }))
    const grant = { data: { grant_token: 'setup-grant', scope: 'payment_sources.manage' } }
    apiMocks.post.mockImplementation((path: string) => path === '/auth/step-up-grants'
      ? Promise.resolve(grant) : new Promise(() => {}))
    renderPage()
    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))
    await user.click(await screen.findByRole('button', { name: /Stripe Payments.*NOT SET UP/i }))
    await user.click(await screen.findByRole('button', { name: /Set Up Stripe Payments/i }))
    expect(apiMocks.post).not.toHaveBeenCalled()
    await verifyPaymentChange(user)
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith(
      '/stripe/connect/connect', undefined,
      { headers: { 'X-Step-Up-Authorization': 'setup-grant' } },
    ))
    expect(apiMocks.post.mock.calls.filter(([path]) => path === '/auth/step-up-grants')).toHaveLength(1)
  })

  it('previews a QR upload locally and verifies before saving it', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))
    await user.click(screen.getByRole('button', { name: /Zelle Payments/i }))
    await user.upload(await screen.findByLabelText('Upload QR Code'), new File(['qr'], 'qr.png', { type: 'image/png' }))
    await user.click(await screen.findByRole('button', { name: 'Save' }))
    expect(apiMocks.put).not.toHaveBeenCalled()
    expect(await screen.findByRole('alertdialog', { name: 'Verify Zelle QR upload' })).toBeInTheDocument()
    await verifyPaymentChange(user)
    await waitFor(() => expect(apiMocks.put).toHaveBeenCalledWith(
      '/admin/zelle-qr-image', { zelle_qr_image: expect.stringMatching(/^data:image\/png;base64,/) },
      { headers: { 'X-Step-Up-Authorization': 'opaque-step-up-grant' } },
    ))
  })

  it('requests verification only when saving payment-source changes', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))

    expect(screen.queryByRole('button', { name: 'Unlock changes' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Your current password')).not.toBeInTheDocument()
    expect(apiMocks.post).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: /Zelle Payments/i }))
    const email = await screen.findByLabelText('Zelle Email')
    await user.clear(email)
    await user.type(email, 'updated@truckpitstop.com')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(apiMocks.put).not.toHaveBeenCalled()
    await verifyPaymentChange(user)

    await waitFor(() => {
      expect(apiMocks.put).toHaveBeenCalledWith(
        '/admin/zelle-settings',
        { zelle_email: 'updated@truckpitstop.com', zelle_phone: '5551234567' },
        { headers: { 'X-Step-Up-Authorization': 'opaque-step-up-grant' } },
      )
    })
  })

  it('requires a final confirmation before a verified Zelle disablement', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))
    await user.click(screen.getByRole('button', { name: /Zelle Payments/i }))

    await user.clear(await screen.findByLabelText('Zelle Email'))
    await user.clear(screen.getByLabelText('Zelle Phone'))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(apiMocks.put).not.toHaveBeenCalled()
    await verifyPaymentChange(user)

    const confirmation = await screen.findByRole('alertdialog', { name: 'Disable Zelle payments?' })
    expect(apiMocks.put).not.toHaveBeenCalledWith('/admin/zelle-settings', expect.anything(), expect.anything())
    await user.click(within(confirmation).getByRole('button', { name: 'Disable Zelle' }))

    await waitFor(() => expect(apiMocks.put).toHaveBeenCalledWith(
      '/admin/zelle-settings',
      { zelle_email: null, zelle_phone: null },
      { headers: { 'X-Step-Up-Authorization': 'opaque-step-up-grant' } },
    ))
  })

  it('requires a final confirmation before removing a verified Zelle QR code', async () => {
    const user = userEvent.setup()
    apiMocks.get.mockImplementation((path: string) => Promise.resolve({ data: {
      '/stripe/connect/status': stripeConnection,
      '/quickbooks/status': quickBooksConnection,
      '/admin/garage-profile': garageProfile,
      '/admin/zelle-settings': { zelle_email: 'payments@truckpitstop.com', zelle_phone: null, zelle_qr_image: 'data:image/png;base64,qr' },
    }[path] ?? garageProfile }))
    renderPage()

    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))
    await user.click(screen.getByRole('button', { name: /Zelle Payments/i }))
    await user.click(await screen.findByRole('button', { name: 'Remove' }))
    await verifyPaymentChange(user)

    const confirmation = await screen.findByRole('alertdialog', { name: 'Remove the Zelle QR code?' })
    expect(apiMocks.put).not.toHaveBeenCalledWith('/admin/zelle-qr-image', expect.anything(), expect.anything())
    await user.click(within(confirmation).getByRole('button', { name: 'Remove QR code' }))

    await waitFor(() => expect(apiMocks.put).toHaveBeenCalledWith(
      '/admin/zelle-qr-image',
      { zelle_qr_image: null },
      { headers: { 'X-Step-Up-Authorization': 'opaque-step-up-grant' } },
    ))
  })

  it('requests exactly one scoped password for Stripe disconnection', async () => {
    const user = userEvent.setup()
    apiMocks.post.mockImplementation((path: string, body?: { scope?: string }) => {
      if (path === '/auth/step-up-grants') {
        return Promise.resolve({ data: {
          grant_token: 'manage-grant',
          scope: body?.scope ?? 'payment_sources.manage',
          expires_at: new Date(Date.now() + 10 * 60 * 1000).toISOString(),
          one_time: body?.scope !== 'payment_sources.manage',
        } })
      }
      return Promise.resolve({ data: { disconnected: true } })
    })
    renderPage()

    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))

    await user.click(screen.getByRole('button', { name: 'Disconnect Stripe' }))
    await verifyPaymentChange(user)
    const confirmation = await screen.findByRole('alertdialog', { name: 'Disconnect Stripe account?' })
    expect(confirmation).toHaveClass('db-payment-dialog__panel')
    await user.click(within(confirmation).getByRole('button', { name: 'Disconnect Stripe' }))

    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith('/auth/step-up-grants', expect.objectContaining({
        scope: 'payment_sources.stripe.disconnect',
      }))
      expect(apiMocks.post).toHaveBeenCalledWith(
        '/stripe/connect/disconnect',
        undefined,
        { headers: { 'X-Step-Up-Authorization': 'manage-grant' } },
      )
    })
  })

  it('verifies a locked Stripe action before showing the consequence dialog', async () => {
    const user = userEvent.setup()
    apiMocks.post.mockImplementation((path: string, body?: { scope?: string }) => {
      if (path === '/auth/step-up-grants') {
        return Promise.resolve({ data: {
          grant_token: 'one-time-stripe-grant',
          scope: body?.scope ?? 'payment_sources.stripe.disconnect',
          expires_at: new Date(Date.now() + 2 * 60 * 1000).toISOString(),
          one_time: true,
        } })
      }
      return Promise.resolve({ data: { disconnected: true } })
    })
    renderPage()

    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))
    await user.click(screen.getByRole('button', { name: 'Disconnect Stripe' }))

    expect(screen.queryByRole('alertdialog', { name: 'Disconnect Stripe account?' })).not.toBeInTheDocument()
    const stepUp = await screen.findByRole('alertdialog', { name: 'Verify Stripe disconnection' })
    expect(apiMocks.post).not.toHaveBeenCalledWith('/stripe/connect/disconnect', expect.anything(), expect.anything())
    await user.type(within(stepUp).getByLabelText('Your current password'), 'fresh-password')
    await user.click(within(stepUp).getByRole('button', { name: 'Verify and continue' }))

    const confirmation = await screen.findByRole('alertdialog', { name: 'Disconnect Stripe account?' })
    expect(confirmation).toHaveClass('db-payment-dialog__panel')
    expect(apiMocks.post).not.toHaveBeenCalledWith('/stripe/connect/disconnect', expect.anything(), expect.anything())
    await user.click(within(confirmation).getByRole('button', { name: 'Disconnect Stripe' }))

    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith('/auth/step-up-grants', {
        password: 'fresh-password',
        scope: 'payment_sources.stripe.disconnect',
        target_tenant_id: null,
      })
      expect(apiMocks.post).toHaveBeenCalledWith(
        '/stripe/connect/disconnect',
        undefined,
        { headers: { 'X-Step-Up-Authorization': 'one-time-stripe-grant' } },
      )
    })
  })

  it('dismisses locked payment-source verification with Escape before any mutation', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))
    await user.click(screen.getByRole('button', { name: 'Disconnect Stripe' }))
    await screen.findByRole('alertdialog', { name: 'Verify Stripe disconnection' })

    await user.keyboard('{Escape}')

    expect(screen.queryByRole('alertdialog', { name: 'Verify Stripe disconnection' })).not.toBeInTheDocument()
    expect(apiMocks.post).not.toHaveBeenCalledWith('/stripe/connect/disconnect', expect.anything(), expect.anything())
  })

  it('verifies a locked QuickBooks action before showing its themed consequence dialog', async () => {
    const user = userEvent.setup()
    apiMocks.get.mockImplementation((path: string) => {
      const dataByPath: Record<string, unknown> = {
        '/stripe/connect/status': stripeConnection,
        '/quickbooks/status': {
          ...quickBooksConnection,
          is_connected: true,
          token_health: 'healthy',
        },
        '/admin/garage-profile': garageProfile,
        '/admin/zelle-settings': { zelle_email: 'payments@truckpitstop.com', zelle_phone: null, zelle_qr_image: null },
      }
      return Promise.resolve({ data: dataByPath[path] ?? garageProfile })
    })
    apiMocks.post.mockImplementation((path: string, body?: { scope?: string }) => {
      if (path === '/auth/step-up-grants') {
        return Promise.resolve({ data: {
          grant_token: 'one-time-quickbooks-grant',
          scope: body?.scope ?? 'payment_sources.quickbooks.disconnect',
          expires_at: new Date(Date.now() + 2 * 60 * 1000).toISOString(),
          one_time: true,
        } })
      }
      return Promise.resolve({ data: { disconnected: true } })
    })
    renderPage()

    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))
    await user.click(await screen.findByRole('button', { name: 'Disconnect QuickBooks' }))

    expect(screen.queryByRole('alertdialog', { name: 'Disconnect QuickBooks?' })).not.toBeInTheDocument()
    const stepUp = await screen.findByRole('alertdialog', { name: 'Verify QuickBooks disconnection' })
    expect(stepUp).toHaveClass('db-payment-dialog__panel')
    expect(apiMocks.post).not.toHaveBeenCalledWith('/quickbooks/disconnect', expect.anything(), expect.anything())
    const verifyAction = within(stepUp).getByRole('button', { name: 'Verify and continue' })
    expect(verifyAction).toHaveClass('db-payment-dialog__verify-action')
    expect(verifyAction).toBeDisabled()
    await user.type(within(stepUp).getByLabelText('Your current password'), 'fresh-password')
    expect(verifyAction).toBeEnabled()
    await user.click(verifyAction)

    const confirmation = await screen.findByRole('alertdialog', { name: 'Disconnect QuickBooks?' })
    expect(confirmation).toHaveClass('db-payment-dialog__panel')
    expect(within(confirmation).getByText(/Accounting sync and QuickBooks payment processing will stop/)).toBeInTheDocument()
    expect(apiMocks.post).not.toHaveBeenCalledWith('/quickbooks/disconnect', expect.anything(), expect.anything())
    await user.click(within(confirmation).getByRole('button', { name: 'Disconnect QuickBooks' }))

    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith('/auth/step-up-grants', {
        password: 'fresh-password',
        scope: 'payment_sources.quickbooks.disconnect',
        target_tenant_id: null,
      })
      expect(apiMocks.post).toHaveBeenCalledWith(
        '/quickbooks/disconnect',
        undefined,
        { headers: { 'X-Step-Up-Authorization': 'one-time-quickbooks-grant' } },
      )
    })
  })

  it('dismisses the QuickBooks consequence dialog without mutation from every safe exit', async () => {
    const user = userEvent.setup()
    apiMocks.get.mockImplementation((path: string) => Promise.resolve({ data: {
      '/stripe/connect/status': stripeConnection,
      '/quickbooks/status': { ...quickBooksConnection, is_connected: true, token_health: 'healthy' },
      '/admin/garage-profile': garageProfile,
      '/admin/zelle-settings': { zelle_email: 'payments@truckpitstop.com', zelle_phone: null, zelle_qr_image: null },
    }[path] ?? garageProfile }))
    renderPage()

    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))

    const openConfirmation = async () => {
      await user.click(await screen.findByRole('button', { name: 'Disconnect QuickBooks' }))
      await verifyPaymentChange(user)
      return screen.findByRole('alertdialog', { name: 'Disconnect QuickBooks?' })
    }

    await openConfirmation()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('alertdialog', { name: 'Disconnect QuickBooks?' })).not.toBeInTheDocument()

    const backdropDialog = await openConfirmation()
    fireEvent.mouseDown(backdropDialog.parentElement as HTMLElement)
    expect(screen.queryByRole('alertdialog', { name: 'Disconnect QuickBooks?' })).not.toBeInTheDocument()

    const closeDialog = await openConfirmation()
    await user.click(within(closeDialog).getByRole('button', { name: 'Close confirmation' }))
    expect(screen.queryByRole('alertdialog', { name: 'Disconnect QuickBooks?' })).not.toBeInTheDocument()
    expect(apiMocks.post).not.toHaveBeenCalledWith('/quickbooks/disconnect', expect.anything(), expect.anything())
  })

  it('locks the shared consequence dialog while Stripe disconnection is pending', async () => {
    const user = userEvent.setup()
    let finishDisconnect: ((value: { data: { disconnected: boolean } }) => void) | undefined
    apiMocks.post.mockImplementation((path: string, body?: { scope?: string }) => {
      if (path === '/auth/step-up-grants') {
        return Promise.resolve({ data: {
          grant_token: 'manage-grant',
          scope: body?.scope ?? 'payment_sources.manage',
          expires_at: new Date(Date.now() + 2 * 60 * 1000).toISOString(),
          one_time: true,
        } })
      }
      if (path === '/stripe/connect/disconnect') {
        return new Promise((resolve) => { finishDisconnect = resolve })
      }
      return Promise.resolve({ data: {} })
    })
    renderPage()

    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))
    await user.click(screen.getByRole('button', { name: 'Disconnect Stripe' }))
    await verifyPaymentChange(user)
    const confirmation = await screen.findByRole('alertdialog', { name: 'Disconnect Stripe account?' })
    await user.click(within(confirmation).getByRole('button', { name: 'Disconnect Stripe' }))

    await waitFor(() => {
      const pendingDialog = screen.getByRole('alertdialog', { name: 'Disconnect Stripe account?' })
      expect(within(pendingDialog).getByRole('button', { name: 'Disconnecting...' })).toBeDisabled()
      expect(within(pendingDialog).getByRole('button', { name: 'Cancel' })).toBeDisabled()
      expect(within(pendingDialog).getByRole('button', { name: 'Close confirmation' })).toBeDisabled()
    })
    await user.keyboard('{Escape}')
    expect(screen.getByRole('alertdialog', { name: 'Disconnect Stripe account?' })).toBeInTheDocument()

    finishDisconnect?.({ data: { disconnected: true } })
    await waitFor(() => {
      expect(screen.queryByRole('alertdialog', { name: 'Disconnect Stripe account?' })).not.toBeInTheDocument()
    })
  })

  it('explains the migration consequence for a legacy Stripe connection', async () => {
    const user = userEvent.setup()
    apiMocks.get.mockImplementation((path: string) => Promise.resolve({ data: {
      '/stripe/connect/status': { ...stripeConnection, connection_type: 'express_legacy' },
      '/quickbooks/status': quickBooksConnection,
      '/admin/garage-profile': garageProfile,
      '/admin/zelle-settings': { zelle_email: 'payments@truckpitstop.com', zelle_phone: null, zelle_qr_image: null },
    }[path] ?? garageProfile }))
    renderPage()

    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))
    await user.click(screen.getByRole('button', { name: 'Disconnect Legacy Connection' }))
    await verifyPaymentChange(user)
    const confirmation = await screen.findByRole('alertdialog', { name: 'Disconnect legacy Stripe connection?' })
    expect(within(confirmation).getByText('After disconnecting, you can set up the new Stripe-hosted connection.')).toBeInTheDocument()
  })

  it('verifies QuickBooks connect and requests fresh verification after a rejected Zelle change', async () => {
    const user = userEvent.setup()
    apiMocks.get.mockImplementation((path: string) => {
      const dataByPath: Record<string, unknown> = {
        '/stripe/connect/status': stripeConnection,
        '/quickbooks/status': quickBooksConnection,
        '/admin/garage-profile': garageProfile,
        '/admin/zelle-settings': { zelle_email: 'payments@truckpitstop.com', zelle_phone: null, zelle_qr_image: null },
      }
      return Promise.resolve({ data: dataByPath[path] ?? garageProfile })
    })
    apiMocks.post.mockImplementation((path: string) => {
      if (path === '/auth/step-up-grants') {
        return Promise.resolve({ data: {
          grant_token: 'manage-grant',
          scope: 'payment_sources.manage',
          expires_at: new Date(Date.now() + 10 * 60 * 1000).toISOString(),
          one_time: false,
        } })
      }
      if (path === '/quickbooks/connect') return new Promise(() => {})
      return Promise.resolve({ data: {} })
    })
    apiMocks.put.mockRejectedValue({
      response: {
        status: 428,
        data: { detail: { required_scope: 'payment_sources.manage', message: 'Verify again.' } },
      },
    })
    renderPage()

    await user.click(screen.getByRole('button', { name: 'Payments & Accounting' }))

    await user.click(screen.getByRole('button', { name: /QuickBooks Online/i }))
    await user.click(await screen.findByRole('button', { name: 'Connect My QuickBooks' }))
    await verifyPaymentChange(user)
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith(
      '/quickbooks/connect',
      undefined,
      { headers: { 'X-Step-Up-Authorization': 'manage-grant' } },
    ))

    await user.click(screen.getByRole('button', { name: /Zelle Payments/i }))
    const email = await screen.findByLabelText('Zelle Email')
    await user.clear(email)
    await user.type(email, 'retry@truckpitstop.com')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(apiMocks.put).not.toHaveBeenCalled()
    await verifyPaymentChange(user)
    await waitFor(() => expect(apiMocks.put).toHaveBeenCalled())
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alertdialog', { name: 'Verify Zelle contact changes' })).toBeInTheDocument()
    expect(apiMocks.post.mock.calls.filter(([path]) => path === '/auth/step-up-grants')).toHaveLength(2)
  })
})
