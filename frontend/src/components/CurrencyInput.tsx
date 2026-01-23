import { useState, useEffect } from 'react'

type CurrencyInputProps = {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
  disabled?: boolean
  required?: boolean
}

export default function CurrencyInput({
  value,
  onChange,
  placeholder = '0.00',
  className = '',
  disabled = false,
  required = false,
}: CurrencyInputProps) {
  const [displayValue, setDisplayValue] = useState(value)

  useEffect(() => {
    setDisplayValue(value)
  }, [value])

  const formatCurrency = (val: string): string => {
    const num = parseFloat(val)
    if (isNaN(num)) return ''
    return num.toFixed(2)
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

  return (
    <div className="relative">
      <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
      <input
        type="number"
        step="0.01"
        min="0"
        value={displayValue}
        onChange={handleChange}
        onBlur={handleBlur}
        disabled={disabled}
        required={required}
        className={`w-full rounded-lg border border-gray-200 pl-7 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
        placeholder={placeholder}
      />
    </div>
  )
}
