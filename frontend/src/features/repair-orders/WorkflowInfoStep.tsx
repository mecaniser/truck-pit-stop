import { useEffect, useState } from 'react'
import { Popover, PopoverButton, PopoverGroup, PopoverPanel } from '@headlessui/react'
import { X } from 'lucide-react'
import type { RepairOrder } from '@/types'

export { PopoverGroup as WorkflowInfoGroup }
export type WorkflowInfo = Pick<RepairOrder, 'created_at' | 'assigned_at' | 'acknowledged_at' | 'work_started_at' | 'work_completed_at' | 'actual_tracked_minutes' | 'hold_reason' | 'internal_notes'>

type Props = {
  stage: 'intake' | 'technician' | 'bay' | 'review'
  label: string
  className: string
  info?: WorkflowInfo
  technician?: string | null
  status: string
  description?: string | null
  mileage?: number | null
  operationCount?: number
  reviewDraft?: string
}

function timestamp(value?: string | null) {
  if (!value || !Number.isFinite(Date.parse(value))) return 'Not recorded'
  return new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function duration(minutes: number) {
  const rounded = Math.floor(minutes)
  return `${Math.floor(rounded / 60)}h ${rounded % 60}m`
}

function savedReviews(value?: string | null): { notes: string; reviewed_by?: string; reviewed_at?: string }[] {
  try {
    const data: unknown = JSON.parse(value || '{}')
    if (!data || typeof data !== 'object' || !('reviews' in data) || !Array.isArray(data.reviews)) return []
    return data.reviews.filter((r): r is { notes: string; reviewed_by?: string; reviewed_at?: string } =>
      !!r && typeof r === 'object' && r.type === 'manager_review' && typeof r.notes === 'string'
      && (r.reviewed_by == null || typeof r.reviewed_by === 'string')
      && (r.reviewed_at == null || typeof r.reviewed_at === 'string'))
  } catch { return [] }
}

function Details({ stage, info, technician, status, description, mileage, operationCount, reviewDraft }: Props) {
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000)
    return () => window.clearInterval(timer)
  }, [])
  const start = Date.parse(info?.work_started_at || '')
  const opened = Date.parse(info?.created_at || '')
  const waitBeforeStart = Number.isFinite(start) && Number.isFinite(opened) && start >= opened
    ? duration(Math.round((start - opened) / 60_000)) : null
  const end = info?.work_completed_at ? Date.parse(info.work_completed_at) : status === 'in_progress' ? now : NaN
  const elapsed = Number.isFinite(start) && Number.isFinite(end) && end >= start ? duration((end - start) / 60_000) : 'Not available'
  const row = (name: string, value: string) => <div className="space-y-1"><dt className="text-xs text-gray-500">{name}</dt><dd className="text-sm font-medium text-gray-900">{value}</dd></div>
  const reviews = savedReviews(info?.internal_notes)
  return <div className="space-y-3 whitespace-normal break-words">
    {stage === 'intake' && <>
      <dl className="space-y-3">{row('Order opened', timestamp(info?.created_at))}{row('Mileage at intake', mileage != null ? mileage.toLocaleString() : 'Not recorded')}</dl>
      <div><p className="text-xs text-gray-500">Work requested</p><p className="mt-1 text-sm whitespace-pre-wrap">{description || 'No intake description recorded.'}</p></div>
    </>}
    {stage === 'technician' && <>
      <p className="text-sm font-semibold">{technician || (info?.work_started_at ? 'Shop-managed' : 'No technician assigned')}</p>
      {!technician && info?.work_started_at && <p className="text-sm text-gray-600">No technician assigned</p>}
      <dl className="space-y-3">
        {technician && row('Assigned', timestamp(info?.assigned_at))}
        {technician && row('Acknowledged', info?.acknowledged_at ? timestamp(info.acknowledged_at) : 'Awaiting acknowledgment')}
        {info?.work_started_at ? row(technician ? 'Repair started' : 'Started', timestamp(info.work_started_at)) : <p className="text-sm text-gray-600">Work has not started</p>}
      </dl>
      {waitBeforeStart && <p className="text-sm text-gray-600">Started {waitBeforeStart} after order opened</p>}
    </>}
    {stage === 'bay' && <>
      <dl className="space-y-3">{row('Work status', status.replace(/_/g, ' '))}{row('Work scope', operationCount == null ? 'Not available' : `${operationCount} labor / operation ${operationCount === 1 ? 'line' : 'lines'}`)}{row('Job started', timestamp(info?.work_started_at))}{row('Work completed', timestamp(info?.work_completed_at))}{row(info?.work_completed_at ? 'Elapsed job time' : 'Elapsed since job started', elapsed)}{row('Recorded labor time', info?.actual_tracked_minutes != null && Number.isFinite(info.actual_tracked_minutes) && info.actual_tracked_minutes >= 0 ? duration(info.actual_tracked_minutes) : 'Not recorded')}</dl>
      <p className="text-xs text-gray-500">Elapsed time includes pauses. Labor time counts tracked work only.</p>
      <div><p className="text-xs text-gray-500">Recorded hold reason</p><p className="mt-1 text-sm">{info?.hold_reason || 'No hold reason recorded.'}</p></div>
    </>}
    {stage === 'review' && <>
      <p className="text-sm font-medium">{status === 'pending_review' ? 'Awaiting quality review' : ['completed', 'invoiced', 'paid'].includes(status) ? 'Work finalized' : status === 'cancelled' ? 'Order cancelled' : 'Work has not reached quality review'}</p>
      {reviews.length ? reviews.map((review, index) => <div key={index} className="border-t border-gray-100 pt-3"><p className="text-xs text-gray-500">{review.reviewed_by || 'Reviewer not recorded'} · {timestamp(review.reviewed_at)}</p><p className="mt-1 whitespace-pre-wrap text-sm">{review.notes}</p></div>) : <p className="text-sm text-gray-600">No saved quality-review notes.</p>}
      {reviewDraft?.trim() && <div className="border-t border-gray-100 pt-3"><p className="text-xs font-semibold text-amber-700">Unsaved review notes</p><p className="mt-1 whitespace-pre-wrap text-sm">{reviewDraft}</p></div>}
    </>}
  </div>
}

export default function WorkflowInfoStep(props: Props) {
  const title = { intake: 'Check-in details', technician: 'Technician details', bay: 'In-the-bay details', review: 'Quality-review details' }[props.stage]
  return <Popover className="shrink-0">
    {({ close, open }) => <>
      <PopoverButton aria-label={props.stage === 'technician' ? 'Technician status' : undefined} className={`db-pipeline-step inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-600 ${props.className}`}>
        {props.label}
        <span
          aria-hidden="true"
          data-testid="workflow-popover-indicator"
          data-open={open}
          className="inline-flex h-3 w-3 items-center justify-center rounded-full border border-current/70"
        >
          <span className={`h-1.5 w-1.5 rounded-full bg-current transition-transform duration-150 ${open ? 'scale-100' : 'scale-0'}`} />
        </span>
      </PopoverButton>
      <PopoverPanel anchor="bottom start" focus aria-label={title} className="z-[100] w-80 max-w-[calc(100vw-2rem)] overflow-y-auto rounded-xl bg-white p-4 text-left shadow-lg ring-1 ring-gray-200 [--anchor-gap:8px] [--anchor-padding:16px]">
        <div className="mb-3 flex items-center justify-between gap-2"><h3 tabIndex={0} data-autofocus className="text-base font-bold text-gray-900 outline-none">{title}</h3><button type="button" onClick={() => close()} aria-label={`Close ${title.toLowerCase()}`} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-600"><X className="h-4 w-4" /></button></div>
        <Details {...props} />
      </PopoverPanel>
    </>}
  </Popover>
}
