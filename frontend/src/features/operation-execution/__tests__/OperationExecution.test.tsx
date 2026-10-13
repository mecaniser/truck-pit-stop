import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import { MechanicOperations, OperationExecutionControls, OperationExecutionFeedback, OperationExecutionStatus } from '../OperationExecution'
import { trackedTimeLabel } from '../format'
import { operationKeys, useOperationExecution, type OperationExecution, type OperationPage } from '../queries'

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
const operation: OperationExecution = {
  labor_id: 'labor-a', description: 'Inspect steering', mechanic_id: null, mechanic_name: null,
  status: 'pending', version: 0, completed_at: null, completed_by: null, tracked_seconds: 0,
  active_session: null, required_tasks_remaining: 0, can_assign: true, can_complete: true,
  can_reopen: false, can_start_timer: false, can_stop_timer: false,
}
function page(item = operation): OperationPage {
  return { items: [item], summary: { tracked: item.status === null ? 0 : 1, completed: item.status === 'completed' ? 1 : 0, remaining: item.status === 'pending' ? 1 : 0, legacy_untracked: item.status === null ? 1 : 0 }, order_status: 'in_progress', is_order_lead: true }
}
const technicians = [{ mechanic_id: 'tech-a', mechanic_name: 'Alex Mechanic' }, { mechanic_id: 'tech-b', mechanic_name: 'Blair Mechanic' }]
function setUser(tenant = 'tenant-a', role = 'garage_owner', id = 'owner-a') {
  useAuthStore.setState({ user: { id, tenant_id: tenant, role, is_active: true } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']> })
}
function Workspace({ order = 'order-a' }: { order?: string }) {
  const query = useOperationExecution(order)
  return <><OperationExecutionFeedback query={query} />{query.data?.items.map(item => <div key={item.labor_id}><OperationExecutionStatus item={item} /><OperationExecutionControls orderId={order} item={item} technicians={technicians} disabled={query.isError || query.isFetching} /></div>)}</>
}
function mount(mechanic = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const view = render(<QueryClientProvider client={client}>{mechanic ? <MechanicOperations orderId="order-a" /> : <Workspace />}</QueryClientProvider>)
  return { client, ...view, changeOrder: (order: string) => view.rerender(<QueryClientProvider client={client}><Workspace order={order} /></QueryClientProvider>) }
}
beforeEach(() => { vi.clearAllMocks(); setUser(); api.get.mockResolvedValue({ data: page() }) })

describe('operation execution', () => {
  it('assigns the operation without starting a timer or changing the order lead, and waits for canonical persistence', async () => {
    const user = userEvent.setup()
    let resolve!: (value: unknown) => void
    api.put.mockImplementation(() => new Promise(done => { resolve = done }))
    mount()
    const select = await screen.findByRole('combobox', { name: 'Technician for Inspect steering' })
    await waitFor(() => expect(select).toBeEnabled())
    await user.selectOptions(select, 'tech-a')
    expect(select).toHaveValue('')
    expect(select).toBeDisabled()
    expect(api.put).toHaveBeenCalledWith('/repair-orders/order-a/operations/labor-a/assignment', { mechanic_id: 'tech-a', expected_version: 0 })
    expect(api.post).not.toHaveBeenCalled()
    const assigned = page({ ...operation, mechanic_id: 'tech-a', mechanic_name: 'Alex Mechanic', version: 1 })
    api.get.mockResolvedValue({ data: assigned })
    await act(async () => resolve({ data: assigned }))
    await waitFor(() => expect(select).toHaveValue('tech-a'))
    expect(screen.getByText('No tracked time')).toBeVisible()
  })
  it('refreshes a stale completion without replaying it or falsely completing the row', async () => {
    const user = userEvent.setup(); mount()
    const complete = await screen.findByRole('button', { name: 'Complete operation' })
    await waitFor(() => expect(complete).toBeEnabled())
    api.put.mockRejectedValue({ response: { status: 409, data: { detail: 'This operation changed. Refresh and try again.' } } })
    api.get.mockResolvedValue({ data: page({ ...operation, version: 3, required_tasks_remaining: 1, can_complete: false }) })
    await user.click(complete)
    await screen.findByText('This operation changed. Refresh and try again.')
    expect(api.put).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('Completed')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Complete operation' })).not.toBeInTheDocument()
    expect(screen.getByText('1 required checklist task remaining.')).toBeVisible()
  })
  it('explicitly enrolls legacy work with its current technician without a reassignment or timer', async () => {
    const legacy = page({ ...operation, status: null, tracked_seconds: null, mechanic_id: 'tech-a', mechanic_name: 'Alex Mechanic', can_complete: false })
    api.get.mockResolvedValue({ data: legacy }); api.put.mockResolvedValue({ data: legacy }); mount()
    const track = await screen.findByRole('button', { name: 'Track operation' })
    await waitFor(() => expect(track).toBeEnabled())
    await userEvent.setup().click(track)
    expect(api.put).toHaveBeenCalledWith('/repair-orders/order-a/operations/labor-a/assignment', { mechanic_id: 'tech-a', expected_version: 0 })
    expect(api.post).not.toHaveBeenCalled()
  })
  it('sends exact session identity when stopping and only presents capabilities granted to a helper', async () => {
    setUser('tenant-a', 'mechanic', 'tech-a')
    const running = page({ ...operation, mechanic_id: 'tech-a', mechanic_name: 'Alex Mechanic', tracked_seconds: 65, can_assign: false, can_complete: false, can_stop_timer: true,
      active_session: { id: 'session-a', mechanic_id: 'tech-a', mechanic_name: 'Alex Mechanic', started_at: '2026-10-13T10:00:00Z' } })
    running.is_order_lead = false
    api.get.mockResolvedValue({ data: running }); api.post.mockResolvedValue({ data: running })
    mount(true)
    const stop = await screen.findByRole('button', { name: 'Stop timer' })
    await waitFor(() => expect(stop).toBeEnabled())
    expect(screen.getByText('Assigned operations')).toBeVisible()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Complete operation' })).not.toBeInTheDocument()
    await userEvent.setup().click(stop)
    expect(api.post).toHaveBeenCalledWith('/repair-orders/order-a/operations/labor-a/timer/stop', { expected_version: 0, session_id: 'session-a' })
  })
  it('distinguishes legacy untracked work, zero recorded time, and actual elapsed time', async () => {
    api.get.mockResolvedValue({ data: page({ ...operation, status: null, tracked_seconds: null, can_complete: false }) }); mount()
    await screen.findByText('Not tracked')
    expect(screen.queryByText('Completed')).not.toBeInTheDocument()
    expect(screen.queryByText('No tracked time')).not.toBeInTheDocument()
    expect(trackedTimeLabel(null)).toBe('Time not tracked')
    expect(trackedTimeLabel(0)).toBe('No tracked time')
    expect(trackedTimeLabel(3660)).toBe('1h 1m tracked')
  })
  it('preserves an operation on refresh failure, disables writes, and offers a visible retry', async () => {
    const { client } = mount()
    const complete = await screen.findByRole('button', { name: 'Complete operation' })
    api.get.mockRejectedValue(new Error('Offline'))
    await act(async () => { await client.invalidateQueries({ queryKey: operationKeys.order('tenant-a', 'order-a') }) })
    await screen.findByRole('alert')
    expect(screen.getByText('Not completed')).toBeVisible()
    expect(complete).toBeDisabled()
    api.get.mockResolvedValue({ data: page() })
    await userEvent.setup().click(screen.getByRole('button', { name: 'Retry operation progress' }))
    await waitFor(() => expect(complete).toBeEnabled())
  })
  it('does not report zero completion when initial loading or the response contract fails', async () => {
    api.get.mockResolvedValue({ data: { items: [] } }); mount(true)
    await screen.findByRole('alert')
    expect(screen.queryByText(/0\/0/)).not.toBeInTheDocument()
    expect(screen.queryByText('No operations assigned.')).not.toBeInTheDocument()
  })
  it('isolates identities and ignores a late response from another order and tenant', async () => {
    let resolve!: (value: unknown) => void
    api.get.mockImplementationOnce(() => new Promise(done => { resolve = done }))
    const view = mount()
    act(() => setUser('tenant-b', 'garage_owner', 'owner-b'))
    api.get.mockResolvedValue({ data: page({ ...operation, description: 'Tenant B work', mechanic_name: 'Tenant B tech' }) })
    view.changeOrder('order-b')
    await screen.findByText('Tenant B tech')
    await act(async () => resolve({ data: page({ ...operation, mechanic_name: 'Private tenant A tech' }) }))
    expect(screen.queryByText('Private tenant A tech')).not.toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/repair-orders/order-b/operations', expect.objectContaining({ signal: expect.any(AbortSignal) }))
  })
  it('shows explicit reopen with the recorded completion actor', async () => {
    const completed = page({ ...operation, status: 'completed', can_assign: false, can_complete: false, can_reopen: true, version: 2, completed_by: { id: 'staff-a', name: 'Casey Staff' }, completed_at: '2026-10-13T12:00:00Z' })
    api.get.mockResolvedValue({ data: completed }); api.put.mockResolvedValue({ data: completed }); mount()
    const reopen = await screen.findByRole('button', { name: 'Reopen operation' })
    await waitFor(() => expect(reopen).toBeEnabled())
    expect(screen.getByText(/Completed by Casey Staff/)).toBeVisible()
    await userEvent.setup().click(reopen)
    expect(api.put).toHaveBeenCalledWith('/repair-orders/order-a/operations/labor-a/completion', { expected_version: 2, is_completed: false })
  })
  it('never loads private execution metadata for customer roles', () => {
    setUser('tenant-a', 'customer'); mount()
    expect(api.get).not.toHaveBeenCalled()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })
})
