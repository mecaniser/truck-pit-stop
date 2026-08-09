import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../lib/api'
import { useDebouncedValue } from '../hooks/useDebouncedValue'

export interface Suggestion {
  text: string
  times_used: number
}

export type SuggestionVariant = 'dark' | 'light' | 'blueNoir'

export interface SuggestionTheme {
  background: string
  border: string
  shadow: string
  itemHoverBg: string
  text: string
  mutedText: string
}

const THEMES: Record<SuggestionVariant, SuggestionTheme> = {
  light: {
    background: '#ffffff',
    border: '1px solid #e5e7eb',
    shadow: '0 12px 28px rgba(0,0,0,0.12)',
    itemHoverBg: '#f3f4f6',
    text: '#111827',
    mutedText: '#6b7280',
  },
  dark: {
    // fleet module's CSS custom properties — only resolve inside fleet.css
    background: 'var(--ink)',
    border: '1px solid var(--line)',
    shadow: '0 12px 28px rgba(0,0,0,0.35)',
    itemHoverBg: 'var(--line)',
    text: 'var(--text)',
    mutedText: 'var(--muted-2)',
  },
  blueNoir: {
    // Concrete hex matching the main dashboard's BlueNoir theme
    // (tailwind.config blueNoir.800/700) — no CSS var dependency.
    background: '#101820',
    border: '1px solid rgba(255,255,255,0.1)',
    shadow: '0 12px 28px rgba(0,0,0,0.45)',
    itemHoverBg: '#182028',
    text: '#ffffff',
    mutedText: '#9ca3af',
  },
}

/**
 * Shared behavior behind SuggestingTextarea / SuggestingInput: debounced
 * fetch of the shop's own past text for this field, open/close + click-
 * outside handling, keyboard nav (ArrowUp/Down/Enter/Escape), and the
 * dark/light color theme. Each caller supplies its own input element and
 * wires handleKeyDown to it.
 */
export function useSuggestions({
  value,
  onChange,
  onSelect,
  suggestUrl,
  variant,
  getQuery,
  mergeSuggestion,
  limit = 6,
}: {
  value: string
  onChange: (value: string) => void
  /** Fired only when a suggestion is explicitly picked (click or Enter), not on every keystroke. */
  onSelect?: (value: string) => void
  suggestUrl: string
  variant: SuggestionVariant
  /** Lets a multi-value field search only the fragment currently being typed. */
  getQuery?: (value: string) => string
  /** Lets a multi-value field complete its active fragment without replacing prior text. */
  mergeSuggestion?: (currentValue: string, suggestion: string) => string
  limit?: number
}) {
  const [isOpen, setIsOpen] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)
  const query = getQuery ? getQuery(value) : value
  const debouncedQuery = useDebouncedValue(query, 250)

  const { data: suggestions } = useQuery<Suggestion[]>({
    queryKey: ['field-suggestions', suggestUrl, debouncedQuery, limit],
    queryFn: async () => {
      const response = await api.get(suggestUrl, { params: { q: debouncedQuery, limit } })
      return response.data
    },
    enabled: isOpen && debouncedQuery.trim().length >= 2,
  })

  const normalizedQuery = query.trim().toLocaleLowerCase()
  const visibleSuggestions = (suggestions || []).filter((s) => s.text.trim().toLocaleLowerCase() !== normalizedQuery)

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
    onChange(mergeSuggestion ? mergeSuggestion(value, text) : text)
    onSelect?.(text)
    setIsOpen(false)
  }

  function handleKeyDown<T extends Element>(e: React.KeyboardEvent<T>, fallback?: (e: React.KeyboardEvent<T>) => void) {
    if (!isOpen || visibleSuggestions.length === 0) {
      fallback?.(e)
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
      e.preventDefault()
      e.stopPropagation()
      setIsOpen(false)
    } else {
      fallback?.(e)
    }
  }

  return {
    isOpen,
    setIsOpen,
    highlightedIndex,
    setHighlightedIndex,
    containerRef,
    visibleSuggestions,
    applySuggestion,
    handleKeyDown,
    theme: THEMES[variant],
  }
}
