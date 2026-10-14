import { useState } from 'react'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import StaffHoldDialog from '../StaffHoldDialog'
import { canManageWorkHold, staffHoldHistoryDetail, type WorkHoldOrder } from '../staffHold'

const api = vi.hoisted(() => ({ post: vi.fn() }))
const toast = vi.hoisted(() => ({ success: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
vi.mock('react-hot-toast', () => ({ default: toast }))
const order: WorkHoldOrder = { id: 'order-a', order_number: 'QA-HOLD', status: 'in_progress', updated_at: '2026-10-14T00:30:00.123456Z', hold_reason: null, held_at: null, is_internal: false, is_fleet_work: false }
const held = { ...order, updated_at: '2026-10-14T00:31:00.123456Z', hold_reason: 'waiting_for_parts', held_at: '2026-10-14T00:31:00.123456Z' }
function Host({ current = order, onUpdated }: { current?: WorkHoldOrder; onUpdated?: () => void }) {
  const [open, setOpen] = useState(false)
  return <><button onClick={() => setOpen(true)}>Manage hold</button>{open && <StaffHoldDialog order={current} onClose={() => setOpen(false)} onUpdated={onUpdated} />}</>
}
function mount(current = order) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const refresh = vi.spyOn(client, 'invalidateQueries')
  const onUpdated = vi.fn()
  const view = render(<QueryClientProvider client={client}><Host current={current} onUpdated={onUpdated} /></QueryClientProvider>)
  return { ...view, refresh, onUpdated, changeOrder: (next: WorkHoldOrder) => view.rerender(<QueryClientProvider client={client}><Host current={next} onUpdated={onUpdated} /></QueryClientProvider>) }
}
beforeEach(() => { vi.clearAllMocks(); useAuthStore.setState({ user: { id: 'owner-a', tenant_id: 'tenant-a', role: 'garage_owner' } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']> }) })

describe('staff work hold', () => {
  it('keeps the original reason readable in hold and release history without exposing serialized data', () => {
    expect(staffHoldHistoryDetail('work_held', JSON.stringify({ current: { hold_reason: 'waiting_for_parts' } }))).toBe('Waiting for parts')
    expect(staffHoldHistoryDetail('work_hold_released', JSON.stringify({ previous: { hold_reason: 'Custom reason' }, current: { hold_reason: null } }))).toBe('Custom reason')
    expect(staffHoldHistoryDetail('work_held', '{broken')).toBeUndefined()
    expect(staffHoldHistoryDetail('work_held', '{}')).toBeUndefined()
  })
  it('submits the exact raw version and confirms stopped timers only after server success', async () => {
    api.post.mockResolvedValue({ data: { ...held, stopped_sessions_count: 2 } })
    const { refresh, onUpdated } = mount(); const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Manage hold' }))
    await user.click(screen.getByRole('button', { name: 'Put on hold' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(api.post).toHaveBeenCalledExactlyOnceWith('/repair-orders/order-a/staff-hold', { expected_updated_at: order.updated_at, reason: 'waiting_for_parts' })
    expect(toast.success).toHaveBeenCalledWith('Order on hold. 2 timers stopped.')
    expect(refresh).toHaveBeenCalledWith({ queryKey: ['order-operations', 'tenant-a', 'order-a'] })
    expect(refresh).toHaveBeenCalledWith({ queryKey: ['repair-order-workspace', 'order-a'] })
    expect(onUpdated).toHaveBeenCalledOnce()
  })
  it('releases with the dedicated staff route and never sends a timer or mechanic-resume request', async () => {
    api.post.mockResolvedValue({ data: { ...order, updated_at: '2026-10-14T00:32:00.123456Z', stopped_sessions_count: 0 } })
    mount(held); const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Manage hold' }))
    expect(screen.getByText('Technicians can start work again. No timers will start automatically.')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Release hold' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(api.post).toHaveBeenCalledExactlyOnceWith('/repair-orders/order-a/staff-release-hold', { expected_updated_at: held.updated_at })
  })
  it('requires a meaningful custom reason and retains it after failure without replay', async () => {
    api.post.mockRejectedValue({ response: { status: 409, data: { detail: 'Another workflow update is in progress.' } } })
    mount(); const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Manage hold' }))
    await user.selectOptions(screen.getByRole('combobox', { name: 'Hold reason' }), 'custom')
    const reason = screen.getByRole('textbox', { name: /Other hold reason/ })
    expect(reason).toHaveAttribute('maxlength', '100')
    await user.type(reason, '   ')
    expect(screen.getByRole('button', { name: 'Put on hold' })).toBeDisabled()
    await user.clear(reason); await user.type(reason, '  Waiting for bay inspection  ')
    await user.click(screen.getByRole('button', { name: 'Put on hold' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Another workflow update')
    expect(reason).toHaveValue('  Waiting for bay inspection  ')
    expect(api.post).toHaveBeenCalledExactlyOnceWith('/repair-orders/order-a/staff-hold', { expected_updated_at: order.updated_at, reason: 'Waiting for bay inspection' })
    expect(toast.success).not.toHaveBeenCalled()
  })
  it('rejects a stale open dialog without changing the captured intent or replaying', async () => {
    const view = mount(); const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Manage hold' }))
    view.changeOrder(held)
    expect(screen.getByRole('dialog', { name: 'Put order on hold' })).toBeVisible()
    expect(screen.getByRole('alert')).toHaveTextContent('This order changed')
    expect(screen.getByRole('button', { name: 'Put on hold' })).toBeDisabled()
    expect(api.post).not.toHaveBeenCalled()
  })
  it('supports Escape, named close and Cancel with focus return and no writes', async () => {
    mount(); const user = userEvent.setup(); const trigger = screen.getByRole('button', { name: 'Manage hold' })
    for (const action of ['escape', 'Close hold dialog', 'Cancel']) {
      await user.click(trigger)
      if (action === 'escape') await user.keyboard('{Escape}')
      else await user.click(screen.getByRole('button', { name: action }))
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      await waitFor(() => expect(trigger).toHaveFocus())
    }
    expect(api.post).not.toHaveBeenCalled()
  })
  it('blocks duplicate submission and dismissal while saving', async () => {
    let resolve!: (value: unknown) => void
    api.post.mockImplementation(() => new Promise(done => { resolve = done }))
    mount(); const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Manage hold' }))
    await user.click(screen.getByRole('button', { name: 'Put on hold' }))
    expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Close hold dialog' })).toBeDisabled()
    await user.keyboard('{Escape}')
    expect(screen.getByRole('dialog')).toBeVisible()
    expect(api.post).toHaveBeenCalledTimes(1)
    await act(async () => resolve({ data: { ...held, stopped_sessions_count: 0 } }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })
  it.each([{ ...held, id: 'wrong-order', stopped_sessions_count: 0 }, { ...held, updated_at: order.updated_at, stopped_sessions_count: 0 }, { ...held, hold_reason: null, stopped_sessions_count: 0 }, {}])('does not report an invalid or mismatched success payload as confirmed', async data => {
    api.post.mockResolvedValue({ data }); const { refresh } = mount(); const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Manage hold' }))
    await user.click(screen.getByRole('button', { name: 'Put on hold' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Change could not be confirmed')
    expect(refresh).toHaveBeenCalled(); expect(toast.success).not.toHaveBeenCalled(); expect(api.post).toHaveBeenCalledOnce()
  })
  it('limits staff controls to in-progress staff scope', () => {
    for (const role of ['garage_owner', 'garage_admin', 'receptionist']) expect(canManageWorkHold(role, order)).toBe(true)
    for (const role of ['mechanic', 'customer', 'driver', undefined]) expect(canManageWorkHold(role, order)).toBe(false)
    expect(canManageWorkHold('fleet_manager', order)).toBe(false)
    expect(canManageWorkHold('fleet_manager', { ...order, is_internal: true })).toBe(true)
    expect(canManageWorkHold('fleet_manager', { ...order, is_fleet_work: true })).toBe(true)
    expect(canManageWorkHold('garage_owner', { ...order, status: 'completed' })).toBe(false)
  })
})
