import type { CashReceiptSummary } from '@/types'

export default function CashReceiptBreakdown({ receipt }: { receipt: CashReceiptSummary }) {
  const rows = [
    ['Services & parts', receipt.subtotal],
    ['Shop supplies', receipt.shop_supplies_amount],
    ['Card processing fee', receipt.service_fee_amount],
    [Number(receipt.tax_amount) === 0 ? 'Sales tax — not charged' : 'Sales tax', receipt.tax_amount],
    ...(Number(receipt.discount_amount) > 0 ? [['Discount', `-${receipt.discount_amount}`]] : []),
    ['Total paid', receipt.amount],
    ['Balance due', '0.00'],
  ]
  return <dl aria-label="Recorded cash payment">
    {rows.map(([label, amount]) => <div key={label} className="flex items-center justify-between gap-3 border-b border-[#1e2432] py-[9px] text-[13px] last:border-0">
      <dt className="text-[#9aa1b3]">{label}</dt>
      <dd className="whitespace-nowrap font-semibold text-[#eceef4] tabular-nums">${Number(amount).toFixed(2)}</dd>
    </div>)}
  </dl>
}
