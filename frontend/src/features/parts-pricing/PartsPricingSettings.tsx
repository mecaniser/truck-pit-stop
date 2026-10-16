import { useEffect, useRef, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import SlidePanelForm from '@/components/SlidePanelForm'
import PricingFeedback from './PricingFeedback'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { pricingError, pricingMoney, type PricingBand } from './contract'
import { defaultSchema, enteredMoney, historySchema, matrixDetailSchema, matrixListSchema, sampleSchema, type MatrixDetail } from './configuration'
import { isPricingScopeCurrent, usePricingScope } from './usePricingScope'
import './parts-pricing.css'

type BandDraft = { min_cost: string; max_cost: string; markup_percent: string }
const emptyBands = (): BandDraft[] => [{ min_cost: '0.00', max_cost: '', markup_percent: '' }]
function Settings({ onClose, scope }: { onClose: () => void; scope: string }) {
  const qc = useQueryClient()
  const [selection, setSelection] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [archived, setArchived] = useState(false)
  const [cursor, setCursor] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [bands, setBands] = useState<BandDraft[]>(emptyBands)
  const [base, setBase] = useState<MatrixDetail | null>(null)
  const [fresh, setFresh] = useState<MatrixDetail | null>(null)
  const [error, setError] = useState<{ message: string; location: 'general' | 'sample' } | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [history, setHistory] = useState(false)
  const [historyCursor, setHistoryCursor] = useState<string | null>(null)
  const [sampleCost, setSampleCost] = useState('')
  const [sampleCatalog, setSampleCatalog] = useState('')
  const [sample, setSample] = useState<ReturnType<typeof sampleSchema.parse> | null>(null)
  const [defaultReview, setDefaultReview] = useState(false)
  const controller = useRef(new AbortController())
  const active = () => !controller.current.signal.aborted && isPricingScopeCurrent(scope)
  const attempt = useRef<{ key: string; id: string } | null>(null)
  useEffect(() => { controller.current = new AbortController(); const active = controller.current; return () => { active.abort(); qc.removeQueries({ queryKey: ['parts-pricing-settings', scope] }) } }, [qc, scope])
  const query = useQuery({ queryKey: ['parts-pricing-settings', scope, 'matrices', archived, cursor], queryFn: async ({ signal }) => matrixListSchema.parse((await api.get('/parts-pricing/matrices', { signal, params: { include_archived: archived, limit: 50, ...(cursor ? { cursor } : {}) } })).data), gcTime: 0, retry: false })
  const policy = useQuery({ queryKey: ['parts-pricing-settings', scope, 'default'], queryFn: async ({ signal }) => defaultSchema.parse((await api.get('/parts-pricing/default', { signal })).data), gcTime: 0, retry: false })
  const revisions = useQuery({ queryKey: ['parts-pricing-settings', scope, 'history', selection, historyCursor], queryFn: async ({ signal }) => historySchema.parse((await api.get(`/parts-pricing/matrices/${selection}/revisions`, { signal, params: { limit: 20, ...(historyCursor ? { cursor: historyCursor } : {}) } })).data), enabled: history && Boolean(selection), gcTime: 0, retry: false })
  const reset = () => { setSelection(null); setBase(null); setFresh(null); setCreating(false); setError(null); setNotice(null); setHistory(false); setHistoryCursor(null); setSample(null); setDefaultReview(false); attempt.current = null }
  const load = async (id: string) => {
    reset(); setBusy(true)
    try { const result = matrixDetailSchema.parse((await api.get(`/parts-pricing/matrices/${id}`, { signal: controller.current.signal })).data).matrix; if (result.id !== id) throw new Error('Invalid matrix identity'); if (!active()) return; setSelection(id); setBase(result); setName(result.name); setBands(result.bands.map(band => ({ ...band, max_cost: band.max_cost ?? '' }))) }
    catch (cause) { if (active()) setError({ message: pricingError(cause, 'This matrix could not be loaded.'), location: 'general' }) }
    finally { if (active()) setBusy(false) }
  }
  const normalizedBands = (): PricingBand[] => bands.map(band => ({ min_cost: enteredMoney(band.min_cost) ?? '0.00', max_cost: enteredMoney(band.max_cost), markup_percent: band.markup_percent.trim() }))
  const refresh = async () => { setCursor(null); await qc.invalidateQueries({ queryKey: ['parts-pricing-settings', scope] }) }
  const write = async (path: string, method: 'post' | 'put', body: unknown, message: string) => {
    if (busy) return
    const key = JSON.stringify([path, body]); const id = attempt.current?.key === key ? attempt.current.id : crypto.randomUUID()
    attempt.current = { key, id }; setBusy(true); setError(null); setNotice(null)
    try {
      const response = await api[method](path, body, { signal: controller.current.signal, headers: { 'Idempotency-Key': id }, skipAuthRefresh: true })
      if (!active()) return
      if (path.endsWith('/default')) defaultSchema.parse(response.data)
      else { const result = matrixDetailSchema.parse(response.data).matrix; if (selection && result.id !== selection) throw new Error('Invalid matrix identity'); setBase(result); setSelection(result.id); setCreating(false) }
      attempt.current = null; setDefaultReview(false); setSample(null); setNotice(message); await refresh()
    } catch (cause) {
      if (!active()) return
      const status = (cause as { response?: { status?: number } }).response?.status
      if (status === 409) {
        attempt.current = null; setDefaultReview(false)
        await refresh()
        if (selection) { try { const fresh = matrixDetailSchema.parse((await api.get(`/parts-pricing/matrices/${selection}`, { signal: controller.current.signal })).data).matrix; if (active() && fresh.id === selection) setFresh(fresh) } catch { /* Preserve the draft, never substitute another entity. */ } }
      }
      if (!active()) return
      setError({ message: `${pricingError(cause, cause instanceof Error ? cause.message : 'Changes could not be saved.')}${status === 409 ? ' Your draft is kept. Review the current version before saving again.' : ''}`, location: 'general' })
    } finally { if (active()) setBusy(false) }
  }
  const save = () => {
    if (fresh) return
    try { const body = { name: name.trim(), bands: normalizedBands(), ...(base ? { expected_version: base.version } : {}) }; void write(base ? `/parts-pricing/matrices/${base.id}` : '/parts-pricing/matrices', base ? 'put' : 'post', body, 'Matrix saved. Default selection is separate.') } catch (cause) { setError({ message: (cause as Error).message, location: 'general' }) }
  }
  const preview = async () => {
    setBusy(true); setError(null); setSample(null)
    try { const result = sampleSchema.parse((await api.post('/parts-pricing/preview', { mode: 'samples', bands: normalizedBands(), samples: [{ sample_key: 'sample', label: 'Sample part', actual_unit_cost: enteredMoney(sampleCost), catalog_unit_price: enteredMoney(sampleCatalog) }] }, { signal: controller.current.signal })).data); if (result.cases.length !== 1 || result.cases[0].sample_key !== 'sample') throw new Error('Invalid sample response'); if (active()) setSample(result) }
    catch (cause) { if (active()) setError({ message: pricingError(cause, cause instanceof Error ? cause.message : 'Preview unavailable.'), location: 'sample' }) }
    finally { if (active()) setBusy(false) }
  }
  return <SlidePanelForm portalToShell isOpen onClose={() => { if (!busy) onClose() }} title="Parts pricing" category="Inventory" panelClassName="db-parts-pricing" overlayClassName="db-parts-pricing-overlay" width="sm:w-[680px]" hideFooter>
    {error?.location === 'general' && <PricingFeedback revision={error}>{error.message}</PricingFeedback>}{fresh && <div className="db-parts-pricing__confirm"><strong>Current saved matrix · {fresh.name}</strong><p className="db-parts-pricing__muted">Revision {fresh.current_revision} · {fresh.archived_at ? 'Archived' : 'Active'}</p>{fresh.bands.map((band, index) => <p key={index}>{pricingMoney(band.min_cost)}–{band.max_cost === null ? '∞' : pricingMoney(band.max_cost)} · {band.markup_percent}% markup</p>)}<button type="button" onClick={() => { setBase(fresh); setFresh(null); setError(null) }}>Keep my draft against this version</button><button type="button" onClick={() => { setBase(fresh); setName(fresh.name); setBands(fresh.bands.map(band => ({ ...band, max_cost: band.max_cost ?? '' }))); setFresh(null); setError(null) }}>Load saved values</button></div>}{notice && <p role="status">{notice}</p>}
    {!creating && !selection ? <>
      {policy.data?.matrix_id === null && !policy.isError && <p className="db-parts-pricing__muted">No default — using catalog prices.</p>}
      <div className="db-parts-pricing__toolbar"><label className="db-parts-pricing__check"><input type="checkbox" checked={archived} onChange={event => { setArchived(event.target.checked); setCursor(null) }} />Show archived</label><button type="button" disabled={busy} onClick={() => { reset(); setCreating(true); setName(''); setBands(emptyBands()) }}><Plus size={16} />New matrix</button></div>
      {query.isPending && <p role="status">Loading matrices…</p>}{query.isError && <p role="alert">Matrices unavailable. <button type="button" onClick={() => void query.refetch()}>Retry</button></p>}
      {!query.isError && query.data && <><ul className="db-parts-pricing__quote-lines">{query.data.items.map(matrix => <li key={matrix.id}><button type="button" disabled={busy} onClick={() => void load(matrix.id)}>{matrix.name}</button><span>{matrix.is_default ? 'Default' : matrix.archived_at ? 'Archived' : 'Inactive'} · v{matrix.current_revision}</span></li>)}</ul>{!query.data.items.length && <p className="db-parts-pricing__muted">No matrices yet.</p>}<div className="db-parts-pricing__actions">{cursor && <button type="button" onClick={() => setCursor(null)}>First page</button>}{query.data.next_cursor && <button type="button" onClick={() => setCursor(query.data!.next_cursor)}>Next page</button>}</div></>}
    </> : <>
      <div className="db-parts-pricing__toolbar"><button type="button" disabled={busy} onClick={reset}>All matrices</button><span className="db-parts-pricing__muted">{base ? `Revision ${base.current_revision} · ${base.archived_at ? 'Archived' : policy.data?.matrix_id === base.id ? 'Default' : 'Inactive'}` : 'New · inactive until selected'}</span></div>
      <label>Name<input value={name} maxLength={100} onChange={event => { setName(event.target.value); setSample(null) }} disabled={busy || Boolean(base?.archived_at)} /></label>
      <div className="db-parts-pricing__bands"><div className="db-parts-pricing__band-labels"><span>Cost from</span><span>Under</span><span>Markup %</span><span /></div>{bands.map((band, index) => <div className="db-parts-pricing__band" key={index}>{(['min_cost', 'max_cost', 'markup_percent'] as const).map(field => <label key={field}><span className="db-parts-pricing__mobile-label">{field === 'min_cost' ? 'Cost from' : field === 'max_cost' ? 'Under' : 'Markup %'}</span><input aria-label={`${field === 'min_cost' ? 'Cost from' : field === 'max_cost' ? 'Cost to' : 'Markup percent'} band ${index + 1}`} inputMode="decimal" placeholder={field === 'max_cost' ? 'No limit' : '0'} value={band[field]} disabled={busy || Boolean(base?.archived_at)} onChange={event => { setBands(current => current.map((item, row) => row === index ? { ...item, [field]: event.target.value } : item)); setSample(null) }} /></label>)}<button type="button" aria-label={`Remove band ${index + 1}`} disabled={busy || bands.length === 1 || Boolean(base?.archived_at)} onClick={() => { setBands(current => current.filter((_, row) => row !== index)); setSample(null) }}><Trash2 size={16} /></button></div>)}</div>
      <div className="db-parts-pricing__actions"><button type="button" disabled={busy || bands.length >= 30 || Boolean(base?.archived_at)} onClick={() => { setBands(current => [...current, { min_cost: current[current.length - 1]?.max_cost || '', max_cost: '', markup_percent: '' }]); setSample(null) }}>Add band</button><button type="button" disabled={busy || Boolean(fresh) || !name.trim() || Boolean(base?.archived_at)} onClick={save}>Save matrix</button></div>
      <div className="db-parts-pricing__sample"><strong>Sample preview</strong><div className="db-parts-pricing__fields"><label>Actual cost<input inputMode="decimal" placeholder="Unknown" disabled={busy} value={sampleCost} onChange={event => { setSampleCost(event.target.value); setSample(null) }} /></label><label>Catalog price<input inputMode="decimal" placeholder="Unknown" disabled={busy} value={sampleCatalog} onChange={event => { setSampleCatalog(event.target.value); setSample(null) }} /></label></div><button type="button" disabled={busy} onClick={() => void preview()}>Preview sample</button>{error?.location === 'sample' && <PricingFeedback revision={error}>{error.message}</PricingFeedback>}{sample && <PricingFeedback role="status" revision={sample}>{sample.cases.map(item => <div key={item.sample_key}><div className="db-parts-pricing__total"><span>Current {pricingMoney(item.current.unit_price)}</span><strong>Proposed {pricingMoney(item.proposed.unit_price)}</strong></div><p className="db-parts-pricing__muted">Profit {pricingMoney(item.proposed.gross_profit)} · Markup {item.proposed.markup_percent ?? '—'}% · Margin {item.proposed.margin_percent ?? '—'}%</p>{[...item.proposed.warnings, ...item.proposed.errors].map((warning, index) => <p key={index}>{warning.message}</p>)}</div>)}</PricingFeedback>}</div>
      {base && <>{policy.data?.matrix_id === base.id && <p className="db-parts-pricing__muted">Clear or replace the default before archiving.</p>}<div className="db-parts-pricing__actions"><button type="button" disabled={busy} onClick={() => { setHistory(value => !value); setHistoryCursor(null) }}>{history ? 'Hide history' : 'History'}</button><button type="button" disabled={busy || policy.isError || !policy.data || Boolean(base.archived_at)} onClick={() => setDefaultReview(true)}>{policy.data?.matrix_id === base.id ? 'Clear default' : 'Use as default'}</button><button type="button" disabled={busy || policy.isError || !policy.data || policy.data.matrix_id === base.id} onClick={() => void write(`/parts-pricing/matrices/${base.id}/${base.archived_at ? 'restore' : 'archive'}`, 'post', { expected_version: base.version }, base.archived_at ? 'Matrix restored.' : 'Matrix archived.')}>{base.archived_at ? 'Restore' : 'Archive'}</button></div>
      {defaultReview && policy.data && !policy.isError && <div className="db-parts-pricing__confirm"><p>{policy.data.matrix_id === base.id ? 'Clear the default for future parts?' : `Use ${base.name} for future parts?`} Saved lines keep their prices.</p><button type="button" disabled={busy} onClick={() => setDefaultReview(false)}>Cancel</button><button type="button" disabled={busy} onClick={() => void write('/parts-pricing/default', 'put', { matrix_id: policy.data!.matrix_id === base.id ? null : base.id, expected_generation: policy.data!.generation }, 'Default updated for future parts.')}>Confirm default</button></div>}
      {history && <div>{revisions.isPending && <p role="status">Loading history…</p>}{revisions.isError && <p role="alert">History unavailable.</p>}{!revisions.isError && revisions.data?.items.map(revision => <div className="db-parts-pricing__revision" key={revision.id}><strong>Revision {revision.revision} · {revision.name}</strong><small>{new Date(revision.created_at).toLocaleString()}</small>{revision.bands.map((band, index) => <p key={index}>{pricingMoney(band.min_cost)}–{band.max_cost === null ? '∞' : pricingMoney(band.max_cost)} · {band.markup_percent}% markup</p>)}</div>)}{revisions.data?.next_cursor && <button type="button" onClick={() => setHistoryCursor(revisions.data!.next_cursor)}>Older revisions</button>}</div>}</>}
    </>}
  </SlidePanelForm>
}
export default function PartsPricingSettings({ onClose }: { onClose: () => void }) {
  const scope = usePricingScope(); const role = useAuthStore(state => state.user?.role)
  if (role !== 'garage_owner' && role !== 'garage_admin') return null
  return <Settings key={scope} scope={scope} onClose={onClose} />
}
