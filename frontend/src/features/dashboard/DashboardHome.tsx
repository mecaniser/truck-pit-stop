import { useEffect, useState, useCallback, useRef } from 'react'
import { Spinner } from '@/components/ui'
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  DollarSign,
  History,
  LayoutGrid,
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
import { isAxiosError } from 'axios'
import toast from 'react-hot-toast'
import api from '../../lib/api'
import { formatUSPhone } from '@/utils/phone'
import { useAuthStore } from '../../stores/authStore'
import { useTheme } from '../../contexts/ThemeContext'
import { useWebSocket } from '../../hooks/useWebSocket'
import { useNotificationManager } from '../../hooks/useNotificationManager'
import NotificationBanner from '../../components/NotificationBanner'
import AlertsBanner from '../../components/AlertsBanner'
import SectionInfoTooltip from '@/components/SectionInfoTooltip'
import SuggestingInput from '@/components/SuggestingInput'
import RecentActivityFeed from './RecentActivityFeed'

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
  quote_sent: boolean | null
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

// Ticks every minute so alert priority scores stay current without user interaction
function useNow(): number {
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60000)
    return () => clearInterval(id)
  }, [])
  return now
}

type OrderAlertLevel = 'red' | 'amber' | 'none'
interface OrderAlert {
  level: OrderAlertLevel
  /** Higher number = more urgent. Used to rank animation slots globally. */
  priority: number
  /** When false the card shows a colored state but never consumes an animation slot. */
  canAnimate: boolean
}

function getOrderAlert(order: RecentOrder, nowMs: number): OrderAlert {
  const isOnHold = order.status === 'in_progress' && !!order.hold_reason
  const statusMins = Math.floor((nowMs - new Date(order.updated_at).getTime()) / 60000)
  const holdMins = isOnHold && order.held_at
    ? Math.floor((nowMs - new Date(order.held_at).getTime()) / 60000)
    : 0
  // Priority 1 — critical: on hold > 2 h
  if (isOnHold && holdMins >= 120)
    return { level: 'red', priority: 10000 + holdMins, canAnimate: true }
  // Priority 2 — high: pending review blocks invoice/payment — immediate, no threshold
  if (order.status === 'pending_review')
    return { level: 'amber', priority: 2500, canAnimate: true }
  // Priority 3 — high: approved, no technician > 30 min
  if (order.status === 'approved' && !order.mechanic_name && statusMins >= 30)
    return { level: 'amber', priority: 2000 + statusMins, canAnimate: true }
  // Priority 3 — medium: assigned, no acknowledgment > 15 min
  if (order.status === 'assigned' && statusMins >= 15)
    return { level: 'amber', priority: 1000 + statusMins, canAnimate: true }
  // Priority 4 — low: quoted AND sent, no customer reply > 4 h — color only, never animated
  if (order.status === 'quoted' && order.quote_sent === true && statusMins >= 240)
    return { level: 'amber', priority: 0, canAnimate: false }
  return { level: 'none', priority: -1, canAnimate: false }
}

const getTeamCapacityStatus = (mechanic: TeamCapacityStatusItem | undefined) => {
  if (!mechanic) {
    return {
      label: 'Status unavailable',
      badgeLabel: 'Unknown',
      badgeClass: 'border-gray-500/20 bg-gray-500/10 text-gray-300',
    }
  }

  if (mechanic.active_session) {
    return {
      label: 'Working on assigned jobs',
      badgeLabel: 'Working',
      badgeClass: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-200',
    }
  }

  if (mechanic.break_active) {
    return {
      label: 'On Break',
      badgeLabel: 'On Break',
      badgeClass: 'border-amber-500/20 bg-amber-500/10 text-amber-200',
    }
  }

  if (mechanic.attendance_active) {
    return {
      label: 'Clocked in and ready',
      badgeLabel: 'Ready',
      badgeClass: 'border-sky-500/20 bg-sky-500/10 text-sky-200',
    }
  }

  return {
    label: 'Clocked Out',
    badgeLabel: 'Offline',
    badgeClass: 'border-gray-500/20 bg-gray-500/10 text-gray-300',
  }
}

const getTeamCapacitySortPriority = (mechanic: TeamCapacityStatusItem | undefined) => {
  if (mechanic?.active_session) return 0
  if (mechanic?.attendance_active && !mechanic.break_active) return 1
  if (mechanic?.break_active) return 2
  if (mechanic?.attendance_active) return 3
  return 4
}

const STATUS_BADGE: Record<string, { label: string; className: string }> = {
  draft:          { label: 'Draft',         className: 'bg-gray-500/20 text-gray-300' },
  quoted:         { label: 'Quoted',        className: 'bg-blue-500/20 text-blue-300' },
  declined:       { label: 'Declined',      className: 'bg-red-500/20 text-red-300' },
  pending_review: { label: 'Needs Review',  className: 'bg-amber-500/20 text-amber-300' },
  completed:      { label: 'Invoice Customer', className: 'bg-teal-500/20 text-teal-300' },
  invoiced:       { label: 'Payment Due',   className: 'bg-yellow-500/20 text-yellow-300' },
  approved:       { label: 'Approved',      className: 'bg-green-500/20 text-green-300' },
  assigned:       { label: 'Assigned',      className: 'bg-amber-500/20 text-amber-300' },
  acknowledged:   { label: "Ack'd",         className: 'bg-sky-500/20 text-sky-300' },
  in_progress:    { label: 'In Progress',   className: 'bg-green-500/20 text-green-300' },
}

function OrderCard({
  order,
  onClick,
  accentColor,
  alert,
  animated,
}: {
  order: RecentOrder
  onClick: () => void
  accentColor: string
  alert: OrderAlert
  animated: boolean
}) {
  const isOnHold = order.status === 'in_progress' && !!order.hold_reason
  const elapsed = useElapsedTime(
    order.status === 'in_progress' && !isOnHold ? order.work_started_at : null,
  )
  const holdElapsed = useElapsedTime(isOnHold ? order.held_at : null)

  const badge = isOnHold
    ? { label: 'On Hold', className: 'bg-orange-500/20 text-orange-300' }
    : order.pending_zelle_confirmation
    ? { label: 'Zelle Review', className: 'bg-amber-500/20 text-amber-300' }
    : STATUS_BADGE[order.status] ?? { label: order.status.replace(/_/g, ' '), className: 'bg-gray-500/20 text-gray-300' }

  // Contextual sub-note shown below the customer/vehicle line
  const contextNote: { text: string; color: string } | null = (() => {
    if (order.pending_zelle_confirmation)
      return { text: 'Customer marked payment sent. Confirm receipt before closing.', color: 'text-amber-400' }
    if (order.status === 'quoted' || order.status === 'draft') {
      if (!order.quote_sent)
        return { text: 'Quote ready — not sent to customer yet', color: 'text-gray-400' }
      if (alert.level === 'amber')
        return { text: 'No response · follow up needed', color: 'text-amber-400' }
      return { text: 'Awaiting customer response', color: 'text-blue-400' }
    }
    if (order.status === 'pending_review')
      return { text: 'Pending review · approve to send invoice', color: 'text-amber-400' }
    if (isOnHold) return null
    if (order.status === 'approved' && !order.mechanic_name)
      return alert.level === 'amber'
        ? { text: 'Approved · no technician assigned yet', color: 'text-amber-400' }
        : { text: 'Approved · needs technician assignment', color: 'text-amber-400' }
    if ((order.status === 'approved' || order.status === 'assigned') && order.mechanic_name)
      return alert.level === 'amber'
        ? { text: `Assigned to ${order.mechanic_name} · not picked up yet`, color: 'text-amber-400' }
        : { text: `Assigned to ${order.mechanic_name}`, color: 'text-sky-400' }
    if (order.status === 'acknowledged' && order.mechanic_name)
      return { text: `${order.mechanic_name} acknowledged`, color: 'text-sky-400' }
    if (order.status === 'in_progress' && order.mechanic_name)
      return { text: `${order.mechanic_name} is working on this`, color: 'text-green-400' }
    return null
  })()

  return (
    <button
      onClick={onClick}
      className={`w-full text-left rounded-lg p-3 2xl:p-2.5 hover:bg-white/10 transition-colors border group ${
        alert.level === 'red'
          ? `bg-red-500/5 border-red-500/30${animated ? ' order-alert-red' : ''}`
          : alert.level === 'amber'
          ? `bg-amber-500/5 border-amber-500/30${animated ? ' order-alert-amber' : ''}`
          : 'bg-white/5 border-white/5'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-white text-sm 2xl:text-base">{order.order_number}</span>
            <span className={`text-[10px] 2xl:text-xs font-semibold px-1.5 py-0.5 rounded whitespace-nowrap ${badge.className}`}>{badge.label}</span>
            {elapsed && (
              <span className="text-xs 2xl:text-sm font-mono" style={{ color: accentColor }}>{elapsed}</span>
            )}
            {holdElapsed && (
              <span className="text-xs 2xl:text-sm font-mono text-orange-400">{holdElapsed} on hold</span>
            )}
          </div>
          <p className="text-gray-400 text-xs 2xl:text-sm truncate mt-1">
            {order.customer_name} &bull; {order.vehicle_info}
          </p>
          {isOnHold && order.hold_reason && (
            <p className="text-xs mt-0.5 text-orange-400 truncate">
              Hold: {order.hold_reason.replace(/_/g, ' ')}
            </p>
          )}
          {contextNote && (
            <p className={`text-xs mt-0.5 truncate ${contextNote.color}`}>
              {contextNote.text}
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
  const [openStatusPanel, setOpenStatusPanel] = useState<'team' | 'revenue' | null>(null)
  const [activeMobileLane, setActiveMobileLane] = useState<0 | 1 | 2>(0)
  const teamCapacityTouchStartY = useRef<number | null>(null)
  const teamCapacityDidSwipe = useRef(false)
  const [queueView, setQueueView] = useState<'queue' | 'activity'>('queue')
  const [activityCount, setActivityCount] = useState(0)
  const [isDesktop, setIsDesktop] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia('(min-width: 1024px)').matches : true
  )
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 1024px)')
    const handler = (e: MediaQueryListEvent) => setIsDesktop(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])
  const handleTeamCapacityTouchStart = (event: React.TouchEvent<HTMLElement>) => {
    if (isDesktop || !event.touches[0]) return
    teamCapacityTouchStartY.current = event.touches[0].clientY
    teamCapacityDidSwipe.current = false
  }
  const handleTeamCapacityTouchEnd = (event: React.TouchEvent<HTMLElement>) => {
    const startY = teamCapacityTouchStartY.current
    teamCapacityTouchStartY.current = null
    if (isDesktop || startY === null || !event.changedTouches[0]) return
    const deltaY = startY - event.changedTouches[0].clientY
    if (Math.abs(deltaY) < 24) return
    teamCapacityDidSwipe.current = true
    setOpenStatusPanel(deltaY > 0 ? 'team' : null)
  }
  const [dismissedAlertKeys, setDismissedAlertKeys] = useState<Set<string>>(new Set())
  const [exitingAlertKey, setExitingAlertKey] = useState<string | null>(null)
  const nowMs = useNow()

  const isMechanic = user?.role === 'mechanic'
  const isManager = user?.role === 'garage_owner' || user?.role === 'garage_admin'
  // Matches ACTIVITY_ROLES in backend/app/api/v1/endpoints/activity.py —
  // mechanics/fleet managers stay scoped to their own boards.
  const canViewActivity = ['garage_owner', 'garage_admin', 'receptionist'].includes(user?.role || '')
  const isExpandedFont = fontSize === 'comfortable' || fontSize === 'large'
  // Notification manager for queued, deduplicated notifications
  const { notify, banners, dismissBanner, clearBanners } = useNotificationManager()
  
  // Connect to WebSocket for real-time updates (replaces polling)
  useWebSocket({ onNotification: notify })
  
  // The home screen is an action queue. Capacity and financial reporting live
  // on their dedicated screens and are not loaded during routine navigation.
  const { data: stats, isLoading: loading, error: queryError, isFetching: isRefreshing, dataUpdatedAt } = useQuery<DashboardStats>({
    queryKey: ['dashboard-action-queue'],
    queryFn: async () => {
      const response = await api.get('/dashboard/action-queue')
      return response.data
    },
    refetchOnWindowFocus: true, // Refresh when tab becomes visible
    // A 429 means we're rate-limited, not that the request is broken —
    // retrying immediately just extends the block. Let the limiter's
    // window clear instead of hammering it.
    retry: (failureCount, err) => !(isAxiosError(err) && err.response?.status === 429) && failureCount < 1,
    refetchOnMount: false,
    staleTime: 60 * 1000,
  })

  const isRateLimited = isAxiosError(queryError) && queryError.response?.status === 429
  const error = queryError ? (isRateLimited ? 'Too many requests — waiting a moment before retrying' : 'Failed to load work queue') : null
  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt) : null
  
  const handleManualRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ['dashboard-action-queue'] })
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
  const teamMembers: MechanicWorkload[] = []
  const teamStatusByMechanicId = new Map<string, TeamCapacityStatusItem>()
  const teamAssignedTotal = teamMembers.reduce((sum, m) => sum + m.assigned_count, 0)
  const teamInProgressTotal = teamMembers.reduce((sum, m) => sum + m.in_progress_count, 0)
  const teamQueuedTotal = Math.max(teamAssignedTotal - teamInProgressTotal, 0)
  const teamWorkingCount = teamMembers.filter((m) => !!teamStatusByMechanicId.get(m.mechanic_id)?.active_session).length
  const teamReadyCount = teamMembers.filter((m) => {
    const status = teamStatusByMechanicId.get(m.mechanic_id)
    return !!status?.attendance_active && !status?.break_active && !status?.active_session
  }).length
  const teamOfflineCount = teamMembers.filter((m) => {
    const status = teamStatusByMechanicId.get(m.mechanic_id)
    return !status?.attendance_active && !status?.active_session && !status?.break_active
  }).length
  const prioritizedTeamMembers = [...teamMembers].sort((a, b) => {
    const priorityA = getTeamCapacitySortPriority(teamStatusByMechanicId.get(a.mechanic_id))
    const priorityB = getTeamCapacitySortPriority(teamStatusByMechanicId.get(b.mechanic_id))

    if (priorityA !== priorityB) return priorityA - priorityB
    if (b.in_progress_count !== a.in_progress_count) return b.in_progress_count - a.in_progress_count
    if (b.assigned_count !== a.assigned_count) return b.assigned_count - a.assigned_count
    return a.mechanic_name.localeCompare(b.mechanic_name)
  })
  const teamSnapshotCards = [
    {
      label: 'Active Jobs',
      value: teamInProgressTotal,
      className: 'border-emerald-500/15 bg-emerald-500/5',
      valueClass: 'text-emerald-300',
    },
    {
      label: 'On Floor',
      value: teamReadyCount + teamWorkingCount,
      className: 'border-sky-500/15 bg-sky-500/5',
      valueClass: 'text-sky-200',
    },
    {
      label: 'Queued Jobs',
      value: teamQueuedTotal,
      className: 'border-amber-500/15 bg-amber-500/5',
      valueClass: 'text-amber-200',
    },
    {
      label: 'Offline',
      value: teamOfflineCount,
      className: 'border-gray-500/15 bg-gray-500/5',
      valueClass: 'text-gray-200',
    },
  ]
  const teamCapacityHeaderClass = isExpandedFont ? 'text-base 2xl:text-lg' : 'text-sm 2xl:text-base'
  const teamCapacityMetaClass = isExpandedFont ? 'text-sm 2xl:text-base' : 'text-xs 2xl:text-sm'
  const teamCapacityNameClass = isExpandedFont ? 'text-base 2xl:text-lg' : 'text-sm 2xl:text-[15px]'
  const teamCapacityBodyClass = isExpandedFont ? 'text-sm 2xl:text-[15px]' : 'text-xs 2xl:text-sm'
  const teamCapacityGridHeightClass = isExpandedFont
    ? 'md:max-h-60 lg:max-h-40 2xl:max-h-44'
    : 'md:max-h-56 lg:max-h-36 2xl:max-h-40'
  const needsActionCount = stats?.orders_needing_action?.length || 0
  const onFloorCount = stats?.orders_on_floor?.length || 0
  const readyToCloseCount = stats?.orders_ready_to_close?.length || 0
  const highestPriorityMobileLane: 0 | 1 | 2 = needsActionCount > 0 ? 0 : onFloorCount > 0 ? 1 : 2
  const displayedMobileLane =
    (activeMobileLane === 0 && needsActionCount === 0) ||
    (activeMobileLane === 1 && onFloorCount === 0)
      ? highestPriorityMobileLane
      : activeMobileLane
  const getLaneContainerClass = (idx: 0 | 1 | 2) =>
    `bg-white/[0.03] rounded-xl border border-white/10 overflow-hidden flex flex-col ${
      isDesktop
        ? 'min-h-0'
        : displayedMobileLane === idx
          ? 'flex-1 min-h-0'
          : 'flex-none'
    }`
  const getLaneBodyClass = (idx: 0 | 1 | 2) =>
    isDesktop
      ? 'flex-1 min-h-0'
      : displayedMobileLane === idx
        ? 'flex-1 min-h-0 overflow-hidden'
        : 'h-0 overflow-hidden'
  // Global alert priority — computed once per render (nowMs ticks every minute)
  const allOrders: RecentOrder[] = [
    ...(stats?.orders_needing_action ?? []),
    ...(stats?.orders_on_floor ?? []),
    ...(stats?.orders_ready_to_close ?? []),
  ]
  const animatedIds = new Set(
    allOrders
      .map(o => ({ id: o.id, ...getOrderAlert(o, nowMs) }))
      .filter(a => a.canAnimate)
      .sort((a, b) => b.priority - a.priority)
      .slice(0, 3)
      .map(a => a.id)
  )
  const alertCounts = allOrders.reduce(
    (acc, o) => {
      const { level } = getOrderAlert(o, nowMs)
      if (level === 'red') acc.critical++
      else if (level === 'amber') acc.warning++
      return acc
    },
    { critical: 0, warning: 0 },
  )

  const revenueCards = [
    { label: 'Today Revenue', value: metricValue(stats?.revenue?.today), tone: 'text-emerald-400' },
    { label: 'Today Gross', value: metricValue(stats?.revenue?.today_gross_profit), tone: 'text-amber-300' },
    { label: 'Week Revenue', value: metricValue(stats?.revenue?.this_week), tone: 'text-emerald-400' },
    { label: 'Month Revenue', value: metricValue(stats?.revenue?.this_month), tone: 'text-emerald-400' },
  ]
  const hasAttentionRequired = false

  const handleDismissAlert = (key: string) => {
    setExitingAlertKey(key)
    setTimeout(() => {
      setDismissedAlertKeys(prev => new Set(prev).add(key))
      setExitingAlertKey(null)
    }, 200)
  }

  useEffect(() => {
    if (!hasAttentionRequired) {
      setDismissedAlertKeys(new Set())
      setExitingAlertKey(null)
    }
  }, [hasAttentionRequired])

  // On mobile the attention pills eat scarce vertical space, so auto-dismiss
  // them after a grace period: the first clears at 15s, then one more every 6s.
  // Staff can still tap through to the linked view before then. Desktop keeps
  // them until manually dismissed.
  const activeAlertKeys = [
    (stats?.low_stock_count ?? 0) > 0 && 'lowStock',
    (stats?.overdue_approvals ?? 0) > 0 && 'overdueApprovals',
    (stats?.declined_quotes ?? 0) > 0 && 'declinedQuotes',
  ].filter(Boolean) as string[]
  const activeAlertSignature = activeAlertKeys.join(',')

  useEffect(() => {
    if (isDesktop || !hasAttentionRequired) return
    const pending = activeAlertKeys.filter(k => !dismissedAlertKeys.has(k))
    if (pending.length === 0) return
    // First pill clears at 15s, then one more every 6s, so they fade out one at
    // a time rather than all at once.
    const timers = pending.map((k, i) =>
      setTimeout(() => handleDismissAlert(k), 15000 + i * 6000)
    )
    return () => timers.forEach(clearTimeout)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDesktop, hasAttentionRequired, activeAlertSignature])


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
        <Spinner size="xl" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-red-400">{error}</p>
        <button
          onClick={handleManualRefresh}
          disabled={isRefreshing}
          className="mt-4 inline-flex items-center gap-2 hover:opacity-80 disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ color: accentColors[500] }}
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
          {isRefreshing ? 'Retrying…' : 'Try again'}
        </button>
      </div>
    )
  }

  return (
    <div
      className={`flex flex-1 min-h-0 flex-col overflow-hidden ${
        isExpandedFont ? 'gap-4 2xl:gap-3' : 'gap-5 2xl:gap-4'
      }`}
    >
      {/* Header */}
      <div className="flex-shrink-0">
        <div className="flex flex-row items-start justify-between gap-3 lg:items-end">
          <div className="min-w-0">
            <h1 className="text-2xl sm:text-3xl 2xl:text-[2.15rem] font-bold text-white">
              {isMechanic ? 'My Workbench' : 'Shop Cockpit'}
            </h1>
            <p className="text-gray-400 mt-1 2xl:text-[1.02rem] truncate">
              {isMechanic
                ? `You have ${stats?.my_in_progress || 0} jobs in progress`
                : `Welcome back, ${user?.first_name || user?.email}`}
            </p>
          </div>

          {/* Manager CTA Buttons. On mobile they sit on the title's row and go
              icon-only to save width; labels return at sm+. */}
          {isManager && (
            <div className="flex flex-shrink-0 flex-wrap items-center justify-end gap-2.5 sm:gap-3 lg:flex-nowrap">
              <button
                onClick={() => setShowQuickForm(!showQuickForm)}
                className="flex h-12 min-w-12 items-center justify-center gap-2 rounded-xl px-3.5 font-semibold text-white transition-colors sm:px-4"
                style={{
                  backgroundColor: showQuickForm ? accentColors[600] : accentColors[500],
                  boxShadow: `0 10px 15px -3px ${accentColors[500]}33`,
                }}
                aria-label="Lightning Order"
              >
                <Zap className="h-5 w-5" />
                <span className="hidden sm:inline">Lightning Order</span>
              </button>
              <button
                onClick={() => navigate('/dashboard/repair-orders?new=true')}
                className="flex h-12 min-w-12 items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3.5 font-semibold text-white transition-colors hover:bg-white/10 sm:px-4"
                aria-label="Full Order"
              >
                <Plus className="h-5 w-5" />
                <span className="hidden sm:inline">Full Order</span>
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
              <SuggestingInput
                value={quickComplaint}
                onChange={(val) => {
                  setQuickComplaint(val)
                  if (quickTouched) {
                    setQuickErrors((prev) => ({
                      ...prev,
                      complaint: val.trim() ? undefined : 'Description required',
                    }))
                  }
                }}
                suggestUrl="/repair-orders/description-suggestions"
                variant="blueNoir"
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
              className="px-4 py-2 h-[38px] disabled:opacity-50 text-white font-semibold rounded-lg flex items-center gap-2 transition-colors shrink-0 self-end sm:self-start"
              style={{ backgroundColor: accentColors[500] }}
            >
              {quickSubmitting ? (
                <Spinner size="sm" className="border-white/40 border-t-white" />
              ) : (
                <Send className="w-4 h-4" />
              )}
              <span>Create</span>
            </button>
          </div>
        </form>
      )}

      {/* Attention pills (managers only) — each dismisses independently */}
      {isManager && hasAttentionRequired && (
        <AlertsBanner
          lowStockCount={stats?.low_stock_count || 0}
          overdueApprovals={stats?.overdue_approvals || 0}
          declinedQuotes={stats?.declined_quotes || 0}
          dismissedKeys={dismissedAlertKeys}
          exitingKey={exitingAlertKey}
          onDismiss={handleDismissAlert}
        />
      )}

      <div className={`flex flex-1 min-h-0 flex-col ${isExpandedFont ? 'gap-4 2xl:gap-3' : 'gap-5 2xl:gap-4'}`}>
        {/* Work Queue */}
        <div className="flex flex-1 min-h-0 flex-col gap-2.5 2xl:gap-2">
          <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden flex flex-col min-h-0 h-full">
          <div className="flex items-start justify-between gap-3 px-3.5 py-3 2xl:px-3 2xl:py-2.5 border-b border-white/10 flex-shrink-0 sm:items-center">
            <div className="flex min-w-0 items-center gap-2 flex-wrap">
              <div className="inline-flex items-center gap-2 text-sm 2xl:text-base font-semibold text-gray-300 uppercase tracking-[0.14em]">
                <span>{queueView === 'activity' ? 'Activity' : 'Work Queue'}</span>
              </div>
              {queueView === 'activity' ? (
                <>
                  <SectionInfoTooltip text="Recent repair-order activity across quotes, invoices, and payments — grouped by day and staff member." />
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-white/10 text-gray-300 whitespace-nowrap">
                    {activityCount} {activityCount === 1 ? 'event' : 'events'}
                  </span>
                </>
              ) : (
                <>
                  <SectionInfoTooltip text="Operational swimlanes showing where repair orders need immediate attention, are actively being worked, or are ready for final closeout." />
                  {alertCounts.critical > 0 && (
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-red-500/15 text-red-400 whitespace-nowrap">
                      {alertCounts.critical} critical
                    </span>
                  )}
                  {alertCounts.warning > 0 && (
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400 whitespace-nowrap">
                      {alertCounts.warning} {alertCounts.warning === 1 ? 'warning' : 'warnings'}
                    </span>
                  )}
                </>
              )}
            </div>

            <div className="flex shrink-0 items-center gap-2">
              {canViewActivity && (
                <div className="flex items-center gap-0.5 bg-white/5 rounded-md p-0.5">
                  <button
                    onClick={() => setQueueView('queue')}
                    className={`flex items-center gap-1.5 px-2.5 py-1 text-xs 2xl:text-sm rounded transition-colors ${
                      queueView === 'queue' ? 'bg-white/10 text-white' : 'text-gray-400 hover:text-white'
                    }`}
                  >
                    <LayoutGrid className="w-3.5 h-3.5" />
                    <span>Queue</span>
                  </button>
                  <button
                    onClick={() => setQueueView('activity')}
                    className={`flex items-center gap-1.5 px-2.5 py-1 text-xs 2xl:text-sm rounded transition-colors ${
                      queueView === 'activity' ? 'bg-white/10 text-white' : 'text-gray-400 hover:text-white'
                    }`}
                  >
                    <History className="w-3.5 h-3.5" />
                    <span>Activity</span>
                  </button>
                </div>
              )}
              <button
                onClick={handleManualRefresh}
                disabled={isRefreshing}
                className="flex items-center justify-center gap-1 rounded-md bg-white/5 px-1.5 py-1 text-xs text-gray-400 transition-colors hover:bg-white/10 hover:text-white sm:gap-2 sm:px-2.5 2xl:text-sm"
                title="Refresh dashboard"
                aria-label={isRefreshing ? 'Refreshing dashboard' : `Refresh dashboard, updated ${formatLastUpdated() || 'recently'}`}
              >
                <RefreshCw className={`w-3 h-3 ${isRefreshing ? 'animate-spin' : ''}`} />
                <span className="hidden sm:inline">{formatLastUpdated() || 'Refresh'}</span>
                <span className={`h-1.5 w-1.5 rounded-full ${error ? 'bg-red-500' : 'bg-green-500 animate-pulse'}`} />
              </button>
            </div>
          </div>

          {queueView === 'activity' ? (
            <RecentActivityFeed
              className="flex flex-1 min-h-0 flex-col p-3 2xl:p-2.5"
              onCountChange={setActivityCount}
            />
          ) : (
          <div className="flex flex-1 min-h-0 flex-col gap-3 p-3 2xl:gap-2.5 2xl:p-2.5 lg:grid lg:grid-cols-3">
              {/* Lane 1: Needs Action */}
              <div className={`${getLaneContainerClass(0)} ${needsActionCount === 0 ? 'hidden lg:flex' : ''}`}>
                <div className="flex items-center justify-between px-3.5 py-2.5 2xl:py-2 border-b border-white/10 flex-shrink-0 cursor-pointer lg:cursor-default" onClick={() => setActiveMobileLane(0)}>
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-red-400" />
                    <h3 className="text-sm 2xl:text-base font-semibold text-white">Needs Action</h3>
                    <SectionInfoTooltip text="Orders blocked by approvals, missing info, or other manager actions that should be handled first." />
                  </div>
                  <span className="text-xs 2xl:text-sm font-medium text-red-400 bg-red-500/10 px-2 py-0.5 rounded-full">
                    {needsActionCount}
                  </span>
                </div>
                <div className={getLaneBodyClass(0)}>
                  <div className="p-2.5 space-y-2 2xl:space-y-1.5 overflow-y-auto h-full scrollbar-dark">
                    {!stats?.orders_needing_action?.length ? (
                      <p className="text-gray-500 text-sm 2xl:text-base text-center py-6">All clear</p>
                    ) : (
                      stats.orders_needing_action.map((order) => (
                        <OrderCard
                          key={order.id}
                          order={order}
                          accentColor={accentColors[400]}
                          onClick={() => navigate(`/dashboard/repair-orders?selected=${order.id}&queue=needs_action`)}
                          alert={getOrderAlert(order, nowMs)}
                          animated={animatedIds.has(order.id)}
                        />
                      ))
                    )}
                  </div>
                </div>
              </div>

              {/* Lane 2: On the Floor */}
              <div className={`${getLaneContainerClass(1)} ${onFloorCount === 0 ? 'hidden lg:flex' : ''}`}>
                <div className="flex items-center justify-between px-3.5 py-2.5 2xl:py-2 border-b border-white/10 flex-shrink-0 cursor-pointer lg:cursor-default" onClick={() => setActiveMobileLane(1)}>
                  <div className="flex items-center gap-2">
                    <Wrench className="w-4 h-4" style={{ color: accentColors[400] }} />
                    <h3 className="text-sm 2xl:text-base font-semibold text-white">On the Floor</h3>
                    <SectionInfoTooltip text="Orders currently in production with technicians assigned or actively working." />
                  </div>
                  <span className="text-xs 2xl:text-sm font-medium px-2 py-0.5 rounded-full" style={{ color: accentColors[400], backgroundColor: `${accentColors[500]}1a` }}>
                    {onFloorCount}
                  </span>
                </div>
                <div className={getLaneBodyClass(1)}>
                  <div className="p-2.5 space-y-2 2xl:space-y-1.5 overflow-y-auto h-full scrollbar-dark">
                    {!stats?.orders_on_floor?.length ? (
                      <p className="text-gray-500 text-sm 2xl:text-base text-center py-6">No active work</p>
                    ) : (
                      stats.orders_on_floor.map((order) => (
                        <OrderCard
                          key={order.id}
                          order={order}
                          accentColor={accentColors[400]}
                          onClick={() => navigate(`/dashboard/repair-orders?selected=${order.id}&queue=on_floor`)}
                          alert={getOrderAlert(order, nowMs)}
                          animated={animatedIds.has(order.id)}
                        />
                      ))
                    )}
                  </div>
                </div>
              </div>

              {/* Lane 3: Ready to Close */}
              <div className={getLaneContainerClass(2)}>
                <div className="flex items-center justify-between px-3.5 py-2.5 2xl:py-2 border-b border-white/10 flex-shrink-0 cursor-pointer lg:cursor-default" onClick={() => setActiveMobileLane(2)}>
                  <div className="flex items-center gap-2">
                    <DollarSign className="w-4 h-4 text-emerald-400" />
                    <h3 className="text-sm 2xl:text-base font-semibold text-white">Ready to Close</h3>
                    <SectionInfoTooltip text="Completed work waiting for invoice to be sent, plus invoiced orders awaiting payment." />
                  </div>
                  <span className="text-xs 2xl:text-sm font-medium text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full">
                    {readyToCloseCount}
                  </span>
                </div>
                <div className={getLaneBodyClass(2)}>
                  <div className="p-2.5 space-y-2 2xl:space-y-1.5 overflow-y-auto h-full scrollbar-dark">
                    {!stats?.orders_ready_to_close?.length ? (
                      <p className="text-gray-500 text-sm 2xl:text-base text-center py-6">Nothing pending</p>
                    ) : (
                      stats.orders_ready_to_close.map((order) => (
                        <OrderCard
                          key={order.id}
                          order={order}
                          accentColor={accentColors[400]}
                          onClick={() => navigate(`/dashboard/repair-orders?selected=${order.id}&queue=ready_to_close`)}
                          alert={getOrderAlert(order, nowMs)}
                          animated={animatedIds.has(order.id)}
                        />
                      ))
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
          </div>
        </div>

        {/* Team capacity belongs on the dedicated team board and financial KPIs
            belong in Analytics. Keeping them off the operational home screen
            also avoids fetching those expensive aggregates on every visit. */}
        {false && isManager && (
          <div
            className={`fixed bottom-[calc(3.75rem+env(safe-area-inset-bottom))] left-2 z-30 mb-0 flex w-auto flex-shrink-0 flex-col border border-white/10 bg-[#171c23]/95 shadow-[0_-8px_24px_rgba(0,0,0,0.3)] transition-[max-height] duration-300 ease-out md:relative md:bottom-auto md:left-auto md:right-auto md:z-auto md:mb-0 md:w-full md:max-h-none md:flex-row md:items-stretch md:overflow-visible md:rounded-xl md:border-b md:bg-white/5 md:shadow-none ${
              openStatusPanel !== null
                ? 'right-2 max-h-[calc(100vh-7rem)] overflow-visible rounded-xl border-b animate-in slide-in-from-bottom-8'
                : 'right-2 max-h-10 overflow-hidden rounded-t-xl border-b-0'
            }`}
          >
            {/* Tabs: one shared strip, so it reads as a single control with two views
                rather than two unrelated buttons. */}
            <div
              className="relative z-50 flex items-stretch bg-[#171c23] md:bg-transparent"
            >
              <button
                type="button"
                onTouchStart={handleTeamCapacityTouchStart}
                onTouchEnd={handleTeamCapacityTouchEnd}
                onClick={() => {
                  if (teamCapacityDidSwipe.current) {
                    teamCapacityDidSwipe.current = false
                    return
                  }
                  setOpenStatusPanel(p => p === 'team' ? null : 'team')
                }}
                aria-expanded={openStatusPanel === 'team'}
                className={`flex flex-1 touch-pan-y flex-row items-center justify-center gap-1 px-2 py-1.5 transition-colors md:flex-none md:flex-col md:items-start md:justify-start md:px-3.5 md:py-2 2xl:px-3 border-b-2 ${openStatusPanel === 'team' ? 'text-white border-b-current' : 'text-gray-300 border-b-transparent hover:text-white'}`}
                style={openStatusPanel === 'team' ? { borderBottomColor: accentColors[500] } : undefined}
              >
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.12em] md:gap-2 md:text-sm md:tracking-[0.14em] 2xl:text-base">
                  {openStatusPanel === 'team' ? <ChevronUp className="h-3.5 w-3.5 md:h-4 md:w-4" /> : <ChevronDown className="h-3.5 w-3.5 md:h-4 md:w-4" />}
                  Team Capacity
                </span>
                <span className="hidden flex-wrap items-center gap-1.5 md:flex">
                  {teamSnapshotCards.map((card) => (
                    <span
                      key={card.label}
                      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] text-gray-400 ${card.className}`}
                    >
                      <span className={`text-xs font-semibold ${card.valueClass}`}>{card.value}</span>
                      <span>{card.label}</span>
                    </span>
                  ))}
                </span>
              </button>
              <div className="block w-px my-2 bg-white/10" />
              <button
                type="button"
                onClick={() => setOpenStatusPanel(p => p === 'revenue' ? null : 'revenue')}
                aria-expanded={openStatusPanel === 'revenue'}
                className={`flex flex-1 flex-row items-center justify-center gap-1 px-2 py-1.5 transition-colors md:flex-none md:flex-col md:items-start md:justify-start md:px-3.5 md:py-2 2xl:px-3 border-b-2 ${openStatusPanel === 'revenue' ? 'text-white border-b-current' : 'text-gray-300 border-b-transparent hover:text-white'}`}
                style={openStatusPanel === 'revenue' ? { borderBottomColor: accentColors[500] } : undefined}
              >
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.12em] md:gap-2 md:text-sm md:tracking-[0.14em] 2xl:text-base">
                  {openStatusPanel === 'revenue' ? <ChevronUp className="h-3.5 w-3.5 md:h-4 md:w-4" /> : <ChevronDown className="h-3.5 w-3.5 md:h-4 md:w-4" />}
                  Revenue KPIs
                </span>
                <span className="hidden items-center text-[10px] text-gray-400 bg-white/5 border border-white/10 rounded-full px-1.5 py-0.5 md:inline-flex 2xl:text-sm md:px-2.5">
                  {stats?.revenue?.total_paid_orders || 0} paid orders
                </span>
              </button>
            </div>

            {/* Expanded content renders as an overlay drawer above the rail so it never
                shrinks the Work Queue's flex-1 space. */}
            {openStatusPanel !== null && (
              <>
                <button
                  type="button"
                  aria-label="Close panel"
                  onClick={() => setOpenStatusPanel(null)}
                  className="fixed inset-0 z-40 cursor-default bg-black/40"
                />
                <div className="relative z-50 max-h-[calc(100vh-10rem)] overflow-y-auto border-t border-white/10 bg-[#14181f] p-2.5 shadow-2xl space-y-3 md:absolute md:bottom-full md:left-0 md:right-0 md:mb-2 md:max-h-[70vh] md:rounded-xl md:border md:p-3.5 md:space-y-4 2xl:p-3">
                  {openStatusPanel === 'team' && (
                    <div>
                      <div className="mb-2.5 hidden flex-col gap-2.5 md:flex lg:flex-row lg:items-center lg:justify-between">
                        <div className="flex items-center gap-2">
                          <span className={`${teamCapacityHeaderClass} font-semibold text-gray-300 uppercase tracking-[0.14em]`}>
                            Team Capacity
                          </span>
                          <button
                            type="button"
                            onClick={() => navigate('/dashboard/mechanics')}
                            className={`hidden lg:inline-block ${teamCapacityHeaderClass} text-gray-500 hover:text-white transition-colors`}
                          >
                            View board
                          </button>
                          <SectionInfoTooltip text="Technician staffing capacity snapshot with active vs queued work, per-technician load, and click-through to detailed timer boards." />
                        </div>
                        <div className="hidden lg:ml-auto lg:flex lg:flex-wrap lg:items-center lg:justify-end lg:gap-2 lg:pl-4">
                          {teamSnapshotCards.map((card) => (
                            <div
                              key={card.label}
                              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] text-gray-400 ${card.className}`}
                            >
                              <span className={`text-sm font-semibold ${card.valueClass}`}>{card.value}</span>
                              <span>{card.label}</span>
                            </div>
                          ))}
                        </div>
                      </div>

                      {!teamMembers.length ? (
                        <span className={`${teamCapacityMetaClass} text-gray-500`}>No technicians</span>
                      ) : (
                        <div className="space-y-3 lg:space-y-2">
                          <div className="flex items-center justify-between gap-3 px-1 lg:px-0">
                            <div className="min-w-0">
                              <div className="text-[11px] 2xl:text-xs uppercase tracking-[0.18em] text-gray-500">
                                Technician Board
                              </div>
                              <p className="mt-1 hidden text-xs text-gray-500 md:block 2xl:text-sm lg:hidden">
                                Tap a technician to open timers and assignments.
                              </p>
                            </div>
                            <span className={`${teamCapacityMetaClass} shrink-0 text-gray-500`}>
                              {teamMembers.length} techs
                            </span>
                          </div>

                          <div className={`grid grid-cols-1 gap-1.5 overflow-visible md:grid-cols-2 md:gap-2.5 md:overflow-y-auto md:pr-1 xl:grid-cols-3 2xl:grid-cols-4 ${teamCapacityGridHeightClass}`}>
                            {prioritizedTeamMembers.slice(0, 8).map((m) => {
                              const loadPct = m.assigned_count > 0
                                ? Math.round((m.in_progress_count / m.assigned_count) * 100)
                                : 0
                              const queued = Math.max(m.assigned_count - m.in_progress_count, 0)
                              const status = getTeamCapacityStatus(teamStatusByMechanicId.get(m.mechanic_id))
                              return (
                                <button
                                  type="button"
                                  key={m.mechanic_id}
                                  onClick={() => navigate(`/dashboard/mechanics/${m.mechanic_id}`)}
                                  className="min-h-[76px] min-w-0 rounded-lg border border-white/10 bg-white/[0.04] px-1.5 py-2 text-left transition-colors hover:bg-white/[0.06] md:rounded-xl md:px-3 md:py-3 lg:px-2.5 lg:py-2.5"
                                  title={`${m.mechanic_name}: ${status.label} · ${m.in_progress_count} active / ${m.assigned_count} assigned`}
                                >
                                  <div className="flex items-center gap-1.5">
                                    <div className="flex min-w-0 flex-1 items-center gap-2">
                                      <div
                                        className="h-6 w-6 rounded-full flex items-center justify-center text-[10px] font-semibold shrink-0 md:h-7 md:w-7 md:text-xs"
                                        style={{ backgroundColor: `${accentColors[500]}33`, color: accentColors[400] }}
                                      >
                                        {m.mechanic_name.charAt(0).toUpperCase()}
                                      </div>
                                      <span className={`${teamCapacityNameClass} text-xs font-semibold text-white truncate md:text-sm`}>{m.mechanic_name}</span>
                                    </div>
                                    <div className="flex shrink-0 items-center gap-1 lg:hidden">
                                      <span className="inline-flex items-center gap-0.5 rounded-md border border-white/10 bg-black/10 px-1.5 py-0.5">
                                        <span className="text-[10px] font-semibold text-white">{m.in_progress_count}</span>
                                        <span className="text-[8px] uppercase tracking-[0.06em] text-gray-500">Active</span>
                                      </span>
                                      <span className={`inline-flex items-center gap-0.5 rounded-md border px-1.5 py-0.5 ${queued > 0 ? 'border-amber-500/20 bg-amber-500/10' : 'border-white/10 bg-black/10'}`}>
                                        <span className={`text-[10px] font-semibold ${queued > 0 ? 'text-amber-200' : 'text-gray-300'}`}>{queued}</span>
                                        <span className="text-[8px] uppercase tracking-[0.06em] text-gray-500">Queued</span>
                                      </span>
                                    </div>
                                    <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium md:px-2.5 md:py-1 md:text-[11px] 2xl:text-xs ${status.badgeClass}`}>
                                      {status.badgeLabel}
                                    </span>
                                  </div>
                                  <div className={`mt-3 hidden md:flex lg:hidden items-center justify-between gap-2 ${teamCapacityBodyClass} text-gray-400`}>
                                    <span className="truncate">{status.label}</span>
                                    <span className="shrink-0">{m.assigned_count > 0 ? `${loadPct}% load` : 'Open capacity'}</span>
                                  </div>
                                  <div className="mt-2 hidden md:block lg:hidden h-2 rounded-full bg-white/10 overflow-hidden">
                                    <div
                                      className="h-2 rounded-full"
                                      style={{ width: `${loadPct}%`, backgroundColor: accentColors[500] }}
                                    />
                                  </div>
                                  <div className={`mt-2 hidden lg:flex items-center gap-3 ${teamCapacityBodyClass} text-gray-300`}>
                                    <span>
                                      <span className="font-semibold text-white">{m.in_progress_count}</span> active
                                    </span>
                                    <span>
                                      <span className={`font-semibold ${queued > 0 ? 'text-amber-200' : 'text-white'}`}>{queued}</span> queued
                                    </span>
                                    <span className="ml-auto shrink-0 text-gray-400">
                                      {m.assigned_count > 0 ? `${loadPct}% load` : 'Open capacity'}
                                    </span>
                                  </div>
                                  <div className="mt-2 hidden lg:block h-1.5 rounded-full bg-white/10 overflow-hidden">
                                    <div
                                      className="h-1.5 rounded-full"
                                      style={{ width: `${loadPct}%`, backgroundColor: accentColors[500] }}
                                    />
                                  </div>
                                </button>
                              )
                            })}
                            {teamMembers.length > 8 && (
                              <div className={`${teamCapacityMetaClass} text-gray-500 px-1 col-span-full`}>
                                +{teamMembers.length - 8} more technicians
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {openStatusPanel === 'revenue' && (
                    <div>
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between mb-2.5">
                        <div className="flex items-center gap-2">
                          <span className="text-sm 2xl:text-base font-semibold text-gray-400 uppercase tracking-[0.14em]">
                            Revenue KPIs
                          </span>
                          <SectionInfoTooltip text="Minimal finance snapshot for the current shop day, week, and month." />
                        </div>
                        <span className="text-xs 2xl:text-sm text-gray-400 bg-white/5 border border-white/10 rounded-full px-2.5 py-1">
                          {stats?.revenue?.total_paid_orders || 0} paid orders
                        </span>
                      </div>
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
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
