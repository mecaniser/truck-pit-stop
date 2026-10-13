import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import MechanicPortalPage from '../MechanicPortalPage'

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
vi.mock('@/hooks/useWebSocket', () => ({ useWebSocket: () => ({}) }))
vi.mock('@/hooks/useNotificationManager', () => ({ useNotificationManager: () => ({ notify: vi.fn(), banners: [], dismissBanner: vi.fn(), clearBanners: vi.fn() }) }))
vi.mock('@/hooks/useSuggestionToasts', () => ({ useSuggestionToasts: () => undefined }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ accent: 'orange', setAccent: vi.fn(), fontSize: 'medium', setFontSize: vi.fn(), resetToDefaults: vi.fn() }), ACCENT_OPTIONS: [], FONT_SIZE_OPTIONS: [] }))
vi.mock('@/hooks/useCoreCountdown', () => ({ useCoreCountdown: () => ({ countdownNowMs: Date.parse('2026-10-13T12:00:00Z') }) }))
const baseJob = { id: 'order-a', order_number: 'QA110-HELPER', status: 'in_progress', is_order_lead: false, vehicle_info: 'C-001 Test truck', description: 'Inspect steering', services_count: 1, created_at: '2026-10-13T10:00:00Z', updated_at: '2026-10-13T10:00:00Z', work_started_at: '2026-10-13T10:00:00Z', hold_reason: null, held_at: null, ro_today_tracked_minutes: 0 }
const baseItem = { labor_id: 'labor-a', description: 'Inspect steering', mechanic_id: 'helper-a', mechanic_name: 'Alex Helper', status: 'pending', version: 1, completed_at: null, completed_by: null, tracked_seconds: 0, active_session: null, required_tasks_remaining: 0, can_assign: false, can_complete: true, can_reopen: false, can_start_timer: true, can_stop_timer: false }
let job: typeof baseJob
let item: typeof baseItem
let running: boolean
function operations() { return { items: [item], summary: { tracked: 1, completed: item.status === 'completed' ? 1 : 0, remaining: item.status === 'pending' ? 1 : 0, legacy_untracked: 0 }, order_status: job.status, is_order_lead: job.is_order_lead } }
function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><MechanicPortalPage /></QueryClientProvider>)
}
beforeEach(() => {
  vi.clearAllMocks(); job = { ...baseJob }; item = { ...baseItem }; running = false
  useAuthStore.setState({ user: { id: 'helper-a', tenant_id: 'tenant-a', role: 'mechanic', first_name: 'Alex', is_active: true } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']> })
  HTMLElement.prototype.scrollIntoView = vi.fn()
  api.get.mockImplementation(async (url: string) => {
    if (url === '/mechanics/my-jobs') return { data: [job] }
    if (url === '/mechanics/me/day-summary') return { data: { attendance_active: true, break_active: false, core_countdown_remaining_minutes: 300, tracked_minutes: 0, core_countdown_elapsed_minutes: 0, active_session: running ? { id: 'session-a', session_type: 'repair_order', repair_order_id: 'order-a', labor_id: 'labor-a', started_at: '2026-10-13T11:59:00Z' } : null } }
    if (url === '/mechanics/my-stats') return { data: { available_points: 0 } }
    if (url === '/mechanics/my-jobs/order-a') return { data: { ...job, vehicle_year: 2021, vehicle_make: 'Test', vehicle_model: 'Truck', services: [], work_completed_at: null } }
    if (url === '/repair-orders/order-a/operations') return { data: operations() }
    if (url === '/repair-orders/order-a/checklist') return { data: { items: [], total: 0, skip: 0, limit: 100, summary: { total: 0, completed: 0, required: 0, required_remaining: 0 }, can_update: true } }
    return { data: [] }
  })
})
describe('mechanic operation workspace', () => {
  it('opens helper operations without starting the whole order, omits lead-only controls and photo requests', async () => {
    mount()
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Open operations' }))
    await screen.findByRole('region', { name: 'Operation progress' })
    const start = await screen.findByRole('button', { name: 'Start timer' })
    await waitFor(() => expect(start).toBeEnabled())
    expect(screen.queryByRole('button', { name: /^HOLD$/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^(DONE|JOB DONE|Job Done|RESUME|ACCEPT & START)$/ })).not.toBeInTheDocument()
    expect(screen.queryByText('Photos')).not.toBeInTheDocument()
    expect(api.get.mock.calls.some(([url]) => String(url).endsWith('/photos'))).toBe(false)
    expect(api.post).not.toHaveBeenCalled()
    api.post.mockImplementation(async () => { running = true; return { data: operations() } })
    await userEvent.setup().click(start)
    await screen.findByRole('button', { name: 'Operations' })
    expect(api.post).toHaveBeenCalledWith('/repair-orders/order-a/operations/labor-a/timer/start', { expected_version: 1 })
    expect(screen.queryByRole('button', { name: 'Job Done' })).not.toBeInTheDocument()
  })
  it('keeps operation reopening reachable during whole-order review for an assigned helper', async () => {
    job.status = 'pending_review'; item = { ...item, status: 'completed', can_complete: false, can_start_timer: false, can_reopen: true }
    api.put.mockResolvedValue({ data: operations() }); mount()
    await userEvent.setup().click(await screen.findByRole('button', { name: /C-001 Test truck.*Pending Review/ }))
    const reopen = await screen.findByRole('button', { name: 'Reopen operation' })
    await waitFor(() => expect(reopen).toBeEnabled())
    await userEvent.setup().click(reopen)
    expect(api.put).toHaveBeenCalledWith('/repair-orders/order-a/operations/labor-a/completion', { expected_version: 1, is_completed: false })
    expect(screen.queryByRole('button', { name: 'Job Done' })).not.toBeInTheDocument()
  })
  it('does not describe a failed job request as all caught up', async () => {
    const normal = api.get.getMockImplementation()!
    api.get.mockImplementation((url: string) => url === '/mechanics/my-jobs' ? Promise.reject(new Error('Offline')) : normal(url))
    mount(); await screen.findByRole('button', { name: 'Retry jobs' })
    expect(screen.queryByText('All caught up!')).not.toBeInTheDocument()
  })
  it('preserves read-only parts-only scope for the lead when no operation rows exist', async () => {
    job.is_order_lead = true
    const normal = api.get.getMockImplementation()!
    api.get.mockImplementation(async (url: string) => {
      if (url === '/repair-orders/order-a/operations') return { data: { items: [], summary: { tracked: 0, completed: 0, remaining: 0, legacy_untracked: 0 }, order_status: 'in_progress', is_order_lead: true } }
      const response = await normal(url)
      return url === '/mechanics/my-jobs/order-a' ? { data: { ...response.data, services: [{ name: 'Install oil filter', description: 'Parts-only legacy scope' }] } } : response
    })
    mount()
    await userEvent.setup().click(await screen.findByRole('button', { name: /C-001 Test truck.*Order lead/ }))
    await screen.findByText('Install oil filter')
    expect(screen.getByText('Parts-only legacy scope')).toBeVisible()
    expect(screen.queryByText('No operations assigned.')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Complete operation' })).not.toBeInTheDocument()
  })
  it('never reveals legacy lead scope to a helper or substitutes it for a failed operation request', async () => {
    const normal = api.get.getMockImplementation()!
    api.get.mockImplementation(async (url: string) => {
      if (url === '/repair-orders/order-a/operations') return { data: { items: [], summary: { tracked: 0, completed: 0, remaining: 0, legacy_untracked: 0 }, order_status: 'in_progress', is_order_lead: false } }
      const response = await normal(url)
      return url === '/mechanics/my-jobs/order-a' ? { data: { ...response.data, services: [{ name: 'Private lead scope' }] } } : response
    })
    mount()
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Open operations' }))
    await screen.findByText('No operations assigned.')
    expect(screen.queryByText('Private lead scope')).not.toBeInTheDocument()
  })
  it('keeps operation load failure distinct from successful empty legacy scope for the lead', async () => {
    job.is_order_lead = true
    const normal = api.get.getMockImplementation()!
    api.get.mockImplementation(async (url: string) => {
      if (url === '/repair-orders/order-a/operations') throw new Error('Offline')
      const response = await normal(url)
      return url === '/mechanics/my-jobs/order-a' ? { data: { ...response.data, services: [{ name: 'Unverified old scope' }] } } : response
    })
    mount()
    await userEvent.setup().click(await screen.findByRole('button', { name: /C-001 Test truck.*Order lead/ }))
    await screen.findByRole('button', { name: 'Retry operation progress' })
    expect(screen.queryByText('Unverified old scope')).not.toBeInTheDocument()
    expect(screen.queryByText('No operations assigned.')).not.toBeInTheDocument()
  })
})
