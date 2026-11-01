import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'

import type { ImportedBilling } from '@/types'
export type { ImportedBilling } from '@/types'

export const importedPaymentLabel = (status: ImportedBilling['payment_status']) => ({
  paid: 'Paid in ETS', partially_paid: 'Partially paid in ETS', unpaid: 'Unpaid in ETS', unverified: 'Payment unverified',
})[status]

export function importedBillingSeverity(billing?: ImportedBilling | null, failed = false) {
  const status = !failed && billing ? billing.payment_status : 'unverified'
  const label = importedPaymentLabel(status)
  const remaining = importedMoney(status === 'unverified' ? null : billing?.recorded_remaining_amount)
  const amountsAvailable = importedMoney(billing?.total_amount) !== 'Unavailable'
    && importedMoney(billing?.recorded_completed_amount) !== 'Unavailable'
  const healthy = !failed && status === 'paid' && !billing?.review_required && amountsAvailable && remaining === '$0.00'
  const description = failed ? 'Billing unavailable'
    : billing?.review_required ? `Review needed · ${label}`
      : status === 'unverified' ? label
        : `${label} · ${remaining === 'Unavailable' ? 'Balance unavailable' : !amountsAvailable ? 'Payment details unavailable' : `Remaining ${remaining}`}`
  const heading = failed ? 'Billing unavailable' : billing?.review_required ? 'Review needed'
    : status === 'unverified' ? label : remaining === 'Unavailable' ? 'Balance unavailable'
      : !amountsAvailable ? 'Payment details unavailable' : healthy ? 'Payment verified' : 'Payment remaining'
  return { tone: healthy ? 'healthy' : 'warning', description, heading, remaining } as const
}

export function useImportedBilling(orderId: string | undefined, enabled: boolean) {
  const user = useAuthStore(state => state.user)
  const epoch = useAuthStore(state => state.authSessionEpoch)
  const logout = useAuthStore(state => state.logoutInProgress)
  return useQuery({
    queryKey: ['imported-billing', user?.tenant_id, user?.id, user?.role, epoch, orderId],
    queryFn: async ({ signal }) => {
      const response = await api.get<ImportedBilling>(`/repair-orders/${orderId}/imported-billing`, { signal })
      if (response.data.source !== 'easy_truck_shop_import' || !['imported_records', 'ets_source_snapshot'].includes(response.data.evidence_basis)) {
        throw new Error('Imported billing evidence unavailable')
      }
      return response.data
    },
    enabled: enabled && Boolean(orderId && user?.tenant_id && user?.id) && !logout,
    retry: false,
    staleTime: 0,
  })
}

export function importedMoney(value?: string | null) {
  if (typeof value !== 'string' || !/^\d+(?:\.\d{1,2})?$/.test(value)) return 'Unavailable'
  const [whole, fraction = ''] = value.split('.')
  const normalized = whole.replace(/^0+(?=\d)/, '')
  return `$${normalized.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${fraction.padEnd(2, '0')}`
}
