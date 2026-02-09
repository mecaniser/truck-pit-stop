import { LayoutGrid, Rows } from 'lucide-react'
import { useTheme } from '../contexts/ThemeContext'

type ViewMode = 'list' | 'cards'

type ViewToggleProps = {
  value: ViewMode
  onChange: (mode: ViewMode) => void
  className?: string
  disabled?: boolean
  variant?: 'dark' | 'light'
}

export default function ViewToggle({ value, onChange, className = '', disabled = false, variant = 'dark' }: ViewToggleProps) {
  const { accentColors } = useTheme()
  
  const baseButton =
    'flex items-center justify-center gap-1 px-3 py-1 rounded-md text-sm font-medium transition'

  const disabledClass = disabled ? 'pointer-events-none opacity-50' : ''

  const containerClass = variant === 'light' 
    ? 'bg-gray-100 border border-gray-200' 
    : 'bg-white/10 border border-white/15'

  const inactiveClass = variant === 'light'
    ? 'text-gray-600 hover:bg-gray-200'
    : 'text-white hover:bg-white/20'

  return (
    <div className={`flex items-center gap-1 rounded-md p-0.5 ${containerClass} ${className} ${disabledClass}`}>
      <button
        type="button"
        onClick={() => onChange('list')}
        className={`${baseButton} ${value === 'list' ? 'text-white' : inactiveClass}`}
        style={value === 'list' ? { backgroundColor: accentColors[500] } : undefined}
      >
        <Rows className="w-4 h-4" /> List
      </button>
      <button
        type="button"
        onClick={() => onChange('cards')}
        className={`${baseButton} ${value === 'cards' ? 'text-white' : inactiveClass}`}
        style={value === 'cards' ? { backgroundColor: accentColors[500] } : undefined}
      >
        <LayoutGrid className="w-4 h-4" /> Cards
      </button>
    </div>
  )
}
