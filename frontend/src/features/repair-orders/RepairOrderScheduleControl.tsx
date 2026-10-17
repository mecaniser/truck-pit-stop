import { useEffect, useRef, useState } from 'react'
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarClock, X } from 'lucide-react'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { formatScheduleDate, scheduleDeadline, scheduleLabels, scheduleSchema, type OrderSchedule, type OrderScheduleSummary, type ScheduleChoice, type ScheduleField } from './repairOrderSchedule'
import './repairOrderSchedule.css'

type FailureDetail = { code?: string; message?: string; field?: ScheduleField; choices?: ScheduleChoice[] }
function failureDetail(error: unknown): FailureDetail {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return { message: detail }
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) return detail as FailureDetail
  return { message: 'The schedule could not be confirmed. Your draft is still here.' }
}
const fields = ['scheduled_start_local', 'promised_finish_local'] as const
function draftFor(schedule: OrderSchedule) {
  return { scheduled_start_local: schedule.scheduled_start_local ?? '', promised_finish_local: schedule.promised_finish_local ?? '', scheduled_start_fold: schedule.scheduled_start_fold, promised_finish_fold: schedule.promised_finish_fold }
}
function foldKey(field: ScheduleField) { return field === 'scheduled_start_local' ? 'scheduled_start_fold' : 'promised_finish_fold' }

export default function RepairOrderScheduleControl({ orderId, schedule = {}, onUpdated }: { orderId: string; schedule?: OrderScheduleSummary; onUpdated?: () => void }) {
  const [open, setOpen] = useState(false)
  const user = useAuthStore(state => state.user)
  const epoch = useAuthStore(state => state.authSessionEpoch)
  const role = user?.role
  if (!['garage_owner', 'garage_admin', 'receptionist', 'fleet_manager', 'mechanic'].includes(role ?? '')) return null
  const deadline = scheduleDeadline(schedule)
  const start = formatScheduleDate(schedule.scheduled_start_at, schedule.schedule_timezone)
  return <div className="db-order-schedule-control">
    <button type="button" className="db-order-schedule-trigger" onClick={() => setOpen(true)} aria-label="Open repair order schedule">
      <CalendarClock size={15} aria-hidden="true" /><span>Schedule</span>
    </button>
    {(deadline || start) && <span className="db-order-schedule-summary" data-overdue={schedule.is_overdue || undefined}>{deadline ?? `Start · ${start}`}</span>}
    {open && <RepairOrderScheduleDialog key={`${orderId}:${user?.tenant_id}:${user?.id}:${user?.role}:${epoch}`} orderId={orderId} onClose={() => setOpen(false)} onUpdated={onUpdated} />}
  </div>
}

export function RepairOrderScheduleDialog({ orderId, onClose, onUpdated }: { orderId: string; onClose: () => void; onUpdated?: () => void }) {
  const client = useQueryClient()
  const user = useAuthStore(state => state.user)
  const epoch = useAuthStore(state => state.authSessionEpoch)
  const [baseline, setBaseline] = useState<OrderSchedule | null>(null)
  const [draft, setDraft] = useState<ReturnType<typeof draftFor> | null>(null)
  const [error, setError] = useState<FailureDetail | null>(null)
  const [latest, setLatest] = useState<OrderSchedule | null>(null)
  const [needsReview, setNeedsReview] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const saving = useRef(false)
  const load = async (signal?: AbortSignal) => {
    const result = scheduleSchema.parse((await api.get(`/repair-orders/${orderId}/schedule`, { signal })).data)
    if (result.id !== orderId) throw new Error('Mismatched schedule')
    return result
  }
  const query = useQuery({ queryKey: ['repair-order-schedule', user?.tenant_id, user?.id, user?.role, epoch, orderId], queryFn: ({ signal }) => load(signal), staleTime: 0, refetchOnWindowFocus: false, retry: false })
  useEffect(() => {
    if (query.data && !baseline) { setBaseline(query.data); setDraft(draftFor(query.data)) }
  }, [query.data, baseline])
  const refreshSaved = async () => {
    setRefreshing(true)
    try { setLatest(await load()) } catch { setLatest(null) } finally { setRefreshing(false) }
  }
  const invalidate = async () => {
    await Promise.all(['repair-orders', 'repair-order-detail', 'repair-order-workspace', 'repair-order-schedule', 'dashboard-action-queue', 'dashboard-daily-workset', 'dashboard-stats', 'customerRepairOrders'].map(key => client.invalidateQueries({ queryKey: [key] })))
    onUpdated?.()
  }
  const mutation = useMutation({
    retry: false,
    onSettled: () => { saving.current = false },
    mutationFn: async () => {
      if (!baseline || !draft) throw new Error('Schedule is not loaded')
      const result = scheduleSchema.parse((await api.patch(`/repair-orders/${orderId}/schedule`, {
        expected_updated_at: baseline.updated_at, timezone: baseline.timezone,
        ...draft, scheduled_start_local: draft.scheduled_start_local || null, promised_finish_local: draft.promised_finish_local || null,
      })).data)
      if (result.id !== orderId) throw new Error('Mismatched schedule')
      return result
    },
    onSuccess: async () => { await invalidate(); onClose() },
    onError: async failure => {
      const detail = failureDetail(failure)
      setError(detail)
      const status = (failure as { response?: { status?: number } })?.response?.status
      // Validation does not commit. Other failures may be stale or an uncertain
      // successful write; fetch for comparison, never replay with a new version.
      if (status !== 422) { setNeedsReview(true); await refreshSaved(); await invalidate() }
    },
  })
  const dismiss = () => { if (!mutation.isPending) onClose() }
  const readOnly = baseline && !baseline.can_edit
  const currentError = error ?? (query.isError ? failureDetail(query.error) : null)
  return <Dialog open onClose={dismiss} className="db-order-schedule-dialog fixed inset-0 z-[150]">
    <div className="fixed inset-0 bg-black/50" aria-hidden="true" />
    <div className="fixed inset-x-0 flex items-center justify-center p-3" style={{ top: 'var(--db-workspace-viewport-top, 0px)', height: 'var(--db-workspace-viewport-height, 100dvh)' }}>
      <DialogPanel className="db-order-schedule-panel flex max-h-full w-full max-w-md flex-col overflow-hidden rounded-xl shadow-xl">
        <div className="db-order-schedule-heading flex shrink-0 items-center justify-between gap-2 px-4 py-2">
          <DialogTitle className="text-base font-semibold">Repair order schedule</DialogTitle>
          <button type="button" className="db-order-schedule-close" aria-label="Close schedule dialog" disabled={mutation.isPending} onClick={dismiss}><X size={20} /></button>
        </div>
        <form className="flex min-h-0 flex-col" onSubmit={event => { event.preventDefault(); if (draft && baseline?.can_edit && !saving.current && !mutation.isPending && !needsReview) { saving.current = true; setError(null); mutation.mutate() } }}>
          <div className="db-order-schedule-body min-h-0 space-y-3 overflow-y-auto px-4 py-3">
            {!baseline && !query.isError && <p role="status">Loading schedule…</p>}
            {baseline && draft && <>
              <p className="db-order-schedule-muted text-sm">Shop time · {baseline.timezone}</p>
              {readOnly && <p className="text-sm">This schedule is read-only for this order or your role.</p>}
              {fields.map(field => <div key={field} className="db-order-schedule-field">
                <label htmlFor={`schedule-${field}`} className="block text-sm font-semibold">{scheduleLabels[field]}</label>
                <div className="db-order-schedule-field-controls mt-1 flex min-w-0 items-center gap-2">
                  <input id={`schedule-${field}`} type="datetime-local" step="60" value={draft[field]} disabled={mutation.isPending || !!readOnly} onChange={event => { setDraft({ ...draft, [field]: event.target.value, [foldKey(field)]: null }); if (error?.field === field) setError(null) }} className="db-order-schedule-input min-w-0 flex-1" />
                  <button type="button" className="db-order-schedule-button" aria-label={`Clear ${scheduleLabels[field].toLowerCase()}`} disabled={mutation.isPending || !!readOnly || !draft[field]} onClick={() => { setDraft({ ...draft, [field]: '', [foldKey(field)]: null }); if (error?.field === field) setError(null) }}>Clear</button>
                </div>
                {error?.code === 'schedule_time_ambiguous' && error.field === field && error.choices && <fieldset className="mt-2 space-y-1">
                  <legend className="text-sm">This clock time occurs twice. Choose which one.</legend>
                  {error.choices.map(choice => <label key={choice.fold} className="db-order-schedule-choice flex items-center gap-2 text-sm">
                    <input type="radio" disabled={mutation.isPending} name={`${field}-fold`} checked={draft[foldKey(field)] === choice.fold} onChange={() => setDraft({ ...draft, [foldKey(field)]: choice.fold })} />
                    {choice.fold === 0 ? 'First' : 'Second'} occurrence (UTC{choice.utc_offset})
                  </label>)}
                </fieldset>}
              </div>)}
            </>}
            {currentError && <p role="alert" className="db-order-schedule-error text-sm">{currentError.message}</p>}
            {query.isError && !baseline && <button type="button" className="db-order-schedule-button" onClick={() => void query.refetch()}>Retry loading schedule</button>}
            {needsReview && <section aria-label="Review saved schedule" className="db-order-schedule-conflict space-y-2 rounded-lg border p-3 text-sm">
              <p>Your draft has been kept. Review the saved schedule before continuing.</p>
              {refreshing ? <p role="status">Loading saved schedule…</p> : latest ? <>
                <p>Saved in {latest.timezone}</p>
                <dl>{fields.map(field => <div key={field}><dt className="font-semibold">{scheduleLabels[field]}</dt><dd>{latest[field]?.replace('T', ' ') ?? 'Not set'}</dd></div>)}</dl>
                <div className="flex flex-wrap gap-2">
                  <button type="button" className="db-order-schedule-button" onClick={() => { setBaseline(latest); setDraft(draftFor(latest)); setNeedsReview(false); setLatest(null); setError(null) }}>Use saved schedule</button>
                  {error?.code === 'schedule_changed' && latest.can_edit && latest.timezone === baseline?.timezone && <button type="button" className="db-order-schedule-button" onClick={() => { setBaseline(latest); setNeedsReview(false); setLatest(null); setError(null) }}>Keep my draft</button>}
                </div>
              </> : <button type="button" className="db-order-schedule-button" onClick={() => void refreshSaved()}>Reload saved schedule</button>}
            </section>}
          </div>
          <div className="db-order-schedule-footer flex shrink-0 flex-wrap justify-end gap-2 px-4 py-2">
            <button type="button" className="db-order-schedule-button" disabled={mutation.isPending} onClick={dismiss}>Cancel</button>
            {!readOnly && <button type="submit" className="db-order-schedule-button db-order-schedule-save" disabled={!baseline || !draft || mutation.isPending || needsReview}>{mutation.isPending ? 'Saving…' : 'Save'}</button>}
          </div>
        </form>
      </DialogPanel>
    </div>
  </Dialog>
}
