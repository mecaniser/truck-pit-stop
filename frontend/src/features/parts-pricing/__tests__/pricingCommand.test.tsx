import { useState } from 'react'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ post: vi.fn(), auth: { user: { id: 'user-1', tenant_id: 'tenant-1', role: 'garage_owner' }, authSessionEpoch: 1, logoutInProgress: false } }))
vi.mock('@/lib/api', () => ({ default: { post: mocks.post } }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: Object.assign((select: (state: typeof mocks.auth) => unknown) => select(mocks.auth), { getState: () => mocks.auth }) }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ accentColors: { 500: '#d86a15' } }) }))
import { parsePricingPreview, type ResolveRequest } from '../contract'
import { usePricingCommand } from '../usePricingCommand'
import { quote, request } from './fixtures'
function Harness({ write, context = 'order-1', plan = request }: { write: ReturnType<typeof vi.fn>; context?: string; plan?: ResolveRequest }) {
  const command = usePricingCommand(context)
  const [status, setStatus] = useState('')
  return <><button onClick={() => void command.execute(plan, write).then(() => setStatus('saved')).catch(cause => setStatus(cause.name))}>Add</button><output>{status}</output>{command.dialog}</>
}
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done }); return { promise, resolve } }
beforeEach(() => { mocks.post.mockReset(); mocks.auth.user = { id: 'user-1', tenant_id: 'tenant-1', role: 'garage_owner' }; mocks.auth.authSessionEpoch = 1; mocks.auth.logoutInProgress = false })
describe('pricing command confirmation and replay', () => {
  it('requires explicit confirmation for managed prices and uses a UUID', async () => {
    const user = userEvent.setup(); const write = vi.fn().mockResolvedValue({}); mocks.post.mockResolvedValue({ data: quote() }); render(<Harness write={write} />)
    await user.click(screen.getByText('Add')); expect(await screen.findByRole('dialog')).toBeInTheDocument(); expect(write).not.toHaveBeenCalled()
    await user.click(screen.getByText('Confirm price')); await waitFor(() => expect(write).toHaveBeenCalledTimes(1))
    expect(write.mock.calls[0][0]).toEqual({ pricing_preview_fingerprint: 'opaque-1', pricing_presentation: 'shop' }); expect(write.mock.calls[0][1].headers['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/)
  })
  it('does not add a review dialog for an unmanaged unchanged add', async () => {
    const user = userEvent.setup(); const write = vi.fn().mockResolvedValue({}); mocks.post.mockResolvedValue({ data: quote({ required: false }) }); render(<Harness write={write} />)
    await user.click(screen.getByText('Add')); await waitFor(() => expect(write).toHaveBeenCalledTimes(1)); expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it('retries an uncertain write with its original UUID and fingerprint', async () => {
    const user = userEvent.setup(); const write = vi.fn().mockRejectedValueOnce(new Error('Network interrupted')).mockResolvedValueOnce({}); mocks.post.mockResolvedValue({ data: quote() }); render(<Harness write={write} />)
    await user.click(screen.getByText('Add')); await user.click(await screen.findByText('Confirm price')); await screen.findByText('Error'); await user.click(screen.getByText('Add')); await screen.findByText('saved')
    expect(mocks.post).toHaveBeenCalledTimes(1); expect(write.mock.calls[1][1].headers).toEqual(write.mock.calls[0][1].headers); expect(write.mock.calls[1][0]).toEqual(write.mock.calls[0][0])
  })
  it('shows old and new prices on409 and writes only after re-acceptance with a new UUID', async () => {
    const user = userEvent.setup(); const write = vi.fn().mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'pricing_preview_changed', message: 'Price changed.', preview: quote({ fingerprint: 'opaque-2', total: '18.00' }) } } } }).mockResolvedValueOnce({}); mocks.post.mockResolvedValue({ data: quote() }); render(<Harness write={write} />)
    await user.click(screen.getByText('Add')); await user.click(await screen.findByText('Confirm price')); expect(await screen.findByText('Accept new price')).toBeInTheDocument(); expect(screen.getByText(/Was \$15.00/)).toBeInTheDocument(); expect(write).toHaveBeenCalledTimes(1)
    await user.click(screen.getByText('Accept new price')); await screen.findByText('saved'); expect(write.mock.calls[1][1].headers).not.toEqual(write.mock.calls[0][1].headers); expect(write.mock.calls[1][0].pricing_preview_fingerprint).toBe('opaque-2')
  })
  it('refetches a missing conflict preview and waits for explicit acceptance', async () => {
    const user = userEvent.setup(); const write = vi.fn().mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'pricing_preview_changed', message: 'Labor changed while applying this service. Review the updated work.' } } } }).mockResolvedValueOnce({})
    mocks.post.mockResolvedValueOnce({ data: quote({ required: false }) }).mockResolvedValueOnce({ data: quote({ required: false, fingerprint: 'fresh-no-embedded-preview', total: '21.00' }) }); render(<Harness write={write} />)
    await user.click(screen.getByText('Add')); expect(await screen.findByText('Accept new price')).toBeInTheDocument(); expect(write).toHaveBeenCalledTimes(1); expect(mocks.post).toHaveBeenCalledTimes(2)
    expect(screen.getByRole('dialog')).toHaveTextContent('Labor changed while applying this service.')
    await user.click(screen.getByText('Accept new price')); await screen.findByText('saved')
    expect(write.mock.calls[1][0].pricing_preview_fingerprint).toBe('fresh-no-embedded-preview'); expect(write.mock.calls[1][1].headers).not.toEqual(write.mock.calls[0][1].headers)
  })
  it('shows a failed conflict refresh and makes an explicit retry obtain a new quote', async () => {
    const user = userEvent.setup(); const write = vi.fn().mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'pricing_preview_changed', message: 'Price changed.' } } } }).mockResolvedValueOnce({})
    mocks.post.mockResolvedValueOnce({ data: quote({ required: false }) }).mockRejectedValueOnce(new Error('Network interrupted')).mockResolvedValueOnce({ data: quote({ fingerprint: 'recovered' }) }); render(<Harness write={write} />)
    await user.click(screen.getByText('Add')); expect(await screen.findByRole('alert')).toHaveTextContent('Your draft is kept. Try again.'); expect(write).toHaveBeenCalledTimes(1)
    await user.click(screen.getByText('Add')); await user.click(await screen.findByText('Confirm price')); await screen.findByText('saved')
    expect(mocks.post).toHaveBeenCalledTimes(3); expect(write.mock.calls[1][0].pricing_preview_fingerprint).toBe('recovered')
  })
  it('Escape cancels without writing', async () => { const user = userEvent.setup(); const write = vi.fn(); mocks.post.mockResolvedValue({ data: quote() }); render(<Harness write={write} />); await user.click(screen.getByText('Add')); await screen.findByRole('dialog'); await user.keyboard('{Escape}'); await screen.findByText('PricingCancelled'); expect(write).not.toHaveBeenCalled() })
  it('rejects foreign part metadata before confirmation', async () => { const user = userEvent.setup(); const write = vi.fn(); const data = quote(); data.lines[0].inventory_id = 'foreign'; mocks.post.mockResolvedValue({ data }); render(<Harness write={write} />); await user.click(screen.getByText('Add')); await screen.findByText('Error'); expect(screen.queryByRole('dialog')).not.toBeInTheDocument(); expect(write).not.toHaveBeenCalled() })
  it.each(['tenant', 'role', 'epoch', 'context'])('cancels a pending read after %s changes', async kind => {
    const user = userEvent.setup(); const read = deferred<{ data: ReturnType<typeof quote> }>(); const write = vi.fn(); mocks.post.mockReturnValue(read.promise); const view = render(<Harness write={write} />); await user.click(screen.getByText('Add'))
    if (kind === 'tenant') mocks.auth.user = { ...mocks.auth.user, tenant_id: 'tenant-2' }; if (kind === 'role') mocks.auth.user = { ...mocks.auth.user, role: 'mechanic' }; if (kind === 'epoch') mocks.auth.authSessionEpoch++
    view.rerender(<Harness write={write} context={kind === 'context' ? 'order-2' : 'order-1'} />); await act(async () => { read.resolve({ data: quote() }) }); expect(write).not.toHaveBeenCalled(); expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it('rejects a write completion from the previous actor', async () => { const user = userEvent.setup(); const pending = deferred<unknown>(); const write = vi.fn().mockReturnValue(pending.promise); mocks.post.mockResolvedValue({ data: quote({ required: false }) }); const view = render(<Harness write={write} />); await user.click(screen.getByText('Add')); await waitFor(() => expect(write).toHaveBeenCalled()); mocks.auth.user = { ...mocks.auth.user, id: 'user-2' }; view.rerender(<Harness write={write} />); await act(async () => { pending.resolve({}) }); expect(screen.queryByText('saved')).not.toBeInTheDocument(); await screen.findByText('PricingCancelled') })
})
describe('audience-safe projections', () => {
  it('rejects shop line money in fleet previews', () => { const fleet = quote({ projection: 'fleet' }); expect(() => parsePricingPreview({ ...fleet, lines: [{ ...fleet.lines[0], pricing: { charged_unit_price: '15.00' } }] }, { ...request, pricing_presentation: 'fleet' }, 'garage_owner')).toThrow() })
  it('rejects elevated management data without explicit owner opt-in or on a conflict', () => { const data = { ...quote(), management: { default_generation: 1, lines: [] } }; expect(() => parsePricingPreview(data, request, 'garage_owner')).toThrow(); expect(() => parsePricingPreview(data, { ...request, include_management_details: true }, 'mechanic')).toThrow(); expect(() => parsePricingPreview(data, { ...request, include_management_details: true }, 'garage_owner', true)).toThrow() })
  it('forces fleet actors to the fleet projection', () => { expect(() => parsePricingPreview(quote(), request, 'fleet_manager')).toThrow(); expect(parsePricingPreview(quote({ projection: 'fleet' }), request, 'fleet_manager').projection).toBe('fleet') })
})
