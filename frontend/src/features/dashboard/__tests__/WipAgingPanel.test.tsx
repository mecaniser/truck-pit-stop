import { useState } from 'react'
import { fireEvent, render, screen, within, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import WipAgingPanel from '../WipAgingPanel'
import { clockLabel, DEFAULT_WIP_FILTERS, type WipAgingResponse, type WipAgingRow, type WipFilters } from '../wipAging'

const testState = vi.hoisted(() => ({
  options: {} as { queryKey: unknown[]; queryFn: (context: { signal: AbortSignal }) => Promise<unknown> },
  data: undefined as unknown,
  isError: false,
  isFetching: false,
  isLoading: false,
  refetch: vi.fn(),
  get: vi.fn(),
}))
vi.mock('@tanstack/react-query', () => ({ useQuery: (options: typeof testState.options) => { testState.options = options; return { ...testState, error: testState.isError ? new Error('offline') : null } } }))
vi.mock('@/lib/api', () => ({ default: { get: testState.get } }))
vi.mock('@/hooks/useDebouncedValue', () => ({ useDebouncedValue: (value: string) => value }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (selector: (state: unknown) => unknown) => selector({ user: { id: 'owner-a', tenant_id: 'shop-a' } }) }))

const known = (seconds: number) => ({ state: 'known' as const, seconds, since: '2026-10-29T12:00:00Z', issue: null })
const row: WipAgingRow = {
  id: 'active-1', order_number: 'LOCAL-001', status: 'in_progress', customer_name: 'Synthetic Fleet',
  vehicle_info: '2023 Truck', vehicle_unit_number: '609', category: 'parts', reason: 'waiting_for_parts',
  hold_reason: 'waiting_for_parts', assignment: 'assigned', technician_names: ['Local Mechanic'],
  order_age: known(259200), current_wait: known(18000), promised_finish_at: '2026-10-29T13:00:00Z',
  overdue_seconds: 7200, is_overdue: true, action_lane: 'on_floor',
}
export const fixture: WipAgingResponse = {
  as_of: '2026-10-29T15:00:00Z', timezone: 'America/New_York', scope: 'shop',
  filters: { search: '', category: 'all', overdue_only: false, timing: 'all', sort: 'priority' },
  summary: { total_jobs: 51, category_counts: { approval: 0, parts: 49, technician: 0, review: 1, other_hold: 0, active: 1, preparation: 0 }, overdue_jobs: 1, unknown_wait_jobs: 1 },
  filtered_total: 51, offset: 0, limit: 50, has_more: true, items: [row],
}
const open = vi.fn()
function Harness({ initial = DEFAULT_WIP_FILTERS }: { initial?: WipFilters }) {
  const [filters, setFilters] = useState(initial)
  return <WipAgingPanel filters={filters} onFiltersChange={setFilters} onOpenRecord={open} />
}
beforeEach(() => {
  testState.data = structuredClone(fixture)
  testState.isError = false; testState.isFetching = false; testState.isLoading = false
  testState.get.mockReset(); testState.refetch.mockReset(); open.mockReset()
})

describe('A2 Shop Work aging', () => {
  it('shows distinct server clocks and complete counts rather than the loaded page size', () => {
    render(<Harness />)
    expect(screen.getByText('51 matching jobs')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Parts 49' })).toBeInTheDocument()
    expect(screen.getByText('5h')).toBeInTheDocument()
    expect(screen.getByText('3d')).toBeInTheDocument()
    expect(screen.getByText('Promise overdue · 2h')).toBeInTheDocument()
    expect(screen.queryByText(/Payment Due|Work value|Updated/)).not.toBeInTheDocument()
  })
  it('shows missing timing as Unknown and does not invent a clock for active work', () => {
    testState.data = { ...fixture, items: [
      { ...row, current_wait: { state: 'unknown', seconds: null, since: null, issue: 'missing_timestamp' } },
      { ...row, id: 'active-2', order_number: 'LOCAL-002', reason: 'work_in_progress', current_wait: { state: 'not_applicable', seconds: null, since: null, issue: null } },
    ] }
    render(<Harness />)
    expect(within(screen.getByRole('button', { name: 'Open LOCAL-001 in Shop Work' })).getByText('Unknown')).toBeInTheDocument()
    expect(screen.queryByText('0m')).not.toBeInTheDocument()
    expect(screen.getByText('Work in progress')).toBeInTheDocument()
  })
  it('never turns an invalid or negative known clock into zero', () => {
    expect(clockLabel({ ...known(-1) })).toBe('Unknown')
    expect(clockLabel({ ...known(Number.NaN) })).toBe('Unknown')
    expect(clockLabel({ ...known(0), seconds: null })).toBe('Unknown')
  })
  it('requests server filtering and resets pagination when category, deadline, timing or search changes', () => {
    render(<Harness initial={{ ...DEFAULT_WIP_FILTERS, offset: 50 }} />)
    fireEvent.click(screen.getByRole('button', { name: 'Parts 49' }))
    expect(testState.options.queryKey[3]).toMatchObject({ category: 'parts', offset: 0 })
    fireEvent.click(screen.getByRole('button', { name: 'Filters' }))
    fireEvent.click(screen.getByRole('button', { name: 'Promise overdue 1' }))
    fireEvent.change(screen.getByLabelText('Wait timing'), { target: { value: 'unknown' } })
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search active work' }), { target: { value: '100%_truck' } })
    expect(testState.options.queryKey[3]).toMatchObject({ category: 'parts', overdue_only: true, timing: 'unknown', search: '100%_truck', offset: 0 })
  })
  it('keeps filter and timing explanations collapsed and supports keyboard dismissal', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    const trigger = screen.getByRole('button', { name: 'Filters' })
    trigger.focus()
    await user.keyboard('{Enter}')
    expect(screen.getByRole('dialog', { name: 'Active work filters' })).toBeInTheDocument()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(trigger).toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'About work timing' }))
    expect(screen.getByRole('dialog', { name: 'Work timing explained' })).toHaveTextContent('Order age is not time in the shop.')
    await user.click(screen.getByRole('searchbox', { name: 'Search active work' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })
  it('offers mobile category selection and an actionable search-wide Unknown count', () => {
    render(<Harness />)
    fireEvent.change(screen.getByLabelText('Active work category'), { target: { value: 'parts' } })
    fireEvent.click(screen.getByRole('button', { name: '1 unknown across all active jobs; filter unknown wait timing' }))
    expect(testState.options.queryKey[3]).toMatchObject({ category: 'parts', timing: 'unknown', offset: 0 })
  })
  it('uses the server has_more flag and page offset', () => {
    render(<Harness />)
    expect(screen.getByRole('button', { name: 'Previous active jobs' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Next active jobs' }))
    expect(testState.options.queryKey[3]).toMatchObject({ offset: 50 })
  })
  it('opens the existing job in its action lane without any save action', () => {
    render(<Harness />)
    fireEvent.click(screen.getByRole('button', { name: 'Open LOCAL-001 in Shop Work' }))
    expect(open).toHaveBeenCalledWith('active-1', 'on_floor')
    expect(testState.get).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: /create invoice|save|record payment/i })).not.toBeInTheDocument()
  })
  it('labels recorded approval holds without asserting a customer failed to reply', () => {
    testState.data = { ...fixture, items: [{ ...row, reason: 'approval_hold' }] }
    render(<Harness />)
    expect(screen.getByText('Approval hold')).toBeInTheDocument()
    expect(screen.queryByText('Awaiting approval')).not.toBeInTheDocument()
  })
  it('uses assigned scope and separates the cache by principal and shop', () => {
    testState.data = { ...fixture, scope: 'assigned' }
    render(<Harness />)
    expect(screen.getByText('51 matching jobs · assigned to you')).toBeInTheDocument()
    expect(testState.options.queryKey.slice(0, 3)).toEqual(['dashboard-wip-aging', 'shop-a', 'owner-a'])
  })
  it('does not show stale records as current after an error', () => {
    testState.isError = true
    render(<Harness />)
    expect(screen.getByRole('alert')).toHaveTextContent('Active work could not be loaded.')
    expect(screen.queryByRole('button', { name: 'Open LOCAL-001 in Shop Work' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry active work' }))
    expect(testState.refetch).toHaveBeenCalledOnce()
  })
  it('keeps empty active work distinct from payment follow-up', () => {
    testState.data = { ...fixture, summary: { ...fixture.summary, total_jobs: 0 }, filtered_total: 0, items: [], has_more: false }
    render(<Harness />)
    expect(screen.getByText('No active jobs in this view')).toBeInTheDocument()
    expect(screen.getByText('Completed work and payment follow-up stay in Closeout.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next active jobs' })).toBeDisabled()
  })
  it('fetches only the additive read endpoint with a cancellable request', async () => {
    testState.get.mockResolvedValue({ data: fixture })
    render(<Harness />)
    const signal = new AbortController().signal
    await testState.options.queryFn({ signal })
    expect(testState.get).toHaveBeenCalledWith('/dashboard/wip-aging', { params: { ...DEFAULT_WIP_FILTERS, limit: 50 }, signal })
  })
})
