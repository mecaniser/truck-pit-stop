import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { PullMotiveReading } from '../TruckTelemetry'
import { useAuthStore } from '@/stores/authStore'
import type { BoardTruck } from '../types'
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: mocks }))
const truck = { id: 'truck', board_membership_customer_id: 'selected', fleet_customer_id: 'other' } as BoardTruck
function show(value = truck) { const client = new QueryClient(); const invalidate = vi.spyOn(client, 'invalidateQueries'); render(<QueryClientProvider client={client}><PullMotiveReading truck={value} /></QueryClientProvider>); return invalidate }
beforeEach(() => { vi.resetAllMocks(); useAuthStore.setState({ user: { id: 'staff', role: 'garage_owner' } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']> }) })
it('does not pretend a manual session is an OAuth connection', async () => {
  mocks.get.mockResolvedValue({ data: { configured: false, status: 'not_configured', company: null } }); show()
  fireEvent.click(screen.getByRole('button')); expect(await screen.findByRole('status')).toHaveTextContent('Motive connection required')
  expect(mocks.post).not.toHaveBeenCalled()
})
it('pulls only the selected company and refreshes board and truck caches', async () => {
  mocks.get.mockResolvedValue({ data: { configured: true, status: 'connected', company: { id: 'provider' }, next_sync_at: null } })
  mocks.post.mockResolvedValue({ data: { status: 'connected', completed_at: new Date().toISOString() } })
  const invalidate = show(); fireEvent.click(screen.getByRole('button'))
  expect(await screen.findByRole('status')).toHaveTextContent('Company sync completed')
  expect(mocks.post).toHaveBeenCalledWith('/fleet/motive/sync', { fleet_customer_id: 'selected' })
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['fleet-board'] })
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['fleet-truck', 'truck'] })
})
it('honors provider cooldown without another sync', async () => {
  mocks.get.mockResolvedValue({ data: { configured: true, status: 'connected', company: {}, next_sync_at: new Date(Date.now() + 300000).toISOString() } }); show(); fireEvent.click(screen.getByRole('button'))
  expect(await screen.findByRole('status')).toHaveTextContent('Next refresh available'); expect(mocks.post).not.toHaveBeenCalled()
})
it('keeps existing readings on failure and hides provider details', async () => {
  mocks.get.mockRejectedValue(new Error('secret')); show(); fireEvent.click(screen.getByRole('button'))
  expect(await screen.findByRole('status')).toHaveTextContent('Could not refresh'); expect(screen.queryByText(/secret/)).not.toBeInTheDocument()
})
it('does not fall back to another membership', () => { show({ ...truck, board_membership_customer_id: null }); expect(screen.queryByRole('button')).not.toBeInTheDocument() })
it('hides the staff action from other roles', () => { useAuthStore.setState({ user: { role: 'fleet_manager' } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']> }); show(); expect(screen.queryByRole('button')).not.toBeInTheDocument() })
