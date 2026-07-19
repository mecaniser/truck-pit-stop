import { render, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  default: {
    get: apiMocks.get,
  },
}))

vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: vi.fn(),
}))

vi.mock('@/contexts/ThemeContext', () => ({
  useTheme: () => ({ accentColors: { primary: '#2563eb' } }),
}))

import RepairOrdersPage from '../RepairOrdersPage'

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
        <RepairOrdersPage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('RepairOrdersPage request cancellation', () => {
  afterEach(() => {
    apiMocks.get.mockReset()
  })

  it('aborts an in-flight repair-order page request when the page unmounts', async () => {
    let resolveRequest: (() => void) | undefined
    const pendingRequest = new Promise<{ data: { items: []; total: number; has_more: boolean } }>((resolve) => {
      resolveRequest = () => resolve({ data: { items: [], total: 0, has_more: false } })
    })

    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders') return pendingRequest
      return Promise.resolve({ data: url === '/dashboard/stats' ? { mechanic_workload: [] } : { labor_rate: 100 } })
    })

    const { unmount } = renderPage()

    await waitFor(() => {
      expect(apiMocks.get).toHaveBeenCalledWith('/repair-orders', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    })

    const [, config] = apiMocks.get.mock.calls.find(([url]) => url === '/repair-orders')!
    const signal = config.signal as AbortSignal
    expect(signal.aborted).toBe(false)

    unmount()

    await waitFor(() => expect(signal.aborted).toBe(true))
    resolveRequest?.()
  })
})
