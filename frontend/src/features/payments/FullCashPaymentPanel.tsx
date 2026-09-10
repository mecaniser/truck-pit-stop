import { useEffect, useId, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Banknote } from 'lucide-react'

import { confirmFullCashPayment, createIdempotencyKey, paymentApiError } from './api'
import { formatMoney } from './money'
import type { InvoiceSettlementSummary } from './types'

export default function FullCashPaymentPanel({ invoiceId, summary, onUpdated, onChoosingChange }: {
  invoiceId: string
  summary: InvoiceSettlementSummary
  onUpdated: (next: InvoiceSettlementSummary) => void
  onChoosingChange: (choosing: boolean) => void
}) {
  const queryClient = useQueryClient()
  const [expanded, setExpanded] = useState(false)
  const [note, setNote] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [rejectedVersion, setRejectedVersion] = useState<number | null>(null)
  const request = useRef<{ key: string; version: number; note: string } | null>(null)
  const inFlight = useRef(false)
  const mounted = useRef(true)
  const panelId = useId()
  const noteId = useId()
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const stale = rejectedVersion === summary.version
  const allowed = summary.allowed_actions?.confirm_cash === true && !stale
  const reason = stale ? 'Invoice changed. Refreshing payment details before cash can be confirmed.' : summary.allowed_actions?.cash_unavailable_reason

  // Keep cash out of generic partial-payment rails and older-server surfaces.
  if (summary.invoice_id !== invoiceId || summary.state === 'paid' || (!allowed && !reason)) return null

  const choose = (value: boolean) => {
    setExpanded(value)
    onChoosingChange(value)
  }

  const confirm = async () => {
    if (!allowed || inFlight.current) return
    if (!request.current || request.current.version !== summary.version || request.current.note !== note.trim()) {
      request.current = { key: createIdempotencyKey(), version: summary.version, note: note.trim() }
    }
    inFlight.current = true
    setPending(true)
    setError(null)
    try {
      const result = await confirmFullCashPayment(invoiceId, {
        expected_settlement_version: request.current.version,
        ...(request.current.note ? { note: request.current.note } : {}),
      }, request.current.key)
      if (!mounted.current) return
      queryClient.setQueryData(['invoice-settlement', 'authenticated', invoiceId], result.settlement)
      void queryClient.invalidateQueries({ queryKey: ['invoice-settlement-allocations', 'authenticated', invoiceId] })
      onUpdated(result.settlement)
      choose(false)
    } catch (failure) {
      if (!mounted.current) return
      const parsed = paymentApiError(failure, 'Cash confirmation was not verified. Retry to check the same receipt.')
      setError(parsed.message)
      if (parsed.status === 409 && (typeof parsed.current_version === 'number' || parsed.code === 'stale_settlement_version')) {
        request.current = null
        setRejectedVersion(summary.version)
        void queryClient.invalidateQueries({ queryKey: ['invoice-settlement', 'authenticated', invoiceId] })
      }
    } finally {
      inFlight.current = false
      if (mounted.current) setPending(false)
    }
  }

  return <section className="rounded-2xl border border-slate-200 bg-white p-4 text-slate-950" aria-label="Full cash payment">
    <button type="button" disabled={!allowed || pending} aria-expanded={expanded} aria-controls={panelId}
      onClick={() => choose(!expanded)} className="flex min-h-11 w-full items-center gap-3 rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 disabled:cursor-not-allowed">
      <Banknote className="h-5 w-5 shrink-0 text-slate-500" aria-hidden="true" />
      <span className="flex-1"><span className="block text-sm font-bold">Cash</span><span className="block text-xs text-slate-500">Full payment only</span></span>
      <span className="text-xs font-semibold text-slate-500">{allowed ? expanded ? 'Cancel' : 'Choose cash' : 'Unavailable'}</span>
    </button>
    {!allowed && reason && <p className="mt-2 text-xs leading-relaxed text-slate-600">{reason}</p>}
    {expanded && <div id={panelId} className="mt-3 space-y-3 border-t border-slate-200 pt-4">
      <div className="flex items-baseline justify-between gap-3"><span className="text-sm text-slate-600">Full amount to collect</span><strong className="text-xl tabular-nums">{formatMoney(summary.principal_total)}</strong></div>
      <p className="text-xs leading-relaxed text-slate-600">No card fee. Recorded in this shop’s cash receipts only—not sent to QuickBooks. Cannot be combined with another payment method.</p>
      <label htmlFor={noteId} className="block text-xs font-semibold text-slate-600">Receipt note (optional)</label>
      <textarea id={noteId} value={note} maxLength={1000} disabled={pending || request.current !== null} onChange={event => setNote(event.target.value)} rows={2} className="w-full rounded-xl border border-slate-200 bg-white p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 disabled:opacity-70" />
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      <button type="button" disabled={pending || !allowed} onClick={() => void confirm()} className="min-h-11 w-full rounded-xl bg-emerald-800 px-4 py-3 text-sm font-bold text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-2 disabled:opacity-50">
        {pending ? 'Recording cash…' : `Confirm ${formatMoney(summary.principal_total)} cash received`}
      </button>
      <p className="text-xs text-slate-500">Confirm only after the shop has received the full cash amount.</p>
    </div>}
  </section>
}
