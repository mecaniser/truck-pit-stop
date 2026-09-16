import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { PropsWithChildren } from 'react'
import { expect, it, vi } from 'vitest'
import { DB048_SETTLEMENT_FIXTURES } from '@/test-fixtures/db048/settlements'
import type { InvoiceSettlementSummary } from '../types'

const api = vi.hoisted(() => ({ fetchSettlement: vi.fn() }))
vi.mock('../api', () => api)
import { useInvoiceSettlement } from '../useInvoiceSettlement'

it('keeps a newer confirmed cache result when an older in-flight query or mutation finishes', async () => {
  const original = DB048_SETTLEMENT_FIXTURES.unpaid.summary
  let finish!: (value: InvoiceSettlementSummary) => void
  api.fetchSettlement.mockReturnValue(new Promise(resolve => { finish = resolve }))
  const client = new QueryClient()
  const key = ['invoice-settlement', 'authenticated', original.invoice_id]
  const view = renderHook(() => useInvoiceSettlement({ kind: 'authenticated', invoiceId: original.invoice_id }), {
    wrapper: ({ children }: PropsWithChildren) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
  })
  const paid = { ...original, version: original.version + 2, state: 'paid' as const }
  await act(async () => { client.setQueryData(key, paid) })
  await act(async () => finish(original))
  await waitFor(() => expect(view.result.current.isFetching).toBe(false))
  expect(view.result.current.data).toEqual(paid)
  await act(async () => { client.setQueryData(key, { ...original, version: original.version + 1 }) })
  expect(view.result.current.data).toEqual(paid)
})
