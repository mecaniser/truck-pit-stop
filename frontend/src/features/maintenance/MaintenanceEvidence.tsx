import { emptyAttestation, toAttestation } from './attestation'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { usePricingScope } from '@/features/parts-pricing/usePricingScope'
import PricingFeedback from '@/features/parts-pricing/PricingFeedback'
import { errorDetail, maintenanceError, MaintenanceCancelled, programPath, scopedProgram, useMaintenanceCommand } from './api'
import { evidenceMutationSchema, parseTargetPreview, refFor, type Channel, type Completion, type EvidenceIntent, type Program, type TargetPreview, type TargetRequest } from './contract'
import { AttestationFields, TargetReview } from './MaintenanceFields'

export default function MaintenanceEvidence({ vehicleId, channel, program, completion, onDone, onCancel }: { vehicleId: string; channel: Channel; program: Program; completion?: Completion; onDone: () => void; onCancel: () => void }) {
  const scope = usePricingScope(); const role = useAuthStore(state => state.user?.role)
  const command = useMaintenanceCommand(`${vehicleId}:${program.id}:evidence`)
  const [action, setAction] = useState<EvidenceIntent['action']>(completion ? 'reaffirm' : program.work?.state === 'pending_evidence' ? 'resolve_pending' : 'recognize')
  const [sourceKind, setSourceKind] = useState<'repair_order' | 'external_service'>('repair_order'); const [sourceId, setSourceId] = useState(''); const [sourcePage, setSourcePage] = useState(0); const [status, setStatus] = useState('completed')
  const [attestation, setAttestation] = useState(emptyAttestation); const [reason, setReason] = useState(''); const [acknowledged, setAcknowledged] = useState(false)
  const [preview, setPreview] = useState<TargetPreview | null>(null); const [error, setError] = useState<{ message: string } | null>(null)
  const sources = useQuery({ queryKey: ['maintenance-sources', scope, vehicleId, sourceKind, sourcePage, status, channel], enabled: action === 'recognize', gcTime: 0, retry: false,
    queryFn: async ({ signal }) => {
      const raw = (await api.get<{ items: { id: string; vehicle_id: string; status?: string; order_number?: string; description?: string; service_date?: string; voided_at?: string | null }[]; has_more: boolean }>(sourceKind === 'external_service' ? `/vehicles/${vehicleId}/external-services` : '/repair-orders', { signal, params: { skip: sourcePage * 25, limit: 25, ...(sourceKind === 'repair_order' ? { vehicle_id: vehicleId, status, paginated: true, pricing_presentation: channel } : { include_voided: false }) } })).data
      if (!Array.isArray(raw.items) || raw.items.some(item => item.vehicle_id !== vehicleId)) throw new Error('Invalid maintenance source response.')
      return { ...raw, items: raw.items.filter(item => sourceKind === 'external_service' ? !item.voided_at : ['completed', 'invoiced', 'paid'].includes(item.status ?? '')) }
    },
  })
  const source = action === 'resolve_pending' && program.work?.repair_order_id ? { kind: 'repair_order' as const, id: program.work.repair_order_id } : action === 'recognize' && sourceId ? { kind: sourceKind, id: sourceId } : completion?.source.id && completion.source.kind !== 'manual' ? { kind: completion.source.kind, id: completion.source.id } : undefined
  const changed = () => { setPreview(null); setError(null); setAcknowledged(false) }
  const intent = (links: string[] = []): EvidenceIntent => {
    if (action === 'resolve_pending') { if (!program.work) throw new Error('Reload the pending work.'); return { action, work_link_id: program.work.work_link_id, expected_link_version: program.work.version, attestation: toAttestation(attestation) } }
    if (action === 'recognize') { if (!sourceId || !sources.data?.items.some(item => item.id === sourceId)) throw new Error('Choose eligible service history.'); return { action, source: { kind: sourceKind, id: sourceId }, attestation: toAttestation(attestation) } }
    if (!completion || reason.trim().length < 3) throw new Error('Enter a correction reason of at least 3 characters.')
    const common = { completion_id: completion.id, reason: reason.trim(), acknowledged_work_link_ids: links }
    return action === 'supersede' ? { action, ...common, attestation: toAttestation(attestation) } : { action, ...common }
  }
  const request = (links?: string[]): Extract<TargetRequest, { purpose: 'evidence' }> => ({ purpose: 'evidence', channel, program: refFor(program), evidence: intent(links) })
  const review = async () => { try { setError(null); const body = request(); setPreview(await command.run(`/vehicles/${vehicleId}/maintenance-target-preview`, body, value => parseTargetPreview(value, body), 'post', true)); setAcknowledged(false) } catch (failure) { if (!(failure instanceof MaintenanceCancelled)) setError({ message: maintenanceError(failure) }) } }
  const save = async () => {
    if (!preview) return
    try {
      setError(null); let accepted = preview
      const links = preview.affected_work.map(work => work.work_link_id)
      if (links.length && !acknowledged) throw new Error('Acknowledge the affected work before saving.')
      const body = request(links)
      if (links.length && completion) {
        const checked = await command.run(`/vehicles/${vehicleId}/maintenance-target-preview`, body, value => parseTargetPreview(value, body), 'post', true)
        if (JSON.stringify(checked.items) !== JSON.stringify(preview.items) || JSON.stringify(checked.affected_work) !== JSON.stringify(preview.affected_work)) { setPreview(checked); setAcknowledged(false); throw new Error('The targets or affected work changed. Review them again.') }
        accepted = checked
      }
      await command.run(`${programPath(vehicleId, program.id)}/evidence`, { channel, program: body.program, evidence: body.evidence, expected_target_fingerprint: accepted.expected_target_fingerprint }, raw => { const result = evidenceMutationSchema.parse(raw); scopedProgram(result.program, vehicleId, program.id); if (result.completion.program_id !== program.id) throw new Error('Invalid maintenance evidence response.'); return result }); onDone()
    } catch (failure) { if (failure instanceof MaintenanceCancelled) return; setError({ message: maintenanceError(failure) }); const fresh = errorDetail(failure)?.preview; if (fresh) { try { setPreview(parseTargetPreview(fresh, request(preview.affected_work.map(work => work.work_link_id)))); setAcknowledged(false) } catch { setPreview(null) } } }
  }
  return <section className="db-maintenance__editor" aria-label={`Service evidence for ${program.name}`} onKeyDown={event => { if (event.key === 'Escape' && !command.busy) { event.stopPropagation(); onCancel() } }}><h4>{completion ? 'Review evidence' : action === 'resolve_pending' ? 'Resolve readings' : 'Record prior service'} · {program.name}</h4>
    <fieldset disabled={command.busy} onChange={changed}>
      {completion && <label>Correction<select value={action} onChange={event => setAction(event.target.value as typeof action)}><option value="reaffirm">Reaffirm evidence</option><option value="supersede">Correct evidence</option><option value="revoke">Revoke evidence</option></select></label>}
      {action === 'recognize' && <><div className="db-maintenance__fields"><label>Source<select value={sourceKind} onChange={event => { setSourceKind(event.target.value as typeof sourceKind); setSourceId(''); setSourcePage(0); setAttestation(emptyAttestation()) }}><option value="repair_order">Repair order</option>{['garage_owner', 'garage_admin'].includes(role ?? '') && <option value="external_service">Outside service</option>}</select></label>{sourceKind === 'repair_order' && <label>Order status<select value={status} onChange={event => { setStatus(event.target.value); setSourceId(''); setSourcePage(0) }}><option value="completed">Completed</option><option value="invoiced">Invoiced</option><option value="paid">Paid</option></select></label>}</div>
        <label>Service record<select value={sourceId} disabled={sources.isPending || sources.isError} onChange={event => { setSourceId(event.target.value); setAttestation(emptyAttestation()) }}><option value="">Choose service record</option>{!sources.isError && sources.data?.items.map(item => <option key={item.id} value={item.id}>{item.order_number ?? item.service_date} · {item.description || 'Service'}</option>)}</select></label>
        {sources.isError && <p role="alert">Source records unavailable. <button type="button" onClick={() => void sources.refetch()}>Retry records</button></p>}{(sourcePage > 0 || sources.data?.has_more) && <div className="db-maintenance__actions"><button type="button" disabled={sourcePage === 0} onClick={() => { setSourcePage(value => value - 1); setSourceId(''); changed() }}>Previous records</button><button type="button" disabled={!sources.data?.has_more} onClick={() => { setSourcePage(value => value + 1); setSourceId(''); changed() }}>Next records</button></div>}
      </>}
      {!['reaffirm', 'revoke'].includes(action) && <AttestationFields value={attestation} source={source} onChange={value => { setAttestation(value); changed() }} />}
      {completion && <label>Reason<input value={reason} maxLength={500} onChange={event => setReason(event.target.value)} /></label>}
      <button type="button" onClick={() => void review()}>Review targets</button>
    </fieldset>
    {preview && <><TargetReview preview={preview} names={{[program.id]: program.name}} />{preview.affected_work.length > 0 && <label className="db-maintenance__check"><input type="checkbox" checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} />I reviewed the affected work.</label>}</>}
    {error && <PricingFeedback revision={error}>{error.message}</PricingFeedback>}
    <div className="db-maintenance__actions"><button type="button" disabled={command.busy} onClick={onCancel}>Cancel</button><button type="button" disabled={command.busy || !preview || (preview.affected_work.length > 0 && !acknowledged)} onClick={() => void save()}>{command.busy ? 'Saving…' : 'Save evidence'}</button></div>
  </section>
}
