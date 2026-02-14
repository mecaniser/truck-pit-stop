import { useMemo } from 'react'
import type { SuggestedNextAction } from '@/types'

export interface MechanicSuggestionJob {
  id: string
  order_number: string
  status: string
  updated_at: string
}

interface DaySummarySuggestionState {
  attendance_active: boolean
  break_active: boolean
  core_countdown_remaining_minutes: number
  active_session: {
    session_type: 'repair_order' | 'misc'
    repair_order_id?: string | null
  } | null
}

interface DeriveSuggestionOptions {
  ignoreBreak?: boolean
}

export interface MechanicSuggestion {
  action: SuggestedNextAction
  recommendedJob: MechanicSuggestionJob | null
}

// Keep this decision order in sync with backend `compute_next_action_recommendation`.
export function deriveMechanicSuggestion(
  daySummary: DaySummarySuggestionState | undefined,
  jobs: MechanicSuggestionJob[] | undefined,
  options: DeriveSuggestionOptions = {},
): MechanicSuggestion {
  const activeJobs = jobs || []
  const suggestedByStatus = (status: string) =>
    [...activeJobs]
      .filter((job) => job.status === status)
      .sort((a, b) => new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime())[0] || null

  const assignedReadyJob = suggestedByStatus('acknowledged') || suggestedByStatus('assigned')
  const activeSession = daySummary?.active_session
  const activeRoId = activeSession?.session_type === 'repair_order' ? activeSession.repair_order_id : null
  const untimedInProgressJob =
    [...activeJobs]
      .filter((job) => job.status === 'in_progress' && job.id !== activeRoId)
      .sort((a, b) => new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime())[0] || null

  if (!daySummary?.attendance_active) {
    return { action: 'clock_in', recommendedJob: null }
  }
  if (!options.ignoreBreak && daySummary.break_active) {
    return { action: 'end_break', recommendedJob: null }
  }
  if (activeSession?.session_type === 'repair_order') {
    const currentRo = activeSession.repair_order_id
      ? activeJobs.find((job) => job.id === activeSession.repair_order_id) || null
      : null
    return { action: 'continue_ro', recommendedJob: currentRo }
  }
  if (activeSession?.session_type === 'misc' && assignedReadyJob) {
    return { action: 'stop_misc_pick_ro', recommendedJob: assignedReadyJob }
  }
  if (!activeSession && untimedInProgressJob) {
    return { action: 'start_assigned_ro', recommendedJob: untimedInProgressJob }
  }
  if (!activeSession && assignedReadyJob) {
    return { action: 'start_assigned_ro', recommendedJob: assignedReadyJob }
  }
  if (!activeSession && (daySummary.core_countdown_remaining_minutes || 0) <= 0) {
    return { action: 'clock_out', recommendedJob: null }
  }
  return { action: 'start_misc', recommendedJob: null }
}

export function useMechanicSuggestion(
  daySummary: DaySummarySuggestionState | undefined,
  jobs: MechanicSuggestionJob[] | undefined,
) {
  const mechanicSuggestion = useMemo(() => deriveMechanicSuggestion(daySummary, jobs), [daySummary, jobs])
  const isMiscSuggestion = mechanicSuggestion.action === 'start_misc'
  const isStopMiscSuggestion = mechanicSuggestion.action === 'stop_misc_pick_ro'
  const highlightedJobId = (
    mechanicSuggestion.action === 'continue_ro'
    || mechanicSuggestion.action === 'start_assigned_ro'
    || mechanicSuggestion.action === 'stop_misc_pick_ro'
  ) ? mechanicSuggestion.recommendedJob?.id || null : null
  const isOnBreak = !!daySummary?.break_active
  const hasActiveDayTimer = !!daySummary?.active_session
  const shouldPulseTimerToggle = !isOnBreak && (
    (isMiscSuggestion && !hasActiveDayTimer)
    || (isStopMiscSuggestion && daySummary?.active_session?.session_type === 'misc')
  )

  return {
    mechanicSuggestion,
    isMiscSuggestion,
    isStopMiscSuggestion,
    highlightedJobId,
    shouldPulseTimerToggle,
  }
}
