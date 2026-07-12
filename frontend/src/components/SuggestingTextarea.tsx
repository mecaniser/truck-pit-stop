import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../lib/api'
import { useDebouncedValue } from '../hooks/useDebouncedValue'

interface Suggestion {
  text: string
  times_used: number
}

interface SuggestingTextareaProps extends Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, 'onChange'> {
  value: string
  onChange: (value: string) => void
  /** Backend endpoint that returns [{ text, times_used }], filtered by ?q= */
  suggestUrl?: string
}

/**
 * A plain textarea with an autocomplete dropdown fed by the shop's own past
 * text in this field (e.g. repair order complaint/work-performed history) —
 * not a canned list, not an AI model, just "what has this shop typed
 * before that's close to what you're typing now."
 */
export default function SuggestingTextarea({
  value,
  onChange,
  suggestUrl = '/repair-orders/description-suggestions',
  style,
  ...textareaProps
}: SuggestingTextareaProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)
  const debouncedValue = useDebouncedValue(value, 250)

  const { data: suggestions } = useQuery<Suggestion[]>({
    queryKey: ['description-suggestions', suggestUrl, debouncedValue],
    queryFn: async () => {
      const response = await api.get(suggestUrl, { params: { q: debouncedValue, limit: 6 } })
      return response.data
    },
    enabled: isOpen && debouncedValue.trim().length >= 2,
  })

  const visibleSuggestions = (suggestions || []).filter((s) => s.text !== value)

  useEffect(() => {
    setHighlightedIndex(0)
  }, [suggestions])

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const applySuggestion = (text: string) => {
    onChange(text)
    setIsOpen(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (!isOpen || visibleSuggestions.length === 0) {
      textareaProps.onKeyDown?.(e)
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlightedIndex((i) => Math.min(i + 1, visibleSuggestions.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlightedIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      applySuggestion(visibleSuggestions[highlightedIndex].text)
    } else if (e.key === 'Escape') {
      setIsOpen(false)
    } else {
      textareaProps.onKeyDown?.(e)
    }
  }

  return (
    <div ref={containerRef} style={{ position: 'relative' }}>
      <textarea
        {...textareaProps}
        value={value}
        onChange={(e) => {
          onChange(e.target.value)
          setIsOpen(true)
        }}
        onFocus={(e) => {
          setIsOpen(true)
          textareaProps.onFocus?.(e)
        }}
        onKeyDown={handleKeyDown}
        style={style}
      />
      {isOpen && visibleSuggestions.length > 0 && (
        <div
          style={{
            position: 'absolute', zIndex: 50, top: '100%', left: 0, right: 0, marginTop: 4,
            background: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 9,
            boxShadow: '0 12px 28px rgba(0,0,0,0.35)', overflow: 'hidden', maxHeight: 220, overflowY: 'auto',
          }}
        >
          {visibleSuggestions.map((s, i) => (
            <button
              key={s.text}
              type="button"
              onMouseDown={(e) => {
                e.preventDefault()
                applySuggestion(s.text)
              }}
              onMouseEnter={() => setHighlightedIndex(i)}
              style={{
                display: 'flex', width: '100%', alignItems: 'center', justifyContent: 'space-between', gap: 10,
                padding: '9px 12px', textAlign: 'left', border: 'none', cursor: 'pointer', font: 'inherit', fontSize: 13,
                background: i === highlightedIndex ? 'var(--line)' : 'transparent',
                color: 'var(--text)',
              }}
            >
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.text}</span>
              <span style={{ flexShrink: 0, fontSize: 11, color: 'var(--muted-2)' }}>
                used {s.times_used}×
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
