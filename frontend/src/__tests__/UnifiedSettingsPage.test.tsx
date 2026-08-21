import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { useAuthStore } from '../stores/authStore'

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
    apiMocks.get.mockImplementation((path: string) => {
      const dataByPath: Record<string, unknown> = {
        '/stripe/connect/status': stripeConnection,
        '/quickbooks/status': quickBooksConnection,
        '/admin/garage-profile': garageProfile,
        '/admin/zelle-settings': { zelle_email: 'payments@truckpitstop.com', zelle_phone: null, zelle_qr_image: null },
      }
      return Promise.resolve({ data: dataByPath[path] ?? garageProfile })
    })
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
})
