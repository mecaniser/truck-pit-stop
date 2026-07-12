import { useMemo, useState, useRef, useEffect, useLayoutEffect } from 'react'
import { createPortal } from 'react-dom'
import { ChevronDown } from 'lucide-react'
import { useTheme } from '../contexts/ThemeContext'

export interface BaseSelectOption {
  value: string
  label: string
  subLabel?: string
  /** Extra text to match against when searching, without displaying it directly
   * (e.g. a secondary name so a company-name label is still findable by the
   * contact's personal name, or vice versa). */
  searchText?: string
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
  variant?: 'light' | 'dark'
  /** Control height class (default h-[42px]). Pass e.g. 'h-[34px]' to match a
   *  denser row where the select must line up with 34px-tall siblings. */
  heightClass?: string
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
  variant = 'light',
  heightClass = 'h-[42px]',
}: BaseSelectProps) {
  const dark = variant === 'dark'
  const { accentColors } = useTheme()
  const [isOpen, setIsOpen] = useState(false)
  const [query, setQuery] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  // The floating list renders in a portal with fixed positioning anchored to the
  // trigger, so an ancestor with overflow:auto (e.g. the fleet modal) can't clip
  // it or grow a scrollbar. null = closed/unmeasured.
  const [menuPos, setMenuPos] = useState<{ left: number; width: number; top?: number; bottom?: number } | null>(null)

  const computePosition = () => {
    const el = containerRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const estimatedMenuHeight = 256 // matches max-h below
    const spaceBelow = window.innerHeight - rect.bottom
    const openUp = spaceBelow < estimatedMenuHeight && rect.top > spaceBelow
    setMenuPos({
      left: rect.left,
      width: rect.width,
      top: openUp ? undefined : rect.bottom + 4,
      bottom: openUp ? window.innerHeight - rect.top + 4 : undefined,
    })
  }

  const filtered = useMemo(() => {
    if (!searchable || !query.trim()) return options
    const q = query.toLowerCase()
    return options.filter((opt) =>
      opt.label.toLowerCase().includes(q) ||
      opt.subLabel?.toLowerCase().includes(q) ||
      opt.searchText?.toLowerCase().includes(q)
    )
  }, [options, query, searchable])

  const selected = options.find((opt) => opt.value === value)

  // Measure before paint when opening; keep the menu glued to the trigger while
  // the user scrolls or resizes.
  useLayoutEffect(() => {
    if (!isOpen) { setMenuPos(null); return }
    computePosition()
    const onMove = () => computePosition()
    window.addEventListener('scroll', onMove, true) // capture: also catch inner scrollers
    window.addEventListener('resize', onMove)
    return () => {
      window.removeEventListener('scroll', onMove, true)
      window.removeEventListener('resize', onMove)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen])

  // Focus input when dropdown opens
  useEffect(() => {
    if (isOpen && searchable && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isOpen, searchable])

  // Close on click outside — but not when clicking inside the portaled menu.
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node
      if (containerRef.current?.contains(target)) return
      if (menuRef.current?.contains(target)) return
      setIsOpen(false)
      setQuery('')
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
          className={`w-full ${heightClass} px-4 border rounded-lg text-left focus:outline-none focus:ring-2 transition-colors flex items-center justify-between ${
            dark
              ? 'border-white/20 bg-white/10 text-white'
              : 'border-gray-300 bg-white text-gray-900'
          } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
          style={{ ['--tw-ring-color' as string]: accentColors[500] }}
        >
          <span className={`block truncate ${!selected && (dark ? 'text-gray-500' : 'text-gray-400')}`}>
            {selected ? selected.label : placeholder}
          </span>
          <ChevronDown className={`w-4 h-4 shrink-0 ${dark ? 'text-gray-400' : 'text-gray-400'}`} />
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
          className={`w-full ${heightClass} px-4 border rounded-lg focus:outline-none focus:ring-2 transition-colors ${
            dark
              ? 'border-white/40 bg-white/10 text-white placeholder:text-gray-500'
              : 'bg-white text-gray-900'
          }`}
          style={{ borderColor: accentColors[500], ['--tw-ring-color' as string]: accentColors[500] }}
        />
      )}

      {/* Dropdown — portaled to <body> with fixed positioning so an ancestor's
          overflow:auto can't clip it or grow a scrollbar. */}
      {isOpen && menuPos && createPortal(
        <div
          ref={menuRef}
          style={{
            position: 'fixed',
            left: menuPos.left,
            width: menuPos.width,
            top: menuPos.top,
            bottom: menuPos.bottom,
          }}
          className={`z-[100] max-h-64 overflow-auto rounded-lg py-1 shadow-xl ${
            dark
              ? 'bg-gray-900 border border-white/20'
              : 'bg-white ring-1 ring-black/10'
          }`}
        >
          {filtered.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onMouseDown={(e) => {
                e.preventDefault()
                e.stopPropagation()
                handleSelect(opt.value)
              }}
              className={`w-full text-left px-4 py-2 text-sm transition-colors ${
                dark
                  ? opt.value === value
                    ? 'text-white'
                    : 'text-gray-200 hover:bg-white/10'
                  : opt.value === value
                    ? 'text-gray-900'
                    : 'text-gray-900 hover:bg-gray-50'
              }`}
              style={opt.value === value ? { backgroundColor: `${accentColors[500]}1a`, color: accentColors[400] } : undefined}
            >
              <div className="flex flex-col">
                <span className="font-medium">{opt.label}</span>
                {opt.subLabel && (
                  <span className={`text-xs ${dark ? 'text-gray-400' : 'text-gray-500'}`}>{opt.subLabel}</span>
                )}
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
              className="w-full text-left px-4 py-2 text-sm font-medium transition-colors hover:opacity-80"
              style={{ color: accentColors[600] }}
            >
              {addNewLabel}
            </button>
          )}

          {filtered.length === 0 && !allowAddNew && (
            <div className={`px-4 py-2 text-sm ${dark ? 'text-gray-500' : 'text-gray-500'}`}>No results</div>
          )}
        </div>,
        document.body,
      )}
    </div>
  )
}
