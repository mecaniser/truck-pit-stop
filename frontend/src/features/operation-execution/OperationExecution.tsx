import { ControlButton } from '@/components/ui/Controls'
import PlatformSelect from '@/components/PlatformSelect'
import { useState } from 'react'
import { trackedTimeLabel } from './format'
import { OperationNotes } from './OperationNotes'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, Play, RefreshCw, RotateCcw, Square } from 'lucide-react'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { checklistOpenEvent, errorDetail } from '@/features/service-checklists/queries'
import { invalidateOperationExecution, operationPageSchema, useOperationExecution, type OperationExecution } from './queries'

export function OperationExecutionStatus({ item, dark = false }: { item: OperationExecution; dark?: boolean }) {
  return <span className={`db-operation-status inline-flex max-w-full flex-wrap items-center gap-x-2 gap-y-0.5 text-xs ${dark ? 'text-zinc-300' : 'text-slate-600'}`}>
    <span className={item.status === 'completed' ? (dark ? 'text-emerald-300' : 'text-emerald-700') : ''}>{item.status === 'completed' ? 'Completed' : item.status === 'pending' ? 'Not completed' : 'Not tracked'}</span>
    <span className="break-words">{item.mechanic_name || 'Unassigned'}</span>
    {item.status !== null && <span className="whitespace-nowrap tabular-nums">{trackedTimeLabel(item.tracked_seconds)}</span>}
    {item.active_session && <span className={`whitespace-nowrap font-semibold ${dark ? 'text-amber-300' : 'text-amber-800'}`}>Timer running</span>}
  </span>
}

export function OperationExecutionFeedback({ query, dark = false }: { query: ReturnType<typeof useOperationExecution>; dark?: boolean }) {
  if (!query.allowed) return null
  if (query.isPending) return <p role="status" className="py-1 text-xs">Loading operation progress…</p>
  if (!query.isError) return null
  return <p role="alert" className={`py-2 text-xs ${dark ? 'text-red-300' : 'text-red-700'}`}>Operation progress could not be refreshed. Status is unverified. <ControlButton type="button" disabled={query.isFetching} onClick={() => void query.refetch()} className="inline-flex  items-center gap-1 whitespace-nowrap underline"><RefreshCw size={13} />{query.isFetching ? 'Retrying…' : 'Retry operation progress'}</ControlButton></p>
}

type Technician = { mechanic_id: string; mechanic_name: string }
type Action = { type: 'assignment'; mechanicId: string | null } | { type: 'completion'; completed: boolean } | { type: 'start' } | { type: 'stop'; sessionId: string }

export function OperationExecutionControls({ orderId, item, technicians = [], disabled = false, dark = false, onUpdated }: {
  orderId: string; item: OperationExecution; technicians?: Technician[]; disabled?: boolean; dark?: boolean; onUpdated?: () => void
}) {
  const tenantId = useAuthStore(state => state.user?.tenant_id)
  const client = useQueryClient()
  const [error, setError] = useState('')
  const mutation = useMutation({
    mutationFn: async (action: Action) => {
      const base = `/repair-orders/${orderId}/operations/${item.labor_id}`
      const version = { expected_version: item.version }
      const response = action.type === 'assignment' ? await api.put(`${base}/assignment`, { ...version, mechanic_id: action.mechanicId })
        : action.type === 'completion' ? await api.put(`${base}/completion`, { ...version, is_completed: action.completed })
          : action.type === 'start' ? await api.post(`${base}/timer/start`, version)
            : await api.post(`${base}/timer/stop`, { ...version, session_id: action.sessionId })
      return operationPageSchema.parse(response.data)
    },
    onSuccess: async () => {
      setError('')
      if (tenantId) await invalidateOperationExecution(client, tenantId, orderId)
      onUpdated?.()
    },
    onError: async failure => {
      setError(errorDetail(failure, 'Change could not be confirmed. Refresh progress before trying again.'))
      // A failed response may still have committed; never replay a write or retain stale capabilities.
      if (tenantId) await invalidateOperationExecution(client, tenantId, orderId)
      onUpdated?.()
    },
  })
  const busy = disabled || mutation.isPending
  const control = `inline-flex min-h-10 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg border px-3 py-1.5 text-xs font-semibold disabled:cursor-default disabled:opacity-50 ${dark ? 'border-zinc-600 bg-zinc-800 text-zinc-100' : 'border-gray-300 bg-white text-slate-700'}`
  const assignedMissing = item.mechanic_id && !technicians.some(tech => tech.mechanic_id === item.mechanic_id)
  return <div className={`space-y-1.5 border-b pb-2 ${dark ? 'border-zinc-700' : 'border-gray-200'}`} aria-label={`Execution: ${item.description}`}>
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      {item.can_assign && <label className="flex min-w-0 max-w-full items-center gap-2 text-xs">
        <span className="shrink-0">Technician</span>
        <PlatformSelect aria-label={`Technician for ${item.description}`} value={item.mechanic_id ?? ''} disabled={busy} onChange={event => mutation.mutate({ type: 'assignment', mechanicId: event.target.value || null })} className={`${control} min-w-0 max-w-[min(100%,16rem)] flex-1`}>
          <option value="">Unassigned</option>
          {assignedMissing && <option value={item.mechanic_id!} disabled>{item.mechanic_name || 'Previous technician'}</option>}
          {technicians.map(tech => <option key={tech.mechanic_id} value={tech.mechanic_id}>{tech.mechanic_name}</option>)}
        </PlatformSelect>
      </label>}
      {item.status === null && item.can_assign && item.mechanic_id && <ControlButton type="button" disabled={busy} onClick={() => mutation.mutate({ type: 'assignment', mechanicId: item.mechanic_id })} className={control}>Track operation</ControlButton>}
      {item.can_start_timer && <ControlButton type="button" disabled={busy} onClick={() => mutation.mutate({ type: 'start' })} className={control}><Play size={14} />Start timer</ControlButton>}
      {item.can_stop_timer && item.active_session && <ControlButton type="button" disabled={busy} onClick={() => mutation.mutate({ type: 'stop', sessionId: item.active_session!.id })} className={control}><Square size={13} />Stop timer</ControlButton>}
      {item.can_complete && <ControlButton type="button" disabled={busy} onClick={() => mutation.mutate({ type: 'completion', completed: true })} className={control}><Check size={14} />Complete operation</ControlButton>}
      {item.can_reopen && <ControlButton type="button" disabled={busy} onClick={() => mutation.mutate({ type: 'completion', completed: false })} className={control}><RotateCcw size={14} />Reopen operation</ControlButton>}
      {mutation.isPending && <span role="status" className="text-xs">Saving…</span>}
    </div>
    {item.required_tasks_remaining > 0 && item.status !== 'completed' && <div className={`flex flex-wrap items-center gap-x-2 text-xs ${dark ? 'text-amber-300' : 'text-amber-800'}`}><span>{item.required_tasks_remaining} required checklist task{item.required_tasks_remaining === 1 ? '' : 's'} remaining.</span><ControlButton type="button" onClick={() => window.dispatchEvent(new CustomEvent(checklistOpenEvent, { detail: { orderId } }))} className=" whitespace-nowrap underline">View checklist</ControlButton></div>}
    {item.completed_at && <p className={`text-xs ${dark ? 'text-zinc-400' : 'text-slate-500'}`}>Completed by {item.completed_by?.name || 'Staff'} · <time dateTime={item.completed_at}>{new Date(item.completed_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</time></p>}
    {error && <p role="alert" className={`break-words text-xs ${dark ? 'text-red-300' : 'text-red-700'}`}>{error}</p>}
  </div>
}

export function MechanicOperations({ orderId, refreshToken, leadScope = [] }: { orderId: string; refreshToken?: unknown; leadScope?: Array<{ name: string; description?: string | null }> }) {
  const query = useOperationExecution(orderId, refreshToken)
  // Historical orders may carry scope in notes or standalone parts, without Labor rows.
  // Only the lead's successful, empty operation response may reveal that read-only fallback.
  const showLeadScope = query.isSuccess && query.data.is_order_lead && query.data.items.length === 0 && leadScope.length > 0
  return <section aria-label="Operation progress" className="min-w-0 space-y-2">
    <div className="flex flex-wrap items-baseline justify-between gap-2">
      <h3 className="text-sm font-semibold text-zinc-100">{showLeadScope ? 'Work to do' : query.data?.is_order_lead ? 'Operations' : 'Assigned operations'}</h3>
      {query.data && !query.isError && query.data.items.length > 0 && <span className="text-xs text-zinc-400">{query.data.summary.completed}/{query.data.summary.tracked} tracked complete{query.data.summary.legacy_untracked > 0 ? ` · ${query.data.summary.legacy_untracked} not tracked` : ''}</span>}
    </div>
    <OperationExecutionFeedback query={query} dark />
    {query.data && ['draft', 'quoted', 'approved', 'assigned', 'acknowledged'].includes(query.data.order_status) && <p className="text-xs text-zinc-400">Operation timers become available when the order lead starts work.</p>}
    {query.data?.items.map(item => <article key={item.labor_id} className="min-w-0 space-y-2 rounded-xl border border-zinc-700 bg-zinc-900 p-3">
      <h4 className="break-words text-sm font-semibold text-zinc-100">{item.description}</h4>
      <OperationExecutionStatus item={item} dark />
      <OperationExecutionControls orderId={orderId} item={item} disabled={query.isError || query.isFetching} dark />
      <OperationNotes orderId={orderId} laborId={item.labor_id} description={item.description} orderStatus={query.data?.order_status} assignmentId={item.mechanic_id} dark />
    </article>)}
    {showLeadScope && <ul className="divide-y divide-zinc-700 rounded-xl border border-zinc-700 px-3">{leadScope.map((service, index) => <li key={`${service.name}:${index}`} className="py-2"><p className="break-words text-sm text-zinc-100">{service.name}</p>{service.description && <p className="mt-1 break-words text-xs text-zinc-400">{service.description}</p>}</li>)}</ul>}
    {query.data?.items.length === 0 && !query.isError && !showLeadScope && <p className="text-xs text-zinc-400">No operations assigned.</p>}
  </section>
}
