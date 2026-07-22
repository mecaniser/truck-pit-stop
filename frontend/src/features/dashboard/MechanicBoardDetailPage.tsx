import { useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { ArrowLeft, PlayCircle, Square, Pencil, Trash2, Settings, ChevronDown, ChevronUp, ChevronLeft, ChevronRight, CalendarDays, User } from 'lucide-react'
import api from '@/lib/api'
import { MISC_WORK_OPTIONS, formatMiscCategory, formatSessionType } from '@/lib/mechanicWorkLabels'
import { formatSuggestedNextAction } from '@/lib/mechanicSuggestions'
import LiveElapsedTimer from '@/components/LiveElapsedTimer'
import SectionInfoTooltip from '@/components/SectionInfoTooltip'
import { useWebSocket } from '@/hooks/useWebSocket'
import type { AttentionPriority } from '@/types'
import { ATTENTION_REASON_LABELS } from '@/types'
import { 
  Card, Button, Input, Badge, StatusLED, Header, Spinner, 
  staggeredReveal, Label
} from '@/components/ui'

interface SessionRow {
  id: string
  session_type: 'repair_order' | 'misc'
  repair_order_id: string | null
  misc_category: string | null
  note: string | null
  started_at: string
  ended_at: string | null
  stop_reason: string | null
}

interface MechanicSummary {
  mechanic_id: string
  mechanic_name: string
  date: string
  timezone: string
  shift_start_local: string
  shift_end_local: string
  core_target_minutes: number
  tracked_minutes: number
  ro_minutes: number
  misc_minutes: number
  overtime_minutes: number
  utilization_percent: number
  efficiency_percent: number | null
  attendance_active: boolean
  attendance_started_at: string | null
  attendance_ended_at: string | null
  break_active: boolean
  break_started_at: string | null
  attendance_minutes: number
  break_minutes: number
  idle_minutes: number
  late_arrival_minutes: number
  early_leave_minutes: number
  flex_budget_minutes: number
  flex_used_minutes: number
  flex_remaining_minutes: number
  flex_overrun_minutes: number
  core_gap_minutes: number
  core_countdown_elapsed_minutes: number
  core_countdown_remaining_minutes: number
  tracked_vs_attendance_gap_minutes: number
  work_coverage_percent: number | null
  assigned_ready_orders_count: number
  untimed_in_progress_orders_count: number
  held_orders_count: number
  held_orders: Array<{
    id: string
    order_number: string
    hold_reason: string | null
    held_at: string | null
  }>
  recommended_order_id: string | null
  recommended_order_number: string | null
  suggested_next_action: 'clock_in' | 'end_break' | 'continue_ro' | 'stop_misc_pick_ro' | 'start_assigned_ro' | 'start_misc' | 'clock_out'
  attention_priority: AttentionPriority
  attention_reasons: string[]
  active_session: {
    id: string
    session_type: 'repair_order' | 'misc'
    repair_order_id: string | null
    misc_category: string | null
    started_at: string | null
  } | null
  trend_7_days: Array<{
    date: string
    tracked_minutes: number
    utilization_percent: number
    efficiency_percent: number | null
  }>
}

interface BoardDetailResponse {
  mechanic: MechanicSummary
  today_sessions: SessionRow[]
}

type EditMode = 'edit' | 'delete' | null
const formatCoverageLabel = (coverage: number | null, attendanceMinutes: number) => {
  if (coverage == null) return 'n/a'
  if (attendanceMinutes < 15) return 'warming up'
  return `${coverage.toFixed(1)}%`
}

const HOLD_REASON_LABELS: Record<string, string> = {
  waiting_for_parts: 'Waiting for parts',
  waiting_for_customer_approval: 'Waiting for customer approval',
  need_more_info: 'Need more information',
  other: 'Other',
  switched_to_other_ro: 'Switched to another job',
}

const formatHoldReason = (reason?: string | null) => {
  if (!reason) return 'On hold'
  return HOLD_REASON_LABELS[reason] || reason.replace(/_/g, ' ')
}

const formatDuration = (minutes: number) => {
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

const formatTimeInZone = (isoTimestamp: string | null, timeZone: string) => {
  if (!isoTimestamp) return null
  const parsed = new Date(isoTimestamp)
  if (Number.isNaN(parsed.getTime())) return null
  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
    timeZone,
    timeZoneName: 'short',
  }).format(parsed)
}

const computeSessionDurationMinutes = (s: SessionRow): number => {
  const start = new Date(s.started_at).getTime()
  const end = s.ended_at ? new Date(s.ended_at).getTime() : Date.now()
  return Math.max(0, (end - start) / 60000)
}

const localDateKey = (value = new Date()) => [
  value.getFullYear(),
  String(value.getMonth() + 1).padStart(2, '0'),
  String(value.getDate()).padStart(2, '0'),
].join('-')

type DetailTab = 'overview' | 'controls'

export default function MechanicBoardDetailPage() {
  const { mechanicId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  useWebSocket()

  const [sessionType, setSessionType] = useState<'repair_order' | 'misc'>('misc')
  const [repairOrderId, setRepairOrderId] = useState('')
  const [miscCategory, setMiscCategory] = useState('shop_cleanup')
  const [note, setNote] = useState('')
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [trendEndDate, setTrendEndDate] = useState<string | null>(null)
  const currentWorkDateRef = useRef<string | null>(null)

  const [activeTab, setActiveTab] = useState<DetailTab>('overview')
  const [sessionsExpanded, setSessionsExpanded] = useState(false)

  const [editMode, setEditMode] = useState<EditMode>(null)
  const [selectedSession, setSelectedSession] = useState<SessionRow | null>(null)
  const [editReason, setEditReason] = useState('')
  const [editNote, setEditNote] = useState('')

  const { data, isLoading, isError } = useQuery<BoardDetailResponse>({
    queryKey: ['mechanic-board-detail', mechanicId, selectedDate, trendEndDate],
    queryFn: async () => {
      const response = await api.get(`/dashboard/mechanics/${mechanicId}/board`, {
        params: selectedDate ? {
          date: selectedDate,
          ...(trendEndDate ? { trend_end_date: trendEndDate } : {}),
        } : undefined,
      })
      return response.data
    },
    enabled: !!mechanicId,
    refetchOnWindowFocus: true,
  })

  const refreshBoard = () => {
    queryClient.invalidateQueries({ queryKey: ['mechanic-board-detail', mechanicId] })
    queryClient.invalidateQueries({ queryKey: ['mechanic-board-team'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
    queryClient.invalidateQueries({ queryKey: ['mechanic-day-summary'] })
  }

  const startTimerMutation = useMutation({
    mutationFn: async () => {
      if (!mechanicId) throw new Error('Missing mechanic id')
      const payload: any = {
        session_type: sessionType,
        note: note || undefined,
      }
      if (sessionType === 'repair_order') {
        payload.repair_order_id = repairOrderId
      } else {
        payload.misc_category = miscCategory
      }
      await api.post(`/dashboard/mechanics/${mechanicId}/timer/start`, payload)
    },
    onSuccess: () => {
      toast.success('Timer started')
      setNote('')
      setRepairOrderId('')
      refreshBoard()
    },
    onError: (error: any) => toast.error(error?.response?.data?.detail || 'Failed to start timer'),
  })

  const stopTimerMutation = useMutation({
    mutationFn: async () => {
      if (!mechanicId) throw new Error('Missing mechanic id')
      await api.post(`/dashboard/mechanics/${mechanicId}/timer/stop`, {})
    },
    onSuccess: () => {
      toast.success('Timer stopped')
      refreshBoard()
    },
    onError: (error: any) => toast.error(error?.response?.data?.detail || 'Failed to stop timer'),
  })

  const attendanceToggleMutation = useMutation({
    mutationFn: async () => {
      if (!mechanicId) throw new Error('Missing mechanic id')
      if (data?.mechanic.attendance_active) {
        await api.post(`/dashboard/mechanics/${mechanicId}/attendance/clock-out`, {})
        return
      }
      await api.post(`/dashboard/mechanics/${mechanicId}/attendance/clock-in`, {})
    },
    onSuccess: () => {
      toast.success(data?.mechanic.attendance_active ? 'Clocked out' : 'Clocked in')
      refreshBoard()
    },
    onError: (error: any) => toast.error(error?.response?.data?.detail || 'Failed to update attendance'),
  })

  const breakToggleMutation = useMutation({
    mutationFn: async () => {
      if (!mechanicId) throw new Error('Missing mechanic id')
      if (data?.mechanic.break_active) {
        await api.post(`/dashboard/mechanics/${mechanicId}/break/end`, {})
        return
      }
      await api.post(`/dashboard/mechanics/${mechanicId}/break/start`, {})
    },
    onSuccess: () => {
      toast.success(data?.mechanic.break_active ? 'Break ended' : 'Break started')
      refreshBoard()
    },
    onError: (error: any) => toast.error(error?.response?.data?.detail || 'Failed to update break state'),
  })

  const editSessionMutation = useMutation({
    mutationFn: async () => {
      if (!selectedSession) throw new Error('No session selected')
      await api.patch(`/dashboard/mechanics/time-sessions/${selectedSession.id}`, {
        note: editNote,
        manager_reason: editReason,
      })
    },
    onSuccess: () => {
      toast.success('Session updated')
      setEditMode(null)
      setSelectedSession(null)
      setEditReason('')
      setEditNote('')
      refreshBoard()
    },
    onError: (error: any) => toast.error(error?.response?.data?.detail || 'Failed to edit session'),
  })

  const deleteSessionMutation = useMutation({
    mutationFn: async () => {
      if (!selectedSession) throw new Error('No session selected')
      await api.post(`/dashboard/mechanics/time-sessions/${selectedSession.id}/delete`, {
        manager_reason: editReason,
      })
    },
    onSuccess: () => {
      toast.success('Session deleted')
      setEditMode(null)
      setSelectedSession(null)
      setEditReason('')
      setEditNote('')
      refreshBoard()
    },
    onError: (error: any) => toast.error(error?.response?.data?.detail || 'Failed to delete session'),
  })

  const active = useMemo(() => data?.mechanic.active_session != null, [data?.mechanic.active_session])

  const sessionTotals = useMemo(() => {
    if (!data?.today_sessions.length) return null
    const totals: Record<string, number> = { repair_order: 0, misc: 0 }
    for (const s of data.today_sessions) {
      const mins = computeSessionDurationMinutes(s)
      totals[s.session_type] = (totals[s.session_type] || 0) + mins
    }
    return totals
  }, [data?.today_sessions])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" />
      </div>
    )
  }

  if (isError || !data) {
    return (
      <Card className="p-6">
        <p className="text-red-400">Failed to load technician board detail.</p>
      </Card>
    )
  }

  const m = data.mechanic
  if (!selectedDate && !currentWorkDateRef.current) {
    currentWorkDateRef.current = m.date
  }
  const todayDate = currentWorkDateRef.current || localDateKey()
  const isToday = m.date === todayDate
  const trendRows = m.trend_7_days || []
  const attendanceStartedLabel = formatTimeInZone(m.attendance_started_at, m.timezone)
  const attendanceEndedLabel = formatTimeInZone(m.attendance_ended_at, m.timezone)
  const attendanceMetaLabel = m.attendance_active
    ? (attendanceStartedLabel ? `Clocked in at ${attendanceStartedLabel}` : null)
    : (attendanceEndedLabel ? `Clocked out at ${attendanceEndedLabel}` : null)
  const attendanceWindowLabel = attendanceStartedLabel
    ? `${attendanceStartedLabel}${attendanceEndedLabel ? ` – ${attendanceEndedLabel}` : ' – now'}`
    : 'No clock activity'

  const formatTrendDate = (isoDate: string) => {
    const parsed = new Date(`${isoDate}T00:00:00`)
    if (Number.isNaN(parsed.getTime())) return isoDate
    return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  }
  const openRecommendedOrder = () => {
    if (!m.recommended_order_id) return
    navigate(`/dashboard/repair-orders?selected=${m.recommended_order_id}`)
  }
  const changeDate = (dateValue: string, nextTrendEndDate = trendEndDate || todayDate) => {
    setSelectedDate(dateValue)
    setTrendEndDate(nextTrendEndDate)
    setSessionsExpanded(false)
    setActiveTab('overview')
  }
  const moveTrendWeek = (days: number) => {
    const parsed = new Date(`${trendEndDate || todayDate}T12:00:00`)
    parsed.setDate(parsed.getDate() + days)
    const nextTrendEndDate = localDateKey(parsed)
    const cappedTrendEndDate = nextTrendEndDate > todayDate ? todayDate : nextTrendEndDate
    changeDate(cappedTrendEndDate, cappedTrendEndDate)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <button 
          onClick={() => navigate('/dashboard/mechanics')} 
          className="p-2.5 rounded-xl bg-zinc-800/60 hover:bg-zinc-700 text-zinc-300 border border-zinc-700/50 transition-all duration-200"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <Header
          title={m.mechanic_name}
          subtitle={`${m.date} · ${m.timezone}`}
          icon={<User className="w-5 h-5 text-[var(--accent-400)]" />}
        />
      </div>

      {isToday && m.attention_priority !== 'green' && m.attention_reasons.length > 0 ? (
        <Card 
          variant="subtle" 
          padding="none" 
          className={`px-4 py-3 ${m.attention_priority === 'red' ? 'border-red-500/30 bg-red-950/30' : 'border-amber-500/30 bg-amber-950/30'}`}
        >
          <div className="flex items-center gap-3">
            <StatusLED status={m.attention_priority === 'red' ? 'error' : 'warning'} />
            <span className={`text-sm font-medium ${m.attention_priority === 'red' ? 'text-red-200' : 'text-amber-200'}`}>
              {m.attention_reasons.map((r) => ATTENTION_REASON_LABELS[r] || r).join(' · ')}
            </span>
          </div>
        </Card>
      ) : null}

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-zinc-700/50 pb-px">
        <button
          onClick={() => setActiveTab('overview')}
          className={`px-4 py-2.5 text-sm font-semibold rounded-t-xl transition-all duration-200 ${
            activeTab === 'overview'
              ? 'bg-zinc-800/80 text-zinc-100 border border-zinc-700/50 border-b-transparent -mb-px'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/40'
          }`}
        >
          Overview
        </button>
        {isToday ? (
          <button
            onClick={() => setActiveTab('controls')}
            className={`px-4 py-2.5 text-sm font-semibold rounded-t-xl transition-all duration-200 flex items-center gap-2 ${
              activeTab === 'controls'
                ? 'bg-zinc-800/80 text-zinc-100 border border-zinc-700/50 border-b-transparent -mb-px'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/40'
            }`}
          >
            <Settings className="w-3.5 h-3.5" />
            Admin Controls
          </button>
        ) : null}
      </div>

      {/* ── OVERVIEW TAB ── */}
      {activeTab === 'overview' && (
        <>
          <Card className="space-y-4">
            <div className="flex items-center gap-2">
              <h2 className="text-zinc-100 font-semibold">Daily Summary</h2>
              <SectionInfoTooltip text="At-a-glance performance for this technician on the selected work day: scheduled shift, attendance, tracked hours, work mix, utilization, and efficiency." />
            </div>
            <div className="text-xs text-zinc-400">
              Scheduled shift: <span className="font-semibold text-zinc-200">{m.shift_start_local}–{m.shift_end_local}</span>
              {' · '}Attendance: <span className="font-semibold text-zinc-200">{formatDuration(m.attendance_minutes)}</span>
              {' · '}Clock activity: <span className="font-semibold text-zinc-200">{attendanceWindowLabel}</span>
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-8 gap-4 text-sm">
              <div className="text-zinc-400">Tracked<br /><span className="text-zinc-100 font-semibold">{(m.tracked_minutes / 60).toFixed(1)}h</span></div>
              <div className="text-zinc-400">RO<br /><span className="text-zinc-100 font-semibold">{(m.ro_minutes / 60).toFixed(1)}h</span></div>
              <div className="text-zinc-400">Misc<br /><span className="text-zinc-100 font-semibold">{(m.misc_minutes / 60).toFixed(1)}h</span></div>
              <div className="text-zinc-400">Break<br /><span className="text-zinc-100 font-semibold">{(m.break_minutes / 60).toFixed(1)}h</span></div>
              <div className="text-zinc-400">Idle<br /><span className="text-zinc-100 font-semibold">{(m.idle_minutes / 60).toFixed(1)}h</span></div>
              <div className="text-zinc-400">Utilization<br /><span className="text-amber-400 font-semibold">{m.utilization_percent.toFixed(1)}%</span></div>
              <div className="text-zinc-400">Efficiency<br /><span className="text-zinc-100 font-semibold">{m.efficiency_percent == null ? 'n/a' : `${m.efficiency_percent.toFixed(1)}%`}</span></div>
              <div className="text-zinc-400">Core Gap<br /><span className="text-zinc-100 font-semibold">{(m.core_gap_minutes / 60).toFixed(1)}h</span></div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
              <div className="rounded-xl border border-[var(--accent-500)]/30 bg-[var(--accent-500)]/10 px-3 py-2.5 text-[var(--accent-400)]">
                Core Countdown Remaining: <span className="font-semibold">{(m.core_countdown_remaining_minutes / 60).toFixed(1)}h</span>
              </div>
              <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/40 px-3 py-2.5 text-zinc-200">
                Tracked Progress: <span className="font-semibold">{(m.tracked_minutes / 60).toFixed(1)}h / {(m.core_target_minutes / 60).toFixed(1)}h</span>
              </div>
              <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/40 px-3 py-2.5 text-zinc-200">
                Work Coverage: <span className="font-semibold">{formatCoverageLabel(m.work_coverage_percent, m.attendance_minutes)}</span>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
              <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/40 px-3 py-2.5 text-zinc-300 flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:gap-2">
                <div className="flex items-center gap-2">
                  <StatusLED status={m.attendance_active ? 'active' : 'inactive'} />
                  Attendance:{' '}
                  <span className={m.attendance_active ? 'text-emerald-300' : 'text-zinc-200'}>
                    {m.attendance_active ? 'Clocked In' : 'Clocked Out'}
                  </span>
                </div>
                {attendanceMetaLabel ? (
                  <span className="text-[11px] text-zinc-500">{attendanceMetaLabel}</span>
                ) : null}
              </div>
              <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/40 px-3 py-2.5 text-zinc-300 flex items-center gap-2">
                <StatusLED status={m.break_active ? 'warning' : 'inactive'} />
                Break:{' '}
                <span className={m.break_active ? 'text-amber-300' : 'text-zinc-200'}>
                  {m.break_active ? 'On Break' : 'No Break'}
                </span>
              </div>
              <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/40 px-3 py-2.5 text-zinc-300">
                Flex: <span className="text-zinc-100">{m.flex_used_minutes}m / {m.flex_budget_minutes}m</span>
                {m.flex_overrun_minutes > 0 ? <span className="text-red-300"> · +{m.flex_overrun_minutes}m</span> : null}
              </div>
            </div>
            <div className="text-sm text-zinc-400 flex items-center gap-2">
              Live timer:{' '}
              {m.active_session?.started_at ? (
                <span className="text-emerald-300 flex items-center gap-2">
                  <StatusLED status="active" />
                  {formatSessionType(m.active_session.session_type)}
                  {m.active_session.session_type === 'misc' && m.active_session.misc_category
                    ? ` (${formatMiscCategory(m.active_session.misc_category)})`
                    : ''}
                  {' '}· <LiveElapsedTimer startedAt={m.active_session.started_at} className="font-mono text-emerald-200" />
                </span>
              ) : (
                <span className="text-zinc-300 flex items-center gap-2">
                  <StatusLED status="inactive" />
                  idle
                </span>
              )}
            </div>
            {isToday ? <Card variant="subtle" padding="sm" className="space-y-2">
              <div className="text-xs text-zinc-400">
                Suggested next action:{' '}
                <span className="text-zinc-200 font-medium">{formatSuggestedNextAction(m.suggested_next_action)}</span>
              </div>
              <div className="text-[11px] text-zinc-500">
                Ready assigned: <span className="text-zinc-200">{m.assigned_ready_orders_count}</span>
                {' · '}
                Untimed in-progress: <span className="text-zinc-200">{m.untimed_in_progress_orders_count}</span>
                {m.recommended_order_number ? (
                  <>
                    {' · '}
                    Recommended RO: <span className="text-zinc-200">{m.recommended_order_number}</span>
                  </>
                ) : null}
              </div>
              <div className="flex items-center gap-2 pt-2">
                {m.recommended_order_id ? (
                  <Button size="sm" onClick={openRecommendedOrder}>
                    Open Recommended RO
                  </Button>
                ) : null}
              </div>
            </Card> : null}
            {m.held_orders_count > 0 ? (
              <Card variant="subtle" padding="sm" className="border-amber-500/30 bg-amber-950/30">
                <div className="text-xs text-amber-200 font-semibold flex items-center gap-2">
                  <StatusLED status="warning" />
                  On-hold repair orders ({m.held_orders_count})
                </div>
                <div className="mt-2 space-y-1">
                  {(m.held_orders || []).map((order) => (
                    <div key={order.id} className="text-xs text-amber-100">
                      {order.order_number} · {formatHoldReason(order.hold_reason)}
                    </div>
                  ))}
                </div>
              </Card>
            ) : null}
          </Card>

          <Card className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <h2 className="text-zinc-100 font-semibold">7-Day Trend</h2>
                <SectionInfoTooltip text="Select a day to inspect its attendance and work sessions. Use the week controls or calendar to browse older work." />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button className="whitespace-nowrap" size="sm" variant="secondary" onClick={() => moveTrendWeek(-7)} aria-label="Previous week">
                  <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
                    <ChevronLeft className="h-4 w-4 shrink-0" />
                    Previous week
                  </span>
                </Button>
                <label className="relative flex items-center">
                  <CalendarDays className="pointer-events-none absolute left-3 h-4 w-4 text-zinc-500" />
                  <input
                    type="date"
                    value={m.date}
                    max={todayDate}
                    onChange={(event) => event.target.value && changeDate(event.target.value, event.target.value)}
                    aria-label="Select work day"
                    className="min-w-[9.5rem] rounded-xl border border-zinc-700/50 bg-zinc-800/60 py-2 pl-9 pr-3 text-sm text-zinc-200"
                  />
                </label>
                {!isToday ? (
                  <Button className="whitespace-nowrap" size="sm" variant="secondary" onClick={() => changeDate(todayDate, todayDate)}>Today</Button>
                ) : null}
                <Button
                  className="whitespace-nowrap"
                  size="sm"
                  variant="secondary"
                  onClick={() => moveTrendWeek(7)}
                  disabled={(trendEndDate || todayDate) >= todayDate}
                  aria-label="Next week"
                >
                  <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
                    Next week
                    <ChevronRight className="h-4 w-4 shrink-0" />
                  </span>
                </Button>
              </div>
            </div>
            {!trendRows.length ? (
              <p className="text-sm text-zinc-400">No trend data yet.</p>
            ) : (
              <>
                <div className="space-y-2 md:hidden">
                  {trendRows.map((row, i) => (
                    <button
                      key={row.date}
                      type="button"
                      onClick={() => changeDate(row.date)}
                      aria-pressed={row.date === m.date}
                      className="w-full text-left"
                    >
                    <Card
                      variant="subtle"
                      padding="sm"
                      className={`animate-[fadeIn_0.3s_ease-out_forwards] opacity-0 transition-colors ${row.date === m.date ? 'border-[var(--accent-400)] bg-[var(--accent-500)]/10' : 'hover:border-zinc-500'}`}
                      style={staggeredReveal(i)}
                    >
                      <div className="flex items-center justify-between text-xs text-zinc-400">
                        <span>{row.date}</span>
                        <span className="text-zinc-100 font-medium">{row.utilization_percent.toFixed(1)}%</span>
                      </div>
                      <div className="mt-2 h-2 bg-zinc-800/60 rounded-full overflow-hidden">
                        <div className="h-2 bg-[var(--accent-500)] rounded-full transition-all" style={{ width: `${Math.min(row.utilization_percent, 100)}%` }} />
                      </div>
                      <div className="mt-2 text-[11px] text-zinc-500">
                        Tracked {(row.tracked_minutes / 60).toFixed(1)}h · Efficiency {row.efficiency_percent == null ? 'n/a' : `${row.efficiency_percent.toFixed(1)}%`}
                      </div>
                    </Card>
                    </button>
                  ))}
                </div>
                <div className="hidden md:grid md:grid-cols-7 md:gap-3">
                  {trendRows.map((row, i) => (
                    <button
                      key={row.date}
                      type="button"
                      onClick={() => changeDate(row.date)}
                      aria-pressed={row.date === m.date}
                      className="min-w-0 text-left"
                    >
                    <Card
                      variant="subtle"
                      padding="sm"
                      className={`h-full animate-[fadeIn_0.3s_ease-out_forwards] opacity-0 transition-colors ${row.date === m.date ? 'border-[var(--accent-400)] bg-[var(--accent-500)]/10' : 'hover:border-zinc-500'}`}
                      style={staggeredReveal(i)}
                    >
                      <div className="flex items-center justify-between text-[11px] text-zinc-400">
                        <span>{formatTrendDate(row.date)}</span>
                        <span className="text-zinc-100 font-medium">{row.utilization_percent.toFixed(0)}%</span>
                      </div>
                      <div className="mt-2 h-2 bg-zinc-800/60 rounded-full overflow-hidden">
                        <div className="h-2 bg-[var(--accent-500)] rounded-full transition-all" style={{ width: `${Math.min(row.utilization_percent, 100)}%` }} />
                      </div>
                      <div className="mt-2 text-[10px] text-zinc-500 leading-tight">
                        {(row.tracked_minutes / 60).toFixed(1)}h · {row.efficiency_percent == null ? 'n/a' : `${row.efficiency_percent.toFixed(0)}%`}
                      </div>
                    </Card>
                    </button>
                  ))}
                </div>
              </>
            )}
          </Card>

          {/* Selected-day sessions — active session prominent, history collapsed */}
          <Card className="space-y-4">
            <div className="flex items-center gap-2">
              <h2 className="text-zinc-100 font-semibold">Work Sessions · {formatTrendDate(m.date)}</h2>
              <SectionInfoTooltip text="Chronological record of all timer sessions for the selected day, including active, stopped, edited, and deletable entries." />
            </div>

            {!data.today_sessions.length ? (
              <p className="text-zinc-400 text-sm">No sessions recorded for this day.</p>
            ) : (() => {
              const activeSession = data.today_sessions.find((s) => !s.ended_at)
              const completedSessions = data.today_sessions.filter((s) => !!s.ended_at)

              const renderSessionRow = (s: SessionRow, index?: number) => {
                const durationMin = computeSessionDurationMinutes(s)
                return (
                  <Card 
                    key={s.id} 
                    variant="subtle" 
                    padding="sm"
                    className={index !== undefined ? 'animate-[fadeIn_0.3s_ease-out_forwards] opacity-0' : ''}
                    style={index !== undefined ? staggeredReveal(index) : undefined}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-zinc-100 text-sm font-semibold">
                            {formatSessionType(s.session_type)}
                            {s.misc_category ? ` · ${formatMiscCategory(s.misc_category)}` : ''}
                          </span>
                          {s.ended_at ? (
                            <Badge variant="warning">{formatDuration(durationMin)}</Badge>
                          ) : null}
                        </div>
                        <div className="text-xs text-zinc-400 mt-1">
                          {new Date(s.started_at).toLocaleTimeString()} – {s.ended_at ? new Date(s.ended_at).toLocaleTimeString() : 'now'}
                        </div>
                        {!s.ended_at ? (
                          <div className="text-xs text-emerald-300 mt-2 flex items-center gap-2">
                            <StatusLED status="active" />
                            Running: <LiveElapsedTimer startedAt={s.started_at} className="font-mono text-emerald-200" />
                          </div>
                        ) : null}
                        {s.note && <div className="text-xs text-zinc-300 mt-2 truncate">{s.note}</div>}
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          onClick={() => {
                            setSelectedSession(s)
                            setEditNote(s.note || '')
                            setEditReason('')
                            setEditMode('edit')
                          }}
                          className="p-2 rounded-lg bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 border border-amber-500/30 transition-all duration-200"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => {
                            setSelectedSession(s)
                            setEditReason('')
                            setEditMode('delete')
                          }}
                          className="p-2 rounded-lg bg-red-500/20 text-red-300 hover:bg-red-500/30 border border-red-500/30 transition-all duration-200"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  </Card>
                )
              }

              return (
                <div className="space-y-3">
                  {/* Active session — always visible */}
                  {activeSession ? renderSessionRow(activeSession) : (
                    <div className="text-sm text-zinc-400 flex items-center gap-2">
                      <StatusLED status="inactive" />
                      No active timer
                    </div>
                  )}

                  {/* Summary footer — always visible */}
                  {sessionTotals && (
                    <Card variant="subtle" padding="sm" className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-300">
                      <span>Total RO: <span className="text-zinc-100 font-semibold">{formatDuration(sessionTotals.repair_order || 0)}</span></span>
                      <span>Total Misc: <span className="text-zinc-100 font-semibold">{formatDuration(sessionTotals.misc || 0)}</span></span>
                      <span>Break: <span className="text-zinc-100 font-semibold">{formatDuration(m.break_minutes)}</span></span>
                      <span>Idle: <span className="text-zinc-100 font-semibold">{formatDuration(m.idle_minutes)}</span></span>
                    </Card>
                  )}

                  {/* Completed sessions — collapsed by default */}
                  {completedSessions.length > 0 && (
                    <>
                      <button
                        onClick={() => setSessionsExpanded(!sessionsExpanded)}
                        className="flex items-center gap-2 text-xs text-zinc-400 hover:text-zinc-200 transition-all duration-200 font-medium"
                      >
                        {sessionsExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        {sessionsExpanded ? 'Hide' : 'Show'} {completedSessions.length} completed session{completedSessions.length !== 1 ? 's' : ''}
                      </button>
                      {sessionsExpanded && (
                        <div className="space-y-2">
                          {completedSessions.map((s, i) => renderSessionRow(s, i))}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )
            })()}
          </Card>
        </>
      )}

      {/* ── CONTROLS TAB ── */}
      {activeTab === 'controls' && (
        <Card className="space-y-4">
          <div className="flex items-center gap-2">
            <h2 className="text-zinc-100 font-semibold">Admin Override Controls</h2>
            <SectionInfoTooltip text="Owner/admin controls to start or stop this technician's active timer with mandatory manager reason for audit tracking." />
          </div>
          <div className={m.attendance_active ? 'grid grid-cols-1 lg:grid-cols-2 gap-4' : 'max-w-xl'}>
            <Card variant="subtle" padding="sm" className="space-y-3">
              <div className="text-xs text-zinc-400 flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:gap-2">
                <div className="flex items-center gap-2">
                  <StatusLED status={m.attendance_active ? 'active' : 'inactive'} />
                  Attendance:{' '}
                  <span className={m.attendance_active ? 'text-emerald-300 font-medium' : 'text-zinc-300'}>
                    {m.attendance_active ? 'Clocked In' : 'Clocked Out'}
                  </span>
                </div>
                {attendanceMetaLabel ? (
                  <span className="text-[11px] text-zinc-500">{attendanceMetaLabel}</span>
                ) : null}
              </div>
              <button
                onClick={() => attendanceToggleMutation.mutate()}
                disabled={attendanceToggleMutation.isPending}
                className={`w-full flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed ${
                  m.attendance_active 
                    ? 'bg-red-950/80 hover:bg-red-900 text-red-400 border border-red-800/50' 
                    : 'bg-emerald-950/80 hover:bg-emerald-900 text-emerald-400 border border-emerald-800/50'
                }`}
              >
                {attendanceToggleMutation.isPending ? <Spinner size="xs" /> : null}
                {m.attendance_active ? 'Clock Out Technician' : 'Clock In Technician'}
              </button>
            </Card>
            {m.attendance_active ? <Card variant="subtle" padding="sm" className="space-y-3">
              <div className="text-xs text-zinc-400 flex items-center gap-2">
                <StatusLED status={m.break_active ? 'warning' : 'inactive'} />
                Break:{' '}
                <span className={m.break_active ? 'text-amber-300 font-medium' : 'text-zinc-300'}>
                  {m.break_active ? 'On Break' : 'Not on Break'}
                </span>
              </div>
              <button
                onClick={() => breakToggleMutation.mutate()}
                disabled={breakToggleMutation.isPending}
                className={`w-full flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed ${
                  m.break_active 
                    ? 'bg-blue-950/80 hover:bg-blue-900 text-blue-400 border border-blue-800/50' 
                    : 'bg-amber-950/80 hover:bg-amber-900 text-amber-400 border border-amber-800/50'
                }`}
              >
                {breakToggleMutation.isPending ? <Spinner size="xs" /> : null}
                {m.break_active ? 'End Break' : 'Start Break'}
              </button>
            </Card> : null}
          </div>
          {m.attendance_active ? <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {!active ? (
            <div className="space-y-3">
              <Label>Session Type</Label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setSessionType('misc')}
                  className={`px-4 py-2.5 rounded-xl border text-sm font-semibold transition-all duration-200 ${
                    sessionType === 'misc'
                      ? 'bg-[var(--accent-500)]/20 border-[var(--accent-400)] text-[var(--accent-400)]'
                      : 'bg-zinc-800/60 border-zinc-600/50 text-zinc-300 hover:bg-zinc-700 hover:border-zinc-500'
                  }`}
                >
                  Misc
                </button>
                <button
                  type="button"
                  onClick={() => setSessionType('repair_order')}
                  className={`px-4 py-2.5 rounded-xl border text-sm font-semibold transition-all duration-200 ${
                    sessionType === 'repair_order'
                      ? 'bg-[var(--accent-500)]/20 border-[var(--accent-400)] text-[var(--accent-400)]'
                      : 'bg-zinc-800/60 border-zinc-600/50 text-zinc-300 hover:bg-zinc-700 hover:border-zinc-500'
                  }`}
                >
                  Repair Order
                </button>
              </div>
              {sessionType === 'repair_order' ? (
                <Input
                  value={repairOrderId}
                  onChange={(e) => setRepairOrderId(e.target.value)}
                  placeholder="Repair order UUID"
                />
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  {MISC_WORK_OPTIONS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setMiscCategory(option.value)}
                      className={`px-3 py-2 rounded-xl border text-xs font-semibold transition-all duration-200 ${
                        miscCategory === option.value
                          ? 'bg-[var(--accent-500)]/20 border-[var(--accent-400)] text-[var(--accent-400)]'
                          : 'bg-zinc-800/60 border-zinc-600/50 text-zinc-300 hover:bg-zinc-700 hover:border-zinc-500'
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              )}
              <Input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Note (optional)"
              />
              <button
                onClick={() => startTimerMutation.mutate()}
                disabled={startTimerMutation.isPending || (sessionType === 'repair_order' && !repairOrderId.trim())}
                className="w-full flex items-center justify-center gap-2 bg-[var(--accent-600)] hover:bg-[var(--accent-500)] text-white font-semibold rounded-xl px-4 py-2.5 text-sm border border-[var(--accent-400)]/50 hover:shadow-[0_0_24px_var(--accent-500)] transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-none"
              >
                {startTimerMutation.isPending ? <Spinner size="xs" /> : <PlayCircle className="w-4 h-4" />}
                Start Timer
              </button>
            </div>
            ) : (
            <div className="space-y-3">
              <Label>Stop Timer</Label>
              <div className="text-sm text-zinc-400 flex items-center gap-2">
                Current state:{' '}
                {active ? (
                  <span className="text-emerald-300 flex items-center gap-2">
                    <StatusLED status="active" />
                    active timer running
                    {m.active_session?.started_at ? (
                      <>
                        {' '}· <LiveElapsedTimer startedAt={m.active_session.started_at} className="font-mono text-emerald-200" />
                      </>
                    ) : null}
                  </span>
                ) : (
                  <span className="text-zinc-300 flex items-center gap-2">
                    <StatusLED status="inactive" />
                    idle
                  </span>
                )}
              </div>
              <button
                onClick={() => stopTimerMutation.mutate()}
                disabled={stopTimerMutation.isPending}
                className="w-full flex items-center justify-center gap-2 bg-red-950/80 hover:bg-red-900 text-red-400 font-semibold rounded-xl px-4 py-2.5 text-sm border border-red-800/50 hover:border-red-600 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {stopTimerMutation.isPending ? <Spinner size="xs" /> : <Square className="w-4 h-4" />}
                Stop Active Timer
              </button>
            </div>
            )}
          </div>
          : null}
        </Card>
      )}

      {editMode && selectedSession && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 px-4">
          <Card className="w-full max-w-md p-6 space-y-4">
            <h3 className="text-zinc-100 font-semibold text-lg">
              {editMode === 'edit' ? 'Edit Session Note' : 'Delete Session'}
            </h3>
            {editMode === 'edit' && (
              <div>
                <Label>Note</Label>
                <textarea
                  value={editNote}
                  onChange={(e) => setEditNote(e.target.value)}
                  rows={3}
                  className="w-full px-4 py-3 bg-zinc-800/60 border border-zinc-600/50 rounded-xl text-zinc-100 text-sm placeholder-zinc-500 focus:outline-none focus:border-[var(--accent-500)] focus:bg-zinc-800 focus:ring-2 focus:ring-[var(--accent-500)]/20 transition-all duration-200 hover:border-zinc-500"
                />
              </div>
            )}
            <div>
              <Label>Manager Reason</Label>
              <Input
                value={editReason}
                onChange={(e) => setEditReason(e.target.value)}
                placeholder="Manager reason (required)"
              />
            </div>
            <div className="flex justify-end gap-3 pt-4 border-t border-zinc-800/50">
              <Button
                variant="secondary"
                onClick={() => {
                  setEditMode(null)
                  setSelectedSession(null)
                }}
              >
                Cancel
              </Button>
              {editMode === 'edit' ? (
                <button
                  onClick={() => editSessionMutation.mutate()}
                  disabled={!editReason.trim() || editSessionMutation.isPending}
                  className="px-4 py-2.5 text-sm rounded-xl bg-amber-950/80 hover:bg-amber-900 text-amber-400 font-semibold border border-amber-800/50 hover:border-amber-600 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {editSessionMutation.isPending ? 'Saving...' : 'Save'}
                </button>
              ) : (
                <Button
                  variant="danger"
                  onClick={() => deleteSessionMutation.mutate()}
                  disabled={!editReason.trim() || deleteSessionMutation.isPending}
                >
                  {deleteSessionMutation.isPending ? 'Deleting...' : 'Delete'}
                </Button>
              )}
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}
