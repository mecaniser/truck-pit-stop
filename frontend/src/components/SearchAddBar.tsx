import { Plus } from 'lucide-react'
import { useTheme } from '../contexts/ThemeContext'

type SearchAddBarProps = {
  value: string
  onChange: (value: string) => void
  placeholder: string
  onAdd: () => void
  addLabel?: string
  addLabelMobile?: string
  className?: string
  inputWidthClass?: string
  showAddButton?: boolean
  addDisabled?: boolean
}

export default function SearchAddBar({
  value,
  onChange,
  placeholder,
  onAdd,
  addLabel = 'Add',
  addLabelMobile = 'Add',
  className = '',
  inputWidthClass = 'sm:min-w-[320px] md:max-w-xl',
  showAddButton = true,
  addDisabled = false,
}: SearchAddBarProps) {
  const { accentColors } = useTheme()
  
  return (
    <div className={`db-search-add-bar flex items-center gap-2 sm:gap-3 flex-nowrap ${className}`}>
      <div className={`db-search-add-bar__field relative flex-1 min-w-0 ${inputWidthClass}`}>
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full pl-10 pr-3 py-2 rounded-lg bg-white/10 border border-white/20 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-inset"
          style={{ ['--tw-ring-color' as string]: accentColors[500] }}
        />
        <svg
          className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      </div>
      {showAddButton && (
        <div className="flex items-center gap-2 sm:gap-3 justify-end sm:ml-auto shrink-0">
          <button
            type="button"
            onClick={onAdd}
            disabled={addDisabled}
            className="db-search-add-bar__primary-action inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white transition-colors disabled:opacity-70"
            style={{ backgroundColor: accentColors[600] }}
          >
            <Plus className="w-4 h-4" />
            <span className="hidden sm:inline">{addLabel}</span>
            <span className="sm:hidden">{addLabelMobile}</span>
          </button>
        </div>
      )}
    </div>
  )
}
