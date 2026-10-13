import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: apiMocks }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ accentColors: { 400: '#22d3ee', 500: '#06b6d4', 600: '#0891b2' } }) }))
vi.mock('@/hooks/useTenantBranding', () => ({ default: () => ({ data: { name: 'Test Shop', logo_url: null } }) }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (selector: (state: { user: { id: string; tenant_id: string } }) => unknown) => selector({ user: { id: 'owner', tenant_id: 'tenant-1' } }) }))
vi.mock('../PartsInventoryWorkspace', () => ({ PartsInventoryGate: ({ legacy }: { legacy: ReactNode }) => legacy }))
vi.mock('@/components/SlidePanelForm', () => ({ default: ({ isOpen, title }: { isOpen: boolean; title: string }) => isOpen ? <div role="dialog" aria-label={title} /> : null }))

import InventoryPage from '../InventoryPage'

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="inventory-location">{location.search}</output>
}
function renderPage() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={['/dashboard/garage/inventory?filter=stock&selected=part-44']}><InventoryPage /><LocationProbe /></MemoryRouter></QueryClientProvider>)
}
afterEach(() => vi.resetAllMocks())

describe('legacy inventory search deep links', () => {
  it('opens an item directly even when it is absent from the catalog response', async () => {
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/inventory/part-44') return Promise.resolve({ data: { id: 'part-44', name: 'Air filter', sku: 'AF-44', stock_quantity: 0, on_order_quantity: 0, reorder_level: 0, cost: '10', selling_price: '20', unit_type: 'each' } })
      if (url === '/inventory/sync-status') return Promise.resolve({ data: {} })
      return Promise.resolve({ data: { items: [], has_more: false } })
    })
    renderPage()
    expect(await screen.findByRole('dialog', { name: 'Air filter' })).toBeInTheDocument()
    expect(apiMocks.get).toHaveBeenCalledWith('/inventory/part-44', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    await waitFor(() => expect(screen.getByTestId('inventory-location')).toHaveTextContent('?filter=stock'))
    expect(screen.getByTestId('inventory-location')).not.toHaveTextContent('selected=')
    expect(apiMocks.post).not.toHaveBeenCalled()
    expect(apiMocks.put).not.toHaveBeenCalled()
  })

  it('handles a missing or inaccessible linked item without opening an unrelated record', async () => {
    apiMocks.get.mockImplementation((url: string) => url === '/inventory/part-44' ? Promise.reject({ response: { status: 403 } }) : Promise.resolve({ data: { items: [], has_more: false } }))
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('That inventory item is unavailable with your current access.')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
