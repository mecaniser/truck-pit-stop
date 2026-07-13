import { useSuggestions, type SuggestionVariant } from './useSuggestions'
import SuggestionDropdown from './SuggestionDropdown'

interface SuggestingInputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'onChange' | 'onSelect'> {
  value: string
  onChange: (value: string) => void
  /** Fired only when a suggestion is explicitly picked (click or Enter), not on every keystroke — distinct from the native textarea/input onSelect (text-selection) event, which this component does not expose. */
  onSelect?: (value: string) => void
  /** Backend endpoint that returns [{ text, times_used }], filtered by ?q= */
  suggestUrl: string
  /**
   * 'dark' styles the dropdown with the fleet module's CSS custom properties
   * (--ink/--line/--text/...), which only resolve inside fleet.css. 'light'
   * (default) uses plain colors for white-background admin pages.
   */
  variant?: SuggestionVariant
}

/**
 * Single-line sibling of SuggestingTextarea — same "type freely, dropdown
 * suggests from the shop's own history, never forces a choice" behavior,
 * for short-label fields like a service name.
 */
export default function SuggestingInput({
  value,
  onChange,
  onSelect,
  suggestUrl,
  variant = 'light',
  style,
  ...inputProps
}: SuggestingInputProps) {
  const {
    isOpen, setIsOpen, highlightedIndex, setHighlightedIndex, containerRef,
    visibleSuggestions, applySuggestion, handleKeyDown, theme,
  } = useSuggestions({ value, onChange, onSelect, suggestUrl, variant })

  return (
    <div ref={containerRef} style={{ position: 'relative' }}>
      <input
        {...inputProps}
        type="text"
        value={value}
        onChange={(e) => {
          onChange(e.target.value)
          setIsOpen(true)
        }}
        onFocus={(e) => {
          setIsOpen(true)
          inputProps.onFocus?.(e)
        }}
        onKeyDown={(e) => handleKeyDown(e, inputProps.onKeyDown)}
        style={style}
      />
      {isOpen && visibleSuggestions.length > 0 && (
        <SuggestionDropdown
          suggestions={visibleSuggestions}
          highlightedIndex={highlightedIndex}
          onHover={setHighlightedIndex}
          onSelect={applySuggestion}
          theme={theme}
        />
      )}
    </div>
  )
}
