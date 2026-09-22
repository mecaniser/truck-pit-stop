import { useLayoutEffect, useRef } from 'react'

/** A formatted display over the existing ungrouped decimal API value. */
export default function DiscountAmountInput({ label, value, onChange, disabled }: {
  label: string
  value: string
  onChange: (value: string) => void
  disabled?: boolean
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const pendingCaret = useRef<number | null>(null)
  const [whole, fraction] = value.split('.')
  const display = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (fraction === undefined ? '' : `.${fraction}`)

  useLayoutEffect(() => {
    if (pendingCaret.current === null || !inputRef.current) return
    let index = 0
    let remaining = pendingCaret.current
    while (index < display.length && remaining > 0) {
      if (display[index] !== ',') remaining--
      index++
    }
    inputRef.current.setSelectionRange(index, index)
    pendingCaret.current = null
  }, [display])

  return (
    <span className="relative inline-flex w-28 shrink-0">
      <span aria-hidden="true" className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-sm text-slate-500">$</span>
      <input
        ref={inputRef}
        aria-label={label}
        title={display ? `$${display}` : undefined}
        inputMode="decimal"
        disabled={disabled}
        value={display}
        onChange={event => {
          const text = event.target.value
          const raw = text.replace(/[$,\s]/g, '')
          if (!/^\d*(?:\.\d{0,2})?$/.test(raw)) return
          pendingCaret.current = text.slice(0, event.target.selectionStart ?? text.length).replace(/[$,\s]/g, '').length
          onChange(raw)
        }}
        onBlur={() => {
          if (value && Number.isFinite(Number(value))) onChange(Number(value).toFixed(2))
        }}
        placeholder="0.00"
        className="h-9 w-full rounded-lg border border-gray-200 bg-white pl-5 pr-2 text-right font-['JetBrains_Mono',monospace] text-sm text-slate-950 placeholder:text-slate-500 disabled:opacity-60"
      />
    </span>
  )
}
