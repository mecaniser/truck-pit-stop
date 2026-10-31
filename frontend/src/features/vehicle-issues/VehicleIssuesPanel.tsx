import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useLocation } from 'react-router-dom'
import { ArrowUpRight, ChevronLeft, ChevronRight, Plus, RotateCcw, X } from 'lucide-react'
import api from '@/lib/api'
import DatePicker from '@/components/DatePicker'
import { useAuthStore } from '@/stores/authStore'
import { usePricingScope, isPricingScopeCurrent } from '@/features/parts-pricing/usePricingScope'
import { appearanceTokenRecord, useTheme } from '@/contexts/ThemeContext'
import ShopWorkSelect from '@/features/dashboard/ShopWorkSelect'
import { recommendationLink, revealWorkspaceContent } from '@/features/repair-orders/recommendationConversion'
import { draftFor, emptyDraft, issueError, issueFields, mutationSchema, ownersSchema, scopedIssue, scopedPage, type IssueDraft, type IssueState, type VehicleIssue } from './contract'
import { useIssueDraftGuard } from './useIssueDraftGuard'
import { readTruckIssueRestore, readTruckIssueReturn, type TruckIssueReturn } from './navigation'
import './vehicleIssues.css'

type Props = { vehicleId: string; customerId?: string; contextOrderId?: string }
type Action = 'view' | 'create' | 'edit' | 'resolved' | 'dismissed' | 'open' | 'link' | 'end'
type Command = { path: string; method: 'post' | 'patch'; body: Record<string, unknown>; issueId?: string }
const stateOptions = [{ value: 'open', label: 'Open' }, { value: 'resolved', label: 'Resolved' }, { value: 'dismissed', label: 'Dismissed' }, { value: 'all', label: 'All issues' }] as const
const priorityOptions = [{ value: 'urgent', label: 'Urgent' }, { value: 'soon', label: 'Soon' }, { value: 'monitor', label: 'Monitor' }]
const actionLabels: Record<Action, string> = { view: 'Truck issue', create: 'Add issue', edit: 'Edit issue', resolved: 'Resolve issue', dismissed: 'Dismiss issue', open: 'Reopen issue', link: 'Link this visit', end: 'End visit link' }

export default function VehicleIssuesPanel(props: Props) {
  const scope = usePricingScope()
  const user = useAuthStore(state => state.user)
  const loggingOut = useAuthStore(state => state.logoutInProgress)
  const authenticated = useAuthStore(state => state.isAuthenticated)
  if (!authenticated || !user?.is_active || !user.tenant_id || loggingOut || !['garage_owner', 'garage_admin', 'receptionist'].includes(user.role)) return null
  return <IssueContext key={JSON.stringify([scope, props.vehicleId, props.customerId, props.contextOrderId])} {...props} scope={scope} />
}

function IssueContext({ vehicleId, customerId, contextOrderId, scope }: Props & { scope: string }) {
  const client = useQueryClient()
  const location = useLocation()
  const restored = readTruckIssueRestore(location.state, scope, vehicleId)
  const [filter, setFilter] = useState<IssueState | 'all'>(restored?.filter ?? 'open')
  const [skip, setSkip] = useState(restored?.skip ?? 0)
  const [selected, setSelected] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const rows = useRef(new Map<string, HTMLButtonElement>())
  const restoredFocus = useRef<string | null>(null)
  const prefix = useMemo(() => ['vehicle-issues', scope, vehicleId] as const, [scope, vehicleId])
  const context = useMemo(() => ({ customer_id: customerId, context_order_id: contextOrderId }), [customerId, contextOrderId])
  const base = `/vehicles/${vehicleId}/issues`
  const query = useQuery({
    queryKey: [...prefix, customerId ?? null, contextOrderId ?? null, 'list', filter, skip],
    queryFn: async ({ signal }) => scopedPage((await api.get(base, { params: { ...context, state: filter, skip, limit: 25 }, signal })).data, vehicleId, skip, filter),
    refetchOnMount: 'always',
  })
  useEffect(() => () => { void client.cancelQueries({ queryKey: prefix }) }, [client, prefix])
  useEffect(() => {
    if (!restored || query.isError || !query.data || restoredFocus.current === location.key) return
    const row = rows.current.get(restored.issueId)
    if (!row) return
    const frame = requestAnimationFrame(() => { row.focus({ preventScroll: true }); revealWorkspaceContent(row); restoredFocus.current = location.key })
    return () => cancelAnimationFrame(frame)
  }, [restored, query.data, query.isError, location.key])
  const refresh = async () => { await client.invalidateQueries({ queryKey: prefix }) }
  return <section className="db-truck-issues" aria-label="Truck issues">
    <header className="db-truck-issues__header"><h3>Truck issues</h3><div className="db-truck-issues__controls">
      <ShopWorkSelect label="Issue state" value={filter} options={[...stateOptions]} onChange={value => { setFilter(value); setSkip(0) }} />
      <button type="button" className="db-truck-issues__icon" aria-label="Refresh truck issues" disabled={query.isFetching} onClick={() => void query.refetch()}><RotateCcw size={15} /></button>
      <button type="button" disabled={query.isError || query.isPending} onClick={() => setCreating(true)}><Plus size={15} />Add issue</button>
    </div></header>
    {query.isPending && <p role="status">Loading truck issues…</p>}
    {query.isError && <p role="alert">Could not load truck issues. <button type="button" onClick={() => void query.refetch()}>Retry</button></p>}
    {!query.isError && query.data?.total === 0 && <p>No {filter === 'all' ? '' : `${filter} `}truck issues.</p>}
    {!query.isError && query.data && <ul className="db-truck-issues__list">{query.data.items.map(issue => <li key={issue.id}>
      <button ref={element => { if (element) rows.current.set(issue.id, element); else rows.current.delete(issue.id) }} type="button" className="db-truck-issues__row" onClick={() => setSelected(issue.id)} aria-label={`View truck issue: ${issue.description}`}>
        <span className="db-truck-issues__description">{issue.description}</span>
        <IssueMetadata issue={issue} />
        {issue.current_link && <span className="db-truck-issues__muted">{issue.current_link.availability === 'available' ? `Linked visit · ${issue.current_link.order_number}` : 'Linked visit unavailable'}</span>}
      </button>
    </li>)}</ul>}
    {(skip > 0 || query.data?.has_more) && <footer className="db-truck-issues__paging">
      <span>{query.data ? `${query.data.items.length ? skip + 1 : 0}–${skip + query.data.items.length} of ${query.data.total}` : 'Issues'}</span>
      <button type="button" disabled={skip === 0 || query.isFetching} onClick={() => setSkip(Math.max(0, skip - 25))}><ChevronLeft size={15} />Previous</button>
      <button type="button" disabled={!query.data?.has_more || query.isFetching} onClick={() => setSkip(skip + 25)}>Next<ChevronRight size={15} /></button>
    </footer>}
    {(creating || selected) && <IssueDialog key={selected ?? 'new'} vehicleId={vehicleId} contextOrderId={contextOrderId} context={context} scope={scope} prefix={prefix} issueId={selected} filter={filter} skip={skip} onClose={() => { setSelected(null); setCreating(false) }} refresh={refresh} />}
  </section>
}

function IssueMetadata({ issue }: { issue: VehicleIssue }) {
  return <span className="db-truck-issues__metadata">
    <strong data-priority={issue.priority}>{issue.priority}</strong>
    {issue.state !== 'open' && <span>{issue.state}</span>}
    <span>{issue.responsible_user ? `${issue.responsible_user.display_name}${issue.responsible_user.active ? '' : ' (inactive)'}` : 'Unassigned'}</span>
    <span data-follow-up={issue.follow_up_state}>{issue.follow_up_on ? <><time dateTime={issue.follow_up_on}>{issue.follow_up_on}</time>{['today', 'overdue', 'unknown'].includes(issue.follow_up_state) && ` · ${issue.follow_up_state === 'unknown' ? 'Timing unknown' : issue.follow_up_state}`}</> : 'Not scheduled'}</span>
  </span>
}

function IssueDialog({ vehicleId, contextOrderId, context, scope, prefix, issueId, filter, skip, onClose, refresh }: {
  vehicleId: string; contextOrderId?: string; context: { customer_id?: string; context_order_id?: string }; scope: string; prefix: readonly string[]; issueId: string | null;
  onClose: () => void; refresh: () => Promise<void>;
  filter: IssueState | 'all'; skip: number;
}) {
  const { appearance } = useTheme()
  const location = useLocation()
  const [action, setAction] = useState<Action>(issueId ? 'view' : 'create')
  const [draft, setDraft] = useState<IssueDraft>(emptyDraft)
  const [originalDraft, setOriginalDraft] = useState<IssueDraft>(emptyDraft)
  const [editingIssue, setEditingIssue] = useState<VehicleIssue | undefined>()
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [uncertain, setUncertain] = useState(false)
  const [pendingLeave, setPendingLeave] = useState<(() => void) | null>(null)
  const command = useRef<Command | null>(null)
  const controller = useRef(new AbortController())
  const submitLock = useRef(false)
  useEffect(() => { const current = new AbortController(); controller.current = current; return () => current.abort() }, [])
  const base = `/vehicles/${vehicleId}/issues`
  const detail = useQuery({
    queryKey: [...prefix, context.customer_id ?? null, context.context_order_id ?? null, 'detail', issueId], enabled: Boolean(issueId),
    queryFn: async ({ signal }) => scopedIssue((await api.get(`${base}/${issueId}`, { params: context, signal })).data, vehicleId, issueId ?? undefined),
    refetchOnMount: 'always',
  })
  const owners = useQuery({ queryKey: [...prefix, 'owners'], enabled: action === 'create' || action === 'edit', queryFn: async ({ signal }) => ownersSchema.parse((await api.get(`/vehicles/${vehicleId}/issue-owners`, { signal })).data), refetchOnMount: 'always' })
  const dirty = uncertain || (action === 'create' || action === 'edit' ? JSON.stringify(draft) !== JSON.stringify(originalDraft) : reason.length > 0)
  const requestLeave = useCallback((next: () => void) => { setPendingLeave(() => next) }, [])
  const requestNavigationLeave = useCallback((next: () => void) => { setPendingLeave(() => () => { onClose(); next() }) }, [onClose])
  useIssueDraftGuard(dirty || busy, requestNavigationLeave)
  const leave = () => { if (busy) return; if (dirty) requestLeave(onClose); else onClose() }
  const issue = detail.data
  const begin = (next: Action) => {
    if (!issue || detail.isError || detail.isFetching) return
    setAction(next); setEditingIssue(issue); setReason(''); setError(''); command.current = null; setUncertain(false)
    if (next === 'edit') { const value = draftFor(issue); setDraft(value); setOriginalDraft(value) }
  }
  const resetAction = () => { setAction('view'); setError(''); setReason(''); setUncertain(false); command.current = null; setDraft(emptyDraft()); setOriginalDraft(emptyDraft()) }
  const cancel = () => { if (dirty) requestLeave(issueId ? resetAction : onClose); else if (issueId) resetAction(); else onClose() }
  const submit = async () => {
    if (submitLock.current || !isPricingScopeCurrent(scope)) return
    try {
      if (!command.current) {
        const body: Record<string, unknown> = { request_id: crypto.randomUUID() }
        if (action === 'create' || action === 'edit') Object.assign(body, issueFields(draft, action === 'edit' ? editingIssue : undefined))
        if (action !== 'create') {
          if (!editingIssue) throw new Error('Reload this issue before making changes.')
          body.expected_version = editingIssue.version
        }
        let path = action === 'create' ? base : `${base}/${issueId}`
        if (action === 'resolved' || action === 'dismissed' || action === 'open' || action === 'end') {
          if (!reason.trim() || reason.trim().length > 1000) throw new Error('Enter a reason (1–1,000 characters).')
          body.reason = reason.trim()
          if (action === 'end') path += `/links/${editingIssue?.current_link?.id}/end`
          else { path += '/state'; body.state = action }
        }
        if (action === 'link') { path += '/links'; body.target_order_id = contextOrderId }
        command.current = { path, body, method: action === 'edit' ? 'patch' : 'post', issueId: issueId ?? undefined }
      }
      submitLock.current = true; setBusy(true); setError('')
      const current = command.current
      const response = await api[current.method](current.path, current.body, { signal: controller.current.signal })
      const result = mutationSchema.parse(response.data)
      scopedIssue(result.issue, vehicleId, current.issueId)
      if (controller.current.signal.aborted || !isPricingScopeCurrent(scope)) return
      command.current = null; setUncertain(false)
      await refresh()
      if (!controller.current.signal.aborted && isPricingScopeCurrent(scope)) onClose()
    } catch (failure) {
      if (controller.current.signal.aborted || !isPricingScopeCurrent(scope)) return
      const status = (failure as { response?: { status?: number } })?.response?.status
      const sent = submitLock.current
      if (sent && (!status || status >= 500)) {
        setUncertain(true)
        setError('Save could not be confirmed. Retry the same request before making another change.')
      } else {
        command.current = null
        setError(issueError(failure, failure instanceof Error && !sent ? failure.message : 'Could not save this issue. Reload it and try again.'))
        if (status === 409 || status === 404 || status === 403) { await refresh(); setEditingIssue(undefined) }
      }
    } finally { submitLock.current = false; if (!controller.current.signal.aborted) setBusy(false) }
  }
  const form = action !== 'view'
  const ownerOptions = [{ value: '', label: 'Unassigned' }, ...(owners.data?.items.map(owner => ({ value: owner.id, label: owner.display_name })) ?? [])]
  if (editingIssue?.responsible_user && !ownerOptions.some(owner => owner.value === editingIssue.responsible_user?.id)) ownerOptions.push({ value: editingIssue.responsible_user.id, label: `${editingIssue.responsible_user.display_name} (inactive)` })
  const style = appearanceTokenRecord(appearance) as CSSProperties
  const openLink = issue?.current_link?.availability === 'available' ? issue.current_link : null
  const originCandidate = openLink?.target_order_id && issueId ? {
    scope, vehicleId, issueId, filter, skip, pathname: location.pathname, search: location.search,
    sourceOrderId: location.pathname === '/dashboard/customers' ? null : contextOrderId ?? new URLSearchParams(location.search).get('selected'),
    customerId: context.customer_id ?? null, targetOrderId: openLink.target_order_id,
  } : null
  const returnOrigin: TruckIssueReturn | null = readTruckIssueReturn({ truckIssueReturn: originCandidate }, scope, openLink?.target_order_id ?? null)
  const visitHref = openLink?.target_order_id ? location.pathname === '/dashboard/customers'
    ? `/dashboard/repair-orders?selected=${openLink.target_order_id}`
    : recommendationLink(location.pathname, location.search, openLink.target_order_id, {}) : ''
  return <Dialog open onClose={() => { if (pendingLeave) setPendingLeave(null); else leave() }} className="db-issue-dialog" style={style} data-appearance-mode={appearance.mode}>
    <div className="db-issue-dialog__backdrop" aria-hidden="true" />
    <div className="db-issue-dialog__position"><DialogPanel className="db-issue-dialog__panel">
      <header><DialogTitle>{pendingLeave ? 'Discard unsaved issue changes?' : actionLabels[action]}</DialogTitle><button type="button" className="db-truck-issues__icon" aria-label="Close truck issue" disabled={busy} onClick={leave}><X size={18} /></button></header>
      {pendingLeave ? <><p>{uncertain ? 'The save may have reached the server. Reopen this truck’s issues to check before making another change.' : 'Your changes have not been saved.'}</p><div className="db-issue-dialog__actions"><button type="button" data-autofocus onClick={() => setPendingLeave(null)}>Keep editing</button><button type="button" disabled={busy} onClick={() => { const next = pendingLeave; setPendingLeave(null); next() }}>Discard changes</button></div></> : <>
        {issueId && detail.isPending && <p role="status">Loading issue…</p>}
        {detail.isError && <p role="alert">Could not load this issue. <button type="button" onClick={() => void detail.refetch()}>Retry</button></p>}
        {issue && action === 'view' && !detail.isError && <><p className="db-truck-issues__full-description">{issue.description}</p><IssueMetadata issue={issue} />
          {issue.state_reason && <p className="db-truck-issues__muted">Reason: {issue.state_reason}</p>}
          {openLink && (openLink.target_order_id === contextOrderId ? <p>This visit · {openLink.order_number}</p> : <Link to={visitHref} state={returnOrigin ? { truckIssueReturn: returnOrigin } : undefined} onClick={onClose}>Visit {openLink.order_number}<ArrowUpRight size={15} /></Link>)}
          {issue.current_link?.availability === 'unavailable' && <p>Linked visit unavailable</p>}
          <div className="db-issue-dialog__actions">
            {issue.capabilities.can_edit && <button type="button" disabled={detail.isFetching} onClick={() => begin('edit')}>Edit</button>}
            {issue.capabilities.can_change_state && (issue.state === 'open' ? <><button type="button" disabled={detail.isFetching} onClick={() => begin('resolved')}>Resolve</button><button type="button" disabled={detail.isFetching} onClick={() => begin('dismissed')}>Dismiss</button></> : <button type="button" disabled={detail.isFetching} onClick={() => begin('open')}>Reopen</button>)}
            {issue.capabilities.can_link_context && contextOrderId && !issue.current_link && <button type="button" disabled={detail.isFetching} onClick={() => begin('link')}>Link this visit</button>}
            {issue.capabilities.can_end_link && issue.current_link && <button type="button" disabled={detail.isFetching} onClick={() => begin('end')}>End visit link</button>}
          </div>
        </>}
        {form && <form onSubmit={event => { event.preventDefault(); void submit() }}>
          <fieldset disabled={busy || uncertain || (action !== 'create' && !editingIssue)}>
            {(action === 'create' || action === 'edit') ? <>
              <label>Description<textarea data-autofocus value={draft.description} maxLength={2000} required rows={3} onChange={event => setDraft({ ...draft, description: event.target.value })} /></label>
              <div className="db-issue-dialog__fields"><label>Priority<ShopWorkSelect label="Issue priority" value={draft.priority} options={priorityOptions} onChange={value => setDraft({ ...draft, priority: value as IssueDraft['priority'] })} /></label>
                <label>Responsible staff<ShopWorkSelect label="Responsible staff" value={draft.owner} options={ownerOptions} onChange={owner => setDraft({ ...draft, owner })} /></label>
                <DatePicker label="Follow-up date" value={draft.date} onChange={date => setDraft({ ...draft, date })} placeholder="Not scheduled" showDayDetails={false} />
              </div>
              {owners.isPending && <p role="status">Loading staff…</p>}{owners.isError && <p role="alert">Staff list unavailable. <button type="button" onClick={() => void owners.refetch()}>Retry staff</button></p>}
            </> : <>
              <p>{action === 'link' ? 'Reference this existing visit. This creates no work and does not resolve the issue.' : action === 'end' ? 'End this visit reference. The issue’s state stays unchanged.' : action === 'resolved' ? 'Record that this issue is resolved. This does not close or charge the repair order.' : action === 'open' ? 'Reopen this issue for follow-up.' : 'Keep this issue in history as dismissed.'}</p>
              {action !== 'link' && <label>Reason<textarea data-autofocus value={reason} maxLength={1000} required rows={3} onChange={event => setReason(event.target.value)} /></label>}
            </>}
          </fieldset>
          {error && <p role="alert">{error}</p>}
          {!editingIssue && action !== 'create' && <button type="button" onClick={resetAction}>Back to latest issue</button>}
          <div className="db-issue-dialog__actions"><button type="button" disabled={busy} onClick={cancel}>Cancel</button><button type="submit" className="db-issue-dialog__primary" disabled={busy || (action !== 'create' && !editingIssue) || ((action === 'create' || action === 'edit') && (owners.isPending || owners.isError))}>{busy ? 'Saving…' : uncertain ? 'Retry same request' : action === 'edit' || action === 'create' ? 'Save issue' : actionLabels[action]}</button></div>
        </form>}
      </>}
    </DialogPanel></div>
  </Dialog>
}
