import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { isPricingScopeCurrent, usePricingScope } from '@/features/parts-pricing/usePricingScope'
import { pricingMoney } from '@/features/parts-pricing/contract'
import PricingFeedback from '@/features/parts-pricing/PricingFeedback'
import { parseIntake, policySourceLabel, type IntakePricing } from './contract'
import '@/features/customers/customer-pricing.css'

function IntakePricingSummary({ preview }: { preview: IntakePricing }) {
  if (preview.policy_kind === 'internal') return <span>Internal pricing</span>
  if (preview.projection === 'fleet') return <span>{preview.agreement_applies ? 'Account pricing applies' : 'Shop pricing applies'}</span>
  return <span>Labor {pricingMoney(preview.labor.rate)}/hr · {policySourceLabel(preview.labor.source)}<br />Parts · {policySourceLabel(preview.parts.source)} {preview.parts.mode === 'matrix' ? 'matrix' : 'catalog'}</span>
}

/** Reads only the caller's safe projection; a changed quote requires a deliberate acceptance. */
export function useIntakePricing(customerId: string | null | undefined, vehicleId: string | null | undefined, enabled: boolean, projection: 'shop' | 'fleet' = 'shop') {
  const scope = usePricingScope(); const client = useQueryClient(); const role = useAuthStore(state => state.user?.role)
  const identity = JSON.stringify([scope, customerId, vehicleId ?? null, projection, enabled])
  const currentIdentity = useRef(identity); currentIdentity.current = identity
  const [conflict, setConflict] = useState<{ identity: string; preview: IntakePricing; onAccepted?: () => void } | null>(null)
  const allowed = ['garage_owner', 'garage_admin', 'receptionist', 'fleet_manager'].includes(role ?? '') && (role !== 'fleet_manager' || projection === 'fleet')
  const active = enabled && Boolean(customerId) && allowed
  const queryKey = ['customer-pricing-intake', scope, customerId, vehicleId ?? null, projection]
  const query = useQuery({ queryKey, enabled: active, queryFn: async ({ signal }) => parseIntake((await api.get(`/customers/${customerId}/pricing-preview`, { signal, params: { pricing_presentation: projection, ...(vehicleId ? { vehicle_id: vehicleId } : {}) } })).data, customerId!, vehicleId ?? null, projection), gcTime: 0, staleTime: Infinity, retry: false, refetchOnWindowFocus: false })
  useEffect(() => {
    setConflict(current => current?.identity === identity ? current : null)
    if (!active) client.removeQueries({ queryKey: ['customer-pricing-intake', scope, customerId, vehicleId ?? null, projection] })
  }, [active, scope, customerId, vehicleId, projection, client, identity])
  useEffect(() => () => { client.removeQueries({ queryKey: ['customer-pricing-intake', scope] }) }, [client, scope])
  const changed = conflict?.identity === identity ? conflict : null
  const preview = active ? changed?.preview ?? (!query.isError ? query.data : undefined) : undefined
  const ready = !active || Boolean(preview && !changed)
  const handleConflict = (failure: unknown, submitted?: { customerId: string; vehicleId: string }, onAccepted?: () => void) => {
    const detail = (failure as { response?: { data?: { detail?: { code?: string; preview?: unknown } } } }).response?.data?.detail
    const targetCustomer = submitted?.customerId ?? customerId
    const targetVehicle = submitted?.vehicleId ?? vehicleId ?? null
    const targetIdentity = JSON.stringify([scope, targetCustomer, targetVehicle, projection, enabled])
    // A standard intake may have just created the customer/truck before its RO
    // write. Only that exact submitted context may replace the reviewed scope.
    if (detail?.code !== 'account_pricing_changed' || !enabled || !allowed || !targetCustomer || (currentIdentity.current !== identity && currentIdentity.current !== targetIdentity) || !isPricingScopeCurrent(scope)) return false
    try { setConflict({ identity: targetIdentity, preview: parseIntake(detail.preview, targetCustomer, targetVehicle, projection), onAccepted }); return true } catch { return false }
  }
  const confirmation = () => {
    if (!isPricingScopeCurrent(scope) || (active && !ready)) throw new Error('Review the account pricing before creating the order.')
    return preview ? { expected_pricing_policy: preview.expected_pricing_policy, pricing_presentation: preview.projection } : {}
  }
  const notice = active ? <div className="db-account-pricing-notice">
    {changed ? <PricingFeedback revision={changed}><IntakePricingSummary preview={changed.preview} /><div>Account pricing changed. <button type="button" onClick={() => { if (currentIdentity.current !== identity || !isPricingScopeCurrent(scope)) return; client.setQueryData(queryKey, changed.preview); setConflict(null); changed.onAccepted?.() }}>Use current defaults</button></div></PricingFeedback> : preview ? <IntakePricingSummary preview={preview} /> : query.isError ? <p role="alert">Account pricing unavailable. <button type="button" onClick={() => void query.refetch()}>Retry pricing</button></p> : <p role="status">Loading account pricing…</p>}
  </div> : null
  return { preview, ready, notice, confirmation, handleConflict }
}
