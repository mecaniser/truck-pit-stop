import PlatformSelect from '@/components/PlatformSelect'
import { useState } from 'react'
import DatePicker from '@/components/DatePicker'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { usePricingScope } from '@/features/parts-pricing/usePricingScope'
import { label, type Observation, type TargetPreview, type Targets } from './contract'
import type { AttestationDraft } from './attestation'
import PricingFeedback from '@/features/parts-pricing/PricingFeedback'

export function AttestationFields({ value, onChange, disabled = false, source }: { value: AttestationDraft; onChange: (value: AttestationDraft) => void; disabled?: boolean; source?: { kind: 'repair_order' | 'external_service'; id: string } }) {
  const update = (next: Partial<AttestationDraft>) => onChange({ ...value, ...next })
  return <fieldset disabled={disabled} className="db-maintenance__fields" onKeyDown={event => { if (event.key === 'Escape' && event.defaultPrevented) event.stopPropagation() }}><DatePicker label="Service date" value={value.date} onChange={date => update({ date })} disabled={disabled} showDayDetails={false} />
    {(['odometer_miles', 'engine_hours'] as const).map(meter => { const key = meter === 'odometer_miles' ? 'miles' : 'hours'; return <label key={meter}>{meter === 'odometer_miles' ? 'Miles at service' : 'Hours at service'}<input inputMode="decimal" value={value[key]} disabled={Boolean(value.sources[meter])} placeholder="Unknown" onChange={event => update({ [key]: event.target.value })} />{source?.kind === 'external_service' && meter === 'odometer_miles' && <button type="button" onClick={() => update({ sources: { ...value.sources, [meter]: value.sources[meter] ? undefined : { kind: 'source', meter, source_kind: source.kind, source_id: source.id } } })}>{value.sources[meter] ? 'Enter manually' : 'Use source reading'}</button>}{value.sources[meter] && <small>Source reading will be verified in preview.</small>}</label> })}
    <label>Reading basis<PlatformSelect value={value.basis} onChange={event => update({ basis: event.target.value as AttestationDraft['basis'] })}><option value="staff_observed">Observed</option><option value="staff_reported">Reported</option></PlatformSelect></label>
    <label className="db-maintenance__check db-maintenance__wide"><input type="checkbox" checked={value.confirmed} onChange={event => update({ confirmed: event.target.checked })} />These are the actual service date and readings.</label>
  </fieldset>
}
export function Reading({ value }: { value: Observation | null }) {
  if (!value) return <span className="db-maintenance__muted">No reading</span>
  return <span className="db-maintenance__reading"><strong>{value.value} {value.unit}</strong>{value.comparison_value !== null && value.comparison_value !== value.value && <span> · Compared as {value.comparison_value} {value.unit}</span>}<small>{label(value.source)} · {label(value.basis)} · {(value.observed_precision === 'date' ? value.observed_on : value.observed_at ?? value.observed_on) ?? 'Observation time unknown'} · {label(value.admission)}{value.freshness !== 'fresh' ? ` · ${value.freshness}` : ''}</small></span>
}
export function TargetValues({ value }: { value: Targets }) { const values = [value.due_on, value.odometer_miles === null ? null : `${value.odometer_miles.toLocaleString()} mi`, value.engine_hours === null ? null : `${value.engine_hours} h`].filter(Boolean); return <span>{values.join(' · ') || 'No targets set'}</span> }
export function TargetReview({ preview, names = {} }: { preview: TargetPreview; names?: Record<string, string> }) {
  const affectedOrders = preview.affected_work.filter((work, index, all) => !work.repair_order_id || all.findIndex(other => other.repair_order_id === work.repair_order_id) === index)
  return <PricingFeedback revision={preview} role="status"><div className="db-maintenance__review" aria-label="Target review">{preview.items.map((item, index) => <div key={item.program_id ?? index}>
    <strong>{names[item.program_id ?? 'new'] ? `${names[item.program_id ?? 'new']} · ` : ''}{label(item.outcome)}</strong><div><small>Before </small><TargetValues value={item.previous_targets} /></div><div><small>After </small><TargetValues value={item.proposed_targets} /></div>
    {item.resolved_attestation && <div>Service {item.resolved_attestation.performed_on}{item.resolved_attestation.readings.odometer_miles && <Reading value={item.resolved_attestation.readings.odometer_miles} />}{item.resolved_attestation.readings.engine_hours && <Reading value={item.resolved_attestation.readings.engine_hours} />}</div>}
    {item.missing.length > 0 && <p>Still needed: {item.missing.map(label).join(', ')}.</p>}{item.warnings.map((warning, i) => <p key={i}>{warning.message}</p>)}
  </div>)}{preview.warnings.map((warning, i) => <p key={i}>{warning.message}</p>)}{affectedOrders.length > 0 && <p>Affected work: {affectedOrders.map(work => work.order_number || 'Saved work').join(', ')}.</p>}</div></PricingFeedback>
}
export function ServicePicker({ value, name, onChange, disabled = false }: { value: string; name?: string; onChange: (id: string) => void; disabled?: boolean }) {
  const scope = usePricingScope(); const [search, setSearch] = useState(''); const queryText = useDebouncedValue(search, 250)
  const query = useQuery({ queryKey: ['maintenance-services', scope, queryText], gcTime: 0, retry: false, queryFn: async ({ signal }) => { const result = (await api.get<{ id: string; name: string }[]>('/services/typeahead', { signal, params: { q: queryText || undefined, limit: 20 } })).data; if (!Array.isArray(result)) throw new Error('Services unavailable'); return result } })
  return <div className="db-maintenance__service"><label>Find service<input type="search" value={search} maxLength={100} onChange={event => setSearch(event.target.value)} disabled={disabled} /></label><label>Service<PlatformSelect value={value} disabled={disabled || query.isPending || query.isError} onChange={event => onChange(event.target.value)}><option value="">No service</option>{value && !query.data?.some(item => item.id === value) && <option value={value}>{name || 'Selected service'}</option>}{!query.isError && query.data?.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</PlatformSelect></label>{query.isError && <p role="alert">Services unavailable. <button type="button" onClick={() => void query.refetch()}>Retry services</button></p>}</div>
}
