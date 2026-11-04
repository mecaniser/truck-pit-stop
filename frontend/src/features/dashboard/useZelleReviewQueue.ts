import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { getAuthenticatedSessionIdentity, useAuthStore } from '@/stores/authStore'

export interface ZelleReviewRow {
  kind: 'canonical_zelle_attempt' | 'legacy_zelle_submission'
  invoice_id: string
  repair_order_id: string | null
  display_invoice_number: string
  customer_id: string
  customer_display_name: string
  principal_amount: string
  attempt_id: string | null
  settlement_id: string | null
  settlement_version: number | null
  created_at: string
  reported_at: string | null
  report_status: 'explicit_report' | 'legacy_report' | 'unverified_request'
  review_mode: 'canonical_attempt' | 'legacy_invoice'
  can_confirm: boolean
}
interface QueuePage { rows: ZelleReviewRow[]; next_cursor: string | null }

export function useZelleReviewQueue() {
  const identity = useAuthStore(getAuthenticatedSessionIdentity)
  const user = useAuthStore(state => state.user)
  const allowed = !!identity && (user?.role === 'garage_owner' || (user?.role === 'garage_admin' && user.permissions?.payments === true))
  const query = useQuery({
    queryKey: ['zelle-review-queue', identity, allowed], enabled: allowed, retry: false, refetchInterval: 60000,
    queryFn: async ({ signal }) => {
      const rows: ZelleReviewRow[] = []
      const seen = new Set<string>()
      let cursor: string | null = null
      for (let page = 0; page < 50; page++) {
        signal.throwIfAborted()
        const result: QueuePage = (await api.get<QueuePage>('/payments/zelle-review-queue', { params: { limit: 100, ...(cursor ? { cursor } : {}) }, signal })).data
        signal.throwIfAborted()
        if (!Array.isArray(result.rows)) throw new Error('Payment review unavailable')
        rows.push(...result.rows)
        if (!result.next_cursor) return [...new Map(rows.map(row => [row.attempt_id ? `attempt:${row.attempt_id}` : `legacy:${row.invoice_id}`, row])).values()]
        if (seen.has(result.next_cursor)) throw new Error('Payment review incomplete')
        seen.add(result.next_cursor); cursor = result.next_cursor
      }
      throw new Error('Payment review incomplete')
    },
  })
  return { ...query, allowed, identity, rows: allowed && !query.isError ? query.data || [] : [] }
}
export type ZelleReviewQueueState = ReturnType<typeof useZelleReviewQueue>

