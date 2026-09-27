import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import api from '@/lib/api'

type Review = { id: string; reviewer_name: string | null; rating: number; review_text: string | null; review_created_at?: string | null; reply_text: string | null; status: string; requires_approval: boolean; publish_failure_reason: string | null; published_at?: string | null }
type InboxPage = { items: Review[]; total: number; limit: number; offset: number }
const filters = [['', 'All'], ['needs_reply', 'Needs reply'], ['new', 'Unread'], ['awaiting_approval', 'Awaiting approval'], ['published', 'Replied'], ['failed', 'Failed']]
const STATUS_LABELS: Record<string, string> = { new: 'New', awaiting_approval: 'Awaiting approval', publishing: 'Publishing', published: 'Replied', failed: 'Failed' }
const PAGE_SIZE = 50
const shortDate = (iso?: string | null) => iso ? new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : null
// DB-092: the inbox is paged; accept the pre-DB-092 plain list so a frontend deployed ahead of its API still renders.
const toPage = (data: Review[] | InboxPage, offset: number): InboxPage => Array.isArray(data) ? { items: data, total: data.length, limit: data.length, offset } : data

export default function GoogleReviewsPage() {
  const queryClient = useQueryClient(); const [filter, setFilter] = useState(''); const [selected, setSelected] = useState<Review | null>(null); const [busy, setBusy] = useState<Record<string, string>>({})
  const [editingReply, setEditingReply] = useState(false)
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey: ['google-reviews', filter],
    initialPageParam: 0,
    queryFn: async ({ pageParam }) => toPage((await api.get('/google-reviews', { params: { ...(filter ? { status: filter } : {}), limit: PAGE_SIZE, offset: pageParam } })).data, pageParam),
    getNextPageParam: last => last.offset + last.items.length < last.total ? last.offset + last.items.length : undefined,
    refetchInterval: 30000,
  })
  const reviews = data?.pages.flatMap(page => page.items) ?? []
  const total = data?.pages[0]?.total ?? 0
  const { data: metrics } = useQuery({ queryKey: ['google-review-metrics'], queryFn: async () => (await api.get('/google-reviews/metrics')).data })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['google-reviews'] })
  const open = (review: Review) => { setSelected(review); setEditingReply(false) }
  // One action per review at a time, tracked per review so another can be worked meanwhile; a response only replaces the panel if its review is still open.
  const run = async (actionName: string, request: (id: string) => Promise<{ data: Review }>, success: string, failure: string) => { if (!selected || busy[selected.id]) return; const id = selected.id; setBusy(current => ({ ...current, [id]: actionName })); try { const { data } = await request(id); setSelected(current => current?.id === id ? data : current); if (selected.id === id) setEditingReply(false); refresh(); toast.success(success) } catch (error) { toast.error((error as { response?: { data?: { detail?: string } } }).response?.data?.detail || failure) } finally { setBusy(current => { const next = { ...current }; delete next[id]; return next }) } }
  const action = (actionName: string) => run(actionName, id => api.post(`/google-reviews/${id}/${actionName}`), actionName === 'publish' ? 'Reply published' : 'Reply updated', 'Action failed')
  const saveEdit = () => { if (!selected?.reply_text) return; const reply_text = selected.reply_text; return run('save', id => api.put(`/google-reviews/${id}/reply`, { reply_text }), 'Draft saved', 'Could not save draft') }
  const pending = selected ? busy[selected.id] ?? null : null
  const label = (actionName: string, idle: string, working: string) => pending === actionName ? working : idle
  // DB-092: a reply already public on Google is shown read-only; replacing it is an explicit, warned step.
  const replied = selected?.status === 'published'
  const locked = replied && !editingReply
  const secondary = 'rounded bg-white/10 px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50'
  return <div className="db-operating-surface__scroller db-reviews-workspace mx-auto w-full max-w-6xl p-4 sm:p-6 text-white">
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3"><div><h1 className="text-2xl font-semibold">Google Reviews</h1><p className="mt-1 text-sm text-gray-400">AI reply approval queue.</p></div><Link to="/dashboard/garage/reviews/settings" className="rounded-lg border border-white/15 px-3 py-2 text-sm hover:bg-white/10">Google connection & settings</Link></div>
    <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">{[['New', metrics?.new_reviews], ['Unreplied', metrics?.unreplied_reviews], ['Avg rating', metrics?.average_rating], ['Response time', metrics?.average_response_time_hours ? `${metrics.average_response_time_hours}h` : '—']].map(([label, value]) => { const body = <><div className="text-xs text-gray-400">{label}</div><div className="mt-1 text-xl font-semibold">{String(value ?? '—')}</div></>; return label === 'Unreplied' ? <button key={String(label)} type="button" onClick={() => setFilter('needs_reply')} className="rounded-xl border border-white/10 bg-white/5 p-4 text-left hover:bg-white/10">{body}</button> : <div key={String(label)} className="rounded-xl border border-white/10 bg-white/5 p-4">{body}</div> })}</div>
    <div className="grid gap-4 lg:grid-cols-[1fr,1.1fr]">
      <section className="min-w-0 rounded-xl border border-white/10 bg-white/5">
        <div className="flex gap-2 overflow-x-auto border-b border-white/10 p-3">{filters.map(([value, label]) => <button key={value} onClick={() => setFilter(value)} className={`whitespace-nowrap rounded px-2 py-1 text-sm ${filter === value ? 'bg-emerald-500 text-black' : 'text-gray-300 hover:bg-white/10'}`}>{label}</button>)}</div>
        <div className="max-h-[65vh] overflow-y-auto">
          {reviews.map(review => <button key={review.id} onClick={() => open(review)} className={`block w-full border-b border-white/10 p-4 text-left hover:bg-white/5 ${selected?.id === review.id ? 'bg-white/10' : ''}`}><div className="flex justify-between"><b>{review.reviewer_name || 'Google reviewer'}</b><span className="text-amber-300">{'★'.repeat(review.rating)}</span></div><p className="mt-1 line-clamp-2 text-sm text-gray-300">{review.review_text || 'No written review'}</p><span className="mt-2 inline-block text-xs text-gray-400">{STATUS_LABELS[review.status] ?? review.status.replace(/_/g, ' ')}{shortDate(review.review_created_at) && ` · ${shortDate(review.review_created_at)}`}</span></button>)}
          {!reviews.length && <p className="p-6 text-sm text-gray-400">No reviews match this filter.</p>}
          {reviews.length > 0 && <div className="flex items-center justify-between gap-3 p-4 text-xs text-gray-400"><span>Showing {reviews.length} of {total}</span>{hasNextPage && <button type="button" onClick={() => fetchNextPage()} disabled={isFetchingNextPage} className={secondary}>{isFetchingNextPage ? 'Loading…' : 'Load more'}</button>}</div>}
        </div>
      </section>
      <section className="min-w-0 rounded-xl border border-white/10 bg-white/5 p-5">{selected ? <>
        <div className="flex justify-between"><h2 className="font-semibold">{selected.reviewer_name || 'Google reviewer'}</h2><span className="text-amber-300">{'★'.repeat(selected.rating)}</span></div>
        <p className="mt-1 text-xs text-gray-400">{[shortDate(selected.review_created_at) && `Reviewed ${shortDate(selected.review_created_at)}`, replied && shortDate(selected.published_at) && `Replied ${shortDate(selected.published_at)}`].filter(Boolean).join(' · ')}</p>
        <p className="my-4 whitespace-pre-wrap text-gray-300">{selected.review_text || 'No written review'}</p>
        <label htmlFor="google-review-reply" className="text-xs text-gray-400">{replied ? 'Public reply on Google' : 'Public reply'}</label>
        <textarea id="google-review-reply" value={selected.reply_text || ''} readOnly={!!pending || locked} aria-busy={pending === 'generate'} onChange={event => setSelected({ ...selected, reply_text: event.target.value })} className="mt-1 min-h-32 w-full rounded border border-white/15 bg-black/20 p-3 text-sm read-only:opacity-60" />
        {replied && editingReply && <p className="mt-2 text-sm text-amber-200">Approving will replace your current reply on Google.</p>}
        <div className="mt-3 flex flex-wrap gap-2">{locked
          ? <button type="button" onClick={() => setEditingReply(true)} className={secondary}>Edit public reply</button>
          : replied
            ? <><button onClick={saveEdit} disabled={!!pending} className={secondary}>{label('save', 'Save edit', 'Saving…')}</button><button type="button" onClick={() => setEditingReply(false)} disabled={!!pending} className={secondary}>Cancel</button></>
            : <><button onClick={saveEdit} disabled={!!pending} className={secondary}>{label('save', 'Save edit', 'Saving…')}</button><button onClick={() => action('generate')} disabled={!!pending} className={secondary}>{label('generate', 'Regenerate AI', 'Generating…')}</button>{selected.requires_approval && <button onClick={() => action('approve')} disabled={!!pending} className="rounded bg-amber-400 px-3 py-2 text-sm text-black disabled:cursor-not-allowed disabled:opacity-50">{label('approve', 'Approve', 'Approving…')}</button>}{!selected.requires_approval && <button onClick={() => action('publish')} disabled={!!pending} className="rounded bg-emerald-400 px-3 py-2 text-sm text-black disabled:cursor-not-allowed disabled:opacity-50">{label('publish', 'Publish', 'Publishing…')}</button>}</>}
        </div>
        {selected.publish_failure_reason && <p className="mt-3 text-sm text-red-300">{selected.publish_failure_reason}</p>}
      </> : <p className="text-sm text-gray-400">Select a review to view its AI draft and controls.</p>}</section>
    </div>
  </div>
}
