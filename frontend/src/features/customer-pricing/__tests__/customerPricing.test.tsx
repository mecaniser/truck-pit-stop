import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), state: { user: { id: 'owner', tenant_id: 'tenant', role: 'garage_owner', permissions: { payments: true } }, authSessionEpoch: 1 } }))
vi.mock('@/lib/api', () => ({ default: mocks }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: Object.assign((select: (state: typeof mocks.state) => unknown) => select(mocks.state), { getState: () => mocks.state }) }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ accentColors: { 500: '#0e7490' } }) }))
import CustomerBusinessSettings from '@/features/customers/CustomerBusinessSettings'
import CustomerPricingControl from '@/features/customers/CustomerPricingControl'
import { accountRate, laborSourceLabel } from '../contract'
import { priceSourceLabel } from '@/features/parts-pricing/contract'

const policy = { schema_version: 1, customer_id: 'customer-1', version: 0, configured: { labor_rate: null, parts_matrix_id: null }, effective: { labor: { source: 'shop', rate: '145.00' }, parts: { source: 'shop', mode: 'catalog', matrix: null } }, can_edit: true, ineligible_reason: null, updated_at: null }
const matrix = { id: 'matrix-b', name: 'Account matrix B', version: 2, current_revision: 2, current_revision_id: 'revision-b', is_default: false, archived_at: null, created_at: '2026-10-16T00:00:00Z', updated_at: '2026-10-16T00:00:00Z' }
const configured = { ...policy, version: 1, configured: { labor_rate: '125.00', parts_matrix_id: matrix.id }, effective: { labor: { source: 'customer', rate: '125.00' }, parts: { source: 'customer', mode: 'matrix', matrix: { id: matrix.id, revision_id: 'revision-b', revision: 2, name: matrix.name } } } }
function setup(business = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const node = (id = 'customer-1') => <QueryClientProvider client={client}>{business ? <CustomerBusinessSettings customerId={id} /> : <CustomerPricingControl customerId={id} />}</QueryClientProvider>
  const view = render(node()); return { ...view, client, change: (id = 'customer-1') => view.rerender(node(id)) }
}
beforeEach(() => {
  mocks.get.mockReset(); mocks.put.mockReset(); mocks.state = { user: { id: 'owner', tenant_id: 'tenant', role: 'garage_owner', permissions: { payments: true } }, authSessionEpoch: 1 }
  mocks.get.mockImplementation(async (path: string) => {
    if (path.endsWith('/pricing-policy')) return { data: policy }
    if (path === '/parts-pricing/matrices') return { data: { schema_version: 1, items: [matrix], next_cursor: null } }
    if (path === '/parts-pricing/default') return { data: { matrix_id: null, generation: 0 } }
    if (path.endsWith('/history')) return { data: { schema_version: 1, items: [], next_cursor: null } }
    if (path.endsWith('/tax-exemption')) return { data: { tax_exempt: false, support_reference: null, version: 0, updated_at: null } }
    throw new Error(`Unexpected ${path}`)
  })
  mocks.put.mockResolvedValue({ data: configured })
})
async function edit() { await userEvent.click(await screen.findByRole('button', { name: 'Edit pricing' })); await screen.findByRole('option', { name: matrix.name }) }

describe('customer pricing settings', () => {
  it('writes the two defaults atomically without a generic customer update', async () => {
    setup(); await edit()
    fireEvent.change(screen.getByLabelText('Labor rate / hr'), { target: { value: '125' } })
    fireEvent.change(screen.getByLabelText('Parts matrix'), { target: { value: matrix.id } })
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Agreed account terms' } })
    fireEvent.click(screen.getByText('Save pricing'))
    await screen.findByText('Pricing saved.')
    expect(screen.getByText('Edit pricing')).toHaveFocus()
    expect(mocks.put).toHaveBeenCalledWith('/customers/customer-1/pricing-policy', { expected_version: 0, labor_rate: '125.00', parts_matrix_id: matrix.id, reason: 'Agreed account terms' }, expect.objectContaining({ headers: { 'Idempotency-Key': expect.stringMatching(/^[\da-f-]{36}$/) } }))
    expect(screen.getByText(/Labor \$125.00\/hr/)).toHaveTextContent('Account')
  })
  it.each(['Cancel', 'Escape'])('returns focus to Edit pricing after %s without writing', async action => {
    setup(); await edit(); screen.getByLabelText('Reason').focus()
    if (action === 'Cancel') fireEvent.click(screen.getByText('Cancel'))
    else fireEvent.keyDown(screen.getByLabelText('Reason'), { key: 'Escape' })
    expect(screen.getByText('Edit pricing')).toHaveFocus(); expect(mocks.put).not.toHaveBeenCalled()
  })
  it('closes the innermost matrix dialog on Escape while retaining the pricing draft and disclosure', async () => {
    setup(true); await userEvent.click(screen.getByText('Business settings')); await edit()
    fireEvent.change(screen.getByLabelText('Labor rate / hr'), { target: { value: '135' } })
    const manage = screen.getByRole('button', { name: 'Manage matrices' })
    expect(manage).toHaveTextContent('Manage')
    await userEvent.click(manage)
    const dialog = await screen.findByRole('dialog', { name: 'Parts pricing' })
    const close = within(dialog).getByRole('button', { name: 'Close Parts pricing' }); close.focus()
    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Parts pricing' })).not.toBeInTheDocument())
    expect(screen.getByRole('region', { name: 'Business settings' })).toBeVisible()
    expect(screen.getByLabelText('Labor rate / hr')).toHaveValue('135')
    await waitFor(() => expect(manage).toHaveFocus())
    expect(mocks.put).not.toHaveBeenCalled()
  })
  it('clears both fields to inheritance and cancels edits without a write', async () => {
    const base = mocks.get.getMockImplementation()!; mocks.get.mockImplementation(path => path.endsWith('/pricing-policy') ? Promise.resolve({ data: configured }) : base(path))
    setup(); await edit()
    fireEvent.change(screen.getByLabelText('Labor rate / hr'), { target: { value: '135' } }); fireEvent.click(screen.getByText('Cancel'))
    expect(mocks.put).not.toHaveBeenCalled(); await edit(); expect(screen.getByLabelText('Labor rate / hr')).toHaveValue('125.00')
    fireEvent.change(screen.getByLabelText('Labor rate / hr'), { target: { value: '' } }); fireEvent.change(screen.getByLabelText('Parts matrix'), { target: { value: '' } }); fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Return to shop defaults' } }); fireEvent.click(screen.getByText('Save pricing'))
    await waitFor(() => expect(mocks.put).toHaveBeenCalledOnce()); expect(mocks.put.mock.calls[0][1]).toMatchObject({ labor_rate: null, parts_matrix_id: null, expected_version: 1 })
  })
  it.each(['0', '-1', '1e2', '1.005', '999999999'])('rejects invalid agreed rate %s and keeps the draft', async value => {
    setup(); await edit(); fireEvent.change(screen.getByLabelText('Labor rate / hr'), { target: { value } }); fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Account update' } }); fireEvent.click(screen.getByText('Save pricing'))
    expect(await screen.findByRole('alert')).toHaveFocus(); expect(screen.getByLabelText('Labor rate / hr')).toHaveValue(value); expect(mocks.put).not.toHaveBeenCalled()
  })
  it('requires explicit review of fresh settings after a conflict, retaining the draft', async () => {
    let reads = 0; const base = mocks.get.getMockImplementation()!
    mocks.get.mockImplementation(path => path.endsWith('/pricing-policy') ? Promise.resolve({ data: reads++ ? configured : policy }) : base(path))
    mocks.put.mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'customer_pricing_conflict', message: 'These pricing settings changed.' } } } }).mockResolvedValue({ data: { ...configured, version: 2 } })
    setup(); await edit(); fireEvent.change(screen.getByLabelText('Labor rate / hr'), { target: { value: '135' } }); fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'My account update' } }); fireEvent.click(screen.getByText('Save pricing'))
    await screen.findByText('Current saved pricing'); expect(screen.getByLabelText('Labor rate / hr')).toHaveValue('135'); expect(screen.getByText('Save pricing')).toBeDisabled(); expect(screen.getByText(/Labor \$125.00\/hr/)).toBeVisible()
    fireEvent.click(screen.getByText('Keep draft against current version')); fireEvent.click(screen.getByText('Save pricing'))
    await waitFor(() => expect(mocks.put).toHaveBeenCalledTimes(2)); expect(mocks.put.mock.calls[1][1]).toMatchObject({ expected_version: 1, labor_rate: '135.00' }); expect(mocks.put.mock.calls[1][2].headers).not.toEqual(mocks.put.mock.calls[0][2].headers)
  })
  it('reuses the logical UUID after an uncertain response and blocks duplicate pending clicks', async () => {
    let reject!: (error: Error) => void; mocks.put.mockImplementationOnce(() => new Promise((_, fail) => { reject = fail })).mockResolvedValue({ data: configured })
    setup(); await edit(); fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Confirm agreement' } }); fireEvent.click(screen.getByText('Save pricing'))
    await screen.findByText('Saving…'); fireEvent.click(screen.getByText('Saving…')); expect(mocks.put).toHaveBeenCalledOnce()
    await act(async () => reject(new Error('Network interrupted'))); await screen.findByRole('alert'); fireEvent.click(screen.getByText('Save pricing'))
    await screen.findByText('Pricing saved.'); expect(mocks.put.mock.calls[1][2].headers).toEqual(mocks.put.mock.calls[0][2].headers)
  })
  it('does not replace a missing or foreign response with an unset agreement', async () => {
    mocks.get.mockResolvedValue({ data: { ...configured, customer_id: 'foreign' } }); setup()
    expect(await screen.findByRole('alert')).toHaveTextContent('Customer pricing unavailable'); expect(screen.queryByText('Edit pricing')).not.toBeInTheDocument(); expect(screen.queryByText(/125/)).not.toBeInTheDocument()
  })
  it('keeps internal-account configuration read-only', async () => {
    mocks.get.mockResolvedValue({ data: { ...policy, can_edit: false, ineligible_reason: 'internal_account', effective: { labor: { source: 'internal', rate: null }, parts: { source: 'internal', mode: 'internal', matrix: null } } } }); setup()
    await screen.findByText('Internal account pricing is managed with the truck.'); expect(screen.queryByText('Edit pricing')).not.toBeInTheDocument(); expect(screen.queryByText(/145/)).not.toBeInTheDocument()
  })
  it('loads history only on demand and sends its cursor', async () => {
    const base = mocks.get.getMockImplementation()!
    mocks.get.mockImplementation((path, options) => path.endsWith('/history') ? Promise.resolve({ data: { schema_version: 1, items: [{ id: 'event-1', version: 1, before: policy.configured, after: configured.configured, actor_user_id: 'owner', actor_display_name: 'Owner', reason: 'Agreement accepted', occurred_at: '2026-10-16T00:00:00Z' }], next_cursor: options?.params?.cursor ? null : 'cursor-2' } }) : base(path, options))
    setup(); await screen.findByText('Edit pricing'); expect(mocks.get.mock.calls.some(([path]) => path.endsWith('/history'))).toBe(false)
    fireEvent.click(screen.getByText('History')); await screen.findByText('Agreement accepted'); fireEvent.click(screen.getByText('Older changes'))
    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/customers/customer-1/pricing-policy/history', expect.objectContaining({ params: { limit: 25, cursor: 'cursor-2' } })))
  })
  it('clears customer-scoped drafts and ignores a write completion after identity changes', async () => {
    let resolve!: (value: unknown) => void; mocks.put.mockReturnValue(new Promise(done => { resolve = done })); const view = setup(); await edit()
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Prior identity' } }); fireEvent.click(screen.getByText('Save pricing')); await screen.findByText('Saving…')
    mocks.state.user = { ...mocks.state.user, id: 'other', role: 'mechanic' }; view.change()
    await act(async () => resolve({ data: configured })); expect(screen.queryByText('Pricing saved.')).not.toBeInTheDocument(); expect(screen.queryByRole('textbox')).not.toBeInTheDocument(); expect(view.client.getQueriesData({ queryKey: ['customer-pricing-policy'] })).toEqual([])
  })
  it('shows pricing to admin without payments permission while keeping tax private', async () => {
    mocks.state.user = { ...mocks.state.user, role: 'garage_admin', permissions: { payments: false } }; setup(true)
    expect(mocks.get).not.toHaveBeenCalled(); fireEvent.click(screen.getByText('Business settings')); await screen.findByText('Edit pricing')
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument(); expect(mocks.get.mock.calls.some(([path]) => path.includes('tax-exemption'))).toBe(false)
  })
  it.each(['receptionist', 'mechanic', 'fleet_manager', 'customer'])('never requests private settings for %s', role => { mocks.state.user.role = role; setup(true); expect(screen.queryByText('Business settings')).not.toBeInTheDocument(); expect(mocks.get).not.toHaveBeenCalled() })
  it('uses one disclosure, keeps tax draft on collapse and restores focus on Escape', async () => {
    setup(true); fireEvent.click(screen.getByText('Business settings')); const region = screen.getByRole('region', { name: 'Business settings' })
    fireEvent.click(await within(region).findByRole('checkbox')); fireEvent.change(screen.getByLabelText('Certificate or supporting reference (optional)'), { target: { value: 'Tax draft' } })
    fireEvent.keyDown(region, { key: 'Escape' }); expect(screen.getByText('Business settings')).toHaveFocus(); expect(region).not.toBeVisible()
    fireEvent.click(screen.getByText('Business settings')); expect(screen.getByLabelText('Certificate or supporting reference (optional)')).toHaveValue('Tax draft'); expect(mocks.put).not.toHaveBeenCalled()
  })
})
it('keeps source and calculation distinct without inventing legacy defaults', () => {
  expect(accountRate('')).toBeNull(); expect(accountRate('00125.5')).toBe('125.50')
  expect(priceSourceLabel('matrix', 'customer')).toBe('Account matrix'); expect(priceSourceLabel('fixed', 'customer')).toBe('Fixed')
  expect(laborSourceLabel({ source: 'legacy_unknown', current_source: 'legacy_unknown', charged_hourly_rate: '110.00', default_hourly_rate: null, can_override: true })).toBe('Saved')
})
