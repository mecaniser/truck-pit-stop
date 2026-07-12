import { useEffect, useRef, useState } from 'react'
import { Minus, Plus } from 'lucide-react'
import { formatHoursMinutes } from '@/lib/durationFormat'

type DurationStepperProps = {
  /** Value in decimal hours (e.g. 1.75). */
  hours: number
  /** Called with the new value in decimal hours. */
  onChange: (nextHours: number) => void
  /** Step size in minutes (default 15). */
  stepMinutes?: number
  /** Minimum in minutes (default = one step). */
  minMinutes?: number
  disabled?: boolean
  ariaLabel?: string
  /** When set, `onChange` fires once ~this many ms after the user stops
   *  stepping (optimistic display advances instantly). Use for steppers that
   *  persist to the server so rapid clicks become one request. */
  commitDebounceMs?: number
  /** Visual theme. 'light' (default) suits white surfaces; 'dark' inverts the
   *  pill for dark modals (e.g. the fleet work-order panel). */
  theme?: 'light' | 'dark'
}

const DURATION_THEME = {
  light: { pill: 'border-gray-200 bg-white', btn: 'text-gray-500 hover:bg-gray-50', text: 'text-gray-900 border-gray-200' },
  dark: { pill: 'border-white/15 bg-white/5', btn: 'text-gray-300 hover:bg-white/10', text: 'text-gray-100 border-white/15' },
} as const

/**
 * A single control for entering how long a job takes. Reads out as "1h 45m",
 * steps by 15 minutes, and reports the value back in decimal hours (the number
 * billing math needs). The user never sees the decimal — one control, one
 * reading, no unit label or secondary hint.
 */
export default function DurationStepper({
  hours,
  onChange,
  stepMinutes = 15,
  minMinutes,
  disabled,
  ariaLabel = 'Duration',
  commitDebounceMs,
  theme = 'light',
}: DurationStepperProps) {
  const t = DURATION_THEME[theme]
  const floor = minMinutes ?? stepMinutes
  const [localHours, setLocalHours] = useState(hours)
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastEmitted = useRef(hours)

  const displayHours = commitDebounceMs != null ? localHours : hours
  const totalMinutes = Math.round((Number(displayHours) || 0) * 60)

  // Re-sync from the prop only when no debounced write is pending, so an
  // in-flight save + refetch doesn't clobber the value being stepped.
  useEffect(() => {
    if (commitDebounceMs != null && debounceTimer.current != null) return
    setLocalHours(hours)
    lastEmitted.current = hours
  }, [hours, commitDebounceMs])

  useEffect(() => () => { if (debounceTimer.current) clearTimeout(debounceTimer.current) }, [])

  const setMinutes = (mins: number) => {
    const clamped = Math.max(floor, mins)
    const nextHours = clamped / 60
    if (commitDebounceMs == null) {
      onChange(nextHours)
      return
    }
    setLocalHours(nextHours)
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    debounceTimer.current = setTimeout(() => {
      debounceTimer.current = null
      if (Math.abs(nextHours - lastEmitted.current) < 0.0001) return
      lastEmitted.current = nextHours
      onChange(nextHours)
    }, commitDebounceMs)
  }
  const dec = () => setMinutes(totalMinutes - stepMinutes)
  const inc = () => setMinutes(totalMinutes + stepMinutes)

  return (
    <span
      className={`inline-flex items-center rounded-lg border shadow-sm ${t.pill}`}
      role="group"
      aria-label={ariaLabel}
    >
      <button
        type="button"
        disabled={disabled || totalMinutes <= floor}
        onClick={dec}
        aria-label="Decrease duration"
        className={`flex h-8 w-8 items-center justify-center rounded-l-lg disabled:opacity-40 ${t.btn}`}
      >
        <Minus className="h-3.5 w-3.5" />
      </button>
      <span className={`min-w-[4.5rem] border-x px-2 text-center font-['JetBrains_Mono',monospace] text-sm tabular-nums ${t.text}`}>
        {formatHoursMinutes(displayHours)}
      </span>
      <button
        type="button"
        disabled={disabled}
        onClick={inc}
        aria-label="Increase duration"
        className={`flex h-8 w-8 items-center justify-center rounded-r-lg disabled:opacity-40 ${t.btn}`}
      >
        <Plus className="h-3.5 w-3.5" />
      </button>
    </span>
  )
}
