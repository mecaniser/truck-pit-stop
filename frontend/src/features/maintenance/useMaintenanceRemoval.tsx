import { useEffect, useRef, useState } from 'react'
import api from '@/lib/api'
import { useQueryClient } from '@tanstack/react-query'
import SlidePanelForm from '@/components/SlidePanelForm'
import PricingFeedback from '@/features/parts-pricing/PricingFeedback'
import { isPricingScopeCurrent, usePricingScope } from '@/features/parts-pricing/usePricingScope'
import { errorDetail, invalidateMaintenance, maintenanceError, MaintenanceCancelled } from './api'
import { orderMaintenanceSchema, type OrderMaintenance } from './contract'
import './maintenance.css'

type Removal = { orderId: string; lineId: string; label: string; message?: string; data: OrderMaintenance; send: (fingerprint?: string) => Promise<unknown>; resolve: (value: unknown) => void; reject: (error: unknown) => void }
export function useMaintenanceRemoval(context: string) {
  const client = useQueryClient()
  const scope = usePricingScope(); const identity = `${scope}:${context}`; const live = useRef(identity); live.current = identity
  const [removal, setRemoval] = useState<Removal | null>(null); const current = useRef<Removal | null>(null); const controller = useRef(new AbortController())
  useEffect(() => { const active = new AbortController(); controller.current = active; setRemoval(null); return () => { active.abort(); current.current?.reject(new MaintenanceCancelled()); current.current = null } }, [identity])
  const execute = async <T,>(orderId: string, lineId: string, name: string, send: (fingerprint?: string) => Promise<T>, message?: string): Promise<T> => {
    const signal = controller.current.signal; const captured = identity
    const active = () => !signal.aborted && captured === live.current && isPricingScopeCurrent(scope)
    const read = async () => { if (!active()) throw new MaintenanceCancelled(); let raw: unknown; try { raw = (await api.get(`/repair-orders/${orderId}/maintenance`, { signal })).data } catch (failure) { if (!active()) throw new MaintenanceCancelled(); throw failure } if (!active()) throw new MaintenanceCancelled(); const data = orderMaintenanceSchema.parse(raw); if (data.repair_order_id !== orderId) throw new Error('Invalid maintenance removal scope.'); return data }
    let data = await read()
    if (!data.links.some(link => link.operation_ids.includes(lineId)) && !message) {
      try { const result = await send(); if (!active()) throw new MaintenanceCancelled(); invalidateMaintenance(client); return result }
      catch (failure) { if (errorDetail(failure)?.code !== 'maintenance_preview_changed') throw failure; data = await read() }
    }
    return new Promise<T>((resolve, reject) => { const entry: Removal = { orderId, lineId, label: name, message, data, send: async token => { if (!active()) throw new MaintenanceCancelled(); const result = await send(token); if (!active()) throw new MaintenanceCancelled(); invalidateMaintenance(client); return result }, resolve: value => resolve(value as T), reject }; current.current = entry; setRemoval(entry) })
  }
  const close = (entry: Removal) => { if (current.current !== entry) return; entry.reject(new MaintenanceCancelled()); current.current = null; setRemoval(null) }
  return { execute, dialog: removal && <RemovalPanel key={`${identity}:${removal.lineId}`} removal={removal} onCancel={() => close(removal)} onDone={value => { if (current.current !== removal) return; removal.resolve(value); current.current = null; setRemoval(null) }} /> }
}
// The command owns its modal and its promise lifecycle.
// eslint-disable-next-line react-refresh/only-export-components
function RemovalPanel({ removal, onCancel, onDone }: { removal: Removal; onCancel: () => void; onDone: (value: unknown) => void }) {
  const scope = usePricingScope(); const [data, setData] = useState(removal.data); const [error, setError] = useState<{ message: string } | null>(null); const [busy, setBusy] = useState(false); const [verified, setVerified] = useState(true)
  const controller = useRef(new AbortController()); useEffect(() => { const current = new AbortController(); controller.current = current; return () => current.abort() }, [])
  const active = () => !controller.current.signal.aborted && isPricingScopeCurrent(scope)
  const affected = data.links.filter(link => link.operation_ids.includes(removal.lineId))
  const reload = async () => { try { const next = orderMaintenanceSchema.parse((await api.get(`/repair-orders/${removal.orderId}/maintenance`, { signal: controller.current.signal })).data); if (!active()) return; if (next.repair_order_id !== removal.orderId) throw new Error('Invalid maintenance removal scope.'); setData(next); setVerified(true) } catch (failure) { if (active()) { setVerified(false); setError({ message: maintenanceError(failure) }) } } }
  const submit = async () => { setBusy(true); setError(null); try { onDone(await removal.send(affected.length ? data.expected_review_fingerprint : undefined)) } catch (failure) { if (failure instanceof MaintenanceCancelled) { onCancel(); return } if (active()) { setError({ message: maintenanceError(failure) }); if (errorDetail(failure)?.code === 'maintenance_preview_changed') { setVerified(false); await reload() } } } finally { if (active()) setBusy(false) } }
  return <SlidePanelForm isOpen portalToShell title="Remove work" panelClassName="db-maintenance db-maintenance__dialog" onClose={() => { if (!busy) onCancel() }} onSubmit={event => { event.preventDefault(); void submit() }} isSubmitting={busy} submitDisabled={!verified} submitLabel="Remove work"><p>{removal.message || `Remove ${removal.label}?`}</p>{affected.length > 0 && <><p>This releases the covered maintenance cycles:</p><ul>{affected.map(link => <li key={link.work_link_id}>{data.programs.find(program => program.work?.work_link_id === link.work_link_id)?.name ?? 'Maintenance program'} · cycle {link.cycle} · {link.state}</li>)}</ul></>}{error && <PricingFeedback revision={error}>{error.message} <button type="button" disabled={busy} onClick={() => void reload()}>Reload affected work</button></PricingFeedback>}</SlidePanelForm>
}
