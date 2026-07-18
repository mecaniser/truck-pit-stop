import { useState, useEffect } from 'react'
import { Minus, Plus } from 'lucide-react'

type CurrencyInputProps = {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
  disabled?: boolean
  required?: boolean
  /** When set, renders −/+ buttons that nudge the amount by this many dollars
   *  (e.g. 1 for $1.00 steps). Typing an exact value still works. */
  step?: number
  /** Unit symbol shown inside the input. Defaults to '$' (prefixed). */
  symbol?: string
  /** Render the symbol after the number (e.g. '15 %') instead of before. */
  symbolSuffix?: boolean
  /** Decimal places the value is formatted to on blur/nudge. Default 2. */
  decimals?: number
}

export default function CurrencyInput({
  value,
  onChange,
  placeholder = '0.00',
  className = '',
  disabled = false,
  required = false,
  step,
  symbol = '$',
  symbolSuffix = false,
  decimals = 2,
}: CurrencyInputProps) {
  const [displayValue, setDisplayValue] = useState(value)

  useEffect(() => {
    setDisplayValue(value)
  }, [value])

  const formatCurrency = (val: string): string => {
    const num = parseFloat(val)
    if (isNaN(num)) return ''
    return num.toFixed(decimals)
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setDisplayValue(e.target.value)
    onChange(e.target.value)
  }

  const handleBlur = () => {
    const formatted = formatCurrency(displayValue)
    if (formatted) {
      setDisplayValue(formatted)
      onChange(formatted)
    }
  }

  const nudge = (delta: number) => {
    const current = parseFloat(displayValue)
    const base = Number.isFinite(current) ? current : 0
    const next = Math.max(0, base + delta)
    const formatted = next.toFixed(decimals)
    setDisplayValue(formatted)
    onChange(formatted)
  }

  const input = (
    <div className="relative flex-1">
      <span className={`absolute ${symbolSuffix ? 'right-3' : 'left-3'} top-1/2 -translate-y-1/2 text-gray-400 text-sm`}>
        {symbol}
      </span>
      <input
        type="number"
        step="0.01"
        min="0"
        value={displayValue}
        onChange={handleChange}
        onBlur={handleBlur}
        disabled={disabled}
        required={required}
        className={`w-full rounded-lg border border-gray-200 ${symbolSuffix ? 'pl-3 pr-8' : 'pl-7 pr-3'} py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
        placeholder={placeholder}
      />
    </div>
  )

  if (!step) return input

  // Color-code direction so −/+ can't be confused: red decreases, green increases.
  const stepBtn = 'flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg border bg-white shadow-sm disabled:opacity-50'
  return (
    <div className="flex items-stretch gap-1.5">
      <button type="button" disabled={disabled} onClick={() => nudge(-step)} aria-label="Decrease amount"
        className={`${stepBtn} border-red-200 text-red-500 hover:bg-red-50`}>
        <Minus className="h-3.5 w-3.5" />
      </button>
      {input}
      <button type="button" disabled={disabled} onClick={() => nudge(step)} aria-label="Increase amount"
        className={`${stepBtn} border-emerald-200 text-emerald-600 hover:bg-emerald-50`}>
        <Plus className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}
