import { ControlInput } from '@/components/ui/Controls'
import { useEffect, useRef, useState } from 'react'
import { z } from 'zod'
import SlidePanelForm from '@/components/SlidePanelForm'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { PricingCancelled } from './contract'
import { usePricingCommand } from './usePricingCommand'
import { usePricingScope } from './usePricingScope'
import './parts-pricing.css'
export type AdHocPartInput = { name: string; sku: string | null; quantity: number; unit_price: number; unit_cost: number | null; source_line_id: string | null }
const matchSchema = z.object({ id: z.string().min(1), sku: z.string(), name: z.string() }).strict()
type Match = z.infer<typeof matchSchema>
export function useAdHocPartCommand(orderId: string, presentation: 'shop' | 'fleet' = 'shop', internal = false) {
  const scope = usePricingScope()
  const current = useRef(scope); current.current = scope
  const user = useAuthStore(state => state.user)
  const pricing = usePricingCommand(`ad-hoc:${orderId}`)
  const abort = useRef<AbortController | null>(null)
  const pending = useRef(false)
  const retry = useRef<{ key: string; id: string } | null>(null)
  const awaiting = useRef<{ accept: (value: { manual: boolean; reason: string }) => void; cancel: () => void } | null>(null)
  const [match, setMatch] = useState<Match | null>(null)
  const [manual, setManual] = useState(false)
  const [reason, setReason] = useState('')
  const manager = presentation === 'shop' && !internal && ['garage_owner', 'garage_admin', 'receptionist'].includes(user?.role ?? '')
  useEffect(() => {
    setMatch(null); retry.current = null; pending.current = false
    return () => { abort.current?.abort(); awaiting.current?.cancel(); awaiting.current = null; retry.current = null }
  }, [scope, orderId])
  const execute = async (body: AdHocPartInput) => {
    if (pending.current) throw new PricingCancelled()
    const owner = scope; const actor = useAuthStore.getState(); const controller = new AbortController(); abort.current = controller
    const active = () => { const next = useAuthStore.getState(); return current.current === owner && !controller.signal.aborted && !next.logoutInProgress && next.authSessionEpoch === actor.authSessionEpoch && next.user?.tenant_id === actor.user?.tenant_id && next.user?.id === actor.user?.id && next.user?.role === actor.user?.role }
    if (!actor.user?.tenant_id || !active()) throw new PricingCancelled()
    pending.current = true
    const key = JSON.stringify(body); const id = retry.current?.key === key ? retry.current.id : crypto.randomUUID(); retry.current = { key, id }
    try {
      const response = await api.post(`/repair-orders/${orderId}/parts/ad-hoc`, { ...body, pricing_presentation: presentation }, { signal: controller.signal, headers: { 'Idempotency-Key': id }, skipAuthRefresh: true })
      if (!active()) throw new PricingCancelled()
      retry.current = null; return response.data
    } catch (cause) {
      if (!active()) throw new PricingCancelled()
      const response = (cause as { response?: { status?: number; data?: { detail?: { code?: string; inventory?: unknown } } } }).response
      if (response?.status !== 409 || response.data?.detail?.code !== 'catalog_match_requires_preview') throw cause
      const item = matchSchema.parse(response.data.detail.inventory)
      retry.current = null; setManual(false); setReason(''); setMatch(item)
      const choice = await new Promise<{ manual: boolean; reason: string }>((resolve, reject) => { awaiting.current = { accept: resolve, cancel: () => reject(new PricingCancelled()) } })
      awaiting.current = null; setMatch(null)
      if (!active()) throw new PricingCancelled()
      const line = { client_key: `matched:${item.id}`, inventory_id: item.id, quantity: String(body.quantity), source_line_id: body.source_line_id, pricing_intent: choice.manual && manager ? 'manual' as const : 'default' as const, ...(choice.manual && manager ? { unit_price: body.unit_price.toFixed(2), price_override_reason: choice.reason } : {}) }
      return await pricing.execute({ context: { kind: 'repair_order', repair_order_id: orderId }, plan: { kind: 'parts_add', lines: [line] }, pricing_presentation: presentation }, async (confirmation, options) => (await api.post(`/repair-orders/${orderId}/parts`, { ...line, quantity: body.quantity, ...confirmation }, options)).data, body, true)
    } finally { if (active()) { pending.current = false; setMatch(null); awaiting.current = null } }
  }
  return { execute, dialog: <>{pricing.dialog}{match && <SlidePanelForm portalToShell isOpen={Boolean(match)} title="Part already in catalog" category="Parts pricing" panelClassName="db-parts-pricing" overlayClassName="db-parts-pricing-overlay" width="sm:w-[480px]" onClose={() => awaiting.current?.cancel()} onSubmit={event => { event.preventDefault(); awaiting.current?.accept({ manual, reason: reason.trim() }) }} submitLabel="Review catalog price" submitDisabled={manual && reason.trim().length < 3}>
    {match && <><strong>{match.name}</strong><p className="db-parts-pricing__muted">{match.sku} · Your entered draft is kept.</p>{manager && <><label className="db-parts-pricing__check"><input type="checkbox" checked={manual} onChange={event => setManual(event.target.checked)} />Keep my entered price</label>{manual && <label>Override reason<ControlInput value={reason} maxLength={500} onChange={event => setReason(event.target.value)} /></label>}</>}</>}
  </SlidePanelForm>}</> }
}
