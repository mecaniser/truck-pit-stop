import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), role: 'garage_owner' }))
vi.mock('@/lib/api', () => ({ default: mocks }))
vi.mock('@/stores/authStore', () => { const getState = () => ({ user: { id: 'user-1', tenant_id: 'tenant-1', role: mocks.role }, authSessionEpoch: 1 }); return { useAuthStore: Object.assign((select: (state: ReturnType<typeof getState>) => unknown) => select(getState()), { getState }) } })
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ accentColors: { 500: '#d86a15' } }) }))
import PartsPricingSettings from '../PartsPricingSettings'
import PartPricingPolicy from '../PartPricingPolicy'
import { enteredMoney } from '../configuration'
const matrix = { id: 'matrix-1', name: 'Standard', version: 1, current_revision: 1, current_revision_id: 'revision-1', is_default: false, archived_at: null, created_at: '2026-10-15T12:00:00Z', updated_at: '2026-10-15T12:00:00Z', bands: [{ min_cost: '0.00', max_cost: null, markup_percent: '50' }] }
const policy = { inventory_id: 'inventory-1', pricing_version: 1, actual_unit_cost: '10.00', actual_cost_known: true, selling_price: '20.00', pricing_cost_floor: null, minimum_sale_price: null, fixed_sales_price: false }
function setup() { const client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); return (node: React.ReactNode) => render(<QueryClientProvider client={client}>{node}</QueryClientProvider>) }
beforeEach(() => {
  Object.values(mocks).forEach(mock => { if (typeof mock === 'function') mock.mockReset() }); mocks.role = 'garage_owner'
  mocks.get.mockImplementation(async (path: string) => {
    if (path.endsWith('/default')) return { data: { matrix_id: null, generation: 0 } }
    if (path.endsWith('/matrices')) { const { bands, ...summary } = matrix; void bands; return { data: { schema_version: 1, items: [summary], next_cursor: null } } }
    if (path.endsWith('/pricing-policy')) return { data: { schema_version: 1, policy } }
    return { data: { schema_version: 1, matrix } }
  })
})
describe('private parts pricing configuration', () => {
  it('saves an inactive matrix without selecting a default', async () => {
    const user = userEvent.setup(); mocks.post.mockResolvedValue({ data: { schema_version: 1, matrix } }); setup()(<PartsPricingSettings onClose={vi.fn()} />)
    await user.click(await screen.findByText('New matrix')); await user.type(screen.getByLabelText('Name'), 'Standard'); await user.type(screen.getByLabelText('Markup percent band 1'), '50'); await user.click(screen.getByText('Save matrix'))
    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/parts-pricing/matrices', { name: 'Standard', bands: matrix.bands }, expect.objectContaining({ headers: { 'Idempotency-Key': expect.stringMatching(/^[0-9a-f-]{36}$/) } }))); expect(mocks.put).not.toHaveBeenCalled()
  })
  it('requires a separate explicit action to select a default', async () => { const user = userEvent.setup(); mocks.put.mockResolvedValue({ data: { matrix_id: 'matrix-1', generation: 1 } }); setup()(<PartsPricingSettings onClose={vi.fn()} />); await user.click(await screen.findByText('Standard')); await user.click(await screen.findByText('Use as default')); expect(mocks.put).not.toHaveBeenCalled(); await user.click(screen.getByText('Confirm default')); await waitFor(() => expect(mocks.put).toHaveBeenCalledWith('/parts-pricing/default', { matrix_id: 'matrix-1', expected_generation: 0 }, expect.anything())) })
  it('preserves a matrix draft on CAS conflict and needs explicit acceptance of visible current values', async () => {
    const user = userEvent.setup(); let loads = 0; const get = mocks.get.getMockImplementation()!; mocks.get.mockImplementation(async (path: string) => path.endsWith('/matrices/matrix-1') ? { data: { schema_version: 1, matrix: loads++ ? { ...matrix, name: 'Changed by colleague', version: 2, current_revision: 2 } : matrix } } : get(path)); mocks.put.mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'matrix_version_conflict', message: 'Matrix changed.' } } } }).mockResolvedValue({ data: { schema_version: 1, matrix: { ...matrix, version: 3 } } }); setup()(<PartsPricingSettings onClose={vi.fn()} />)
    await user.click(await screen.findByText('Standard')); await user.clear(await screen.findByLabelText('Name')); await user.type(screen.getByLabelText('Name'), 'My draft'); await user.click(screen.getByText('Save matrix')); expect(await screen.findByText(/Current saved matrix · Changed by colleague/)).toBeInTheDocument(); expect(screen.getByLabelText('Name')).toHaveValue('My draft'); expect(screen.getByText('Save matrix')).toBeDisabled(); await user.click(screen.getByText('Keep my draft against this version')); await user.click(screen.getByText('Save matrix')); await waitFor(() => expect(mocks.put).toHaveBeenCalledTimes(2)); expect(mocks.put.mock.calls[1][1]).toMatchObject({ name: 'My draft', expected_version: 2 }); expect(mocks.put.mock.calls[0][2].headers).not.toEqual(mocks.put.mock.calls[1][2].headers)
  })
  it('keeps the same logical UUID when an uncertain config write is retried', async () => { const user = userEvent.setup(); mocks.put.mockRejectedValueOnce(new Error('Network interrupted')).mockResolvedValue({ data: { schema_version: 1, matrix } }); setup()(<PartsPricingSettings onClose={vi.fn()} />); await user.click(await screen.findByText('Standard')); await user.click(await screen.findByText('Save matrix')); await screen.findByRole('alert'); await user.click(screen.getByText('Save matrix')); await waitFor(() => expect(mocks.put).toHaveBeenCalledTimes(2)); expect(mocks.put.mock.calls[0][2].headers).toEqual(mocks.put.mock.calls[1][2].headers) })
  it('writes blank policy limits as null and preserves explicit zero', async () => { const user = userEvent.setup(); const close = vi.fn(); mocks.patch.mockResolvedValue({ data: { schema_version: 1, policy } }); setup()(<PartPricingPolicy inventoryId="inventory-1" name="Filter" onClose={close} />); await user.type(await screen.findByLabelText('Minimum sale price'), '0'); await user.click(screen.getByText('Save policy')); await waitFor(() => expect(mocks.patch).toHaveBeenCalled()); expect(mocks.patch.mock.calls[0][1]).toEqual({ expected_pricing_version: 1, pricing_cost_floor: null, minimum_sale_price: '0.00', fixed_sales_price: false, selling_price: '20.00' }); expect(close).toHaveBeenCalled() })
  it('never renders management configuration for a mechanic', () => { mocks.role = 'mechanic'; setup()(<PartsPricingSettings onClose={vi.fn()} />); expect(screen.queryByRole('dialog')).not.toBeInTheDocument(); expect(mocks.get).not.toHaveBeenCalled() })
  it('rejects foreign inventory policy before showing editable values', async () => { mocks.get.mockResolvedValue({ data: { schema_version: 1, policy: { ...policy, inventory_id: 'foreign' } } }); setup()(<PartPricingPolicy inventoryId="inventory-1" name="Filter" onClose={vi.fn()} />); await screen.findByRole('alert'); expect(screen.queryByLabelText('Minimum sale price')).not.toBeInTheDocument(); expect(screen.getByText('Save policy')).toBeDisabled() })
})
it('normalizes entered decimals without calculating a price', () => { expect(enteredMoney('0')).toBe('0.00'); expect(enteredMoney('')).toBeNull(); expect(enteredMoney('0001.2')).toBe('1.20'); expect(() => enteredMoney('1e2')).toThrow(); expect(() => enteredMoney('1.005')).toThrow() })

it('preserves a policy draft until the operator accepts the visible fresh baseline', async () => {
  const user = userEvent.setup(); let reads = 0
  mocks.get.mockImplementation(async () => ({ data: { schema_version: 1, policy: reads++ ? { ...policy, selling_price: '25.00', pricing_version: 2 } : policy } }))
  mocks.patch.mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'pricing_version_conflict', message: 'Saved policy changed.' } } } }).mockResolvedValue({ data: { schema_version: 1, policy: { ...policy, pricing_version: 3 } } })
  setup()(<PartPricingPolicy inventoryId="inventory-1" name="Filter" onClose={vi.fn()} />)
  await user.clear(await screen.findByLabelText('Catalog price')); await user.type(screen.getByLabelText('Catalog price'), '30'); await user.click(screen.getByText('Save policy')); expect(await screen.findByText(/Catalog \$25.00/)).toBeInTheDocument(); expect(screen.getByLabelText('Catalog price')).toHaveValue('30'); expect(screen.getByText('Save policy')).toBeDisabled()
  await user.click(screen.getByText('Keep my draft against this version')); await user.click(screen.getByText('Save policy')); await waitFor(() => expect(mocks.patch).toHaveBeenCalledTimes(2)); expect(mocks.patch.mock.calls[1][1]).toMatchObject({ selling_price: '30.00', expected_pricing_version: 2 })
})
it('ignores a policy write completion after authority changes before rerender', async () => {
  let settle!: (value: unknown) => void; const close = vi.fn(); const saved = vi.fn(); mocks.patch.mockReturnValue(new Promise(resolve => { settle = resolve })); const user = userEvent.setup(); setup()(<PartPricingPolicy inventoryId="inventory-1" name="Filter" onClose={close} onSaved={saved} />)
  await screen.findByLabelText('Catalog price'); await user.click(screen.getByText('Save policy')); mocks.role = 'mechanic'; await act(async () => settle({ data: { schema_version: 1, policy } })); expect(close).not.toHaveBeenCalled(); expect(saved).not.toHaveBeenCalled()
})

describe('visible pricing action feedback', () => {
  async function sampleDraft(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByText('New matrix'))
    await user.type(screen.getByLabelText('Name'), 'Unsaved matrix')
    await user.type(screen.getByLabelText('Cost to band 1'), '25')
    await user.type(screen.getByLabelText('Markup percent band 1'), '100')
    await user.click(screen.getByText('Add band'))
    await user.type(screen.getByLabelText('Cost to band 2'), '100')
    await user.type(screen.getByLabelText('Markup percent band 2'), '50')
    await user.click(screen.getByText('Add band'))
    await user.type(screen.getByLabelText('Markup percent band 3'), '30')
    await user.type(screen.getByLabelText('Actual cost'), '100')
    await user.type(screen.getByLabelText('Catalog price'), '45')
  }

  it('reveals a rejected sample beside its action, keeps the complete draft, and allows correction and Escape', async () => {
    const user = userEvent.setup(); const close = vi.fn()
    mocks.post.mockRejectedValue({ response: { status: 422, data: { detail: { message: 'Bands must be contiguous.' } } } })
    setup()(<PartsPricingSettings onClose={close} />)
    await sampleDraft(user)
    await user.clear(screen.getByLabelText('Cost from band 2')); await user.type(screen.getByLabelText('Cost from band 2'), '26')
    await user.click(screen.getByText('Preview sample'))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Bands must be contiguous.')
    expect(alert.closest('.db-parts-pricing__sample')).toContainElement(screen.getByText('Preview sample'))
    expect(alert).toHaveFocus()
    expect(screen.getByLabelText('Name')).toHaveValue('Unsaved matrix')
    expect(screen.getByLabelText('Cost from band 2')).toHaveValue('26')
    expect(screen.getByLabelText('Markup percent band 3')).toHaveValue('30')
    expect(screen.getByLabelText('Actual cost')).toHaveValue('100')
    await user.clear(screen.getByLabelText('Cost from band 2')); await user.type(screen.getByLabelText('Cost from band 2'), '25')
    expect(screen.getByLabelText('Cost from band 2')).toHaveFocus()
    await user.click(screen.getByText('Preview sample'))
    await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(2))
    expect(await screen.findByRole('alert')).toHaveFocus()
    expect(mocks.post.mock.calls.every(([path]) => path === '/parts-pricing/preview')).toBe(true)
    await user.keyboard('{Escape}'); expect(close).toHaveBeenCalledOnce()
  })

  it('reveals the whole successful sample outcome and keeps draft values until edited', async () => {
    const user = userEvent.setup()
    const evaluation = { status: 'priced', unit_price: '45.00', source: 'catalog', pricing_basis: '100.00', effective_minimum: null, band: null, gross_profit: '-55.00', markup_percent: '-55', margin_percent: '-122.22', warnings: [], errors: [] }
    mocks.post.mockResolvedValue({ data: { schema_version: 1, currency: 'USD', current_default: { matrix_id: null, generation: 0 }, cases: [{ sample_key: 'sample', inventory_id: null, label: 'Sample part', actual_unit_cost: '100.00', actual_cost_known: true, catalog_unit_price: '45.00', current: evaluation, proposed: { ...evaluation, unit_price: '130.00', source: 'matrix', band: { min_cost: '100.00', max_cost: null, markup_percent: '30' }, gross_profit: '30.00', markup_percent: '30', margin_percent: '23.08' } }] } })
    setup()(<PartsPricingSettings onClose={vi.fn()} />)
    await sampleDraft(user); await user.click(screen.getByText('Preview sample'))
    const outcome = await screen.findByRole('status')
    expect(within(outcome).getByText('Proposed $130.00')).toBeInTheDocument()
    expect(within(outcome).getByText('Profit $30.00 · Markup 30% · Margin 23.08%')).toBeInTheDocument()
    expect(outcome).toHaveFocus()
    expect(screen.getByLabelText('Name')).toHaveValue('Unsaved matrix')
    expect(screen.getByLabelText('Cost from band 3')).toHaveValue('100')
    await user.type(screen.getByLabelText('Actual cost'), '0')
    expect(screen.getByLabelText('Actual cost')).toHaveFocus()
    expect(screen.queryByText('Proposed $130.00')).not.toBeInTheDocument()
  })

  it('reveals matrix-save rejection without discarding the draft', async () => {
    const user = userEvent.setup()
    mocks.post.mockRejectedValue({ response: { status: 422, data: { detail: { message: 'Bands must be contiguous.' } } } })
    setup()(<PartsPricingSettings onClose={vi.fn()} />)
    await sampleDraft(user); await user.click(screen.getByText('Save matrix'))
    expect(await screen.findByRole('alert')).toHaveFocus()
    expect(screen.getByLabelText('Name')).toHaveValue('Unsaved matrix')
    expect(screen.getByLabelText('Markup percent band 3')).toHaveValue('30')
    expect(mocks.post.mock.calls[0][0]).toBe('/parts-pricing/matrices')
  })

  it.each(['entered amount', 'server rejection'])('reveals policy %s errors and keeps editable values', async (cause) => {
    const user = userEvent.setup(); const close = vi.fn()
    mocks.patch.mockRejectedValue({ response: { status: 422, data: { detail: { message: 'Policy could not be saved.' } } } })
    setup()(<PartPricingPolicy inventoryId="inventory-1" name="Filter" onClose={close} />)
    const amount = cause === 'entered amount' ? '1.005' : '15'
    await user.type(await screen.findByLabelText('Minimum sale price'), amount)
    await user.click(screen.getByText('Save policy'))
    expect(await screen.findByRole('alert')).toHaveFocus()
    expect(screen.getByLabelText('Minimum sale price')).toHaveValue(amount)
    expect(screen.getByLabelText('Catalog price')).toHaveValue('20.00')
    if (cause === 'entered amount') expect(mocks.patch).not.toHaveBeenCalled()
    else expect(mocks.patch).toHaveBeenCalledOnce()
    await user.click(screen.getByLabelText('Minimum sale price'))
    expect(screen.getByLabelText('Minimum sale price')).toHaveFocus()
    await user.keyboard('{Escape}'); expect(close).toHaveBeenCalledOnce()
  })
})
