export type CursorPage<T> = { items: T[]; next_cursor: string | null }

export type ActivityCategory = 'catalog' | 'stock' | 'repairs' | 'purchasing' | 'returns' | 'sales'

export type ActivityEvent = {
  id: string
  inventory_id: string
  category: ActivityCategory
  event_type: string
  occurred_at: string
  correlation_id: string
  origin: 'live' | 'baseline' | 'backfill' | string
  part?: { id: string; sku: string | null; name: string | null } | null
  inventory?: { id: string; sku: string; name: string } | null
  actor: { id: string | null; name: string } | null
  reason: { code?: string | null; note?: string | null } | null
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  stock: {
    physical_on_hand?: number | null
    held_for_checkout?: number | null
    available_to_sell?: number | null
    delta?: number | null
    balance_after?: number | null
    wac?: string | null
  } | null
  money: {
    list_price?: string | null
    charged_price?: string | null
    tax?: string | null
    fee?: string | null
  } | null
  payment: { tender?: string | null; status?: string | null } | null
  source: { type: string; id: string; number: string | null; href: string | null } | null
}

export type LifecycleSummary = {
  inventory_id: string
  as_of: string
  repairs: { units_used: string; repair_order_count: number; last_used_at: string | null }
  purchasing: { units_received: number; receipt_count: number; units_returned_to_vendor: number; open_core_obligations: number }
  sales: { units_sold: number; units_returned: number; net_units: number; gross_item_revenue: string; discounts: string; refunds: string; net_item_revenue: string; last_sold_at: string | null }
  activity: { event_count: number; last_event_at: string | null }
}

export type CounterSaleStatus = 'draft' | 'completed' | 'partially_returned' | 'returned' | 'cancelled'
export type CounterSaleTender = 'cash' | 'check' | 'ach' | 'zelle' | 'external_terminal' | 'fleet_reference' | 'other'

export type CounterSaleLine = {
  id: string
  inventory_id: string
  sku: string
  name: string
  unit_type: string | null
  quantity: number
  returned_quantity: number
  remaining_returnable_quantity: number
  unit_cost: string
  list_unit_price: string
  charged_unit_price: string
  discount_amount: string
  item_subtotal: string
  tax_amount: string
  total_amount: string
  price_override_reason: string | null
  physical_on_hand: number
  held_for_checkout: number
  available_to_sell: number
}

export type CounterSaleAttempt = {
  id: string
  tender: CounterSaleTender
  state: 'succeeded'
  amount: string
  reference: string | null
  created_at: string
}

export type CounterSaleReturnLine = {
  id: string
  sale_line_id: string
  quantity: number
  reason: string
  disposition: 'restock' | 'damaged'
  item_amount: string
  tax_amount: string
}

export type CounterSaleReturn = {
  id: string
  sale_id: string
  version: number
  state: 'completed'
  item_amount: string
  tax_amount: string
  refund_amount: string
  reason: string | null
  refund_reference: string | null
  lines: CounterSaleReturnLine[]
  created_at: string
  completed_at: string | null
}

export type CounterSale = {
  id: string
  sale_number: string
  status: CounterSaleStatus
  version: number
  customer_id: string | null
  buyer_name: string | null
  buyer_email: string | null
  buyer_phone: string | null
  currency: 'USD'
  list_subtotal: string
  charged_subtotal: string
  discount_amount: string
  tax_amount: string
  total_amount: string
  lines: CounterSaleLine[]
  payment_attempts: CounterSaleAttempt[]
  returns: CounterSaleReturn[]
  allowed_actions: Array<'edit_draft' | 'checkout' | 'cancel' | 'download_receipt' | 'create_return'>
  created_at: string
  updated_at: string
  completed_at: string | null
  cancelled_at: string | null
}

export type CounterSaleListItem = Pick<CounterSale, 'id' | 'sale_number' | 'status' | 'buyer_name' | 'buyer_email' | 'total_amount' | 'created_at' | 'completed_at'> & {
  line_count: number
  tender?: CounterSaleTender | null
}

export type CounterSaleDraftLine = {
  inventory_id: string
  quantity: number
  charged_unit_price?: string
  price_override_reason?: string
}

export const COUNTER_SALE_TENDER_LABELS: Record<CounterSaleTender, string> = {
  cash: 'Cash',
  check: 'Check',
  ach: 'ACH',
  zelle: 'Zelle',
  external_terminal: 'External terminal',
  fleet_reference: 'Fleet reference',
  other: 'Other',
}

export const MANUAL_TENDERS = Object.keys(COUNTER_SALE_TENDER_LABELS) as CounterSaleTender[]
