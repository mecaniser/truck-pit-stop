import { useEffect, useState, type KeyboardEvent } from 'react'
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
}: QuantityStepperProps) {
  const [draft, setDraft] = useState(formatQuantity(value, step))
  const [editing, setEditing] = useState(false)
  const atMin = value <= min
  const canRemove = removeAtMin && atMin && !!onRemove

  useEffect(() => {
    if (!editing) setDraft(formatQuantity(value, step))
  }, [value, step, editing])

  const commit = (next: number) => {
    if (next < min) return
    const rounded = Math.round(next / step) * step
    onChange(rounded)
    setDraft(formatQuantity(rounded, step))
  }

  const commitDraft = () => {
    setEditing(false)
    const parsed = parseFloat(draft)
    if (!Number.isFinite(parsed) || parsed < min) {
      setDraft(formatQuantity(value, step))
      return
    }
    commit(parsed)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if ((e.ctrlKey || e.metaKey) && (e.key === '+' || e.key === '=' || e.key === '-' || e.key === '_')) {
      e.preventDefault()
      commit(value + (e.key === '-' || e.key === '_' ? -step : step))
      return
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      commitDraft()
      e.currentTarget.blur()
    } else if (e.key === 'Escape') {
      setEditing(false)
      setDraft(formatQuantity(value, step))
      e.currentTarget.blur()
    }
  }

  return (
    <span className={`inline-flex min-w-[9.75rem] items-center justify-end gap-1.5 ${className}`}>
      <span className="inline-flex items-center rounded-lg border border-gray-200 bg-white shadow-sm">
        <button
          type="button"
          disabled={disabled}
          onClick={canRemove ? onRemove : () => commit(value - step)}
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
          onClick={() => commit(value + step)}
          aria-label={`Increase ${ariaLabel}`}
          className="flex h-8 w-8 items-center justify-center rounded-r-lg text-gray-500 hover:bg-gray-50 disabled:opacity-50"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </span>
      <span className="w-7 text-left text-xs text-gray-500">{unitLabel}</span>
    </span>
  )
}
