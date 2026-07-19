import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '@/stores/authStore'
import MechanicsPage from '../MechanicsPage'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  default: {
    get: apiMocks.get,
    post: apiMocks.post,
    put: apiMocks.put,
    patch: apiMocks.patch,
    defaults: { headers: { common: {} } },
  },
}))

vi.mock('react-hot-toast', () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('@/contexts/ThemeContext', () => ({
  useTheme: () => ({
    accentColors: { 400: '#22D3EE', 500: '#06B6D4', 600: '#0891B2' },
  }),
}))

vi.mock('@/components/MapboxAddressInput', () => ({
  default: React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement> & { onAddressSelect?: unknown }>(({ onAddressSelect: _onAddressSelect, ...props }, ref) => (
    <input {...props} ref={ref} />
  )),
}))

const mechanic = {
  id: 'mechanic-1',
  email: 'sami@example.com',
  first_name: 'Sami',
  last_name: 'Rivera',
  phone: '(704) 835-2433',
  address: '',
  role: 'mechanic',
  is_active: true,
  tenant_id: 'tenant-1',
  customer_id: null,
  assigned_count: 0,
  in_progress_count: 0,
  available_points: 0,
  total_earned: 0,
  streak_days: 0,
  pending_requests: 0,
  core_hours_target_minutes_override: null,
  shift_start_local_override: null,
  shift_end_local_override: null,
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
        <MechanicsPage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('MechanicsPage technician editing', () => {
  beforeEach(() => {
    apiMocks.get.mockReset()
    apiMocks.post.mockReset()
    apiMocks.put.mockReset()
    apiMocks.patch.mockReset()
    localStorage.clear()

    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/mechanics') return Promise.resolve({ data: [mechanic] })
      if (url === '/admin/staff') return Promise.resolve({ data: [] })
      if (url === '/mechanics/pto-requests/pending') return Promise.resolve({ data: [] })
      return Promise.resolve({ data: [] })
    })
    apiMocks.put.mockResolvedValue({ data: { ...mechanic, phone: '(704) 705-0486' } })

    useAuthStore.setState({
      user: {
        id: 'owner-1',
        email: 'owner@example.com',
        first_name: 'Owner',
        last_name: 'User',
        phone: null,
        role: 'garage_owner',
        is_active: true,
        tenant_id: 'tenant-1',
        customer_id: null,
      },
      token: 'token',
      refreshToken: 'refresh',
      isAuthenticated: true,
    })
  })

  it('submits the hidden-role edit form when updating technician contact details', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: 'Edit' }))
    const phoneInput = screen.getByDisplayValue('(704) 835-2433')
    await user.clear(phoneInput)
    await user.type(phoneInput, '7047050486')
    await user.click(screen.getByRole('button', { name: /update technician/i }))

    await waitFor(() => {
      expect(apiMocks.put).toHaveBeenCalledWith('/mechanics/mechanic-1', expect.objectContaining({
        email: 'sami@example.com',
        phone: '(704) 705-0486',
      }))
    })
  })
})
