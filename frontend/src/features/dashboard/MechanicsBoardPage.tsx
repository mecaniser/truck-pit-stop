import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Loader2, Users, Clock3 } from 'lucide-react'
import api from '@/lib/api'
import LiveElapsedTimer from '@/components/LiveElapsedTimer'
import SectionInfoTooltip from '@/components/SectionInfoTooltip'
import { formatMiscCategory, formatSessionType } from '@/lib/mechanicWorkLabels'

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
  idle_minutes: number
  flex_budget_minutes: number
  flex_used_minutes: number
  flex_overrun_minutes: number
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

export default function MechanicsBoardPage() {
  const navigate = useNavigate()
  const { data, isLoading, isError } = useQuery<TeamBoardResponse>({
    queryKey: ['mechanic-board-team'],
    queryFn: async () => {
      const response = await api.get('/dashboard/mechanics/board')
      return response.data
    },
    refetchOnWindowFocus: true,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 animate-spin text-amber-400" />
      </div>
    )
  }

  if (isError || !data) {
    return <div className="text-red-400">Failed to load mechanics board.</div>
  }

  return (
    <div className="space-y-4">
      <div className="bg-white/5 border border-white/10 rounded-xl p-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-semibold text-white">Mechanic Board</h1>
              <SectionInfoTooltip text="Team-wide mechanic performance view with live timer state, daily utilization, and efficiency metrics." />
            </div>
            <p className="text-sm text-gray-400">
              {data.date} · {data.timezone}
            </p>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-gray-300">
              Team tracked: <strong className="text-white">{toHours(data.team_tracked_minutes)}h</strong>
            </span>
            <span className="text-gray-300">
              Core target: <strong className="text-white">{toHours(data.team_core_target_minutes)}h</strong>
            </span>
            <span className="text-amber-300">
              Utilization: <strong>{data.team_utilization_percent.toFixed(1)}%</strong>
            </span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 px-1">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">Team Mechanics</h2>
        <SectionInfoTooltip text="Each mechanic tile shows active timer status, tracked split (repair-order vs misc), utilization, efficiency, and 7-day average trend." />
      </div>

      {!data.mechanics.length ? (
        <div className="bg-white/5 border border-white/10 rounded-xl p-6 text-gray-400">No active mechanics.</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {data.mechanics.map((m) => {
            const trendAvg = m.trend_7_days.length
              ? m.trend_7_days.reduce((acc, row) => acc + row.utilization_percent, 0) / m.trend_7_days.length
              : 0
            return (
              <button
                key={m.mechanic_id}
                onClick={() => navigate(`/dashboard/mechanics/${m.mechanic_id}`)}
                className="text-left bg-white/5 border border-white/10 rounded-xl p-4 hover:bg-white/10 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Users className="w-4 h-4 text-amber-300" />
                    <h2 className="text-white font-medium">{m.mechanic_name}</h2>
                  </div>
                {m.active_session ? (
                  <span className="text-[11px] px-2 py-1 rounded bg-green-500/20 text-green-300">Active</span>
                ) : (
                  <span className="text-[11px] px-2 py-1 rounded bg-gray-500/20 text-gray-300">Idle</span>
                )}
              </div>
              <div className="mt-1 text-[11px] text-gray-400">
                <span className={m.attendance_active ? 'text-emerald-300' : 'text-gray-300'}>
                  {m.attendance_active ? 'Clocked In' : 'Clocked Out'}
                </span>
                {' · '}
                <span className={m.break_active ? 'text-amber-300' : 'text-gray-400'}>
                  {m.break_active ? 'On Break' : 'No Break'}
                </span>
                {' · '}
                <span>Idle {(m.idle_minutes / 60).toFixed(1)}h</span>
              </div>
              {m.active_session?.started_at && (
                <div className="mt-1 text-xs text-green-300 flex items-center gap-1">
                  <span>Running</span>
                  <LiveElapsedTimer startedAt={m.active_session.started_at} className="font-mono text-green-200" />
                  <span className="text-gray-500">·</span>
                  <span className="text-gray-300">
                    {formatSessionType(m.active_session.session_type)}
                    {m.active_session.session_type === 'misc' && m.active_session.misc_category
                      ? ` (${formatMiscCategory(m.active_session.misc_category)})`
                      : ''}
                  </span>
                </div>
              )}
              <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                  <div className="text-gray-400">Tracked: <span className="text-white">{toHours(m.tracked_minutes)}h</span></div>
                  <div className="text-gray-400">Core: <span className="text-white">{toHours(m.core_target_minutes)}h</span></div>
                  <div className="text-gray-400">RO: <span className="text-white">{toHours(m.ro_minutes)}h</span></div>
                  <div className="text-gray-400">Misc: <span className="text-white">{toHours(m.misc_minutes)}h</span></div>
                </div>
                <div className="mt-3">
                  <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
                    <span className="flex items-center gap-1"><Clock3 className="w-3 h-3" /> Utilization</span>
                    <span>{m.utilization_percent.toFixed(1)}%</span>
                  </div>
                  <div className="h-2 bg-white/10 rounded-full overflow-hidden">
                    <div className="h-2 bg-amber-400 rounded-full" style={{ width: `${Math.min(m.utilization_percent, 100)}%` }} />
                  </div>
                </div>
                <div className="mt-2 text-xs text-gray-400">
                  Efficiency: {m.efficiency_percent == null ? 'n/a' : `${m.efficiency_percent.toFixed(1)}%`} · Overtime:{' '}
                  <span className="text-white">{toHours(m.overtime_minutes)}h</span>
                </div>
                <div className="mt-1 text-xs text-gray-500">
                  7-day avg utilization: <span className="text-gray-200">{trendAvg.toFixed(1)}%</span>
                </div>
                <div className="mt-1 text-xs text-gray-500">
                  Flex: <span className="text-gray-200">{m.flex_used_minutes}m/{m.flex_budget_minutes}m</span>
                  {m.flex_overrun_minutes > 0 ? <span className="text-rose-300"> · +{m.flex_overrun_minutes}m</span> : null}
                </div>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
