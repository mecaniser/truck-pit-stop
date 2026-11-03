import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '@/stores/authStore'
import type { Invoice, Quote, RepairOrder } from '@/types'

const apiMocks = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('@/lib/api', () => ({
  default: { get: apiMocks.get },
}))

import PortalDashboardPage from '../PortalDashboardPage'

const order = (overrides: Partial<RepairOrder> = {}): RepairOrder => ({
  id: 'order-1',
  tenant_id: 'tenant-1',
  customer_id: 'customer-1',
  vehicle_id: 'vehicle-1',
  vehicle_make: 'Freightliner',
  vehicle_model: 'Cascadia',
  vehicle_year: 2022,
  vehicle_unit_number: '1047',
  vehicle_vin: '••••1234',
  order_number: 'RO-000001',
  status: 'in_progress',
  description: 'Additional electrical diagnosis',
  customer_notes: null,
  internal_notes: null,
  assigned_mechanic_id: null,
  total_parts_cost: '0.00',
  total_labor_cost: '1450.00',
  total_cost: '1450.00',
  created_at: '2026-08-11T12:00:00Z',
  updated_at: '2026-08-11T14:10:00Z',
  quote_sent: true,
  quote_approved: false,
  ...overrides,
})

const quote = (overrides: Partial<Quote> = {}): Quote => ({
  id: 'quote-2',
  tenant_id: 'tenant-1',
  repair_order_id: 'order-1',
  quote_number: 'Q-000002',
  total_amount: '1450.00',
  notes: null,
  expires_at: null,
  is_approved: false,
  is_declined: false,
  decline_notes: null,
  sent_to_customer: true,
  sent_at: '2026-08-11T14:00:00Z',
  created_at: '2026-08-11T13:55:00Z',
  updated_at: '2026-08-11T14:00:00Z',
  revision: 2,
  authorization_type: 'additional_work',
  previously_authorized_amount: '1000.00',
  delta_amount: '450.00',
  ...overrides,
})

function renderDashboard(repairOrders: RepairOrder[], revisions: Quote[], historyStatus = 200, invoices: Invoice[] = []) {
  apiMocks.get.mockImplementation((url: string) => {
    if (url === '/customers/customer-1') {
      return Promise.resolve({ data: { id: 'customer-1', first_name: 'Casey', last_name: 'Customer' } })
    }
    if (url === '/vehicles') {
      return Promise.resolve({ data: { items: [], has_more: false, skip: 0, limit: 100 } })
    }
    if (url === '/repair-orders') {
      return Promise.resolve({ data: { items: repairOrders, has_more: false, skip: 0, limit: 100 } })
    }
    if (url === '/invoices') return Promise.resolve({ data: invoices })
    if (url.startsWith('/quotes?repair_order_id=')) {
      return Promise.reject({ response: { status: 403 } })
    }
    if (url === '/quotes/repair-order/order-1/history') {
      return historyStatus === 200
        ? Promise.resolve({ data: { revisions, events: [] } })
        : Promise.reject({ response: { status: historyStatus } })
    }
    return Promise.reject(new Error(`Unhandled test request: ${url}`))
  })

  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const view = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PortalDashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...view, queryClient }
}

describe('PortalDashboardPage authorization actions', () => {
  beforeEach(() => {
    apiMocks.get.mockReset()
    useAuthStore.setState({
      user: {
        id: 'customer-user-1',
        email: 'casey@example.test',
        first_name: 'Casey',
        last_name: 'Customer',
        phone: null,
        role: 'customer',
        is_active: true,
        tenant_id: 'tenant-1',
        customer_id: 'customer-1',
      },
      isAuthenticated: true,
    })
  })

  it('keeps historical ETS records out of current debt and payment queues', async () => {
    renderDashboard([], [], 200, [
      { id: 'history-1182', invoice_number: 'ETSINV-1182', source: 'easy_truck_shop_import', status: 'sent', total_amount: '314.02', payment_summary: {state:'unpaid',applied_amount:'0.00',balance_due:'314.02',pending_amount:null,basis:'settlement',note:null} } as Invoice,
      { id: 'current-1687', invoice_number: 'Invoice 1687', source: 'ets_collection_handoff', status: 'sent', total_amount: '268.44', payment_summary: {state:'unpaid',applied_amount:'0.00',balance_due:'268.44',pending_amount:null,basis:'settlement',note:null} } as Invoice,
    ])
    expect(await screen.findByRole('link', { name: 'Pay', exact: true })).toHaveAttribute('href', '/portal/invoices/current-1687')
    expect(screen.getAllByRole('link', { name: 'Pay', exact: true })).toHaveLength(1)
    expect(screen.queryByText('Action required')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Select & pay' })).not.toBeInTheDocument()
    expect(screen.queryByText('0 past due')).not.toBeInTheDocument()
    expect(screen.queryByText(/314.02|582.46|ETSINV-1182/)).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Pay oldest first' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('link').some(link => link.getAttribute('href')?.includes('history-1182'))).toBe(false)
  })

  it('retains an ordinary native unpaid invoice as payable', async () => {
    renderDashboard([], [], 200, [{ id: 'native-unpaid', source: 'native', status: 'sent', total_amount: '100.00', payment_summary: {state:'unpaid',applied_amount:'0.00',balance_due:'100.00',pending_amount:null,basis:'settlement',note:null} } as Invoice])
    expect(await screen.findByRole('link', { name: 'Pay', exact: true })).toHaveAttribute('href', '/portal/invoices/native-unpaid')
  })

  it('shows only the tenant reference for the collection invoice', async () => {
    renderDashboard([], [], 200, [{ id: 'current', invoice_number: 'DBN-COL-INTERNAL-ID', source: 'ets_collection_handoff', status: 'sent', total_amount: '268.44', payment_summary: {state:'unpaid',applied_amount:'0.00',balance_due:'268.44',pending_amount:null,basis:'settlement',note:null}, source_collection: { display_invoice_number: 'TPS-1687' } } as Invoice])
    await screen.findByRole('link', { name: 'Pay', exact: true })
    expect(screen.getAllByText('Invoice TPS-1687').length).toBeGreaterThan(0)
    expect(screen.queryByText(/DBN-COL|INTERNAL-ID/)).not.toBeInTheDocument()
  })

  it('offers selection only for multiple invoices and preserves the selected queue', async () => {
    renderDashboard([], [], 200, [{id:'a',invoice_number:'TPS-1',status:'sent',total_amount:'100.00', payment_summary: {state:'unpaid',applied_amount:'0.00',balance_due:'100.00',pending_amount:null,basis:'settlement',note:null}}, {id:'b',invoice_number:'TPS-2',status:'sent',total_amount:'200.00', payment_summary: {state:'unpaid',applied_amount:'0.00',balance_due:'200.00',pending_amount:null,basis:'settlement',note:null}}] as Invoice[])
    const choose = await screen.findByRole('button', {name:'Select & pay'})
    expect(screen.getAllByRole('link', {name:'Pay',exact:true})).toHaveLength(2)
    expect(screen.queryByText('Action required')).not.toBeInTheDocument()
    fireEvent.click(choose)
    fireEvent.click(screen.getByRole('button',{name:'Select Invoice TPS-1'}))
    expect(screen.getByRole('link',{name:'Pay 1 · $100.00'})).toHaveAttribute('href','/portal/invoices/a')
    fireEvent.click(screen.getByRole('button',{name:'Done'}))
    expect(screen.getAllByRole('link',{name:'Pay',exact:true})).toHaveLength(2)
  })

  it.each([
    ['unpaid','sent','0.00','0.00','100.00'],
    ['partially_paid','partially_paid','40.00','0.00','60.00'],
    ['payment_pending','sent','0.00','20.00','100.00'],
    ['partially_paid_pending','paid','40.00','20.00','60.00'],
    ['paid','sent','100.00','0.00','0.00'],
  ] as const)('uses current %s remaining principal while preserving single-Pay hierarchy', async (state, status, applied, pending, due) => {
    renderDashboard([], [], 200, [{ id:'matrix',invoice_number:'DBN-COL-INTERNAL',source:'ets_collection_handoff',status,total_amount:'100.00',
      source_collection:{display_invoice_number:'TPS-1687',original_bill_to_name:'Original Fleet LLC'},
      payment_summary:{state,applied_amount:applied,balance_due:due,pending_amount:pending,basis:'settlement',note:null},
    } as Invoice])
    if(state === 'paid') {
      await screen.findByText('All paid up')
      expect(screen.queryByRole('link',{name:'Pay',exact:true})).not.toBeInTheDocument()
    } else {
      expect(await screen.findByRole('link',{name:'Pay',exact:true})).toHaveAttribute('href','/portal/invoices/matrix')
      expect(screen.getAllByText(`$${due}`)).toHaveLength(2)
      expect(screen.getAllByRole('link',{name:'Pay',exact:true})).toHaveLength(1)
    }
    expect(screen.queryByText(/DBN-COL|INTERNAL/)).not.toBeInTheDocument()
    expect(screen.queryByRole('link',{name:/Pay invoices|Pay oldest/})).not.toBeInTheDocument()
    expect(screen.queryByRole('button',{name:'Select & pay'})).not.toBeInTheDocument()
    expect(screen.queryByText('Action required')).not.toBeInTheDocument()
  })

  it.each([undefined,null,'NaN','-1.00','1.234'])('keeps missing/invalid balance %s unavailable without a Pay action', async due => {
    renderDashboard([], [], 200, [{id:'unknown',invoice_number:'NS-3',status:'sent',total_amount:'100.00',
      ...(due===undefined?{}:{payment_summary:{state:'unpaid',applied_amount:'0.00',balance_due:due,pending_amount:null,basis:'settlement',note:null}}),
    } as Invoice])
    expect(await screen.findByText(/Some invoice balances need shop verification/)).toBeInTheDocument()
    expect(screen.getByRole('link',{name:'View Invoice NS-3'})).toHaveAttribute('href','/portal/invoices/unknown')
    expect(screen.queryByRole('link',{name:'Pay',exact:true})).not.toBeInTheDocument()
    expect(screen.queryByText('$100.00')).not.toBeInTheDocument()
    expect(screen.queryByText('All paid up')).not.toBeInTheDocument()
  })

  it('sums selected remaining cents and discards stale selected IDs after refetch', async () => {
    const rows = [
      {id:'a',invoice_number:'TPS-1',status:'sent',total_amount:'100.00',payment_summary:{state:'partially_paid',applied_amount:'99.90',balance_due:'0.10',pending_amount:null,basis:'settlement',note:null}},
      {id:'b',invoice_number:'TPS-2',status:'sent',total_amount:'100.00',payment_summary:{state:'partially_paid',applied_amount:'99.80',balance_due:'0.20',pending_amount:null,basis:'settlement',note:null}},
      {id:'unknown',invoice_number:'TPS-3',status:'sent',total_amount:'100.00',payment_summary:{state:'unknown',applied_amount:null,balance_due:null,pending_amount:null,basis:'unknown',note:null}},
    ] as Invoice[]
    const {queryClient}=renderDashboard([],[],200,rows)
    await screen.findByRole('button',{name:'Select & pay'})
    expect(screen.getByText('Known balance due')).toBeInTheDocument()
    expect(screen.getAllByRole('link',{name:'Pay',exact:true})).toHaveLength(2)
    expect(screen.getByText('$0.30')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'Select & pay'}))
    fireEvent.click(screen.getByRole('button',{name:'Select Invoice TPS-1'}))
    fireEvent.click(screen.getByRole('button',{name:'Select Invoice TPS-2'}))
    expect(screen.getByRole('link',{name:'Pay 2 · $0.30'})).toHaveAttribute('href','/portal/invoices/a')
    expect(screen.queryByRole('button',{name:'Select Invoice TPS-3'})).not.toBeInTheDocument()
    apiMocks.get.mockResolvedValueOnce({data:[{...rows[0],payment_summary:{...rows[0].payment_summary,state:'paid',applied_amount:'100.00',balance_due:'0.00'}},rows[1],rows[2]]})
    await act(async()=>{await queryClient.invalidateQueries({queryKey:['customer-dashboard-invoices']})})
    await waitFor(() => expect(screen.queryByRole('link',{name:/Pay 2/})).not.toBeInTheDocument())
    expect(screen.queryByRole('button',{name:'Select & pay'})).not.toBeInTheDocument()
    expect(screen.getByRole('link',{name:'Pay',exact:true})).toHaveAttribute('href','/portal/invoices/b')
    expect(screen.getAllByRole('link',{name:'Pay',exact:true})).toHaveLength(1)
  })

  it('fails closed after a fresh list read fails, then recovers through Retry', async () => {
    const invoice={id:'one',invoice_number:'TPS-1',status:'sent',total_amount:'100.00',payment_summary:{state:'partially_paid',applied_amount:'40.00',balance_due:'60.00',pending_amount:null,basis:'settlement',note:null}} as Invoice
    const {queryClient}=renderDashboard([],[],200,[invoice])
    await screen.findByRole('link',{name:'Pay',exact:true})
    apiMocks.get.mockRejectedValueOnce(new Error('Synthetic read failure'))
    await act(async()=>{await queryClient.invalidateQueries({queryKey:['customer-dashboard-invoices']})})
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to load current invoice balances')
    expect(screen.queryByRole('link',{name:'Pay',exact:true})).not.toBeInTheDocument()
    apiMocks.get.mockResolvedValueOnce({data:[invoice]})
    fireEvent.click(screen.getByRole('button',{name:'Retry invoice balances'}))
    expect(await screen.findByRole('link',{name:'Pay',exact:true})).toBeInTheDocument()
    expect(screen.getAllByText('$60.00')).toHaveLength(2)
  })

  it('uses recorded cash amount in recently paid and paid YTD', async () => {
    renderDashboard([], [], 200, [{ id: 'cash-invoice', status: 'paid', total_amount: '115.00', paid_at: new Date().toISOString(), cash_receipt: { method: 'cash', amount: '101.00' } } as Invoice])
    await screen.findByText('Recently paid')
    expect(screen.getAllByText('$101.00')).toHaveLength(2)
    expect(screen.queryByText('$115.00')).not.toBeInTheDocument()
  })

  it.each([
    ['direct', 'customer-user-direct'],
    ['linked', 'customer-user-linked'],
  ])('shows review for the latest sent authorization for a %s customer', async (_identity, userId) => {
    useAuthStore.setState(state => ({ user: state.user ? { ...state.user, id: userId } : null }))
    renderDashboard([order()], [quote()])

    expect(await screen.findByText('Authorization awaiting review')).toBeInTheDocument()
    expect(screen.getByText('Review authorization')).toBeInTheDocument()
    expect(apiMocks.get).toHaveBeenCalledWith('/quotes/repair-order/order-1/history')
    expect(apiMocks.get).not.toHaveBeenCalledWith('/quotes?repair_order_id=order-1')
  })

  it('does not resurrect a declined authorization after work removal and finalization', async () => {
    renderDashboard(
      [order({ status: 'invoiced', total_cost: '1000.00', updated_at: '2026-08-11T15:00:00Z' })],
      [quote({ is_declined: true, decline_notes: 'Please defer this work.' })],
    )

    expect(await screen.findByText('All paid up')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByText('Authorization awaiting review')).not.toBeInTheDocument()
      expect(screen.queryByText('Review authorization')).not.toBeInTheDocument()
      expect(screen.queryByText('Action required')).not.toBeInTheDocument()
    })
    expect(apiMocks.get).not.toHaveBeenCalledWith('/quotes?repair_order_id=order-1')
  })

  it('uses the canonical latest decision to exclude a declined active revision', async () => {
    renderDashboard([order()], [quote({ is_declined: true })])

    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith('/quotes/repair-order/order-1/history'))
    expect(screen.queryByText('Authorization awaiting review')).not.toBeInTheDocument()
    expect(screen.queryByText('Review authorization')).not.toBeInTheDocument()
  })

  it('uses the latest sent revision and ignores a newer unsent draft', async () => {
    renderDashboard([order()], [
      quote({ id: 'quote-2', revision: 2 }),
      quote({ id: 'quote-3', revision: 3, sent_to_customer: false, sent_at: null, is_declined: true }),
    ])

    expect(await screen.findByText('Authorization awaiting review')).toBeInTheDocument()
    expect(apiMocks.get).not.toHaveBeenCalledWith('/quotes?repair_order_id=order-1')
  })

  it('does not fall back to the forbidden draft route when history is denied', async () => {
    renderDashboard([order()], [], 403)

    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith('/quotes/repair-order/order-1/history'))
    expect(screen.queryByText('Authorization awaiting review')).not.toBeInTheDocument()
    expect(apiMocks.get).not.toHaveBeenCalledWith('/quotes?repair_order_id=order-1')
  })
})
