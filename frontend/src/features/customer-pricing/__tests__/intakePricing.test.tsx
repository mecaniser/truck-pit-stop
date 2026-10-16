import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ get: vi.fn(), submit: vi.fn(), state: { user: { id: 'user', tenant_id: 'tenant', role: 'garage_owner' }, authSessionEpoch: 1 } }))
vi.mock('@/lib/api', () => ({ default: mocks }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: Object.assign((select: (state: typeof mocks.state) => unknown) => select(mocks.state), { getState: () => mocks.state }) }))
import { useIntakePricing } from '../useIntakePricing'
const initial = { schema_version: 1, customer_id: 'customer-1', vehicle_id: 'vehicle-1', expected_pricing_policy: 'token-1', policy_kind: 'external', projection: 'shop', labor: { source: 'customer', rate: '125.00' }, parts: { source: 'customer', mode: 'matrix' } }
let change!: ReturnType<typeof useIntakePricing>['handleConflict']
function Harness({ customer = 'customer-1', vehicle = 'vehicle-1', enabled = true, projection = 'shop' }: { customer?: string; vehicle?: string; enabled?: boolean; projection?: 'shop' | 'fleet' }) {
  const pricing = useIntakePricing(customer, vehicle, enabled, projection); change = pricing.handleConflict
  return <>{pricing.notice}<input aria-label="Work draft" defaultValue="Inspect brakes" /><button disabled={!pricing.ready} onClick={() => mocks.submit(pricing.confirmation())}>Create order</button></>
}
function setup(props: React.ComponentProps<typeof Harness> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); const node = (next: typeof props) => <QueryClientProvider client={client}><Harness {...next} /></QueryClientProvider>
  const view = render(node(props)); return { client, ...view, changeProps: (next: typeof props) => view.rerender(node(next)) }
}
beforeEach(() => { mocks.get.mockReset(); mocks.submit.mockReset(); mocks.state = { user: { id: 'user', tenant_id: 'tenant', role: 'garage_owner' }, authSessionEpoch: 1 }; mocks.get.mockResolvedValue({ data: initial }) })
it('binds the displayed account, vehicle and projection to the creation precondition', async () => {
  setup(); expect(screen.getByText('Create order')).toBeDisabled(); await screen.findByText(/Labor \$125.00\/hr/)
  fireEvent.click(screen.getByText('Create order')); expect(mocks.submit).toHaveBeenCalledWith({ expected_pricing_policy: 'token-1', pricing_presentation: 'shop' })
  expect(mocks.get).toHaveBeenCalledWith('/customers/customer-1/pricing-preview', expect.objectContaining({ params: { vehicle_id: 'vehicle-1', pricing_presentation: 'shop' } }))
})
it('shows fresh terms after 409, preserves work, and requires explicit acceptance without submitting', async () => {
  setup(); await screen.findByText(/125.00/)
  act(() => { expect(change({ response: { data: { detail: { code: 'account_pricing_changed', preview: { ...initial, expected_pricing_policy: 'token-2', labor: { source: 'customer', rate: '135.00' } } } } } })).toBe(true) })
  expect(screen.getByText(/135.00/)).toBeVisible(); expect(screen.getByText('Create order')).toBeDisabled(); expect(screen.getByLabelText('Work draft')).toHaveValue('Inspect brakes'); expect(mocks.submit).not.toHaveBeenCalled()
  fireEvent.click(screen.getByText('Use current defaults')); expect(mocks.submit).not.toHaveBeenCalled(); fireEvent.click(screen.getByText('Create order')); expect(mocks.submit).toHaveBeenCalledWith({ expected_pricing_policy: 'token-2', pricing_presentation: 'shop' })
})
it.each([{ customer_id: 'foreign' }, { vehicle_id: 'foreign' }, { projection: 'fleet' }, { private_reason: 'private' }])('fails closed on invalid preview %j', async wrong => {
  mocks.get.mockResolvedValue({ data: { ...initial, ...wrong } }); setup(); await screen.findByRole('alert'); expect(screen.getByText('Create order')).toBeDisabled(); expect(screen.queryByText(/125.00/)).not.toBeInTheDocument()
})
it('requests only the fleet projection and never renders money or provenance', async () => {
  mocks.state.user.role = 'fleet_manager'; mocks.get.mockResolvedValue({ data: { schema_version: 1, customer_id: initial.customer_id, vehicle_id: initial.vehicle_id, expected_pricing_policy: 'fleet-token', policy_kind: 'external', projection: 'fleet', agreement_applies: true } })
  setup({ projection: 'fleet' }); await screen.findByText('Account pricing applies'); expect(screen.queryByText(/\$|matrix|125/)).not.toBeInTheDocument(); expect(mocks.get.mock.calls[0][1].params.pricing_presentation).toBe('fleet')
})
it('discards a prior customer response and conflict after the selected account changes', async () => {
  let settle!: (value: unknown) => void; mocks.get.mockReturnValueOnce(new Promise(resolve => { settle = resolve })).mockResolvedValue({ data: { ...initial, customer_id: 'customer-2', labor: { source: 'shop', rate: '145.00' } } })
  const view = setup(); const previousConflict = change; view.changeProps({ customer: 'customer-2' }); await screen.findByText(/145.00/)
  await act(async () => settle({ data: initial })); act(() => expect(previousConflict({ response: { data: { detail: { code: 'account_pricing_changed', preview: initial } } } })).toBe(false))
  expect(screen.queryByText(/125.00/)).not.toBeInTheDocument(); fireEvent.click(screen.getByText('Create order')); expect(mocks.submit).toHaveBeenCalledWith({ expected_pricing_policy: 'token-1', pricing_presentation: 'shop' })
})
it('removes private cached preview on close and refetches when reopened', async () => {
  const view = setup(); await screen.findByText(/125.00/); const previousConflict = change; view.changeProps({ enabled: false }); expect(screen.queryByText(/125.00/)).not.toBeInTheDocument()
  act(() => expect(previousConflict({ response: { data: { detail: { code: 'account_pricing_changed', preview: initial } } } })).toBe(false))
  mocks.get.mockResolvedValue({ data: { ...initial, expected_pricing_policy: 'reopened', labor: { source: 'shop', rate: '145.00' } } }); view.changeProps({ enabled: true })
  await screen.findByText(/145.00/); await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2))
})
it('does not request a manager preview for a mechanic or unresolved account', () => {
  mocks.state.user.role = 'mechanic'; setup({ customer: '' }); expect(mocks.get).not.toHaveBeenCalled(); expect(screen.queryByText(/pricing/)).not.toBeInTheDocument()
})
