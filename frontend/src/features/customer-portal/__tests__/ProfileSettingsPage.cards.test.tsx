import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import ProfileSettingsPage from '../ProfileSettingsPage'
const m = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: m.get } }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: () => ({ user: {id:'u1',tenant_id:'t1',customer_id:'c1'}, setUser: vi.fn() }) }))
const customer = { first_name:'Test',last_name:'Driver',email:'driver@example.com',updated_at:'2026-11-02T12:00:00Z',created_at:'2026-01-02T12:00:00Z' }
const mount = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry:false } } })
  render(<MemoryRouter><QueryClientProvider client={client}><ProfileSettingsPage /></QueryClientProvider></MemoryRouter>)
  return client
}
beforeEach(() => vi.resetAllMocks())
it('contact summary reports failure rather than no card and shares scoped cache', async () => {
  m.get.mockImplementation(async (path: string) => {
    if (path.startsWith('/customers/')) return { data:customer }
    throw new Error('offline')
  })
  const client = mount()
  expect(await screen.findByText('Saved cards unavailable. Open Payments to retry.')).toBeInTheDocument()
  expect(screen.queryByText('No card on file')).not.toBeInTheDocument()
  expect(client.getQueryState(['payment-methods',JSON.stringify(['u1','t1','c1'])])?.status).toBe('error')
})
it('contact summary reports pending cards as loading', async () => {
  m.get.mockImplementation((path: string) => path.startsWith('/customers/') ? Promise.resolve({data:customer}) : new Promise(() => {}))
  mount()
  expect(await screen.findByText('Loading saved cards…')).toBeInTheDocument()
  expect(screen.queryByText('No card on file')).not.toBeInTheDocument()
})
it('contact summary shows no card only for a successful empty list', async () => {
  m.get.mockImplementation(async (path: string) => ({data:path.startsWith('/customers/') ? customer : []}))
  mount()
  expect(await screen.findByText('No card on file')).toBeInTheDocument()
})
