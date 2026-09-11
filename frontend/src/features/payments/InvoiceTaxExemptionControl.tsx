import { useEffect, useId, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { CheckCircle2 } from 'lucide-react'
import { applyInvoiceTaxExemption, createIdempotencyKey, paymentApiError } from './api'
import { formatMoney } from './money'
import type { InvoiceSettlementSummary } from './types'

// Existing staff-payment visual language; exemption belongs to invoice totals,
// not to a tender. Disclosure -> optional reference -> confirmed updated total.
export default function InvoiceTaxExemptionControl({ invoiceId, summary, onUpdated, onEditingChange }: {
  invoiceId: string
  summary: InvoiceSettlementSummary
  onUpdated: (summary: InvoiceSettlementSummary) => void
  onEditingChange: (editing: boolean) => void
}) {
  const queryClient = useQueryClient()
  const id = useId()
  const [editing, setEditing] = useState(false)
  const [reference, setReference] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [staleVersion, setStaleVersion] = useState<number | null>(null)
  const request = useRef<{ key: string; version: number; support_reference: string | null } | null>(null)
  const inFlight = useRef(false)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const exemption = summary.tax_exemption
  if (!exemption || summary.invoice_id !== invoiceId) return null

  const changeEditing = (next: boolean) => {
    if (inFlight.current) return
    setEditing(next)
    onEditingChange(next)
  }
  const apply = async () => {
    if (inFlight.current || !exemption.can_apply || staleVersion === summary.version) return
    request.current ??= { key: createIdempotencyKey(), version: summary.version, support_reference: reference.trim() || null }
    const command = request.current
    inFlight.current = true
    setPending(true)
    setError(null)
    try {
      const next = await applyInvoiceTaxExemption(invoiceId, {
        expected_settlement_version: command.version, support_reference: command.support_reference,
      }, command.key)
      if (!mounted.current) return
      queryClient.setQueryData(['invoice-settlement', 'authenticated', invoiceId], next)
      void queryClient.invalidateQueries({ queryKey: ['invoice-settlement-allocations', 'authenticated', invoiceId] })
      onUpdated(next)
      setEditing(false)
      onEditingChange(false)
    } catch (failure) {
      if (!mounted.current) return
      const parsed = paymentApiError(failure, 'Exemption was not confirmed. Retry to check the same request.')
      setError(parsed.message)
      if (parsed.status === 409 && (parsed.code === 'stale_settlement_version' || typeof parsed.current_version === 'number')) {
        request.current = null
        setStaleVersion(summary.version)
        void queryClient.invalidateQueries({ queryKey: ['invoice-settlement', 'authenticated', invoiceId] })
      } else if (parsed.status && parsed.status >= 400 && parsed.status < 500) {
        request.current = null
      }
    } finally {
      inFlight.current = false
      if (mounted.current) setPending(false)
    }
  }

  return <section aria-label="Invoice tax exemption" className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-slate-950">
    {exemption.applied ? <div role="status" className="space-y-1">
      <p className="flex items-center gap-2 text-sm font-semibold"><CheckCircle2 aria-hidden="true" className="h-4 w-4 text-emerald-700" />Tax exemption applied</p>
      {exemption.reason && <p className="break-words text-sm text-slate-600">{exemption.reason}</p>}
      {exemption.support_reference && <p className="break-words text-xs text-slate-600">Reference: {exemption.support_reference}</p>}
    </div> : <>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <span className="text-sm font-semibold">Sales tax exemption</span>
        <button type="button" aria-expanded={editing} aria-controls={id} disabled={!exemption.can_apply || pending}
          onClick={() => changeEditing(!editing)} className="min-h-11 rounded-lg px-2 text-sm font-semibold text-emerald-800 enabled:hover:bg-emerald-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 disabled:cursor-not-allowed disabled:text-slate-500">
          {editing ? 'Cancel' : 'Apply tax exemption'}
        </button>
      </div>
      {!exemption.can_apply && exemption.unavailable_reason && <p className="text-xs leading-relaxed text-slate-600">{exemption.unavailable_reason}</p>}
      {editing && <form id={id} onSubmit={event => { event.preventDefault(); void apply() }} className="mt-2 space-y-3 border-t border-slate-200 pt-3">
        <p className="text-sm leading-relaxed text-slate-600">For a qualifying exemption, regardless of payment method. Shop supplies stay unchanged.</p>
        <label className="block text-sm font-medium" htmlFor={`${id}-reference`}>Certificate or supporting reference (optional)</label>
        <input id={`${id}-reference`} maxLength={255} disabled={pending || request.current !== null} value={reference} onChange={event => setReference(event.target.value)} className="block min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 disabled:opacity-70" />
        <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm"><span>Invoice amount after exemption</span><strong className="text-lg tabular-nums">{formatMoney(exemption.exempt_principal_total)}</strong></div>
        <p className="text-xs text-slate-600">Before any card fee. Applying an exemption does not record a payment.</p>
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <button type="submit" disabled={pending || !exemption.can_apply || staleVersion === summary.version} className="min-h-11 w-full rounded-xl bg-emerald-800 px-4 py-3 text-sm font-semibold text-white hover:bg-emerald-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-2 disabled:opacity-50">
          {pending ? 'Applying exemption…' : 'Apply exemption and update total'}
        </button>
      </form>}
    </>}
  </section>
}
