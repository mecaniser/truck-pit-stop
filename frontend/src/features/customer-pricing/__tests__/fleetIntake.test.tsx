import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, expect, it, vi } from 'vitest'
import type { BoardTruck } from '@/features/fleet/types'
import type { ResolveRequest } from '@/features/parts-pricing/contract'
import { quote } from '@/features/parts-pricing/__tests__/fixtures'
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), done: vi.fn(), close: vi.fn(), state: { user: { id: 'manager', tenant_id: 'tenant', role: 'fleet_manager' }, authSessionEpoch: 1 } }))
vi.mock('@/lib/api', () => ({ default: mocks }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: Object.assign((select: (state: typeof mocks.state) => unknown) => select(mocks.state), { getState: () => mocks.state }) }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))
import { SchedulePMModal } from '@/features/fleet/FleetModals'

const truck = { id: 'truck-1', unit_number: '603', year: 2021, make: 'Volvo', model: 'VNL', vin: '4V4NC9EH0MN000603', plate: '', status: 'yard', odometer: 600_000, pm_interval_miles: 25_000, moving: false, open_work_order_count: 0, open_incident_count: 0 } as BoardTruck
const preview = { schema_version: 1, customer_id: 'account-1', vehicle_id: truck.id, expected_pricing_policy: 'fleet-policy-1', policy_kind: 'external', projection: 'fleet', agreement_applies: true }
function setup() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><SchedulePMModal truck={truck} createMode onClose={mocks.close} onDone={mocks.done} /></QueryClientProvider>)
}
beforeEach(() => {
  vi.clearAllMocks()
  mocks.get.mockImplementation(async (path: string) => ({ data: path.endsWith('/relationships') ? [{ id: 'relationship', customer_id: 'account-1', relationship_type: 'default_payer', is_primary: true, customer_company_name: 'Account one' }] : path.endsWith('/pricing-preview') ? preview : [] }))
  mocks.post.mockImplementation(async (path: string, body: ResolveRequest) => ({ data: path === '/parts-pricing/resolve' ? quote({ projection: 'fleet', required: false, plan: body.plan }) : truck }))
})
it('creates fleet work with its safe account token and the existing P1 confirmation only', async () => {
  setup(); await screen.findByText('Account pricing applies')
  fireEvent.click(screen.getByRole('button', { name: 'Create repair order' }))
  await waitFor(() => expect(mocks.done).toHaveBeenCalledOnce())
  expect(mocks.get).toHaveBeenCalledWith('/customers/account-1/pricing-preview', expect.objectContaining({ params: { vehicle_id: truck.id, pricing_presentation: 'fleet' } }))
  expect(mocks.post).toHaveBeenCalledWith(`/fleet/trucks/${truck.id}/schedule-pm`, expect.objectContaining({ expected_pricing_policy: 'fleet-policy-1', pricing_presentation: 'fleet', pricing_preview_fingerprint: 'opaque-1', bill_to_customer_id: 'account-1' }), expect.anything())
  expect(screen.queryByText(/Labor \$|Account matrix|Shop matrix/)).not.toBeInTheDocument()
  expect(mocks.get.mock.calls.some(([path]) => path.includes('pricing-policy'))).toBe(false)
})
it('keeps fleet selection and explicitly reaccepts changed account defaults without exposing rates', async () => {
  let writes = 0
  mocks.post.mockImplementation(async (path, body) => {
    if (path === '/parts-pricing/resolve') return { data: quote({ projection: 'fleet', required: false, plan: body.plan }) }
    if (!writes++) throw { response: { status: 409, data: { detail: { code: 'account_pricing_changed', message: 'Account defaults changed.', preview: { ...preview, expected_pricing_policy: 'fleet-policy-2', agreement_applies: false } } } } }
    return { data: truck }
  })
  setup(); await screen.findByText('Account pricing applies'); const submit = screen.getByRole('button', { name: 'Create repair order' }); fireEvent.click(submit)
  await screen.findByRole('button', { name: 'Use current defaults' }); expect(submit).toBeDisabled(); expect(mocks.done).not.toHaveBeenCalled()
  expect(screen.getByText('Shop pricing applies')).toBeVisible(); expect(screen.queryByText(/Labor \$|Account matrix|Shop matrix/)).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Use current defaults' })); expect(writes).toBe(1); fireEvent.click(submit)
  await waitFor(() => expect(mocks.done).toHaveBeenCalledOnce())
  const calls = mocks.post.mock.calls.filter(([path]) => path.endsWith('/schedule-pm'))
  expect(calls).toHaveLength(2); expect(calls[1][1]).toMatchObject({ expected_pricing_policy: 'fleet-policy-2', pricing_presentation: 'fleet' })
})
