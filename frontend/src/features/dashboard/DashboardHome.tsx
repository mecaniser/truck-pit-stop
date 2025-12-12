import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../lib/api'
import { useAuthStore } from '../../stores/authStore'

interface StatusCount {
  status: string
  count: number
}

interface RecentOrder {
  id: string
  order_number: string
  status: string
  description: string | null
  customer_name: string
  vehicle_info: string
  total_cost: string
  created_at: string
  updated_at: string
}

interface LowStockItem {
  id: string
  sku: string
  name: string
  stock_quantity: number
  reorder_level: number
}

interface MechanicWorkload {
  mechanic_id: string
  mechanic_name: string
  assigned_count: number
  in_progress_count: number
}

interface RevenueStats {
  today: string
  this_week: string
  this_month: string
  total_paid_orders: number
}

interface DashboardStats {
  total_customers: number
  total_vehicles: number
  total_repair_orders: number
  orders_by_status: StatusCount[]
  active_orders: number
  awaiting_approval: number
  pending_invoices: number
  low_stock_count: number
  low_stock_items: LowStockItem[]
  recent_orders: RecentOrder[]
  my_assigned_orders: number
  my_in_progress: number
  revenue: RevenueStats
  mechanic_workload: MechanicWorkload[]
}

const STATUS_PIPELINE = [
  { key: 'draft', label: 'Draft', color: 'bg-gray-500' },
  { key: 'quoted', label: 'Quoted', color: 'bg-blue-500' },
  { key: 'approved', label: 'Approved', color: 'bg-cyan-500' },
  { key: 'in_progress', label: 'In Progress', color: 'bg-amber-500' },
  { key: 'completed', label: 'Completed', color: 'bg-green-500' },
  { key: 'invoiced', label: 'Invoiced', color: 'bg-purple-500' },
  { key: 'paid', label: 'Paid', color: 'bg-emerald-600' },
]

const STATUS_BADGE_COLORS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  quoted: 'bg-blue-100 text-blue-700',
  approved: 'bg-cyan-100 text-cyan-700',
  in_progress: 'bg-amber-100 text-amber-700',
  completed: 'bg-green-100 text-green-700',
  invoiced: 'bg-purple-100 text-purple-700',
  paid: 'bg-emerald-100 text-emerald-700',
  cancelled: 'bg-red-100 text-red-700',
}

export default function DashboardHome() {
  const { user } = useAuthStore()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const isMechanic = user?.role === 'mechanic'
  const isManager = user?.role === 'garage_admin' || user?.role === 'super_admin'

  useEffect(() => {
    fetchStats()
  }, [])

  const fetchStats = async () => {
    try {
      const response = await api.get('/dashboard/stats')
      setStats(response.data)
    } catch (err) {
      setError('Failed to load dashboard stats')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const getStatusCount = (status: string) => {
    return stats?.orders_by_status.find((s) => s.status === status)?.count || 0
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-amber-500"></div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-red-400">{error}</p>
        <button onClick={fetchStats} className="mt-4 text-amber-500 hover:text-amber-400">
          Try again
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white">
            {isMechanic ? 'My Workbench' : 'Garage Cockpit'}
          </h1>
          <p className="text-gray-400 mt-1">
            {isMechanic
              ? `You have ${stats?.my_in_progress || 0} jobs in progress`
              : `Welcome back, ${user?.full_name || user?.email}`}
          </p>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {isMechanic ? (
          <>
            <KPICard
              title="My Assigned Jobs"
              value={stats?.my_assigned_orders || 0}
              icon="🔧"
              color="amber"
            />
            <KPICard
              title="In Progress"
              value={stats?.my_in_progress || 0}
              icon="⚡"
              color="blue"
            />
          </>
        ) : (
          <>
            <KPICard
              title="Active Repairs"
              value={stats?.active_orders || 0}
              icon="🔧"
              color="amber"
              linkTo="/dashboard/repair-orders?status=in_progress"
            />
            <KPICard
              title="Awaiting Approval"
              value={stats?.awaiting_approval || 0}
              icon="📋"
              color="blue"
              linkTo="/dashboard/repair-orders?status=quoted"
            />
            <KPICard
              title="Ready to Invoice"
              value={stats?.pending_invoices || 0}
              icon="💰"
              color="green"
              linkTo="/dashboard/repair-orders?status=completed"
            />
            <KPICard
              title="Low Stock Items"
              value={stats?.low_stock_count || 0}
              icon="📦"
              color={stats?.low_stock_count ? 'red' : 'gray'}
              linkTo="/dashboard/inventory"
            />
          </>
        )}
      </div>

      {/* Quick Actions */}
      {isManager && (
        <div className="bg-white/5 rounded-xl p-4 sm:p-6 border border-white/10">
          <h2 className="text-lg font-semibold text-white mb-4">Quick Actions</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <QuickActionButton
              to="/dashboard/repair-orders"
              icon="➕"
              label="New Repair Order"
              color="amber"
            />
            <QuickActionButton
              to="/dashboard/customers"
              icon="👤"
              label="Add Customer"
              color="blue"
            />
            <QuickActionButton
              to="/dashboard/vehicles"
              icon="🚛"
              label="Add Vehicle"
              color="cyan"
            />
            <QuickActionButton
              to="/dashboard/inventory"
              icon="📦"
              label="Manage Inventory"
              color="purple"
            />
          </div>
        </div>
      )}

      {/* Status Pipeline Board */}
      <div className="bg-white/5 rounded-xl p-4 sm:p-6 border border-white/10">
        <h2 className="text-lg font-semibold text-white mb-4">Order Pipeline</h2>
        {/* Mobile: horizontal scroll, Desktop: grid */}
        <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
          <div className="flex sm:grid sm:grid-cols-7 gap-2 min-w-max sm:min-w-0">
            {STATUS_PIPELINE.map((stage) => {
              const count = getStatusCount(stage.key)
              return (
                <div
                  key={stage.key}
                  className="bg-white/5 rounded-lg p-3 text-center border border-white/10 hover:border-white/20 transition-colors min-w-[72px] sm:min-w-0"
                >
                  <div className={`w-3 h-3 ${stage.color} rounded-full mx-auto mb-2`}></div>
                  <div className="text-xl sm:text-2xl font-bold text-white">{count}</div>
                  <div className="text-xs text-gray-400 whitespace-nowrap">{stage.label}</div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Two Column Layout: Recent Activity + Low Stock */}
      <div className="grid lg:grid-cols-3 gap-6">
        {/* Recent Activity */}
        <div className="lg:col-span-2 bg-white/5 rounded-xl p-4 sm:p-6 border border-white/10">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Recent Activity</h2>
            <Link
              to="/dashboard/repair-orders"
              className="text-sm text-amber-500 hover:text-amber-400"
            >
              View All
            </Link>
          </div>
          <div className="space-y-3">
            {stats?.recent_orders.length === 0 ? (
              <p className="text-gray-400 text-center py-8">No repair orders yet</p>
            ) : (
              stats?.recent_orders.slice(0, 8).map((order) => (
                <Link
                  key={order.id}
                  to={`/dashboard/repair-orders/${order.id}`}
                  className="block bg-white/5 rounded-lg p-3 hover:bg-white/10 transition-colors border border-white/5"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-white text-sm">
                          {order.order_number}
                        </span>
                        <span
                          className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_BADGE_COLORS[order.status] || 'bg-gray-100 text-gray-700'}`}
                        >
                          {order.status.replace('_', ' ')}
                        </span>
                      </div>
                      <p className="text-gray-400 text-sm truncate mt-1">
                        {order.customer_name} • {order.vehicle_info}
                      </p>
                      {order.description && (
                        <p className="text-gray-500 text-xs truncate mt-0.5">
                          {order.description}
                        </p>
                      )}
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-sm font-medium text-white">
                        ${parseFloat(order.total_cost).toFixed(2)}
                      </div>
                      <div className="text-xs text-gray-500">{formatDate(order.updated_at)}</div>
                    </div>
                  </div>
                </Link>
              ))
            )}
          </div>
        </div>

        {/* Low Stock Alerts */}
        {isManager && (
          <div className="bg-white/5 rounded-xl p-4 sm:p-6 border border-white/10">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">Low Stock Alerts</h2>
              <Link
                to="/dashboard/inventory"
                className="text-sm text-amber-500 hover:text-amber-400"
              >
                Inventory
              </Link>
            </div>
            {stats?.low_stock_items.length === 0 ? (
              <div className="text-center py-8">
                <div className="text-3xl mb-2">✅</div>
                <p className="text-gray-400">All stock levels OK</p>
              </div>
            ) : (
              <div className="space-y-2">
                {stats?.low_stock_items.map((item) => (
                  <div
                    key={item.id}
                    className="bg-red-500/10 border border-red-500/20 rounded-lg p-3"
                  >
                    <div className="font-medium text-white text-sm truncate">{item.name}</div>
                    <div className="text-xs text-gray-400">SKU: {item.sku}</div>
                    <div className="flex items-center justify-between mt-1">
                      <span className="text-red-400 text-sm font-medium">
                        {item.stock_quantity} left
                      </span>
                      <span className="text-gray-500 text-xs">
                        Reorder at {item.reorder_level}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Revenue + Mechanic Workload Row (for managers) */}
      {isManager && (
        <div className="grid lg:grid-cols-2 gap-6">
          {/* Revenue Summary */}
          <div className="bg-white/5 rounded-xl p-4 sm:p-6 border border-white/10">
            <h2 className="text-lg font-semibold text-white mb-4">Revenue Summary</h2>
            <div className="grid grid-cols-3 gap-2 sm:gap-4">
              <RevenueCard
                title="Today"
                amount={stats?.revenue.today || '0.00'}
                icon="📅"
              />
              <RevenueCard
                title="This Week"
                amount={stats?.revenue.this_week || '0.00'}
                icon="📆"
              />
              <RevenueCard
                title="This Month"
                amount={stats?.revenue.this_month || '0.00'}
                icon="🗓️"
              />
            </div>
            <div className="mt-4 pt-4 border-t border-white/10 flex items-center justify-between">
              <span className="text-gray-400 text-sm">Total Paid Orders</span>
              <span className="text-white font-semibold">
                {stats?.revenue.total_paid_orders || 0}
              </span>
            </div>
          </div>

          {/* Mechanic Workload */}
          <div className="bg-white/5 rounded-xl p-4 sm:p-6 border border-white/10">
            <h2 className="text-lg font-semibold text-white mb-4">Mechanic Workload</h2>
            {stats?.mechanic_workload.length === 0 ? (
              <div className="text-center py-8">
                <div className="text-3xl mb-2">👥</div>
                <p className="text-gray-400">No mechanics assigned yet</p>
              </div>
            ) : (
              <div className="space-y-3">
                {stats?.mechanic_workload.map((mechanic) => (
                  <div
                    key={mechanic.mechanic_id}
                    className="bg-white/5 rounded-lg p-3 border border-white/10"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 sm:gap-3 min-w-0 flex-1">
                        <div className="w-8 h-8 rounded-full bg-amber-500/20 flex items-center justify-center text-amber-400 text-sm font-medium shrink-0">
                          {mechanic.mechanic_name.charAt(0).toUpperCase()}
                        </div>
                        <span className="text-white font-medium text-sm truncate">
                          {mechanic.mechanic_name}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 sm:gap-4 text-sm shrink-0">
                        <div className="text-center">
                          <div className="text-white font-semibold">
                            {mechanic.assigned_count}
                          </div>
                          <div className="text-gray-500 text-[10px] sm:text-xs">Assigned</div>
                        </div>
                        <div className="text-center">
                          <div className="text-amber-400 font-semibold">
                            {mechanic.in_progress_count}
                          </div>
                          <div className="text-gray-500 text-[10px] sm:text-xs">Active</div>
                        </div>
                      </div>
                    </div>
                    {/* Workload bar */}
                    <div className="mt-2 h-1.5 bg-white/10 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-amber-500 to-amber-400 rounded-full transition-all"
                        style={{
                          width: `${Math.min((mechanic.in_progress_count / Math.max(mechanic.assigned_count, 1)) * 100, 100)}%`,
                        }}
                      ></div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Summary Stats (for managers) */}
      {isManager && (
        <div className="grid grid-cols-3 gap-4">
          <StatCard title="Total Customers" value={stats?.total_customers || 0} />
          <StatCard title="Total Vehicles" value={stats?.total_vehicles || 0} />
          <StatCard title="Total Orders" value={stats?.total_repair_orders || 0} />
        </div>
      )}
    </div>
  )
}

// KPI Card Component
function KPICard({
  title,
  value,
  icon,
  color,
  linkTo,
}: {
  title: string
  value: number
  icon: string
  color: 'amber' | 'blue' | 'green' | 'red' | 'gray'
  linkTo?: string
}) {
  const colorClasses = {
    amber: 'from-amber-500/20 to-amber-600/10 border-amber-500/30',
    blue: 'from-blue-500/20 to-blue-600/10 border-blue-500/30',
    green: 'from-green-500/20 to-green-600/10 border-green-500/30',
    red: 'from-red-500/20 to-red-600/10 border-red-500/30',
    gray: 'from-gray-500/20 to-gray-600/10 border-gray-500/30',
  }

  const content = (
    <div
      className={`bg-gradient-to-br ${colorClasses[color]} rounded-xl p-4 sm:p-5 border transition-transform hover:scale-[1.02]`}
    >
      <div className="flex items-center justify-between">
        <span className="text-2xl">{icon}</span>
        {value > 0 && color === 'red' && (
          <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></span>
        )}
      </div>
      <div className="mt-3">
        <div className="text-3xl sm:text-4xl font-bold text-white">{value}</div>
        <div className="text-sm text-gray-400 mt-1">{title}</div>
      </div>
    </div>
  )

  if (linkTo) {
    return (
      <Link to={linkTo} className="block">
        {content}
      </Link>
    )
  }
  return content
}

// Quick Action Button
function QuickActionButton({
  to,
  icon,
  label,
  color,
}: {
  to: string
  icon: string
  label: string
  color: 'amber' | 'blue' | 'cyan' | 'purple'
}) {
  const colorClasses = {
    amber: 'hover:bg-amber-500/20 hover:border-amber-500/50 active:bg-amber-500/30',
    blue: 'hover:bg-blue-500/20 hover:border-blue-500/50 active:bg-blue-500/30',
    cyan: 'hover:bg-cyan-500/20 hover:border-cyan-500/50 active:bg-cyan-500/30',
    purple: 'hover:bg-purple-500/20 hover:border-purple-500/50 active:bg-purple-500/30',
  }

  return (
    <Link
      to={to}
      className={`flex flex-col items-center justify-center p-3 sm:p-4 rounded-lg border border-white/10 bg-white/5 transition-all min-h-[80px] ${colorClasses[color]}`}
    >
      <span className="text-xl sm:text-2xl mb-1 sm:mb-2">{icon}</span>
      <span className="text-xs sm:text-sm text-gray-300 text-center leading-tight">{label}</span>
    </Link>
  )
}

// Stat Card
function StatCard({ title, value }: { title: string; value: number }) {
  return (
    <div className="bg-white/5 rounded-lg p-4 border border-white/10 text-center">
      <div className="text-2xl font-bold text-white">{value}</div>
      <div className="text-sm text-gray-400">{title}</div>
    </div>
  )
}

// Revenue Card
function RevenueCard({
  title,
  amount,
  icon,
}: {
  title: string
  amount: string
  icon: string
}) {
  const numAmount = parseFloat(amount)
  // Shorter format for mobile
  const formattedAmount = numAmount >= 1000 
    ? `$${(numAmount / 1000).toFixed(1)}k`
    : numAmount.toLocaleString('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      })

  return (
    <div className="bg-gradient-to-br from-emerald-500/10 to-emerald-600/5 rounded-lg p-2 sm:p-3 border border-emerald-500/20 text-center">
      <div className="text-base sm:text-lg mb-1">{icon}</div>
      <div className="text-lg sm:text-2xl font-bold text-emerald-400">{formattedAmount}</div>
      <div className="text-[10px] sm:text-xs text-gray-400 mt-1">{title}</div>
    </div>
  )
}
