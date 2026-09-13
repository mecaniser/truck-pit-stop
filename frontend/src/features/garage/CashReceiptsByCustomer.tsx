import { ChevronDown } from 'lucide-react'
import { centsToMoney, formatMoney, moneyToCents } from '../payments/money'

export interface CashReceipt {
  customer_id?: string
  invoice_id?: string
  payment_id: string
  payment_number: string
  invoice_number: string
  customer_name: string
  received_at: string
  amount: string
}

export default function CashReceiptsByCustomer({ receipts }: { receipts: CashReceipt[] }) {
  const groups = new Map<string, { name: string; receipts: CashReceipt[]; total: bigint; valid: boolean; invoices: Set<string> }>()
  for (const receipt of receipts) {
    // An older API cannot safely establish that equal names mean the same account.
    const key = receipt.customer_id || `receipt:${receipt.payment_id}`
    const group = groups.get(key) ?? { name: receipt.customer_name.trim() || 'Unnamed customer', receipts: [], total: 0n, valid: true, invoices: new Set<string>() }
    const cents = moneyToCents(receipt.amount)
    group.total += cents ?? 0n
    group.valid &&= cents !== null
    group.receipts.push(receipt)
    group.invoices.add(receipt.invoice_id || receipt.invoice_number)
    groups.set(key, group)
  }
  const sorted = [...groups].sort(([, a], [, b]) => a.total === b.total ? a.name.localeCompare(b.name) : a.total > b.total ? -1 : 1)
  return <ul className="divide-y divide-white/[0.06]" aria-label="Cash receipts by customer">
    {sorted.map(([id, group]) => <li key={id}>
      <details className="group/customer">
        <summary className="list-none [&::-webkit-details-marker]:hidden flex min-h-14 cursor-pointer items-center gap-3 py-3 text-white/85 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px]">
          <ChevronDown aria-hidden="true" className="h-4 w-4 shrink-0 transition-transform group-open/customer:rotate-180 motion-reduce:transition-none" />
          <span className="min-w-0 flex-1">
            <span className="block break-words text-sm font-semibold">{group.name}</span>
            <span className="block text-xs text-white/50">{group.invoices.size} {group.invoices.size === 1 ? 'invoice' : 'invoices'} · {group.receipts.length} cash {group.receipts.length === 1 ? 'receipt' : 'receipts'}</span>
          </span>
          <span className="shrink-0 text-sm font-semibold tabular-nums">{group.valid ? formatMoney(centsToMoney(group.total)) : 'Unavailable'}</span>
        </summary>
        <ul aria-label={`${group.name} cash invoices`} className="ml-7 divide-y divide-white/[0.06] border-t border-white/[0.06]">
          {group.receipts.map(receipt => <li key={receipt.payment_id} className="flex items-start justify-between gap-3 py-3">
            <div className="min-w-0 text-sm">
              <p className="break-words text-white/85">{receipt.payment_number} · {receipt.invoice_number}</p>
              <time className="text-xs text-white/50" dateTime={receipt.received_at}>{new Date(receipt.received_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })} UTC</time>
            </div>
            <span className="shrink-0 text-sm tabular-nums text-white/85">{moneyToCents(receipt.amount) === null ? 'Unavailable' : formatMoney(receipt.amount)}</span>
          </li>)}
        </ul>
      </details>
    </li>)}
  </ul>
}
