import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, Plus } from 'lucide-react'
import { z } from 'zod'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { errorDetail } from '@/features/service-checklists/queries'
import { ExternalServiceReceipts } from './ExternalServiceReceipts'
import './external-services.css'

const fieldsSchema = z.object({
  provider_name: z.string().min(1).max(160),
  service_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).refine(value => {
    const parsed = new Date(`${value}T12:00:00Z`)
    return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value
  }),
  description: z.string().min(1).max(4000),
  odometer: z.number().int().min(0).max(99999999).nullable(), reference: z.string().max(100).nullable(),
  reported_cost: z.string().regex(/^\d+(\.\d{1,2})?$/).refine(value => Number(value) <= 9999999999.99).nullable(),
})
const recordSchema = fieldsSchema.extend({
  id: z.string(), vehicle_id: z.string(), original_vehicle_id: z.string(), source: z.literal('external'), currency: z.literal('USD'),
  version: z.number().int().positive(), voided_at: z.string().nullable(), created_at: z.string(), updated_at: z.string(),
  created_by_user_id: z.string().nullable(), created_by_name: z.string().nullable(),
  updated_by_user_id: z.string().nullable(), updated_by_name: z.string().nullable(),
})
const pageSchema = z.object({ items: z.array(recordSchema), total: z.number().int().nonnegative(), has_more: z.boolean() })
const resultSchema = z.object({ record: recordSchema, replayed: z.boolean() })
const eventSchema = z.object({ id: z.string(), record_id: z.string(), version: z.number().int(), action: z.enum(['create', 'update', 'void', 'restore']), actor_name: z.string().nullable(), created_at: z.string(), reason: z.string().nullable(), snapshot: fieldsSchema })
const eventsSchema = z.object({ items: z.array(eventSchema), total: z.number(), has_more: z.boolean() })
type ServiceRecord = z.infer<typeof recordSchema>
type Editor = { kind: 'create' | 'update' | 'void' | 'restore'; record?: ServiceRecord }
type Draft = { provider_name: string; service_date: string; description: string; odometer: string; reference: string; reported_cost: string }
const dateLabel = (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
const costLabel = (value: string | null) => value === null ? 'Cost not recorded' : `Reported cost $${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const canUse = (role: string) => ['garage_owner', 'garage_admin', 'receptionist'].includes(role)
const draftOf = (record?: ServiceRecord): Draft => ({ provider_name: record?.provider_name ?? '', service_date: record?.service_date ?? '', description: record?.description ?? '', odometer: record?.odometer?.toString() ?? '', reference: record?.reference ?? '', reported_cost: record?.reported_cost ?? '' })

export function ExternalServiceHistory({ vehicleId }: { vehicleId: string }) {
  const user = useAuthStore(state => state.user)
  const epoch = useAuthStore(state => state.authSessionEpoch)
  if (!user?.tenant_id || !canUse(user.role)) return null
  return <ScopedHistory key={`${user.tenant_id}:${user.id}:${user.role}:${epoch}:${vehicleId}`} vehicleId={vehicleId} scope={[user.tenant_id, user.id, user.role, epoch]} />
}

function ScopedHistory({ vehicleId, scope }: { vehicleId: string; scope: (string | number)[] }) {
  const client = useQueryClient()
  const [page, setPage] = useState(0)
  const [includeVoided, setIncludeVoided] = useState(false)
  const [editor, setEditor] = useState<Editor | null>(null)
  const [message, setMessage] = useState('')
  const trigger = useRef<HTMLButtonElement | null>(null)
  const addButton = useRef<HTMLButtonElement | null>(null)
  const path = `/vehicles/${vehicleId}/external-services`
  const prefix = ['external-services', ...scope, vehicleId]
  const query = useQuery({
    queryKey: [...prefix, page, includeVoided],
    queryFn: async ({ signal }) => {
      const result = pageSchema.parse((await api.get(path, { params: { skip: page * 10, limit: 10, include_voided: includeVoided }, signal })).data)
      if (result.items.some(item => item.vehicle_id !== vehicleId)) throw new Error('Invalid vehicle history')
      return result
    }, retry: false, staleTime: 0,
  })
  const openEditor = (next: Editor, button: HTMLButtonElement) => { trigger.current = button; setMessage(''); setEditor(next) }
  const closeEditor = () => { setEditor(null); requestAnimationFrame(() => (trigger.current?.isConnected ? trigger.current : addButton.current)?.focus()) }
  const accessDenied = [401, 403, 404].includes((query.error as { response?: { status?: number } } | null)?.response?.status ?? 0)
  return <section aria-label="Outside-shop service history" className="db-external-services">
    <div className="db-external-services__heading"><h3>Outside-shop history{query.data && !query.isError ? ` (${query.data.total})` : ''}</h3>
      <button ref={addButton} type="button" disabled={Boolean(editor) || !query.data || query.isError || query.isFetching} onClick={event => openEditor({ kind: 'create' }, event.currentTarget)}><Plus size={14} aria-hidden="true" />Add outside service</button>
    </div>
    <p className="db-external-services__muted">Work performed elsewhere · Not billed by this shop.</p>
    {message && <p role="status" className="db-external-services__success">{message}</p>}
    {query.isPending && <p role="status">Loading outside-shop history…</p>}
    {query.isError && <div role="alert">Could not load outside-shop history. <button type="button" disabled={query.isFetching} onClick={() => void query.refetch()}>Retry outside history</button></div>}
    {editor && accessDenied && <button type="button" onClick={closeEditor}>Close service editor</button>}
    {editor && !accessDenied && <ServiceEditor key={`${editor.kind}:${editor.record?.id ?? 'new'}`} editor={editor} path={path} vehicleId={vehicleId} disabled={query.isError || query.isFetching} onCancel={closeEditor}
      onWriteError={() => { void client.invalidateQueries({ queryKey: prefix }) }}
      refresh={async () => { const result = await query.refetch(); if (result.isError) throw new Error('Could not refresh the record.'); return result.data?.items.find(item => item.id === editor.record?.id) }}
      onSaved={result => {
        if (result.record.vehicle_id !== vehicleId) throw new Error('Invalid saved vehicle')
        setMessage(result.replayed ? 'Save confirmed. No duplicate added.' : editor.kind === 'void' ? 'Service voided. You can restore it from Show voided.' : editor.kind === 'restore' ? 'Service restored.' : 'Outside service saved.')
        closeEditor()
        void client.invalidateQueries({ queryKey: prefix })
      }} />}
    <label className="db-external-services__toggle"><input type="checkbox" checked={includeVoided} disabled={Boolean(editor)} onChange={event => { setIncludeVoided(event.target.checked); setPage(0) }} />Show voided</label>
    {query.data && !query.isError && <>
      {!query.data.items.length && <p className="db-external-services__muted">No outside-shop services recorded{includeVoided ? '.' : ' for this vehicle.'}</p>}
      <ul className="db-external-services__list">{query.data.items.map(record => <li key={record.id}>
        <div className="db-external-services__row"><div><strong>{record.provider_name}</strong><span className="db-external-services__meta"><time dateTime={record.service_date}>{dateLabel(record.service_date)}</time><span>Outside shop</span>{record.voided_at && <b>Voided</b>}</span></div><span className="db-external-services__cost">{costLabel(record.reported_cost)}</span></div>
        <p className="db-external-services__description">{record.description}</p>
        {(record.odometer !== null || record.reference) && <p className="db-external-services__meta">{record.odometer !== null && <span>{record.odometer.toLocaleString()} mi</span>}{record.reference && <span>Ref: {record.reference}</span>}</p>}
        <div className="db-external-services__actions"><span className="db-external-services__muted">Recorded by {record.created_by_name || 'Staff'}</span>
          {record.voided_at ? <button type="button" disabled={Boolean(editor) || query.isFetching} aria-label={`Restore service from ${record.provider_name}`} onClick={event => openEditor({ kind: 'restore', record }, event.currentTarget)}>Restore</button> : <>
            <button type="button" disabled={Boolean(editor) || query.isFetching} aria-label={`Edit service from ${record.provider_name}`} onClick={event => openEditor({ kind: 'update', record }, event.currentTarget)}>Edit</button>
            <button type="button" disabled={Boolean(editor) || query.isFetching} aria-label={`Void service from ${record.provider_name}`} onClick={event => openEditor({ kind: 'void', record }, event.currentTarget)}>Void</button>
          </>}
        </div>
        <ExternalServiceReceipts vehicleId={vehicleId} recordId={record.id} recordVersion={record.version} voidedAt={record.voided_at} providerName={record.provider_name} disabled={Boolean(editor) || query.isFetching} />
        <RecordHistory record={record} path={path} scope={scope} />
      </li>)}</ul>
      {(page > 0 || query.data.has_more) && <nav aria-label="Outside service pages" className="db-external-services__actions">
        <button type="button" disabled={!page || query.isFetching || Boolean(editor)} onClick={() => setPage(value => value - 1)}>Previous services</button><span>Page {page + 1}</span><button type="button" disabled={!query.data.has_more || query.isFetching || Boolean(editor)} onClick={() => setPage(value => value + 1)}>Next services</button>
      </nav>}
    </>}
  </section>
}

function ServiceEditor({ editor, path, vehicleId, disabled, onCancel, onSaved, onWriteError, refresh }: {
  editor: Editor; path: string; vehicleId: string; disabled: boolean; onCancel: () => void;
  onSaved: (result: z.infer<typeof resultSchema>) => void; refresh: () => Promise<ServiceRecord | undefined>;
  onWriteError: () => void;
}) {
  const [draft, setDraft] = useState<Draft>(() => draftOf(editor.record))
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const [version, setVersion] = useState(editor.record?.version)
  const [latest, setLatest] = useState<ServiceRecord | null>(null)
  const [conflict, setConflict] = useState(false)
  const attempt = useRef<{ fingerprint: string; body: Record<string, unknown> } | null>(null)
  const posting = useRef(false)
  const isFields = editor.kind === 'create' || editor.kind === 'update'
  const field = (key: keyof Draft, value: string) => setDraft(current => ({ ...current, [key]: value }))
  const business = () => ({ provider_name: draft.provider_name.trim(), service_date: draft.service_date, description: draft.description.trim(), odometer: draft.odometer.trim() === '' ? null : Number(draft.odometer), reference: draft.reference.trim() || null, reported_cost: draft.reported_cost.trim() === '' ? null : Number(draft.reported_cost).toFixed(2) })
  const unchanged = editor.kind === 'update' && JSON.stringify(business()) === JSON.stringify({ ...draftOf(editor.record), odometer: editor.record?.odometer ?? null, reference: editor.record?.reference ?? null, reported_cost: editor.record?.reported_cost === null ? null : Number(editor.record?.reported_cost).toFixed(2) })
  const submit = async () => {
    if (posting.current || disabled || unchanged) return
    setError('')
    if (isFields && (!draft.provider_name.trim() || !draft.description.trim() || !draft.service_date)) { setError('Enter a service date, outside shop and work performed.'); return }
    if (isFields && draft.odometer.trim() && (!/^\d+$/.test(draft.odometer.trim()) || Number(draft.odometer) > 99999999)) { setError('Mileage must be a whole number from 0 to 99,999,999.'); return }
    if (isFields && draft.reported_cost.trim() && (!/^\d+(\.\d{1,2})?$/.test(draft.reported_cost.trim()) || Number(draft.reported_cost) > 9999999999.99)) { setError('Reported cost must be a positive amount or zero, with up to two decimals.'); return }
    if (editor.kind === 'void' && !reason.trim()) { setError('Enter a reason for voiding this service.'); return }
    const payload = { ...(isFields ? business() : {}), ...(editor.kind === 'void' ? { reason: reason.trim() } : {}), ...(editor.kind !== 'create' ? { expected_version: version } : {}) }
    const fingerprint = JSON.stringify(payload)
    if (!attempt.current || attempt.current.fingerprint !== fingerprint) attempt.current = { fingerprint, body: { ...payload, request_id: crypto.randomUUID() } }
    posting.current = true; setPending(true)
    try {
      const url = editor.kind === 'create' ? path : `${path}/${editor.record!.id}${isFields ? '' : `/${editor.kind}`}`
      const response = editor.kind === 'update' ? await api.put(url, attempt.current.body) : await api.post(url, attempt.current.body)
      const result = resultSchema.parse(response.data)
      if (result.record.vehicle_id !== vehicleId || (editor.record && result.record.id !== editor.record.id)) throw new Error('Invalid saved record')
      onSaved(result)
    } catch (failure) {
      const status = (failure as { response?: { status?: number } }).response?.status
      setConflict(status === 409)
      setError(errorDetail(failure, 'Save could not be confirmed. Your draft is kept. Retry to confirm without adding a duplicate.'))
      onWriteError()
    } finally { posting.current = false; setPending(false) }
  }
  const title = { create: 'Add outside service', update: 'Edit outside service', void: 'Void outside service', restore: 'Restore outside service' }[editor.kind]
  return <form aria-label={title} className="db-external-services__editor" onSubmit={event => { event.preventDefault(); void submit() }} onKeyDown={event => { if (event.key === 'Escape' && !pending) { event.preventDefault(); event.stopPropagation(); onCancel() } }}>
    <h4>{title}</h4>
    {isFields ? <div className="db-external-services__fields">
      <label>Outside shop<input autoFocus required maxLength={160} value={draft.provider_name} disabled={pending} onChange={event => field('provider_name', event.target.value)} /></label>
      <label>Service date<input type="date" required min="1900-01-01" value={draft.service_date} disabled={pending} onChange={event => field('service_date', event.target.value)} /></label>
      <label className="db-external-services__wide">Work performed<textarea rows={3} required maxLength={4000} value={draft.description} disabled={pending} onChange={event => field('description', event.target.value)} /></label>
      <label>Mileage at service<input inputMode="numeric" placeholder="Optional" value={draft.odometer} disabled={pending} onChange={event => field('odometer', event.target.value)} /></label>
      <label>Reported cost (USD)<input inputMode="decimal" placeholder="Unknown" value={draft.reported_cost} disabled={pending} onChange={event => field('reported_cost', event.target.value)} /></label>
      <label className="db-external-services__wide">Reference<input maxLength={100} placeholder="Optional invoice or work reference" value={draft.reference} disabled={pending} onChange={event => field('reference', event.target.value)} /></label>
      <p className="db-external-services__wide db-external-services__muted">Historical record only. Current mileage, maintenance schedule and billing stay unchanged.</p>
    </div> : <>
      <p>{editor.record?.provider_name} · {dateLabel(editor.record!.service_date)}</p>
      <p className="db-external-services__muted">{editor.kind === 'void' ? 'This removes the service from active history. The record and changes are kept; you can restore it.' : 'This returns the service to active outside-shop history.'}</p>
      {editor.kind === 'void' && <label>Reason<textarea autoFocus rows={2} required maxLength={500} disabled={pending} value={reason} onChange={event => setReason(event.target.value)} /></label>}
    </>}
    {error && <p role="alert">{error}</p>}
    {conflict && editor.record && <button type="button" disabled={pending || disabled} onClick={async () => { try { const record = await refresh(); if (!record) throw new Error('This record is no longer in this list. Cancel and reopen it from the current history.'); setLatest(record) } catch (failure) { setError((failure as Error).message) } }}>Refresh record</button>}
    {latest && <aside className="db-external-services__latest"><strong>Latest saved version {latest.version}{latest.voided_at ? ' · Voided' : ''}</strong><p>{latest.provider_name} · {dateLabel(latest.service_date)}</p><p>{latest.description}</p><p>{costLabel(latest.reported_cost)}{latest.odometer !== null ? ` · ${latest.odometer.toLocaleString()} mi` : ''}{latest.reference ? ` · ${latest.reference}` : ''}</p>
      <button type="button" disabled={Boolean(latest.voided_at) !== (editor.kind === 'restore')} onClick={() => { setVersion(latest.version); attempt.current = null; setConflict(false); setError(''); setLatest(null) }}>Apply to latest version</button>
    </aside>}
    <div className="db-external-services__actions"><button type="button" disabled={pending} onClick={onCancel}>Cancel</button><button type="submit" autoFocus={editor.kind === 'restore'} disabled={pending || disabled || unchanged} className="db-external-services__primary">{pending ? 'Saving…' : error ? 'Retry save' : editor.kind === 'void' ? 'Void service' : editor.kind === 'restore' ? 'Restore service' : 'Save service'}</button></div>
  </form>
}

function RecordHistory({ record, path, scope }: { record: ServiceRecord; path: string; scope: (string | number)[] }) {
  const [open, setOpen] = useState(false)
  const [page, setPage] = useState(0)
  const history = useQuery({ queryKey: ['external-service-history', ...scope, record.vehicle_id, record.id, record.version, page], enabled: open, retry: false,
    queryFn: async ({ signal }) => {
      const result = eventsSchema.parse((await api.get(`${path}/${record.id}/history`, { params: { skip: page * 10, limit: 10 }, signal })).data)
      if (result.items.some(event => event.record_id !== record.id)) throw new Error('Invalid service history')
      return result
    },
  })
  const labels = { create: 'Recorded', update: 'Edited', void: 'Voided', restore: 'Restored' }
  return <div className="db-external-services__audit"><button type="button" aria-expanded={open} aria-label={`Change history for ${record.provider_name}`} onClick={() => setOpen(value => !value)}><ChevronRight size={14} className={open ? 'rotate-90' : ''} aria-hidden="true" />Change history</button>
    {open && <>
      {history.isPending && <p role="status">Loading changes…</p>}
      {history.isError && <div role="alert">Could not load changes. <button type="button" onClick={() => void history.refetch()}>Retry changes</button></div>}
      {history.data && !history.isError && <><ol>{history.data.items.map(event => <li key={event.id}><div><strong>{labels[event.action]}</strong> · {event.actor_name || 'Staff'} · <time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString()}</time></div>{event.reason && <p>{event.reason}</p>}<p>{dateLabel(event.snapshot.service_date)} · {event.snapshot.provider_name}</p><p className="db-external-services__description">{event.snapshot.description}</p><p>{costLabel(event.snapshot.reported_cost)}{event.snapshot.odometer !== null ? ` · ${event.snapshot.odometer.toLocaleString()} mi` : ''}{event.snapshot.reference ? ` · Ref: ${event.snapshot.reference}` : ''}</p></li>)}</ol>
        {(page > 0 || history.data.has_more) && <nav aria-label={`Changes for ${record.provider_name}`} className="db-external-services__actions"><button type="button" disabled={!page || history.isFetching} onClick={() => setPage(value => value - 1)}>Newer changes</button><button type="button" disabled={!history.data.has_more || history.isFetching} onClick={() => setPage(value => value + 1)}>Older changes</button></nav>}
      </>}
    </>}
  </div>
}
