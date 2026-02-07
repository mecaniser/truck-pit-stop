import { useEffect, useState, useCallback } from 'react'
import {
  AlertTriangle,
  ChevronRight,
  DollarSign,
  Phone,
  Send,
  Truck,
  Wrench,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import api from '../../lib/api'
import { useAuthStore } from '../../stores/authStore'
import AlertsBanner from '../../components/AlertsBanner'

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
  mechanic_name: string | null
  work_started_at: string | null
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
  recent_orders: RecentOrder[]
  my_assigned_orders: number
  my_in_progress: number
  revenue: RevenueStats
  mechanic_workload: MechanicWorkload[]
  overdue_approvals: number
  declined_quotes: number
  orders_needing_action: RecentOrder[]
  orders_on_floor: RecentOrder[]
  orders_ready_to_close: RecentOrder[]
}

const STATUS_BADGE_COLORS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  quoted: 'bg-blue-100 text-blue-700',
  declined: 'bg-red-100 text-red-700',
  approved: 'bg-cyan-100 text-cyan-700',
  assigned: 'bg-cyan-100 text-cyan-700',
  acknowledged: 'bg-cyan-100 text-cyan-700',
  in_progress: 'bg-amber-100 text-amber-700',
  pending_review: 'bg-orange-100 text-orange-700',
  completed: 'bg-green-100 text-green-700',
  invoiced: 'bg-purple-100 text-purple-700',
  paid: 'bg-emerald-100 text-emerald-700',
  cancelled: 'bg-red-100 text-red-700',
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

function useElapsedTime(startedAt: string | null) {
  const [elapsed, setElapsed] = useState('')
  const calc = useCallback(() => {
    if (!startedAt) return ''
    const secs = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000)
    if (secs < 0) return ''
    const h = Math.floor(secs / 3600)
    const m = Math.floor((secs % 3600) / 60)
    return h > 0 ? `${h}h ${m}m` : `${m}m`
  }, [startedAt])

  useEffect(() => {
    if (!startedAt) return
    setElapsed(calc())
    const id = setInterval(() => setElapsed(calc()), 60000)
    return () => clearInterval(id)
  }, [startedAt, calc])

  return elapsed
}

function OrderCard({ order, onClick }: { order: RecentOrder; onClick: () => void }) {
  const elapsed = useElapsedTime(
    order.status === 'in_progress' ? order.work_started_at : null,
  )

  return (
    <button
      onClick={onClick}
      className="w-full text-left bg-white/5 rounded-lg p-3 hover:bg-white/10 transition-colors border border-white/5 group"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium text-white text-sm">{order.order_number}</span>
            <span
              className={`px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap ${STATUS_BADGE_COLORS[order.status] || 'bg-gray-100 text-gray-700'}`}
            >
              {order.status.replace(/_/g, ' ')}
            </span>
            {elapsed && (
              <span className="text-xs text-amber-400 font-mono">{elapsed}</span>
            )}
          </div>
          <p className="text-gray-400 text-xs truncate mt-1">
            {order.customer_name} &bull; {order.vehicle_info}
          </p>
          {order.mechanic_name && (
            <p className="text-amber-400/70 text-xs mt-0.5">&rarr; {order.mechanic_name}</p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <div className="text-right">
            <div className="text-xs font-medium text-white">
              ${parseFloat(order.total_cost).toFixed(2)}
            </div>
            <div className="text-xs text-gray-500">{timeAgo(order.updated_at)}</div>
          </div>
          <ChevronRight className="w-4 h-4 text-gray-500 group-hover:text-amber-400 transition-colors" />
        </div>
      </div>
    </button>
  )
}

export default function DashboardHome() {
  const { user } = useAuthStore()
  const navigate = useNavigate()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Quick order form
  const [quickPhone, setQuickPhone] = useState('')
  const [quickTruck, setQuickTruck] = useState('')
  const [quickComplaint, setQuickComplaint] = useState('')
  const [quickSubmitting, setQuickSubmitting] = useState(false)

  const isMechanic = user?.role === 'mechanic'
  const isManager = user?.role === 'garage_owner' || user?.role === 'garage_admin'

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

  const handleQuickOrder = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!quickTruck.trim()) {
      toast.error('Truck description is required')
      return
    }
    setQuickSubmitting(true)
    try {
      const response = await api.post('/repair-orders/quick', {
        phone: quickPhone.trim() || null,
        vehicle_description: quickTruck.trim(),
        complaint: quickComplaint.trim() || null,
      })
      const order = response.data
      toast.success(
        <span>
          Order <b>{order.order_number}</b> created
        </span>,
      )
      setQuickPhone('')
      setQuickTruck('')
      setQuickComplaint('')
      fetchStats()
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to create order')
    } finally {
      setQuickSubmitting(false)
    }
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
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white">
          {isMechanic ? 'My Workbench' : 'Garage Cockpit'}
        </h1>
        <p className="text-gray-400 mt-1">
          {isMechanic
            ? `You have ${stats?.my_in_progress || 0} jobs in progress`
            : `Welcome back, ${user?.first_name || user?.email}`}
        </p>
      </div>

      {/* Quick Order Bar (managers only) */}
      {isManager && (
        <form
          onSubmit={handleQuickOrder}
          className="bg-gradient-to-r from-amber-500/10 to-amber-600/5 border border-amber-500/20 rounded-xl p-3 sm:p-4"
        >
          <div className="flex items-center gap-2 mb-3">
            <Wrench className="w-4 h-4 text-amber-400" />
            <span className="text-sm font-semibold text-amber-400">Quick Order</span>
          </div>
          <div className="flex flex-col sm:flex-row gap-2">
            <div className="relative flex-shrink-0 sm:w-40">
              <Phone className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
              <input
                type="tel"
                value={quickPhone}
                onChange={(e) => setQuickPhone(e.target.value)}
                placeholder="Phone"
                className="w-full pl-9 pr-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-sm placeholder-gray-500 focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/30"
              />
            </div>
            <div className="relative flex-shrink-0 sm:w-52">
              <Truck className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
              <input
                type="text"
                value={quickTruck}
                onChange={(e) => setQuickTruck(e.target.value)}
                placeholder="Truck (e.g. 2019 Peterbilt 579)"
                required
                className="w-full pl-9 pr-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-sm placeholder-gray-500 focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/30"
              />
            </div>
            <div className="relative flex-1">
              <input
                type="text"
                value={quickComplaint}
                onChange={(e) => setQuickComplaint(e.target.value)}
                placeholder="Complaint (e.g. engine overheating)"
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-sm placeholder-gray-500 focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/30"
              />
            </div>
            <button
              type="submit"
              disabled={quickSubmitting}
              className="px-4 py-2 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white font-semibold rounded-lg flex items-center gap-2 transition-colors shrink-0"
            >
              <Send className="w-4 h-4" />
              <span className="hidden sm:inline">Create</span>
            </button>
          </div>
        </form>
      )}

      {/* Alerts Banner (managers only, conditional) */}
      {isManager && ((stats?.low_stock_count ?? 0) > 0 || (stats?.overdue_approvals ?? 0) > 0 || (stats?.declined_quotes ?? 0) > 0) && (
        <AlertsBanner
          lowStockCount={stats?.low_stock_count || 0}
          overdueApprovals={stats?.overdue_approvals || 0}
          declinedQuotes={stats?.declined_quotes || 0}
        />
      )}

      {/* Work Queue Swimlanes */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Lane 1: Needs Action */}
        <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-red-400" />
              <h3 className="text-sm font-semibold text-white">Needs Action</h3>
            </div>
            <span className="text-xs font-medium text-red-400 bg-red-500/10 px-2 py-0.5 rounded-full">
              {stats?.orders_needing_action?.length || 0}
            </span>
          </div>
          <div className="p-3 space-y-2 max-h-[400px] overflow-y-auto">
            {!stats?.orders_needing_action?.length ? (
              <p className="text-gray-500 text-sm text-center py-6">All clear</p>
            ) : (
              stats.orders_needing_action.map((order) => (
                <OrderCard
                  key={order.id}
                  order={order}
                  onClick={() => navigate(`/dashboard/repair-orders?selected=${order.id}`)}
                />
              ))
            )}
          </div>
        </div>

        {/* Lane 2: On the Floor */}
        <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
            <div className="flex items-center gap-2">
              <Wrench className="w-4 h-4 text-amber-400" />
              <h3 className="text-sm font-semibold text-white">On the Floor</h3>
            </div>
            <span className="text-xs font-medium text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-full">
              {stats?.orders_on_floor?.length || 0}
            </span>
          </div>
          <div className="p-3 space-y-2 max-h-[400px] overflow-y-auto">
            {!stats?.orders_on_floor?.length ? (
              <p className="text-gray-500 text-sm text-center py-6">No active work</p>
            ) : (
              stats.orders_on_floor.map((order) => (
                <OrderCard
                  key={order.id}
                  order={order}
                  onClick={() => navigate(`/dashboard/repair-orders?selected=${order.id}`)}
                />
              ))
            )}
          </div>
        </div>

        {/* Lane 3: Ready to Close */}
        <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
            <div className="flex items-center gap-2">
              <DollarSign className="w-4 h-4 text-emerald-400" />
              <h3 className="text-sm font-semibold text-white">Ready to Close</h3>
            </div>
            <span className="text-xs font-medium text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full">
              {stats?.orders_ready_to_close?.length || 0}
            </span>
          </div>
          <div className="p-3 space-y-2 max-h-[400px] overflow-y-auto">
            {!stats?.orders_ready_to_close?.length ? (
              <p className="text-gray-500 text-sm text-center py-6">Nothing pending</p>
            ) : (
              stats.orders_ready_to_close.map((order) => (
                <OrderCard
                  key={order.id}
                  order={order}
                  onClick={() => navigate(`/dashboard/repair-orders?selected=${order.id}`)}
                />
              ))
            )}
          </div>
        </div>
      </div>

      {/* Bottom Bar: Revenue + Team Workload (managers only) */}
      {isManager && (
        <div className="flex flex-col sm:flex-row gap-4">
          {/* Revenue - Compact row */}
          <div className="flex-1 bg-white/5 rounded-xl p-4 border border-white/10">
            <div className="flex items-center gap-6 flex-wrap">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Revenue</h3>
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-gray-500">Today</span>
                <span className="text-sm font-semibold text-emerald-400">
                  ${parseFloat(stats?.revenue?.today || '0').toLocaleString()}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-gray-500">Week</span>
                <span className="text-sm font-semibold text-emerald-400">
                  ${parseFloat(stats?.revenue?.this_week || '0').toLocaleString()}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-gray-500">Month</span>
                <span className="text-sm font-semibold text-emerald-400">
                  ${parseFloat(stats?.revenue?.this_month || '0').toLocaleString()}
                </span>
              </div>
            </div>
          </div>

          {/* Team Workload - Compact */}
          <div className="bg-white/5 rounded-xl p-4 border border-white/10">
            <div className="flex items-center gap-3">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Team</h3>
              {!stats?.mechanic_workload?.length ? (
                <span className="text-xs text-gray-500">No mechanics</span>
              ) : (
                <div className="flex items-center gap-2 flex-wrap">
                  {stats.mechanic_workload.slice(0, 6).map((m) => (
                    <div
                      key={m.mechanic_id}
                      className="flex items-center gap-1.5 px-2 py-1 bg-white/5 rounded-lg border border-white/10"
                      title={`${m.mechanic_name}: ${m.in_progress_count} active / ${m.assigned_count} assigned`}
                    >
                      <div className="w-5 h-5 rounded-full bg-amber-500/20 flex items-center justify-center text-amber-400 text-xs font-medium">
                        {m.mechanic_name.charAt(0).toUpperCase()}
                      </div>
                      <span className="text-xs text-white">{m.mechanic_name.split(' ')[0]}</span>
                      <span className="text-xs text-amber-400 font-medium">
                        {m.in_progress_count}/{m.assigned_count}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
