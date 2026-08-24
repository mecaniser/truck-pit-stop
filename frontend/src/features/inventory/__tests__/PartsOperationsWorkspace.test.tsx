import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import fixture from '../../../../../backend/tests/fixtures/db038_parts_operations.json'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const authState = vi.hoisted(() => ({ role: 'garage_owner' }))

vi.mock('@/lib/api', () => ({ default: { get: apiMocks.get, post: apiMocks.post } }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (selector: (state: { user: { role: string } }) => unknown) => selector({ user: { role: authState.role } }) }))

import { PartsOperationsGate } from '../PartsOperationsWorkspace'

const oilFilter = fixture.read_contract.expected_oil_filter_demand
const inventoryItem = { ...fixture.inventory[0], tenant_id: fixture.tenant_ids.primary, description: null, category: 'Filters', core_charge: '0.00', selling_price: '20.00', supplier_name: 'Fleet Parts Co', supplier_contact: null, image_url: null, location: 'A-01', is_placeholder: false, created_at: fixture.frozen_at, updated_at: fixture.frozen_at } as const

function LocationProbe() { return <output data-testid="location">{useLocation().pathname}{useLocation().search}</output> }
function renderGate() { const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } }); return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/dashboard/garage/inventory']}><PartsOperationsGate legacy={<p>Legacy inventory catalog</p>} /><LocationProbe /></MemoryRouter></QueryClientProvider>) }

function installFixture() {
  apiMocks.get.mockImplementation((url: string) => {
    if (url === '/parts-operations/summary') return Promise.resolve({ data: { low_stock_count: 1, open_purchase_order_count: 1 } })
    if (url === '/parts-operations/demand') return Promise.resolve({ data: { items: [oilFilter], total: 1, skip: 0, limit: 100, has_more: false } })
    if (url === '/inventory') return Promise.resolve({ data: { items: [inventoryItem], total: 1, skip: 0, limit: 100, has_more: false } })
    if (url === '/parts-operations/purchase-orders') return Promise.resolve({ data: { items: [], total: 0, skip: 0, limit: 100, has_more: false } })
    if (url === '/parts-operations/returns' || url === '/parts-operations/cores' || url === '/parts-operations/activity') return Promise.resolve({ data: { items: [], total: 0, skip: 0, limit: 100, has_more: false } })
    throw new Error(`Unexpected GET ${url}`)
  })
  apiMocks.post.mockResolvedValue({ data: { id: 'po-created' } })
}

describe('DB-038 Parts Operations workspace', () => {
  afterEach(() => { apiMocks.get.mockReset(); apiMocks.post.mockReset(); authState.role = 'garage_owner' })
  it('falls back to the existing catalog only when the server says the feature is unavailable', async () => { apiMocks.get.mockRejectedValue(Object.assign(new Error('off'), { response: { status: 404 } })); renderGate(); expect(await screen.findByText('Legacy inventory catalog')).toBeInTheDocument() })
  it('keeps a transient server failure visible instead of silently simulating an enabled feature', async () => { apiMocks.get.mockRejectedValue(Object.assign(new Error('offline'), { response: { status: 503 } })); renderGate(); expect(await screen.findByRole('alert')).toHaveTextContent('temporarily unavailable'); expect(screen.queryByText('Legacy inventory catalog')).not.toBeInTheDocument() })
  it('uses frozen demand evidence, deep-links to the canonical repair order, and posts an idempotent PO draft', async () => {
    installFixture(); const user = userEvent.setup(); renderGate()
    expect(await screen.findByRole('heading', { name: 'Supply, stock & custody' })).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: /Oil filter/i }))
    await user.click(await screen.findByRole('button', { name: /Repair order TPS-000301/i })); expect(screen.getByTestId('location')).toHaveTextContent('/dashboard/repair-orders?selected=30000000-0000-4000-8000-000000000301')
    await user.type(screen.getByLabelText('PO number'), 'PO-000302'); await user.click(screen.getByRole('button', { name: 'Create draft PO' }))
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/parts-operations/purchase-orders', expect.objectContaining({ supplier_id: fixture.ids.supplier, lines: [expect.objectContaining({ inventory_id: fixture.ids.oil_filter, ordered_quantity: 3 })] }), expect.objectContaining({ headers: expect.objectContaining({ 'Idempotency-Key': expect.stringMatching(/^po-create-/) }) })))
  })
  it('keeps reception staff read-only while exposing the same demand evidence', async () => { authState.role = 'receptionist'; installFixture(); const user = userEvent.setup(); renderGate(); await user.click(await screen.findByRole('button', { name: /Oil filter/i })); expect(screen.getByText(/Read-only access/)).toBeInTheDocument(); expect(screen.queryByRole('button', { name: 'Create draft PO' })).not.toBeInTheDocument() })
  it('keeps the operation tabs keyboard-operable without inventing a route', async () => {
    installFixture()
    const user = userEvent.setup()
    renderGate()
    const demand = await screen.findByRole('tab', { name: 'Demand' })
    demand.focus()
    await user.keyboard('{ArrowRight}')
    const inventory = screen.getByRole('tab', { name: 'Inventory' })
    expect(inventory).toHaveAttribute('aria-selected', 'true')
    expect(inventory).toHaveFocus()
    expect(screen.getByRole('tabpanel', { name: 'Inventory' })).toBeInTheDocument()
  })
})
