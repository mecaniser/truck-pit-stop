import { useState } from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ post: vi.fn(), auth: { user: { id: 'user-1', tenant_id: 'tenant-1', role: 'garage_owner' }, authSessionEpoch: 1, logoutInProgress: false } }))
vi.mock('@/lib/api', () => ({ default: { post: mocks.post } }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: Object.assign((select: (state: typeof mocks.auth) => unknown) => select(mocks.auth), { getState: () => mocks.auth }) }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ accentColors: { 500: '#d86a15' } }) }))
import { useAdHocPartCommand } from '../useAdHocPartCommand'
import { quote } from './fixtures'
import type { ResolveRequest } from '../contract'
const draft = { name: 'Air filter', sku: 'FILTER', quantity: 1, unit_price: 22, unit_cost: 10, source_line_id: null }
const match = { response: { status: 409, data: { detail: { code: 'catalog_match_requires_preview', inventory: { id: 'inventory-1', sku: 'FILTER', name: 'Air filter' } } } } }
function Harness() { const command = useAdHocPartCommand('order-1'); const [status, setStatus] = useState(''); return <><button onClick={() => void command.execute(draft).then(() => setStatus('Saved')).catch(cause => setStatus(cause.name))}>Add draft</button><output>{status}</output>{command.dialog}</> }
beforeEach(() => { mocks.post.mockReset(); mocks.auth.user = { id: 'user-1', tenant_id: 'tenant-1', role: 'garage_owner' }; mocks.auth.authSessionEpoch = 1; mocks.auth.logoutInProgress = false })
it('reuses the entered-price request identity after an uncertain failure', async () => {
  const user = userEvent.setup(); mocks.post.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ data: {} }); render(<Harness />)
  await user.click(screen.getByText('Add draft')); await screen.findByText('Error'); await user.click(screen.getByText('Add draft')); await screen.findByText('Saved')
  expect(mocks.post.mock.calls[0][1]).toMatchObject(draft); expect(mocks.post.mock.calls[1][2].headers).toEqual(mocks.post.mock.calls[0][2].headers)
})
it('keeps catalog matching explicit and passes a reason through preview and write', async () => {
  const user = userEvent.setup(); mocks.post.mockImplementation((url: string, body: ResolveRequest) => url.endsWith('/ad-hoc') ? Promise.reject(match) : url === '/parts-pricing/resolve' ? Promise.resolve({ data: quote({ plan: body.plan, required: false }) }) : Promise.resolve({ data: {} })); render(<Harness />)
  await user.click(screen.getByText('Add draft')); await user.click(await screen.findByLabelText('Keep my entered price')); await user.type(screen.getByLabelText('Override reason'), 'Agreed at counter'); await user.click(screen.getByText('Review catalog price')); await screen.findByText('Confirm price')
  expect(mocks.post.mock.calls.filter(([url]) => url === '/repair-orders/order-1/parts')).toHaveLength(0)
  await user.click(screen.getByText('Confirm price')); await screen.findByText('Saved')
  const resolve = mocks.post.mock.calls.find(([url]) => url === '/parts-pricing/resolve')!; const write = mocks.post.mock.calls.find(([url]) => url === '/repair-orders/order-1/parts')!
  expect(resolve[1].plan.lines[0]).toMatchObject({ pricing_intent: 'manual', unit_price: '22.00', price_override_reason: 'Agreed at counter' }); expect(write[1]).toMatchObject({ ...resolve[1].plan.lines[0], quantity: 1, pricing_preview_fingerprint: 'opaque-1' })
})
it('cancels a matched draft without adding an existing catalog line', async () => {
  const user = userEvent.setup(); mocks.post.mockRejectedValue(match); render(<Harness />); await user.click(screen.getByText('Add draft')); await screen.findByRole('dialog'); await user.keyboard('{Escape}'); await screen.findByText('PricingCancelled'); expect(mocks.post).toHaveBeenCalledTimes(1)
})
it('does not expose manual catalog matching to mechanics', async () => {
  mocks.auth.user.role = 'mechanic'; mocks.post.mockRejectedValue(match); render(<Harness />); fireEvent.click(screen.getByText('Add draft')); await screen.findByRole('dialog'); expect(screen.queryByLabelText('Keep my entered price')).not.toBeInTheDocument()
})
it('rejects a late matched response after an actor change even before rerender', async () => {
  let reject!: (value: unknown) => void; mocks.post.mockReturnValue(new Promise((_, no) => { reject = no })); render(<Harness />); fireEvent.click(screen.getByText('Add draft')); await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1)); mocks.auth.user = { ...mocks.auth.user, tenant_id: 'tenant-2' }; await act(async () => reject(match)); await screen.findByText('PricingCancelled'); expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})
it('blocks repeated clicks while the initial request is pending', async () => {
  mocks.post.mockReturnValue(new Promise(() => {})); render(<Harness />); fireEvent.click(screen.getByText('Add draft')); fireEvent.click(screen.getByText('Add draft')); expect(mocks.post).toHaveBeenCalledTimes(1)
})
