import { useEffect, useState } from 'react'

interface DaySummaryCountdownState {
  core_countdown_remaining_minutes: number
  attendance_active: boolean
  attendance_started_at: string | null
}

export function useCoreCountdown(daySummary: DaySummaryCountdownState | undefined) {
  const [countdownNowMs, setCountdownNowMs] = useState(() => Date.now())
  const [countdownAnchorMs, setCountdownAnchorMs] = useState(() => Date.now())

  useEffect(() => {
    const intervalId = window.setInterval(() => setCountdownNowMs(Date.now()), 1000)
    return () => window.clearInterval(intervalId)
  }, [])

  useEffect(() => {
    setCountdownAnchorMs(Date.now())
  }, [daySummary?.core_countdown_remaining_minutes, daySummary?.attendance_active, daySummary?.attendance_started_at])

  const baseCountdownSeconds = (daySummary?.core_countdown_remaining_minutes || 0) * 60
  const liveCountdownSeconds = daySummary?.attendance_active
    ? Math.max(baseCountdownSeconds - Math.floor((countdownNowMs - countdownAnchorMs) / 1000), 0)
    : baseCountdownSeconds

  return { countdownNowMs, liveCountdownSeconds }
}
