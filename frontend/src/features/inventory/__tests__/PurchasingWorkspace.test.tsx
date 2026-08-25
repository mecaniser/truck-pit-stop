import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const authState = vi.hoisted(() => ({ role: 'garage_owner', id: 'user-1', tenant_id: 'tenant-1' }))

vi.mock('@/lib/api', () => ({ default: { get: apiMocks.get, post: apiMocks.post } }))
vi.mock('@/stores/authStore', () => {
  const state = () => ({ user: { role: authState.role, id: authState.id, tenant_id: authState.tenant_id } })
  const useAuthStore = Object.assign((selector: (value: ReturnType<typeof state>) => unknown) => selector(state()), { getState: state })
  return { useAuthStore }
})
vi.mock('@/features/suppliers/SuppliersPage', () => ({ default: () => <div>Suppliers workspace</div> }))
vi.mock('../PartsOperationsWorkspace', () => ({ default: () => <div>Purchase orders workspace</div> }))

import PurchasingWorkspace from '../PurchasingWorkspace'
import {
  purchasePreparationStorageKey,
  type PurchasePreparationLine,
} from '../PartsInventoryWorkspace'

const assignedLine: PurchasePreparationLine = {
  inventoryId: 'part-assigned',
  name: 'Alternator',
  sku: 'ALT-42',
  sourceId: 'source-1',
  supplierId: 'supplier-1',
  supplierName: 'Fleet Parts Co',
  supplierPartNumber: 'FPC-ALT-42',
  quantity: 4,
  unitCost: '10.00',
  minimumOrderQuantity: 2,
  packQuantity: 2,
  blockedReason: null,
}

const blockedLine: PurchasePreparationLine = {
  inventoryId: 'part-blocked',
  name: 'Fuel filter kit',
  sku: 'FILTER-UNASSIGNED',
  sourceId: null,
  supplierId: null,
  supplierName: null,
  supplierPartNumber: null,
  quantity: 3,
  unitCost: '8.50',
  minimumOrderQuantity: 1,
  packQuantity: 1,
  blockedReason: 'supplier_source_required',
}

function storePreparation(lines: PurchasePreparationLine[]) {
  window.sessionStorage.setItem(purchasePreparationStorageKey(), JSON.stringify(lines))
}

function renderPurchasing() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/dashboard/garage/purchasing?view=orders']}>
        <PurchasingWorkspace />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('DB-038 Purchasing preparation handoff', () => {
  afterEach(() => {
    apiMocks.get.mockReset()
    apiMocks.post.mockReset()
    authState.role = 'garage_owner'
    window.sessionStorage.clear()
  })

  it('groups assigned lines, keeps unassigned lines visible, and excludes blocked lines from draft totals and payloads', async () => {
    apiMocks.get.mockResolvedValue({ data: { low_stock_count: 2, open_purchase_order_count: 0 } })
    apiMocks.post.mockResolvedValue({ data: { count: 1 } })
    storePreparation([assignedLine, blockedLine])
    const user = userEvent.setup()
    renderPurchasing()

    expect(await screen.findByRole('heading', { name: 'Fleet Parts Co' })).toBeInTheDocument()
    expect(screen.getByText('1 line · $40.00')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Supplier required' })).toBeInTheDocument()
    expect(screen.getByText('Excluded from this batch')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Create 1 draft order' }))
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/parts-operations/purchase-orders/batch', {
      groups: [{
        supplier_id: 'supplier-1',
        lines: [{ inventory_id: 'part-assigned', source_id: 'source-1', ordered_quantity: 4, unit_cost: '10.00' }],
      }],
      notes: 'Prepared from Parts & inventory',
    }, { headers: { 'Idempotency-Key': expect.stringMatching(/^po-batch-/) } }))

    await waitFor(() => expect(JSON.parse(window.sessionStorage.getItem(purchasePreparationStorageKey()) || '[]')).toEqual([blockedLine]))
    expect(screen.getByRole('status', { name: 'Purchase preparation result' })).toHaveTextContent('1 blocked part remains in preparation')
  })

  it('retains the complete tray on failure and reuses one idempotency key for the retry', async () => {
    apiMocks.get.mockResolvedValue({ data: { low_stock_count: 1, open_purchase_order_count: 0 } })
    apiMocks.post
      .mockRejectedValueOnce({ response: { status: 502, data: { detail: 'Supplier system unavailable.' } } })
      .mockResolvedValueOnce({ data: { count: 1 } })
    storePreparation([assignedLine, blockedLine])
    const user = userEvent.setup()
    renderPurchasing()

    await user.click(await screen.findByRole('button', { name: 'Create 1 draft order' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Supplier system unavailable.')
    expect(JSON.parse(window.sessionStorage.getItem(purchasePreparationStorageKey()) || '[]')).toEqual([assignedLine, blockedLine])
    const firstKey = apiMocks.post.mock.calls[0][2].headers['Idempotency-Key']

    await user.click(screen.getByRole('button', { name: 'Create 1 draft order' }))
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledTimes(2))
    expect(apiMocks.post.mock.calls[1][2].headers['Idempotency-Key']).toBe(firstKey)
  })

  it('uses the shared pack-aware quantity stepper for totals, payloads, typed normalization, and removal', async () => {
    apiMocks.get.mockResolvedValue({ data: { low_stock_count: 1, open_purchase_order_count: 0 } })
    apiMocks.post.mockResolvedValue({ data: { count: 1 } })
    storePreparation([assignedLine])
    const user = userEvent.setup()
    renderPurchasing()

    const quantity = await screen.findByRole('textbox', { name: 'Quantity for Alternator' })
    expect(screen.queryByRole('spinbutton', { name: 'Quantity for Alternator' })).not.toBeInTheDocument()
    expect(quantity.closest('.db-purchasing__quantity-stepper')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Decrease Quantity for Alternator' }))
    expect(quantity).toHaveValue('2')
    expect(screen.getByText('1 line · $20.00')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Decrease Quantity for Alternator' }))
    expect(quantity).toHaveValue('2')

    await user.click(screen.getByRole('button', { name: 'Increase Quantity for Alternator' }))
    expect(quantity).toHaveValue('4')
    await user.clear(quantity)
    await user.type(quantity, '5')
    await user.tab()
    await waitFor(() => expect(quantity).toHaveValue('6'))
    expect(screen.getByText('1 line · $60.00')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Create 1 draft order' }))
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/parts-operations/purchase-orders/batch', expect.objectContaining({
      groups: [expect.objectContaining({ lines: [expect.objectContaining({ ordered_quantity: 6 })] })],
    }), expect.any(Object)))

    act(() => {
      storePreparation([assignedLine])
      window.dispatchEvent(new Event('db038:purchase-preparation'))
    })
    await user.click(await screen.findByRole('button', { name: 'Remove Alternator from purchase preparation' }))
    expect(screen.getByText('No parts are waiting to be prepared.')).toBeInTheDocument()
  })

  it('keeps reception staff read-only without a fake enabled batch action', async () => {
    authState.role = 'receptionist'
    apiMocks.get.mockResolvedValue({ data: { low_stock_count: 1, open_purchase_order_count: 0 } })
    storePreparation([assignedLine])
    renderPurchasing()

    expect(await screen.findByText('Read-only access. Owners and admins can create draft purchase orders.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create 1 draft order' })).toBeDisabled()
    expect(apiMocks.post).not.toHaveBeenCalled()
  })
})
