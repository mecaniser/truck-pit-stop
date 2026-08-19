import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Customer } from '../../types'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
}))
const themeState = vi.hoisted(() => ({ presentationVariant: 'new' as 'legacy' | 'new' }))

vi.mock('../../lib/api', () => ({
  default: {
    get: apiMocks.get,
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('../../contexts/ThemeContext', () => ({
  useTheme: () => ({
    accentColors: { 400: '#f59e0b', 500: '#d97706', 600: '#b45309', primary: '#2563eb' },
    presentationVariant: themeState.presentationVariant,
  }),
}))

vi.mock('../../stores/authStore', () => ({
  useAuthStore: (selector: (state: { user: { role: string } }) => unknown) => selector({ user: { role: 'shop_owner' } }),
}))

import CustomersPage from './CustomersPage'
import STAFF_CSS from '../../index.css?inline'

const customer = {
  id: 'customer-1',
  first_name: 'Nora',
  last_name: 'North',
  company_name: 'Northline Logistics',
  email: 'dispatch@northline.test',
  phone: '(704) 555-0102',
  billing_address_line1: '100 Service Road',
  billing_address_line2: null,
  billing_city: 'Charlotte',
  billing_state: 'NC',
  billing_zip: '28202',
  billing_country: 'US',
  notes: null,
  auto_approval_threshold: null,
  usdot_number: '1234567',
  mc_number: '7654321',
  fleet_enabled: false,
  vehicle_count: 1,
  balance: '125.00',
  created_at: '2026-08-10T12:00:00Z',
  updated_at: '2026-08-12T12:00:00Z',
} as Customer

const secondCustomer = {
  ...customer,
  id: 'customer-2',
  first_name: 'Maya',
  last_name: 'Miles',
  company_name: 'Miles Freight',
  email: 'maya@miles.test',
  phone: '(704) 555-0118',
  usdot_number: null,
  mc_number: null,
  fleet_enabled: true,
  vehicle_count: 3,
  balance: '0.00',
} as Customer

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="customers-location">{location.search}</output>
}

function renderPage(initialEntry = '/dashboard/customers?view=list') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return {
    queryClient,
    ...render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <CustomersPage />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
    ),
  }
}

function installApiFixture(pageCustomers: Customer[] = [customer]) {
  apiMocks.get.mockImplementation((url: string) => {
    if (url === '/customers') {
      return Promise.resolve({ data: { items: pageCustomers, total: pageCustomers.length, has_more: false } })
    }
    const matchedCustomer = [customer, secondCustomer].find((candidate) => url === `/customers/${candidate.id}`)
    if (matchedCustomer) return Promise.resolve({ data: matchedCustomer })
    if (/\/customers\/[^/]+\/(vehicles|contacts)$/.test(url)) return Promise.resolve({ data: [] })
    return Promise.resolve({ data: [] })
  })
}

describe('DB-035C customer workstation', () => {
  afterEach(() => {
    apiMocks.get.mockReset()
    themeState.presentationVariant = 'new'
  })

  it('opens the canonical page-owned workspace and preserves unrelated query state', async () => {
    installApiFixture()
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: 'Open Northline Logistics customer workspace' }))

    await waitFor(() => expect(screen.getByTestId('customers-location')).toHaveTextContent('?view=list&selected=customer-1'))
    expect(screen.getByRole('region', { name: 'Northline Logistics' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Close' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to Customers' })).toBeInTheDocument()
    expect(document.querySelector('.db-customers-workspace--detail-open')).toBeInTheDocument()
  })

  it('restores a deep-linked customer using the existing customer endpoint', async () => {
    installApiFixture([])
    renderPage('/dashboard/customers?filter=active&selected=customer-1')

    expect(await screen.findByRole('region', { name: 'Northline Logistics' })).toBeInTheDocument()
    expect(apiMocks.get).toHaveBeenCalledWith('/customers/customer-1')
    expect(screen.getByTestId('customers-location')).toHaveTextContent('?filter=active&selected=customer-1')
  })

  it('moves focus into the workspace for keyboard activation and restores it on Back', async () => {
    installApiFixture()
    renderPage()

    const openCustomer = await screen.findByRole('button', { name: 'Open Northline Logistics customer workspace' })
    openCustomer.focus()
    fireEvent.keyDown(openCustomer, { key: 'Enter' })
    fireEvent.click(openCustomer)

    const heading = await screen.findByRole('heading', { name: 'Northline Logistics' })
    await waitFor(() => expect(heading).toHaveFocus())
    fireEvent.click(screen.getByRole('button', { name: 'Back to Customers' }))

    await waitFor(() => expect(screen.getByTestId('customers-location')).toHaveTextContent('?view=list'))
    await waitFor(() => expect(openCustomer).toHaveFocus())
  })

  it('retains the legacy Sidekick and leaves the physical URL unchanged', async () => {
    themeState.presentationVariant = 'legacy'
    installApiFixture()
    renderPage()

    fireEvent.click(await screen.findByRole('row', { name: /Northline Logistics/ }))

    expect(await screen.findByRole('dialog', { name: /Northline Logistics/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument()
    expect(screen.getByTestId('customers-location')).toHaveTextContent('?view=list')
    expect(document.querySelector('.db-customer-detail-workspace')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'View' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Details' })).not.toBeInTheDocument()
  })

  it('inspects a different customer without replacing the selected workspace or URL', async () => {
    installApiFixture([customer, secondCustomer])
    renderPage('/dashboard/customers?view=list&selected=customer-1')

    expect(await screen.findByRole('region', { name: 'Northline Logistics' })).toBeInTheDocument()
    const details = await screen.findAllByRole('button', { name: 'Details' })
    const requestsBeforeInspection = apiMocks.get.mock.calls.length
    fireEvent.click(details[1])

    expect(await screen.findByRole('region', { name: 'Miles Freight details' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Northline Logistics' })).toBeInTheDocument()
    expect(screen.getByTestId('customers-location')).toHaveTextContent('?view=list&selected=customer-1')
    expect(apiMocks.get).toHaveBeenCalledTimes(requestsBeforeInspection)
    expect(details[1]).toHaveAttribute('aria-expanded', 'true')
  })

  it('keeps only one flat Details disclosure open and restores focus when it closes', async () => {
    installApiFixture([customer, secondCustomer])
    renderPage()

    const details = await screen.findAllByRole('button', { name: 'Details' })
    const firstDetails = details[0]!
    firstDetails.focus()
    fireEvent.click(firstDetails)
    const firstBrief = await screen.findByRole('region', { name: 'Northline Logistics details' })
    expect(firstBrief).toBeInTheDocument()
    expect(firstDetails).toHaveFocus()
    const progressiveAction = within(firstBrief).getByRole('button', { name: 'Open customer' })
    const lastFact = firstBrief.querySelector('.db-customer-inspection__facts')
    expect(lastFact).not.toBeNull()
    expect(lastFact!.compareDocumentPosition(progressiveAction) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

    fireEvent.click(details[1])
    expect(screen.queryByRole('region', { name: 'Northline Logistics details' })).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Miles Freight details' })).toBeInTheDocument()
    expect(details[0]).toHaveAttribute('aria-expanded', 'false')

    fireEvent.click(details[1])
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Miles Freight details' })).not.toBeInTheDocument())
    await waitFor(() => expect(details[1]).toHaveFocus())
  })

  it('reveals one progressive Open customer action only after information-only Details', async () => {
    installApiFixture([customer, secondCustomer])
    renderPage('/dashboard/customers?view=list&selected=customer-1')

    const secondRecord = await screen.findByRole('listitem', { name: /Miles Freight/ })
    expect(within(secondRecord).queryByRole('button', { name: 'Open customer' })).not.toBeInTheDocument()

    const details = await screen.findAllByRole('button', { name: 'Details' })
    fireEvent.click(details[1])
    const inspectedBrief = await screen.findByRole('region', { name: 'Miles Freight details' })
    expect(within(inspectedBrief).getAllByRole('button', { name: 'Open customer' })).toHaveLength(1)
    expect(within(secondRecord).getAllByRole('button', { name: 'Open customer' })).toHaveLength(1)
    expect(screen.getByTestId('customers-location')).toHaveTextContent('?view=list&selected=customer-1')

    fireEvent.click(within(inspectedBrief).getByRole('button', { name: 'Open customer' }))
    await waitFor(() => expect(screen.getByTestId('customers-location')).toHaveTextContent('?view=list&selected=customer-2'))
    expect(await screen.findByRole('region', { name: 'Miles Freight' })).toBeInTheDocument()
  })

  it('opens the canonical workspace from the semantic company-name action without nesting controls', async () => {
    const user = userEvent.setup()
    installApiFixture([customer, secondCustomer])
    renderPage('/dashboard/customers?view=list')

    const record = await screen.findByRole('listitem', { name: /Northline Logistics/ })
    const companyAction = within(record).getByRole('button', {
      name: 'Open Northline Logistics customer workspace',
    })

    expect(companyAction).toHaveClass('db-customer-navigator__name-action')
    expect(companyAction.tagName).toBe('BUTTON')
    expect(companyAction.querySelector('button, a')).toBeNull()
    expect(record.querySelector('button button, button a, a button, a a')).toBeNull()

    companyAction.focus()
    expect(companyAction).toHaveFocus()
    await user.keyboard('{Enter}')

    await waitFor(() => expect(screen.getByTestId('customers-location')).toHaveTextContent('?view=list&selected=customer-1'))
    expect(await screen.findByRole('region', { name: 'Northline Logistics' })).toBeInTheDocument()
  })

  it('keeps summary activation, Details inspection, and the progressive Open action independent', async () => {
    const user = userEvent.setup()
    installApiFixture([customer, secondCustomer])
    renderPage('/dashboard/customers?view=list&selected=customer-1')

    const secondRecord = await screen.findByRole('listitem', { name: /Miles Freight/ })
    const summary = secondRecord.querySelector<HTMLElement>('.db-customer-navigator__summary')!
    const details = within(secondRecord).getByRole('button', { name: 'Details' })
    const name = within(secondRecord).getByRole('button', { name: 'Open Miles Freight customer workspace' })

    fireEvent.click(details)
    const brief = await screen.findByRole('region', { name: 'Miles Freight details' })
    expect(screen.getByTestId('customers-location')).toHaveTextContent('?view=list&selected=customer-1')
    fireEvent.click(within(brief).getByText('Available in the customer workspace'))
    expect(screen.getByTestId('customers-location')).toHaveTextContent('?view=list&selected=customer-1')

    fireEvent.click(summary)
    await waitFor(() => expect(screen.getByTestId('customers-location')).toHaveTextContent('?view=list&selected=customer-2'))

    fireEvent.click(screen.getByRole('button', { name: 'Back to Customers' }))
    await waitFor(() => expect(screen.getByTestId('customers-location')).toHaveTextContent('?view=list'))
    fireEvent.click(name)
    await waitFor(() => expect(screen.getByTestId('customers-location')).toHaveTextContent('?view=list&selected=customer-2'))

    fireEvent.click(screen.getByRole('button', { name: 'Back to Customers' }))
    await waitFor(() => expect(screen.getByTestId('customers-location')).toHaveTextContent('?view=list'))
    summary.focus()
    await user.keyboard('{Enter}')
    await waitFor(() => expect(screen.getByTestId('customers-location')).toHaveTextContent('?view=list&selected=customer-2'))
  })

  it('keeps collapsed records to name, phone, and explicit actions, then reveals the flat brief without selection', async () => {
    installApiFixture([customer, secondCustomer])
    renderPage()

    const record = await screen.findByRole('listitem', { name: /Northline Logistics/ })
    expect(within(record).getByText('Northline Logistics')).toBeInTheDocument()
    expect(within(record).getByText('(704) 555-0102')).toBeInTheDocument()
    expect(within(record).getByRole('button', { name: 'Details' })).toHaveAttribute('aria-expanded', 'false')
    expect(within(record).queryByRole('button', { name: 'Open customer' })).not.toBeInTheDocument()
    expect(within(record).queryByText('dispatch@northline.test')).not.toBeInTheDocument()

    const locationBefore = screen.getByTestId('customers-location').textContent
    const requestsBefore = apiMocks.get.mock.calls.length
    fireEvent.click(within(record).getByRole('button', { name: 'Details' }))

    const brief = await screen.findByRole('region', { name: 'Northline Logistics details' })
    expect(within(brief).getByText('dispatch@northline.test')).toBeInTheDocument()
    expect(record).toContainElement(brief)
    expect(record.firstElementChild?.nextElementSibling).toBe(brief)
    expect(screen.getByTestId('customers-location')).toHaveTextContent(locationBefore || '')
    expect(apiMocks.get).toHaveBeenCalledTimes(requestsBefore)
  })

  it('uses the canonical focus-safe staff search field with a visible light-theme border', async () => {
    installApiFixture([customer])
    renderPage()

    const search = await screen.findByRole('searchbox', { name: 'Search customers' })
    const focusSafeRegion = search.closest('.db-staff-search-field-inset')

    expect(focusSafeRegion).not.toBeNull()
    expect(search.closest('.db-staff-search-field')).not.toBeNull()
    expect(focusSafeRegion).toContainElement(search)
    expect(STAFF_CSS).toContain('border: 1px solid var(--workspace-muted) !important')
    expect(STAFF_CSS).toContain('.db-presentation-new .db-staff-search-field-inset { min-width: 0; padding: 4px; }')
  })

  it.each([1440, 960, 390, 320])('keeps navigator and page widths bounded at %ipx', async (width) => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: width })
    installApiFixture([customer, secondCustomer])
    renderPage()

    const navigator = await screen.findByRole('list', { name: 'Customers' })
    const record = within(navigator).getByRole('listitem', { name: /Northline Logistics/ })
    const details = within(record).getByRole('button', { name: 'Details' })
    expect(within(record).queryByRole('button', { name: 'Open customer' })).not.toBeInTheDocument()

    fireEvent.click(details)

    expect(await screen.findByRole('region', { name: 'Northline Logistics details' })).toBeInTheDocument()
    expect(within(record).getAllByRole('button', { name: 'Open customer' })).toHaveLength(1)
    expect(navigator.scrollWidth).toBe(navigator.clientWidth)
    expect(document.documentElement.scrollWidth).toBe(document.documentElement.clientWidth)
    expect(navigator).toHaveClass('db-customer-navigator')
  })
})
