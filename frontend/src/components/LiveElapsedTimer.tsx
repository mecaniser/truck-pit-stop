import { useEffect, useMemo, useState } from 'react'

function formatElapsed(totalSeconds: number): string {
  const safeSeconds = Math.max(0, totalSeconds)
  const hours = Math.floor(safeSeconds / 3600)
  const minutes = Math.floor((safeSeconds % 3600) / 60)
  const seconds = safeSeconds % 60
  return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
}

interface LiveElapsedTimerProps {
  startedAt?: string | null
  className?: string
}

export default function LiveElapsedTimer({ startedAt, className = '' }: LiveElapsedTimerProps) {
  const [nowMs, setNowMs] = useState(() => Date.now())

  useEffect(() => {
    const intervalId = setInterval(() => setNowMs(Date.now()), 1000)
    return () => clearInterval(intervalId)
  }, [])

  const display = useMemo(() => {
    if (!startedAt) return '--:--:--'
    const startMs = new Date(startedAt).getTime()
    if (Number.isNaN(startMs)) return '--:--:--'
    return formatElapsed(Math.floor((nowMs - startMs) / 1000))
  }, [nowMs, startedAt])

  return <span className={className}>{display}</span>
}
