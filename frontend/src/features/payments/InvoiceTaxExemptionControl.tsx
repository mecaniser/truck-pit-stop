import { useEffect, useId, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { CheckCircle2 } from 'lucide-react'
import { applyInvoiceTaxExemption, createIdempotencyKey, paymentApiError } from './api'
import type { InvoiceSettlementSummary } from './types'
import InvoiceChargeControls, { type InvoiceChargeControlProps } from './InvoiceChargeControls'

export default function InvoiceTaxExemptionControl(props: InvoiceChargeControlProps) {
  if (props.summary.invoice_id !== props.invoiceId) return null
  return props.summary.charge_controls
    ? <InvoiceChargeControls key={props.invoiceId} {...props} />
    : <LegacyInvoiceTaxExemptionControl key={props.invoiceId} {...props} />
}

// Existing staff-payment visual language; exemption belongs to invoice totals,
// not to a tender. Disclosure -> optional reference -> confirmed updated total.
function LegacyInvoiceTaxExemptionControl({ invoiceId, summary, onUpdated, onEditingChange, embedded = false }: {
  invoiceId: string
  summary: InvoiceSettlementSummary
  onUpdated: (summary: InvoiceSettlementSummary) => void
  onEditingChange: (editing: boolean) => void
  embedded?: boolean
}) {
  const queryClient = useQueryClient()
  const id = useId()
  const [editing, setEditing] = useState(false)
  const [reference, setReference] = useState('')
  const [showReference, setShowReference] = useState(false)
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

  return <section aria-label="Invoice tax exemption" className={embedded ? 'border-t border-slate-200 pt-3 text-slate-950' : 'rounded-xl border border-slate-200 bg-white px-4 py-3 text-slate-950'}>
    {exemption.applied ? <div role="status" className="space-y-1">
      <p className="flex items-center gap-2 text-sm font-semibold"><CheckCircle2 aria-hidden="true" className="h-4 w-4 text-emerald-700" />Tax exemption applied</p>
      {exemption.reason && <p className="break-words text-sm text-slate-600">{exemption.reason}</p>}
      {exemption.support_reference && <p className="break-words text-xs text-slate-600">Reference: {exemption.support_reference}</p>}
    </div> : <>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <span id={`${id}-label`} className="text-sm font-semibold">Sales tax exemption</span>
        <button type="button" role="switch" aria-checked={editing} aria-labelledby={`${id}-label`} aria-controls={id} disabled={!exemption.can_apply || pending || request.current !== null}
          onClick={() => changeEditing(!editing)} className="flex min-h-11 min-w-11 items-center justify-center rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 disabled:cursor-not-allowed disabled:opacity-50">
          <span aria-hidden="true" className={`relative inline-flex h-6 w-10 shrink-0 rounded-full ${editing ? 'bg-emerald-700' : 'bg-slate-300'}`}>
            <span className={`absolute left-1 top-1 h-4 w-4 rounded-full bg-white ${editing ? 'translate-x-4' : ''}`} />
          </span>
        </button>
      </div>
      {!exemption.can_apply && exemption.unavailable_reason && <p className="text-xs leading-relaxed text-slate-600">{exemption.unavailable_reason}</p>}
      {editing && <form id={id} onSubmit={event => { event.preventDefault(); void apply() }} className="mt-1 space-y-2">
        {!showReference ? <button type="button" onClick={() => setShowReference(true)} className="min-h-11 rounded-lg text-xs font-semibold text-slate-600 underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700">Add certificate/reference</button> : <>
          <label className="block text-xs font-medium" htmlFor={`${id}-reference`}>Certificate or supporting reference (optional)</label>
          <input id={`${id}-reference`} maxLength={255} disabled={pending || request.current !== null} value={reference} onChange={event => setReference(event.target.value)} className="block min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 disabled:opacity-70" />
        </>}
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <button type="submit" disabled={pending || !exemption.can_apply || staleVersion === summary.version} className="min-h-11 rounded-lg border border-emerald-700 px-3 text-xs font-semibold text-emerald-800 hover:bg-emerald-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 disabled:opacity-50">
          {pending ? 'Updating…' : 'Update invoice'}
        </button>
      </form>}
    </>}
  </section>
}
