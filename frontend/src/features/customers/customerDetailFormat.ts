/**
 * Formatting a customer's balance, source, and registration numbers.
 *
 * These lived inside CustomersPage while it was the only screen that showed a
 * customer. The repair-order workspace shows one too now, and a balance that
 * reads "Due $13,152.39" on one screen and something else on the other is the
 * kind of difference that makes an operator distrust both.
 */

export const numericBalance = (value?: string | null): number => {
  const parsed = Number.parseFloat(value || '0')
  return Number.isFinite(parsed) ? parsed : 0
}

export const absoluteCurrency = (value: number): string =>
  Math.abs(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })

/** "Due $1,234.00" / "Credit $50.00" / "$0.00" — the sign is stated, not implied. */
export const balanceLabel = (value?: string | null): string => {
  const balance = numericBalance(value)
  if (balance > 0) return `Due $${absoluteCurrency(balance)}`
  if (balance < 0) return `Credit $${absoluteCurrency(balance)}`
  return '$0.00'
}

export const balanceAmountLabel = (value?: string | null): string =>
  `$${absoluteCurrency(numericBalance(value))}`

export const balanceLabelClass = (value?: string | null, dark = false): string => {
  const balance = numericBalance(value)
  if (balance > 0) return dark ? 'text-amber-400' : 'text-amber-700'
  if (balance < 0) return dark ? 'text-emerald-300' : 'text-emerald-700'
  return dark ? 'text-white/70' : 'text-slate-700'
}

/** "US DOT 3269385" -> "3269385". The label is already on the field. */
export const stripRegNumber = (value?: string | null): string =>
  (value || '').replace(/^\s*(us\s*dot|dot|mc)[\s#:-]*/i, '').trim()

export const formatCustomerSource = (source?: string | null): string | null => {
  if (!source) return null
  if (source === 'walk_in') return 'Walk-in'
  if (source === 'zelle') return 'Zelle'
  if (source === 'portal') return 'Portal'
  return source.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

/** One repair order in a customer's service history. */
export interface CustomerHistoryItem {
  id: string
  order_number: string
  status: string
  vehicle_make: string
  vehicle_model: string
  vehicle_year: number | null
  vehicle_unit_number: string | null
  total_cost: string
  savings: string
  created_at: string | null
  work_completed_at: string | null
}

export interface CustomerHistoryResponse {
  items: CustomerHistoryItem[]
  stats: {
    total_orders: number
    completed_orders: number
    lifetime_spend: string
    lifetime_savings: string
  }
}
