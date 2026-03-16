import { useEffect, useState, useCallback, useRef } from 'react'
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  DollarSign,
  Phone,
  Plus,
  RefreshCw,
  Send,
  Truck,
  Wrench,
  Zap,
  X,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import api from '../../lib/api'
import { formatUSPhone } from '@/utils/phone'
import { formatMiscCategory, formatSessionType } from '@/lib/mechanicWorkLabels'
import { useAuthStore } from '../../stores/authStore'
import { useTheme } from '../../contexts/ThemeContext'
import { useWebSocket } from '../../hooks/useWebSocket'
import { useNotificationManager } from '../../hooks/useNotificationManager'
import NotificationBanner from '../../components/NotificationBanner'
import AlertsBanner from '../../components/AlertsBanner'
import SectionInfoTooltip from '@/components/SectionInfoTooltip'

interface StatusCount {
  status: string
  count: number
}

interface RecentOrder {
  id: string
  order_number: string
  status: string
  pending_zelle_confirmation?: boolean
  description: string | null
  customer_name: string
  vehicle_info: string
  total_cost: string
  created_at: string
  updated_at: string
  mechanic_name: string | null
  work_started_at: string | null
  hold_reason: string | null
  held_at: string | null
}

interface MechanicWorkload {
  mechanic_id: string
  mechanic_name: string
  assigned_count: number
  in_progress_count: number
}

interface TeamCapacityStatusItem {
  mechanic_id: string
  attendance_active: boolean
  break_active: boolean
  active_session: {
    session_type: string
    misc_category: string | null
    started_at: string | null
  } | null
}

interface TeamCapacityBoardResponse {
  mechanics: TeamCapacityStatusItem[]
}

interface RevenueStats {
  today: string
  this_week: string
  this_month: string
  total_paid_orders: number
  today_parts_margin: string
  this_week_parts_margin: string
  this_month_parts_margin: string
  today_gross_profit: string
  this_week_gross_profit: string
  this_month_gross_profit: string
  today_ppi: string
  this_week_ppi: string
  this_month_ppi: string
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
  on_hold: 'bg-orange-100 text-orange-700',
  pending_review: 'bg-orange-100 text-orange-700',
  completed: 'bg-green-100 text-green-700',
  invoiced: 'bg-purple-100 text-purple-700',
  pending_zelle: 'bg-amber-100 text-amber-800',
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

const getTeamCapacityStatus = (mechanic: TeamCapacityStatusItem | undefined) => {
  if (!mechanic) {
    return {
      label: 'Status unavailable',
      textClass: 'text-gray-500',
      dotClass: 'bg-gray-500',
    }
  }

  if (mechanic.active_session) {
    const sessionLabel = formatSessionType(mechanic.active_session.session_type)
    const detail = mechanic.active_session.session_type === 'misc' && mechanic.active_session.misc_category
      ? `${sessionLabel} (${formatMiscCategory(mechanic.active_session.misc_category)})`
      : sessionLabel
    return {
      label: `Running ${detail}`,
      textClass: 'text-emerald-300',
      dotClass: 'bg-emerald-400',
    }
  }

  if (mechanic.break_active) {
    return {
      label: 'On Break',
      textClass: 'text-amber-300',
      dotClass: 'bg-amber-400',
    }
  }

  if (mechanic.attendance_active) {
    return {
      label: 'Clocked In',
      textClass: 'text-sky-300',
      dotClass: 'bg-sky-400',
    }
  }

  return {
    label: 'Clocked Out',
    textClass: 'text-gray-400',
    dotClass: 'bg-gray-500',
  }
}

function OrderCard({ order, onClick, accentColor }: { order: RecentOrder; onClick: () => void; accentColor: string }) {
  const isOnHold = order.status === 'in_progress' && !!order.hold_reason
  const elapsed = useElapsedTime(
    order.status === 'in_progress' && !isOnHold ? order.work_started_at : null,
  )
  const isPendingZelle = order.status === 'invoiced' && !!order.pending_zelle_confirmation
  const statusKey = isOnHold ? 'on_hold' : isPendingZelle ? 'pending_zelle' : order.status
  const statusLabel = isOnHold ? 'on hold' : isPendingZelle ? 'awaiting zelle' : order.status.replace(/_/g, ' ')

  return (
    <button
      onClick={onClick}
      className="w-full text-left bg-white/5 rounded-lg p-3 2xl:p-2.5 hover:bg-white/10 transition-colors border border-white/5 group"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium text-white text-sm 2xl:text-base">{order.order_number}</span>
            <span
              className={`px-2 py-0.5 rounded-full text-xs 2xl:text-[13px] font-medium whitespace-nowrap ${STATUS_BADGE_COLORS[statusKey] || 'bg-gray-100 text-gray-700'}`}
            >
              {statusLabel}
            </span>
            {elapsed && (
              <span className="text-xs 2xl:text-sm font-mono" style={{ color: accentColor }}>{elapsed}</span>
            )}
          </div>
          <p className="text-gray-400 text-xs 2xl:text-sm truncate mt-1">
            {order.customer_name} &bull; {order.vehicle_info}
          </p>
          {order.mechanic_name && (
            <p className="text-xs 2xl:text-sm mt-0.5" style={{ color: accentColor, opacity: 0.7 }}>&rarr; {order.mechanic_name}</p>
          )}
          {isOnHold && order.hold_reason && (
            <p className="text-xs mt-0.5 text-orange-400 truncate">
              Hold: {order.hold_reason.replace(/_/g, ' ')}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <div className="text-right">
            <div className="text-xs 2xl:text-sm font-medium text-white">
              ${parseFloat(order.total_cost).toFixed(2)}
            </div>
            <div className="text-xs 2xl:text-[13px] text-gray-500">{timeAgo(order.updated_at)}</div>
          </div>
          <ChevronRight className="w-4 h-4 text-gray-500 group-hover:opacity-100 transition-colors" style={{ color: accentColor }} />
        </div>
      </div>
    </button>
  )
}

export default function DashboardHome() {
  const { user } = useAuthStore()
  const { accentColors, fontSize } = useTheme()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Quick order form
  const [showQuickForm, setShowQuickForm] = useState(false)
  const [quickPhone, setQuickPhone] = useState('')
  const [quickTruck, setQuickTruck] = useState('')
  const [quickComplaint, setQuickComplaint] = useState('')
  const [quickSubmitting, setQuickSubmitting] = useState(false)
  const [quickErrors, setQuickErrors] = useState<{ phone?: string; truck?: string; complaint?: string }>({})
  const [quickTouched, setQuickTouched] = useState(false)
  const [isRevenueCollapsed, setIsRevenueCollapsed] = useState(true)
  const [workQueueMaxHeight, setWorkQueueMaxHeight] = useState<number | null>(null)
  const dashboardRootRef = useRef<HTMLDivElement | null>(null)
  const workQueueRef = useRef<HTMLDivElement | null>(null)
  const teamCapacityRef = useRef<HTMLDivElement | null>(null)
  const revenueRef = useRef<HTMLDivElement | null>(null)

  const isMechanic = user?.role === 'mechanic'
  const isManager = user?.role === 'garage_owner' || user?.role === 'garage_admin'
  const isExpandedFont = fontSize === 'comfortable' || fontSize === 'large'
  
  // Notification manager for queued, deduplicated notifications
  const { notify, banners, dismissBanner, clearBanners } = useNotificationManager()
  
  // Connect to WebSocket for real-time updates (replaces polling)
  useWebSocket({ onNotification: notify })
  
  // Dashboard stats query (WebSocket invalidates this on updates)
  const { data: stats, isLoading: loading, error: queryError, isFetching: isRefreshing, dataUpdatedAt } = useQuery<DashboardStats>({
    queryKey: ['dashboard-stats'],
    queryFn: async () => {
      const response = await api.get('/dashboard/stats')
      return response.data
    },
    refetchOnWindowFocus: true, // Refresh when tab becomes visible
  })

  const { data: teamBoard } = useQuery<TeamCapacityBoardResponse>({
    queryKey: ['mechanic-board-team'],
    queryFn: async () => {
      const response = await api.get('/dashboard/mechanics/board')
      return response.data
    },
    enabled: isManager,
    refetchOnWindowFocus: true,
  })
  
  const error = queryError ? 'Failed to load dashboard stats' : null
  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt) : null
  
  const handleManualRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
    queryClient.invalidateQueries({ queryKey: ['mechanic-board-team'] })
  }

  // Format "last updated" time
  const formatLastUpdated = () => {
    if (!lastUpdated) return ''
    const now = new Date()
    const diffSecs = Math.floor((now.getTime() - lastUpdated.getTime()) / 1000)
    if (diffSecs < 10) return 'just now'
    if (diffSecs < 60) return `${diffSecs}s ago`
    const diffMins = Math.floor(diffSecs / 60)
    if (diffMins < 60) return `${diffMins}m ago`
    return lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  const metricValue = (value?: string) => parseFloat(value || '0')
  const teamMembers = stats?.mechanic_workload || []
  const teamStatusByMechanicId = new Map((teamBoard?.mechanics || []).map((mechanic) => [mechanic.mechanic_id, mechanic]))
  const teamAssignedTotal = teamMembers.reduce((sum, m) => sum + m.assigned_count, 0)
  const teamInProgressTotal = teamMembers.reduce((sum, m) => sum + m.in_progress_count, 0)
  const teamQueuedTotal = Math.max(teamAssignedTotal - teamInProgressTotal, 0)
  const teamUtilization = teamAssignedTotal > 0
    ? Math.round((teamInProgressTotal / teamAssignedTotal) * 100)
    : 0
  const teamCapacityHeaderClass = isExpandedFont ? 'text-base 2xl:text-lg' : 'text-sm 2xl:text-base'
  const teamCapacityMetaClass = isExpandedFont ? 'text-sm 2xl:text-base' : 'text-xs 2xl:text-sm'
  const teamCapacityNameClass = isExpandedFont ? 'text-base 2xl:text-lg' : 'text-sm 2xl:text-[15px]'
  const teamCapacityBodyClass = isExpandedFont ? 'text-sm 2xl:text-[15px]' : 'text-xs 2xl:text-sm'
  const teamCapacityGridHeightClass = isExpandedFont ? 'max-h-52 2xl:max-h-48' : 'max-h-48 2xl:max-h-44'
  const workQueueLaneHeightClass = isExpandedFont
    ? 'min-h-[clamp(10.5rem,21vh,12rem)]'
    : 'min-h-[clamp(10rem,20vh,11.75rem)]'
  const workQueueSummary = [
    {
      label: 'Needs Action',
      count: stats?.orders_needing_action?.length || 0,
      className: 'border-red-500/20 bg-red-500/10 text-red-300',
    },
    {
      label: 'On Floor',
      count: stats?.orders_on_floor?.length || 0,
      className: 'border-sky-500/20 bg-sky-500/10 text-sky-300',
    },
    {
      label: 'Ready',
      count: stats?.orders_ready_to_close?.length || 0,
      className: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300',
    },
  ]

  const revenueCards = [
    { label: 'Today Revenue', value: metricValue(stats?.revenue?.today), tone: 'text-emerald-400' },
    { label: 'Today Gross', value: metricValue(stats?.revenue?.today_gross_profit), tone: 'text-amber-300' },
    { label: 'Week Revenue', value: metricValue(stats?.revenue?.this_week), tone: 'text-emerald-400' },
    { label: 'Month Revenue', value: metricValue(stats?.revenue?.this_month), tone: 'text-emerald-400' },
  ]

  useEffect(() => {
    const measureWorkQueueHeight = () => {
      if (typeof window === 'undefined') return
      if (window.innerWidth < 1024) {
        setWorkQueueMaxHeight(null)
        return
      }

      const root = dashboardRootRef.current
      const queue = workQueueRef.current
      if (!root || !queue) return

      const rootStyles = window.getComputedStyle(root)
      const rowGap = parseFloat(rootStyles.rowGap || rootStyles.gap || '0')
      const queueTop = queue.getBoundingClientRect().top
      const teamHeight = teamCapacityRef.current?.getBoundingClientRect().height ?? 0
      const revenueHeight = revenueRef.current?.getBoundingClientRect().height ?? 0
      const gapsBelow = [teamHeight > 0, revenueHeight > 0].filter(Boolean).length
      const viewportPadding = 20
      const availableHeight = window.innerHeight - queueTop - teamHeight - revenueHeight - (rowGap * gapsBelow) - viewportPadding
      const minQueueHeight = isExpandedFont ? 300 : 260
      const nextHeight = Number.isFinite(availableHeight)
        ? Math.max(Math.floor(availableHeight), minQueueHeight)
        : null

      setWorkQueueMaxHeight((current) => (current === nextHeight ? current : nextHeight))
    }

    measureWorkQueueHeight()
    window.addEventListener('resize', measureWorkQueueHeight)
    return () => window.removeEventListener('resize', measureWorkQueueHeight)
  }, [
    banners.length,
    isExpandedFont,
    isManager,
    isRevenueCollapsed,
    showQuickForm,
    stats?.declined_quotes,
    stats?.low_stock_count,
    stats?.orders_needing_action?.length,
    stats?.orders_on_floor?.length,
    stats?.orders_ready_to_close?.length,
    stats?.overdue_approvals,
    teamMembers.length,
  ])

  const validateQuickForm = () => {
    const errors: { phone?: string; complaint?: string } = {}
    // Phone required - strip formatting to check digits
    const phoneDigits = quickPhone.replace(/\D/g, '')
    if (!phoneDigits || phoneDigits.length < 10) {
      errors.phone = 'Valid phone number required'
    }
    // Complaint/description required
    if (!quickComplaint.trim()) {
      errors.complaint = 'Description is required'
    }
    // Truck/vehicle is optional - backend defaults to "Unknown"
    setQuickErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleQuickOrder = async (e: React.FormEvent) => {
    e.preventDefault()
    setQuickTouched(true)
    if (!validateQuickForm()) {
      return
    }
    setQuickSubmitting(true)
    try {
      const response = await api.post('/repair-orders/quick', {
        phone: quickPhone.trim() || null,
        vehicle_description: quickTruck.trim() || null,
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
      setQuickErrors({})
      setQuickTouched(false)
      setShowQuickForm(false)
      handleManualRefresh()
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to create order')
    } finally {
      setQuickSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2" style={{ borderColor: accentColors[500] }}></div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-red-400">{error}</p>
        <button onClick={handleManualRefresh} className="mt-4 hover:opacity-80" style={{ color: accentColors[500] }}>
          Try again
        </button>
      </div>
    )
  }

  return (
    <div
      ref={dashboardRootRef}
      className={`flex flex-col flex-1 min-h-0 2xl:h-[calc(100vh-7.5rem)] 2xl:overflow-hidden ${
        isExpandedFont ? 'gap-4 2xl:gap-3' : 'gap-5 2xl:gap-4'
      }`}
    >
      {/* Header */}
      <div className="flex-shrink-0">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="text-2xl sm:text-3xl 2xl:text-[2.15rem] font-bold text-white">
              {isMechanic ? 'My Workbench' : 'Garage Cockpit'}
            </h1>
            <p className="text-gray-400 mt-1 2xl:text-[1.02rem]">
              {isMechanic
                ? `You have ${stats?.my_in_progress || 0} jobs in progress`
                : `Welcome back, ${user?.first_name || user?.email}`}
            </p>
          </div>

          {/* Manager CTA Buttons */}
          {isManager && (
            <div className="flex flex-wrap items-center gap-3 lg:flex-nowrap lg:justify-end">
              <button
                onClick={() => setShowQuickForm(!showQuickForm)}
                className="flex items-center justify-center gap-2 px-4 py-2.5 font-semibold rounded-xl transition-colors text-white"
                style={{
                  backgroundColor: showQuickForm ? accentColors[600] : accentColors[500],
                  boxShadow: `0 10px 15px -3px ${accentColors[500]}33`,
                }}
              >
                <Zap className="w-4 h-4" />
                <span>Lightning Order</span>
              </button>
              <button
                onClick={() => navigate('/dashboard/repair-orders?new=true')}
                className="flex items-center justify-center gap-2 px-4 py-2.5 bg-white/5 hover:bg-white/10 text-white font-semibold rounded-xl transition-colors border border-white/10"
              >
                <Plus className="w-4 h-4" />
                <span>Full Order</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Real-time notification banners */}
      <NotificationBanner
        banners={banners}
        onDismiss={dismissBanner}
        onDismissAll={clearBanners}
        autoDismissMs={10000}
      />

      {/* Quick Order Form (managers only, collapsible) */}
      {isManager && showQuickForm && (
        <form
          onSubmit={handleQuickOrder}
          className="rounded-xl p-3 sm:p-4 animate-in slide-in-from-top-2 duration-200"
          style={{
            background: `linear-gradient(to right, ${accentColors[500]}1a, ${accentColors[600]}0d)`,
            borderWidth: 1,
            borderColor: `${accentColors[500]}33`,
          }}
        >
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Zap className="w-4 h-4" style={{ color: accentColors[400] }} />
              <span className="text-sm font-semibold" style={{ color: accentColors[400] }}>Lightning Order</span>
              <span className="text-xs text-gray-500">— Walk-in / Phone call</span>
            </div>
            <button
              type="button"
              onClick={() => setShowQuickForm(false)}
              className="p-1 text-gray-500 hover:text-white rounded"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="flex flex-col sm:flex-row sm:items-start gap-2">
            {/* Phone - Required */}
            <div className="flex-shrink-0 sm:w-40">
              <div className="relative">
                <Phone className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                <input
                  type="tel"
                  value={quickPhone}
                  onChange={(e) => {
                    setQuickPhone(formatUSPhone(e.target.value))
                    if (quickTouched) {
                      const digits = e.target.value.replace(/\D/g, '')
                      setQuickErrors((prev) => ({
                        ...prev,
                        phone: digits.length >= 10 ? undefined : 'Valid phone required',
                      }))
                    }
                  }}
                  placeholder="(555) 123-4567"
                  className={`w-full pl-9 pr-3 py-2 bg-white/5 border rounded-lg text-white text-base placeholder-gray-500 focus:outline-none focus:ring-1 ${
                    quickTouched && quickErrors.phone
                      ? 'border-red-500 focus:border-red-500 focus:ring-red-500/30'
                      : 'border-white/10'
                  }`}
                  style={!(quickTouched && quickErrors.phone) ? {
                    ['--tw-ring-color' as string]: `${accentColors[500]}4d`,
                  } : undefined}
                />
              </div>
              {quickTouched && quickErrors.phone && (
                <p className="mt-1 text-xs text-red-400 flex items-center gap-1">
                  <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                  </svg>
                  {quickErrors.phone}
                </p>
              )}
            </div>
            {/* Description - Required */}
            <div className="flex-1">
              <input
                type="text"
                value={quickComplaint}
                onChange={(e) => {
                  setQuickComplaint(e.target.value)
                  if (quickTouched) {
                    setQuickErrors((prev) => ({
                      ...prev,
                      complaint: e.target.value.trim() ? undefined : 'Description required',
                    }))
                  }
                }}
                placeholder="Issue (e.g. engine overheating) *"
                className={`w-full px-3 py-2 bg-white/5 border rounded-lg text-white text-base placeholder-gray-500 focus:outline-none focus:ring-1 ${
                  quickTouched && quickErrors.complaint
                    ? 'border-red-500 focus:border-red-500 focus:ring-red-500/30'
                    : 'border-white/10'
                }`}
              />
              {quickTouched && quickErrors.complaint && (
                <p className="mt-1 text-xs text-red-400 flex items-center gap-1">
                  <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                  </svg>
                  {quickErrors.complaint}
                </p>
              )}
            </div>
            {/* Truck - Optional */}
            <div className="flex-shrink-0 sm:w-48">
              <div className="relative">
                <Truck className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                <input
                  type="text"
                  value={quickTruck}
                  onChange={(e) => setQuickTruck(e.target.value)}
                  placeholder="Truck (optional)"
                  className="w-full pl-9 pr-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-base placeholder-gray-500 focus:outline-none focus:ring-1"
                />
              </div>
            </div>
            <button
              type="submit"
              disabled={quickSubmitting}
              className="px-4 py-2 h-[38px] disabled:opacity-50 text-white font-semibold rounded-lg flex items-center gap-2 transition-colors shrink-0 self-start"
              style={{ backgroundColor: accentColors[500] }}
            >
              {quickSubmitting ? (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
              ) : (
                <Send className="w-4 h-4" />
              )}
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

      {/* Work Queue */}
      <div
        ref={workQueueRef}
        className="flex flex-col gap-2.5 2xl:gap-2 min-h-0 flex-1"
        style={workQueueMaxHeight ? { maxHeight: `${workQueueMaxHeight}px` } : undefined}
      >
        <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden flex flex-col min-h-0 h-full">
          <div className="flex flex-col gap-3 px-3.5 py-3 2xl:px-3 2xl:py-2.5 border-b border-white/10 flex-shrink-0 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-center gap-2">
              <div className="inline-flex items-center gap-2 text-sm 2xl:text-base font-semibold text-gray-300 uppercase tracking-[0.14em]">
                <span>Work Queue</span>
              </div>
              <SectionInfoTooltip text="Operational swimlanes showing where repair orders need immediate attention, are actively being worked, or are ready for final closeout." />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {workQueueSummary.map((item) => (
                <span
                  key={item.label}
                  className={`inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs 2xl:text-sm font-medium ${item.className}`}
                >
                  <span className="text-white">{item.count}</span>
                  <span>{item.label}</span>
                </span>
              ))}
              <button
                onClick={handleManualRefresh}
                disabled={isRefreshing}
                className="flex items-center gap-2 px-2.5 py-1 text-xs 2xl:text-sm text-gray-400 hover:text-white bg-white/5 hover:bg-white/10 rounded-md transition-colors"
                title="Refresh dashboard"
              >
                <RefreshCw className={`w-3 h-3 ${isRefreshing ? 'animate-spin' : ''}`} />
                <span>{formatLastUpdated() || 'Refresh'}</span>
                <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 2xl:gap-2.5 p-3 2xl:p-2.5 flex-1 min-h-0">
              {/* Lane 1: Needs Action */}
              <div className={`bg-white/[0.03] rounded-xl border border-white/10 overflow-hidden flex flex-col ${workQueueLaneHeightClass}`}>
                <div className="flex items-center justify-between px-3.5 py-2.5 2xl:py-2 border-b border-white/10 flex-shrink-0">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-red-400" />
                    <h3 className="text-sm 2xl:text-base font-semibold text-white">Needs Action</h3>
                    <SectionInfoTooltip text="Orders blocked by approvals, missing info, or other manager actions that should be handled first." />
                  </div>
                  <span className="text-xs 2xl:text-sm font-medium text-red-400 bg-red-500/10 px-2 py-0.5 rounded-full">
                    {stats?.orders_needing_action?.length || 0}
                  </span>
                </div>
                <div className="p-2.5 space-y-2 2xl:space-y-1.5 overflow-y-auto flex-1">
                  {!stats?.orders_needing_action?.length ? (
                    <p className="text-gray-500 text-sm 2xl:text-base text-center py-6">All clear</p>
                  ) : (
                    stats.orders_needing_action.map((order) => (
                      <OrderCard
                        key={order.id}
                        order={order}
                        accentColor={accentColors[400]}
                        onClick={() => navigate(`/dashboard/repair-orders?selected=${order.id}`)}
                      />
                    ))
                  )}
                </div>
              </div>

              {/* Lane 2: On the Floor */}
              <div className={`bg-white/[0.03] rounded-xl border border-white/10 overflow-hidden flex flex-col ${workQueueLaneHeightClass}`}>
                <div className="flex items-center justify-between px-3.5 py-2.5 2xl:py-2 border-b border-white/10 flex-shrink-0">
                  <div className="flex items-center gap-2">
                    <Wrench className="w-4 h-4" style={{ color: accentColors[400] }} />
                    <h3 className="text-sm 2xl:text-base font-semibold text-white">On the Floor</h3>
                    <SectionInfoTooltip text="Orders currently in production with mechanics assigned or actively working." />
                  </div>
                  <span className="text-xs 2xl:text-sm font-medium px-2 py-0.5 rounded-full" style={{ color: accentColors[400], backgroundColor: `${accentColors[500]}1a` }}>
                    {stats?.orders_on_floor?.length || 0}
                  </span>
                </div>
                <div className="p-2.5 space-y-2 2xl:space-y-1.5 overflow-y-auto flex-1">
                  {!stats?.orders_on_floor?.length ? (
                    <p className="text-gray-500 text-sm 2xl:text-base text-center py-6">No active work</p>
                  ) : (
                    stats.orders_on_floor.map((order) => (
                      <OrderCard
                        key={order.id}
                        order={order}
                        accentColor={accentColors[400]}
                        onClick={() => navigate(`/dashboard/repair-orders?selected=${order.id}`)}
                      />
                    ))
                  )}
                </div>
              </div>

              {/* Lane 3: Ready to Close */}
              <div className={`bg-white/[0.03] rounded-xl border border-white/10 overflow-hidden flex flex-col ${workQueueLaneHeightClass}`}>
                <div className="flex items-center justify-between px-3.5 py-2.5 2xl:py-2 border-b border-white/10 flex-shrink-0">
                  <div className="flex items-center gap-2">
                    <DollarSign className="w-4 h-4 text-emerald-400" />
                    <h3 className="text-sm 2xl:text-base font-semibold text-white">Ready to Close</h3>
                    <SectionInfoTooltip text="Orders that are operationally complete and ready for invoicing, payment, and closeout." />
                  </div>
                  <span className="text-xs 2xl:text-sm font-medium text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full">
                    {stats?.orders_ready_to_close?.length || 0}
                  </span>
                </div>
                <div className="p-2.5 space-y-2 2xl:space-y-1.5 overflow-y-auto flex-1">
                  {!stats?.orders_ready_to_close?.length ? (
                    <p className="text-gray-500 text-sm 2xl:text-base text-center py-6">Nothing pending</p>
                  ) : (
                    stats.orders_ready_to_close.map((order) => (
                      <OrderCard
                        key={order.id}
                        order={order}
                        accentColor={accentColors[400]}
                        onClick={() => navigate(`/dashboard/repair-orders?selected=${order.id}`)}
                      />
                    ))
                  )}
                </div>
              </div>
            </div>
        </div>
      </div>

      {isManager && (
        <div ref={teamCapacityRef} className="flex-shrink-0 bg-white/5 rounded-xl p-3.5 2xl:p-3 border border-white/10">
          <div className="flex items-center justify-between gap-3 mb-2.5">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => navigate('/dashboard/mechanics')}
                className={`${teamCapacityHeaderClass} font-semibold text-gray-300 uppercase tracking-[0.14em] hover:text-white transition-colors`}
              >
                Team Capacity
              </button>
              <SectionInfoTooltip text="Mechanic staffing capacity snapshot with active vs queued work, per-mechanic load, and click-through to detailed timer boards." />
            </div>
            <div className={`${teamCapacityMetaClass} text-gray-400`}>
              {teamAssignedTotal} assigned
            </div>
          </div>

          {!teamMembers.length ? (
            <span className={`${teamCapacityMetaClass} text-gray-500`}>No mechanics</span>
          ) : (
            <div className="space-y-2.5">
              <div className="rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-[11px] 2xl:text-xs uppercase tracking-[0.18em] text-gray-500">
                      Team utilization
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm 2xl:text-[15px] text-gray-300">
                      <span>
                        <span className="font-semibold text-white">{teamInProgressTotal}</span> active now
                      </span>
                      <span>
                        <span className="font-semibold text-white">{teamQueuedTotal}</span> queued next
                      </span>
                    </div>
                  </div>
                  <span className="shrink-0 text-base 2xl:text-lg font-semibold text-white">{teamUtilization}%</span>
                </div>
                <div className="mt-2 h-2.5 rounded-full bg-white/10 overflow-hidden">
                  <div
                    className="h-2.5 rounded-full"
                    style={{ width: `${teamUtilization}%`, backgroundColor: accentColors[500] }}
                  />
                </div>
              </div>

              <div className={`grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-2.5 overflow-y-auto pr-1 ${teamCapacityGridHeightClass}`}>
                {teamMembers.slice(0, 8).map((m) => {
                  const loadPct = m.assigned_count > 0
                    ? Math.round((m.in_progress_count / m.assigned_count) * 100)
                    : 0
                  const queued = Math.max(m.assigned_count - m.in_progress_count, 0)
                  const status = getTeamCapacityStatus(teamStatusByMechanicId.get(m.mechanic_id))
                  const loadLabel = m.assigned_count > 0 ? `${loadPct}% loaded` : 'No jobs queued'
                  return (
                    <button
                      type="button"
                      key={m.mechanic_id}
                      onClick={() => navigate(`/dashboard/mechanics/${m.mechanic_id}`)}
                      className="rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5 text-left hover:bg-white/[0.06] transition-colors"
                      title={`${m.mechanic_name}: ${status.label} · ${m.in_progress_count} active / ${m.assigned_count} assigned`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <div
                            className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold shrink-0"
                            style={{ backgroundColor: `${accentColors[500]}33`, color: accentColors[400] }}
                          >
                            {m.mechanic_name.charAt(0).toUpperCase()}
                          </div>
                          <span className={`${teamCapacityNameClass} font-semibold text-white truncate`}>{m.mechanic_name}</span>
                        </div>
                        <span className="shrink-0 rounded-full border border-white/10 bg-white/[0.05] px-2 py-1 text-[11px] 2xl:text-xs font-medium text-gray-300">
                          {loadLabel}
                        </span>
                      </div>
                      <div className={`mt-2 ${teamCapacityBodyClass} flex items-center gap-2 ${status.textClass}`}>
                        <span className={`w-2 h-2 rounded-full shrink-0 ${status.dotClass}`} />
                        <span className="truncate">{status.label}</span>
                      </div>
                      <div className={`mt-1.5 ${teamCapacityBodyClass} text-gray-300`}>
                        <span className="font-semibold text-white">{m.in_progress_count}</span> active
                        {' · '}
                        <span className="font-semibold text-white">{queued}</span> queued
                      </div>
                      <div className="mt-2 h-2 rounded-full bg-white/10 overflow-hidden">
                        <div
                          className="h-2 rounded-full"
                          style={{ width: `${loadPct}%`, backgroundColor: accentColors[500] }}
                        />
                      </div>
                    </button>
                  )
                })}
                {teamMembers.length > 8 && (
                  <div className={`${teamCapacityMetaClass} text-gray-500 px-1 col-span-full`}>
                    +{teamMembers.length - 8} more mechanics
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {isManager && (
        <div ref={revenueRef} className="flex-shrink-0 bg-white/5 rounded-xl p-3 2xl:p-2.5 border border-white/10">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between mb-2.5">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setIsRevenueCollapsed((current) => !current)}
                aria-expanded={!isRevenueCollapsed}
                className="inline-flex items-center gap-2 text-sm 2xl:text-base font-semibold text-gray-400 uppercase tracking-[0.14em] hover:text-white transition-colors"
              >
                {isRevenueCollapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
                <span>Revenue KPIs</span>
              </button>
              <SectionInfoTooltip text="Minimal finance snapshot for the current garage day, week, and month." />
            </div>
            <span className="text-xs 2xl:text-sm text-gray-400 bg-white/5 border border-white/10 rounded-full px-2.5 py-1">
              {stats?.revenue?.total_paid_orders || 0} paid orders
            </span>
          </div>
          {!isRevenueCollapsed && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {revenueCards.map((card) => (
                <div key={card.label} className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5">
                  <div className="text-[11px] 2xl:text-xs uppercase tracking-[0.16em] text-gray-500">{card.label}</div>
                  <div className={`mt-1.5 text-base 2xl:text-lg font-semibold ${card.tone}`}>
                    ${card.value.toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
