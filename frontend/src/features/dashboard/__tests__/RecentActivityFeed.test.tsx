import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import RecentActivityFeed from '../RecentActivityFeed'
import type { ActivityFeedResponse } from '../activityFeedQuery'

const state = vi.hoisted(() => ({ user: { id: 'owner', tenant_id: 'shop-a', role: 'garage_owner', is_active: true }, epoch: 1, isAuthenticated: true, logoutInProgress: false, authProvider: 'legacy', data: undefined as ActivityFeedResponse | undefined, isLoading: false, isError: false, isFetching: false, error: null as unknown, filters: {} as Record<string, string>, refetch: vi.fn(), get: vi.fn(), navigate: vi.fn() }))
vi.mock('../activityFeedQuery', () => ({ useActivityFeed: (filters: Record<string, string>) => { state.filters = filters; return state } }))
vi.mock('@/stores/authStore', async importOriginal => ({ ...await importOriginal<typeof import('@/stores/authStore')>(), useAuthStore: (select: (s: unknown) => unknown) => select({ user: state.user, authSessionEpoch: state.epoch, isAuthenticated: state.isAuthenticated, logoutInProgress: state.logoutInProgress, authProvider: state.authProvider }) }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ appearance: {} }), appearanceTokenRecord: () => ({}) }))
vi.mock('@/lib/api', () => ({ default: { get: state.get } }))
vi.mock('react-router-dom', () => ({ useNavigate: () => state.navigate }))
const event = (id: string, actor: string, time: string) => ({ id, event_type: 'ro_created', label: `Created ${id}`, occurred_at: `2026-11-01T${time}:00Z`, actor_name: actor, order_id: `order-${id}`, order_number: `RO-${id}` })
const page: ActivityFeedResponse = { items: [event('1', 'Alex', '15:00'), event('2', 'Sam', '14:00'), event('3', 'Alex', '13:00')], next_cursor: null, has_more: false, available_actors: [{ id: 'alex', name: 'Alex' }], warnings: [] }
afterEach(() => vi.unstubAllGlobals())
beforeEach(() => { state.user = { id: 'owner', tenant_id: 'shop-a', role: 'garage_owner', is_active: true }; state.epoch = 1; state.isAuthenticated = true; state.logoutInProgress = false; state.authProvider = 'legacy'; vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }); state.data = structuredClone(page); state.isLoading = false; state.isError = false; state.isFetching = false; state.error = null; state.get.mockReset(); state.refetch.mockReset(); state.navigate.mockReset() })
describe('Shop Work activity consistency', () => {
  it('keeps events in time order across actors and opens the exact existing record', () => {
    render(<RecentActivityFeed />)
    expect(screen.getAllByRole('listitem').map(row => row.textContent)).toEqual([expect.stringContaining('Created 1'), expect.stringContaining('Created 2'), expect.stringContaining('Created 3')])
    fireEvent.click(screen.getByRole('button', { name: /Created 2/ }))
    expect(state.navigate).toHaveBeenCalledWith('/dashboard/repair-orders?selected=order-2')
    expect(screen.queryByText(/3 actions/)).not.toBeInTheDocument()
  })
  it('keeps named filters behind one control and supports nested selection, date entry and reset', async () => {
    const user = userEvent.setup(); render(<RecentActivityFeed />)
    expect(screen.queryByLabelText('From date')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Activity filters' }))
    await user.click(screen.getByRole('button', { name: 'Activity type' }))
    await user.click(screen.getByRole('option', { name: 'Order created', exact: true }))
    expect(state.filters.event_type).toBe('ro_created')
    expect(screen.getByRole('dialog', { name: 'Activity filters' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('From date'), { target: { value: '2026-10-29' } })
    expect(state.filters.date_from).toBe('2026-10-29')
    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(state.filters).toEqual({ actor_id: undefined, event_type: undefined, date_from: undefined, date_to: undefined })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument(); expect(screen.getByRole('button', { name: 'Activity filters' })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'Activity filters' }))
    await user.click(screen.getByRole('button', { name: 'Close activity filters' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it('distinguishes initial failure, loading, empty, and denied activity', () => {
    state.data = undefined; state.isError = true
    const { rerender } = render(<RecentActivityFeed />)
    expect(screen.getByRole('alert')).toHaveTextContent('Activity could not be loaded')
    expect(screen.queryByText('No recent activity')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry activity' })); expect(state.refetch).toHaveBeenCalledOnce()
    state.isError = false; state.isLoading = true; rerender(<RecentActivityFeed />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading activity')
    state.isLoading = false; state.data = { ...page, items: [] }; rerender(<RecentActivityFeed />)
    expect(screen.getByRole('status')).toHaveTextContent('No recent activity')
    state.isError = true; state.error = { response: { status: 403 } }; rerender(<RecentActivityFeed />)
    expect(screen.getByRole('alert')).toHaveTextContent('unavailable for this account')
    expect(screen.queryByRole('button', { name: /Created/ })).not.toBeInTheDocument()
  })
  it('keeps incomplete coverage visible without a stack of warning banners', async () => {
    state.data = { ...page, warnings: ['Invoice activity could not be checked.', 'Payment history is incomplete.'] }
    render(<RecentActivityFeed />)
    await userEvent.click(screen.getByRole('button', { name: 'Activity incomplete' }))
    const dialog = screen.getByRole('dialog', { name: 'Activity coverage' })
    expect(dialog).toHaveTextContent('Invoice activity could not be checked.')
    expect(dialog).toHaveTextContent('Payment history is incomplete.')
    expect(within(dialog).getByRole('button', { name: 'Close activity coverage' })).toBeInTheDocument()
  })
  it('preserves events and offers one retry when older-page loading fails', async () => {
    state.data = { ...page, next_cursor: 'older', has_more: true }
    state.get.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ data: { ...page, items: [event('4', 'Sam', '12:00')], has_more: false } })
    render(<RecentActivityFeed />)
    await userEvent.click(screen.getByRole('button', { name: 'Load older activity' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Older activity could not be loaded')
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
    await userEvent.click(screen.getByRole('button', { name: 'Retry older activity' }))
    await waitFor(() => expect(screen.getAllByRole('listitem')).toHaveLength(4))
    expect(state.get).toHaveBeenLastCalledWith('/activity', { params: { limit: 20, cursor: 'older', actor_id: undefined, event_type: undefined, date_from: undefined, date_to: undefined }, signal: expect.any(AbortSignal) })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
  it('discards an older page that finishes after the activity filter changes', async () => {
    state.data = { ...page, next_cursor: 'older-a', has_more: true }
    let finish!: (value: { data: ActivityFeedResponse }) => void
    state.get.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const user = userEvent.setup()
    const { rerender } = render(<RecentActivityFeed />)
    await user.click(screen.getByRole('button', { name: 'Load older activity' }))
    await user.click(screen.getByRole('button', { name: 'Activity filters' }))
    await user.click(screen.getByRole('button', { name: 'Activity type' }))
    await user.click(screen.getByRole('option', { name: 'Order created', exact: true }))
    state.data = { ...page, items: [event('filtered', 'Sam', '11:00')], has_more: false }
    rerender(<RecentActivityFeed />)
    await act(async () => finish({ data: { ...page, items: [event('stale-filter', 'Alex', '12:00')] } }))
    expect(screen.queryByRole('button', { name: /Created stale-filter/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Created filtered/ })).toBeInTheDocument()
  })
  it.each(['tenant', 'session'])('discards an older page that finishes after the %s changes', async change => {
    state.data = { ...page, next_cursor: 'older-a', has_more: true }
    let finish!: (value: { data: ActivityFeedResponse }) => void
    state.get.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const { rerender } = render(<RecentActivityFeed />)
    await userEvent.click(screen.getByRole('button', { name: 'Load older activity' }))
    if (change === 'tenant') state.user = { ...state.user, tenant_id: 'shop-b' }
    else state.epoch++
    state.data = { ...page, items: [event('new-scope', 'Sam', '11:00')], has_more: false }
    rerender(<RecentActivityFeed />)
    await act(async () => finish({ data: { ...page, items: [event('stale-scope', 'Alex', '12:00')] } }))
    expect(screen.queryByRole('button', { name: /Created stale-scope/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Created new-scope/ })).toBeInTheDocument()
  })
  it('leaves events without a record readable and non-actionable', () => {
    state.data = { ...page, items: [{ ...page.items[0], order_id: null }] }
    render(<RecentActivityFeed />)
    expect(screen.getByRole('button', { name: /Created 1/ })).toBeDisabled()
  })
})
