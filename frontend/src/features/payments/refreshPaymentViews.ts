import type { QueryClient } from '@tanstack/react-query'

// Queue membership and totals come from the server. A pending or partial
// payment must never optimistically remove an order from Ready to Close.
export function refreshPaymentViews(queryClient: QueryClient) {
  for (const key of [
    'dashboard-action-queue',
    'dashboard-daily-workset',
    'repair-orders',
    'invoices',
  ]) {
    void queryClient.invalidateQueries({ queryKey: [key] })
  }
}
