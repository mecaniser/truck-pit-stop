import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import toast, { Toaster } from 'react-hot-toast'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import GarageAnalyticsPage from '../features/garage/GarageAnalyticsPage'
import { garageOwnerSession } from '../test-fixtures/db035/staffSession'
import api from '../lib/api'
import { useAuthStore } from '../stores/authStore'
import { SessionQueryProvider } from './SessionQueryProvider'

vi.mock('../lib/sessionKeepAlive', () => ({ startSessionKeepAlive: vi.fn(), stopSessionKeepAlive: vi.fn() }))
vi.mock('../contexts/ThemeContext', () => ({ useTheme: () => ({ accentColors: { 500: '#000' } }) }))
afterEach(() => { cleanup(); useAuthStore.getState().clearSession(); vi.restoreAllMocks() })

it('does not reuse a warm inventory report while the next shop is loading', async () => {
  const report = { rows: [{ sku: 'A-PRIVATE', name: 'Shop A private stock', quantity: 1,
    unit_cost: 1, part_value: 1, core_value: 0, total_value: 1 }], total_value: 1, part_value: 1, core_value: 0 }
  const get = vi.spyOn(api, 'get').mockResolvedValueOnce({ data: report }).mockImplementation(() => new Promise(() => {}))
  const store = useAuthStore.getState()
  store.login('a', 'refresh-a', garageOwnerSession)
  render(<SessionQueryProvider><MemoryRouter initialEntries={['/dashboard/garage/analytics?tab=inventory']}>
    <GarageAnalyticsPage /><Toaster />
  </MemoryRouter></SessionQueryProvider>)
  await screen.findAllByText('Shop A private stock')
  act(() => { toast.success('Shop A repair complete') })
  await screen.findByText('Shop A repair complete')
  vi.spyOn(api, 'post').mockResolvedValue({})
  await act(async () => { await store.logout(); store.login('b', 'refresh-b', { ...garageOwnerSession, id: 'b', tenant_id: 'shop-b' }) })
  await waitFor(() => expect(get.mock.calls.length).toBeGreaterThan(1))
  expect(screen.queryAllByText('Shop A private stock')).toHaveLength(0)
  expect(screen.queryByText('Shop A repair complete')).toBeNull()
})
