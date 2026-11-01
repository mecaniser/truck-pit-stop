import { ControlButton } from '@/components/ui/Controls'
import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, MessageSquare, Plus } from 'lucide-react'
import { z } from 'zod'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { errorDetail } from '@/features/service-checklists/queries'
import { canReadOperationNotes } from './notesPrivacy'
import './operation-notes.css'

const noteSchema = z.object({
  id: z.string(), labor_id: z.string(), body: z.string(),
  actor_user_id: z.string().nullable(), actor_name: z.string().nullable(), created_at: z.string(),
})
const notesSchema = z.object({
  items: z.array(noteSchema), can_add: z.boolean(), read_only_reason: z.string().nullable(),
})
type Props = { orderId: string; laborId: string; description: string; expanded?: boolean; dark?: boolean; orderStatus?: string; assignmentId?: string | null }

/** Remount on identity changes so drafts and cached permissions cannot cross sessions. */
export function OperationNotes(props: Props) {
  const user = useAuthStore(state => state.user)
  const epoch = useAuthStore(state => state.authSessionEpoch)
  if (!user?.tenant_id || !canReadOperationNotes(user.role)) return null
  return <ScopedOperationNotes {...props} key={`${user.tenant_id}:${user.id}:${user.role}:${epoch}:${props.orderId}:${props.laborId}`}
    scope={[user.tenant_id, user.id, user.role, epoch]} />
}

function ScopedOperationNotes({ orderId, laborId, description, expanded = true, dark = false, orderStatus, assignmentId, scope }: Props & { scope: unknown[] }) {
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const [composing, setComposing] = useState(false)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const attempt = useRef<{ id: string; body: string } | null>(null)
  const posting = useRef(false)
  const path = `/repair-orders/${orderId}/operations/${laborId}/notes`
  const queryKey = ['operation-notes', ...scope, orderId, laborId, orderStatus, assignmentId]
  const query = useQuery({
    queryKey,
    queryFn: async ({ signal }) => notesSchema.parse((await api.get(path, { signal })).data),
    enabled: expanded && open,
    retry: false,
    staleTime: 0,
  })
  const mutation = useMutation({
    mutationFn: async (payload: { id: string; body: string }) => noteSchema.parse((await api.post(path, payload)).data),
    retry: false,
    onSuccess: note => {
      client.setQueryData<z.infer<typeof notesSchema>>(queryKey, current => current ? {
        ...current, items: [...current.items.filter(item => item.id !== note.id), note],
      } : current)
      setDraft('')
      setComposing(false)
      setError('')
      setSaved(true)
      attempt.current = null
      void client.invalidateQueries({ queryKey })
      void client.invalidateQueries({ queryKey: ['repair-order-detail', orderId] })
    },
    onError: failure => {
      setError(errorDetail(failure, 'Save could not be confirmed. Your draft is kept. Retry to confirm it without adding a duplicate.'))
      // Refresh capabilities, but never automatically repeat a write.
      void client.invalidateQueries({ queryKey })
    },
    onSettled: () => { posting.current = false },
  })
  const canSubmit = Boolean(query.data && (query.data.can_add || (error && attempt.current?.body === draft.trim())))
  const submit = () => {
    const body = draft.trim()
    if (posting.current || !body || body.length > 4000 || !canSubmit || query.isError || query.isFetching) return
    if (!attempt.current || attempt.current.body !== body) attempt.current = { id: crypto.randomUUID(), body }
    posting.current = true
    setError('')
    setSaved(false)
    mutation.mutate(attempt.current)
  }
  // Keep the component mounted when the operation collapses, retaining its draft.
  if (!expanded) return null
  const muted = dark ? 'text-zinc-400' : 'text-slate-500'
  const control = `db-operation-note-action inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md px-2 text-xs font-semibold disabled:opacity-50 ${dark ? 'text-zinc-200 hover:bg-zinc-800' : 'text-slate-700 hover:bg-slate-100'}`
  return <section aria-label={`Operation notes: ${description}`} className={`db-operation-notes min-w-0 px-2 pb-1 ${dark ? 'text-zinc-100' : 'text-slate-800'}`}>
    <ControlButton controlKind="action" type="button" aria-expanded={open} aria-controls={`operation-notes-${laborId}`} className={control}
      onClick={() => setOpen(value => !value)}>
      <ChevronRight size={14} className={open ? 'rotate-90' : ''} /><MessageSquare size={14} />Operation notes
      {query.data && !query.isError && query.data.items.length > 0 && <span className="tabular-nums">{query.data.items.length}</span>}
      {draft && !open && <span className={muted}>Draft</span>}
    </ControlButton>
    {open && <div id={`operation-notes-${laborId}`} className="min-w-0 space-y-2 pt-1">
      <p className={`text-xs ${muted}`}>Shop only · Not shown on invoices or customer views.</p>
      {query.isPending && <p role="status" className="text-xs">Loading operation notes…</p>}
      {query.isError && <div role="alert" className={`text-xs ${dark ? 'text-red-300' : 'text-red-700'}`}>
        Operation notes could not be refreshed. <ControlButton type="button" className={`${control} underline`} disabled={query.isFetching} onClick={() => void query.refetch()}>{query.isFetching ? 'Retrying…' : 'Retry notes'}</ControlButton>
      </div>}
      {query.data && !query.isError && <>
        {query.data.items.length === 0 && !query.isError && <p className={`text-xs ${muted}`}>No operation notes yet.</p>}
        <ul className={`divide-y ${dark ? 'divide-zinc-700' : 'divide-slate-200'}`}>
          {query.data.items.map(note => <li key={note.id} className="min-w-0 py-2">
            <div className={`flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-xs ${muted}`}>
              <span className={`break-words font-semibold ${dark ? 'text-zinc-200' : 'text-slate-700'}`}>{note.actor_name || 'Staff'}</span>
              <time dateTime={note.created_at}>{new Date(note.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</time>
            </div>
            <p className="mt-1 whitespace-pre-wrap break-words text-sm [overflow-wrap:anywhere]">{note.body}</p>
          </li>)}
        </ul>
        {!query.data.can_add && <p className={`text-xs ${muted}`}>{query.data.read_only_reason || 'Operation notes are read-only.'}</p>}
        {!composing && query.data.can_add && <ControlButton type="button" className={control} disabled={query.isError || query.isFetching} onClick={() => { setComposing(true); setSaved(false) }}><Plus size={14} />Add operation note</ControlButton>}
      </>}
      {composing && <form className="space-y-2" onSubmit={event => { event.preventDefault(); submit() }}>
        <label htmlFor={`operation-note-draft-${laborId}`} className="block break-words text-xs font-semibold [overflow-wrap:anywhere]">Note for {description}</label>
        <textarea id={`operation-note-draft-${laborId}`} autoFocus rows={3} maxLength={4000} value={draft}
          disabled={mutation.isPending} onChange={event => setDraft(event.target.value)}
          placeholder="Record findings, work performed or the next step…"
          className={`w-full min-w-0 resize-y rounded-lg border px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 ${dark ? 'border-zinc-600 bg-zinc-900' : 'border-slate-300 bg-white'}`} />
        {error && <p role="alert" className={`break-words text-xs ${dark ? 'text-red-300' : 'text-red-700'}`}>{error}</p>}
        <div className="flex flex-wrap items-center justify-end gap-2">
          <span className={`mr-auto text-xs tabular-nums ${muted}`}>{draft.length}/4000</span>
          <ControlButton type="button" disabled={mutation.isPending} className={control} onClick={() => { setComposing(false); setDraft(''); setError(''); attempt.current = null }}>Cancel</ControlButton>
          <ControlButton type="submit" disabled={mutation.isPending || !draft.trim() || !canSubmit || query.isError || query.isFetching}
            className="db-operation-note-action inline-flex items-center justify-center whitespace-nowrap rounded-md bg-orange-600 px-3 text-xs font-semibold text-white hover:bg-orange-700 disabled:opacity-50">
            {mutation.isPending ? 'Saving…' : error ? 'Retry save' : 'Save note'}
          </ControlButton>
        </div>
      </form>}
      {saved && <p role="status" className={`text-xs ${dark ? 'text-emerald-300' : 'text-emerald-700'}`}>Operation note saved.</p>}
    </div>}
  </section>
}
