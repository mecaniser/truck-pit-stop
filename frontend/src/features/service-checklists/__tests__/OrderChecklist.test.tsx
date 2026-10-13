import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import OrderChecklist from '../OrderChecklist'
import { openChecklistOnCompletionError } from '../queries'
import type { OrderChecklistItem, OrderChecklistPage } from '../types'

const mocks = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: mocks }))
const task: OrderChecklistItem = { id: 'task-a', labor_id: 'labor-a', service_name: 'Oil service', label: 'Check for leaks', required: true, position: 0, is_completed: false, completed_at: null, completed_by: null, version: 1 }
const page = (items = [task], overrides: Partial<OrderChecklistPage> = {}): OrderChecklistPage => ({ items, total: items.length, skip: 0, limit: 100, summary: { total: items.length, completed: 0, required: 1, required_remaining: 1 }, can_update: true, ...overrides })
function setUser(tenant = 'tenant-a', role = 'garage_owner', id = 'owner-a') {
  useAuthStore.setState({ user: { id, tenant_id: tenant, role, is_active: true } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']> })
}
function mount(order = 'order-a') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const view = render(<QueryClientProvider client={client}><OrderChecklist orderId={order} /></QueryClientProvider>)
  return { client, ...view, changeOrder: (id: string) => view.rerender(<QueryClientProvider client={client}><OrderChecklist orderId={id} /></QueryClientProvider>) }
}
beforeEach(() => { vi.clearAllMocks(); setUser(); mocks.get.mockResolvedValue({ data: page() }) })
describe('persisted work checklists', () => {
  it('waits for persistence and renders server attribution; a failed reopen keeps the saved check', async () => {
    const user = userEvent.setup()
    let resolve!: () => void
    mocks.patch.mockImplementationOnce(() => new Promise<void>(done => { resolve = done }))
    mount()
    const check = await screen.findByRole('checkbox', { name: 'Check for leaks' })
    await user.click(check)
    expect(check).not.toBeChecked()
    expect(check).toBeDisabled()
    expect(mocks.patch).toHaveBeenCalledWith('/repair-orders/order-a/checklist/task-a', { is_completed: true, expected_version: 1 })
    mocks.get.mockResolvedValue({ data: page([{ ...task, is_completed: true, completed_at: '2026-10-12T12:00:00Z', completed_by: { id: 'mechanic-a', name: 'Casey Mechanic' }, version: 2 }], { summary: { total: 1, completed: 1, required: 1, required_remaining: 0 } }) })
    await act(async () => resolve())
    await screen.findByText(/Casey Mechanic/)
    await waitFor(() => expect(check).toBeEnabled())
    expect(check).toBeChecked()
    mocks.patch.mockRejectedValueOnce({ response: { status: 500 } })
    await user.click(check)
    await screen.findByText('Task was not saved. Try again.')
    expect(check).toBeChecked()
  })
  it('refreshes a stale task without replaying the operator mutation', async () => {
    const user = userEvent.setup(); mount()
    const check = await screen.findByRole('checkbox', { name: 'Check for leaks' })
    mocks.patch.mockRejectedValue({ response: { status: 409, data: { detail: 'This task changed. Refresh the checklist and try again.' } } })
    mocks.get.mockResolvedValue({ data: page([{ ...task, version: 3 }]) })
    await user.click(check)
    await screen.findByRole('alert')
    await waitFor(() => expect(check).toBeEnabled())
    expect(mocks.patch).toHaveBeenCalledTimes(1)
    await user.click(check)
    expect(mocks.patch).toHaveBeenLastCalledWith('/repair-orders/order-a/checklist/task-a', { is_completed: true, expected_version: 3 })
  })
  it('shows complete-scope counts while paging and distinguishes optional/frozen work', async () => {
    const user = userEvent.setup()
    const items = Array.from({ length: 100 }, (_, i) => ({ ...task, id: `task-${i}`, label: `Check ${i}` }))
    const summary = { total: 101, completed: 0, required: 100, required_remaining: 100 }
    mocks.get.mockImplementation((_url, config) => Promise.resolve({ data: config.params.skip === 100
      ? page([{ ...task, id: 'last', label: 'Record filter brand', required: false }], { skip: 100, total: 101, summary, can_update: false })
      : page(items, { total: 101, summary, can_update: false }) }))
    mount()
    await screen.findByText('100 required remaining')
    expect(screen.getAllByRole('checkbox')[0]).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Load more tasks' }))
    await screen.findByText('Record filter brand')
    expect(screen.getByText('Optional')).toBeVisible()
    expect(screen.getByText('Checklist · 0/101')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Load more tasks' })).not.toBeInTheDocument()
  })
  it('isolates tenant and order switches, ignoring late responses from a prior scope', async () => {
    let resolve!: (value: unknown) => void
    mocks.get.mockImplementationOnce(() => new Promise(done => { resolve = done }))
    const view = mount()
    act(() => setUser('tenant-b'))
    mocks.get.mockResolvedValue({ data: page([{ ...task, label: 'Tenant B task' }]) })
    view.changeOrder('order-b')
    await screen.findByText('Tenant B task')
    await act(async () => resolve({ data: page([{ ...task, label: 'Private tenant A task' }]) }))
    expect(screen.queryByText('Private tenant A task')).not.toBeInTheDocument()
    expect(mocks.get).toHaveBeenCalledWith('/repair-orders/order-b/checklist', expect.objectContaining({ signal: expect.any(AbortSignal) }))
  })
  it('opens and refreshes on a server completion refusal; unrelated conflicts do not open it', async () => {
    const user = userEvent.setup(); mount()
    const heading = await screen.findByRole('button', { name: /Checklist/ })
    await user.click(heading)
    const calls = mocks.get.mock.calls.length
    act(() => { expect(openChecklistOnCompletionError({ response: { status: 409, data: { detail: 'Complete the 2 required checklist tasks before finishing this work order.' } } }, 'order-a')).toBe(true) })
    expect(heading).toHaveAttribute('aria-expanded', 'true')
    await waitFor(() => expect(mocks.get.mock.calls.length).toBeGreaterThan(calls))
    expect(openChecklistOnCompletionError({ response: { status: 409, data: { detail: 'Pricing is locked' } } }, 'order-a')).toBe(false)
  })
  it('keeps errors visible instead of suggesting that a failed request cleared the job', async () => {
    mocks.get.mockRejectedValue(new Error('Offline')); mount()
    await screen.findByRole('alert')
    expect(screen.queryByText(/0 required remaining/)).not.toBeInTheDocument()
  })
  it('rejects an unexpected success payload instead of crashing the containing order', async () => {
    mocks.get.mockResolvedValue({ data: { id: 'legacy-order-response' } }); mount()
    await screen.findByRole('alert')
    expect(screen.queryByText(/0 required remaining/)).not.toBeInTheDocument()
  })
  it('does not fetch or render internal work for customer roles', () => {
    setUser('tenant-a', 'customer'); mount()
    expect(mocks.get).not.toHaveBeenCalled()
    expect(screen.queryByRole('region')).not.toBeInTheDocument()
  })
  it('requires explicit per-task execution permission for mechanics on mixed-assignment jobs', async () => {
    setUser('tenant-a', 'mechanic', 'helper-a')
    mocks.get.mockResolvedValue({ data: page([
      { ...task, id: 'mine', label: 'My inspection', can_update: true },
      { ...task, id: 'other', label: 'Other technician inspection', can_update: false },
      { ...task, id: 'unknown', label: 'Permission unavailable' },
    ], { summary: { total: 3, completed: 0, required: 3, required_remaining: 3 } }) })
    mount()
    expect(await screen.findByRole('checkbox', { name: 'My inspection' })).toBeEnabled()
    expect(screen.getByRole('checkbox', { name: 'Other technician inspection' })).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: 'Permission unavailable' })).toBeDisabled()
  })
})
