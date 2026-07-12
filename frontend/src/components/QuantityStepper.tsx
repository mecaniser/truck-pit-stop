import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { Minus, Plus, Trash2 } from 'lucide-react'

type QuantityStepperProps = {
  value: number
  onChange: (next: number) => void
  min?: number
  step?: number
  unitLabel?: string
  disabled?: boolean
  ariaLabel: string
  onRemove?: () => void
  removeAtMin?: boolean
  className?: string
  /** Wrapper alignment. 'end' (default) suits table/price rows; 'start' suits
   *  label-over-field forms so the pill lines up under its left-aligned label. */
  align?: 'start' | 'end'
  /** When set, `onChange` fires once ~this many ms after the user stops
   *  stepping instead of on every click. The control still advances instantly
   *  (optimistic local value). Use for steppers that persist to the server so a
   *  flurry of clicks becomes a single request (avoids rate-limit 429s). Leave
   *  unset for steppers that only update local state. */
  commitDebounceMs?: number
}

const formatQuantity = (value: number, step: number) => (
  step < 1 ? value.toFixed(2) : String(value)
)

export default function QuantityStepper({
  value,
  onChange,
  min = 1,
  step = 1,
  unitLabel = 'ea',
  disabled,
  ariaLabel,
  onRemove,
  removeAtMin = false,
  className = '',
  align = 'end',
  commitDebounceMs,
}: QuantityStepperProps) {
  // Optimistic display value: for debounced steppers it advances on each click
  // while the write is pending; otherwise it just tracks the prop.
  const [localValue, setLocalValue] = useState(value)
  const [draft, setDraft] = useState(formatQuantity(value, step))
  const [editing, setEditing] = useState(false)
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastEmitted = useRef(value)

  const displayValue = commitDebounceMs != null ? localValue : value
  const atMin = displayValue <= min
  const canRemove = removeAtMin && atMin && !!onRemove

  // Re-sync from the prop only when idle (not typing, no pending debounced
  // write) so an in-flight save + refetch doesn't clobber what the user is
  // actively stepping.
  useEffect(() => {
    if (editing) return
    if (commitDebounceMs != null && debounceTimer.current != null) return
    setLocalValue(value)
    setDraft(formatQuantity(value, step))
    lastEmitted.current = value
  }, [value, step, editing, commitDebounceMs])

  useEffect(() => () => { if (debounceTimer.current) clearTimeout(debounceTimer.current) }, [])

  // Number of decimals implied by the step (e.g. step 0.25 -> 2), so typed
  // values are cleaned of float noise without being forced onto the step grid.
  const stepDecimals = (String(step).split('.')[1] || '').length

  const emit = (resolved: number) => {
    if (commitDebounceMs == null) {
      onChange(resolved)
      return
    }
    setLocalValue(resolved)
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    debounceTimer.current = setTimeout(() => {
      debounceTimer.current = null
      if (Math.abs(resolved - lastEmitted.current) < Math.pow(10, -(stepDecimals + 2))) return
      lastEmitted.current = resolved
      onChange(resolved)
    }, commitDebounceMs)
  }

  // snap=true (button/keyboard nudges) rounds to the nearest step multiple so
  // stepping stays on a clean grid. snap=false (typed values) keeps the exact
  // number the user entered — typing 45 with step 30 stays 45, not 60.
  const commit = (next: number, snap: boolean) => {
    if (next < min) return
    const resolved = snap
      ? Math.round(next / step) * step
      : Number(next.toFixed(stepDecimals))
    emit(resolved)
    setDraft(formatQuantity(resolved, step))
  }

  const commitDraft = () => {
    setEditing(false)
    const parsed = parseFloat(draft)
    if (!Number.isFinite(parsed) || parsed < min) {
      setDraft(formatQuantity(displayValue, step))
      return
    }
    commit(parsed, false)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if ((e.ctrlKey || e.metaKey) && (e.key === '+' || e.key === '=' || e.key === '-' || e.key === '_')) {
      e.preventDefault()
      commit(displayValue + (e.key === '-' || e.key === '_' ? -step : step), true)
      return
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      commitDraft()
      e.currentTarget.blur()
    } else if (e.key === 'Escape') {
      setEditing(false)
      setDraft(formatQuantity(displayValue, step))
      e.currentTarget.blur()
    }
  }

  return (
    <span className={`inline-flex items-center gap-1.5 ${align === 'start' ? 'justify-start' : 'min-w-[9.75rem] justify-end'} ${className}`}>
      <span className="inline-flex items-center rounded-lg border border-gray-200 bg-white shadow-sm">
        <button
          type="button"
          disabled={disabled}
          onClick={canRemove ? onRemove : () => commit(displayValue - step, true)}
          aria-label={canRemove ? `Remove ${ariaLabel}` : `Decrease ${ariaLabel}`}
          className={`flex h-8 w-8 items-center justify-center rounded-l-lg disabled:opacity-50 ${
            canRemove ? 'text-red-500 hover:bg-red-50' : 'text-gray-500 hover:bg-gray-50'
          }`}
        >
          {canRemove ? <Trash2 className="h-3.5 w-3.5" /> : <Minus className="h-3.5 w-3.5" />}
        </button>
        <input
          type="text"
          inputMode="decimal"
          disabled={disabled}
          value={draft}
          onFocus={() => setEditing(true)}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commitDraft}
          onKeyDown={handleKeyDown}
          aria-label={ariaLabel}
          title="Type a value, or use Ctrl/Cmd + and Ctrl/Cmd - to step"
          className="h-8 w-14 border-x border-gray-200 bg-transparent text-center font-['JetBrains_Mono',monospace] text-sm tabular-nums text-gray-900 outline-none focus:bg-gray-50 disabled:opacity-50"
        />
        <button
          type="button"
          disabled={disabled}
          onClick={() => commit(displayValue + step, true)}
          aria-label={`Increase ${ariaLabel}`}
          className="flex h-8 w-8 items-center justify-center rounded-r-lg text-gray-500 hover:bg-gray-50 disabled:opacity-50"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </span>
      {unitLabel !== '' && <span className="w-7 text-left text-xs text-gray-500">{unitLabel}</span>}
    </span>
  )
}
