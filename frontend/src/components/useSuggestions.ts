import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../lib/api'
import { useDebouncedValue } from '../hooks/useDebouncedValue'

export interface Suggestion {
  text: string
  times_used: number
}

export type SuggestionVariant = 'dark' | 'light'

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
  suggestUrl,
  variant,
}: {
  value: string
  onChange: (value: string) => void
  suggestUrl: string
  variant: SuggestionVariant
}) {
  const [isOpen, setIsOpen] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)
  const debouncedValue = useDebouncedValue(value, 250)

  const { data: suggestions } = useQuery<Suggestion[]>({
    queryKey: ['field-suggestions', suggestUrl, debouncedValue],
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
