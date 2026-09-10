import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import QuickBooksCompanyIdentity from '../features/dashboard/QuickBooksCompanyIdentity'

const mocks = vi.hoisted(() => ({ get: vi.fn(), user: { id: 'user-a', tenant_id: 'tenant-a' } }))
vi.mock('../lib/api', () => ({ default: { get: mocks.get } }))
vi.mock('../stores/authStore', () => ({ useAuthStore: () => ({ user: mocks.user }) }))
const connection = { is_connected: true, realm_id: 'realm-a', connected_at: '2026-09-01' }
const identity = { status: 'available', environment: 'production', realm_id: 'realm-a', company: {
  name: 'Truck Pit Stop', legal_name: 'Truck Pit Stop LLC', address_lines: ['123 Service Rd', 'Charlotte, NC'], email: 'shop@example.com', phone: '555-123-4567',
} }

function setup(props = { open: true, connection }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = (next = props) => <QueryClientProvider client={client}><QuickBooksCompanyIdentity {...next} /></QueryClientProvider>
  return { ...render(view()), view }
}

describe('QuickBooks company identity', () => {
  beforeEach(() => {
    mocks.get.mockReset()
    mocks.user = { id: 'user-a', tenant_id: 'tenant-a' }
  })
  it('shows provider company details with a visible copyable company ID', async () => {
    mocks.get.mockResolvedValue({ data: identity })
    setup()
    expect(await screen.findByRole('heading', { name: 'Truck Pit Stop' })).toBeInTheDocument()
    expect(screen.getByText('Legal name: Truck Pit Stop LLC')).toBeInTheDocument()
    expect(screen.getByText('123 Service Rd')).toBeInTheDocument()
    expect(screen.getByText('Production')).toBeInTheDocument()
    expect(screen.getByText('shop@example.com')).toBeInTheDocument()
    expect(screen.getByText('realm-a')).toBeVisible()
    expect(screen.queryByText('Connection details')).not.toBeInTheDocument()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    fireEvent.click(screen.getByRole('button', { name: 'Copy QuickBooks company ID' }))
    expect(await screen.findByText('Company ID copied')).toBeInTheDocument()
    expect(writeText).toHaveBeenCalledWith('realm-a')
    expect(mocks.get).toHaveBeenCalledWith('/quickbooks/company-identity')
  })
  it('offers manual copying when clipboard access fails', async () => {
    mocks.get.mockResolvedValue({ data: identity })
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) } })
    setup()
    fireEvent.click(await screen.findByRole('button', { name: 'Copy QuickBooks company ID' }))
    expect(await screen.findByText(/Select the company ID to copy it manually/)).toBeInTheDocument()
    expect(screen.getByText('realm-a')).toBeVisible()
  })
  it.each([false, true])('does not request details when closed or disconnected (%s)', async (open) => {
    setup({ open, connection: { ...connection, is_connected: !open } })
    expect(mocks.get).not.toHaveBeenCalled()
  })
  it('keeps loading and lookup failures separate from connection health', async () => {
    mocks.get.mockRejectedValue(new Error('provider unavailable'))
    setup()
    expect(screen.getByRole('status')).toHaveTextContent('Loading connected company')
    expect(await screen.findByText(/Your QuickBooks connection has not been changed/)).toBeInTheDocument()
    expect(mocks.get).toHaveBeenCalledTimes(1)
  })
  it('does not substitute shop identity for missing provider fields', async () => {
    mocks.get.mockResolvedValue({ data: { ...identity, environment: 'unknown', company: { name: null, legal_name: null, address_lines: [], email: null, phone: null } } })
    setup()
    expect(await screen.findByRole('heading', { name: 'Connected QuickBooks company' })).toBeInTheDocument()
    expect(screen.queryByText('Production')).not.toBeInTheDocument()
    expect(screen.queryByText('Truck Pit Stop')).not.toBeInTheDocument()
  })
  it('rejects identity for a different connected realm', async () => {
    mocks.get.mockResolvedValue({ data: { ...identity, realm_id: 'wrong-realm' } })
    setup()
    expect(await screen.findByText(/temporarily unavailable/)).toBeInTheDocument()
    expect(screen.queryByRole('heading')).not.toBeInTheDocument()
  })
  it('does not carry cached company details into another tenant', async () => {
    mocks.get.mockResolvedValueOnce({ data: identity }).mockImplementationOnce(() => new Promise(() => {}))
    const { rerender, view } = setup()
    await screen.findByRole('heading', { name: 'Truck Pit Stop' })
    mocks.user = { id: 'user-b', tenant_id: 'tenant-b' }
    rerender(view())
    await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2))
    expect(screen.queryByRole('heading', { name: 'Truck Pit Stop' })).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Loading')
  })
})
