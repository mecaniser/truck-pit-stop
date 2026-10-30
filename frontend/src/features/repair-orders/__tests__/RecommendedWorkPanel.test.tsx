import type { ComponentProps } from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import RecommendedWorkPanel from '../RecommendedWorkPanel'

const mocks = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn(),
  user: { id: 'user-a', tenant_id: 'tenant-a', role: 'garage_owner' },
}))
vi.mock('@/lib/api', () => ({ default: mocks }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (selector: (state: { user: typeof mocks.user }) => unknown) => selector({ user: mocks.user }) }))

const sourceId = '00000000-0000-4000-8000-000000000099'
const item = (id = 1, description = 'Inspect left rear seal') => ({
  id: `00000000-0000-4000-8000-${String(id).padStart(12, '0')}`, description, priority: 'urgent', created_at: '2026-09-10T14:00:00Z',
  vehicle: { id: '00000000-0000-4000-8000-000000000098', unit_number: '031', year: 2022, make: 'Freightliner', model: 'Cascadia' },
  source_order: { id: sourceId, order_number: 'RO-0101', status: 'paid', created_at: '2026-09-09T14:00:00Z' },
})
const page = (items = [item()], total = items.length, skip = 0) => ({ data: { items, total, skip, limit: 25 } })

function Location() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}</output>
}

function setup(props: ComponentProps<typeof RecommendedWorkPanel> = { vehicleId: 'truck-a', customerId: 'customer-a', contextOrderId: 'current-a' }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const content = (nextProps: typeof props) => <QueryClientProvider client={client}><MemoryRouter>
    <RecommendedWorkPanel {...nextProps} /><Location />
  </MemoryRouter></QueryClientProvider>
  const result = render(content(props))
  return { ...result, client, change: (nextProps: typeof props) => result.rerender(content(nextProps)) }
}

beforeEach(() => {
  mocks.user = { id: 'user-a', tenant_id: 'tenant-a', role: 'garage_owner' }
  mocks.get.mockResolvedValue(page())
})
afterEach(() => vi.clearAllMocks())

describe('truck recommendation continuity', () => {
  it('labels customer truck recommendations without implying a current RO or enabling conversion', async () => {
    mocks.get.mockResolvedValueOnce(page([]))
    setup({ vehicleId: 'truck-a', customerId: 'customer-a', noCurrentOrder: true, canConvert: false })
    expect(await screen.findByText('No open recommendations from repair orders.')).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Recommendations from repair orders' })).toBeVisible()
    expect(screen.queryByRole('button', { name: /add|convert|resolve|delete/i })).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('sends all context filters and cancellation signal, renders reduced work and navigates to the source', async () => {
    const { client } = setup()
    expect(await screen.findByText('Inspect left rear seal')).toBeInTheDocument()
    expect(screen.getByText('urgent')).toBeInTheDocument()
    expect(screen.getByText('Recorded Sep 10, 2026')).toBeInTheDocument()
    expect(mocks.get).toHaveBeenCalledWith('/repair-orders/recommended-work', {
      params: { vehicle_id: 'truck-a', customer_id: 'customer-a', context_order_id: 'current-a', skip: 0, limit: 25 }, signal: expect.any(AbortSignal),
    })
    expect(client.getQueryCache().getAll()[0].queryKey).toEqual(['recommended-work', 'tenant-a', 'truck-a', 'customer-a', 'current-a', 0, 25])
    const link = screen.getByRole('link', { name: 'Open source order RO-0101' })
    expect(link).toHaveAttribute('href', `/dashboard/repair-orders?selected=${sourceId}&recommendation=${item().id}`)
    fireEvent.click(link)
    expect(screen.getByTestId('location')).toHaveTextContent(`/dashboard/repair-orders?selected=${sourceId}&recommendation=${item().id}`)
    expect(screen.queryByRole('button', { name: /add|convert|resolve|delete/i })).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
    expect(mocks.patch).not.toHaveBeenCalled()
    expect(mocks.delete).not.toHaveBeenCalled()
  })

  it.each(['mechanic', 'fleet_manager', 'customer', 'driver', 'super_admin'])('does not expose or request data for %s', (role) => {
    mocks.user.role = role
    setup()
    expect(screen.queryByRole('region')).not.toBeInTheDocument()
    expect(mocks.get).not.toHaveBeenCalled()
  })

  it.each(['garage_owner', 'garage_admin', 'receptionist'])('allows %s', async (role) => {
    mocks.user.role = role
    setup()
    expect(await screen.findByText('Inspect left rear seal')).toBeInTheDocument()
  })

  it('distinguishes pending, failed and empty results with retry', async () => {
    let reject!: (reason: Error) => void
    mocks.get.mockImplementationOnce(() => new Promise((_resolve, rejectPromise) => { reject = rejectPromise }))
    setup()
    expect(screen.getByText('Loading recommendations…')).toBeInTheDocument()
    await act(async () => reject(new Error('unavailable')))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load recommendations.')
    expect(screen.queryByText('No open recommendations on other orders.')).not.toBeInTheDocument()
    mocks.get.mockResolvedValueOnce(page([]))
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('No open recommendations on other orders.')).toBeInTheDocument()
  })

  it.each([
    ['null body', null],
    ['legacy list', []],
    ['string body', 'unavailable'],
    ['missing items', { total: 0, skip: 0, limit: 25 }],
    ['non-array items', { ...page().data, items: {} }],
    ['null row', { ...page().data, items: [null] }],
    ['missing source order', { ...page().data, items: [{ ...item(), source_order: undefined }] }],
    ['malformed source id', { ...page().data, items: [{ ...item(), source_order: { ...item().source_order, id: 'invalid' } }] }],
    ['invalid recorded date', { ...page().data, items: [{ ...item(), created_at: 'not-a-date' }] }],
    ['invalid source date', { ...page().data, items: [{ ...item(), source_order: { ...item().source_order, created_at: 'not-a-date' } }] }],
    ['object description', { ...page().data, items: [{ ...item(), description: { text: 'unsafe' } }] }],
    ['unknown priority', { ...page().data, items: [{ ...item(), priority: 'unknown' }] }],
    ['missing vehicle', { ...page().data, items: [{ ...item(), vehicle: undefined }] }],
    ['missing total', { items: [], skip: 0, limit: 25 }],
    ['negative count', { items: [], total: -1, skip: 0, limit: 25 }],
    ['string count', { items: [], total: '0', skip: 0, limit: 25 }],
    ['mismatched page offset', { ...page().data, skip: 25 }],
    ['wrong page size', { ...page().data, limit: 100 }],
    ['false empty count', { ...page().data, total: 0 }],
  ])('shows unavailable for a malformed HTTP 200: %s', async (_label, data) => {
    mocks.get.mockResolvedValueOnce({ data })
    setup()
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load recommendations.')
    expect(screen.queryByText('No open recommendations on other orders.')).not.toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeEnabled()
  })

  it('removes an earlier empty result when its refresh response is malformed', async () => {
    mocks.get.mockResolvedValueOnce(page([]))
    setup()
    await screen.findByText('No open recommendations on other orders.')
    mocks.get.mockResolvedValueOnce({ data: [] })
    fireEvent.click(screen.getByRole('button', { name: 'Refresh recommendations' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not refresh recommendations.')
    expect(screen.queryByText('No open recommendations on other orders.')).not.toBeInTheDocument()
  })

  it('retains a validated page with an unavailable notice after a malformed refresh', async () => {
    setup()
    await screen.findByText('Inspect left rear seal')
    mocks.get.mockResolvedValueOnce({ data: { total: 0 } })
    fireEvent.click(screen.getByRole('button', { name: 'Refresh recommendations' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not refresh recommendations. Showing the last loaded page.')
    expect(screen.getByText('Inspect left rear seal')).toBeInTheDocument()
    expect(screen.queryByText('No open recommendations on other orders.')).not.toBeInTheDocument()
  })

  it('pages beyond 25, retains distinct recommendations with matching descriptions and permits a failed-page retry', async () => {
    mocks.get.mockResolvedValueOnce(page(Array.from({ length: 25 }, (_, i) => item(i + 1)), 27))
    const { client } = setup()
    expect(await screen.findByText('1–25 of 27')).toBeInTheDocument()
    expect(screen.getAllByText('Inspect left rear seal')).toHaveLength(25)
    mocks.get.mockRejectedValueOnce(new Error('offline'))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load recommendations.')
    expect(screen.queryByText('Inspect left rear seal')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Previous' })).toBeEnabled()
    mocks.get.mockResolvedValueOnce(page([item(25), item(26)], 27, 25))
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('26–27 of 27')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
    expect(client.getQueryCache().getAll()[1].queryKey).toEqual(['recommended-work', 'tenant-a', 'truck-a', 'customer-a', 'current-a', 25, 25])
  })

  it('cancels old context and never shows a late response after switching truck/order/customer', async () => {
    let resolveOld!: (value: ReturnType<typeof page>) => void
    mocks.get.mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve }))
    const view = setup()
    const oldSignal = mocks.get.mock.calls[0][1].signal as AbortSignal
    mocks.get.mockResolvedValueOnce(page([item(101, 'New truck recommendation')]))
    view.change({ vehicleId: 'truck-b', customerId: 'customer-b', contextOrderId: 'current-b' })
    expect(oldSignal.aborted).toBe(true)
    expect(await screen.findByText('New truck recommendation')).toBeInTheDocument()
    await act(async () => resolveOld(page()))
    expect(screen.queryByText('Inspect left rear seal')).not.toBeInTheDocument()
    expect(view.client.getQueryCache().getAll().some(query => JSON.stringify(query.queryKey) === JSON.stringify(['recommended-work', 'tenant-a', 'truck-b', 'customer-b', 'current-b', 0, 25]))).toBe(true)
  })

  it('clears displayed data immediately and resets the page when context changes', async () => {
    mocks.get.mockResolvedValueOnce(page([item()], 26))
    const view = setup()
    await screen.findByText('Inspect left rear seal')
    mocks.get.mockResolvedValueOnce(page([item(26, 'Second page')], 26, 25))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByText('Second page')
    mocks.get.mockImplementationOnce(() => new Promise(() => {}))
    view.change({ vehicleId: 'truck-b', customerId: 'customer-b', contextOrderId: 'current-b' })
    expect(screen.queryByText('Second page')).not.toBeInTheDocument()
    expect(screen.getByText('Loading recommendations…')).toBeInTheDocument()
    expect(mocks.get.mock.calls.at(-1)?.[1].params.skip).toBe(0)
  })

  it('refreshes on return and shared recommendation invalidation', async () => {
    const view = setup()
    await screen.findByText('Inspect left rear seal')
    await act(async () => { await view.client.invalidateQueries({ queryKey: ['recommended-work'] }) })
    expect(mocks.get).toHaveBeenCalledTimes(2)
    view.change({ vehicleId: 'truck-b', customerId: 'customer-b', contextOrderId: 'current-b' })
    await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(3))
    view.change({ vehicleId: 'truck-a', customerId: 'customer-a', contextOrderId: 'current-a' })
    await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(4))
  })
})
