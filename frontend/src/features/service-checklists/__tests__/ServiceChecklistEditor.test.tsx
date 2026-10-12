import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ThemeProvider } from '@/contexts/ThemeContext'
import { useAuthStore } from '@/stores/authStore'
import ServiceChecklistEditor from '../ServiceChecklistEditor'
import ServicesManagementPage from '@/features/dashboard/ServicesManagementPage'

const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: mocks }))
vi.mock('react-hot-toast', () => ({ default: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }))
const template = { service_id: 'service-a', version: 2, items: [{ id: 'task-a', label: 'Secure drain plug', required: true }, { id: 'task-b', label: 'Record filter brand', required: false }] }
function mount(component = <ServiceChecklistEditor serviceId="service-a" />) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}>{component}</QueryClientProvider>)
}
beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({ user: { id: 'owner-a', tenant_id: 'tenant-a', role: 'garage_owner', is_active: true } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']> })
  mocks.get.mockResolvedValue({ data: template })
})
describe('service checklist templates', () => {
  it('adds required tasks, preserves stable IDs through reorder, and explicitly saves a revision', async () => {
    const user = userEvent.setup(); mount()
    await screen.findByDisplayValue('Secure drain plug')
    await user.click(screen.getByRole('button', { name: 'Move task 2 up' }))
    expect(screen.getByRole('textbox', { name: 'Task 1', exact: true })).toHaveValue('Record filter brand')
    await user.click(screen.getByRole('button', { name: 'Add task' }))
    expect(screen.getByRole('checkbox', { name: 'Task 3 required' })).toBeChecked()
    const save = screen.getByRole('button', { name: 'Save checklist' })
    expect(save).toBeDisabled()
    await user.type(screen.getByRole('textbox', { name: 'Task 3', exact: true }), 'Check for leaks')
    mocks.put.mockResolvedValue({ data: { ...template, version: 3 } })
    await user.click(save)
    await screen.findByText('Checklist saved. Existing jobs keep their original tasks.')
    expect(mocks.put).toHaveBeenCalledWith('/services/service-a/checklist', {
      expected_version: 2,
      items: [template.items[1], template.items[0], { label: 'Check for leaks', required: true }],
    })
  })
  it('retains the draft on conflict and only replaces it after an explicit reload', async () => {
    const user = userEvent.setup(); mount()
    const field = await screen.findByRole('textbox', { name: 'Task 1', exact: true })
    await user.clear(field); await user.type(field, 'My unsaved task')
    mocks.put.mockRejectedValue({ response: { status: 409, data: { detail: 'This checklist changed. Reload it before saving.' } } })
    await user.click(screen.getByRole('button', { name: 'Save checklist' }))
    await screen.findByRole('alert')
    expect(field).toHaveValue('My unsaved task')
    expect(screen.getByRole('button', { name: 'Save checklist' })).toBeDisabled()
    expect(mocks.put).toHaveBeenCalledTimes(1)
    mocks.get.mockResolvedValue({ data: { ...template, version: 3, items: [{ ...template.items[0], label: 'Another author task' }] } })
    await user.click(screen.getByRole('button', { name: 'Discard edits and reload' }))
    await screen.findByDisplayValue('Another author task')
    expect(screen.queryByDisplayValue('My unsaved task')).not.toBeInTheDocument()
  })
  it('can remove all future tasks without touching existing job snapshots', async () => {
    const user = userEvent.setup(); mount()
    await screen.findByDisplayValue('Secure drain plug')
    await user.click(screen.getByRole('button', { name: 'Remove task 2' }))
    await user.click(screen.getByRole('button', { name: 'Remove task 1' }))
    mocks.put.mockResolvedValue({ data: { ...template, version: 3, items: [] } })
    await user.click(screen.getByRole('button', { name: 'Save checklist' }))
    expect(mocks.put).toHaveBeenCalledWith('/services/service-a/checklist', { expected_version: 2, items: [] })
  })
  it('discards a template draft when the authenticated scope changes', async () => {
    const user = userEvent.setup(); mount()
    const field = await screen.findByRole('textbox', { name: 'Task 1', exact: true })
    await user.clear(field); await user.type(field, 'Private tenant A draft')
    mocks.get.mockResolvedValue({ data: { ...template, items: [{ ...template.items[0], label: 'Tenant B task' }] } })
    act(() => useAuthStore.setState(state => ({ user: { ...state.user!, tenant_id: 'tenant-b' } })))
    await screen.findByDisplayValue('Tenant B task')
    expect(screen.queryByDisplayValue('Private tenant A draft')).not.toBeInTheDocument()
    expect(mocks.put).not.toHaveBeenCalled()
  })
  it('keeps a newly created service open after checklist failure and retries without creating a duplicate', async () => {
    const user = userEvent.setup()
    const service = { id: 'created-service', name: 'QA Oil service', category_id: null, description: null, duration_minutes: 60, base_price: null, icon: null, sort_order: 0, is_active: true, requires_vehicle: true, parts: [], labor_cost: '100', parts_cost: '0', computed_total_price: '100' }
    mocks.get.mockImplementation((url: string) => Promise.resolve({ data: url.endsWith('/checklist') ? { service_id: service.id, version: 0, items: [] } : [] }))
    mocks.post.mockResolvedValue({ data: service })
    mocks.put.mockRejectedValueOnce({ response: { status: 500 } })
    mount(<ThemeProvider><ServicesManagementPage /></ThemeProvider>)
    await user.click(await screen.findByRole('button', { name: /Add Service/i }))
    await user.type(screen.getByPlaceholderText('Battery Test & Replacement'), service.name)
    await user.click(screen.getByRole('button', { name: 'Add task' }))
    await user.type(screen.getByRole('textbox', { name: 'Task 1', exact: true }), 'Verify oil level')
    await user.click(screen.getByRole('button', { name: 'Create Service', exact: true }))
    await screen.findByText('Service created. Checklist has not been saved. Retry below.')
    expect(screen.getByRole('dialog', { name: 'Edit Service' })).toBeVisible()
    expect(screen.getByRole('textbox', { name: 'Task 1', exact: true })).toHaveValue('Verify oil level')
    expect(screen.queryByRole('button', { name: 'Create Service', exact: true })).not.toBeInTheDocument()
    mocks.put.mockResolvedValueOnce({ data: { service_id: service.id, version: 1, items: [{ id: 'created-task', label: 'Verify oil level', required: true }] } })
    await user.click(screen.getByRole('button', { name: 'Save checklist' }))
    await screen.findByText('Checklist saved. Existing jobs keep their original tasks.')
    expect(mocks.post).toHaveBeenCalledTimes(1)
    expect(mocks.put).toHaveBeenNthCalledWith(2, '/services/created-service/checklist', { expected_version: 0, items: [{ label: 'Verify oil level', required: true }] })
    expect(within(screen.getByRole('dialog')).getByRole('button', { name: 'Save checklist' })).toBeDisabled()
    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/services', expect.objectContaining({ name: service.name })))
  })
})
