/**
 * Chart palette + theme tokens for the analytics surfaces.
 *
 * Colors here were validated with the dataviz skill's `validate_palette.js`
 * against the dark chart surface (#1a1a19) — do not eyeball-swap them. The
 * design handoff's original hexes (#34d399 emerald, #a78bfa violet, #f87171
 * red, and the 8-colour scatter set) FAILED the lightness-band and CVD-
 * separation checks; these are the corrected, in-band, CVD-safe replacements.
 *
 *   parts / margin / danger / cumulative  → validated non-accent series
 *   CATEGORICAL[]                          → ≤6 validated categorical order
 *   STATUS                                 → good / mixed / bad (quadrant, flags)
 *
 * The PRIMARY series colour is the user's live accent (accentColors[500] from
 * ThemeContext) — CVD-safe against `parts` for all five accent options — so
 * charts follow the chosen theme. Read it per-chart via useTheme().
 */

// Non-accent, semantically-fixed series colours (validated, dark surface).
export const SERIES = {
  parts: '#3987e5', // blue
  margin: '#199e70', // aqua/green (replaces too-light #34d399)
  danger: '#e66767', // red (replaces #f87171)
  cumulative: '#9085e9', // violet (replaces #a78bfa)
  neutral: '#6b7280', // muted grey (funnel first stage, etc.)
} as const

// Fixed categorical order for "colour by category" marks (e.g. RO type on the
// profitability scatter). Assign in order, never cycle; a 7th+ folds to Other.
export const CATEGORICAL = [
  '#3987e5', // blue
  '#199e70', // aqua
  '#c98500', // yellow
  '#008300', // green
  '#9085e9', // violet
  '#e66767', // red
] as const

// Status ramp — reserved for good/warning/bad state, never reused as a series.
export const STATUS = {
  good: '#199e70',
  mixed: '#c98500',
  bad: '#e66767',
} as const

// Neutral chart chrome (dark BlueNoir surface).
export const CHART = {
  grid: 'rgba(255,255,255,0.06)',
  axis: '#6b7280',
  axisTick: '#c3c2b7',
  cursorFill: 'rgba(255,255,255,0.03)',
  tooltipBg: '#151b26',
  tooltipBorder: '1px solid rgba(255,255,255,0.1)',
  tooltipText: '#e5e7eb',
  tooltipMuted: '#9ca3af',
} as const

/** Pick a categorical colour by index, folding overflow to a neutral "Other". */
export function categoricalColor(index: number): string {
  return index < CATEGORICAL.length ? CATEGORICAL[index] : SERIES.neutral
}

/**
 * Per-tab accent colours (the "Visual Hierarchy" handoff requires every tab to
 * own a distinct accent so it's identifiable by colour alone). These are
 * validated near-equivalents of the handoff's hexes — same hue family, snapped
 * into the dark lightness band so they read correctly (the handoff's literal
 * #34d399 / #facc15 / etc. were out-of-band on the dark surface). Dashboard
 * uses the user's live theme accent, so it's resolved at the call site.
 */
export const TAB_ACCENT = {
  sales: '#3987e5', // blue   (handoff #60a5fa)
  fees: '#d95926', // orange (handoff #fb923c)
  tax: '#c98500', // amber  (handoff #facc15)
  parts: '#199e70', // emerald(handoff #34d399)
  inventory: '#1c9dd4', // sky    (handoff #38bdf8)
  serviceTypes: '#6366F1', // indigo (handoff #818cf8)
  fleet: '#d95926', // orange (handoff #fb923c)
} as const
