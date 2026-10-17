import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { User } from '@/types'
import type { TargetRequest } from '@/features/maintenance/contract'
import { orderMaintenance, program, targetPreview, work } from '@/features/maintenance/__tests__/fixtures'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: apiMocks }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))
vi.mock('@/hooks/useWebSocket', () => ({ useWebSocket: vi.fn() }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ accentColors: { 500: '#f59e0b' } }) }))
vi.mock('../PriceBuilderPanel', () => ({ default: (props: { onCompleteWorkOrder?: (mileage: number) => void; onApproveCompletion?: () => void }) => <>
  <button type="button" onClick={() => props.onCompleteWorkOrder?.(12345)}>Complete work callback</button>
  <button type="button" onClick={props.onApproveCompletion}>Approve completion callback</button>
</> }))

import { useAuthStore } from '@/stores/authStore'
import RepairOrdersPage from '../RepairOrdersPage'

const order = {
  id: 'order-1', tenant_id: 'tenant-1', customer_id: 'customer-1', vehicle_id: 'vehicle-1',
  vehicle_make: 'Freightliner', vehicle_model: 'Cascadia', vehicle_year: 2022, vehicle_unit_number: '22',
  vehicle_vin: 'VIN22', customer_company_name: 'North Freight', customer_email: 'dispatch@example.test',
  order_number: 'RO-000001', status: 'pending_review', description: 'Maintenance service', customer_notes: null,
  internal_notes: null, assigned_mechanic_id: null, total_parts_cost: '0.00', total_labor_cost: '100.00',
  total_cost: '100.00', created_at: '2026-10-01T12:00:00Z', updated_at: '2026-10-01T13:00:00Z',
  is_internal: false,
}
let internal = false
let expectedChannel: 'shop' | 'fleet' = 'shop'
beforeEach(() => {
  apiMocks.get.mockReset(); apiMocks.post.mockReset(); apiMocks.put.mockReset()
  Object.defineProperty(window, 'scrollTo', { value: vi.fn(), configurable: true })
  apiMocks.get.mockImplementation(async (url: string, config?: { params?: { channel?: string } }) => {
    const current = { ...order, is_internal: internal }
    if (url === '/repair-orders') return { data: { items: [], total: 0, has_more: false } }
    if (url.endsWith('/workspace')) return { data: current }
    if (url.endsWith('/detail')) return { data: { ...current, parts_usage: [], labor_items: [], history_events: [] } }
    if (url.endsWith('/maintenance')) { if (config?.params?.channel !== expectedChannel) throw new Error('422: exact maintenance channel is required'); return { data: orderMaintenance([program('program-1', { work: work() })]) } }
    if (url.endsWith('/history')) return { data: { revisions: [], events: [] } }
    if (url === '/dashboard/stats') return { data: { mechanic_workload: [] } }
    if (url.includes('/settings')) return { data: { labor_rate: 100 } }
    if (url.startsWith('/quotes?')) return { data: null }
    return { data: [] }
  })
  apiMocks.post.mockImplementation(async (url: string, body: TargetRequest) => {
    if (url.endsWith('/maintenance-target-preview')) return { data: targetPreview(body) }
    if (url.endsWith('/complete')) return { data: { repair_order_id: order.id, raw_status: 'invoiced' } }
    if (url.endsWith('/approve-completion')) return { data: { ...order, status: 'invoiced' } }
    throw new Error(`Unexpected POST ${url}`)
  })
})
afterEach(() => { useAuthStore.setState({ user: null, isAuthenticated: false }); vi.clearAllMocks() })

describe('RepairOrdersPage maintenance finalization adapters', () => {
  it.each([
    ['garage_owner', true, 'Complete work callback', 'fleet', '/fleet/work-orders/order-1/complete'],
    ['garage_admin', true, 'Complete work callback', 'fleet', '/fleet/work-orders/order-1/complete'],
    ['fleet_manager', true, 'Complete work callback', 'fleet', '/fleet/work-orders/order-1/complete'],
    ['garage_owner', true, 'Approve completion callback', 'fleet', '/fleet/work-orders/order-1/complete'],
    ['garage_owner', false, 'Approve completion callback', 'shop', '/repair-orders/order-1/approve-completion'],
    ['fleet_manager', false, 'Approve completion callback', 'fleet', '/repair-orders/order-1/approve-completion'],
  ] as const)('uses the %s actor’s endpoint projection for internal=%s via %s', async (role, isInternal, callback, channel, endpoint) => {
    internal = isInternal
    expectedChannel = channel
    useAuthStore.setState({ user: { id: 'actor-1', tenant_id: 'tenant-1', role, first_name: 'Staff', last_name: 'User', email: 'staff@example.test', is_active: true, phone: null, customer_id: null } as User, isAuthenticated: true, logoutInProgress: false })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    const view = render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/?selected=order-1']}><RepairOrdersPage /></MemoryRouter></QueryClientProvider>)
    const user = userEvent.setup(); await user.click(await screen.findByRole('button', { name: callback }))
    const review = await screen.findByRole('dialog', { name: 'Review maintenance completion' }); expect(apiMocks.get).toHaveBeenCalledWith('/repair-orders/order-1/maintenance', expect.objectContaining({ params: { channel } })); await user.click(within(review).getByRole('button', { name: 'Review targets' }))
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/vehicles/vehicle-1/maintenance-target-preview', expect.objectContaining({ purpose: 'completion', channel, repair_order_id: 'order-1' }), expect.anything()))
    await user.click(within(review).getByRole('button', { name: 'Finalize & Send Invoice' }))
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith(endpoint, expect.objectContaining({ maintenance_review: expect.objectContaining({ request_id: expect.stringMatching(/^[0-9a-f-]{36}$/), expected_review_fingerprint: 'review-1', expected_target_fingerprint: 'target-1', entries: [{ work_link_id: 'link-1', expected_link_version: 1, program: { program_id: 'program-1', expected_version: 1 }, attestation: null }] }) })))
    const writes = apiMocks.post.mock.calls.filter(([url]) => !url.endsWith('/maintenance-target-preview')); expect(writes).toHaveLength(1); expect(writes[0][1].mileage_out).toBe(callback === 'Complete work callback' ? 12345 : null)
    await waitFor(() => expect(review).not.toBeInTheDocument()); view.unmount(); client.clear()
  })
})
