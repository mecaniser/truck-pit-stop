import { emptyAttestation, toAttestation } from './attestation'
import { useEffect, useRef, useState } from 'react'
import DatePicker from '@/components/DatePicker'
import { useAuthStore } from '@/stores/authStore'
import PricingFeedback from '@/features/parts-pricing/PricingFeedback'
import { errorDetail, maintenanceError, maintenancePath, programPath, scopedProgram, useMaintenanceCommand, MaintenanceCancelled } from './api'
import { hours, parseTargetPreview, programMutationSchema, refFor, whole, type Channel, type Config, type Program, type TargetPreview, type TargetRequest, type TargetSeed } from './contract'
import { AttestationFields, ServicePicker, TargetReview } from './MaintenanceFields'

const reloadCodes = new Set(['maintenance_version_conflict', 'maintenance_preview_changed', 'maintenance_cycle_claimed', 'maintenance_review_required', 'maintenance_template_unavailable', 'maintenance_source_changed', 'maintenance_restore_conflict'])

export default function ProgramEditor({ vehicleId, channel, program, onDone, onCancel, onReload }: { vehicleId: string; channel: Channel; program?: Program; onDone: () => void; onCancel: () => void; onReload?: () => Promise<Program> }) {
  const role = useAuthStore(state => state.user?.role)
  const canAttest = ['garage_owner', 'garage_admin', 'fleet_manager'].includes(role ?? '') && (program?.capabilities.can_record_evidence ?? true)
  // The original version stays with the draft until an explicit reload/remount.
  const [base, setBase] = useState(program)
  const [name, setName] = useState(base?.name ?? ''); const [days, setDays] = useState(String(base?.intervals.days ?? ''))
  const [miles, setMiles] = useState(String(base?.intervals.miles ?? '')); const [engineHours, setHours] = useState(base?.intervals.engine_hours ?? '')
  const [serviceId, setService] = useState(base?.service?.id ?? ''); const [action, setAction] = useState<'preserve' | 'replace' | 'recalculate' | 'rebaseline' | 'convert_legacy'>(base ? 'preserve' : 'replace')
  const [seedKind, setSeedKind] = useState<'explicit' | 'baseline'>('explicit')
  const [dueOn, setDueOn] = useState(base?.targets.due_on ?? ''); const [dueMiles, setDueMiles] = useState(String(base?.targets.odometer_miles ?? '')); const [dueHours, setDueHours] = useState(base?.targets.engine_hours ?? '')
  const [attestation, setAttestation] = useState(emptyAttestation); const [reason, setReason] = useState('')
  const [preview, setPreview] = useState<TargetPreview | null>(null); const [error, setError] = useState<{ message: string; reloadSaved?: boolean } | null>(null)
  const reportError = (failure: unknown) => setError({ message: maintenanceError(failure), reloadSaved: reloadCodes.has(errorDetail(failure)?.code ?? '') })
  const command = useMaintenanceCommand(`${vehicleId}:${base?.id ?? 'new'}:configuration`)
  const mounted = useRef(true); useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const [reloading, setReloading] = useState(false)
  const reload = async () => { if (!onReload) return; setReloading(true); try { const saved = await onReload(); if (!mounted.current) return; setBase(saved); setName(saved.name); setDays(String(saved.intervals.days ?? '')); setMiles(String(saved.intervals.miles ?? '')); setHours(saved.intervals.engine_hours ?? ''); setService(saved.service?.id ?? ''); setAction('preserve'); setDueOn(saved.targets.due_on ?? ''); setDueMiles(String(saved.targets.odometer_miles ?? '')); setDueHours(saved.targets.engine_hours ?? ''); setAttestation(emptyAttestation()); setReason(''); setPreview(null); setError(null) } catch (failure) { if (mounted.current) setError({ message: maintenanceError(failure), reloadSaved: true }) } finally { if (mounted.current) setReloading(false) } }
  const altered = () => { setPreview(null); setError(null) }
  const config = (): Config => {
    const intervals = { days: whole(days, 'day interval', 36500), miles: whole(miles, 'mile interval'), engine_hours: hours(engineHours) }
    if (!name.trim()) throw new Error('Enter a program name.')
    if (Object.values(intervals).some(value => value !== null && Number(value) <= 0)) throw new Error('Intervals must be positive. Leave unused fields blank.')
    if ((base?.mode !== 'legacy' || action === 'convert_legacy') && Object.values(intervals).every(value => value === null)) throw new Error('Set at least one positive interval.')
    if (base && action === 'preserve' && (['days', 'miles', 'engine_hours'] as const).some(key => (base.intervals[key] === null) !== (intervals[key] === null))) throw new Error('Review targets when enabling or disabling an interval.')
    return { name: name.trim(), intervals, service_id: base?.mode === 'legacy' && action !== 'convert_legacy' ? null : serviceId || null }
  }
  const seed = (configuration: Config): TargetSeed => seedKind === 'baseline' ? { kind: 'baseline', attestation: toAttestation(attestation) } : { kind: 'explicit', targets: { due_on: configuration.intervals.days === null ? null : dueOn || null, odometer_miles: configuration.intervals.miles === null ? null : whole(dueMiles, 'target mileage'), engine_hours: configuration.intervals.engine_hours === null ? null : hours(dueHours) } }
  const request = (): Extract<TargetRequest, { purpose: 'configuration' }> => {
    const configuration = config()
    if ((action === 'rebaseline' || action === 'convert_legacy') && reason.trim().length < 3) throw new Error('Enter a reason of at least 3 characters.')
    return { purpose: 'configuration', channel, program: base ? refFor(base) : null, config: configuration, action: base ? action === 'preserve' ? 'replace' : action : 'create', seed: seed(configuration), reason: reason.trim() || null }
  }
  const review = async () => { try { setError(null); const body = request(); setPreview(await command.run(`/vehicles/${vehicleId}/maintenance-target-preview`, body, value => parseTargetPreview(value, body), 'post', true)) } catch (failure) { if (!(failure instanceof MaintenanceCancelled)) reportError(failure) } }
  const save = async () => {
    try {
      setError(null); const configuration = config()
      if (action !== 'preserve' && !preview) throw new Error('Review the targets before saving.')
      const body = { channel, ...(base ? { expected_version: base.version } : {}), config: configuration, targets: action === 'preserve' ? { kind: 'preserve' } : { kind: action, seed: seed(configuration), reason: reason.trim() || null, expected_target_fingerprint: preview!.expected_target_fingerprint } }
      await command.run(base ? programPath(vehicleId, base.id) : maintenancePath(vehicleId), body, value => { const result = programMutationSchema.parse(value); scopedProgram(result.program, vehicleId, base?.id); return result }, base ? 'patch' : 'post'); onDone()
    } catch (failure) { if (failure instanceof MaintenanceCancelled) return; reportError(failure); const fresh = errorDetail(failure)?.preview; if (fresh && action !== 'preserve') { try { setPreview(parseTargetPreview(fresh, request())) } catch { setPreview(null) } } }
  }
  return <form aria-label={base ? `Edit ${base.name}` : 'New maintenance program'} onSubmit={event => { event.preventDefault(); void save() }} onKeyDown={event => { if (event.defaultPrevented) { event.stopPropagation(); return } if (event.key === 'Escape' && !command.busy && event.currentTarget.contains(event.target as Node)) { event.stopPropagation(); onCancel() } }} onChange={altered} className="db-maintenance__editor">
    <fieldset disabled={command.busy || reloading}><label>Name<input value={name} maxLength={120} onChange={event => setName(event.target.value)} /></label><fieldset className="db-maintenance__fields"><legend>Repeat every</legend><label>Days<input inputMode="numeric" value={days} placeholder="Off" onChange={event => setDays(event.target.value)} /></label><label>Miles<input inputMode="numeric" value={miles} placeholder="Off" onChange={event => setMiles(event.target.value)} /></label><label>Engine hours<input inputMode="decimal" value={engineHours} placeholder="Off" onChange={event => setHours(event.target.value)} /></label></fieldset>
      {base?.mode === 'legacy' && action !== 'convert_legacy' ? <p>Legacy package: {base.legacy_package?.map(item => item.name).join(' · ') || 'No service'}</p> : <ServicePicker value={serviceId} name={base?.service?.name} onChange={value => { setService(value); altered() }} />}
      {base && <label>Targets<select value={action} onChange={event => setAction(event.target.value as typeof action)}><option value="preserve">Keep targets</option><option value="replace">Set targets</option>{canAttest && <><option value="recalculate">Recalculate from service</option><option value="rebaseline">Rebaseline</option></>}{canAttest && base.mode === 'legacy' && <option value="convert_legacy">Convert legacy program</option>}</select></label>}
      {action !== 'preserve' && <><label>Starting point<select value={seedKind} onChange={event => setSeedKind(event.target.value as typeof seedKind)}><option value="explicit">Next targets</option>{canAttest && <option value="baseline">Actual service</option>}</select></label>{seedKind === 'baseline' ? <AttestationFields value={attestation} onChange={value => { setAttestation(value); altered() }} /> : <div className="db-maintenance__fields">{days && <DatePicker label="Next date" value={dueOn} onChange={value => { setDueOn(value); altered() }} disabled={command.busy || reloading} showDayDetails={false} />}{miles && <label>Next miles<input inputMode="numeric" value={dueMiles} onChange={event => setDueMiles(event.target.value)} /></label>}{engineHours && <label>Next hours<input inputMode="decimal" value={dueHours} onChange={event => setDueHours(event.target.value)} /></label>}</div>}{(action === 'rebaseline' || action === 'convert_legacy') && <label>Reason<input value={reason} maxLength={500} onChange={event => setReason(event.target.value)} /></label>}<button type="button" onClick={() => void review()}>Review targets</button></>}
    </fieldset>
    {preview && <TargetReview preview={preview} names={{[base?.id ?? 'new']: name}} />}{error && <PricingFeedback revision={error}>{error.message}{error.reloadSaved && base && onReload && <button type="button" disabled={command.busy || reloading} onClick={() => void reload()}>Discard draft & reload saved</button>}</PricingFeedback>}
    <div className="db-maintenance__actions"><button type="button" disabled={command.busy || reloading} onClick={onCancel}>Cancel</button><button type="submit" disabled={command.busy || reloading || (action !== 'preserve' && !preview)}>{command.busy ? 'Saving…' : 'Save program'}</button></div>
  </form>
}
