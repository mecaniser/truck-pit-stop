import React from 'react'
import { LayoutGrid, Rows } from 'lucide-react'

type ViewMode = 'list' | 'cards'

type ViewToggleProps = {
  value: ViewMode
  onChange: (mode: ViewMode) => void
  className?: string
  disabled?: boolean
}

export default function ViewToggle({ value, onChange, className = '', disabled = false }: ViewToggleProps) {
  const baseButton =
    'flex items-center justify-center gap-1 px-3 py-1 rounded-md text-sm font-medium transition'

  const disabledClass = disabled ? 'pointer-events-none opacity-50' : ''

  return (
    <div className={`flex items-center gap-1 bg-white/10 border border-white/15 rounded-md p-0.5 ${className} ${disabledClass}`}>
      <button
        type="button"
        onClick={() => onChange('list')}
        className={`${baseButton} ${value === 'list' ? 'bg-amber-500 text-white' : 'text-white hover:bg-white/20'}`}
      >
        <Rows className="w-4 h-4" /> List
      </button>
      <button
        type="button"
        onClick={() => onChange('cards')}
        className={`${baseButton} ${value === 'cards' ? 'bg-amber-500 text-white' : 'text-white hover:bg-white/20'}`}
      >
        <LayoutGrid className="w-4 h-4" /> Cards
      </button>
    </div>
  )
}
