import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronRight, Users } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '@/lib/api'
import LiveElapsedTimer from '@/components/LiveElapsedTimer'
import SectionInfoTooltip from '@/components/SectionInfoTooltip'
import { formatMiscCategory, formatSessionType } from '@/lib/mechanicWorkLabels'
import { formatSuggestedNextAction } from '@/lib/mechanicSuggestions'
import { useWebSocket } from '@/hooks/useWebSocket'
import type { AttentionPriority } from '@/types'
import { ATTENTION_REASON_LABELS } from '@/types'
import { 
  Card, Input, Badge, StatusLED, Header, Spinner, staggeredReveal 
} from '@/components/ui'

interface MechanicBoardItem {
  mechanic_id: string
  mechanic_name: string
  core_target_minutes: number
  tracked_minutes: number
  ro_minutes: number
  misc_minutes: number
  overtime_minutes: number
  utilization_percent: number
  efficiency_percent: number | null
  attendance_active: boolean
  break_active: boolean
  attendance_minutes: number
  idle_minutes: number
  flex_budget_minutes: number
  flex_used_minutes: number
  flex_overrun_minutes: number
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
  trend_7_days: Array<{
    date: string
    tracked_minutes: number
    utilization_percent: number
    efficiency_percent: number | null
  }>
  active_session: {
    id: string
    session_type: string
    repair_order_id: string | null
    misc_category: string | null
    started_at: string | null
  } | null
}

interface TeamBoardResponse {
  date: string
  timezone: string
  team_core_target_minutes: number
  team_tracked_minutes: number
  team_overtime_minutes: number
  team_utilization_percent: number
  mechanics: MechanicBoardItem[]
}

const toHours = (minutes: number) => (minutes / 60).toFixed(1)

const PRIORITY_ORDER: Record<AttentionPriority, number> = { red: 0, yellow: 1, green: 2 }
const PRIORITY_BORDER: Record<AttentionPriority, string> = {
  red: 'border-l-red-500',
  yellow: 'border-l-amber-400',
  green: 'border-l-emerald-500',
}
const PRIORITY_LED: Record<AttentionPriority, 'error' | 'warning' | 'active'> = {
  red: 'error',
  yellow: 'warning',
  green: 'active',
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

const getMechanicStatusBadge = (mechanic: MechanicBoardItem) => {
  if (mechanic.active_session) {
    return { variant: 'success' as const, label: 'Active Job', className: '' }
  }
  if (mechanic.break_active) {
    return { variant: 'warning' as const, label: 'On Break', className: '' }
  }
  if (mechanic.attendance_active) {
    return { variant: 'default' as const, label: 'Clocked In', className: '' }
  }
  return { variant: 'default' as const, label: 'Clocked Out', className: 'opacity-50' }
}

function sortByAttention(mechanics: MechanicBoardItem[]): MechanicBoardItem[] {
  return [...mechanics].sort((a, b) => {
    const pa = PRIORITY_ORDER[a.attention_priority] ?? 2
    const pb = PRIORITY_ORDER[b.attention_priority] ?? 2
    if (pa !== pb) return pa - pb
    return a.core_countdown_remaining_minutes - b.core_countdown_remaining_minutes
  })
}

export default function MechanicsBoardPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  useWebSocket()
  const [stopTarget, setStopTarget] = useState<{ mechanicId: string; mechanicName: string } | null>(null)
  const [stopReason, setStopReason] = useState('')
  const stopReasonInputRef = useRef<HTMLInputElement | null>(null)
  const cancelStopButtonRef = useRef<HTMLButtonElement | null>(null)
  const confirmStopButtonRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    if (!stopTarget) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    stopReasonInputRef.current?.focus()
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [stopTarget])

  const { data, isLoading, isError } = useQuery<TeamBoardResponse>({
    queryKey: ['mechanic-board-team'],
    queryFn: async () => {
      const response = await api.get('/dashboard/mechanics/board')
      return response.data
    },
    refetchOnWindowFocus: true,
  })

  const stopMiscMutation = useMutation({
    mutationFn: async ({ mechanicId, managerReason }: { mechanicId: string; managerReason: string }) => {
      await api.post(`/dashboard/mechanics/${mechanicId}/timer/stop`, {
        manager_reason: managerReason,
      })
    },
    onSuccess: () => {
      toast.success('Misc timer stopped')
      setStopTarget(null)
      setStopReason('')
      queryClient.invalidateQueries({ queryKey: ['mechanic-board-team'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-board-detail'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
    },
    onError: (error: any) => toast.error(error?.response?.data?.detail || 'Failed to stop misc timer'),
  })

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
        <p className="text-red-400">Failed to load technicians board.</p>
      </Card>
    )
  }

  const sorted = sortByAttention(data.mechanics)
  const redCount = sorted.filter((m) => m.attention_priority === 'red').length
  const yellowCount = sorted.filter((m) => m.attention_priority === 'yellow').length
  const greenCount = sorted.filter((m) => m.attention_priority === 'green').length

  return (
    <div className="space-y-4">
      {/* Header */}
      <Header
        title="Technician Board"
        subtitle={`${data.date} · ${data.timezone}`}
        icon={<Users className="w-5 h-5 text-[var(--accent-400)]" />}
        actions={
          <div className="flex items-center gap-3 text-sm">
            <span className="text-zinc-300">
              Tracked: <strong className="text-zinc-100">{toHours(data.team_tracked_minutes)}h</strong> / {toHours(data.team_core_target_minutes)}h
            </span>
            <Badge variant="warning">
              Utilization: {data.team_utilization_percent.toFixed(1)}%
            </Badge>
          </div>
        }
      />
      <SectionInfoTooltip text="Team-wide mechanic monitoring. Cards are sorted by attention priority — red needs action now, yellow worth checking, green on track." />

      {/* Attention summary banner */}
      {sorted.length > 0 ? (
        <div className="flex items-center gap-4 px-1 text-xs">
          {redCount > 0 ? (
            <span className="flex items-center gap-2 text-red-300 font-medium">
              <StatusLED status="error" />
              {redCount} need{redCount === 1 ? 's' : ''} attention
            </span>
          ) : null}
          {yellowCount > 0 ? (
            <span className="flex items-center gap-2 text-amber-300 font-medium">
              <StatusLED status="warning" />
              {yellowCount} worth checking
            </span>
          ) : null}
          <span className="flex items-center gap-2 text-emerald-300">
            <StatusLED status="active" />
            {greenCount} on track
          </span>
        </div>
      ) : null}

      {/* Mechanic cards */}
      {!sorted.length ? (
        <Card className="p-6">
          <p className="text-zinc-400">No active technicians.</p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {sorted.map((m, index) => {
            const mechanicDetailPath = `/dashboard/mechanics/${m.mechanic_id}`
            const statusBadge = getMechanicStatusBadge(m)
            const corePercent = m.core_target_minutes > 0
              ? Math.min(((m.core_target_minutes - m.core_countdown_remaining_minutes) / m.core_target_minutes) * 100, 100)
              : 0
            const firstReason = m.attention_reasons[0]
              ? ATTENTION_REASON_LABELS[m.attention_reasons[0]] || m.attention_reasons[0]
              : null

            return (
              <Card
                key={m.mechanic_id}
                hover
                padding="none"
                className={`p-4 cursor-pointer border-l-4 ${PRIORITY_BORDER[m.attention_priority]} animate-[fadeIn_0.3s_ease-out_forwards] opacity-0`}
                style={staggeredReveal(index)}
              >
                <div
                  role="button"
                  tabIndex={0}
                  aria-label={`Open technician board for ${m.mechanic_name}`}
                  onClick={() => navigate(mechanicDetailPath)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      navigate(mechanicDetailPath)
                    }
                  }}
                >
                  {/* Row 1: Name + status + chevron */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <StatusLED status={PRIORITY_LED[m.attention_priority]} />
                      <h2 className="text-zinc-100 font-semibold">{m.mechanic_name}</h2>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant={statusBadge.variant} className={statusBadge.className}>{statusBadge.label}</Badge>
                      <ChevronRight className="w-4 h-4 text-zinc-600" />
                    </div>
                  </div>

                  {/* Row 2: Attention reason (if red/yellow) */}
                  {firstReason && m.attention_priority !== 'green' ? (
                    <div className={`mt-2 text-xs font-medium ${m.attention_priority === 'red' ? 'text-red-300' : 'text-amber-300'}`}>
                      {firstReason}
                      {m.attention_reasons.length > 1 ? (
                        <span className="text-zinc-500 font-normal"> +{m.attention_reasons.length - 1} more</span>
                      ) : null}
                    </div>
                  ) : null}

                  {/* Row 3: Suggested action */}
                  <div className="mt-3 flex items-center justify-between gap-2">
                    <div className="text-xs text-zinc-400 truncate">
                      Suggested: <span className="text-zinc-200">{formatSuggestedNextAction(m.suggested_next_action)}</span>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {m.active_session?.session_type === 'misc' ? (
                        <button
                          onClick={(event) => {
                            event.stopPropagation()
                            setStopTarget({ mechanicId: m.mechanic_id, mechanicName: m.mechanic_name })
                          }}
                          className="px-3 py-1.5 text-xs rounded-lg bg-red-950/80 hover:bg-red-900 text-red-400 font-semibold border border-red-800/50 hover:border-red-600 transition-all duration-200"
                        >
                          Stop Misc
                        </button>
                      ) : null}
                      {(m.suggested_next_action === 'continue_ro' || m.suggested_next_action === 'stop_misc_pick_ro' || m.suggested_next_action === 'start_assigned_ro') ? (
                        <button
                          onClick={(event) => {
                            event.stopPropagation()
                            navigate(mechanicDetailPath)
                          }}
                          className="px-3 py-1.5 text-xs rounded-lg bg-[var(--accent-600)] hover:bg-[var(--accent-500)] text-white font-semibold border border-[var(--accent-400)]/50 hover:shadow-[0_0_24px_var(--accent-500)] transition-all duration-200"
                        >
                          Go to Detail
                        </button>
                      ) : null}
                    </div>
                  </div>

                  {/* Row 4: Core remaining bar */}
                  <div className="mt-4">
                    <div className="flex items-center justify-between text-xs text-zinc-400 mb-1.5">
                      <span>Core Remaining</span>
                      <span className="text-zinc-100 font-medium">{toHours(m.core_countdown_remaining_minutes)}h left</span>
                    </div>
                    <div className="h-2 bg-zinc-800/60 rounded-full overflow-hidden">
                      <div className="h-2 bg-[var(--accent-500)] rounded-full transition-all" style={{ width: `${corePercent}%` }} />
                    </div>
                  </div>

                  {/* Row 5: Summary line */}
                  <div className="mt-3 text-xs text-zinc-400">
                    Tracked {toHours(m.tracked_minutes)}h · RO {toHours(m.ro_minutes)}h · Misc {toHours(m.misc_minutes)}h
                  </div>

                  {m.held_orders_count > 0 ? (
                    <div className="mt-2 text-xs text-amber-300">
                      On hold: <span className="text-amber-200">{m.held_orders?.[0]?.order_number || `${m.held_orders_count} job(s)`}</span>
                      {m.held_orders?.[0]?.hold_reason ? (
                        <span className="text-amber-100"> · {formatHoldReason(m.held_orders[0].hold_reason)}</span>
                      ) : null}
                      {m.held_orders_count > 1 ? (
                        <span className="text-amber-200"> · +{m.held_orders_count - 1} more</span>
                      ) : null}
                    </div>
                  ) : null}

                  {/* Row 6: Active timer (only if running) */}
                  {m.active_session?.started_at ? (
                    <div className="mt-3 text-xs text-emerald-300 flex items-center gap-2">
                      <StatusLED status="active" />
                      <LiveElapsedTimer startedAt={m.active_session.started_at} className="font-mono text-emerald-200" />
                      <span className="text-zinc-500">·</span>
                      <span className="text-zinc-300">
                        {formatSessionType(m.active_session.session_type)}
                        {m.active_session.session_type === 'misc' && m.active_session.misc_category
                          ? ` (${formatMiscCategory(m.active_session.misc_category)})`
                          : ''}
                      </span>
                    </div>
                  ) : null}
                </div>
              </Card>
            )
          })}
        </div>
      )}

      {/* Stop Misc Modal */}
      {stopTarget ? (
        <div
          className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 px-4"
          tabIndex={-1}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              setStopTarget(null)
              setStopReason('')
              return
            }
            if (event.key === 'Tab') {
              const focusable = [
                stopReasonInputRef.current,
                cancelStopButtonRef.current,
                confirmStopButtonRef.current,
              ].filter(Boolean) as Array<HTMLInputElement | HTMLButtonElement>
              if (!focusable.length) return
              const activeElement = document.activeElement as HTMLInputElement | HTMLButtonElement | null
              const currentIndex = activeElement ? focusable.indexOf(activeElement) : -1
              const isShift = event.shiftKey
              const nextIndex = currentIndex < 0
                ? 0
                : isShift
                  ? (currentIndex <= 0 ? focusable.length - 1 : currentIndex - 1)
                  : (currentIndex >= focusable.length - 1 ? 0 : currentIndex + 1)
              event.preventDefault()
              focusable[nextIndex]?.focus()
            }
          }}
        >
          <Card className="w-full max-w-md p-6 space-y-4">
            <h3 className="text-zinc-100 font-semibold text-lg">Stop Misc Timer</h3>
            <p className="text-sm text-zinc-400">
              Provide manager reason to stop misc timer for <span className="text-zinc-100 font-medium">{stopTarget.mechanicName}</span>.
            </p>
            <Input
              ref={stopReasonInputRef}
              value={stopReason}
              onChange={(event) => setStopReason(event.target.value)}
              placeholder="Manager reason (required)"
            />
            <div className="flex justify-end gap-3 pt-4 border-t border-zinc-800/50">
              <button
                ref={cancelStopButtonRef}
                onClick={() => {
                  setStopTarget(null)
                  setStopReason('')
                }}
                className="px-4 py-2.5 text-sm rounded-xl bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 font-semibold border border-zinc-600/50 hover:border-zinc-500 transition-all duration-200"
              >
                Cancel
              </button>
              <button
                ref={confirmStopButtonRef}
                onClick={() => {
                  if (!stopTarget || !stopReason.trim()) return
                  stopMiscMutation.mutate({ mechanicId: stopTarget.mechanicId, managerReason: stopReason.trim() })
                }}
                disabled={!stopReason.trim() || stopMiscMutation.isPending}
                className="px-4 py-2.5 text-sm rounded-xl bg-red-950/80 hover:bg-red-900 text-red-400 font-semibold border border-red-800/50 hover:border-red-600 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {stopMiscMutation.isPending ? 'Stopping...' : 'Stop Misc'}
              </button>
            </div>
          </Card>
        </div>
      ) : null}
    </div>
  )
}
