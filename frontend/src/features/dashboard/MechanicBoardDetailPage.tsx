import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { ArrowLeft, Loader2, PlayCircle, Square, Pencil, Trash2, Settings, ChevronDown, ChevronUp } from 'lucide-react'
import api from '@/lib/api'
import { MISC_WORK_OPTIONS, formatMiscCategory, formatSessionType } from '@/lib/mechanicWorkLabels'
import { formatSuggestedNextAction } from '@/lib/mechanicSuggestions'
import LiveElapsedTimer from '@/components/LiveElapsedTimer'
import SectionInfoTooltip from '@/components/SectionInfoTooltip'
import { useWebSocket } from '@/hooks/useWebSocket'
import type { AttentionPriority } from '@/types'
import { ATTENTION_REASON_LABELS } from '@/types'

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

const computeSessionDurationMinutes = (s: SessionRow): number => {
  const start = new Date(s.started_at).getTime()
  const end = s.ended_at ? new Date(s.ended_at).getTime() : Date.now()
  return Math.max(0, (end - start) / 60000)
}

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
  const [startReason, setStartReason] = useState('')
  const [stopReason, setStopReason] = useState('')
  const [attendanceReason, setAttendanceReason] = useState('')
  const [breakReason, setBreakReason] = useState('')

  const [activeTab, setActiveTab] = useState<DetailTab>('overview')
  const [sessionsExpanded, setSessionsExpanded] = useState(false)

  const [editMode, setEditMode] = useState<EditMode>(null)
  const [selectedSession, setSelectedSession] = useState<SessionRow | null>(null)
  const [editReason, setEditReason] = useState('')
  const [editNote, setEditNote] = useState('')

  const { data, isLoading, isError } = useQuery<BoardDetailResponse>({
    queryKey: ['mechanic-board-detail', mechanicId],
    queryFn: async () => {
      const response = await api.get(`/dashboard/mechanics/${mechanicId}/board`)
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
        manager_reason: startReason,
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
      setStartReason('')
      setNote('')
      setRepairOrderId('')
      refreshBoard()
    },
    onError: (error: any) => toast.error(error?.response?.data?.detail || 'Failed to start timer'),
  })

  const stopTimerMutation = useMutation({
    mutationFn: async () => {
      if (!mechanicId) throw new Error('Missing mechanic id')
      await api.post(`/dashboard/mechanics/${mechanicId}/timer/stop`, { manager_reason: stopReason })
    },
    onSuccess: () => {
      toast.success('Timer stopped')
      setStopReason('')
      refreshBoard()
    },
    onError: (error: any) => toast.error(error?.response?.data?.detail || 'Failed to stop timer'),
  })

  const attendanceToggleMutation = useMutation({
    mutationFn: async () => {
      if (!mechanicId) throw new Error('Missing mechanic id')
      if (data?.mechanic.attendance_active) {
        await api.post(`/dashboard/mechanics/${mechanicId}/attendance/clock-out`, {
          manager_reason: attendanceReason,
        })
        return
      }
      await api.post(`/dashboard/mechanics/${mechanicId}/attendance/clock-in`, {
        manager_reason: attendanceReason,
      })
    },
    onSuccess: () => {
      toast.success(data?.mechanic.attendance_active ? 'Clocked out' : 'Clocked in')
      setAttendanceReason('')
      refreshBoard()
    },
    onError: (error: any) => toast.error(error?.response?.data?.detail || 'Failed to update attendance'),
  })

  const breakToggleMutation = useMutation({
    mutationFn: async () => {
      if (!mechanicId) throw new Error('Missing mechanic id')
      if (data?.mechanic.break_active) {
        await api.post(`/dashboard/mechanics/${mechanicId}/break/end`, {
          manager_reason: breakReason,
        })
        return
      }
      await api.post(`/dashboard/mechanics/${mechanicId}/break/start`, {
        manager_reason: breakReason,
      })
    },
    onSuccess: () => {
      toast.success(data?.mechanic.break_active ? 'Break ended' : 'Break started')
      setBreakReason('')
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
        <Loader2 className="w-8 h-8 animate-spin text-amber-400" />
      </div>
    )
  }

  if (isError || !data) {
    return <div className="text-red-400">Failed to load mechanic board detail.</div>
  }

  const m = data.mechanic
  const trendRows = m.trend_7_days || []
  const formatTrendDate = (isoDate: string) => {
    const parsed = new Date(`${isoDate}T00:00:00`)
    if (Number.isNaN(parsed.getTime())) return isoDate
    return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  }
  const openRecommendedOrder = () => {
    if (!m.recommended_order_id) return
    navigate(`/dashboard/repair-orders?selected=${m.recommended_order_id}`)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/dashboard/mechanics')} className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-gray-300">
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div>
          <h1 className="text-xl font-semibold text-white">{m.mechanic_name}</h1>
          <p className="text-xs text-gray-400">{m.date} · {m.timezone}</p>
        </div>
      </div>

      {m.attention_priority !== 'green' && m.attention_reasons.length > 0 ? (
        <div className={`rounded-lg px-3 py-2 text-sm font-medium ${m.attention_priority === 'red' ? 'bg-rose-500/15 border border-rose-500/30 text-rose-200' : 'bg-amber-500/15 border border-amber-400/30 text-amber-200'}`}>
          {m.attention_reasons.map((r) => ATTENTION_REASON_LABELS[r] || r).join(' · ')}
        </div>
      ) : null}

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-white/10 pb-px">
        <button
          onClick={() => setActiveTab('overview')}
          className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
            activeTab === 'overview'
              ? 'bg-white/10 text-white border border-white/10 border-b-transparent -mb-px'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          Overview
        </button>
        <button
          onClick={() => setActiveTab('controls')}
          className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors flex items-center gap-1.5 ${
            activeTab === 'controls'
              ? 'bg-white/10 text-white border border-white/10 border-b-transparent -mb-px'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          <Settings className="w-3.5 h-3.5" />
          Admin Controls
        </button>
      </div>

      {/* ── OVERVIEW TAB ── */}
      {activeTab === 'overview' && (
        <>
          <div className="bg-white/5 border border-white/10 rounded-xl p-4 space-y-3">
            <div className="flex items-center gap-2">
              <h2 className="text-white font-medium">Today Summary</h2>
              <SectionInfoTooltip text="At-a-glance performance for this mechanic today: tracked hours, work mix, utilization, efficiency, and whether a timer is currently running." />
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-8 gap-3 text-sm">
              <div className="text-gray-400">Tracked<br /><span className="text-white font-semibold">{(m.tracked_minutes / 60).toFixed(1)}h</span></div>
              <div className="text-gray-400">RO<br /><span className="text-white font-semibold">{(m.ro_minutes / 60).toFixed(1)}h</span></div>
              <div className="text-gray-400">Misc<br /><span className="text-white font-semibold">{(m.misc_minutes / 60).toFixed(1)}h</span></div>
              <div className="text-gray-400">Break<br /><span className="text-white font-semibold">{(m.break_minutes / 60).toFixed(1)}h</span></div>
              <div className="text-gray-400">Idle<br /><span className="text-white font-semibold">{(m.idle_minutes / 60).toFixed(1)}h</span></div>
              <div className="text-gray-400">Utilization<br /><span className="text-amber-300 font-semibold">{m.utilization_percent.toFixed(1)}%</span></div>
              <div className="text-gray-400">Efficiency<br /><span className="text-white font-semibold">{m.efficiency_percent == null ? 'n/a' : `${m.efficiency_percent.toFixed(1)}%`}</span></div>
              <div className="text-gray-400">Core Gap<br /><span className="text-white font-semibold">{(m.core_gap_minutes / 60).toFixed(1)}h</span></div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
              <div className="rounded-lg border border-cyan-400/30 bg-cyan-500/10 px-2.5 py-2 text-cyan-100">
                Core Countdown Remaining: <span className="font-semibold">{(m.core_countdown_remaining_minutes / 60).toFixed(1)}h</span>
              </div>
              <div className="rounded-lg border border-white/10 bg-white/5 px-2.5 py-2 text-gray-200">
                Tracked Progress: <span className="font-semibold">{(m.tracked_minutes / 60).toFixed(1)}h / {(m.core_target_minutes / 60).toFixed(1)}h</span>
              </div>
              <div className="rounded-lg border border-white/10 bg-white/5 px-2.5 py-2 text-gray-200">
                Work Coverage: <span className="font-semibold">{formatCoverageLabel(m.work_coverage_percent, m.attendance_minutes)}</span>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
              <div className="rounded-lg border border-white/10 bg-white/5 px-2.5 py-2 text-gray-300">
                Attendance:{' '}
                <span className={m.attendance_active ? 'text-emerald-300' : 'text-gray-200'}>
                  {m.attendance_active ? 'Clocked In' : 'Clocked Out'}
                </span>
              </div>
              <div className="rounded-lg border border-white/10 bg-white/5 px-2.5 py-2 text-gray-300">
                Break:{' '}
                <span className={m.break_active ? 'text-amber-300' : 'text-gray-200'}>
                  {m.break_active ? 'On Break' : 'No Break'}
                </span>
              </div>
              <div className="rounded-lg border border-white/10 bg-white/5 px-2.5 py-2 text-gray-300">
                Flex: <span className="text-white">{m.flex_used_minutes}m / {m.flex_budget_minutes}m</span>
                {m.flex_overrun_minutes > 0 ? <span className="text-rose-300"> · +{m.flex_overrun_minutes}m</span> : null}
              </div>
            </div>
            <div className="text-sm text-gray-400">
              Live timer:{' '}
              {m.active_session?.started_at ? (
                <span className="text-emerald-300">
                  {formatSessionType(m.active_session.session_type)}
                  {m.active_session.session_type === 'misc' && m.active_session.misc_category
                    ? ` (${formatMiscCategory(m.active_session.misc_category)})`
                    : ''}
                  {' '}· <LiveElapsedTimer startedAt={m.active_session.started_at} className="font-mono text-emerald-200" />
                </span>
              ) : (
                <span className="text-gray-300">idle</span>
              )}
            </div>
            <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-2">
              <div className="text-xs text-gray-400">
                Suggested next action:{' '}
                <span className="text-gray-200">{formatSuggestedNextAction(m.suggested_next_action)}</span>
              </div>
              <div className="mt-1 text-[11px] text-gray-500">
                Ready assigned: <span className="text-gray-200">{m.assigned_ready_orders_count}</span>
                {' · '}
                Untimed in-progress: <span className="text-gray-200">{m.untimed_in_progress_orders_count}</span>
                {m.recommended_order_number ? (
                  <>
                    {' · '}
                    Recommended RO: <span className="text-gray-200">{m.recommended_order_number}</span>
                  </>
                ) : null}
              </div>
              <div className="mt-2 flex items-center gap-2">
                {m.recommended_order_id ? (
                  <button
                    onClick={openRecommendedOrder}
                    className="px-2.5 py-1.5 rounded bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold"
                  >
                    Open Recommended RO
                  </button>
                ) : null}
                {m.suggested_next_action === 'stop_misc_pick_ro' && m.active_session?.session_type === 'misc' ? (
                  <button
                    onClick={() => setStopReason('Stopping misc to pick up assigned repair order')}
                    className="px-2.5 py-1.5 rounded bg-rose-600/80 hover:bg-rose-600 text-white text-xs font-semibold"
                  >
                    Prefill Stop Reason
                  </button>
                ) : null}
              </div>
            </div>
            {m.held_orders_count > 0 ? (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
                <div className="text-xs text-amber-200 font-medium">
                  On-hold repair orders ({m.held_orders_count})
                </div>
                <div className="mt-1 space-y-1">
                  {(m.held_orders || []).map((order) => (
                    <div key={order.id} className="text-xs text-amber-100">
                      {order.order_number} · {formatHoldReason(order.hold_reason)}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>

          <div className="bg-white/5 border border-white/10 rounded-xl p-4 space-y-3">
            <div className="flex items-center gap-2">
              <h2 className="text-white font-medium">7-Day Trend</h2>
              <SectionInfoTooltip text="Daily utilization and efficiency trend for the last 7 days. Use this to spot consistency issues and coaching opportunities." />
            </div>
            {!trendRows.length ? (
              <p className="text-sm text-gray-400">No trend data yet.</p>
            ) : (
              <>
                <div className="space-y-2 md:hidden">
                  {trendRows.map((row) => (
                    <div key={row.date} className="rounded-lg border border-white/10 bg-white/5 p-2">
                      <div className="flex items-center justify-between text-xs text-gray-400">
                        <span>{row.date}</span>
                        <span>{row.utilization_percent.toFixed(1)}%</span>
                      </div>
                      <div className="mt-1 h-2 bg-white/10 rounded-full overflow-hidden">
                        <div className="h-2 bg-amber-400 rounded-full" style={{ width: `${Math.min(row.utilization_percent, 100)}%` }} />
                      </div>
                      <div className="mt-1 text-[11px] text-gray-500">
                        Tracked {(row.tracked_minutes / 60).toFixed(1)}h · Efficiency {row.efficiency_percent == null ? 'n/a' : `${row.efficiency_percent.toFixed(1)}%`}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="hidden md:grid md:grid-cols-7 md:gap-2">
                  {trendRows.map((row) => (
                    <div key={row.date} className="rounded-lg border border-white/10 bg-white/5 p-2">
                      <div className="flex items-center justify-between text-[11px] text-gray-400">
                        <span>{formatTrendDate(row.date)}</span>
                        <span>{row.utilization_percent.toFixed(0)}%</span>
                      </div>
                      <div className="mt-1 h-2 bg-white/10 rounded-full overflow-hidden">
                        <div className="h-2 bg-amber-400 rounded-full" style={{ width: `${Math.min(row.utilization_percent, 100)}%` }} />
                      </div>
                      <div className="mt-1 text-[10px] text-gray-500 leading-tight">
                        {(row.tracked_minutes / 60).toFixed(1)}h · {row.efficiency_percent == null ? 'n/a' : `${row.efficiency_percent.toFixed(0)}%`}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          {/* Today Sessions — active session prominent, history collapsed */}
          <div className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <h2 className="text-white font-medium">Today Sessions</h2>
              <SectionInfoTooltip text="Chronological record of all timer sessions for the selected day, including active, stopped, edited, and deletable entries." />
            </div>

            {!data.today_sessions.length ? (
              <p className="text-gray-400 text-sm">No sessions recorded for this day.</p>
            ) : (() => {
              const activeSession = data.today_sessions.find((s) => !s.ended_at)
              const completedSessions = data.today_sessions.filter((s) => !!s.ended_at)

              const renderSessionRow = (s: SessionRow) => {
                const durationMin = computeSessionDurationMinutes(s)
                return (
                  <div key={s.id} className="rounded-lg border border-white/10 bg-white/5 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-white text-sm font-medium">
                            {formatSessionType(s.session_type)}
                            {s.misc_category ? ` · ${formatMiscCategory(s.misc_category)}` : ''}
                          </span>
                          {s.ended_at ? (
                            <span className="text-xs font-semibold text-amber-300 bg-amber-500/10 px-1.5 py-0.5 rounded">
                              {formatDuration(durationMin)}
                            </span>
                          ) : null}
                        </div>
                        <div className="text-xs text-gray-400 mt-0.5">
                          {new Date(s.started_at).toLocaleTimeString()} – {s.ended_at ? new Date(s.ended_at).toLocaleTimeString() : 'now'}
                        </div>
                        {!s.ended_at ? (
                          <div className="text-xs text-emerald-300 mt-1">
                            Running: <LiveElapsedTimer startedAt={s.started_at} className="font-mono text-emerald-200" />
                          </div>
                        ) : null}
                        {s.note && <div className="text-xs text-gray-300 mt-1 truncate">{s.note}</div>}
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          onClick={() => {
                            setSelectedSession(s)
                            setEditNote(s.note || '')
                            setEditReason('')
                            setEditMode('edit')
                          }}
                          className="p-1.5 rounded bg-amber-500/20 text-amber-300 hover:bg-amber-500/30"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => {
                            setSelectedSession(s)
                            setEditReason('')
                            setEditMode('delete')
                          }}
                          className="p-1.5 rounded bg-rose-500/20 text-rose-300 hover:bg-rose-500/30"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  </div>
                )
              }

              return (
                <div className="space-y-2">
                  {/* Active session — always visible */}
                  {activeSession ? renderSessionRow(activeSession) : (
                    <div className="text-sm text-gray-400">No active timer</div>
                  )}

                  {/* Summary footer — always visible */}
                  {sessionTotals && (
                    <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-300">
                      <span>Total RO: <span className="text-white font-semibold">{formatDuration(sessionTotals.repair_order || 0)}</span></span>
                      <span>Total Misc: <span className="text-white font-semibold">{formatDuration(sessionTotals.misc || 0)}</span></span>
                      <span>Break: <span className="text-white font-semibold">{formatDuration(m.break_minutes)}</span></span>
                      <span>Idle: <span className="text-white font-semibold">{formatDuration(m.idle_minutes)}</span></span>
                    </div>
                  )}

                  {/* Completed sessions — collapsed by default */}
                  {completedSessions.length > 0 && (
                    <>
                      <button
                        onClick={() => setSessionsExpanded(!sessionsExpanded)}
                        className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-200 transition-colors"
                      >
                        {sessionsExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                        {sessionsExpanded ? 'Hide' : 'Show'} {completedSessions.length} completed session{completedSessions.length !== 1 ? 's' : ''}
                      </button>
                      {sessionsExpanded && (
                        <div className="space-y-2">
                          {completedSessions.map(renderSessionRow)}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )
            })()}
          </div>
        </>
      )}

      {/* ── CONTROLS TAB ── */}
      {activeTab === 'controls' && (
        <div className="bg-white/5 border border-white/10 rounded-xl p-4 space-y-3">
          <div className="flex items-center gap-2">
            <h2 className="text-white font-medium">Admin Override Controls</h2>
            <SectionInfoTooltip text="Owner/admin controls to start or stop this mechanic's active timer with mandatory manager reason for audit tracking." />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 space-y-2">
              <div className="text-xs text-gray-400">
                Attendance:{' '}
                <span className={m.attendance_active ? 'text-emerald-300' : 'text-gray-300'}>
                  {m.attendance_active ? 'Clocked In' : 'Clocked Out'}
                </span>
              </div>
              <input
                value={attendanceReason}
                onChange={(e) => setAttendanceReason(e.target.value)}
                placeholder="Manager reason (required)"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500"
              />
              <button
                onClick={() => attendanceToggleMutation.mutate()}
                disabled={!attendanceReason.trim() || attendanceToggleMutation.isPending}
                className={`w-full flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-white disabled:bg-gray-600 ${
                  m.attendance_active ? 'bg-rose-600 hover:bg-rose-700' : 'bg-emerald-600 hover:bg-emerald-700'
                }`}
              >
                {attendanceToggleMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                {m.attendance_active ? 'Clock Out Mechanic' : 'Clock In Mechanic'}
              </button>
            </div>
            <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 space-y-2">
              <div className="text-xs text-gray-400">
                Break:{' '}
                <span className={m.break_active ? 'text-amber-300' : 'text-gray-300'}>
                  {m.break_active ? 'On Break' : 'Not on Break'}
                </span>
              </div>
              <input
                value={breakReason}
                onChange={(e) => setBreakReason(e.target.value)}
                placeholder="Manager reason (required)"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500"
              />
              <button
                onClick={() => breakToggleMutation.mutate()}
                disabled={!breakReason.trim() || breakToggleMutation.isPending || !m.attendance_active}
                className={`w-full flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-white disabled:bg-gray-600 ${
                  m.break_active ? 'bg-blue-600 hover:bg-blue-700' : 'bg-amber-600 hover:bg-amber-700'
                }`}
              >
                {breakToggleMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                {m.break_active ? 'End Break' : 'Start Break'}
              </button>
            </div>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setSessionType('misc')}
                  className={`px-3 py-2 rounded-lg border text-sm font-medium transition-colors ${
                    sessionType === 'misc'
                      ? 'bg-amber-500/20 border-amber-400 text-amber-200'
                      : 'bg-white/5 border-white/10 text-gray-300 hover:bg-white/10'
                  }`}
                >
                  Misc
                </button>
                <button
                  type="button"
                  onClick={() => setSessionType('repair_order')}
                  className={`px-3 py-2 rounded-lg border text-sm font-medium transition-colors ${
                    sessionType === 'repair_order'
                      ? 'bg-amber-500/20 border-amber-400 text-amber-200'
                      : 'bg-white/5 border-white/10 text-gray-300 hover:bg-white/10'
                  }`}
                >
                  Repair Order
                </button>
              </div>
              {sessionType === 'repair_order' ? (
                <input
                  value={repairOrderId}
                  onChange={(e) => setRepairOrderId(e.target.value)}
                  placeholder="Repair order UUID"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500"
                />
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  {MISC_WORK_OPTIONS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setMiscCategory(option.value)}
                      className={`px-3 py-2 rounded-lg border text-sm font-medium transition-colors ${
                        miscCategory === option.value
                          ? 'bg-amber-500/20 border-amber-400 text-amber-200'
                          : 'bg-white/5 border-white/10 text-gray-300 hover:bg-white/10'
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              )}
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Note (optional)"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500"
              />
              <input
                value={startReason}
                onChange={(e) => setStartReason(e.target.value)}
                placeholder="Manager reason (required)"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500"
              />
              <button
                onClick={() => startTimerMutation.mutate()}
                disabled={!startReason.trim() || startTimerMutation.isPending || (sessionType === 'repair_order' && !repairOrderId.trim())}
                className="w-full flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-600 text-white rounded-lg px-3 py-2"
              >
                {startTimerMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlayCircle className="w-4 h-4" />}
                Start Timer
              </button>
            </div>
            <div className="space-y-2">
              <div className="text-sm text-gray-400">
                Current state:{' '}
                {active ? (
                  <span className="text-green-300">
                    active timer running
                    {m.active_session?.started_at ? (
                      <>
                        {' '}· <LiveElapsedTimer startedAt={m.active_session.started_at} className="font-mono text-green-200" />
                      </>
                    ) : null}
                  </span>
                ) : (
                  <span className="text-gray-300">idle</span>
                )}
              </div>
              <input
                value={stopReason}
                onChange={(e) => setStopReason(e.target.value)}
                placeholder="Manager reason (required)"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500"
              />
              <button
                onClick={() => stopTimerMutation.mutate()}
                disabled={!stopReason.trim() || stopTimerMutation.isPending}
                className="w-full flex items-center justify-center gap-2 bg-rose-600 hover:bg-rose-700 disabled:bg-gray-600 text-white rounded-lg px-3 py-2"
              >
                {stopTimerMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Square className="w-4 h-4" />}
                Stop Active Timer
              </button>
            </div>
          </div>
        </div>
      )}

      {editMode && selectedSession && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 px-4">
          <div className="w-full max-w-md bg-gray-900 border border-white/10 rounded-xl p-4 space-y-3">
            <h3 className="text-white font-medium">
              {editMode === 'edit' ? 'Edit Session Note' : 'Delete Session'}
            </h3>
            {editMode === 'edit' && (
              <textarea
                value={editNote}
                onChange={(e) => setEditNote(e.target.value)}
                rows={3}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white"
              />
            )}
            <input
              value={editReason}
              onChange={(e) => setEditReason(e.target.value)}
              placeholder="Manager reason (required)"
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500"
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => {
                  setEditMode(null)
                  setSelectedSession(null)
                }}
                className="px-3 py-2 rounded-lg bg-white/10 text-gray-200"
              >
                Cancel
              </button>
              {editMode === 'edit' ? (
                <button
                  onClick={() => editSessionMutation.mutate()}
                  disabled={!editReason.trim() || editSessionMutation.isPending}
                  className="px-3 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 text-white"
                >
                  {editSessionMutation.isPending ? 'Saving...' : 'Save'}
                </button>
              ) : (
                <button
                  onClick={() => deleteSessionMutation.mutate()}
                  disabled={!editReason.trim() || deleteSessionMutation.isPending}
                  className="px-3 py-2 rounded-lg bg-rose-600 hover:bg-rose-700 disabled:bg-gray-600 text-white"
                >
                  {deleteSessionMutation.isPending ? 'Deleting...' : 'Delete'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
