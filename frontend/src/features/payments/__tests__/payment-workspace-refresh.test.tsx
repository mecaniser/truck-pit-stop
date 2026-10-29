import { act, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { beforeEach, expect, it, vi } from 'vitest'
import { DB048_SETTLEMENT_FIXTURES } from '@/test-fixtures/db048/settlements'
import type { InvoiceSettlementSummary } from '../types'

const server = vi.hoisted(() => ({ summary: null as InvoiceSettlementSummary | null, fail: false }))
vi.mock('../api', async original => ({
  ...await original<typeof import('../api')>(),
  fetchSettlement: vi.fn(async () => {
    if (server.fail) throw new Error('Status unavailable')
    return server.summary
  }),
  fetchAllocations: vi.fn(async () => ({ items: [] })),
}))
vi.mock('../AccountingReconciliationPanel', () => ({ default: () => null }))
vi.mock('../PendingManualPaymentPanel', () => ({ default: () => null }))
vi.mock('../SettlementResolutionPanel', () => ({ default: () => null }))
vi.mock('../SettlementCreditPanel', () => ({ default: () => null }))
vi.mock('../EarlyVehicleReleasePanel', () => ({ default: () => null }))
vi.mock('../FullCashPaymentPanel', () => ({ default: () => null }))
import StaffSettlementDialog from '../StaffSettlementDialog'
import { refreshPaymentViews } from '../refreshPaymentViews'

const base = DB048_SETTLEMENT_FIXTURES.unpaid.summary
const keys = [
  ['dashboard-action-queue'], ['dashboard-daily-workset'],
  ['dashboard-daily-workset', 'value-summary', 'ready_to_close', ''],
  ['repair-orders', 'infinite', { status: 'overdue' }], ['repair-orders', 'status-counts'],
  ['repair-orders', 'value-summary', { status: 'overdue' }], ['invoices'],
]
const reads = keys.map(() => vi.fn(async () => server.summary?.state === 'paid' ? 'closed:0' : `open:${server.summary?.outstanding_balance}`))
function Projection({ index }: { index: number }) {
  const query = useQuery({ queryKey: keys[index], queryFn: reads[index] })
  return <output data-testid={`projection-${index}`}>{query.data}</output>
}
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  const updated = vi.fn()
  render(<QueryClientProvider client={client}>
    {keys.map((_, index) => <Projection key={index} index={index} />)}
    <StaffSettlementDialog invoiceId={base.invoice_id} invoiceNumber="Fixture" open onClose={vi.fn()} onUpdated={updated} />
  </QueryClientProvider>)
  return { client, updated }
}
beforeEach(() => {
  server.summary = { ...base }
  server.fail = false
  reads.forEach(read => read.mockClear())
})
it('refreshes queues, overdue counts and totals when a later card status read confirms payment', async () => {
  const { client, updated } = setup()
  await screen.findByText('Unpaid')
  await waitFor(() => expect(updated).toHaveBeenCalled())
  updated.mockClear()
  server.summary = { ...base, version: base.version + 1, state: 'paid', outstanding_balance: '0.00', allocatable_balance: '0.00' }
  await act(async () => { await client.invalidateQueries({ queryKey: ['invoice-settlement'] }) })
  await screen.findByText('Paid in full')
  await waitFor(() => keys.forEach((_, index) => expect(screen.getByTestId(`projection-${index}`)).toHaveTextContent('closed:0')))
  expect(updated).toHaveBeenCalledTimes(1)
  updated.mockClear()
  await act(async () => {
    client.setQueryData(['invoice-settlement', 'authenticated', base.invoice_id], { ...base, invoice_id: 'other-invoice', version: base.version + 9 })
  })
  await act(async () => {
    client.setQueryData(['invoice-settlement', 'authenticated', base.invoice_id], base)
  })
  expect(screen.getByText('Paid in full')).toBeInTheDocument()
  expect(updated).not.toHaveBeenCalled()
})
it('retains server membership for partial, pending and failed status reads', async () => {
  const { client } = setup()
  await screen.findByText('Unpaid')
  server.summary = { ...base, version: base.version + 1, state: 'partially_paid', outstanding_balance: '40.00' }
  await act(async () => { await client.invalidateQueries({ queryKey: ['invoice-settlement'] }) })
  await waitFor(() => keys.forEach((_, index) => expect(screen.getByTestId(`projection-${index}`)).toHaveTextContent('open:40.00')))
  server.summary = { ...server.summary, version: base.version + 2, state: 'partially_paid_pending', active_pending_principal: '40.00' }
  await act(async () => { await client.invalidateQueries({ queryKey: ['invoice-settlement'] }) })
  server.fail = true
  await act(async () => { await client.invalidateQueries({ queryKey: ['invoice-settlement'] }) })
  keys.forEach((_, index) => expect(screen.getByTestId(`projection-${index}`)).toHaveTextContent('open:40.00'))
})
it('invalidates inactive queues for navigation without refreshing unrelated caches', () => {
  const client = new QueryClient()
  keys.forEach(key => client.setQueryData(key, 'old'))
  client.setQueryData(['invoice-settlement', 'authenticated', 'different-invoice'], base)
  client.setQueryData(['customers'], ['untouched'])
  refreshPaymentViews(client)
  keys.forEach(key => expect(client.getQueryState(key)?.isInvalidated).toBe(true))
  expect(client.getQueryState(['customers'])?.isInvalidated).toBe(false)
  expect(client.getQueryState(['invoice-settlement', 'authenticated', 'different-invoice'])?.isInvalidated).toBe(false)
})
