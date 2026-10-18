import { emptyAttestation, toAttestation } from './attestation'
import { useEffect, useRef, useState } from 'react'
import api from '@/lib/api'
import { useQueryClient } from '@tanstack/react-query'
import SlidePanelForm from '@/components/SlidePanelForm'
import PricingFeedback from '@/features/parts-pricing/PricingFeedback'
import { isPricingScopeCurrent, usePricingScope } from '@/features/parts-pricing/usePricingScope'
import { AttestationFields, TargetReview } from './MaintenanceFields'
import { errorDetail, invalidateMaintenance, maintenanceError, MaintenanceCancelled, scopedProgram, useMaintenanceCommand } from './api'
import { orderMaintenanceSchema, parseTargetPreview, refFor, type Channel, type CompletionEntry, type MaintenanceReview, type OrderMaintenance, type TargetPreview, type TargetRequest } from './contract'
import './maintenance.css'

type Pending = { orderId: string; vehicleId: string; channel: Channel; submitLabel: string; data: OrderMaintenance; send: (review?: MaintenanceReview) => Promise<unknown>; resolve: (value: unknown) => void; reject: (failure: unknown) => void }
export function useMaintenanceFinalization(context: string, submitLabel = 'Finalize & Send Invoice') {
  const client = useQueryClient()
  const scope = usePricingScope(); const identity = `${scope}:${context}`
  const live = useRef(identity); live.current = identity
  const [pending, setPending] = useState<Pending | null>(null); const pendingRef = useRef<Pending | null>(null)
  const controller = useRef(new AbortController())
  useEffect(() => { const current = new AbortController(); controller.current = current; setPending(null); return () => { current.abort(); pendingRef.current?.reject(new MaintenanceCancelled()); pendingRef.current = null } }, [identity])
  const execute = async <T,>(orderId: string, vehicleId: string, channel: Channel, send: (review?: MaintenanceReview) => Promise<T>): Promise<T> => {
    const signal = controller.current.signal; const captured = identity
    const active = () => !signal.aborted && live.current === captured && isPricingScopeCurrent(scope)
    if (!active()) throw new MaintenanceCancelled()
    let raw: unknown
    try { raw = (await api.get(`/repair-orders/${orderId}/maintenance`, { signal, params: { channel } })).data } catch (failure) { if (!active()) throw new MaintenanceCancelled(); throw failure }
    if (!active()) throw new MaintenanceCancelled()
    const data = orderMaintenanceSchema.parse(raw)
    if (data.repair_order_id !== orderId) throw new Error('Invalid order maintenance response.')
    data.programs.forEach(program => scopedProgram(program, vehicleId))
    if (!data.links.some(link => link.state === 'active')) { const result = await send(); if (!active()) throw new MaintenanceCancelled(); invalidateMaintenance(client); return result }
    return new Promise<T>((resolve, reject) => {
      const entry: Pending = { orderId, vehicleId, channel, submitLabel, data, send: async review => { if (!active()) throw new MaintenanceCancelled(); const result = await send(review); if (!active()) throw new MaintenanceCancelled(); invalidateMaintenance(client); return result }, resolve: value => resolve(value as T), reject }
      pendingRef.current = entry; setPending(entry)
    })
  }
  const close = (entry: Pending) => { if (pendingRef.current !== entry) return; entry.reject(new MaintenanceCancelled()); pendingRef.current = null; setPending(null) }
  return { execute, dialog: pending && <FinalizationPanel key={`${identity}:${pending.orderId}`} pending={pending} onCancel={() => close(pending)} onDone={value => { if (pendingRef.current !== pending) return; pending.resolve(value); pendingRef.current = null; setPending(null) }} /> }
}
// The command owns its modal and its promise lifecycle.
// eslint-disable-next-line react-refresh/only-export-components
function FinalizationPanel({ pending, onCancel, onDone }: { pending: Pending; onCancel: () => void; onDone: (value: unknown) => void }) {
  const [order, setOrder] = useState(pending.data); const [selected, setSelected] = useState<string[]>([]); const [attestation, setAttestation] = useState(emptyAttestation)
  const [preview, setPreview] = useState<TargetPreview | null>(null); const [error, setError] = useState<{ message: string } | null>(null); const [saving, setSaving] = useState(false)
  const scope = usePricingScope(); const controller = useRef(new AbortController()); useEffect(() => { const current = new AbortController(); controller.current = current; return () => current.abort() }, [])
  const active = () => !controller.current.signal.aborted && isPricingScopeCurrent(scope)
  const command = useMaintenanceCommand(`${pending.vehicleId}:${pending.orderId}:completion`)
  const attempt = useRef<{ semantic: string; id: string } | null>(null)
  const entries = (): CompletionEntry[] => order.links.filter(link => link.state === 'active').map(link => {
    const program = order.programs.find(program => program.work?.work_link_id === link.work_link_id)
    if (!program) throw new Error('Reload maintenance review before finalizing.')
    return { work_link_id: link.work_link_id, expected_link_version: link.version, program: refFor(program), attestation: selected.includes(program.id) ? toAttestation(attestation) : null }
  })
  const request = (): Extract<TargetRequest, { purpose: 'completion' }> => ({ purpose: 'completion', channel: pending.channel, repair_order_id: pending.orderId, expected_review_fingerprint: order.expected_review_fingerprint, entries: entries() })
  const review = async () => { try { setError(null); const body = request(); setPreview(await command.run(`/vehicles/${pending.vehicleId}/maintenance-target-preview`, body, raw => parseTargetPreview(raw, body), 'post', true)) } catch (failure) { if (!(failure instanceof MaintenanceCancelled)) setError({ message: maintenanceError(failure) }) } }
  const reload = async () => { try { const next = orderMaintenanceSchema.parse((await api.get(`/repair-orders/${pending.orderId}/maintenance`, { signal: controller.current.signal, params: { channel: pending.channel } })).data); if (!active()) return; if (next.repair_order_id !== pending.orderId) throw new Error('Invalid maintenance review'); next.programs.forEach(program => scopedProgram(program, pending.vehicleId)); setOrder(next); setPreview(null); setError(null) } catch (failure) { if (active()) setError({ message: maintenanceError(failure) }) } }
  const finish = async () => {
    if (!preview || saving) return
    setSaving(true); setError(null)
    try { const body = request(); const semantic = JSON.stringify(body.entries); if (attempt.current?.semantic !== semantic) attempt.current = { semantic, id: crypto.randomUUID() }; const result = await pending.send({ request_id: attempt.current.id, expected_review_fingerprint: order.expected_review_fingerprint, expected_target_fingerprint: preview.expected_target_fingerprint, entries: body.entries }); onDone(result) }
    catch (failure) { if (failure instanceof MaintenanceCancelled) { onCancel(); return } setError({ message: maintenanceError(failure) }); const fresh = errorDetail(failure)?.preview; if (fresh) { try { setPreview(parseTargetPreview(fresh, request())) } catch { setPreview(null) } } }
    finally { setSaving(false) }
  }
  return <SlidePanelForm isOpen onClose={() => { if (!saving && !command.busy) onCancel() }} title="Review maintenance completion" panelClassName="db-maintenance db-maintenance__dialog" portalToShell submitLabel={pending.submitLabel} onSubmit={event => { event.preventDefault(); void finish() }} isSubmitting={saving || command.busy} submitDisabled={!preview}>
    <p>Unchecked programs keep their targets until actual service readings are recorded.</p>
    {order.programs.filter(program => order.links.some(link => link.state === 'active' && program.work?.work_link_id === link.work_link_id)).map(program => <label key={program.id} className="db-maintenance__check"><input type="checkbox" disabled={!order.can_record_evidence || saving || command.busy} checked={selected.includes(program.id)} onChange={event => { setSelected(current => event.target.checked ? [...current, program.id] : current.filter(id => id !== program.id)); setPreview(null) }} />{program.name}{program.mode === 'legacy' ? ` · ${(program.legacy_package ?? []).map(service => service.name).join(' + ')}` : ''}</label>)}
    {selected.length > 0 && <AttestationFields value={attestation} disabled={saving || command.busy} source={{ kind: 'repair_order', id: pending.orderId }} onChange={value => { setAttestation(value); setPreview(null) }} />}
    <button type="button" disabled={saving || command.busy} onClick={() => void review()}>Review targets</button>{preview && <TargetReview preview={preview} names={Object.fromEntries(order.programs.map(program => [program.id, program.name]))} />}
    {error && <PricingFeedback revision={error}>{error.message} <button type="button" disabled={saving || command.busy} onClick={() => void reload()}>Reload review</button></PricingFeedback>}
  </SlidePanelForm>
}
