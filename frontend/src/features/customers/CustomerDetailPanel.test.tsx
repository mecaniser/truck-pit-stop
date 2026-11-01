import { useState } from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import CustomerDetailPanel, { type CustomerDetailPanelProps } from './CustomerDetailPanel'
import CustomerDetailFooter from './CustomerDetailFooter'
import { useCustomerVehicleGroups } from './useCustomerVehicleGroups'
import type { Customer, Vehicle } from '@/types'

const auth = vi.hoisted(() => ({ role: 'garage_owner', payments: false }))
vi.mock('./CustomerAccount', () => ({ default: ({ customerId }: { customerId: string }) => <div data-testid="account-workspace">Account for {customerId}</div> }))
vi.mock('@/stores/authStore', () => ({
  useAuthStore: (select: (s: unknown) => unknown) => select({ user: { role: auth.role, permissions: { payments: auth.payments }, tenant_id: 'tenant-a', id: 'owner-a' } }),
  getAuthenticatedSessionIdentity: () => 'test-session',
}))
const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
const customer = { id: 'customer-a', company_name: 'Northline', first_name: 'Nora', last_name: 'North', email: 'dispatch@example.invalid', phone: '5550100001', balance: '145.00', billing_address_line1: '1 Fleet Road', billing_address_line2: 'Suite 2', billing_city: 'Raleigh', billing_state: 'NC', billing_zip: '27601', created_at: '2026-10-12T12:00:00Z' } as Customer
const truck = { equipment_type: 'tractor', id: 'truck-a', customer_id: customer.id, unit_number: 'C-001', year: 2021, make: 'Freightliner', model: 'Cascadia', vin: 'P0000000000000001', license_plate: 'PC001', balance: '145.00' } as Vehicle
const openTruck = vi.fn()
function Harness({ record = customer, ...overrides }: Partial<CustomerDetailPanelProps> & { record?: Customer }) {
  const [tab, setTab] = useState<'overview' | 'history'>('overview')
  const [expanded, setExpanded] = useState<string | null>(null)
  const groups = useCustomerVehicleGroups({ selectedCustomer: record, customerVehicles: overrides.customerVehicles ?? [truck], vehicleRelationshipSearch: '', vehicleRelationshipFilter: 'all' })
  return <CustomerDetailPanel selectedCustomer={record} detailTab={tab} setDetailTab={setTab} expandedHistoryId={expanded} setExpandedHistoryId={setExpanded}
    HistoryRoDetail={() => <p>Saved repair details</p>} customerVehicles={[truck]} customerContacts={[]}
    customerHistory={{ stats: { total_orders: 1, completed_orders: 1, lifetime_spend: '145', lifetime_savings: '0' }, items: [{ id: 'ro-a', order_number: 'RO-101', status: 'completed', total_cost: '145', savings: '0', vehicle_year: 2021, vehicle_make: 'Freightliner', vehicle_model: 'Cascadia', vehicle_unit_number: 'C-001', created_at: null, work_completed_at: null }] }}
    {...groups} vehiclesViewMode="list" setVehiclesViewMode={vi.fn()} vehicleRelationshipSearch="" setVehicleRelationshipSearch={vi.fn()} vehicleRelationshipFilter="all" setVehicleRelationshipFilter={vi.fn()}
    setSelectedVehicleInPanel={openTruck} openAddContactModal={vi.fn()} openEditContactModal={vi.fn()} handleDeleteContactClick={vi.fn()} openAddVehicleModal={vi.fn()} openEditVehicleModal={vi.fn()} handleDeleteVehicleClick={vi.fn()} {...overrides} />
}
function setup(props: Partial<CustomerDetailPanelProps> = {}) {
  api.get.mockResolvedValue({ data: { tax_exempt: false, support_reference: null, version: 1, updated_at: null } })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><Harness {...props} /></QueryClientProvider>)
}
describe('compact customer record', () => {
  it('shows account information immediately alongside contact and balance', async () => {
    setup()
    expect(screen.getByRole('link', { name: 'dispatch@example.invalid' })).toBeVisible()
    expect(screen.getByText('$145.00')).toBeVisible()
    const details = screen.getByRole('region', { name: 'Account details' })
    expect(within(details).getByText('Suite 2')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Business settings' })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Account details' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Summary' })).not.toBeInTheDocument()
  })
  it('keeps an unsaved tax draft for the same customer without writing it', async () => {
    setup()
    const toggle = screen.getByRole('button', { name: 'Business settings' })
    fireEvent.click(toggle)
    const details = screen.getByRole('region', { name: 'Business settings' })
    fireEvent.click(await within(details).findByRole('checkbox'))
    fireEvent.change(within(details).getByRole('textbox'), { target: { value: 'Certificate draft' } })
    fireEvent.click(toggle)
    expect(details).not.toBeVisible()
    fireEvent.click(toggle)
    expect(within(details).getByRole('textbox')).toHaveValue('Certificate draft')
    expect(api.put).not.toHaveBeenCalled()
  })
  it('puts equipment relationships before named contacts and supports keyboard opening', async () => {
    setup()
    const trucks = screen.getByRole('heading', { name: /Equipment relationships/ })
    const contacts = screen.getByRole('heading', { name: /Contacts/ })
    expect(trucks.compareDocumentPosition(contacts) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByText('Tractor / Truck')).toBeVisible()
    const open = screen.getByRole('button', { name: /Open .*C-001/ })
    open.focus()
    await userEvent.keyboard('{Enter}')
    expect(openTruck).toHaveBeenCalledWith(truck)
  })
  it('does not carry an unsaved tax draft into a different customer', async () => {
    api.get.mockResolvedValue({ data: { tax_exempt: false, support_reference: null, version: 1, updated_at: null } })
    const client = new QueryClient()
    const view = render(<QueryClientProvider client={client}><Harness /></QueryClientProvider>)
    fireEvent.click(screen.getByRole('button', { name: 'Business settings' }))
    fireEvent.click(await screen.findByRole('checkbox'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Certificate draft' } })
    view.rerender(<QueryClientProvider client={client}><Harness record={{ ...customer, id: 'customer-b' }} /></QueryClientProvider>)
    expect(screen.getByRole('button', { name: 'Business settings' })).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(screen.getByRole('button', { name: 'Business settings' }))
    expect(await screen.findByRole('checkbox')).not.toBeChecked()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(api.put).not.toHaveBeenCalled()
  })
  it.each([['-50', 'Credit', '$50.00'], [undefined, 'Balance due', '—']])('keeps %s balance meaning', (balance, label, amount) => {
    setup({ selectedCustomer: { ...customer, balance } as Customer })
    const balanceRegion = screen.getByLabelText('Customer balance due')
    expect(balanceRegion).toHaveTextContent(label!)
    expect(balanceRegion).toHaveTextContent(amount!)
  })
  it.each(['list', 'grid'] as const)('separates historical ETS amounts from paid cash balances in %s view', (vehiclesViewMode) => {
    setup({ vehiclesViewMode, selectedCustomer: { ...customer, balance: '0.00', legacy_ets_balance: '2058.12' },
      customerVehicles: [{ ...truck, balance: '0.00', legacy_ets_balance: '968.91' }] })
    expect(screen.getByLabelText('Customer balance due')).toHaveTextContent('Balance due · DieselBridge$0.00')
    expect(screen.getByText('ETS history $2,058.12 · unverified')).toBeVisible()
    expect(screen.getByText('ETS history $968.91 · unverified')).toBeVisible()
    expect(screen.getAllByText('$0.00')).toHaveLength(2)
    expect(screen.queryByText(/^Due /)).not.toBeInTheDocument()
  })
  it.each(['list', 'grid'] as const)('preserves genuine debt separately from ETS history in %s view', (vehiclesViewMode) => {
    setup({ vehiclesViewMode, customerVehicles: [{ ...truck, legacy_ets_balance: '968.91' }] })
    expect(screen.getByText('Due $145.00')).toBeVisible()
    expect(screen.getByText('ETS history $968.91 · unverified')).toBeVisible()
  })
  it.each(['list', 'grid'] as const)('keeps unknown equipment balance unknown in %s view', (vehiclesViewMode) => {
    setup({ vehiclesViewMode, customerVehicles: [{ ...truck, balance: undefined, legacy_ets_balance: '968.91' }] })
    expect(within(screen.getByRole('button', { name: /Open .*C-001/ })).getByText('—')).toBeVisible()
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
  })
  it('shows history load failure with retry instead of fabricated empty totals', () => {
    const retry = vi.fn()
    setup({ detailTab: 'history', historyError: true, onRetryHistory: retry, customerHistory: undefined })
    fireEvent.click(screen.getByRole('button', { name: 'History', exact: true }))
    expect(screen.getByRole('alert')).toHaveTextContent('Could not load customer history')
    expect(screen.queryByText('Lifetime spend')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry customer history' }))
    expect(retry).toHaveBeenCalledOnce()
  })
  it('keeps history keyboard expandable without repeating activity tiles', async () => {
    setup()
    expect(screen.queryByRole('heading', { name: 'Activity' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'History' }))
    const open = screen.getByRole('button', { name: /RO-101/ })
    open.focus()
    await userEvent.keyboard('{Enter}')
    expect(screen.getByText('Saved repair details')).toBeVisible()
    expect(open).toHaveAttribute('aria-expanded', 'true')
  })
  it('retains contact and truck commands', () => {
    const addContact = vi.fn(), addTruck = vi.fn(), editContact = vi.fn(), deleteContact = vi.fn()
    setup({ openAddContactModal: addContact, openAddVehicleModal: addTruck, openEditContactModal: editContact, handleDeleteContactClick: deleteContact, customerContacts: [{ id: 'contact-a', first_name: 'Dana', last_name: 'Dispatch', email: 'dana@example.invalid', phone: '5550100002', is_primary: true }] as CustomerDetailPanelProps['customerContacts'] })
    fireEvent.click(screen.getByRole('button', { name: 'Add Contact' }))
    fireEvent.click(screen.getByRole('button', { name: 'Add / Link' }))
    fireEvent.click(screen.getByRole('button', { name: 'Edit Dana Dispatch' }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete Dana Dispatch' }))
    expect([addContact, addTruck, editContact, deleteContact].every(fn => fn.mock.calls.length === 1)).toBe(true)
  })
  it('opens card-view trucks from the keyboard', async () => {
    setup({ vehiclesViewMode: 'grid' })
    expect(screen.getByText('Tractor / Truck')).toBeVisible()
    const open = screen.getByRole('button', { name: /Open .*C-001/ })
    open.focus()
    await userEvent.keyboard('{Enter}')
    expect(openTruck).toHaveBeenCalledWith(truck)
  })
  it('does not show an empty truck state while trucks are loading', () => {
    setup({ isLoadingVehicles: true, customerVehicles: undefined })
    expect(screen.queryByText('No vehicles on file')).not.toBeInTheDocument()
    expect(screen.getByText('Loading trucks…')).toBeVisible()
  })
  it('retains the existing customer action handlers', () => {
    const remove = vi.fn(), merge = vi.fn(), edit = vi.fn()
    render(<CustomerDetailFooter selectedCustomer={customer} handleDeleteClick={remove} onMerge={merge} handleEditFromDetail={edit} />)
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    fireEvent.click(screen.getByRole('button', { name: 'Merge' }))
    fireEvent.click(screen.getByRole('button', { name: 'Edit Customer' }))
    expect(remove).toHaveBeenCalledWith(customer)
    expect(merge).toHaveBeenCalledOnce()
    expect(edit).toHaveBeenCalledOnce()
  })
})

it('shows failed trucks and contacts without false emptiness or stale counts', () => {
  const trucks = vi.fn(), contacts = vi.fn()
  setup({ vehiclesError: true, contactsError: true, onRetryVehicles: trucks, onRetryContacts: contacts })
  expect(screen.getAllByRole('alert')).toHaveLength(2)
  expect(screen.getByRole('heading', { name: /Equipment relationships/ })).toHaveTextContent('—')
  expect(screen.queryByText('No vehicles on file')).not.toBeInTheDocument()
  expect(screen.queryByText('Using company contact details above.')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Open .*C-001/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Add First Vehicle' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Retry trucks' }))
  fireEvent.click(screen.getByRole('button', { name: 'Retry contacts' }))
  expect(trucks).toHaveBeenCalledOnce()
  expect(contacts).toHaveBeenCalledOnce()
})
it('keeps failed reads visible and disables repeat retries while fetching', () => {
  const retry = vi.fn()
  setup({ vehiclesError: true, isFetchingVehicles: true, onRetryVehicles: retry })
  expect(screen.getByRole('alert')).toHaveAttribute('aria-busy', 'true')
  const button = screen.getByRole('button', { name: 'Retrying…' })
  expect(button).toBeDisabled()
  fireEvent.click(button)
  expect(retry).not.toHaveBeenCalled()
})
it('does not claim absent contacts during the initial request', () => {
  setup({ customerContacts: undefined, isLoadingContacts: true })
  expect(screen.getByText('Loading contacts…')).toBeVisible()
  expect(screen.queryByText('Using company contact details above.')).not.toBeInTheDocument()
})
it('preserves truthful successful empty states', () => {
  setup({ customerVehicles: [], customerContacts: [], vehicleCount: 0 })
  expect(screen.getByText('No vehicles on file')).toBeVisible()
  expect(screen.getByText('Using company contact details above.')).toBeVisible()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})


describe('DB-151 Account destination permissions', () => {
  it('opens the existing Account view for the exact requested customer', () => {
    setup({ requestedView: 'account' })
    expect(screen.getByTestId('account-workspace')).toHaveTextContent('Account for customer-a')
    expect(screen.getByRole('button', { name: 'Account', exact: true })).toHaveAttribute('aria-pressed', 'true')
  })
  it.each(['garage_admin', 'receptionist'])('does not open Account for %s without payments permission', (role) => {
    auth.role = role
    try {
      setup({ requestedView: 'account' })
      expect(screen.queryByTestId('account-workspace')).not.toBeInTheDocument()
      expect(screen.getByRole('alert')).toHaveTextContent('not available with your permissions')
    } finally { auth.role = 'garage_owner' }
  })
  it('reports tab changes to preserve the route during refresh and browser back', async () => {
    const onViewChange = vi.fn()
    setup({ requestedView: 'account', onViewChange })
    await userEvent.click(screen.getByRole('button', { name: 'History', exact: true }))
    expect(onViewChange).toHaveBeenCalledWith('history')
  })
})
