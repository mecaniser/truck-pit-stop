import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'

import { Spinner } from '@/components/ui'

import { paymentApiError } from './api'
import AccountingReconciliationPanel from './AccountingReconciliationPanel'
import EarlyVehicleReleasePanel from './EarlyVehicleReleasePanel'
import FullCashPaymentPanel from './FullCashPaymentPanel'
import InvoiceTaxExemptionControl from './InvoiceTaxExemptionControl'
import PendingManualPaymentPanel from './PendingManualPaymentPanel'
import SettlementPaymentPanel from './SettlementPaymentPanel'
import SettlementCreditPanel from './SettlementCreditPanel'
import SettlementResolutionPanel from './SettlementResolutionPanel'
import SettlementSummaryCard from './SettlementSummaryCard'
import type { InvoiceSettlementSummary } from './types'
import { useInvoiceAllocations, useInvoiceSettlement } from './useInvoiceSettlement'

export default function StaffSettlementDialog({
  invoiceId,
  invoiceNumber,
  open,
  onClose,
  onUpdated,
}: {
  invoiceId: string
  invoiceNumber: string
  open: boolean
  onClose: () => void
  onUpdated?: () => void
}) {
  const access = open ? { kind: 'authenticated' as const, invoiceId } : null
  const settlementQuery = useInvoiceSettlement(access)
  const allocationsQuery = useInvoiceAllocations(access, open && Boolean(settlementQuery.data))
  const [current, setCurrent] = useState<InvoiceSettlementSummary | null>(null)
  const [editingExemption, setEditingExemption] = useState(false)
  const closeRef = useRef<HTMLButtonElement>(null)
  const dialogRef = useRef<HTMLElement>(null)

  useEffect(() => setCurrent(settlementQuery.data ?? null), [settlementQuery.data])
  useEffect(() => setEditingExemption(false), [invoiceId, open])
  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    closeRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
        return
      }
      if (event.key !== 'Tab') return
      const focusable = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ) ?? []).filter(element => !element.hasAttribute('hidden') && element.offsetParent !== null)
      if (focusable.length === 0) {
        event.preventDefault()
        dialogRef.current?.focus()
        return
      }
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      previous?.focus?.()
    }
  }, [onClose, open])

  if (!open) return null

  const handleUpdated = (next: InvoiceSettlementSummary) => {
    setCurrent(next)
    onUpdated?.()
  }

  return (
    <div className="fixed inset-0 z-[10000] overflow-y-auto bg-black/60 p-3 backdrop-blur-sm sm:p-6" role="presentation" onMouseDown={event => { if (event.currentTarget === event.target) onClose() }}>
      <section ref={dialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="staff-settlement-heading" className="mx-auto w-full max-w-xl overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 shadow-2xl">
        <header className="flex items-start justify-between gap-4 border-b border-slate-200 bg-white px-4 py-4 sm:px-5">
          <div>
            <p className="text-[11px] font-extrabold uppercase tracking-[0.12em] text-slate-500">Invoice {invoiceNumber}</p>
            <h2 id="staff-settlement-heading" className="mt-1 text-lg font-extrabold text-slate-950">Record or review payment</h2>
          </div>
          <button ref={closeRef} type="button" aria-label="Close invoice settlement" onClick={onClose} className="flex h-11 w-11 items-center justify-center rounded-full text-slate-500 hover:bg-slate-100 hover:text-slate-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#b9472f]"><X className="h-5 w-5" /></button>
        </header>

        <div className="max-h-[calc(100vh-8rem)] space-y-4 overflow-y-auto p-4 sm:p-5">
          {settlementQuery.isLoading ? (
            <div className="flex min-h-48 items-center justify-center"><Spinner size="lg" /></div>
          ) : settlementQuery.error || !current ? (
            <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
              <p className="font-bold">Settlement details are unavailable.</p>
              <p className="mt-1">{paymentApiError(settlementQuery.error, 'Refresh and try again. The invoice was not changed.').message}</p>
            </div>
          ) : (
            <>
              <SettlementSummaryCard summary={current} allocations={allocationsQuery.data?.items ?? []} tone="light" />
              <InvoiceTaxExemptionControl key={invoiceId} invoiceId={invoiceId} summary={current} onUpdated={handleUpdated} onEditingChange={setEditingExemption} />
              <fieldset disabled={editingExemption} className="min-w-0 space-y-4 border-0 p-0">
              <PendingManualPaymentPanel
                invoiceId={invoiceId}
                summary={current}
                allocations={allocationsQuery.data?.items ?? []}
                tone="light"
                onUpdated={handleUpdated}
              />
              <SettlementResolutionPanel
                access={{ kind: 'authenticated', invoiceId }}
                summary={current}
                allocations={allocationsQuery.data?.items ?? []}
                audience="staff"
                tone="light"
                onUpdated={handleUpdated}
              />
              <SettlementCreditPanel
                access={{ kind: 'authenticated', invoiceId }}
                summary={current}
                tone="light"
                onUpdated={handleUpdated}
              />
              {current.accounting_sync_status !== 'not_applicable_local_cash' && <AccountingReconciliationPanel
                invoiceId={invoiceId}
                canRetry={current.allowed_actions?.retry_accounting === true}
              />}
              <EarlyVehicleReleasePanel
                invoiceId={invoiceId}
                summary={current}
                onUpdated={handleUpdated}
              />
              <FullCashPaymentPanel
                key={invoiceId}
                invoiceId={invoiceId}
                summary={current}
                onUpdated={handleUpdated}
                onChoosingChange={() => undefined}
              >
              {cash => <SettlementPaymentPanel
                access={{ kind: 'authenticated', invoiceId }}
                summary={current}
                audience="staff"
                tone="light"
                onUpdated={handleUpdated}
                cashTender={cash}
              />}
              </FullCashPaymentPanel>
              </fieldset>
            </>
          )}
        </div>
      </section>
    </div>
  )
}

export { StaffSettlementDialog }
