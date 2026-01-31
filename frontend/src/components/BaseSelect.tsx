import { useMemo, useState, useRef, useEffect } from 'react'
import { ChevronDown } from 'lucide-react'

export interface BaseSelectOption {
  value: string
  label: string
  subLabel?: string
}

interface BaseSelectProps {
  options: BaseSelectOption[]
  value: string
  onChange: (val: string) => void
  placeholder?: string
  searchable?: boolean
  allowAddNew?: boolean
  addNewLabel?: string
  onAddNew?: () => void
  disabled?: boolean
}

export default function BaseSelect({
  options,
  value,
  onChange,
  placeholder = 'Select an option',
  searchable = true,
  allowAddNew = false,
  addNewLabel = '+ Add new',
  onAddNew,
  disabled = false,
}: BaseSelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [query, setQuery] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const filtered = useMemo(() => {
    if (!searchable || !query.trim()) return options
    const q = query.toLowerCase()
    return options.filter((opt) => opt.label.toLowerCase().includes(q) || opt.subLabel?.toLowerCase().includes(q))
  }, [options, query, searchable])

  const selected = options.find((opt) => opt.value === value)

  // Focus input when dropdown opens
  useEffect(() => {
    if (isOpen && searchable && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isOpen, searchable])

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
        setQuery('')
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleSelect = (val: string) => {
    if (allowAddNew && val === 'add_new') {
      if (onAddNew) onAddNew()
      setIsOpen(false)
      setQuery('')
    } else {
      onChange(val)
      setIsOpen(false)
      setQuery('')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setIsOpen(false)
      setQuery('')
    } else if (e.key === 'Enter' && filtered.length === 1) {
      handleSelect(filtered[0].value)
    }
  }

  return (
    <div ref={containerRef} className="relative">
      {/* Closed state: show button */}
      {!isOpen ? (
        <button
          type="button"
          onClick={() => !disabled && setIsOpen(true)}
          disabled={disabled}
          className={`w-full px-4 py-2.5 border border-gray-300 rounded-lg bg-white text-left text-gray-900 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors flex items-center justify-between ${
            disabled ? 'opacity-50 cursor-not-allowed' : ''
          }`}
        >
          <span className="block truncate">{selected ? selected.label : placeholder}</span>
          <ChevronDown className="w-4 h-4 text-gray-400 shrink-0" />
        </button>
      ) : (
        /* Open state: show search input */
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={selected ? selected.label : placeholder}
          className="w-full px-4 py-2.5 border border-amber-500 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-amber-500 transition-colors"
        />
      )}

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute z-50 mt-1 max-h-64 w-full overflow-auto rounded-lg bg-white py-1 shadow-xl ring-1 ring-black/10">
          {filtered.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onMouseDown={(e) => {
                e.preventDefault()
                e.stopPropagation()
                handleSelect(opt.value)
              }}
              className={`w-full text-left px-4 py-2 text-sm hover:bg-amber-50 hover:text-amber-700 transition-colors ${
                opt.value === value ? 'bg-amber-50 text-amber-700' : 'text-gray-900'
              }`}
            >
              <div className="flex flex-col">
                <span className="font-medium">{opt.label}</span>
                {opt.subLabel && <span className="text-xs text-gray-500">{opt.subLabel}</span>}
              </div>
            </button>
          ))}

          {allowAddNew && (
            <button
              type="button"
              onMouseDown={(e) => {
                e.preventDefault()
                e.stopPropagation()
                handleSelect('add_new')
              }}
              className="w-full text-left px-4 py-2 text-sm font-medium text-amber-700 hover:bg-amber-100 hover:text-amber-800 transition-colors"
            >
              {addNewLabel}
            </button>
          )}

          {filtered.length === 0 && !allowAddNew && (
            <div className="px-4 py-2 text-sm text-gray-500">No results</div>
          )}
        </div>
      )}
    </div>
  )
}
