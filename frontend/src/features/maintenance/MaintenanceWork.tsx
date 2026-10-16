import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { usePricingScope } from '@/features/parts-pricing/usePricingScope'
import { pricingMoney } from '@/features/parts-pricing/contract'
import PricingFeedback from '@/features/parts-pricing/PricingFeedback'
import { operationPageSchema } from '@/features/operation-execution/queries'
import { errorDetail, maintenanceError, MaintenanceCancelled, scopedProgram, useMaintenanceCommand } from './api'
import { parseWorkPreview, programServices, refFor, workMutationSchema, type Channel, type CoverageGroup, type Program, type WorkPreview, type WorkRequest } from './contract'

export default function MaintenanceWork({ vehicleId, channel, programs, customerId, onDone, onCancel }: { vehicleId: string; channel: Channel; programs: Program[]; customerId?: string; onDone: (orderId: string) => void; onCancel: () => void }) {
  const scope = usePricingScope(); const command = useMaintenanceCommand(`${vehicleId}:work`)
  const [targetId, setTargetId] = useState(''); const [payer, setPayer] = useState(customerId ?? ''); const [description, setDescription] = useState('')
  const [operations, setOperations] = useState<Record<string, string>>({}); const [preview, setPreview] = useState<WorkPreview | null>(null)
  const [error, setError] = useState<{ message: string } | null>(null); const [stockAccepted, setStockAccepted] = useState(false)
  const groups = useMemo(() => { const result = new Map<string, { service: ReturnType<typeof programServices>[number]; programs: Program[] }>(); for (const program of programs) for (const service of programServices(program)) { const group = result.get(service.id); if (group) { if (!group.programs.some(item => item.id === program.id)) group.programs.push(program) } else result.set(service.id, { service, programs: [program] }) } return [...result.values()] }, [programs])
  const orders = useQuery({ queryKey: ['maintenance-drafts', scope, vehicleId, channel], gcTime: 0, retry: false, queryFn: async ({ signal }) => { const response = await api.get<{ items: { id: string; vehicle_id: string; order_number: string; status: string }[] }>('/repair-orders', { signal, params: { vehicle_id: vehicleId, status: 'draft', paginated: true, limit: 100, pricing_presentation: channel } }); if (!Array.isArray(response.data.items) || response.data.items.some(order => order.vehicle_id !== vehicleId)) throw new Error('Invalid truck work response'); return response.data.items.filter(order => order.status === 'draft') } })
  const payers = useQuery({ queryKey: ['maintenance-payers', scope, vehicleId], enabled: !customerId && !targetId, gcTime: 0, retry: false, queryFn: async ({ signal }) => { const result = (await api.get<{ customer_id: string; customer_company_name: string | null; effective_to: string | null }[]>(`/vehicles/${vehicleId}/relationships`, { signal })).data; if (!Array.isArray(result)) throw new Error('Payers unavailable'); return result.filter(item => !item.effective_to) } })
  const existing = useQuery({ queryKey: ['maintenance-operations', scope, targetId, channel], enabled: Boolean(targetId), gcTime: 0, retry: false, queryFn: async ({ signal }) => {
    const [summary, execution] = await Promise.all([api.get<{ lines: { id: string; source_service_id: string | null; description: string }[] }>(`/repair-orders/${targetId}/price-build`, { signal, params: { pricing_presentation: channel } }), api.get(`/repair-orders/${targetId}/operations`, { signal })])
    const state = operationPageSchema.parse(execution.data)
    if (!Array.isArray(summary.data.lines)) throw new Error('Operations unavailable')
    return summary.data.lines.flatMap(line => { const operation = state.items.find(item => item.labor_id === line.id); return operation && operation.status !== 'completed' && !operation.active_session ? [{ ...line, version: operation.version }] : [] })
  } })
  const changed = () => { setPreview(null); setError(null); setStockAccepted(false) }
  const request = (): WorkRequest => {
    if (programs.some(program => !programServices(program).length)) throw new Error('Choose a service for every selected program.')
    if (!targetId && !payer) throw new Error('Choose a bill-to customer.')
    const coverage: CoverageGroup[] = groups.map(group => { const chosen = operations[group.service.id]; const operation = existing.data?.find(item => item.id === chosen && item.source_service_id === group.service.id); if (chosen && !operation) throw new Error('Reload the selected operation before continuing.'); return { key: group.service.id, service_id: group.service.id, program_ids: group.programs.map(item => item.id), operation: operation ? { kind: 'existing', labor_id: operation.id, expected_operation_version: operation.version } : { kind: 'new' } } })
    return { channel, programs: programs.map(refFor), target: targetId ? { kind: 'existing', repair_order_id: targetId } : { kind: 'new', bill_to_customer_id: payer, description: description.trim() || null }, coverage }
  }
  const review = async () => { try { setError(null); const body = request(); setPreview(await command.run(`/vehicles/${vehicleId}/maintenance-work-preview`, body, value => parseWorkPreview(value, vehicleId, body), 'post', true)) } catch (failure) { if (!(failure instanceof MaintenanceCancelled)) setError({ message: maintenanceError(failure) }) } }
  const commit = async () => {
    if (!preview) return
    try { setError(null); const body = request(); const result = await command.run(`/vehicles/${vehicleId}/maintenance-work`, { ...body, expected_work_fingerprint: preview.expected_work_fingerprint }, value => { const result = workMutationSchema.parse(value); if ((body.target.kind === 'existing' && result.repair_order_id !== body.target.repair_order_id) || new Set(result.programs.map(program => program.id)).size !== programs.length || result.programs.length !== programs.length || result.programs.some(program => !programs.some(item => item.id === program.id))) throw new Error('Maintenance work response does not match the selected programs.'); result.programs.forEach(program => scopedProgram(program, vehicleId)); return result }); onDone(result.repair_order_id) }
    catch (failure) { if (failure instanceof MaintenanceCancelled) return; setError({ message: maintenanceError(failure) }); setStockAccepted(false); const fresh = errorDetail(failure)?.preview; if (fresh) { try { setPreview(parseWorkPreview(fresh, vehicleId, request())) } catch { setPreview(null) } } }
  }
  return <section className="db-maintenance__editor" aria-label="Plan maintenance work" onKeyDown={event => { if (event.key === 'Escape' && !command.busy) { event.stopPropagation(); onCancel() } }}>
    <h4>Plan work · {programs.length} programs</h4><fieldset disabled={command.busy} onChange={changed}>
      <label>Repair order<select value={targetId} onChange={event => { setTargetId(event.target.value); setOperations({}) }}><option value="">Create new order</option>{!orders.isError && orders.data?.map(order => <option key={order.id} value={order.id}>{order.order_number}</option>)}</select></label>
      {orders.isError && <p role="alert">Draft orders unavailable. <button type="button" onClick={() => void orders.refetch()}>Retry orders</button></p>}
      {!targetId && <>{!customerId && <label>Bill to<select value={payer} onChange={event => setPayer(event.target.value)}><option value="">Choose customer</option>{!payers.isError && payers.data?.filter((item, i, all) => all.findIndex(other => other.customer_id === item.customer_id) === i).map(item => <option key={item.customer_id} value={item.customer_id}>{item.customer_company_name || 'Customer'}</option>)}</select></label>}<label>Work description<input value={description} onChange={event => setDescription(event.target.value)} /></label></>}
      {payers.isError && <p role="alert">Bill-to customers unavailable. <button type="button" onClick={() => void payers.refetch()}>Retry customers</button></p>}
      {groups.map(group => <div className="db-maintenance__group" key={group.service.id}><strong>{group.service.name}</strong><small>Covers {group.programs.map(program => program.name).join(', ')}{group.programs.length > 1 ? ' · one operation and parts bundle' : ''}</small>{targetId && <label>Operation<select value={operations[group.service.id] ?? ''} disabled={existing.isPending || existing.isError} onChange={event => setOperations(current => ({ ...current, [group.service.id]: event.target.value }))}><option value="">Add new operation</option>{!existing.isError && existing.data?.filter(operation => operation.source_service_id === group.service.id).map(operation => <option key={operation.id} value={operation.id}>Use saved · {operation.description}</option>)}</select></label>}</div>)}
      {existing.isError && <p role="alert">Operations unavailable. <button type="button" onClick={() => void existing.refetch()}>Retry operations</button></p>}
      <button type="button" disabled={Boolean(targetId) && (existing.isPending || existing.isError)} onClick={() => void review()}>Review work</button>
    </fieldset>
    {preview && <PricingFeedback revision={preview} role="status"><div className="db-maintenance__review" aria-label="Work confirmation"><h4>{pricingMoney(preview.totals.repair_total)} · Order total</h4>{preview.projection === 'shop' && <small>Labor · {preview.account_policy.labor.source} {pricingMoney(preview.account_policy.labor.rate)}/hr · Parts · {preview.account_policy.parts.source} {preview.account_policy.parts.mode}</small>}{preview.projection === 'fleet' && preview.agreement_applies && <small>Account agreement applies.</small>}
      {preview.coverage.map(group => <div key={group.key}>{group.service_name} · {group.hours} h · {group.checklist_items} tasks{group.preserves_saved_operation ? ' · saved operation retained' : ''}</div>)}
      <ul>{preview.lines.map(line => <li key={line.line_key}><span>{line.quantity} × {line.name} · {line.disposition}</span>{preview.projection === 'shop' && 'pricing' in line && <span>{pricingMoney(line.pricing.line_total)}</span>}</li>)}</ul>
      {preview.warnings.map((warning, i) => <p key={i}>{warning.message}</p>)}{preview.availability.state !== 'ready' && <label className="db-maintenance__check"><input type="checkbox" checked={stockAccepted} onChange={event => setStockAccepted(event.target.checked)} />Accept the displayed stock shortages and omitted parts.</label>}
    </div></PricingFeedback>}{error && <PricingFeedback revision={error}>{error.message}</PricingFeedback>}
    <div className="db-maintenance__actions"><button type="button" disabled={command.busy} onClick={onCancel}>Cancel</button><button type="button" disabled={command.busy || !preview || (preview.availability.state !== 'ready' && !stockAccepted)} onClick={() => void commit()}>{command.busy ? 'Saving…' : targetId ? 'Add to order' : 'Create work'}</button></div>
  </section>
}
