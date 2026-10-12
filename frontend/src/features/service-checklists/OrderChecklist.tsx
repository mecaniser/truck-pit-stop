import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, RefreshCw } from 'lucide-react'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { checklistKeys, checklistOpenEvent, errorDetail, invalidateOrderChecklist, isConflict } from './queries'
import { checklistPageSchema } from './schemas'
import type { OrderChecklistItem } from './types'

export default function OrderChecklist({ orderId, refreshToken, orderStatus, dark = false }: { orderId: string; refreshToken?: unknown; orderStatus?: string; dark?: boolean }) {
  const user = useAuthStore(state => state.user)
  const sessionEpoch = useAuthStore(state => state.authSessionEpoch)
  if (!user?.tenant_id || !['garage_owner', 'garage_admin', 'receptionist', 'mechanic', 'fleet_manager'].includes(user.role)) return null
  return <Checklist key={`${user.tenant_id}:${user.id}:${user.role}:${sessionEpoch}:${orderId}`} tenantId={user.tenant_id} orderId={orderId} refreshToken={refreshToken} orderStatus={orderStatus} dark={dark} actorScope={`${user.id}:${user.role}:${sessionEpoch}`} />
}
function Checklist({ tenantId, orderId, refreshToken, orderStatus, dark, actorScope }: { tenantId: string; orderId: string; refreshToken?: unknown; orderStatus?: string; dark: boolean; actorScope: string }) {
  const client = useQueryClient()
  const [open, setOpen] = useState(true)
  const [message, setMessage] = useState('')
  const section = useRef<HTMLElement>(null)
  const contentId = useId()
  const query = useInfiniteQuery({
    queryKey: [...checklistKeys.order(tenantId, orderId), { limit: 100, actorScope }],
    initialPageParam: 0,
    queryFn: async ({ signal, pageParam }) => checklistPageSchema.parse((await api.get(`/repair-orders/${orderId}/checklist`, { signal, params: { skip: pageParam, limit: 100 } })).data),
    getNextPageParam: last => last.skip + last.items.length < last.total ? last.skip + last.items.length : undefined,
    staleTime: 0,
  })
  useEffect(() => { void client.invalidateQueries({ queryKey: checklistKeys.order(tenantId, orderId) }) }, [client, tenantId, orderId, refreshToken, orderStatus])
  useEffect(() => {
    const handleOpen = (event: Event) => {
      if ((event as CustomEvent<{ orderId: string }>).detail.orderId !== orderId) return
      setOpen(true)
      setMessage('Required checklist tasks are still open. Review the refreshed checklist before finishing.')
      void client.invalidateQueries({ queryKey: checklistKeys.order(tenantId, orderId) })
      section.current?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
    }
    window.addEventListener(checklistOpenEvent, handleOpen)
    return () => window.removeEventListener(checklistOpenEvent, handleOpen)
  }, [client, tenantId, orderId])
  const first = query.isError && !query.isFetchNextPageError ? undefined : query.data?.pages[0]
  const groups = useMemo(() => {
    const map = new Map<string, OrderChecklistItem[]>()
    for (const item of query.data?.pages.flatMap(page => page.items) ?? []) {
      const items = map.get(item.labor_id) ?? []
      if (!items.some(existing => existing.id === item.id)) items.push(item)
      map.set(item.labor_id, items)
    }
    return [...map.values()]
  }, [query.data])
  // Errors and loading must never imply that required work is cleared.
  if (first?.total === 0 && !query.isError && !query.isFetching && !message) return null
  const canUpdate = Boolean(first?.can_update) && !query.isError && (!orderStatus || ['in_progress', 'pending_review'].includes(orderStatus))
  const muted = dark ? '!text-[#d4d4d8]' : '!text-[#4b5563]'
  return <section ref={section} aria-label="Work order checklist" className={`my-3 rounded-xl border p-3 ${dark ? 'border-zinc-700 !bg-[#18181b] !text-[#f4f4f5]' : 'border-gray-200 !bg-[#ffffff] !text-[#111827]'}`}>
    <button type="button" onClick={() => setOpen(value => !value)} aria-expanded={open} aria-controls={contentId} className="flex min-h-10 w-full items-center justify-between gap-2 text-left">
      <span className="flex flex-wrap items-center gap-x-2 gap-y-1"><span className="whitespace-nowrap text-sm font-semibold">Checklist{first ? ` · ${first.summary.completed}/${first.summary.total}` : ''}</span>
        {first && <span className={`text-xs ${first.summary.required_remaining ? (dark ? '!text-[#fcd34d]' : '!text-[#92400e]') : muted}`}>{query.isFetching && first.summary.required_remaining === 0 ? 'Checking required tasks…' : `${first.summary.required_remaining} required remaining`}</span>}
      </span><ChevronRight size={18} className={`shrink-0 transition-transform ${open ? 'rotate-90' : ''}`} />
    </button>
    {open && <div id={contentId} className="space-y-3 pt-2">
      {query.isPending && <p role="status" className={`text-sm ${muted}`}>Loading checklist…</p>}
      {query.isError && <p role="alert" className={`text-sm ${dark ? '!text-[#fca5a5]' : '!text-[#b91c1c]'}`}>Checklist could not be refreshed. Completion status is unverified. <button type="button" onClick={() => void query.refetch()} className="inline-flex items-center gap-1 whitespace-nowrap underline"><RefreshCw size={12} />Retry</button></p>}
      {message && <p role="status" className={`text-xs ${dark ? '!text-[#fcd34d]' : '!text-[#92400e]'}`}>{message}</p>}
      {first && !canUpdate && <p className={`text-xs ${muted}`}>Read only. Checks can be changed while this work order is open and work has started.</p>}
      {first && groups.map(items => <div key={items[0].labor_id}>
        <h4 className={`mb-1 text-xs font-semibold ${muted}`}>{items[0].service_name}</h4>
        <ul className="divide-y divide-current/10">{items.map(item => <ChecklistRow key={item.id} item={item} tenantId={tenantId} orderId={orderId} canUpdate={canUpdate} dark={dark} />)}</ul>
      </div>)}
      {query.hasNextPage && <button type="button" disabled={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()} className="min-h-10 whitespace-nowrap text-sm font-semibold underline disabled:opacity-40">{query.isFetchingNextPage ? 'Loading more…' : 'Load more tasks'}</button>}
      {query.isFetching && !query.isPending && !query.isFetchingNextPage && <p role="status" className={`text-xs ${muted}`}>Refreshing checklist…</p>}
    </div>}
  </section>
}
function ChecklistRow({ item, tenantId, orderId, canUpdate, dark }: {
  item: OrderChecklistItem; tenantId: string; orderId: string; canUpdate: boolean; dark: boolean
}) {
  const client = useQueryClient()
  const [error, setError] = useState('')
  const mutation = useMutation({
    mutationFn: async () => api.patch(`/repair-orders/${orderId}/checklist/${item.id}`, { is_completed: !item.is_completed, expected_version: item.version }),
    onSuccess: async () => { setError(''); await invalidateOrderChecklist(client, tenantId, orderId) },
    onError: async failure => {
      setError(errorDetail(failure, 'Task was not saved. Try again.'))
      if (isConflict(failure)) await invalidateOrderChecklist(client, tenantId, orderId)
    },
  })
  return <li className="py-1.5">
    <label className="flex min-h-10 cursor-pointer items-start gap-3 py-1">
      <input type="checkbox" checked={item.is_completed} disabled={!canUpdate || mutation.isPending} onChange={() => mutation.mutate()} className="mt-0.5 h-5 w-5 shrink-0 accent-emerald-600 disabled:cursor-default" />
      <span className="min-w-0 flex-1 text-sm"><span className="break-words">{item.label}</span>{!item.required && <span className={`ml-2 text-xs ${dark ? '!text-[#d4d4d8]' : '!text-[#4b5563]'}`}>Optional</span>}
        {item.is_completed && <span className={`mt-1 block text-xs ${dark ? '!text-[#d4d4d8]' : '!text-[#4b5563]'}`}>
          {item.completed_by?.name || 'Staff'}{item.completed_at && <> · <time dateTime={item.completed_at}>{new Date(item.completed_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</time></>}
        </span>}
        {mutation.isPending && <span role="status" className="mt-1 block text-xs">Saving…</span>}
      </span>
    </label>
    {error && <p role="alert" className={`ml-8 text-xs ${dark ? '!text-[#fca5a5]' : '!text-[#b91c1c]'}`}>{error}</p>}
  </li>
}
