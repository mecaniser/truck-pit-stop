import { AlertTriangle, CheckCircle2, Clock3, RefreshCw } from 'lucide-react'

import { formatMoney, isPositiveMoney } from './money'
import type { InvoiceSettlementSummary, PaymentAllocation } from './types'

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
  cash: 'Cash',
}

export default function SettlementSummaryCard({
  summary,
  allocations = [],
  tone = 'dark',
  compact = false,
}: {
  summary: InvoiceSettlementSummary
  allocations?: PaymentAllocation[]
  tone?: 'dark' | 'light'
  compact?: boolean
}) {
  const dark = tone === 'dark'
  const panel = dark
    ? 'border-[#2a3245] bg-[#151b27] text-[#edf0f6]'
    : 'border-slate-200 bg-white text-slate-950'
  const quiet = dark ? 'text-[#99a4b7]' : 'text-slate-500'
  const divider = dark ? 'border-[#2a3245]' : 'border-slate-200'
  const paid = summary.state === 'paid'
  const pending = isPositiveMoney(summary.active_pending_principal)
  const resolution = isPositiveMoney(summary.unapplied_credit) || isPositiveMoney(summary.refund_pending)

  return (
    <section className={`overflow-hidden rounded-2xl border ${panel}`} aria-labelledby={`settlement-${summary.invoice_id}`}>
      <div className={`flex flex-wrap items-start justify-between gap-3 ${compact ? 'p-3' : 'p-4'}`}>
        <div>
          <p className={`text-[11px] font-extrabold uppercase tracking-[0.12em] ${quiet}`}>Invoice settlement</p>
          <h2 id={`settlement-${summary.invoice_id}`} className="mt-1 flex items-center gap-2 text-sm font-extrabold">
            {paid ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : pending ? <Clock3 className="h-4 w-4 text-amber-500" /> : <RefreshCw className="h-4 w-4 text-sky-500" />}
            {paid && summary.accounting_sync_status === 'not_applicable_local_cash' ? 'Paid in cash' : STATE_LABELS[summary.state]}
          </h2>
        </div>
        <p className="text-right">
          <span className={`block text-[11px] font-bold uppercase tracking-wide ${quiet}`}>Outstanding</span>
          <span className="block text-2xl font-extrabold tabular-nums">{formatMoney(summary.outstanding_balance)}</span>
        </p>
      </div>

      <dl className={`grid grid-cols-2 border-t ${divider} sm:grid-cols-4`}>
        {[
          ['Invoice total', summary.principal_total],
          ['Confirmed', summary.confirmed_principal],
          ['Pending', summary.active_pending_principal],
          ['Available to pay', summary.allocatable_balance],
        ].map(([label, value]) => (
          <div key={label} className={`border-r px-3 py-2.5 last:border-r-0 ${divider}`}>
            <dt className={`text-[11px] ${quiet}`}>{label}</dt>
            <dd className="mt-0.5 font-bold tabular-nums">{formatMoney(value)}</dd>
          </div>
        ))}
      </dl>

      {resolution && (
        <div className={`flex gap-2 border-t px-3 py-3 text-sm ${divider} ${dark ? 'bg-amber-400/10 text-amber-200' : 'bg-amber-50 text-amber-900'}`}>
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            {isPositiveMoney(summary.refund_pending)
              ? `${formatMoney(summary.refund_pending)} refund pending.`
              : `${formatMoney(summary.unapplied_credit)} is unapplied and must be refunded or explicitly accepted as customer credit.`}
          </p>
        </div>
      )}

      {summary.accounting_sync_status !== 'synced'
        && summary.accounting_sync_status !== 'not_applicable_local_cash'
        && summary.accounting_sync_status !== 'not_started'
        && summary.accounting_sync_status !== 'not_required' && (
        <div className={`border-t px-3 py-2.5 text-xs ${divider} ${summary.accounting_sync_status === 'pending' ? quiet : 'text-red-500'}`} role={summary.accounting_sync_status === 'pending' ? 'status' : 'alert'}>
          {summary.accounting_sync_status === 'pending'
            ? 'Payment recorded. QuickBooks accounting sync is pending; no duplicate payment is needed.'
            : 'QuickBooks accounting sync needs staff attention. The payment remains recorded in DieselBridge.'}
        </div>
      )}

      {summary.accounting_sync_status === 'not_applicable_local_cash' && (
        <p className={`border-t px-3 py-2.5 text-xs ${divider} ${quiet}`}>Cash recorded locally. Not synced to QuickBooks.</p>
      )}

      {allocations.length > 0 && (
        <div className={`border-t ${divider}`}>
          <p className={`px-3 pt-3 text-[11px] font-extrabold uppercase tracking-[0.12em] ${quiet}`}>Payment history</p>
          <ol className={`divide-y ${dark ? 'divide-[#2a3245]' : 'divide-slate-200'}`}>
            {allocations.map((allocation) => (
              <li key={allocation.id} className="flex items-start justify-between gap-3 px-3 py-2.5 text-sm">
                <div className="min-w-0">
                  <p className="font-semibold">{RAIL_LABELS[allocation.rail]} · <span className="capitalize">{allocation.state.replace(/_/g, ' ')}</span></p>
                  <p className={`truncate text-xs ${quiet}`}>
                    {allocation.actor_name ? `${allocation.actor_name} · ` : ''}
                    {allocation.reference_number ? `Ref ${allocation.reference_number} · ` : ''}
                    {new Date(allocation.confirmed_at || allocation.created_at).toLocaleString()}
                  </p>
                  {isPositiveMoney(allocation.card_fee_amount) && (
                    <p className={`mt-0.5 text-[11px] ${quiet}`}>
                      Card fee {formatMoney(allocation.card_fee_amount)}
                      {isPositiveMoney(allocation.card_fee_tax_amount) ? ` · fee tax ${formatMoney(allocation.card_fee_tax_amount)}` : ''}
                      {' · '}charged {formatMoney(allocation.provider_charge_amount)}
                    </p>
                  )}
                </div>
                <span className="shrink-0 font-bold tabular-nums">{formatMoney(allocation.applied_principal_amount)}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  )
}

export { SettlementSummaryCard }
