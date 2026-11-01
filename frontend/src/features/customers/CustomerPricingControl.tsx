import { ControlButton, ControlInput } from '@/components/ui/Controls'
import PlatformSelect from '@/components/PlatformSelect'
import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import PartsPricingSettings from '@/features/parts-pricing/PartsPricingSettings'
import PricingFeedback from '@/features/parts-pricing/PricingFeedback'
import { matrixListSchema } from '@/features/parts-pricing/configuration'
import { pricingError, pricingMoney } from '@/features/parts-pricing/contract'
import { isPricingScopeCurrent, usePricingScope } from '@/features/parts-pricing/usePricingScope'
import { accountRate, customerHistorySchema, customerPolicySchema, policySourceLabel, type CustomerPricingPolicy } from '@/features/customer-pricing/contract'
import './customer-pricing.css'

function PolicyEditor({ customerId, scope }: { customerId: string; scope: string }) {
  const client = useQueryClient(); const abort = useRef(new AbortController())
  const [editing, setEditing] = useState(false); const [base, setBase] = useState<CustomerPricingPolicy | null>(null)
  const [rate, setRate] = useState(''); const [matrixId, setMatrixId] = useState(''); const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false); const [error, setError] = useState<{ message: string } | null>(null); const [saved, setSaved] = useState(false)
  const [fresh, setFresh] = useState<CustomerPricingPolicy | null>(null)
  const [history, setHistory] = useState(false); const [cursor, setCursor] = useState<string | null>(null)
  const [matricesOpen, setMatricesOpen] = useState(false); const matricesTrigger = useRef<HTMLButtonElement>(null)
  const editTrigger = useRef<HTMLButtonElement>(null); const restoreFocus = useRef(false)
  const attempt = useRef<{ body: string; id: string } | null>(null)
  const key = ['customer-pricing-policy', scope, customerId]
  const active = () => !abort.current.signal.aborted && isPricingScopeCurrent(scope)
  const read = async (signal: AbortSignal) => {
    const result = customerPolicySchema.parse((await api.get(`/customers/${customerId}/pricing-policy`, { signal })).data)
    if (result.customer_id !== customerId) throw new Error('Invalid customer pricing response')
    return result
  }
  const query = useQuery({ queryKey: key, queryFn: ({ signal }) => read(signal), gcTime: 0, retry: false, refetchOnWindowFocus: false })
  const matrices = useQuery({ queryKey: ['customer-pricing-matrices', scope], enabled: editing && Boolean(query.data?.can_edit), gcTime: 0, retry: false, queryFn: async ({ signal }) => {
    const items: ReturnType<typeof matrixListSchema.parse>['items'] = []; let cursor: string | null = null
    const seen = new Set<string>()
    do {
      const page = matrixListSchema.parse((await api.get('/parts-pricing/matrices', { signal, params: { include_archived: false, limit: 50, ...(cursor ? { cursor } : {}) } })).data)
      items.push(...page.items.filter(item => !item.archived_at)); cursor = page.next_cursor
      if (cursor && seen.has(cursor)) throw new Error('Invalid matrix page')
      if (cursor) seen.add(cursor)
    } while (cursor)
    return items
  } })
  const revisions = useQuery({ queryKey: ['customer-pricing-history', scope, customerId, cursor], enabled: history, gcTime: 0, retry: false, queryFn: async ({ signal }) => customerHistorySchema.parse((await api.get(`/customers/${customerId}/pricing-policy/history`, { signal, params: { limit: 25, ...(cursor ? { cursor } : {}) } })).data) })
  useEffect(() => { abort.current = new AbortController(); const controller = abort.current; return () => { controller.abort(); for (const prefix of ['customer-pricing-policy', 'customer-pricing-history', 'customer-pricing-matrices']) client.removeQueries({ queryKey: [prefix, scope] }) } }, [client, scope])
  useEffect(() => { if (!editing && restoreFocus.current) { editTrigger.current?.focus({ preventScroll: true }); restoreFocus.current = false } }, [editing])
  const edit = (policy: CustomerPricingPolicy) => { setBase(policy); setRate(policy.configured.labor_rate ?? ''); setMatrixId(policy.configured.parts_matrix_id ?? ''); setReason(''); setFresh(null); setError(null); setSaved(false); attempt.current = null; setEditing(true) }
  const cancel = () => { if (!busy) { restoreFocus.current = true; setEditing(false); setBase(null); setFresh(null); setError(null); setReason(''); attempt.current = null } }
  const save = async () => {
    if (!base || fresh || busy) return
    setError(null); setSaved(false); setBusy(true)
    try {
      const body = { expected_version: base.version, labor_rate: accountRate(rate), parts_matrix_id: matrixId || null, reason: reason.trim() }
      if (body.reason.length < 3 || body.reason.length > 500) throw new Error('Enter a reason of 3–500 characters.')
      const serialized = JSON.stringify(body); const id = attempt.current?.body === serialized ? attempt.current.id : crypto.randomUUID(); attempt.current = { body: serialized, id }
      const next = customerPolicySchema.parse((await api.put(`/customers/${customerId}/pricing-policy`, body, { signal: abort.current.signal, headers: { 'Idempotency-Key': id }, skipAuthRefresh: true })).data)
      if (next.customer_id !== customerId) throw new Error('Invalid customer pricing response')
      if (!active()) return
      client.setQueryData(key, next); void client.invalidateQueries({ queryKey: ['customer-pricing-intake', scope] }); void client.invalidateQueries({ queryKey: ['customer-pricing-history', scope, customerId] })
      restoreFocus.current = true; setEditing(false); setBase(null); setSaved(true); setReason(''); attempt.current = null
    } catch (failure) {
      if (!active()) return
      const status = (failure as { response?: { status?: number } }).response?.status
      if (status && status < 500) attempt.current = null
      if (status === 409) { try { const current = await read(abort.current.signal); if (active()) setFresh(current) } catch { /* The failed write never replaces the displayed draft. */ } }
      if (active()) setError({ message: pricingError(failure, failure instanceof Error ? failure.message : 'Pricing could not be saved. Your draft is kept.') })
    } finally { if (active()) setBusy(false) }
  }
  if (query.isPending) return <p role="status">Loading customer pricing…</p>
  if (query.isError || !query.data) return <p role="alert">Customer pricing unavailable. <ControlButton type="button" onClick={() => void query.refetch()}>Retry pricing</ControlButton></p>
  const policy = query.data
  const summary = (value: CustomerPricingPolicy) => <span>Labor {value.effective.labor.rate === null ? 'Internal' : `${pricingMoney(value.effective.labor.rate)}/hr`} · {policySourceLabel(value.effective.labor.source)}<br />Parts · {value.effective.parts.matrix?.name ?? (value.effective.parts.mode === 'internal' ? 'At cost' : 'Catalog')} · {policySourceLabel(value.effective.parts.source)}</span>
  return <section aria-label="Customer pricing" className="db-customer-pricing">
    <div className="db-customer-pricing__heading"><h3>Pricing</h3>{!editing && policy.can_edit && <ControlButton ref={editTrigger} type="button" onClick={() => edit(policy)}>Edit pricing</ControlButton>}<ControlButton type="button" onClick={() => { setHistory(value => !value); setCursor(null) }}>{history ? 'Hide history' : 'History'}</ControlButton></div>
    <div className="db-customer-pricing__summary">{summary(policy)}</div>{editing && <form aria-label="Customer pricing settings" onSubmit={event => { event.preventDefault(); void save() }} onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); cancel() } }}>
      <div className="db-customer-pricing__fields"><label>Labor rate / hr<ControlInput inputMode="decimal" placeholder="Use shop rate" value={rate} disabled={busy} onChange={event => setRate(event.target.value)} /></label><div className="db-customer-pricing__matrix"><label>Parts matrix<PlatformSelect value={matrixId} disabled={busy || matrices.isPending || matrices.isError} onChange={event => setMatrixId(event.target.value)}><option value="">Use shop default</option>{matrixId && !matrices.data?.some(item => item.id === matrixId) && <option value={matrixId}>{base?.effective.parts.matrix?.name ?? 'Selected matrix'}</option>}{!matrices.isError && matrices.data?.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</PlatformSelect></label><ControlButton ref={matricesTrigger} type="button" aria-label="Manage matrices" disabled={busy} onClick={() => setMatricesOpen(true)}>Manage</ControlButton></div></div>
      {matrices.isError && <p role="alert">Matrices unavailable. <ControlButton type="button" onClick={() => void matrices.refetch()}>Retry matrices</ControlButton></p>}
      <label>Reason<ControlInput value={reason} maxLength={500} disabled={busy} onChange={event => setReason(event.target.value)} /></label>
      {error && <PricingFeedback revision={error}>{error.message}{fresh && <div className="db-customer-pricing__conflict"><strong>Current saved pricing</strong><div>{summary(fresh)}</div><ControlButton type="button" onClick={() => { setBase(fresh); setFresh(null); setError(null); attempt.current = null }}>Keep draft against current version</ControlButton><ControlButton type="button" onClick={() => edit(fresh)}>Load saved values</ControlButton></div>}</PricingFeedback>}
      <div className="db-customer-pricing__actions"><ControlButton type="button" disabled={busy} onClick={cancel}>Cancel</ControlButton><ControlButton type="submit" disabled={busy || Boolean(fresh) || !base?.can_edit || matrices.isError || matrices.isPending}>{busy ? 'Saving…' : 'Save pricing'}</ControlButton></div>
    </form>}
    {!policy.can_edit ? <p>Internal account pricing is managed with the truck.</p> : <p className="db-customer-pricing__muted">New orders only. Saved work keeps its prices.</p>}
    {saved && <p role="status">Pricing saved.</p>}
    {history && <div className="db-customer-pricing__history">{revisions.isPending ? <p role="status">Loading pricing history…</p> : revisions.isError ? <p role="alert">Pricing history unavailable. <ControlButton type="button" onClick={() => void revisions.refetch()}>Retry history</ControlButton></p> : <>{!revisions.data?.items.length && <p>No pricing changes yet.</p>}{revisions.data?.items.map(item => <article key={item.id}><strong>{new Date(item.occurred_at).toLocaleString()} · {item.actor_display_name || 'Staff'}</strong><p>Labor {item.before.labor_rate === null ? 'Shop rate' : pricingMoney(item.before.labor_rate)} → {item.after.labor_rate === null ? 'Shop rate' : pricingMoney(item.after.labor_rate)} · Parts {item.after.parts_matrix_id === null ? 'Shop default' : 'Account matrix'}</p><p>{item.reason}</p></article>)}{cursor && <ControlButton type="button" onClick={() => setCursor(null)}>Latest changes</ControlButton>}{revisions.data?.next_cursor && <ControlButton type="button" onClick={() => setCursor(revisions.data!.next_cursor)}>Older changes</ControlButton>}</>}</div>}
    {matricesOpen && <PartsPricingSettings onClose={() => { setMatricesOpen(false); void matrices.refetch(); matricesTrigger.current?.focus() }} />}
  </section>
}

export default function CustomerPricingControl({ customerId }: { customerId: string }) {
  const scope = usePricingScope(); const role = useAuthStore(state => state.user?.role)
  if (role !== 'garage_owner' && role !== 'garage_admin') return null
  return <PolicyEditor key={`${scope}:${customerId}`} customerId={customerId} scope={scope} />
}
