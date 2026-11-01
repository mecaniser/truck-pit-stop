import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ list: vi.fn(), fetch: vi.fn(), claim: vi.fn(), ack: vi.fn(), reconcile: vi.fn() }))
vi.mock('../api', () => ({ fetchEtsReceiptTasks: mocks.list, fetchSourceCollection: mocks.fetch, claimEtsReceiptTask: mocks.claim, acknowledgeEtsReceiptTask: mocks.ack, reconcileSourceCollection: mocks.reconcile }))
import EtsReceiptTasks from '../EtsReceiptTasks'
import type { EtsReceiptTask, SourceCollectionSummary } from '../types'

const summary = { id: 'handoff', state: 'active', version: 2, source_invoice_number: '1687', source_capture_sha256: 'fresh-digest', source_revision: 'fresh-revision' } as SourceCollectionSummary
const task: EtsReceiptTask = {
  id: 'task', handoff_id: 'handoff', invoice_id: 'native', payment_id: 'receipt-123', attempt_id: null,
  principal_amount: '100.00', received_amount: '103.00', fee_amount: '3.00', unapplied_amount: '0.00', currency: 'USD',
  effective_at: '2026-11-01T10:00:00Z', state: 'claimed', version: 2, expected_source_revision: 'old', claim_expires_at: '2099-11-01T12:00:00Z',
}
beforeEach(() => {
  vi.resetAllMocks()
  mocks.fetch.mockResolvedValue(summary)
  mocks.list.mockResolvedValue({ items: [task], total: 1, skip: 0, limit: 20 })
})
function show(onChange = vi.fn()) {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><EtsReceiptTasks handoff={summary} onChange={onChange} /></QueryClientProvider>)
  return onChange
}

describe('manual ETS receipt reconciliation', () => {
  it('shows principal and DBN marker, then verifies exact allocation references with fresh evidence', async () => {
    mocks.ack.mockResolvedValue({ ...task, state: 'verified' })
    show()
    await screen.findByText('$100.00 to record in ETS')
    expect(screen.getByText('DBN-RECEIPT:receipt-123')).toBeInTheDocument()
    expect(screen.queryByText('$103.00 to record in ETS')).not.toBeInTheDocument()
    const verify = screen.getByRole('button', { name: 'Verify ETS receipt' })
    expect(verify).toBeDisabled()
    fireEvent.change(screen.getByLabelText('ETS allocation IDs from the recorded receipt'), { target: { value: 'allocation-1, allocation-2' } })
    fireEvent.click(verify)
    await waitFor(() => expect(mocks.ack).toHaveBeenCalled())
    expect(mocks.ack.mock.calls[0].slice(0, 3)).toEqual([task, summary, ['allocation-1', 'allocation-2']])
    expect(mocks.reconcile).not.toHaveBeenCalled()
  })

  it('allows reclaim of an expired lease and prevents verification until refreshed', async () => {
    mocks.list.mockResolvedValue({ items: [{ ...task, claim_expires_at: '2000-01-01T00:00:00Z' }], total: 1, skip: 0, limit: 20 })
    mocks.claim.mockResolvedValue(task)
    show()
    fireEvent.click(await screen.findByRole('button', { name: 'Reclaim ETS update' }))
    await waitFor(() => expect(mocks.claim).toHaveBeenCalled())
    expect(mocks.ack).not.toHaveBeenCalled()
  })

  it('unwraps a reconcile result and keeps a source conflict visible', async () => {
    const conflict = { ...summary, state: 'source_conflict' }
    mocks.reconcile.mockResolvedValue({ handoff: conflict, conflict: true })
    const onChange = show()
    fireEvent.click(await screen.findByRole('button', { name: 'Reconcile ETS payments' }))
    await screen.findByRole('alert')
    expect(onChange).toHaveBeenCalledWith(conflict)
    expect(onChange).not.toHaveBeenCalledWith(expect.objectContaining({ handoff: conflict }))
    expect(mocks.ack).not.toHaveBeenCalled()
  })
})
