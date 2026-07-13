import type { Suggestion, SuggestionTheme } from './useSuggestions'

/** Shared dropdown list rendered under SuggestingTextarea / SuggestingInput. */
export default function SuggestionDropdown({
  suggestions,
  highlightedIndex,
  onHover,
  onSelect,
  theme,
}: {
  suggestions: Suggestion[]
  highlightedIndex: number
  onHover: (index: number) => void
  onSelect: (text: string) => void
  theme: SuggestionTheme
}) {
  return (
    <div
      style={{
        position: 'absolute', zIndex: 50, top: '100%', left: 0, right: 0, marginTop: 4,
        background: theme.background, border: theme.border, borderRadius: 9,
        boxShadow: theme.shadow, overflow: 'hidden', maxHeight: 220, overflowY: 'auto',
      }}
    >
      {suggestions.map((s, i) => (
        <button
          key={s.text}
          type="button"
          onMouseDown={(e) => {
            e.preventDefault()
            onSelect(s.text)
          }}
          onMouseEnter={() => onHover(i)}
          style={{
            display: 'flex', width: '100%', alignItems: 'center', justifyContent: 'space-between', gap: 10,
            padding: '9px 12px', textAlign: 'left', border: 'none', cursor: 'pointer', font: 'inherit', fontSize: 13,
            background: i === highlightedIndex ? theme.itemHoverBg : 'transparent',
            color: theme.text,
          }}
        >
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.text}</span>
          <span style={{ flexShrink: 0, fontSize: 11, color: theme.mutedText }}>
            used {s.times_used}×
          </span>
        </button>
      ))}
    </div>
  )
}
