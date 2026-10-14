import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import PriceBuilderPanel from '../PriceBuilderPanel'
import type { WorkHoldOrder } from '../staffHold'
import type { ComponentProps } from 'react'
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
const order: WorkHoldOrder = { id: 'order-a', order_number: 'QA115', status: 'in_progress', hold_reason: null, held_at: null, updated_at: '2026-10-14T00:30:00.123456Z', is_internal: false }
const summary = { order_id: order.id, labor_total: '0.00', parts_total: '0.00', total_cost: '0.00', pricing_locked: false, can_edit_work: true, lines: [], warnings: [] }
function mount(current = order, props: Partial<ComponentProps<typeof PriceBuilderPanel>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const view = (value: WorkHoldOrder) => <QueryClientProvider client={client}><PriceBuilderPanel {...props} orderId={value.id} orderStatus={value.status} canEdit workHoldOrder={value} workflowInfo={{ created_at: value.updated_at, hold_reason: value.hold_reason }} /></QueryClientProvider>
  const result = render(view(current))
  return { change: (next: WorkHoldOrder) => result.rerender(view(next)) }
}
beforeAll(() => {
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    unobserve() {}
    disconnect() {}
  })
})
afterAll(() => vi.unstubAllGlobals())
beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({ user: { id: 'owner-a', tenant_id: 'tenant-a', role: 'garage_owner' } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']> })
  api.get.mockImplementation((url: string) => Promise.resolve({ data: url.endsWith('/price-build') ? summary : url.endsWith('/operations') ? { items: [], summary: { tracked: 0, completed: 0, remaining: 0, legacy_untracked: 0 }, order_status: 'in_progress', is_order_lead: false } : [] }))
})
afterEach(() => { vi.restoreAllMocks(); useAuthStore.setState({ user: null }) })
it('keeps the desktop hold action in the footer and stops offering it when finalized', async () => {
  const view = mount(); const user = userEvent.setup()
  const hold = await screen.findByRole('button', { name: 'Put on hold', exact: true })
  expect(hold.closest('.db-workspace-footer')).not.toBeNull()
  await user.click(hold); expect(screen.getByRole('dialog', { name: 'Put order on hold' })).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Close hold dialog' }))
  view.change({ ...order, status: 'completed' })
  expect(screen.queryByRole('button', { name: 'Put on hold' })).not.toBeInTheDocument()
  expect(api.post).not.toHaveBeenCalled()
})
it('opens from mobile More, returns focus there, and exposes release directly with a visible reason', async () => {
  vi.spyOn(window, 'matchMedia').mockImplementation(query => ({ matches: query.includes('max-width'), media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn() }))
  const view = mount(); const user = userEvent.setup()
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Put on hold' })).not.toBeInTheDocument())
  const more = screen.getByRole('button', { name: 'Repair order actions', exact: true })
  await user.click(more); await user.click(await screen.findByRole('button', { name: 'Put on hold', exact: true }))
  expect(screen.getByRole('dialog', { name: 'Put order on hold' })).toBeVisible()
  await user.keyboard('{Escape}')
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  await waitFor(() => expect(more).toHaveFocus())
  view.change({ ...order, hold_reason: 'waiting_for_parts', held_at: order.updated_at })
  expect(screen.getByRole('button', { name: 'Release hold', exact: true })).toBeVisible()
  expect(screen.getByText(/· Waiting for parts/)).toBeVisible()
  expect(api.post).not.toHaveBeenCalled()
})
it('does not expose a hold action after the pricing contract locks work', async () => {
  api.get.mockImplementation((url: string) => Promise.resolve({ data: url.endsWith('/price-build') ? { ...summary, pricing_locked: true, can_edit_work: false } : [] }))
  mount()
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Put on hold' })).not.toBeInTheDocument())
})

it.each([false, true])('disarms an open completion confirmation when held (internal=%s)', async internal => {
  const complete = vi.fn()
  const view = mount({ ...order, is_internal: internal }, {
    isInternalOrder: internal, onAdminCompleteWork: complete, onCompleteWorkOrder: complete,
  })
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: internal ? 'Finalize & Invoice' : 'Mark Completed', exact: true }))
  expect(screen.getByText(internal ? 'Finalize work order' : 'Mark work completed')).toBeVisible()
  view.change({ ...order, is_internal: internal, hold_reason: 'waiting_for_parts', held_at: order.updated_at })
  expect(screen.queryByText(internal ? 'Finalize work order' : 'Mark work completed')).not.toBeInTheDocument()
  view.change({ ...order, is_internal: internal })
  expect(screen.queryByText(internal ? 'Finalize work order' : 'Mark work completed')).not.toBeInTheDocument()
  expect(complete).not.toHaveBeenCalled()
})
