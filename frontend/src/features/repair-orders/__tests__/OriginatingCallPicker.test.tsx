import { act, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { beforeEach, expect, it, vi } from 'vitest'
const api = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
import OriginatingCallPicker from '../OriginatingCallPicker'
const option = { reference_token: 'signed-reference', call_id: 'call-1', opportunity_id: 'op-1', started_at: '2026-10-14T15:00:00Z', contact_label: 'Shop contact', service_summary: 'Tire repair', expires_at: '2026-10-15T15:00:00Z' }
beforeEach(() => vi.resetAllMocks())
function Picker({ customerId = 'customer-1' }: { customerId?: string }) {
  const [value, setValue] = useState<string | null>(null)
  return <OriginatingCallPicker key={customerId} customerId={customerId} value={value} onChange={setValue} />
}
it('loads through the authenticated client only on request and never auto-selects', async () => {
  api.post.mockResolvedValue({ data: { options: [option] } })
  render(<Picker />)
  expect(api.post).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Link originating call' }))
  expect(await screen.findByText('Tire repair')).toBeVisible()
  expect(api.post).toHaveBeenCalledWith('/repair-orders/originating-call-options', { customer_id: 'customer-1' }, { signal: expect.any(AbortSignal) })
  expect(screen.getByRole('radio', { name: 'Leave unlinked' })).toBeChecked()
  fireEvent.click(screen.getByRole('radio', { name: /Shop contact/ }))
  expect(screen.getByRole('radio', { name: /Shop contact/ })).toBeChecked()
  fireEvent.click(screen.getByRole('radio', { name: 'Leave unlinked' }))
  expect(screen.getByRole('radio', { name: 'Leave unlinked' })).toBeChecked()
})
it.each([409, 502])('keeps the repair usable when calls are unavailable (%s)', async status => {
  api.post.mockRejectedValue({ response: { status, data: { detail: 'private provider diagnostic' } } })
  render(<Picker />)
  fireEvent.click(screen.getByRole('button', { name: 'Link originating call' }))
  expect(await screen.findByRole('status')).toHaveTextContent('You can still create this repair order')
  expect(screen.queryByText('private provider diagnostic')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Link originating call' })).toBeEnabled()
})
it('aborts and ignores a late response after changing customer', async () => {
  let resolve!: (value: unknown) => void
  api.post.mockImplementation(() => new Promise(r => { resolve = r }))
  const view = render(<Picker />)
  fireEvent.click(screen.getByRole('button', { name: 'Link originating call' }))
  const signal = api.post.mock.calls[0][2].signal
  view.rerender(<Picker customerId="customer-2" />)
  expect(signal.aborted).toBe(true)
  await act(async () => resolve({ data: { options: [option] } }))
  expect(screen.queryByText('Tire repair')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Link originating call' })).toBeEnabled()
})
