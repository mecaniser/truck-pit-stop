import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import CustomerPortalPage from '../CustomerPortalPage'

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: mocks.get, post: mocks.post } }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: () => ({ user: { id: 'customer-user', tenant_id: 'tenant-a', customer_id: 'customer-a', first_name: 'Customer' } }) }))
vi.mock('@/hooks/useTenantBranding', () => ({ default: () => ({ data: { name: 'Sample Shop' } }) }))
vi.mock('@/hooks/useWebSocket', () => ({ useWebSocket: () => undefined }))
vi.mock('@/hooks/useNotificationManager', () => ({ useNotificationManager: () => ({ notify: vi.fn(), banners: [], dismissBanner: vi.fn(), clearBanners: vi.fn() }) }))
vi.mock('@/components/brand/TenantBrandLogo', () => ({ default: () => <span>Sample Shop</span> }))

function renderHistory(path = '/portal/repairs') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Routes><Route path="/portal/*" element={<CustomerPortalPage />} /></Routes></MemoryRouter></QueryClientProvider>)
  return client
}

describe('repair history financial read failures', () => {
  let invoicesFail = false
  const originalScrollTo = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollTo')
  beforeAll(() => Object.defineProperty(HTMLElement.prototype, 'scrollTo', { configurable: true, value: vi.fn() }))
  afterAll(() => {
    if (originalScrollTo) Object.defineProperty(HTMLElement.prototype, 'scrollTo', originalScrollTo)
    else Reflect.deleteProperty(HTMLElement.prototype, 'scrollTo')
  })
  afterEach(() => { cleanup(); vi.restoreAllMocks() })
  beforeEach(() => {
    vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined)
    invoicesFail = false
    mocks.get.mockReset()
    mocks.post.mockReset()
    mocks.get.mockImplementation(async (url: string) => {
      if (url === '/vehicles') return { data: [{ id: 'vehicle-a', make: 'Freightliner', model: 'Cascadia', unit_number: '12' }, { id: 'vehicle-b', make: 'Volvo', model: 'VNR', unit_number: '13' }] }
      if (url === '/repair-orders') return { data: [{ id: 'order-a', vehicle_id: 'vehicle-a', order_number: 'RO-A', description: 'Historical service', status: 'paid', total_cost: '999.99', updated_at: '2026-10-20T12:00:00Z' }] }
      if (url === '/invoices') {
        if (invoicesFail) throw new Error('Invoice read unavailable')
        return { data: [{ id: 'invoice-a', repair_order_id: 'order-a', total_amount: '123.45', status: 'paid' }] }
      }
      throw new Error(`Unexpected read: ${url}`)
    })
  })

  it('hides cached invoice amounts and PDF after a failed refetch, then restores them only after retry succeeds', async () => {
    const client = renderHistory()
    expect(await screen.findByText('$123.45')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Download invoice for/ })).toHaveAttribute('href', '/api/v1/invoices/invoice-a/pdf')
    expect(screen.queryByText('$999.99')).not.toBeInTheDocument()
    expect(screen.queryByText(/paid (this year|ytd)/i)).not.toBeInTheDocument()

    invoicesFail = true
    await act(async () => { await client.refetchQueries({ queryKey: ['customer-history-invoices', 'tenant-a', 'customer-a'] }) })
    expect(await screen.findByText('Invoice amounts couldn’t load.')).toBeInTheDocument()
    expect(screen.getByText('Historical service')).toBeInTheDocument()
    expect(screen.getByText('Amount unavailable')).toBeInTheDocument()
    expect(screen.queryByText('$123.45')).not.toBeInTheDocument()
    expect(screen.queryByText('$999.99')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Download invoice for/ })).not.toBeInTheDocument()
    expect(screen.queryByText(/paid (this year|ytd)/i)).not.toBeInTheDocument()

    invoicesFail = false
    await userEvent.setup().click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(screen.queryByText('Invoice amounts couldn’t load.')).not.toBeInTheDocument())
    expect(screen.getByText('$123.45')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Download invoice for/ })).toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })

  it('shows an unavailable amount on an initial invoice failure instead of using the repair-order total', async () => {
    invoicesFail = true
    renderHistory()
    expect(await screen.findByText('Invoice amounts couldn’t load.')).toBeInTheDocument()
    expect(screen.getByText('Amount unavailable')).toBeInTheDocument()
    expect(screen.queryByText('$999.99')).not.toBeInTheDocument()
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Download invoice for/ })).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('separates details and download controls and places booking beside vehicle scope', async () => {
    renderHistory('/portal/repairs?vehicle_id=vehicle-a')
    const details = await screen.findByRole('button', { name: 'View repair RO-A' })
    const download = screen.getByRole('link', { name: 'Download invoice for RO-A' })
    expect(details.contains(download)).toBe(false)
    expect(download.closest('article')).toBe(details.closest('article'))
    expect(download).toHaveAttribute('download')
    expect(screen.getByRole('link', { name: 'Book a service' })).toHaveAttribute('href', '/portal/services?vehicle_id=vehicle-a')
    expect(screen.getByRole('combobox', { name: 'Vehicle scope' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'All', exact: true })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.setup().click(screen.getByRole('button', { name: 'Cancelled', exact: true }))
    expect(screen.getByRole('button', { name: 'Cancelled', exact: true })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByRole('button', { name: 'View repair RO-A' })).not.toBeInTheDocument()
  })

  it('clears vehicle scope without losing the Current repairs destination', async () => {
    renderHistory('/portal/repairs?vehicle_id=vehicle-a&view=active')
    expect(await screen.findByRole('heading', { name: 'Active repairs' })).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: 'All vehicles', exact: true }))
    expect(screen.getByRole('heading', { name: 'Active repairs' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Book a service' })).toHaveAttribute('href', '/portal/services')
  })

  it('recovers an unknown portal route without a blank page', async () => {
    renderHistory('/portal/missing-page?vehicle_id=vehicle-a')
    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to Home' })).toHaveAttribute('href', '/portal?vehicle_id=vehicle-a')
    expect(mocks.post).not.toHaveBeenCalled()
  })

})
