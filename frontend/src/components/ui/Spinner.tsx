// Shared loading spinner — the single loading indicator for the app.
// One border-arc shape, sized by context rather than raw pixels, tinted with
// the themeable accent so it re-colors per role (garage amber, admin gold).
//
// See /src/styles/DESIGN_SYSTEM.md and the loading-indicator audit for the
// patterns this replaces (hand-rolled <svg class="animate-spin">, CSS
// border-spinners, lucide Loader2).

export type SpinnerSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl'

// size → [box, border-width]. Border scales with the disc so the arc stays
// proportional at every size.
const SIZES: Record<SpinnerSize, { box: string; border: string }> = {
  xs: { box: 'h-3.5 w-3.5', border: 'border-2' },   // 14px — inside buttons
  sm: { box: 'h-4 w-4', border: 'border-2' },       // 16px — inline / next to text
  md: { box: 'h-6 w-6', border: 'border-[2.5px]' }, // 24px — panels, cards
  lg: { box: 'h-8 w-8', border: 'border-[3px]' },   // 32px — section blocks
  xl: { box: 'h-12 w-12', border: 'border-[3px]' }, // 48px — full-page / route load
}

export interface SpinnerProps {
  size?: SpinnerSize
  /** Accessible label announced to screen readers. Defaults to "Loading". */
  label?: string
  /** Extra classes on the spinning disc (e.g. a color override). */
  className?: string
}

export function Spinner({ size = 'sm', label = 'Loading', className = '' }: SpinnerProps) {
  const { box, border } = SIZES[size]
  return (
    <span
      role="status"
      aria-label={label}
      className={`inline-block shrink-0 animate-spin rounded-full border-gray-400/30 border-t-[var(--accent-400)] ${box} ${border} ${className}`}
    />
  )
}

export interface LoadingLineProps {
  children: React.ReactNode
  size?: SpinnerSize
  /** Extra classes on the wrapper (spacing, text color, etc.). */
  className?: string
}

/**
 * A spinner paired with a short label, for the many "Loading…" text spots that
 * previously had no visual. Inherits text color; the spinner keeps the accent.
 */
export function LoadingLine({ children, size = 'sm', className = '' }: LoadingLineProps) {
  return (
    <span className={`inline-flex items-center gap-2 text-sm text-gray-500 ${className}`}>
      <Spinner size={size} label="Loading" />
      <span>{children}</span>
    </span>
  )
}

export default Spinner
