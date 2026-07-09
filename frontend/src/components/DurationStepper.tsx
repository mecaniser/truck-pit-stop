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
}

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
}: DurationStepperProps) {
  const floor = minMinutes ?? stepMinutes
  const totalMinutes = Math.round((Number(hours) || 0) * 60)

  const setMinutes = (mins: number) => {
    const clamped = Math.max(floor, mins)
    onChange(clamped / 60)
  }
  const dec = () => setMinutes(totalMinutes - stepMinutes)
  const inc = () => setMinutes(totalMinutes + stepMinutes)

  return (
    <span
      className="inline-flex items-center rounded-lg border border-gray-200 bg-white shadow-sm"
      role="group"
      aria-label={ariaLabel}
    >
      <button
        type="button"
        disabled={disabled || totalMinutes <= floor}
        onClick={dec}
        aria-label="Decrease duration"
        className="flex h-8 w-8 items-center justify-center rounded-l-lg text-gray-500 hover:bg-gray-50 disabled:opacity-40"
      >
        <Minus className="h-3.5 w-3.5" />
      </button>
      <span className="min-w-[4.5rem] border-x border-gray-200 px-2 text-center font-['JetBrains_Mono',monospace] text-sm tabular-nums text-gray-900">
        {formatHoursMinutes(hours)}
      </span>
      <button
        type="button"
        disabled={disabled}
        onClick={inc}
        aria-label="Increase duration"
        className="flex h-8 w-8 items-center justify-center rounded-r-lg text-gray-500 hover:bg-gray-50 disabled:opacity-40"
      >
        <Plus className="h-3.5 w-3.5" />
      </button>
    </span>
  )
}
