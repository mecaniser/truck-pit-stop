import { useEffect, useId, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useLocation } from 'react-router-dom'
import { ArrowUpRight, Plus } from 'lucide-react'
import { z } from 'zod'
import api from '@/lib/api'
import { conversionHours, conversionTotal, conversionSchema, recommendationLink, revealWorkspaceContent, type RecommendationConversion } from './recommendationConversion'

export interface ConversionContext {
  canConvert: boolean
  hourlyRate?: number
  rateReadOnly?: boolean
  onOpenOperation?: (id: string) => void
}

type Props = ConversionContext & {
  recommendationId: string
  description: string
  contextOrderId?: string
  conversion?: RecommendationConversion | null
}
type Submission = { request_id: string; hours: string; hourly_rate: string; replaces_conversion_id: string | null }
const responseSchema = z.object({ conversion: conversionSchema, replayed: z.boolean() })
const money = (value: number) => value.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

export function ConversionLink({ conversion, contextOrderId, onOpenOperation }: Pick<Props, 'conversion' | 'contextOrderId' | 'onOpenOperation'>) {
  const location = useLocation()
  if (!conversion) return null
  const labels = { active: 'Added to', operation_removed: 'Operation removed from', target_cancelled: 'Order cancelled:', target_deleted: 'Order deleted:', superseded: 'Replaced work on' }
  return <span className="inline-flex min-w-0 flex-wrap items-center gap-x-1 text-xs text-slate-600">
    <span>{labels[conversion.state]}</span>
    {conversion.target_order.available ? <Link
      className="inline-flex items-center gap-1 whitespace-nowrap rounded px-1 py-1 font-medium text-orange-700 underline underline-offset-2"
      to={recommendationLink(location.pathname, location.search, conversion.target_order.id, { operation: conversion.labor_id })}
      aria-label={`Open linked operation on ${conversion.target_order.order_number}`}
      onClick={(event) => {
        if (conversion.state === 'active' && conversion.target_order.id === contextOrderId && onOpenOperation) {
          event.preventDefault(); onOpenOperation(conversion.labor_id)
        }
      }}>
      {conversion.target_order.order_number}<ArrowUpRight className="h-3 w-3" />
    </Link> : <span>{conversion.target_order.order_number}</span>}
  </span>
}

/** One logical submit retains its UUID and exact payload after an uncertain response. */
export default function RecommendationConversionAction({ recommendationId, description, contextOrderId, conversion, canConvert, hourlyRate, rateReadOnly, onOpenOperation }: Props) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [hours, setHours] = useState('')
  const [rate, setRate] = useState(hourlyRate == null ? '' : hourlyRate.toFixed(2))
  const [error, setError] = useState('')
  const [conflict, setConflict] = useState<RecommendationConversion | null>(null)
  // A refresh can reveal removal/cancellation after a concurrent-add conflict.
  // Let the authoritative latest receipt replace that earlier error snapshot.
  useEffect(() => { setConflict(null) }, [conversion])
  const submission = useRef<Submission | null>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const form = useRef<HTMLFormElement>(null)
  useEffect(() => {
    if (!open) return
    const frame = requestAnimationFrame(() => { if (form.current) revealWorkspaceContent(form.current) })
    return () => cancelAnimationFrame(frame)
  }, [open])
  const restoreFocus = useRef(false)
  useEffect(() => {
    if (!open && restoreFocus.current) { trigger.current?.focus(); restoreFocus.current = false }
  }, [open])
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  const helpId = useId()
  const parsedHours = conversionHours(hours)
  const parsedRate = /^\d+(?:\.\d{1,2})?$/.test(rate.trim()) ? Number(rate) : NaN
  const validRate = Number.isFinite(parsedRate) && parsedRate >= 0 && parsedRate <= 99999999.99
  const effective = conflict ?? conversion
  const mutation = useMutation({
    mutationFn: async (body: Submission) => {
      const response = await api.post<unknown>(`/repair-orders/${contextOrderId}/recommended-work/${recommendationId}/convert`, body)
      const result = responseSchema.parse(response.data)
      if (result.conversion.recommendation_id !== recommendationId || result.conversion.target_order.id !== contextOrderId) throw new Error('Invalid conversion response')
      return result
    },
    onSuccess: async ({ conversion: linked }) => {
      // Store the server's receipt before refetching; no optimistic operation or price.
      queryClient.setQueriesData({ queryKey: ['recommended-work'] }, (cached: unknown) => {
        if (!cached || typeof cached !== 'object' || !('items' in cached) || !Array.isArray(cached.items)) return cached
        return { ...cached, items: cached.items.map((item) => item.id === recommendationId ? { ...item, conversion: linked } : item) }
      })
      setOpen(false); setError(''); setConflict(null); submission.current = null
      await Promise.all([
        ['recommended-work'], ['recommended-services'], ['price-build', contextOrderId],
        ['repair-order-detail', contextOrderId], ['repair-orders'],
      ].map((queryKey) => queryClient.invalidateQueries({ queryKey })))
      if (alive.current && linked.state === 'active') onOpenOperation?.(linked.labor_id)
    },
    onError: (failure: unknown) => {
      const response = (failure as { response?: { status?: number; data?: { detail?: unknown } } }).response
      const detail = response?.data?.detail
      const message = typeof detail === 'string' ? detail : detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string' ? detail.message : null
      const existing = detail && typeof detail === 'object' && 'conversion' in detail ? conversionSchema.safeParse(detail.conversion) : null
      if (existing?.success) setConflict(existing.data)
      // A definite rejection is safe to edit; an unknown result must retry unchanged.
      if (response?.status && [400, 403, 404, 409, 422].includes(response.status)) submission.current = null
      setError(message || 'Could not confirm the operation. Retry safely with the same details.')
    },
  })
  const close = () => { if (!mutation.isPending) { restoreFocus.current = true; setOpen(false) } }
  const mayAdd = canConvert && !!contextOrderId && (!effective || effective.can_replace)
  return <div className="db-recommendation-conversion w-full min-w-0">
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <ConversionLink conversion={effective} contextOrderId={contextOrderId} onOpenOperation={onOpenOperation} />
      {mayAdd && !open && <button ref={trigger} type="button" onClick={() => {
        if (!submission.current && !hours) setRate(hourlyRate == null ? '' : hourlyRate.toFixed(2))
        setOpen(true)
      }} className="inline-flex items-center gap-1 whitespace-nowrap rounded-md px-2 py-1 text-xs font-semibold text-orange-700 hover:bg-orange-50"
        aria-label={`${effective ? 'Add again' : 'Add to this order'}: ${description}`}>
        <Plus className="h-3.5 w-3.5" />{effective ? 'Add again' : 'Add to this order'}
      </button>}
    </div>
    {open && mayAdd && <form ref={form} className="mt-1 rounded-lg border border-orange-200 bg-orange-50/40 p-2" aria-label={`Add recommendation: ${description}`}
      onKeyDown={(event) => { if (event.key === 'Escape') { event.stopPropagation(); close() } }}
      onSubmit={(event) => {
        event.preventDefault()
        if (mutation.isPending) return
        if (!submission.current) {
          if (parsedHours == null || !validRate) { setError('Enter 0.01–999.99 hours and a valid rate with up to two decimals.'); return }
          submission.current = { request_id: crypto.randomUUID(), hours: parsedHours.toFixed(2), hourly_rate: parsedRate.toFixed(2), replaces_conversion_id: effective?.id ?? null }
        }
        setError(''); mutation.mutate(submission.current)
      }}>
      {effective?.can_replace && <p className="db-recommendation-replacement-warning mb-2 text-xs">This creates a replacement operation. The previous link stays in the work history.</p>}
      <div className="flex flex-wrap items-end gap-2">
        <label className="min-w-0 flex-1 basis-24 text-xs font-medium text-gray-700">Hours
          <input autoFocus type="text" inputMode="decimal" aria-describedby={helpId} placeholder="1.5 or 1:30"
            value={hours} disabled={mutation.isPending || !!submission.current} onChange={(event) => { setHours(event.target.value); setError('') }}
            className="mt-1 block h-8 w-full min-w-0 rounded-md border border-gray-300 bg-white px-2 text-sm text-gray-900 disabled:opacity-60" />
        </label>
        <label className="min-w-0 flex-1 basis-24 text-xs font-medium text-gray-700">Rate / hr
          <input type="text" inputMode="decimal" value={rate} readOnly={rateReadOnly} disabled={mutation.isPending || !!submission.current}
            onChange={(event) => { setRate(event.target.value); setError('') }}
            className="mt-1 block h-8 w-full min-w-0 rounded-md border border-gray-300 bg-white px-2 text-sm text-gray-900 disabled:opacity-60" />
        </label>
        <span className="py-1 text-sm font-semibold tabular-nums text-gray-900">Labor {parsedHours != null && validRate ? money(conversionTotal(parsedHours, parsedRate)) : '—'}</span>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={close} disabled={mutation.isPending} className="whitespace-nowrap rounded-md px-2 py-1 text-xs font-medium text-gray-600">Cancel</button>
          <button type="submit" disabled={mutation.isPending} className="whitespace-nowrap rounded-md bg-orange-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50">{mutation.isPending ? 'Adding…' : submission.current ? 'Retry safely' : effective ? 'Add replacement' : 'Add operation'}</button>
        </div>
      </div>
      <p id={helpId} className="mt-1 text-xs text-slate-600">Added work stays unresolved until it is completed and marked resolved.</p>
    </form>}
    {error && <p role="alert" className="mt-1 break-words text-xs text-red-700">{error}</p>}
  </div>
}
