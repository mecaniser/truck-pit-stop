import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import SlidePanelForm from '@/components/SlidePanelForm'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { pricingError, pricingMoney } from './contract'
import { enteredMoney, policySchema, type InventoryPricingPolicy } from './configuration'
import { isPricingScopeCurrent, usePricingScope } from './usePricingScope'
import './parts-pricing.css'
function Editor({ inventoryId, name, onClose, onSaved, scope }: { scope: string; inventoryId: string; name: string; onClose: () => void; onSaved?: () => void }) {
  const queryClient = useQueryClient()
  const [policy, setPolicy] = useState<InventoryPricingPolicy | null>(null)
  const [fresh, setFresh] = useState<InventoryPricingPolicy | null>(null)
  const [floor, setFloor] = useState(''); const [minimum, setMinimum] = useState(''); const [fixed, setFixed] = useState(false); const [selling, setSelling] = useState('')
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null); const [loaded, setLoaded] = useState(false)
  const controller = useRef(new AbortController()); const attempt = useRef<{ body: string; id: string } | null>(null)
  const active = () => !controller.current.signal.aborted && isPricingScopeCurrent(scope)
  const read = async () => {
    const result = policySchema.parse((await api.get(`/parts-pricing/inventory/${inventoryId}/pricing-policy`, { signal: controller.current.signal })).data).policy
    if (result.inventory_id !== inventoryId) throw new Error('Invalid part identity')
    return result
  }
  useEffect(() => {
    controller.current = new AbortController()
    const abort = controller.current
    void read().then(result => { if (!abort.signal.aborted && isPricingScopeCurrent(scope)) { setPolicy(result); setFloor(result.pricing_cost_floor ?? ''); setMinimum(result.minimum_sale_price ?? ''); setFixed(result.fixed_sales_price); setSelling(result.selling_price); setLoaded(true) } }).catch(cause => { if (!abort.signal.aborted && isPricingScopeCurrent(scope)) setError(pricingError(cause, 'Pricing policy could not be loaded.')) })
    return () => abort.abort()
    // The scoped parent remounts for every actor/session/inventory change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const save = async () => {
    if (!policy || fresh || busy) return
    setBusy(true); setError(null)
    try {
      const body = { expected_pricing_version: policy.pricing_version, pricing_cost_floor: enteredMoney(floor), minimum_sale_price: enteredMoney(minimum), fixed_sales_price: fixed, selling_price: enteredMoney(selling) }
      if (body.selling_price === null) throw new Error('Catalog price is required.')
      const key = JSON.stringify(body); const id = attempt.current?.body === key ? attempt.current.id : crypto.randomUUID(); attempt.current = { body: key, id }
      const next = policySchema.parse((await api.patch(`/parts-pricing/inventory/${inventoryId}/pricing-policy`, body, { signal: controller.current.signal, headers: { 'Idempotency-Key': id }, skipAuthRefresh: true })).data).policy
      if (next.inventory_id !== inventoryId) throw new Error('Invalid part identity')
      if (active()) { attempt.current = null; void queryClient.invalidateQueries({ queryKey: ['part-policy-summary'] }); onSaved?.(); onClose() }
    } catch (cause) {
      if (!active()) return
      const conflict = (cause as { response?: { status?: number } }).response?.status === 409
      if (conflict) { attempt.current = null; try { const fresh = await read(); if (active()) setFresh(fresh) } catch { if (active()) setPolicy(null) } }
      if (!active()) return
      setError(`${pricingError(cause, cause instanceof Error ? cause.message : 'Policy could not be saved.')}${conflict ? ' Your draft is kept. Review the current version and save again.' : ''}`)
    } finally { if (active()) setBusy(false) }
  }
  return <SlidePanelForm portalToShell isOpen title="Part pricing" category={name} panelClassName="db-parts-pricing" overlayClassName="db-parts-pricing-overlay" width="sm:w-[500px]" onClose={() => { if (!busy) onClose() }} onSubmit={event => { event.preventDefault(); void save() }} isSubmitting={busy} submitLabel="Save policy" submitDisabled={!policy || !loaded || Boolean(fresh)}>
    {error && <p role="alert">{error}</p>}{fresh && <div className="db-parts-pricing__confirm"><strong>Current saved policy</strong><p>Catalog {pricingMoney(fresh.selling_price)} · Cost floor {pricingMoney(fresh.pricing_cost_floor)} · Sale minimum {pricingMoney(fresh.minimum_sale_price)} · {fresh.fixed_sales_price ? 'Fixed' : 'Shop pricing'}</p><button type="button" onClick={() => { setPolicy(fresh); setFresh(null); setError(null) }}>Keep my draft against this version</button><button type="button" onClick={() => { setPolicy(fresh); setFloor(fresh.pricing_cost_floor ?? ''); setMinimum(fresh.minimum_sale_price ?? ''); setFixed(fresh.fixed_sales_price); setSelling(fresh.selling_price); setFresh(null); setError(null) }}>Load saved values</button></div>}{!loaded && !error && <p role="status">Loading pricing…</p>}{loaded && <><p className="db-parts-pricing__muted">Actual cost {policy?.actual_cost_known ? pricingMoney(policy.actual_unit_cost) : 'Unknown'}</p><div className="db-parts-pricing__fields"><label>Pricing cost floor<input inputMode="decimal" placeholder="None" value={floor} disabled={busy} onChange={event => setFloor(event.target.value)} /></label><label>Minimum sale price<input inputMode="decimal" placeholder="None" value={minimum} disabled={busy} onChange={event => setMinimum(event.target.value)} /></label><label>Catalog price<input inputMode="decimal" value={selling} disabled={busy} onChange={event => setSelling(event.target.value)} /></label><label className="db-parts-pricing__check"><input type="checkbox" checked={fixed} disabled={busy} onChange={event => setFixed(event.target.checked)} />Fixed sales price</label></div><p className="db-parts-pricing__muted">Cost floor sets the markup basis; sale minimum limits the charge. Blank leaves either unset. Saved lines keep their prices.</p></>}
  </SlidePanelForm>
}
export default function PartPricingPolicy(props: { inventoryId: string; name: string; onClose: () => void; onSaved?: () => void }) {
  const scope = usePricingScope(); const role = useAuthStore(state => state.user?.role)
  if (role !== 'garage_owner' && role !== 'garage_admin') return null
  return <Editor key={`${scope}:${props.inventoryId}`} scope={scope} {...props} />
}
