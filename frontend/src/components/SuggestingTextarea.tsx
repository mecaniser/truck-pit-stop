import { useId } from 'react'
import { useSuggestions, type SuggestionVariant } from './useSuggestions'
import SuggestionDropdown from './SuggestionDropdown'

interface SuggestingTextareaProps extends Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, 'onChange' | 'onSelect'> {
  value: string
  onChange: (value: string) => void
  /** Fired only when a suggestion is explicitly picked (click or Enter), not on every keystroke — distinct from the native textarea/input onSelect (text-selection) event, which this component does not expose. */
  onSelect?: (value: string) => void
  /** Backend endpoint that returns [{ text, times_used }], filtered by ?q= */
  suggestUrl?: string
  /**
   * 'dark' (default) styles the dropdown with the fleet module's CSS custom
   * properties (--ink/--line/--text/...), which only exist inside fleet.css.
   * 'light' uses plain Tailwind classes for use on white-background admin
   * pages outside the fleet module.
   */
  variant?: SuggestionVariant
  /** Search only the active fragment in a multi-value textarea. */
  getSuggestionQuery?: (value: string) => string
  /** Merge a selected suggestion into the current value instead of replacing it. */
  mergeSuggestion?: (currentValue: string, suggestion: string) => string
  suggestionLabel?: string
  suggestionLimit?: number
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
  onSelect,
  suggestUrl = '/repair-orders/description-suggestions',
  variant = 'dark',
  getSuggestionQuery,
  mergeSuggestion,
  suggestionLabel,
  suggestionLimit,
  style,
  ...textareaProps
}: SuggestingTextareaProps) {
  const suggestionListId = useId()
  const {
    isOpen, setIsOpen, highlightedIndex, setHighlightedIndex, containerRef,
    visibleSuggestions, applySuggestion, handleKeyDown, theme,
  } = useSuggestions({
    value, onChange, onSelect, suggestUrl, variant,
    getQuery: getSuggestionQuery, mergeSuggestion, limit: suggestionLimit,
  })

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
        onKeyDown={(e) => handleKeyDown(e, textareaProps.onKeyDown)}
        aria-autocomplete="list"
        aria-controls={isOpen && visibleSuggestions.length > 0 ? suggestionListId : undefined}
        aria-expanded={isOpen && visibleSuggestions.length > 0}
        style={style}
      />
      {isOpen && visibleSuggestions.length > 0 && (
        <SuggestionDropdown
          suggestions={visibleSuggestions}
          highlightedIndex={highlightedIndex}
          onHover={setHighlightedIndex}
          onSelect={applySuggestion}
          theme={theme}
          id={suggestionListId}
          label={suggestionLabel}
        />
      )}
    </div>
  )
}
