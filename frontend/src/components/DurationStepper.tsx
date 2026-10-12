import { useEffect, useId, useRef, useState } from 'react'
import { Minus, Plus } from 'lucide-react'
import { formatHoursMinutes } from '@/lib/durationFormat'

type DurationStepperProps = {
  /** Value in decimal hours (e.g. 1.75). */
  hours: number
  /** Called with the new value in decimal hours. */
  onChange: (nextHours: number) => void
  /** Fires immediately with the optimistic value on every step, even before
   *  the debounced `onChange` commits. Use when a sibling control needs to
   *  read the in-progress value (e.g. a live total computed from this and
   *  another stepper). */
  onLocalChange?: (nextHours: number) => void
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
  /** Control size. 'md' (default, 32px) for dense rows; 'lg' (42px) for larger
   *  touch targets — e.g. a gloved shop-floor workflow. */
  size?: 'md' | 'lg'
}

const DURATION_THEME = {
  light: { pill: 'border-gray-200 bg-white', btn: 'text-gray-500 hover:bg-gray-50', text: 'text-gray-900 border-gray-200' },
  dark: { pill: 'border-white/15 bg-white/5', btn: 'text-gray-300 hover:bg-white/10', text: 'text-gray-100 border-white/15' },
} as const

const DUR_SIZE = {
  md: { btn: 32, value: 72, font: 14 },
  lg: { btn: 42, value: 84, font: 15 },
} as const

// Accept decimal hours, h:mm, or explicit hour/minute units. Never partially
// parse malformed values (e.g. "1:75" or "2hours-extra") into billable time.
function parseMinutes(value: string): number | null {
  const text = value.trim().toLowerCase()
  let minutes: number
  if (/^\d+(?:\.\d+)?$/.test(text)) {
    minutes = Number(text) * 60
  } else {
    const clock = text.match(/^(\d+):([0-5]\d)$/)
    const units = text.match(/^(?:(\d+)h)?\s*(?:(\d+)m)?$/)
    if (clock) minutes = Number(clock[1]) * 60 + Number(clock[2])
    else if (units && (units[1] || units[2])) minutes = Number(units[1] || 0) * 60 + Number(units[2] || 0)
    else return null
  }
  const rounded = Math.round(minutes)
  return Number.isSafeInteger(rounded) ? rounded : null
}

/** Editable duration with minute precision and quarter-hour shortcuts. */
export default function DurationStepper({
  hours,
  onChange,
  onLocalChange,
  stepMinutes = 15,
  minMinutes,
  disabled,
  ariaLabel = 'Duration',
  commitDebounceMs,
  theme = 'light',
  size = 'md',
}: DurationStepperProps) {
  const t = DURATION_THEME[theme]
  const sz = DUR_SIZE[size]
  const floor = minMinutes ?? stepMinutes
  const [localHours, setLocalHours] = useState(hours)
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastEmitted = useRef(hours)
  const [draft, setDraft] = useState<string | null>(null)
  const [error, setError] = useState(false)
  const dirtyDraft = useRef(false)
  const skipBlur = useRef(false)
  const helpId = useId()
  const errorId = useId()

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
    if (disabled) return
    setDraft(null)
    dirtyDraft.current = false
    setError(false)
    const clamped = Math.max(floor, mins)
    const nextHours = clamped / 60
    onLocalChange?.(nextHours)
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
  const resolveDraft = () => {
    const minutes = draft == null ? totalMinutes : parseMinutes(draft)
    if (minutes == null || minutes < floor) {
      setError(true)
      return null
    }
    return minutes
  }
  const commitDraft = () => {
    if (disabled) return
    if (!dirtyDraft.current) { setDraft(null); return }
    const minutes = resolveDraft()
    if (minutes != null) setMinutes(minutes)
  }
  const step = (direction: number) => {
    const minutes = dirtyDraft.current ? resolveDraft() : totalMinutes
    if (minutes != null) setMinutes(minutes + direction * stepMinutes)
  }

  return (
    <span
      className={`relative inline-flex items-center rounded-lg border shadow-sm ${t.pill}`}
      role="group"
      aria-label={ariaLabel}
    >
      <button
        type="button"
        disabled={disabled || totalMinutes <= floor}
        onPointerDown={(e) => e.preventDefault()}
        onClick={() => step(-1)}
        aria-label="Decrease duration"
        style={{ width: sz.btn, height: sz.btn }}
        className={`flex items-center justify-center rounded-l-lg disabled:opacity-40 ${t.btn}`}
      >
        <Minus className="h-3.5 w-3.5" />
      </button>
      <input
        type="text"
        inputMode="decimal"
        disabled={disabled}
        aria-label={ariaLabel}
        aria-invalid={error || undefined}
        aria-describedby={error ? `${helpId} ${errorId}` : helpId}
        title="Type hours (1.5) or h:mm (1:30). Enter to save; Escape to cancel."
        value={draft ?? formatHoursMinutes(displayHours)}
        onFocus={(e) => {
          if (draft == null) setDraft(`${Math.floor(totalMinutes / 60)}:${String(totalMinutes % 60).padStart(2, '0')}`)
          e.currentTarget.select()
        }}
        onChange={(e) => { setDraft(e.target.value); dirtyDraft.current = true; setError(false) }}
        onBlur={() => {
          if (skipBlur.current) { skipBlur.current = false; return }
          commitDraft()
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            e.stopPropagation()
            commitDraft()
            skipBlur.current = true
            e.currentTarget.blur()
          } else if (e.key === 'Escape') {
            e.preventDefault()
            e.stopPropagation()
            setDraft(null)
            dirtyDraft.current = false
            setError(false)
            skipBlur.current = true
            e.currentTarget.blur()
          }
        }}
        style={{ width: sz.value, height: sz.btn, fontSize: sz.font }}
        className={`min-w-0 flex-none rounded-none border-x bg-transparent px-1 text-center font-['JetBrains_Mono',monospace] tabular-nums outline-none focus:ring-2 focus:ring-inset focus:ring-orange-400 disabled:opacity-40 ${t.text}`}
      />
      <span id={helpId} className="sr-only">Enter decimal hours or hours:minutes. Enter saves; Escape cancels.</span>
      {error && (
        <span id={errorId} role="alert" className="absolute bottom-full left-0 z-10 mb-1 w-52 rounded-md bg-red-700 px-2 py-1 text-xs text-white shadow">
          Enter hours (1.5) or h:mm (1:30){floor > 0 ? `, at least ${floor} minutes` : ''}.
        </span>
      )}
      <button
        type="button"
        disabled={disabled}
        onPointerDown={(e) => e.preventDefault()}
        onClick={() => step(1)}
        aria-label="Increase duration"
        style={{ width: sz.btn, height: sz.btn }}
        className={`flex items-center justify-center rounded-r-lg disabled:opacity-40 ${t.btn}`}
      >
        <Plus className="h-3.5 w-3.5" />
      </button>
    </span>
  )
}
