import type { CSSProperties } from 'react'
import { LayoutGrid, Rows } from 'lucide-react'
import { useTheme } from '../contexts/ThemeContext'

export type ViewMode = 'list' | 'cards'

export type ViewToggleProps = {
  value: ViewMode
  onChange: (mode: ViewMode) => void
  className?: string
  disabled?: boolean
  variant?: 'dark' | 'light'
  ariaLabel?: string
}

export default function ViewToggle({
  value,
  onChange,
  className = '',
  disabled = false,
  variant = 'dark',
  ariaLabel,
}: ViewToggleProps) {
  const { accentColors } = useTheme()
  const nextMode: ViewMode = value === 'list' ? 'cards' : 'list'
  const label = nextMode === 'cards' ? 'Show cards' : 'Show list'
  const Icon = nextMode === 'cards' ? LayoutGrid : Rows
  const surfaceClass = variant === 'light'
    ? 'border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:bg-gray-100 hover:text-gray-900 focus-visible:ring-offset-white'
    : 'border-white/15 bg-white/10 text-white/80 hover:border-white/25 hover:bg-white/15 hover:text-white focus-visible:ring-offset-slate-900'

  return (
    <button
      type="button"
      disabled={disabled}
      aria-label={ariaLabel ?? label}
      title={label}
      onClick={() => onChange(nextMode)}
      className={`inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg border px-3 text-sm font-semibold transition-[background-color,border-color,color,box-shadow,transform] duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--view-toggle-accent)] focus-visible:ring-offset-2 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100 ${surfaceClass} ${className}`}
      style={{ '--view-toggle-accent': accentColors[500] } as CSSProperties}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      <span>{label}</span>
    </button>
  )
}
