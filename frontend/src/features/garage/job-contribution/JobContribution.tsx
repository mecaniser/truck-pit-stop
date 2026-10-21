import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ChevronDown } from 'lucide-react'
import { useAuthStore, getAuthenticatedSessionIdentity } from '@/stores/authStore'
import api from '@/lib/api'
import { costMoney, hours, reasonLabel, validateSchedule } from './model'
import type { ContributionDetail, ContributionReport, ContributionRow, PolicyList, TechnicianPolicy } from './types'
import './jobContribution.css'
const ROOT = 'owner-job-contribution'
const status = (error: unknown) => (error as { response?: { status?: number } })?.response?.status
const errorText = (error: unknown) => status(error) === 409 ? 'Source or version changed. Refresh, inspect, then submit again.' : status(error) === 422 ? 'Check rate boundaries, coverage and review assertions.' : status(error) === 413 ? 'Too much source data. Narrow the date range.' : 'Cost data could not be loaded or saved. Draft preserved.'
import { isCostOwner } from './access'
type Read = <T>(path: string, params: object, signal?: AbortSignal) => Promise<T>
type Write = <T>(path: string, body: object, key: string) => Promise<T>
export default function JobContribution() {
  const state = useAuthStore()
  const client = useQueryClient()
  const identity = getAuthenticatedSessionIdentity(state)
  useEffect(() => () => { void client.cancelQueries({ queryKey: [ROOT] }); client.removeQueries({ queryKey: [ROOT] }) }, [client, identity])
  if (!isCostOwner(state) || !identity) return null
  return <OwnerReport key={identity} identity={identity} />
}
function OwnerReport({ identity }: { identity: string }) {
  const client = useQueryClient()
  const [denied, setDenied] = useState(false)
  const [dates, setDates] = useState({ from: '', to: '' })
  const [draftDates, setDraftDates] = useState(dates)
  const [search, setSearch] = useState('')
  const [scope, setScope] = useState('all')
  const [cursor, setCursor] = useState<string | null>(null)
  const [previous, setPrevious] = useState<Array<string | null>>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [rates, setRates] = useState(false)
  const current = () => isCostOwner(useAuthStore.getState()) && getAuthenticatedSessionIdentity(useAuthStore.getState()) === identity
  const reject = (error: unknown) => { if ([401, 403].includes(status(error) ?? 0)) { setDenied(true); client.removeQueries({ queryKey: [ROOT] }) } }
  const read: Read = async (path, params, signal) => { if (!current()) throw Error('Owner session changed'); try { const response = await api.get(path, { params, signal }); if (!current()) throw Error('Owner session changed'); return response.data } catch (error) { reject(error); throw error } }
  const write: Write = async (path, body, key) => { if (!current()) throw Error('Owner session changed'); try { const response = await api.post(path, body, { headers: { 'Idempotency-Key': key } }); if (!current()) throw Error('Owner session changed'); void client.invalidateQueries({ queryKey: [ROOT, identity] }); return response.data } catch (error) { reject(error); throw error } }
  const params = { ...(dates.from ? dates : {}), q: search, scope, limit: 25, ...(cursor ? { cursor } : {}) }
  const report = useQuery({ queryKey: [ROOT, identity, 'report', params], queryFn: ({ signal }) => read<ContributionReport>('/reports/job-contribution', params, signal), enabled: !denied, retry: false, gcTime: 0 })
  const reset = () => { setCursor(null); setPrevious([]); setSelected(null) }
  if (denied) return <p role="alert">Owner access required. Cost data cleared.</p>
  return <section className="db-job-cost" aria-label="Job Contribution"><header className="jc-toolbar"><div><h2>Job Contribution</h2><small>Owner only · Direct costs · Before shop overhead</small></div><button onClick={() => { setRates(!rates); setSelected(null) }}>{rates ? 'Back to contribution' : 'Technician Costs'}</button></header>
    {rates ? <TechnicianCosts identity={identity} read={read} write={write} timezone={report.data?.shop_timezone} activation={report.data?.activation_at} /> : <>
      <form className="jc-filters" onSubmit={event => { event.preventDefault(); setDates(draftDates); reset() }}><label>From<input type="date" value={draftDates.from} required={Boolean(draftDates.to)} onChange={e => setDraftDates({ ...draftDates, from: e.target.value })} /></label><label>Through<input type="date" min={draftDates.from} value={draftDates.to} required={Boolean(draftDates.from)} onChange={e => setDraftDates({ ...draftDates, to: e.target.value })} /></label><button>Apply dates</button><label>Order or customer<input type="search" maxLength={100} value={search} onChange={e => { setSearch(e.target.value); reset() }} /></label><label>Scope<select value={scope} onChange={e => { setScope(e.target.value); reset() }}>{['all', 'real', 'review', 'test', 'history'].map(value => <option key={value}>{value}</option>)}</select></label></form>
      {report.isLoading && <p role="status">Loading contribution…</p>}{report.error && <p role="alert">{errorText(report.error)} <button onClick={() => void report.refetch()}>Retry</button></p>}
      {report.data && <><p className="jc-muted">{report.data.from} – {report.data.to} · {report.data.shop_timezone} · Completion date, otherwise creation date</p><div className="jc-metrics"><Metric label="Reviewed complete contribution" value={costMoney(report.data.summary.reviewed_complete_contribution)} detail={`${report.data.summary.complete_row_count} complete jobs`} /><Metric label="Known recorded labor cost" value={costMoney(report.data.summary.known_recorded_direct_cost)} detail={`${hours(report.data.summary.costed_seconds)} costed / ${hours(report.data.summary.recorded_seconds)} recorded`} /><Metric label="Real jobs needing review" value={String(report.data.summary.incomplete_row_count)} detail={report.data.summary.is_complete ? 'Reviewed recorded scope complete' : 'Included totals incomplete'} /></div><p className="jc-muted">{report.data.summary.real_count} real · {report.data.summary.test_count} test excluded · {report.data.summary.unknown_count} unclassified held · {report.data.summary.history_count} source history</p><div>{report.data.rows.map(row => <button className="jc-row" key={row.order_id} onClick={() => setSelected(row.order_id)}><span><strong>{row.order_number}</strong><span>{row.customer_name}</span><small>{row.source_owner === 'ets_history' ? 'ETS history' : `${row.business_classification} · ${row.review_status} review`}</small></span><span><small>Issued direct revenue</small>{costMoney(row.revenue.net_direct_revenue)}</span><span><small>Direct contribution</small><strong>{costMoney(row.direct_contribution)}</strong><small>{row.direct_contribution === null ? 'Incomplete / excluded' : `${row.margin_pct ?? '—'}% margin`}</small></span></button>)}{!report.data.rows.length && <p>No jobs in this cohort.</p>}</div><nav className="jc-pagination" aria-label="Contribution pages"><button disabled={!previous.length} onClick={() => { setCursor(previous[previous.length - 1]); setPrevious(previous.slice(0, -1)); setSelected(null) }}>Previous</button><button disabled={!report.data.next_cursor} onClick={() => { setPrevious([...previous, cursor]); setCursor(report.data!.next_cursor); setSelected(null) }}>Next</button></nav></>}
      {selected && <JobDetail key={selected} identity={identity} orderId={selected} timezone={report.data?.shop_timezone} read={read} write={write} close={() => setSelected(null)} />}
      <details><summary><ChevronDown aria-hidden="true" size={16} />How the numbers work</summary><p>Synthetic example: $500 net direct revenue − $150 parts − (3 hours × $40 loaded hourly cost) = $230 contribution, 46% margin.</p><p>At 5 hours, labor costs $200 and contribution falls to $150, 30% margin. Taxes, fees, supplies and shop overhead stay separate.</p></details>
    </>}
  </section>
}
function Metric({ label, value, detail }: { label: string; value: string; detail: string }) { return <div className="jc-metric"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div> }
function Reasons({ reasons }: { reasons: string[] }) { return reasons.length ? <ul>{[...new Set(reasons)].map(reason => <li key={reason}>{reasonLabel(reason)}</li>)}</ul> : null }
function Breakdown({ row }: { row: ContributionRow }) { return <dl className="jc-breakdown">{[['Issued direct revenue', costMoney(row.revenue.net_direct_revenue)], ['Known technician cost', costMoney(row.labor.known_cost)], ['Known parts cost', costMoney(row.parts.known_cost)], ['Known sublet cost', costMoney(row.sublet.known_cost)], ['Direct contribution', costMoney(row.direct_contribution)], ['Labor coverage', reasonLabel(row.labor.status)], ['Parts coverage', `${row.parts.line_count} lines · ${row.parts.missing_cost_line_count} missing costs · ${reasonLabel(row.parts.status)}`], ['Sublet coverage', `${row.sublet.line_count} lines · ${row.sublet.missing_cost_line_count} missing costs · ${reasonLabel(row.sublet.status)}`], ['Recorded / costed time', `${hours(row.labor.recorded_seconds)} / ${hours(row.labor.costed_seconds)}`], ['Operation / general RO time', `${hours(row.labor.operation_attributed_seconds)} / ${hours(row.labor.general_ro_seconds)}`], ['Open sessions (provisional)', String(row.labor.open_session_count)], ['Unrated / held / before activation', `${hours(row.labor.unrated_seconds)} / ${hours(row.labor.held_seconds)} / ${hours(row.labor.pre_activation_seconds)}`], ['Tax / fees / supplies (excluded)', `${costMoney(row.revenue.tax)} / ${costMoney(row.revenue.fees)} / ${costMoney(row.revenue.supplies)}`]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl> }
function JobDetail({ identity, orderId, timezone, read, write, close }: { identity: string; orderId: string; timezone?: string; read: Read; write: Write; close: () => void }) {
  const data = useQuery({ queryKey: [ROOT, identity, 'detail', orderId], queryFn: ({ signal }) => read<ContributionDetail>(`/reports/job-contribution/${orderId}`, {}, signal), retry: false, gcTime: 0 })
  const [classification, setClassification] = useState('unknown'), [capture, setCapture] = useState('incomplete'), [reason, setReason] = useState(''), [error, setError] = useState(''), [saving, setSaving] = useState(false), [saved, setSaved] = useState(false)
  const [exceptions, setExceptions] = useState<string[]>([]), [key, setKey] = useState(() => crypto.randomUUID())
  const detail = data.data
  const [initialized, setInitialized] = useState(false)
  useEffect(() => {
    if (detail && !initialized) {
      setClassification(detail.row.business_classification)
      setCapture(detail.review?.time_capture ?? 'incomplete')
      setExceptions(detail.review?.reviewed_exception_ids ?? [])
      setInitialized(true)
    }
  }, [detail, initialized])
  const edit = () => { setKey(crypto.randomUUID()); setSaved(false); setError('') }
  const submit = async () => { if (!detail || !reason.trim() || saving) return; setSaving(true); setError(''); try { await write(`/reports/job-contribution/${orderId}/review`, { expected_version: detail.row.review_version, source_fingerprint: detail.source_fingerprint, policy_heads_digest: detail.policy_heads_digest, business_classification: classification, time_capture: capture, reviewed_exception_ids: exceptions, reason: reason.trim() }, key); setSaved(true); setReason(''); setKey(crypto.randomUUID()) } catch (e) { setError(errorText(e)) } finally { setSaving(false) } }
  return <article className="jc-detail" aria-label="Job cost review"><header className="jc-toolbar"><h3>{detail?.row.order_number ?? 'Job cost review'}</h3><button onClick={close}>Close details</button></header>{data.isLoading && <p>Loading job cost…</p>}{data.error && <p role="alert">{errorText(data.error)}</p>}{detail && <><Breakdown row={detail.row} /><Reasons reasons={[...detail.row.hold_reasons, ...detail.row.revenue.hold_reasons, ...detail.row.labor.hold_reasons]} /><SeparateShopTime detail={detail} timezone={timezone} /><details><summary><ChevronDown aria-hidden="true" size={16} />Recorded technician time</summary>{detail.sessions.map(session => <div key={session.id}><strong>{session.mechanic_name}</strong> · {hours(session.recorded_seconds)} · {costMoney(session.known_cost)}<Reasons reasons={session.hold_reasons} /></div>)}</details><Link to={`/dashboard/repair-orders?selected=${encodeURIComponent(orderId)}`}>Open repair order</Link>
      {(detail.row.source_owner === 'native' || detail.row.source_owner === 'review_required') ? <form className="jc-review" onSubmit={e => { e.preventDefault(); void submit() }}><h4>Owner scope review</h4><label>Business activity<select value={classification} onChange={e => { setClassification(e.target.value); edit() }}><option value="unknown">Unknown — keep held</option><option value="real">Real business activity</option><option value="test">Test — exclude</option></select></label><label>Time capture assertion<select value={capture} onChange={e => { setCapture(e.target.value); edit() }}><option value="incomplete">Incomplete capture</option><option value="complete">All direct labor recorded</option><option value="no_internal_labor">No internal labor performed</option></select></label><p className="jc-muted">Real activity does not prove payment. Complete capture is a job-time assertion, not payroll approval.</p>{detail.sessions.filter(session => session.hold_reasons.some(code => /auto_stop|correct|delet/.test(code))).map(session => <label className="jc-check" key={session.id}><input type="checkbox" checked={exceptions.includes(session.id)} onChange={e => { setExceptions(e.target.checked ? [...exceptions, session.id] : exceptions.filter(id => id !== session.id)); edit() }} />Acknowledge exception: {session.mechanic_name} · {session.started_at}<Reasons reasons={session.hold_reasons} /></label>)}<label>Review reason<textarea required maxLength={500} value={reason} onChange={e => { setReason(e.target.value); edit() }} /></label><details><summary><ChevronDown aria-hidden="true" size={16} />Review source identity</summary><span className="jc-fingerprint">Source {detail.source_fingerprint}<br />Policy heads {detail.policy_heads_digest}</span></details>{error && <p role="alert">{error} <button type="button" onClick={() => { void data.refetch(); setKey(crypto.randomUUID()) }}>Refresh source</button></p>}{saved && <p role="status">Review saved. Current source recalculated.</p>}<button disabled={saving || !reason.trim()}>{saving ? 'Saving review…' : 'Append owner review'}</button></form> : <p>Source-owned history cannot receive a native costing review.</p>}</>}</article>
}
function SeparateShopTime({ detail, timezone }: { detail: ContributionDetail; timezone?: string }) {
  const time = detail.separate_shop_time
  const observed = time.time_status === 'complete' ? 'Complete observed coverage within selected windows' : time.time_status === 'partial' ? 'Partial observed coverage — some time unavailable' : 'Observed time unavailable'
  const duration = (seconds: number | null) => seconds === null ? 'Unavailable' : hours(seconds)
  const local = (instant: string) => {
    if (!timezone) return 'Local time unavailable'
    try { return new Intl.DateTimeFormat('en-US', { timeZone: timezone, month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(instant)) } catch { return 'Local time unavailable' }
  }
  return <section className="jc-shop-time" aria-label="Separate time within selected job timer window"><h4>Shop time during this job's timer window</h4><p className="jc-muted">{observed}</p><dl className="jc-breakdown"><div><dt>Miscellaneous time</dt><dd>{duration(time.misc_seconds)}</dd></div><div><dt>Observed idle time</dt><dd>{duration(time.idle_seconds)}</dd></div><div><dt>Break time</dt><dd>{duration(time.break_seconds)}</dd></div></dl>{time.scope_windows.map(window => <p className="jc-muted" key={`${window.mechanic_id}-${window.started_at}`}>{detail.sessions.find(session => session.mechanic_id === window.mechanic_id)?.mechanic_name ?? 'Technician'} · {local(window.started_at)} – {local(window.ended_at)} · {timezone ?? 'Shop timezone unavailable'}</p>)}{!time.scope_windows.length && <p className="jc-muted">No valid closed job timer window.</p>}<p className="jc-muted">Cost unavailable · Not allocated to job expense</p></section>
}
function TechnicianCosts({ identity, read, write, timezone, activation }: { identity: string; read: Read; write: Write; timezone?: string; activation?: string }) {
  const [search, setSearch] = useState(''), [cursor, setCursor] = useState<string | null>(null), [previous, setPrevious] = useState<Array<string | null>>([]), [selected, setSelected] = useState<TechnicianPolicy | null>(null)
  const list = useQuery({ queryKey: [ROOT, identity, 'rates', search, cursor], queryFn: ({ signal }) => read<PolicyList>('/reports/technician-costs', { q: search, limit: 25, ...(cursor ? { cursor } : {}) }, signal), retry: false, gcTime: 0 })
  return <section aria-label="Technician Costs"><h3>Technician Costs</h3><p className="jc-muted">Loaded direct employment cost · October 20, 2026 · {timezone ?? 'Shop timezone'} · Shop overhead excluded</p><label>Find technician<input type="search" maxLength={100} value={search} onChange={e => { setSearch(e.target.value); setCursor(null); setPrevious([]); setSelected(null) }} /></label>{list.isLoading && <p>Loading technicians…</p>}{list.error && <p role="alert">{errorText(list.error)}</p>}{list.data?.items.map(item => <button className="jc-row" key={item.mechanic_id} onClick={() => setSelected(item)}><span><strong>{item.mechanic_name}</strong><small>{item.is_active ? 'Active' : 'Inactive — read only'}</small></span><span>{item.version ? `Schedule v${item.version}` : 'No cost rate'}</span></button>)}<nav className="jc-pagination"><button disabled={!previous.length} onClick={() => { setCursor(previous[previous.length - 1]); setPrevious(previous.slice(0, -1)); setSelected(null) }}>Previous technicians</button><button disabled={!list.data?.next_cursor} onClick={() => { setPrevious([...previous, cursor]); setCursor(list.data!.next_cursor); setSelected(null) }}>Next technicians</button></nav>{selected && <RateEditor key={selected.mechanic_id} identity={identity} selected={selected} read={read} write={write} timezone={timezone} activation={activation} close={() => setSelected(null)} />}</section>
}
interface Boundary { contract_version: 1; shop_timezone: string; local: string; fold: null | 0 | 1; effective_at: string; activation_at: string }
interface RateDraft { from: string; to: string; hourly_cost: string; inclusions: string; fromFold?: string; toFold?: string; fromAmbiguous?: boolean; toAmbiguous?: boolean; original?: { from: string; to: string; effective_from: string; effective_to: string | null } }
function localInput(utc: string, timezone: string): string {
  try {
    const parts = new Intl.DateTimeFormat('en-CA', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(utc))
    const get = (key: string) => parts.find(part => part.type === key)?.value ?? ''
    return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`
  } catch { return '' }
}
function scheduleDraft(policy: TechnicianPolicy, timezone?: string): RateDraft[] {
  const zone = timezone ?? policy.policy?.shop_timezone
  if (!policy.policy || !zone) return []
  return policy.policy.segments.map(segment => {
    const from = localInput(segment.effective_from, zone), to = segment.effective_to ? localInput(segment.effective_to, zone) : ''
    return { from, to, hourly_cost: segment.hourly_cost, inclusions: segment.inclusions, original: { from, to, effective_from: segment.effective_from, effective_to: segment.effective_to } }
  })
}
// Drafts stay local. Server resolves shop wall time; browser offsets are never applied.
function RateEditor({ identity, selected, read, write, timezone, activation, close }: { identity: string; selected: TechnicianPolicy; read: Read; write: Write; timezone?: string; activation?: string; close: () => void }) {
  const current = useQuery({ queryKey: [ROOT, identity, 'rate', selected.mechanic_id], queryFn: ({ signal }) => read<TechnicianPolicy>(`/reports/technician-costs/${selected.mechanic_id}`, {}, signal), retry: false, gcTime: 0 })
  const [segments, setSegments] = useState<RateDraft[]>(() => scheduleDraft(selected, timezone))
  const [version, setVersion] = useState(selected.version), [reason, setReason] = useState(''), [error, setError] = useState(''), [saving, setSaving] = useState(false), [key, setKey] = useState(() => crypto.randomUUID())
  const active = current.data ?? selected
  const zone = timezone ?? active.policy?.shop_timezone
  const start = active.policy?.activation_at ?? activation
  const changed = () => { setKey(crypto.randomUUID()); setError('') }
  const update = (index: number, patch: Partial<RateDraft>) => { setSegments(previous => previous.map((segment, i) => i === index ? { ...segment, ...patch } : segment)); changed() }
  const resolve = async (segment: RateDraft, index: number, boundary: 'from' | 'to'): Promise<string | null> => {
    const local = segment[boundary]
    if (!local && boundary === 'to') return null
    const original = segment.original
    if (original && local === original[boundary] && !segment[boundary === 'from' ? 'fromFold' : 'toFold']) return boundary === 'from' ? original.effective_from : original.effective_to
    const fold = segment[boundary === 'from' ? 'fromFold' : 'toFold']
    try {
      const resolved = await read<Boundary>('/reports/technician-costs/time-boundaries', { local, ...(fold ? { fold: Number(fold) } : {}) })
      if (zone && resolved.shop_timezone !== zone) throw Error('Shop timezone changed')
      return resolved.effective_at
    } catch (failure) {
      const detail = (failure as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      const code = typeof detail === 'string' ? detail : JSON.stringify(detail ?? '')
      if (code.includes('schedule_time_ambiguous')) {
        setSegments(previous => previous.map((item, i) => i === index ? { ...item, [boundary === 'from' ? 'fromAmbiguous' : 'toAmbiguous']: true } : item))
        throw Error(`Segment ${index + 1}: choose the first or second occurrence of this repeated shop time.`)
      }
      if (code.includes('schedule_time_nonexistent')) throw Error(`Segment ${index + 1}: that shop time does not exist because clocks move forward. Choose another time.`)
      throw Error(`Segment ${index + 1}: could not resolve shop time. Check the date and time, then retry.`)
    }
  }
  const submit = async () => {
    if (saving || !start || !zone) return
    if (!reason.trim() || reason.trim().length > 500) { setError('Enter a revision reason (1–500 characters).'); return }
    if (!segments.length || segments.some(segment => !segment.from || !segment.hourly_cost || !segment.inclusions.trim())) { setError('Complete each rate segment, including loaded cost and included employment costs.'); return }
    setSaving(true); setError('')
    try {
      const resolved = []
      for (let index = 0; index < segments.length; index++) {
        const segment = segments[index]
        resolved.push({ effective_from: (await resolve(segment, index, 'from'))!, effective_to: await resolve(segment, index, 'to'), hourly_cost: segment.hourly_cost, inclusions: segment.inclusions.trim() })
      }
      const invalid = validateSchedule(resolved, reason, start)
      if (invalid) { setError(invalid); return }
      await write(`/reports/technician-costs/${selected.mechanic_id}`, { expected_version: version, policy_version: 1, currency: 'USD', basis: 'owner_declared_loaded_direct', segments: resolved, reason: reason.trim() }, key)
      close()
    } catch (failure) { setError(failure instanceof Error && !status(failure) ? failure.message : errorText(failure)) } finally { setSaving(false) }
  }
  return <form className="jc-detail" aria-label="Technician rate schedule" onSubmit={event => { event.preventDefault(); void submit() }}>
    <header className="jc-toolbar"><h4>{selected.mechanic_name} · schedule v{version + 1}</h4><button type="button" onClick={close} disabled={saving}>Cancel</button></header>
    <p className="jc-muted">{zone ?? 'Shop timezone unavailable'} · Effective October 20, 2026 · Whole replacement schedule; previous revisions stay unchanged.</p>
    {current.error && <p role="alert">{errorText(current.error)}</p>}
    {active.policy && <details><summary><ChevronDown aria-hidden="true" size={16} />Current approved schedule v{active.version} · {active.policy.shop_timezone}</summary>{active.policy.segments.map((segment, index) => <p key={index}>{localInput(segment.effective_from, active.policy!.shop_timezone).replace('T', ' ')} – {segment.effective_to ? localInput(segment.effective_to, active.policy!.shop_timezone).replace('T', ' ') : 'open'} · {segment.hourly_cost} USD/hour · {segment.inclusions}</p>)}</details>}
    {current.data?.history?.length ? <details><summary><ChevronDown aria-hidden="true" size={16} />Revision history</summary>{current.data.history.map(revision => <p key={revision.revision_id}>Version {revision.version} · {new Date(revision.approved_at).toLocaleDateString('en-US', { timeZone: zone })}</p>)}</details> : null}
    {segments.map((segment, index) => <fieldset key={index} disabled={saving || !active.is_active}><legend>Rate segment {index + 1}</legend>
      <label>Effective from ({zone ?? 'shop time'})<input type="datetime-local" required value={segment.from} min={start && zone ? localInput(start, zone) : undefined} onChange={event => update(index, { from: event.target.value, fromFold: '', fromAmbiguous: false })} /></label>
      {segment.fromAmbiguous && <label>Repeated start time<select required value={segment.fromFold ?? ''} onChange={event => update(index, { fromFold: event.target.value })}><option value="">Choose occurrence</option><option value="0">First occurrence</option><option value="1">Second occurrence</option></select></label>}
      <label>Until (exclusive; blank means open-ended)<input type="datetime-local" value={segment.to} onChange={event => update(index, { to: event.target.value, toFold: '', toAmbiguous: false })} /></label>
      {segment.toAmbiguous && <label>Repeated end time<select required value={segment.toFold ?? ''} onChange={event => update(index, { toFold: event.target.value })}><option value="">Choose occurrence</option><option value="0">First occurrence</option><option value="1">Second occurrence</option></select></label>}
      <label>Loaded hourly cost (USD)<input required inputMode="decimal" value={segment.hourly_cost} onChange={event => update(index, { hourly_cost: event.target.value })} /></label>
      <label>Included direct employment costs<textarea required maxLength={500} value={segment.inclusions} onChange={event => update(index, { inclusions: event.target.value })} /></label>
      <button type="button" onClick={() => { setSegments(segments.filter((_, i) => i !== index)); changed() }}>Remove rate segment</button>
    </fieldset>)}
    <button type="button" disabled={saving || !active.is_active || !zone || !start || segments.length >= 100} onClick={() => { setSegments([...segments, { from: localInput(start!, zone!), to: '', hourly_cost: '', inclusions: '' }]); changed() }}>Add rate segment</button>
    <label>Revision reason<textarea required maxLength={500} value={reason} disabled={saving || !active.is_active} onChange={event => { setReason(event.target.value); changed() }} /></label>
    {active.version !== version && <p role="alert">Newer schedule available. Draft preserved. <button type="button" onClick={() => { setSegments(scheduleDraft(active, timezone)); setVersion(active.version); changed() }}>Replace draft with current schedule</button></p>}
    {error && <p role="alert">{error} <button type="button" disabled={saving} onClick={() => void current.refetch()}>Refresh current version</button></p>}
    <button disabled={saving || !active.is_active || !start || !zone || current.isLoading || Boolean(current.error) || active.version !== version}>{saving ? 'Saving revision…' : 'Append approved cost schedule'}</button>
  </form>
}
