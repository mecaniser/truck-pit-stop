import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import JobContribution from './JobContribution'
import { costMoney, validateSchedule } from './model'
vi.mock('@/lib/api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
const fixture = {
  shop_timezone: 'America/New_York', activation_at: '2026-10-20T04:00:00Z', from: '2026-10-20', to: '2026-10-31', next_cursor: null,
  summary: { real_count: 1, test_count: 2, unknown_count: 3, history_count: 4, complete_row_count: 1, incomplete_row_count: 0, reviewed_complete_contribution: '230.00', known_recorded_direct_cost: '120.00', costed_seconds: 10800, recorded_seconds: 10800, is_complete: true },
  rows: [{ order_id: 'order-1', order_number: 'SYNTHETIC-001', customer_name: 'Synthetic', source_owner: 'native', business_classification: 'real', review_status: 'current', revenue: { net_direct_revenue: '500.00' }, direct_contribution: '230.00', margin_pct: '46.00' }],
}
const owner = { id: 'owner', tenant_id: 'shop', role: 'garage_owner', is_active: true } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']>
function show() { const client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); render(<QueryClientProvider client={client}><MemoryRouter><JobContribution /></MemoryRouter></QueryClientProvider>); return client }
beforeEach(() => { useAuthStore.setState({ isAuthenticated: true, logoutInProgress: false, authSessionEpoch: 1, user: owner }); vi.mocked(api.get).mockReset().mockResolvedValue({ data: fixture }); vi.mocked(api.post).mockReset() })
describe('Owner job contribution', () => {
  it.each(['garage_admin', 'mechanic', 'receptionist', 'super_admin', 'customer', 'fleet_manager'] as const)('never mounts or requests cost data for %s', role => { useAuthStore.setState({ user: { ...owner, role } }); show(); expect(screen.queryByText('Job Contribution')).toBeNull(); expect(api.get).not.toHaveBeenCalled() })
  it('shows trusted contribution and keeps test/unknown/history counts explicit', async () => { show(); expect(await screen.findByText('Reviewed complete contribution')).toBeVisible(); expect(screen.getAllByText('$230.00')).toHaveLength(2); expect(screen.getByText('2 test excluded', { exact: false })).toBeVisible(); expect(api.post).not.toHaveBeenCalled() })
  it('never renders a missing contribution as zero', async () => { vi.mocked(api.get).mockResolvedValue({ data: { ...fixture, rows: [{ ...fixture.rows[0], direct_contribution: null, margin_pct: null }] } }); show(); expect(await screen.findByText('Incomplete / excluded')).toBeVisible(); expect(screen.getByText('Unavailable')).toBeVisible() })
  it('removes owner cost data and cache on role change', async () => { const client = show(); await screen.findByText('SYNTHETIC-001'); act(() => useAuthStore.setState({ user: { ...owner, role: 'garage_admin' } })); expect(screen.queryByText('SYNTHETIC-001')).toBeNull(); await waitFor(() => expect(client.getQueriesData({ queryKey: ['owner-job-contribution'] })).toEqual([])) })
  it('uses a new tenant scope and never displays the previous tenant response', async () => { show(); await screen.findByText('SYNTHETIC-001'); vi.mocked(api.get).mockImplementation(() => new Promise(() => {})); act(() => useAuthStore.setState({ user: { ...owner, tenant_id: 'other-shop' } })); expect(screen.queryByText('SYNTHETIC-001')).toBeNull() })
  it('clears all sensitive display after permission denial', async () => { vi.mocked(api.get).mockRejectedValue({ response: { status: 403 } }); show(); expect(await screen.findByRole('alert')).toHaveTextContent('Owner access required') })
  it('shows explicit numeric illustration only inside collapsed details', async () => { const user = userEvent.setup(); show(); await screen.findByText('SYNTHETIC-001'); const summary = screen.getByText('How the numbers work'); expect(summary.closest('details')).not.toHaveAttribute('open'); await user.click(summary); expect(screen.getByText(/At 5 hours/)).toBeVisible() })
})
describe('Rate values', () => {
  it('distinguishes recorded zero from unknown', () => { expect(costMoney('0.00')).toBe('$0.00'); expect(costMoney(null)).toBe('Unavailable') })
  it('rejects guessed zero, exponent, excess precision and overlap', () => { const segment = { effective_from: '2026-10-20T04:00:00Z', effective_to: null, hourly_cost: '40.0000', inclusions: 'Pay and employment burden' }; expect(validateSchedule([segment], 'Approved cost', segment.effective_from)).toBeNull(); for (const hourly_cost of ['0', '4e1', '40.00001']) expect(validateSchedule([{ ...segment, hourly_cost }], 'Reason', segment.effective_from)).not.toBeNull(); expect(validateSchedule([segment, segment], 'Reason', segment.effective_from)).not.toBeNull() })
})
const mechanic = { mechanic_id: 'mechanic-1', mechanic_name: 'Synthetic technician', is_active: true, version: 0, revision_id: null, policy: null }
async function openRateEditor() {
  const user = userEvent.setup()
  show()
  await screen.findByText('SYNTHETIC-001')
  await user.click(screen.getByRole('button', { name: 'Technician Costs' }))
  await user.click(await screen.findByRole('button', { name: /Synthetic technician/ }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Add rate segment' })).toBeEnabled())
  await user.click(screen.getByRole('button', { name: 'Add rate segment' }))
  await user.type(screen.getByLabelText('Loaded hourly cost (USD)'), '40.0000')
  await user.type(screen.getByLabelText('Included direct employment costs'), 'Direct pay and employment burden')
  await user.type(screen.getByLabelText('Revision reason'), 'Synthetic initial schedule')
  return user
}
function rateReads() {
  vi.mocked(api.get).mockImplementation(async (path, config) => {
    if (path === '/reports/technician-costs') return { data: { items: [mechanic], next_cursor: null } }
    if (path === '/reports/technician-costs/mechanic-1') return { data: { ...mechanic, history: [] } }
    if (path === '/reports/technician-costs/time-boundaries') return { data: { contract_version: 1, shop_timezone: 'America/New_York', local: config?.params.local, fold: null, effective_at: '2026-10-20T04:00:00Z', activation_at: '2026-10-20T04:00:00Z' } }
    return { data: fixture }
  })
}
describe('Owner rate schedule workflow', () => {
  it('resolves friendly shop-local time server-side and sends only A1 metadata', async () => {
    rateReads(); vi.mocked(api.post).mockResolvedValue({ data: { ...mechanic, version: 1 } })
    const user = await openRateEditor()
    expect(screen.getByLabelText('Effective from (America/New_York)')).toHaveValue('2026-10-20T00:00')
    expect(screen.queryByText(/RFC3339/)).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Append approved cost schedule' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledOnce())
    expect(api.get).toHaveBeenCalledWith('/reports/technician-costs/time-boundaries', expect.objectContaining({ params: { local: '2026-10-20T00:00' } }))
    expect(api.post).toHaveBeenCalledWith('/reports/technician-costs/mechanic-1', expect.objectContaining({ expected_version: 0, currency: 'USD', basis: 'owner_declared_loaded_direct', segments: [{ effective_from: '2026-10-20T04:00:00Z', effective_to: null, hourly_cost: '40.0000', inclusions: 'Direct pay and employment burden' }] }), expect.objectContaining({ headers: { 'Idempotency-Key': expect.any(String) } }))
  })
  it('cancel discards draft without posting or resolving a boundary', async () => {
    rateReads(); const user = await openRateEditor()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('form', { name: 'Technician rate schedule' })).toBeNull()
    expect(api.post).not.toHaveBeenCalled()
    expect(vi.mocked(api.get).mock.calls.some(([path]) => path === '/reports/technician-costs/time-boundaries')).toBe(false)
  })
  it('preserves draft after conflict and reuses the same request key for an unchanged retry', async () => {
    rateReads(); vi.mocked(api.post).mockRejectedValue({ response: { status: 409 } })
    const user = await openRateEditor()
    await user.click(screen.getByRole('button', { name: 'Append approved cost schedule' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Source or version changed')
    expect(screen.getByLabelText('Loaded hourly cost (USD)')).toHaveValue('40.0000')
    await user.click(screen.getByRole('button', { name: 'Append approved cost schedule' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2))
    expect(vi.mocked(api.post).mock.calls[0][2]).toEqual(vi.mocked(api.post).mock.calls[1][2])
  })
  it('asks for explicit repeated-time occurrence rather than guessing a DST offset', async () => {
    rateReads()
    const normal = vi.mocked(api.get).getMockImplementation()!
    vi.mocked(api.get).mockImplementation(async (path, config) => {
      if (path === '/reports/technician-costs/time-boundaries' && config?.params.fold === undefined) throw { response: { status: 422, data: { detail: { code: 'schedule_time_ambiguous', choices: [0, 1] } } } }
      return normal(path, config)
    })
    const user = await openRateEditor()
    await user.click(screen.getByRole('button', { name: 'Append approved cost schedule' }))
    expect(await screen.findByLabelText('Repeated start time')).toBeVisible()
    expect(api.post).not.toHaveBeenCalled()
    await user.selectOptions(screen.getByLabelText('Repeated start time'), '1')
    vi.mocked(api.post).mockResolvedValue({ data: mechanic })
    await user.click(screen.getByRole('button', { name: 'Append approved cost schedule' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledOnce())
    expect(api.get).toHaveBeenCalledWith('/reports/technician-costs/time-boundaries', expect.objectContaining({ params: { local: '2026-10-20T00:00', fold: 1 } }))
  })
})
const detailFixture = {
  source_fingerprint: 'a'.repeat(64), policy_heads_digest: 'b'.repeat(64), review: null,
  row: { ...fixture.rows[0], review_version: 0, cost_status: 'partial', hold_reasons: ['time_capture_incomplete'], revenue: { net_direct_revenue: '500.00', hold_reasons: [], tax: '20.00', fees: '10.00', supplies: '5.00' }, labor: { status: 'complete', operation_attributed_seconds: 0, general_ro_seconds: 10800, open_session_count: 0, known_cost: '120.00', hold_reasons: [], recorded_seconds: 10800, costed_seconds: 10800, unrated_seconds: 0, held_seconds: 0, pre_activation_seconds: 0 }, parts: { status: 'complete', known_cost: '150.00', line_count: 1, missing_cost_line_count: 0 }, sublet: { status: 'not_applicable', known_cost: '0.00', line_count: 0, missing_cost_line_count: 0 } },
  sessions: [], separate_shop_time: { scope: 'selected_job_timer_window', scope_windows: [{ mechanic_id: 'mechanic-1', started_at: '2026-10-20T13:00:00Z', ended_at: '2026-10-20T16:00:00Z' }], time_status: 'complete', misc_seconds: 1800, idle_seconds: 900, break_seconds: 600, cost_status: 'unavailable' },
}
describe('Explicit owner job review', () => {
  it('allows the first scope review for the backend unreviewed-native ownership shape', async () => {
    const unknown = { ...detailFixture, row: { ...detailFixture.row, business_classification: 'unknown', source_owner: 'review_required', review_status: 'none', review_version: 0, cost_status: 'unavailable', direct_contribution: null, margin_pct: null, hold_reasons: ['owner_business_review_required', 'owner_time_capture_review_required'] } }
    vi.mocked(api.get).mockImplementation(async path => ({ data: path === '/reports/job-contribution/order-1' ? unknown : fixture }))
    vi.mocked(api.post).mockResolvedValue({ data: {} })
    const user = userEvent.setup(); show()
    await user.click(await screen.findByRole('button', { name: /SYNTHETIC-001/ }))
    await screen.findByText('Owner scope review')
    expect(screen.getByLabelText('Business activity')).toHaveValue('unknown')
    await user.selectOptions(screen.getByLabelText('Business activity'), 'real')
    await user.type(screen.getByLabelText('Review reason'), 'First review of synthetic native work')
    await user.click(screen.getByRole('button', { name: 'Append owner review' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledOnce())
    expect(vi.mocked(api.post).mock.calls[0][1]).toEqual(expect.objectContaining({ expected_version: 0, business_classification: 'real', time_capture: 'incomplete' }))
  })

  it('sends exact current source identity and assertions without monetary fields', async () => {
    vi.mocked(api.get).mockImplementation(async path => ({ data: path === '/reports/job-contribution/order-1' ? detailFixture : fixture }))
    vi.mocked(api.post).mockResolvedValue({ data: {} })
    const user = userEvent.setup(); show()
    await user.click(await screen.findByRole('button', { name: /SYNTHETIC-001/ }))
    await screen.findByText('Owner scope review')
    await user.selectOptions(screen.getByLabelText('Business activity'), 'real')
    await user.selectOptions(screen.getByLabelText('Time capture assertion'), 'complete')
    await user.type(screen.getByLabelText('Review reason'), 'All direct work captured for this synthetic job')
    await user.click(screen.getByRole('button', { name: 'Append owner review' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledOnce())
    const [path, body, config] = vi.mocked(api.post).mock.calls[0]
    expect(path).toBe('/reports/job-contribution/order-1/review')
    expect(body).toEqual({ expected_version: 0, source_fingerprint: 'a'.repeat(64), policy_heads_digest: 'b'.repeat(64), business_classification: 'real', time_capture: 'complete', reviewed_exception_ids: [], reason: 'All direct work captured for this synthetic job' })
    expect(config?.headers).toEqual({ 'Idempotency-Key': expect.any(String) })
  })
  it('preserves assertions and reason on source drift; refresh is explicit', async () => {
    vi.mocked(api.get).mockImplementation(async path => ({ data: path === '/reports/job-contribution/order-1' ? detailFixture : fixture }))
    vi.mocked(api.post).mockRejectedValue({ response: { status: 409 } })
    const user = userEvent.setup(); show()
    await user.click(await screen.findByRole('button', { name: /SYNTHETIC-001/ }))
    await screen.findByText('Owner scope review')
    await user.selectOptions(screen.getByLabelText('Business activity'), 'test')
    await user.type(screen.getByLabelText('Review reason'), 'Synthetic test, exclude')
    await user.click(screen.getByRole('button', { name: 'Append owner review' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Source or version changed')
    expect(screen.getByLabelText('Review reason')).toHaveValue('Synthetic test, exclude')
    expect(screen.getByLabelText('Business activity')).toHaveValue('test')
    expect(screen.getByRole('button', { name: 'Refresh source' })).toBeVisible()
  })
  it('does not offer native reviews for ETS source-owned history', async () => {
    vi.mocked(api.get).mockImplementation(async path => ({ data: path === '/reports/job-contribution/order-1' ? { ...detailFixture, row: { ...detailFixture.row, source_owner: 'ets_history' } } : fixture }))
    const user = userEvent.setup(); show()
    await user.click(await screen.findByRole('button', { name: /SYNTHETIC-001/ }))
    expect(await screen.findByText('Source-owned history cannot receive a native costing review.')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Append owner review' })).toBeNull()
    expect(api.post).not.toHaveBeenCalled()
  })
})
describe('Bounded separate shop time', () => {
  async function openWindow(time: object) {
    vi.mocked(api.get).mockImplementation(async path => ({ data: path === '/reports/job-contribution/order-1' ? { ...detailFixture, separate_shop_time: time } : fixture }))
    const user = userEvent.setup(); show()
    await user.click(await screen.findByRole('button', { name: /SYNTHETIC-001/ }))
    return screen.findByRole('region', { name: 'Separate time within selected job timer window' })
  }
  it('shows unavailable amounts when no valid closed job window exists', async () => {
    const region = await openWindow({ scope: 'selected_job_timer_window', scope_windows: [], time_status: 'unavailable', misc_seconds: null, idle_seconds: null, break_seconds: null, cost_status: 'unavailable' })
    expect(region).toHaveTextContent('No valid closed job timer window.')
    expect(region).toHaveTextContent('Observed time unavailable')
    expect(region.querySelectorAll('dd')).toHaveLength(3)
    for (const value of region.querySelectorAll('dd')) expect(value).toHaveTextContent('Unavailable')
    expect(region).not.toHaveTextContent('0.00 h')
  })
  it('labels partial observations and never replaces unknown idle with zero', async () => {
    const region = await openWindow({ ...detailFixture.separate_shop_time, time_status: 'partial', misc_seconds: 900, idle_seconds: null, break_seconds: 300 })
    expect(region).toHaveTextContent('Partial observed coverage')
    expect(region).toHaveTextContent('0.25 h')
    expect(region).toHaveTextContent('Observed idle timeUnavailable')
    expect(region).toHaveTextContent('America/New_York')
    expect(region).toHaveTextContent('9:00 AM')
    expect(region).toHaveTextContent('12:00 PM')
    expect(region).not.toHaveTextContent('Daily idle')
    expect(region).not.toHaveTextContent('Whole-day')
  })
  it('limits complete coverage wording to selected timer windows', async () => {
    const region = await openWindow(detailFixture.separate_shop_time)
    expect(region).toHaveTextContent('Complete observed coverage within selected windows')
    expect(region).toHaveTextContent("Shop time during this job's timer window")
    expect(region).toHaveTextContent('Cost unavailable · Not allocated to job expense')
  })
})
