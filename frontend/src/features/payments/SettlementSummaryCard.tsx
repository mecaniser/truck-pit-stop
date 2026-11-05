import { AlertTriangle, CheckCircle2, ChevronDown, Clock3, RefreshCw } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ControlButton } from '@/components/ui/Controls'

import { formatMoney, isPositiveMoney } from './money'
import type { InvoiceSettlementSummary, PaymentAllocation, SettlementAccess } from './types'
import PaymentAttemptResolutionControls from './PaymentAttemptResolutionControls'
import EfsReviewControls from './EfsReviewControls'
import { EFS_STATUS_LABELS } from './efsApi'
import { CHECKOUT_LABELS } from './attemptResolutionTypes'

const STATE_LABELS: Record<InvoiceSettlementSummary['state'], string> = {
  unpaid: 'Unpaid',
  payment_pending: 'Payment pending',
  partially_paid: 'Partially paid',
  partially_paid_pending: 'Partially paid · payment pending',
  paid: 'Paid in full',
  overpayment_resolution: 'Overpayment resolution in progress',
}

const RAIL_LABELS: Record<PaymentAllocation['rail'], string> = {
  card: 'Card',
  zelle: 'Zelle',
  check: 'Check',
  ach: 'ACH',
  fleet_payment: 'Fleet Check / Code',
  cash: 'Cash',
}

export default function SettlementSummaryCard({
  summary,
  allocations = [],
  tone = 'dark',
  compact = false,
  streamlined = false,
  resolutionOnly = false,
  hideConfirmed = false,
  hideAvailable = false,
  audience = 'staff',
  children,
  resolutionControls,
  reviewAttemptId,
}: {
  summary: InvoiceSettlementSummary
  allocations?: PaymentAllocation[]
  tone?: 'dark' | 'light'
  compact?: boolean
  streamlined?: boolean
  resolutionOnly?: boolean
  hideConfirmed?: boolean
  hideAvailable?: boolean
  audience?: 'staff' | 'customer'
  children?: ReactNode
  resolutionControls?: { access: SettlementAccess; audience: 'customer' | 'guest' | 'staff'; onUpdated: (next: InvoiceSettlementSummary) => void }
  reviewAttemptId?: string
}) {
  const [historyOpen, setHistoryOpen] = useState(false)
  const [closedNotice, setClosedNotice] = useState('')
  const previousStatuses = useRef(new Map(allocations.map(row => [row.attempt_id, row.resolution?.checkout_status])))
  const historyTrigger = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    const closed = allocations.find(row => {
      const before = previousStatuses.current.get(row.attempt_id)
      return before && !['received', 'cancelled', 'failed'].includes(before) && row.resolution && ['received', 'cancelled', 'failed'].includes(row.resolution.checkout_status)
    })
    previousStatuses.current = new Map(allocations.map(row => [row.attempt_id, row.resolution?.checkout_status]))
    if (!closed || audience !== 'customer') return
    setClosedNotice(closed.resolution?.checkout_status === 'received' ? 'Payment received.' : closed.resolution?.can_retry && !closed.resolution.block_reason ? 'Request closed. You can try another payment.' : 'Request updated. See payment history.')
    historyTrigger.current?.focus({ preventScroll: true })
  }, [allocations, audience])
  const focusedAttempt = useRef<string | null>(null)
  const seenEfs = useRef(new Set<string>())
  useEffect(() => {
    const pending = allocations.filter(row => row.efs?.status === 'awaiting_verification')
    const fresh = pending.find(row => !seenEfs.current.has(row.attempt_id))
    pending.forEach(row => seenEfs.current.add(row.attempt_id))
    if (!fresh || audience !== 'customer') return
    const frame = requestAnimationFrame(() => document.getElementById(`payment-request-${fresh.attempt_id}`)?.focus({ preventScroll: true }))
    return () => cancelAnimationFrame(frame)
  }, [allocations, audience])
  useEffect(() => {
    if (!reviewAttemptId || !allocations.some(row => row.attempt_id === reviewAttemptId)) return
    const identity = `${summary.invoice_id}:${reviewAttemptId}`
    if (focusedAttempt.current === identity) return
    const linked = allocations.find(row => row.attempt_id === reviewAttemptId)
    if (linked?.resolution ? ['received', 'cancelled', 'failed'].includes(linked.resolution.checkout_status) : linked?.state !== 'pending') setHistoryOpen(true)
    const frame = requestAnimationFrame(() => {
      const row = document.getElementById(`payment-request-${reviewAttemptId}`)
      if (row) { row.focus({ preventScroll: true }); row.scrollIntoView({ block: 'nearest' }); focusedAttempt.current = identity }
    })
    return () => cancelAnimationFrame(frame)
  }, [allocations, reviewAttemptId, summary.invoice_id])
  const dark = tone === 'dark'
  const panel = dark
    ? 'border-[#2a3245] bg-[#151b27] text-[#edf0f6]'
    : 'border-slate-200 bg-white text-slate-950'
  const quiet = dark ? 'text-[#99a4b7]' : 'text-slate-500'
  const divider = dark ? 'border-[#2a3245]' : 'border-slate-200'
  const manualExternalAccounting = summary.accounting_sync_status === 'external_reconciliation_pending'
  const accountingStatusNotice = manualExternalAccounting || summary.accounting_sync_status === 'pending'
  const paid = summary.state === 'paid'
  const pending = isPositiveMoney(summary.active_pending_principal)
  const resolution = isPositiveMoney(summary.unapplied_credit) || isPositiveMoney(summary.refund_pending)
  const fullyReserved = audience === 'customer' && streamlined && pending && !isPositiveMoney(summary.allocatable_balance) && formatMoney(summary.active_pending_principal) === formatMoney(summary.outstanding_balance)
  const figures = resolutionOnly ? [] : streamlined ? [
    ...(!hideConfirmed && isPositiveMoney(summary.confirmed_principal) ? [['Paid toward invoice', summary.confirmed_principal]] : []),
    ...(pending && !fullyReserved ? [[resolutionControls && allocations.some(row => row.state === 'pending' && row.resolution) ? 'In progress' : 'Pending confirmation', summary.active_pending_principal], ...(!hideAvailable ? [['Available to pay', summary.allocatable_balance]] : [])] : []),
  ] : [
    ['Invoice total', summary.principal_total],
    ['Confirmed', summary.confirmed_principal],
    ['Pending', summary.active_pending_principal],
    ['Available to pay', summary.allocatable_balance],
  ]

  if (summary.payment_verification_required) return (
    <section className={`rounded-2xl border p-4 text-sm ${panel}`} aria-label="Invoice payment summary">
      <h2 className="font-bold">Payment status needs review</h2>
      <dl className="mt-3 flex justify-between gap-4"><dt>Balance due</dt><dd>Unavailable</dd></dl>
      <p className={`mt-3 ${quiet}`}>{audience === 'staff' ? 'Review the verified received amount before collecting another payment.' : 'Contact the shop before making another payment.'}</p>
      {resolutionControls?.audience === 'staff' && allocations.filter(row => row.efs).map(row => <EfsReviewControls key={row.attempt_id} summary={summary} allocation={row} tone={tone} onUpdated={resolutionControls.onUpdated} />)}
    </section>
  )

  const customerCompact = audience === 'customer' && streamlined
  if (customerCompact && !pending && figures.length === 0 && !resolution && allocations.length === 0 && !children) return null

  const activeAllocations = allocations.filter(row => row.resolution
    ? ['checkout_started', 'transfer_reported', 'verification_pending', 'review_required'].includes(row.resolution.checkout_status)
    : row.state === 'pending')
  const pastAllocations = allocations.filter(row => !activeAllocations.includes(row))
  const renderAllocation = (allocation: PaymentAllocation) => (
              <li key={allocation.id} className="px-3 py-2.5 text-sm">
                <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p id={`payment-request-${allocation.attempt_id}`} tabIndex={-1} className="font-semibold">{allocation.efs ? 'EFS' : RAIL_LABELS[allocation.rail]} · <span>{allocation.efs ? EFS_STATUS_LABELS[allocation.efs.status] : allocation.resolution ? (customerCompact && allocation.resolution.checkout_status === 'review_required' ? 'Awaiting shop review' : CHECKOUT_LABELS[allocation.resolution.checkout_status]) : allocation.state.replace(/_/g, ' ')}</span></p>
                  <p className={`truncate text-xs ${quiet}`}>
                    {allocation.efs ? `Code ending in ${allocation.efs.code_last4} · ` : ''}{!customerCompact && allocation.actor_name ? `${allocation.actor_name} · ` : ''}
                    {allocation.reference_number ? `Ref ${allocation.reference_number} · ` : ''}
                    {(!customerCompact || !activeAllocations.includes(allocation)) && new Date(allocation.confirmed_at || allocation.created_at).toLocaleString()}
                  </p>
                  {isPositiveMoney(allocation.card_fee_amount) && (
                    <p className={`mt-0.5 text-[11px] ${quiet}`}>
                      Card fee {formatMoney(allocation.card_fee_amount)}
                      {isPositiveMoney(allocation.card_fee_tax_amount) ? ` · fee tax ${formatMoney(allocation.card_fee_tax_amount)}` : ''}
                      {' · '}{allocation.state === 'confirmed' ? 'charged' : 'checkout total'} {formatMoney(allocation.provider_charge_amount)}
                    </p>
                  )}
                </div>
                <span className="shrink-0 text-right font-bold tabular-nums">{!customerCompact && (allocation.state === 'pending' || Boolean(allocation.resolution && ['cancelled', 'failed'].includes(allocation.resolution.checkout_status))) && <span className={`block text-[11px] font-normal ${quiet}`}>Requested</span>}{formatMoney(allocation.state === 'pending' || Boolean(allocation.resolution && ['cancelled', 'failed'].includes(allocation.resolution.checkout_status)) ? allocation.principal_amount : allocation.applied_principal_amount)}</span>
                </div>
                {resolutionControls?.audience === 'staff' && allocation.efs && <EfsReviewControls allocation={allocation} summary={summary} tone={tone} onUpdated={resolutionControls.onUpdated} />}
                {resolutionControls && !summary.payment_verification_required && <PaymentAttemptResolutionControls {...resolutionControls} allocation={allocation} summary={summary} tone={tone} />}
              </li>
  )

  return (
    <section className={`overflow-hidden rounded-2xl border ${panel}`} aria-labelledby={customerCompact ? undefined : `settlement-${summary.invoice_id}`} aria-label={customerCompact ? "Payment details" : undefined}>
      {!customerCompact && <div className={`flex flex-wrap items-start justify-between gap-3 ${compact ? 'p-3' : 'p-4'}`}>
        <div>
          {!streamlined && <p className={`text-[11px] font-extrabold uppercase tracking-[0.12em] ${quiet}`}>Invoice settlement</p>}
          <h2 id={`settlement-${summary.invoice_id}`} className="mt-1 flex items-center gap-2 text-sm font-extrabold">
            {paid ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : pending ? <Clock3 className="h-4 w-4 text-amber-500" /> : <RefreshCw className="h-4 w-4 text-sky-500" />}
            {paid && summary.accounting_sync_status === 'not_applicable_local_cash' ? 'Paid in cash' : STATE_LABELS[summary.state]}
          </h2>
        </div>
        <p className="text-right">
          <span className={`block text-xs ${quiet}`}>{streamlined ? 'Balance due' : 'Outstanding'}</span>
          <span className="block text-2xl font-extrabold tabular-nums">{formatMoney(summary.outstanding_balance)}</span>
        </p>
      </div>}

      {figures.length > 0 && <dl className={`flex flex-wrap border-t ${divider}`}>
        {figures.map(([label, value]) => (
          <div key={label} className={`min-w-[120px] flex-1 border-r px-3 py-2.5 last:border-r-0 ${divider}`}>
            <dt className={`text-[11px] ${quiet}`}>{label}</dt>
            <dd className="mt-0.5 font-bold tabular-nums">{formatMoney(value)}</dd>
          </div>
        ))}
      </dl>}

      {audience === 'customer' && pending && <p className={`border-t px-3 py-3 text-sm ${divider} ${quiet}`}>
        Don’t pay an amount in progress again.
      </p>}

      {children}

      {resolution && (
        <div className={`flex gap-2 border-t px-3 py-3 text-sm ${divider} ${dark ? 'bg-amber-400/10 text-amber-200' : 'bg-amber-50 text-amber-900'}`}>
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            {isPositiveMoney(summary.refund_pending) && <span className="block">{formatMoney(summary.refund_pending)} refund pending.</span>}
            {isPositiveMoney(summary.unapplied_credit) && <span className="block">{formatMoney(summary.unapplied_credit)} is unapplied. Review this amount before deciding whether to refund it or retain it as customer credit with the customer’s consent.</span>}
          </p>
        </div>
      )}

      {audience === 'staff' && summary.accounting_sync_status !== 'synced'
        && summary.accounting_sync_status !== 'not_applicable_local_cash'
        && summary.accounting_sync_status !== 'not_started'
        && summary.accounting_sync_status !== 'not_required' && (
        <div className={`border-t px-3 py-2.5 text-xs ${divider} ${accountingStatusNotice ? quiet : 'text-red-500'}`} role={accountingStatusNotice ? 'status' : 'alert'}>
          {manualExternalAccounting
            ? 'Original invoice accounting is reconciled manually with ETS.'
            : summary.accounting_sync_status === 'pending'
            ? 'Payment recorded. QuickBooks accounting sync is pending; no duplicate payment is needed.'
            : 'QuickBooks accounting sync needs staff attention. The payment remains recorded in DieselBridge.'}
        </div>
      )}

      {audience === 'staff' && summary.accounting_sync_status === 'not_applicable_local_cash' && (
        <p className={`border-t px-3 py-2.5 text-xs ${divider} ${quiet}`}>Cash recorded locally. Not synced to QuickBooks.</p>
      )}

      {!resolutionOnly && allocations.length > 0 && (
        customerCompact ? <>
          {closedNotice && <p role="status" className={`border-t px-3 py-3 text-sm ${divider} ${quiet}`}>{closedNotice}</p>}
          {activeAllocations.length > 0 && <div className={`border-t ${divider}`}>
            <h2 className="px-3 pt-3 text-sm font-semibold">Payment requests</h2>
            <ol aria-label="Active payment requests" className={`divide-y ${dark ? 'divide-[#2a3245]' : 'divide-slate-200'}`}>
              {activeAllocations.map(renderAllocation)}
            </ol>
          </div>}
          {pastAllocations.length > 0 && <div className={`border-t ${divider}`}>
            <ControlButton ref={historyTrigger} type="button" aria-expanded={historyOpen} aria-controls={`payment-history-${summary.invoice_id}`} onClick={() => setHistoryOpen(open => !open)} className="flex w-full items-center justify-between gap-3 px-3 text-sm font-semibold">
              <span>Payment history <span className={quiet}>({pastAllocations.length})</span></span><ChevronDown size={16} aria-hidden="true" className={historyOpen ? 'rotate-180' : undefined} />
            </ControlButton>
            {historyOpen && <ol id={`payment-history-${summary.invoice_id}`} aria-label="Past payment requests" className={`divide-y ${dark ? 'divide-[#2a3245]' : 'divide-slate-200'}`}>
              {pastAllocations.map(renderAllocation)}
            </ol>}
          </div>}
        </> : <div className={`border-t ${divider}`}>
          <p className={`px-3 pt-3 text-[11px] font-extrabold uppercase tracking-[0.12em] ${quiet}`}>Payment history</p>
          <ol id={`payment-activity-${summary.invoice_id}`} className={`divide-y ${dark ? 'divide-[#2a3245]' : 'divide-slate-200'}`}>
            {allocations.map(renderAllocation)}
          </ol>
        </div>
      )}
    </section>
  )
}

export { SettlementSummaryCard }
