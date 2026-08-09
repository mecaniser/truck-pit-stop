import type { Suggestion, SuggestionTheme } from './useSuggestions'

/** Shared dropdown list rendered under SuggestingTextarea / SuggestingInput. */
export default function SuggestionDropdown({
  suggestions,
  highlightedIndex,
  onHover,
  onSelect,
  theme,
  id,
  label,
}: {
  suggestions: Suggestion[]
  highlightedIndex: number
  onHover: (index: number) => void
  onSelect: (text: string) => void
  theme: SuggestionTheme
  id?: string
  label?: string
}) {
  return (
    <div
      id={id}
      role="listbox"
      aria-label={label || 'Previous entries'}
      style={{
        position: 'absolute', zIndex: 50, top: '100%', left: 0, right: 0, marginTop: 4,
        background: theme.background, border: theme.border, borderRadius: 9,
        boxShadow: theme.shadow, overflow: 'hidden', maxHeight: 244, overflowY: 'auto',
      }}
    >
      {label && (
        <div style={{
          position: 'sticky', top: 0, zIndex: 1, padding: '8px 12px',
          background: theme.background, borderBottom: theme.border,
          color: theme.mutedText, fontSize: 10.5, fontWeight: 750,
          letterSpacing: '.07em', textTransform: 'uppercase',
        }}>
          {label}
        </div>
      )}
      {suggestions.map((s, i) => (
        <button
          key={s.text}
          type="button"
          role="option"
          aria-selected={i === highlightedIndex}
          aria-label={`${s.text}, used ${s.times_used} ${s.times_used === 1 ? 'time' : 'times'}`}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => onSelect(s.text)}
          onMouseEnter={() => onHover(i)}
          style={{
            display: 'flex', width: '100%', alignItems: 'center', justifyContent: 'space-between', gap: 10,
            minHeight: 44, padding: '9px 12px', textAlign: 'left', border: 'none', cursor: 'pointer', font: 'inherit', fontSize: 13,
            background: i === highlightedIndex ? theme.itemHoverBg : 'transparent',
            color: theme.text,
          }}
        >
          <span style={{
            minWidth: 0, overflow: 'hidden', display: '-webkit-box',
            WebkitBoxOrient: 'vertical', WebkitLineClamp: 2, lineHeight: 1.35,
          }}>{s.text}</span>
          <span style={{ flexShrink: 0, fontSize: 11, color: theme.mutedText }}>
            {s.times_used} {s.times_used === 1 ? 'use' : 'uses'}
          </span>
        </button>
      ))}
    </div>
  )
}
