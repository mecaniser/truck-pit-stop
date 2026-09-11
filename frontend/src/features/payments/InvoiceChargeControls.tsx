import { useEffect, useId, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { adjustInvoiceCharges, createIdempotencyKey, paymentApiError } from './api'
import type { InvoiceSettlementSummary } from './types'

export interface InvoiceChargeControlProps {
  invoiceId: string
  summary: InvoiceSettlementSummary
  onUpdated: (next: InvoiceSettlementSummary) => void
  onEditingChange: (editing: boolean) => void
  embedded?: boolean
}

export default function InvoiceChargeControls({ invoiceId, summary, onUpdated, onEditingChange, embedded }: InvoiceChargeControlProps) {
  const controls = summary.charge_controls!
  const id = useId()
  const queryClient = useQueryClient()
  const [selection, setSelection] = useState<{ tax_exempt: boolean; shop_supplies_enabled: boolean } | null>(null)
  const taxExempt = selection?.tax_exempt ?? controls.tax_exempt
  const supplies = selection?.shop_supplies_enabled ?? controls.shop_supplies_enabled
  const [reference, setReference] = useState(controls.support_reference ?? '')
  const [showReference, setShowReference] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [staleVersion, setStaleVersion] = useState<number | null>(null)
  const request = useRef<{ key: string; body: Parameters<typeof adjustInvoiceCharges>[1] } | null>(null)
  const inFlight = useRef(false)
  const referenceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mounted = useRef(true)
  const normalizedReference = taxExempt ? reference.trim() || null : null
  const dirty = normalizedReference !== controls.support_reference
  const locked = pending || request.current !== null
  const savedVersion = useRef(summary.version)
  useEffect(() => { mounted.current = true; return () => {
    mounted.current = false
    if (referenceTimer.current) clearTimeout(referenceTimer.current)
  } }, [])
  useEffect(() => { onEditingChange(dirty || locked || staleVersion === summary.version) }, [dirty, locked, staleVersion, summary.version, onEditingChange])
  useEffect(() => {
    if (savedVersion.current === summary.version || request.current) return
    savedVersion.current = summary.version
    setSelection(null)
    setReference(controls.support_reference ?? '')
    setError(null)
    setStaleVersion(null)
  }, [summary.version, controls])

  const save = async (nextTaxExempt = taxExempt, nextSupplies = supplies) => {
    if (referenceTimer.current) clearTimeout(referenceTimer.current)
    if (inFlight.current || !mounted.current) return
    if (!request.current && (!controls.can_adjust || staleVersion === summary.version)) return
    const nextReference = nextTaxExempt ? reference.trim() || null : null
    if (!request.current && nextTaxExempt === controls.tax_exempt && nextSupplies === controls.shop_supplies_enabled && nextReference === controls.support_reference) return
    request.current ??= { key: createIdempotencyKey(), body: {
      expected_settlement_version: summary.version, tax_exempt: nextTaxExempt,
      shop_supplies_enabled: nextSupplies, support_reference: nextReference,
    } }
    inFlight.current = true
    setSelection(request.current.body)
    onEditingChange(true)
    setPending(true)
    setError(null)
    try {
      const next = await adjustInvoiceCharges(invoiceId, request.current.body, request.current.key)
      if (!mounted.current) return
      if (next.invoice_id !== invoiceId || !next.charge_controls) throw new Error('Invoice update response could not be verified.')
      request.current = null
      const updated = next.charge_controls
      setSelection(null)
      setReference(updated.support_reference ?? '')
      savedVersion.current = next.version
      queryClient.setQueryData(['invoice-settlement', 'authenticated', invoiceId], next)
      for (const key of ['invoice-settlement-allocations', 'invoice', 'invoices', 'repair-order-detail', 'repair-orders']) {
        void queryClient.invalidateQueries({ queryKey: [key] })
      }
      onUpdated(next)
      onEditingChange(false)
    } catch (failure) {
      if (!mounted.current) return
      const parsed = paymentApiError(failure, 'Invoice update was not confirmed. Retry the same update.')
      setError(parsed.message)
      if (parsed.status && parsed.status >= 400 && parsed.status < 500 && parsed.status !== 408 && parsed.status !== 429) {
        request.current = null
        setSelection(null)
        setReference(controls.support_reference ?? '')
        if (parsed.status === 409 && (parsed.code === 'stale_settlement_version' || typeof parsed.current_version === 'number')) {
          setStaleVersion(summary.version)
          void queryClient.invalidateQueries({ queryKey: ['invoice-settlement', 'authenticated', invoiceId] })
        }
      }
    } finally {
      inFlight.current = false
      if (mounted.current) setPending(false)
    }
  }
  const toggle = (label: string, value: boolean, change: () => void) => <div className="flex items-center justify-between gap-4">
    <span className="text-sm font-semibold">{label}</span>
    <button type="button" role="switch" aria-label={label} aria-checked={value} aria-busy={pending} disabled={!controls.can_adjust || locked || staleVersion === summary.version}
      onPointerDown={event => { if (dirty) event.preventDefault() }}
      onClick={event => { event.currentTarget.focus(); change() }}
      className="flex min-h-11 min-w-11 items-center justify-center rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 disabled:cursor-not-allowed disabled:opacity-50">
      <span aria-hidden="true" className={`relative inline-flex h-6 w-10 shrink-0 rounded-full ${value ? 'bg-emerald-700' : 'bg-slate-300'}`}><span className={`absolute left-1 top-1 h-4 w-4 rounded-full bg-white ${value ? 'translate-x-4' : ''}`} /></span>
    </button>
  </div>
  return <section aria-label="Invoice charges" className={embedded ? 'border-t border-slate-200 pt-2 text-slate-950' : 'rounded-xl border border-slate-200 bg-white px-4 py-3 text-slate-950'}>
    {toggle('Sales tax exemption', taxExempt, () => { void save(!taxExempt, supplies) })}
    {taxExempt && (showReference ? <div className="mb-2 space-y-1">
      <label htmlFor={`${id}-reference`} className="text-xs font-medium">Certificate or supporting reference (optional)</label>
      <input id={`${id}-reference`} maxLength={255} disabled={!controls.can_adjust || locked || staleVersion === summary.version} value={reference} onChange={event => setReference(event.target.value)}
        onBlur={() => { referenceTimer.current = setTimeout(() => { void save() }, 0) }}
        onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); void save() } }}
        className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 disabled:opacity-60" />
    </div> : <button type="button" onClick={() => setShowReference(true)} className="min-h-11 rounded-lg text-xs font-semibold text-slate-600 underline underline-offset-4 focus-visible:ring-2 focus-visible:ring-emerald-700">{reference ? 'View certificate/reference' : 'Add certificate/reference'}</button>)}
    {toggle('Shop supplies', supplies, () => { void save(taxExempt, !supplies) })}
    {pending && <p role="status" className="py-1 text-xs text-slate-500">Updating invoice…</p>}
    {!controls.can_adjust && controls.unavailable_reason && <p className="text-xs text-slate-600">{controls.unavailable_reason}</p>}
    {error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}
    {request.current && !pending && <button type="button" onClick={() => void save()} className="min-h-11 rounded-lg px-2 text-sm font-semibold text-emerald-800 underline focus-visible:ring-2 focus-visible:ring-emerald-700">Retry update</button>}
    {staleVersion === summary.version && <button type="button" onClick={() => { void queryClient.invalidateQueries({ queryKey: ['invoice-settlement', 'authenticated', invoiceId] }) }} className="min-h-11 rounded-lg px-2 text-sm font-semibold text-emerald-800 underline focus-visible:ring-2 focus-visible:ring-emerald-700">Refresh invoice</button>}
  </section>
}
