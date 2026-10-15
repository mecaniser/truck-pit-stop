import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import RepairOrderScheduleControl from '../RepairOrderScheduleControl'
import { formatScheduleDate, overdueSearchParams, scheduleDeadline, scheduleRefreshInterval } from '../repairOrderSchedule'
import { repairOrderHistoryDetail } from '../repairOrderHistory'
import type { RepairOrderHistoryEvent } from '@/types'
const api = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
const saved = { id: 'order-a', timezone: 'America/New_York', scheduled_start_at: '2026-10-16T12:00:00Z', promised_finish_at: '2026-10-16T21:00:00Z', scheduled_start_local: '2026-10-16T08:00', promised_finish_local: '2026-10-16T17:00', scheduled_start_fold: null, promised_finish_fold: null, updated_at: '2026-10-15T18:00:00.123456Z', is_overdue: false, can_edit: true }
function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  const onUpdated = vi.fn()
  render(<QueryClientProvider client={client}><RepairOrderScheduleControl orderId="order-a" schedule={{ ...saved, schedule_timezone: saved.timezone }} onUpdated={onUpdated} /></QueryClientProvider>)
  return { client, invalidate, onUpdated }
}
async function open() {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Open repair order schedule' }))
  await waitFor(() => expect(screen.getByLabelText('Start')).toHaveValue(saved.scheduled_start_local))
  return user
}
beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({ user: { id: 'owner-a', tenant_id: 'tenant-a', role: 'garage_owner' } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']> })
  api.get.mockResolvedValue({ data: saved })
  api.patch.mockResolvedValue({ data: { ...saved, updated_at: '2026-10-15T19:00:00.654321Z' } })
})
afterEach(() => vi.useRealTimers())
describe('repair-order schedule', () => {
  it('formats shop time, refuses invalid zones and preserves URL context leaving a bounded queue', () => {
    expect(formatScheduleDate(saved.scheduled_start_at, saved.timezone)).toMatch(/Oct 16, 8:00 AM EDT/)
    expect(formatScheduleDate(saved.promised_finish_at, 'invalid')).toBeNull()
    expect(formatScheduleDate(saved.promised_finish_at, null)).toBeNull()
    expect(scheduleDeadline({ ...saved, schedule_timezone: saved.timezone, is_overdue: true })).toMatch(/^Overdue · Oct 16, 5:00 PM EDT/)
    const params = overdueSearchParams(new URLSearchParams('queue=on_floor&search=ABC&customer=one&customer_id=two&selected=order-a'), true)
    expect(params.get('queue')).toBeNull(); expect(params.get('overdue')).toBe('true')
    for (const [key, value] of Object.entries({ search: 'ABC', customer: 'one', customer_id: 'two', selected: 'order-a' })) expect(params.get(key)).toBe(value)
    expect(overdueSearchParams(params, false).has('overdue')).toBe(false)
  })
  it('loads on open and sends wall time unchanged with the exact version', async () => {
    const { invalidate, onUpdated } = mount()
    expect(api.get).not.toHaveBeenCalled()
    const user = await open()
    expect(screen.getByText('Shop time · America/New_York')).toBeVisible()
    fireEvent.change(screen.getByLabelText('Start'), { target: { value: '2026-10-17T09:15' } })
    fireEvent.change(screen.getByLabelText('Promised finish'), { target: { value: '2026-10-17T18:00' } })
    await user.click(screen.getByRole('button', { name: 'Save', exact: true }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(api.patch).toHaveBeenCalledExactlyOnceWith('/repair-orders/order-a/schedule', { expected_updated_at: saved.updated_at, timezone: saved.timezone, scheduled_start_local: '2026-10-17T09:15', promised_finish_local: '2026-10-17T18:00', scheduled_start_fold: null, promised_finish_fold: null })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['repair-orders'] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['dashboard-daily-workset'] })
    expect(onUpdated).toHaveBeenCalledOnce()
  })
  it('clears either date or both using explicit nulls', async () => {
    mount(); const user = await open()
    await user.click(screen.getByRole('button', { name: 'Clear start' }))
    expect(screen.getByLabelText('Start')).toHaveValue('')
    expect(screen.getByLabelText('Promised finish')).toHaveValue(saved.promised_finish_local)
    await user.click(screen.getByRole('button', { name: 'Clear promised finish' }))
    await user.click(screen.getByRole('button', { name: 'Save', exact: true }))
    expect(api.patch).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ scheduled_start_local: null, promised_finish_local: null }))
  })
  it('supports Escape, Cancel and named close with focus return and no writes', async () => {
    mount()
    for (const action of ['Escape', 'Cancel', 'Close schedule dialog']) {
      const user = await open()
      if (action === 'Escape') await user.keyboard('{Escape}')
      else await user.click(screen.getByRole('button', { name: action }))
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      await waitFor(() => expect(screen.getByRole('button', { name: 'Open repair order schedule' })).toHaveFocus())
    }
    expect(api.patch).not.toHaveBeenCalled()
  })
  it.each(['schedule_time_nonexistent', 'schedule_finish_before_start'])('preserves invalid draft after %s', async code => {
    api.patch.mockRejectedValue({ response: { status: 422, data: { detail: { code, message: 'Choose a valid time.', field: 'scheduled_start_local' } } } })
    mount(); const user = await open()
    fireEvent.change(screen.getByLabelText('Start'), { target: { value: '2026-03-08T02:30' } })
    await user.click(screen.getByRole('button', { name: 'Save', exact: true }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Choose a valid time.')
    expect(screen.getByLabelText('Start')).toHaveValue('2026-03-08T02:30')
    expect(api.patch).toHaveBeenCalledOnce()
  })
  it('requires deliberate DST occurrence and sends the chosen fold', async () => {
    api.patch.mockRejectedValueOnce({ response: { status: 422, data: { detail: { code: 'schedule_time_ambiguous', message: 'Choose occurrence.', field: 'scheduled_start_local', choices: [{ fold: 0, utc_offset: '-04:00' }, { fold: 1, utc_offset: '-05:00' }] } } } })
    mount(); const user = await open()
    fireEvent.change(screen.getByLabelText('Start'), { target: { value: '2026-11-01T01:30' } })
    await user.click(screen.getByRole('button', { name: 'Save', exact: true }))
    const second = await screen.findByRole('radio', { name: 'Second occurrence (UTC-05:00)' })
    expect(second).not.toBeChecked()
    await user.click(second)
    await user.click(screen.getByRole('button', { name: 'Save', exact: true }))
    expect(api.patch).toHaveBeenLastCalledWith(expect.any(String), expect.objectContaining({ scheduled_start_local: '2026-11-01T01:30', scheduled_start_fold: 1 }))
  })
  it('compares stale server state without replacing the draft or replaying', async () => {
    api.patch.mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'schedule_changed', message: 'Order changed.' } } } })
    mount(); const user = await open()
    const latest = { ...saved, updated_at: '2026-10-15T20:00:00.987654Z', scheduled_start_local: '2026-10-16T09:00' }
    api.get.mockResolvedValue({ data: latest })
    fireEvent.change(screen.getByLabelText('Start'), { target: { value: '2026-10-16T11:00' } })
    await user.click(screen.getByRole('button', { name: 'Save', exact: true }))
    expect(await screen.findByText('2026-10-16 09:00')).toBeVisible()
    expect(screen.getByLabelText('Start')).toHaveValue('2026-10-16T11:00')
    expect(screen.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()
    expect(api.patch).toHaveBeenCalledOnce()
    await user.click(screen.getByRole('button', { name: 'Keep my draft' }))
    expect(api.patch).toHaveBeenCalledOnce()
    await user.click(screen.getByRole('button', { name: 'Save', exact: true }))
    expect(api.patch).toHaveBeenLastCalledWith(expect.any(String), expect.objectContaining({ expected_updated_at: latest.updated_at, scheduled_start_local: '2026-10-16T11:00' }))
  })
  it('adopts saved timezone only by deliberate reload without reinterpreting a draft', async () => {
    api.patch.mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'schedule_timezone_changed', message: 'Shop timezone changed.' } } } })
    mount(); const user = await open()
    api.get.mockResolvedValue({ data: { ...saved, timezone: 'America/Chicago', scheduled_start_local: '2026-10-16T07:00' } })
    await user.click(screen.getByRole('button', { name: 'Save', exact: true }))
    await screen.findByText('Saved in America/Chicago')
    expect(screen.queryByRole('button', { name: 'Keep my draft' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Use saved schedule' }))
    expect(screen.getByText('Shop time · America/Chicago')).toBeVisible()
    expect(screen.getByLabelText('Start')).toHaveValue('2026-10-16T07:00')
    expect(api.patch).toHaveBeenCalledOnce()
  })
  it('blocks duplicate submits and dismissal while saving and preserves uncertain drafts', async () => {
    let reject!: (reason: unknown) => void
    api.patch.mockImplementationOnce(() => new Promise((_, no) => { reject = no }))
    mount(); const user = await open()
    await user.click(screen.getByRole('button', { name: 'Save', exact: true }))
    expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    await user.keyboard('{Escape}')
    expect(screen.getByRole('dialog')).toBeVisible()
    await act(async () => reject(new Error('offline')))
    expect(screen.getByLabelText('Start')).toHaveValue(saved.scheduled_start_local)
    expect(await screen.findByRole('button', { name: 'Use saved schedule' })).toBeVisible()
    expect(api.patch).toHaveBeenCalledOnce()
    expect(screen.queryByRole('button', { name: 'Keep my draft' })).not.toBeInTheDocument()
  })
  it('makes locked schedules read-only', async () => {
    api.get.mockResolvedValue({ data: { ...saved, can_edit: false } })
    mount(); await open()
    expect(screen.getByLabelText('Start')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Save', exact: true })).not.toBeInTheDocument()
  })
  it('renders readable schedule history without JSON implementation fields', () => {
    const detail = repairOrderHistoryDetail({ event_type: 'schedule_changed', detail: JSON.stringify({ timezone: saved.timezone, previous: { scheduled_start_at: null, promised_finish_at: null }, current: saved }) } as RepairOrderHistoryEvent)
    expect(detail).toContain('Start: Not set → Oct 16, 8:00 AM EDT')
    expect(detail).toContain('Promised finish: Not set → Oct 16, 5:00 PM EDT')
    expect(repairOrderHistoryDetail({ event_type: 'schedule_changed', detail: '{bad' } as RepairOrderHistoryEvent)).toBeUndefined()
  })
  it('refreshes an ordinary visible queue when a promised deadline passes', async () => {
    vi.useFakeTimers()
    const fetch = vi.fn().mockResolvedValueOnce([{ ...saved, schedule_timezone: saved.timezone }]).mockResolvedValue([{ ...saved, schedule_timezone: saved.timezone, is_overdue: true }])
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    function Queue() {
      const query = useQuery({ queryKey: ['schedule-clock-test'], queryFn: fetch, refetchInterval: state => scheduleRefreshInterval(state.state.data ?? []), refetchIntervalInBackground: false })
      return <p>{query.data?.map(scheduleDeadline).join(', ')}</p>
    }
    render(<QueryClientProvider client={client}><Queue /></QueryClientProvider>)
    await act(async () => { await vi.advanceTimersByTimeAsync(10) })
    expect(fetch).toHaveBeenCalledOnce()
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000) })
    expect(fetch).toHaveBeenCalledTimes(2)
    await act(async () => { await vi.advanceTimersByTimeAsync(10) })
    expect(screen.getByText(/^Overdue/)).toBeVisible()
    expect(scheduleRefreshInterval([], true)).toBe(60_000)
    expect(scheduleRefreshInterval([])).toBe(false)
    client.clear()
  })
})
