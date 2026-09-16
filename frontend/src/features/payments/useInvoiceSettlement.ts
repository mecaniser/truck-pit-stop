import { useQuery } from '@tanstack/react-query'

import { fetchAllocations, fetchSettlement } from './api'
import type { InvoiceSettlementSummary, SettlementAccess } from './types'

const accessKey = (access: SettlementAccess | null) => access?.kind === 'guest'
  ? ['guest', access.token]
  : ['authenticated', access?.invoiceId]

export function useInvoiceSettlement(access: SettlementAccess | null) {
  return useQuery({
    queryKey: ['invoice-settlement', ...accessKey(access)],
    queryFn: () => fetchSettlement(access!),
    enabled: Boolean(access),
    retry: false,
    // Refetches and mutation responses can finish out of order. Preserve the
    // newest server version for this invoice, including cache writes by controls.
    structuralSharing: (previous, next) => {
      const oldSummary = previous as InvoiceSettlementSummary | undefined
      const nextSummary = next as InvoiceSettlementSummary
      return oldSummary?.invoice_id === nextSummary.invoice_id && oldSummary.version > nextSummary.version
        ? oldSummary : nextSummary
    },
    staleTime: 10_000,
  })
}

export function useInvoiceAllocations(access: SettlementAccess | null, enabled = true) {
  return useQuery({
    queryKey: ['invoice-settlement-allocations', ...accessKey(access)],
    queryFn: () => fetchAllocations(access!),
    enabled: Boolean(access) && enabled,
    retry: false,
    staleTime: 10_000,
  })
}
