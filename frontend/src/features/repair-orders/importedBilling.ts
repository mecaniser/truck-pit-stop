import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'

export type ImportedBilling = {
  source: 'easy_truck_shop_import'
  evidence_basis: 'imported_records' | 'ets_source_snapshot'
  reconciliation_status: 'not_checked'
  invoice_id?: string | null
  invoice_number?: string | null
  total_amount?: string | null
  recorded_completed_amount?: string | null
  recorded_remaining_amount?: string | null
  payment_status: 'paid' | 'partially_paid' | 'unpaid' | 'unverified'
  observed_at?: string | null
  review_required: boolean
  review_reasons: string[]
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
