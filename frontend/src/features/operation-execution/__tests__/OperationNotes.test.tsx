import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import { OperationNotes } from '../OperationNotes'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
const note = { id: 'note-a', labor_id: 'labor-a', body: 'Air leak at rear fitting.', actor_user_id: 'tech-a', actor_name: 'Casey Technician', created_at: '2026-10-14T15:00:00Z' }
const page = { items: [] as typeof note[], can_add: true, read_only_reason: null as string | null }
function setUser(role = 'garage_owner', tenant = 'tenant-a') {
  useAuthStore.setState({ user: { id: 'actor-a', tenant_id: tenant, role } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']>, authSessionEpoch: 0 })
}
type Props = React.ComponentProps<typeof OperationNotes>
const defaults: Props = { orderId: 'order-a', laborId: 'labor-a', description: 'Inspect steering', orderStatus: 'in_progress' }
function mount(initial: Partial<Props> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const content = (props: Partial<Props>) => <QueryClientProvider client={client}><OperationNotes {...defaults} {...props} /></QueryClientProvider>
  const view = render(content(initial))
  return { ...view, client, change: (props: Partial<Props>) => view.rerender(content(props)) }
}
async function openComposer() {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: /Operation notes/ }))
  await user.click(await screen.findByRole('button', { name: 'Add operation note' }))
  return user
}
beforeEach(() => { vi.clearAllMocks(); setUser(); api.get.mockResolvedValue({ data: page }); api.post.mockImplementation(async (_path, body) => ({ data: { ...note, ...body } })) })

describe('operation shop notes', () => {
  it('loads only on notes intent and shows saved author, time and literal text', async () => {
    api.get.mockResolvedValue({ data: { ...page, items: [{ ...note, body: '<img src=x>\nRecheck air fitting.' }] } })
    const view = mount()
    expect(api.get).not.toHaveBeenCalled()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Operation notes' }))
    expect(await screen.findByText('Casey Technician')).toBeVisible()
    expect(view.container.querySelector('time')).toHaveAttribute('datetime', note.created_at)
    expect(screen.getByText(/<img src=x>/)).toBeVisible()
    expect(view.container.querySelector('img')).toBeNull()
    expect(screen.getByText('Shop only · Not shown on invoices or customer views.')).toBeVisible()
    expect(api.get.mock.calls[0][0]).toBe('/repair-orders/order-a/operations/labor-a/notes')
  })
  it.each(['customer', 'fleet_manager', 'driver', 'super_admin'])('never fetches or renders shop notes for %s', role => {
    setUser(role); const view = mount()
    expect(view.container).toBeEmptyDOMElement(); expect(api.get).not.toHaveBeenCalled()
  })
  it('retains the failed draft and reuses the exact ID for explicit retry', async () => {
    api.post.mockRejectedValueOnce(new Error('Response lost'))
    mount(); const user = await openComposer()
    await user.type(screen.getByRole('textbox'), '  Air leak at rear fitting.  ')
    await user.click(screen.getByRole('button', { name: 'Save note' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Your draft is kept')
    expect(screen.getByRole('textbox')).toHaveValue('  Air leak at rear fitting.  ')
    expect(api.post).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Retry save' })).toBeEnabled())
    await user.click(screen.getByRole('button', { name: 'Retry save' }))
    expect(await screen.findByText('Operation note saved.')).toBeVisible()
    expect(api.post.mock.calls[1]).toEqual(api.post.mock.calls[0])
    expect(api.post.mock.calls[0][1]).toEqual({ id: expect.any(String), body: note.body })
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })
  it('blocks duplicate clicks and draft changes while a save is pending', async () => {
    let resolve!: (value: unknown) => void
    api.post.mockImplementation(() => new Promise(done => { resolve = done }))
    mount(); const user = await openComposer()
    await user.type(screen.getByRole('textbox'), note.body)
    await user.dblClick(screen.getByRole('button', { name: 'Save note' }))
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('textbox')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    await act(async () => resolve({ data: note }))
    expect(await screen.findByText('Operation note saved.')).toBeVisible()
  })
  it('preserves a draft through operation collapse and restores it on reopen', async () => {
    const view = mount(); const user = await openComposer()
    await user.type(screen.getByRole('textbox'), 'Check after warmup')
    view.change({ expanded: false }); expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    view.change({ expanded: true })
    expect(screen.getByRole('textbox')).toHaveValue('Check after warmup')
    expect(api.post).not.toHaveBeenCalled()
  })
  it('offers GET retry without falsely reporting an empty list', async () => {
    api.get.mockRejectedValueOnce(new Error('Offline'))
    mount(); const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Operation notes' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be refreshed')
    expect(screen.queryByText('No operation notes yet.')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add operation note' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry notes' }))
    expect(await screen.findByText('No operation notes yet.')).toBeVisible()
  })
  it('hides previously loaded notes when refreshed access is denied', async () => {
    api.get.mockResolvedValueOnce({ data: { ...page, items: [note] } })
    const { client } = mount()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Operation notes' }))
    expect(await screen.findByText(note.body)).toBeVisible()
    api.get.mockRejectedValue({ response: { status: 403, data: { detail: 'This operation is not assigned to you' } } })
    await act(async () => { await client.invalidateQueries({ queryKey: ['operation-notes'] }) })
    expect(await screen.findByRole('alert')).toBeVisible()
    expect(screen.queryByText(note.body)).not.toBeInTheDocument()
    expect(screen.queryByText(note.actor_name)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add operation note' })).not.toBeInTheDocument()
  })
  it('respects canonical read-only state and limits blank and long input', async () => {
    const view = mount(); const user = await openComposer()
    expect(screen.getByRole('button', { name: 'Save note' })).toBeDisabled()
    await user.type(screen.getByRole('textbox'), '   ')
    expect(screen.getByRole('button', { name: 'Save note' })).toBeDisabled()
    expect(screen.getByRole('textbox')).toHaveAttribute('maxlength', '4000')
    api.get.mockResolvedValue({ data: { ...page, can_add: false, read_only_reason: 'This order is finalized.' } })
    view.change({ orderStatus: 'completed' })
    expect(await screen.findByText('This order is finalized.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Save note' })).toBeDisabled()
    expect(api.post).not.toHaveBeenCalled()
  })
  it('can confirm a previously attempted save after finalization, without creating a new draft', async () => {
    api.post.mockRejectedValueOnce(new Error('Response lost'))
    const view = mount(); const user = await openComposer()
    await user.type(screen.getByRole('textbox'), note.body)
    await user.click(screen.getByRole('button', { name: 'Save note' }))
    await screen.findByRole('alert')
    api.get.mockResolvedValue({ data: { ...page, can_add: false, read_only_reason: 'This order is finalized.' } })
    view.change({ orderStatus: 'completed' })
    await screen.findByText('This order is finalized.')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Retry save' })).toBeEnabled())
    await user.click(screen.getByRole('button', { name: 'Retry save' }))
    expect(await screen.findByText('Operation note saved.')).toBeVisible()
    expect(api.post.mock.calls[1][1]).toEqual(api.post.mock.calls[0][1])
  })
  it('does not clear another operation draft when an old request completes', async () => {
    let resolve!: (value: unknown) => void
    api.post.mockImplementation(() => new Promise(done => { resolve = done }))
    const view = mount(); const user = await openComposer()
    await user.type(screen.getByRole('textbox'), 'First operation')
    await user.click(screen.getByRole('button', { name: 'Save note' }))
    view.change({ orderId: 'order-b', laborId: 'labor-b', description: 'Other operation' })
    await openComposer(); await user.type(screen.getByRole('textbox'), 'Second operation draft')
    await act(async () => resolve({ data: note }))
    expect(screen.getByRole('textbox')).toHaveValue('Second operation draft')
    expect(api.post.mock.calls[0][0]).toBe('/repair-orders/order-a/operations/labor-a/notes')
    expect(screen.queryByText('Operation note saved.')).not.toBeInTheDocument()
  })
  it('clears drafts and displayed notes when the authenticated tenant changes', async () => {
    mount(); const user = await openComposer()
    await user.type(screen.getByRole('textbox'), 'Private tenant draft')
    act(() => setUser('garage_owner', 'tenant-b'))
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    await openComposer()
    expect(screen.getByRole('textbox')).toHaveValue('')
  })
})
