import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
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

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
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
