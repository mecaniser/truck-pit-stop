import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider, onlineManager } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }))
const user = { id: 'u1', tenant_id: 't1', role: 'garage_owner', is_active: true }
vi.mock('@/lib/api', () => ({ default: mocks }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (selector?: (s: {user: typeof user}) => unknown) => selector ? selector({user}) : {user} }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ accentColors: { 400: '#22d3ee', 500: '#06b6d4', 600: '#0891b2' } }) }))
vi.mock('@/hooks/useTenantBranding', () => ({ default: () => ({ data: { name: 'Test Shop', logo_url: null } }) }))
vi.mock('@/features/inventory/PartsInventoryWorkspace', () => ({ PartsInventoryGate: ({ legacy }: { legacy: ReactNode }) => legacy }))
import SuppliersPage from '@/features/suppliers/SuppliersPage'
import MechanicsPage from '@/features/mechanics/MechanicsPage'
import InventoryPage from '@/features/inventory/InventoryPage'
function mount(element: ReactNode) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>{element}</MemoryRouter></QueryClientProvider>) }
beforeEach(() => { localStorage.clear(); mocks.get.mockReset(); mocks.post.mockReset(); onlineManager.setOnline(true) })
afterEach(() => { cleanup(); onlineManager.setOnline(true) })
it.each([
 ['suppliers', <SuppliersPage />, /No suppliers match/],
 ['technicians', <MechanicsPage />, /No technicians yet/],
 ['inventory', <InventoryPage />, /No inventory found/],
] as const)('%s failed reads do not show false emptiness and can retry', async (subject, page, emptyText) => {
 mocks.get.mockRejectedValue(new Error('Network failed'))
 mount(page)
 const retry = await screen.findByRole('button', { name: `Retry ${subject}` })
 expect(screen.queryByText(emptyText)).not.toBeInTheDocument()
 mocks.get.mockImplementation((url: string) => Promise.resolve({ data: url === '/mechanics' || url.includes('pto') ? [] : { items: [], has_more: false } }))
 fireEvent.click(retry)
 await waitFor(() => expect(screen.queryByRole('button', {name: `Retry ${subject}`})).not.toBeInTheDocument())
 expect(mocks.post).not.toHaveBeenCalled()
})
it.each([
 ['suppliers', <SuppliersPage />, /No suppliers match/],
 ['technicians', <MechanicsPage />, /No technicians yet/],
 ['inventory', <InventoryPage />, /No inventory found/],
] as const)('%s initially paused offline reads never show false emptiness', async (_, page, emptyText) => {
 onlineManager.setOnline(false)
 mount(page)
 expect(screen.queryByText(emptyText)).not.toBeInTheDocument()
 expect(mocks.get).not.toHaveBeenCalled()
 expect(screen.getByText(/Loading/)).toBeInTheDocument()
})
it.each(['list', 'cards'])('technician work failure has a retry instead of zero work in %s view', async view => {
 localStorage.setItem('tps_view_prefs', JSON.stringify({ mechanics: view }))
 let failed = true
 mocks.get.mockImplementation((url: string) => {
   if (url === '/mechanics') return Promise.resolve({ data: [{ id: 'm1', first_name: 'Test', last_name: 'Technician', email: 'test@example.com', is_active: true, assigned_count: 0 }] })
   if (url === '/mechanics/m1/work' && failed) return Promise.reject(new Error('Network failed'))
   return Promise.resolve({ data: [] })
 })
 mount(<MechanicsPage />)
 fireEvent.click(await screen.findByRole('button', { name: 'View work' }))
 const retry = await screen.findByRole('button', { name: 'Retry technician work' })
 expect(screen.queryByText('No work found for this technician.')).not.toBeInTheDocument()
 failed = false
 fireEvent.click(retry)
 expect(await screen.findByText('No work found for this technician.')).toBeInTheDocument()
 expect(mocks.post).not.toHaveBeenCalled()
})
