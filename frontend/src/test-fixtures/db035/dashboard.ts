import { deepFreeze } from './appearance'

const order = (
  id: string,
  orderNumber: string,
  status: string,
  customerName: string,
  vehicleInfo: string,
  totalCost: string,
  mechanicName: string | null = null,
) => ({
  id,
  order_number: orderNumber,
  status,
  pending_zelle_confirmation: false,
  description: 'Source-grounded dashboard fixture',
  customer_name: customerName,
  vehicle_info: vehicleInfo,
  total_cost: totalCost,
  created_at: '2026-08-11T12:00:00Z',
  updated_at: '2026-08-11T12:30:00Z',
  mechanic_name: mechanicName,
  work_started_at: status === 'in_progress' ? '2026-08-11T12:15:00Z' : null,
  hold_reason: null,
  held_at: null,
  quote_sent: status !== 'draft',
})

export const dashboardActionQueueFixture = deepFreeze({
  total_customers: 3,
  total_vehicles: 4,
  total_repair_orders: 3,
  orders_by_status: [
    { status: 'draft', count: 1 },
    { status: 'in_progress', count: 1 },
    { status: 'completed', count: 1 },
  ],
  active_orders: 2,
  awaiting_approval: 0,
  pending_invoices: 1,
  low_stock_count: 0,
  recent_orders: [],
  my_assigned_orders: 0,
  my_in_progress: 0,
  revenue: {
    today: '0', this_week: '0', this_month: '0', total_paid_orders: 0,
    today_parts_margin: '0', this_week_parts_margin: '0', this_month_parts_margin: '0',
    today_gross_profit: '0', this_week_gross_profit: '0', this_month_gross_profit: '0',
    today_ppi: '0', this_week_ppi: '0', this_month_ppi: '0',
  },
  mechanic_workload: [],
  overdue_approvals: 0,
  declined_quotes: 0,
  orders_needing_action: [
    order('ro-needs-action', 'RO-2025-0417', 'draft', 'NorthStar Logistics', '2021 Freightliner Cascadia 126', '4494.62'),
  ],
  orders_needing_action_has_more: false,
  orders_on_floor: [
    order('ro-on-floor', 'RO-2025-0418', 'in_progress', '77 Cargo LLC', '2023 Freightliner Cascadia 126', '1285.00', 'M. Reyes'),
  ],
  orders_on_floor_has_more: false,
  orders_ready_to_close: [
    order('ro-ready-close', 'RO-2025-0419', 'completed', 'Long Haul Transportation', '2020 Volvo VNR 640', '230.00'),
  ],
  orders_ready_to_close_has_more: false,
})

export const dashboardFixture = dashboardActionQueueFixture

export const emptyDashboardFixture = deepFreeze({
  ...dashboardActionQueueFixture,
  total_customers: 0,
  total_vehicles: 0,
  total_repair_orders: 0,
  orders_by_status: [],
  active_orders: 0,
  pending_invoices: 0,
  orders_needing_action: [],
  orders_on_floor: [],
  orders_ready_to_close: [],
})
