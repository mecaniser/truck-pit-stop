import { ReactNode, forwardRef } from 'react'

// ============ DESIGN SYSTEM STYLES ============
// Hybrid industrial-organic: rounded corners + LED glows + soft shadows

const styles = {
  card: `
    relative bg-zinc-900/80 backdrop-blur-sm 
    border border-zinc-700/50 rounded-2xl
    overflow-hidden shadow-xl shadow-black/20
  `,
  cardElevated: `
    relative bg-zinc-800/60 backdrop-blur-sm 
    border border-zinc-700/50 rounded-2xl
    overflow-hidden shadow-lg shadow-black/20
  `,
  cardSubtle: `
    bg-zinc-800/40 border border-zinc-700/50 rounded-xl
  `,
  input: `
    w-full px-4 py-3 
    bg-zinc-800/60 border border-zinc-600/50 rounded-xl
    text-zinc-100 text-sm
    placeholder-zinc-500 
    focus:outline-none focus:border-[var(--accent-500)] 
    focus:bg-zinc-800 focus:ring-2 focus:ring-[var(--accent-500)]/20
    transition-all duration-200
    hover:border-zinc-500
  `,
  label: `block text-xs font-medium text-zinc-400 mb-2`,
  sectionHeader: `
    text-xs font-bold uppercase tracking-[0.2em] text-zinc-500
    border-b border-zinc-800/50 pb-2 mb-6
    flex items-center gap-3
  `,
}

// ============ CARD ============
interface CardProps {
  children: ReactNode
  className?: string
  hover?: boolean
  variant?: 'default' | 'elevated' | 'subtle'
  padding?: 'none' | 'sm' | 'md' | 'lg'
  style?: React.CSSProperties
}

const paddingClasses = {
  none: '',
  sm: 'p-4',
  md: 'p-6',
  lg: 'p-8',
}

export function GlassNoirCard({ 
  children, 
  className = '', 
  hover = false,
  variant = 'default',
  padding = 'md',
  style
}: CardProps) {
  const variantStyles = {
    default: styles.card,
    elevated: styles.cardElevated,
    subtle: styles.cardSubtle,
  }
  
  return (
    <div
      className={`
        ${variantStyles[variant]}
        ${paddingClasses[padding]}
        ${hover ? 'transition-all duration-300 hover:border-[var(--accent-500)]/40 hover:shadow-lg hover:shadow-[var(--accent-500)]/10' : ''}
        ${className}
      `}
      style={style}
    >
      {children}
    </div>
  )
}

// Alias for cleaner imports
export const Card = GlassNoirCard

// ============ BUTTON ============
interface ButtonProps {
  children: ReactNode
  onClick?: () => void
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
  className?: string
  disabled?: boolean
  type?: 'button' | 'submit'
}

const buttonVariants = {
  primary: `
    bg-[var(--accent-600)] hover:bg-[var(--accent-500)] 
    text-white font-semibold
    border border-[var(--accent-400)]/50
    hover:shadow-[0_0_24px_var(--accent-500)]
    active:scale-[0.98]
  `,
  secondary: `
    bg-zinc-800/80 hover:bg-zinc-700 
    text-zinc-300 font-semibold
    border border-zinc-600/50 hover:border-zinc-500
  `,
  danger: `
    bg-red-950/80 hover:bg-red-900 
    text-red-400 font-semibold
    border border-red-800/50 hover:border-red-600
  `,
  ghost: `
    hover:bg-zinc-800/60 
    text-zinc-400 hover:text-zinc-300
    border border-transparent
  `,
}

const buttonSizes = {
  sm: 'px-3 py-1.5 text-xs rounded-lg',
  md: 'px-4 py-2.5 text-sm rounded-xl',
  lg: 'px-6 py-3 text-sm rounded-xl',
}

export function GlassNoirButton({
  children,
  onClick,
  variant = 'primary',
  size = 'md',
  className = '',
  disabled = false,
  type = 'button',
}: ButtonProps) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`
        ${buttonVariants[variant]}
        ${buttonSizes[size]}
        transition-all duration-200
        disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-none
        ${className}
      `}
    >
      {children}
    </button>
  )
}

// Alias
export const Button = GlassNoirButton

// ============ INPUT ============
interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  error?: boolean
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className = '', error = false, ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={`
          ${styles.input}
          ${error ? 'border-red-500 focus:border-red-400' : ''}
          ${className}
        `}
        {...props}
      />
    )
  }
)
Input.displayName = 'Input'

// ============ LABEL ============
export function Label({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <label className={`${styles.label} ${className}`}>{children}</label>
}

// ============ SECTION HEADER ============
interface SectionHeaderProps {
  children: ReactNode
  icon?: ReactNode
  actions?: ReactNode
}

export function SectionHeader({ children, icon, actions }: SectionHeaderProps) {
  return (
    <div className={styles.sectionHeader}>
      {icon && <span className="text-[var(--accent-400)]">{icon}</span>}
      <span>{children}</span>
      {actions && <div className="ml-auto">{actions}</div>}
    </div>
  )
}

// ============ BADGE ============
interface BadgeProps {
  children: ReactNode
  variant?: 'default' | 'success' | 'warning' | 'error' | 'info' | 'gold'
  className?: string
}

const badgeVariants = {
  default: 'bg-zinc-800/80 text-zinc-300 border-zinc-600/50',
  success: 'bg-emerald-950/80 text-emerald-400 border-emerald-700/50',
  warning: 'bg-amber-950/80 text-amber-400 border-amber-700/50',
  error: 'bg-red-950/80 text-red-400 border-red-700/50',
  info: 'bg-blue-950/80 text-blue-400 border-blue-700/50',
  gold: 'bg-amber-950/80 text-amber-300 border-amber-600/50',
}

export function GlassNoirBadge({ children, variant = 'default', className = '' }: BadgeProps) {
  return (
    <span className={`
      inline-flex items-center gap-2 
      px-3 py-1.5 text-xs font-semibold 
      rounded-full border
      ${badgeVariants[variant]}
      ${className}
    `}>
      {children}
    </span>
  )
}

// Alias
export const Badge = GlassNoirBadge

// ============ STATUS LED ============
type LEDStatus = 'active' | 'inactive' | 'warning' | 'error' | 'info'

const ledColors: Record<LEDStatus, { bg: string; glow: string }> = {
  active: { bg: 'bg-emerald-400', glow: 'shadow-[0_0_10px_rgba(52,211,153,0.9)]' },
  inactive: { bg: 'bg-zinc-600', glow: '' },
  warning: { bg: 'bg-amber-400', glow: 'shadow-[0_0_10px_rgba(251,191,36,0.9)]' },
  error: { bg: 'bg-red-400', glow: 'shadow-[0_0_10px_rgba(248,113,113,0.9)]' },
  info: { bg: 'bg-sky-400', glow: 'shadow-[0_0_10px_rgba(56,189,248,0.9)]' },
}

const ledSizes = {
  sm: 'w-2 h-2',
  md: 'w-2.5 h-2.5',
  lg: 'w-3 h-3',
}

interface StatusLEDProps {
  status: LEDStatus
  size?: 'sm' | 'md' | 'lg'
  pulse?: boolean
}

export function StatusLED({ status, size = 'md', pulse }: StatusLEDProps) {
  const { bg, glow } = ledColors[status]
  const shouldPulse = pulse ?? (status === 'active' || status === 'warning')
  return (
    <div 
      className={`
        ${ledSizes[size]} rounded-full ${bg} ${glow}
        ${shouldPulse ? 'animate-pulse' : ''}
      `} 
    />
  )
}

// ============ HEADER ============
interface HeaderProps {
  title: string
  subtitle?: string
  icon?: ReactNode
  actions?: ReactNode
}

export function GlassNoirHeader({ title, subtitle, icon, actions }: HeaderProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 sm:mb-8">
      <div className="flex items-center gap-3 sm:gap-4 min-w-0">
        {icon && (
          <div className="p-2.5 sm:p-3 bg-[var(--accent-500)]/10 rounded-xl border border-[var(--accent-500)]/30 flex-shrink-0">
            {icon}
          </div>
        )}
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-zinc-100 truncate">{title}</h1>
          {subtitle && <p className="text-sm sm:text-base text-zinc-400 mt-0.5 sm:mt-1 truncate">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex items-center gap-3">{actions}</div>}
    </div>
  )
}

// Alias
export const Header = GlassNoirHeader

// ============ STAT CARD ============
interface StatProps {
  label: string
  value: string | number
  icon?: ReactNode
  trend?: { value: number; positive: boolean }
  className?: string
}

export function GlassNoirStat({ label, value, icon, trend, className = '' }: StatProps) {
  return (
    <GlassNoirCard hover className={className}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-zinc-400 text-sm">{label}</p>
          <p className="text-2xl font-bold text-zinc-100 mt-1">{value}</p>
          {trend && (
            <p className={`text-sm mt-2 ${trend.positive ? 'text-emerald-400' : 'text-red-400'}`}>
              {trend.positive ? '↑' : '↓'} {Math.abs(trend.value)}%
            </p>
          )}
        </div>
        {icon && (
          <div className="p-2 bg-[var(--accent-500)]/10 rounded-xl text-[var(--accent-400)]">
            {icon}
          </div>
        )}
      </div>
    </GlassNoirCard>
  )
}

// Alias
export const Stat = GlassNoirStat

// ============ TOGGLE ============
interface ToggleProps {
  enabled: boolean
  onChange: (enabled: boolean) => void
  disabled?: boolean
}

export function Toggle({ enabled, onChange, disabled = false }: ToggleProps) {
  return (
    <button
      type="button"
      onClick={() => !disabled && onChange(!enabled)}
      disabled={disabled}
      className={`
        relative w-14 h-8 rounded-full border transition-colors
        ${enabled 
          ? 'bg-[var(--accent-600)] border-[var(--accent-400)]/50' 
          : 'bg-zinc-800 border-zinc-600/50'
        }
        ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
      `}
    >
      <span className={`
        absolute top-1 w-5 h-5 bg-white rounded-full 
        transition-transform shadow-md
        ${enabled ? 'left-7' : 'left-1'}
      `} />
    </button>
  )
}

// ============ SPINNER ============
// Spinner moved to ./Spinner.tsx (the shared, size-scaled loading indicator).
// Re-exported from ./index.ts so existing `import { Spinner } from '@/components/ui'` keeps working.

// ============ DIVIDER ============
export function Divider({ className = '' }: { className?: string }) {
  return <div className={`border-t border-zinc-800/50 ${className}`} />
}

// ============ STAGGERED ANIMATION HELPER ============
export const staggeredReveal = (index: number) => ({
  animationDelay: `${index * 50}ms`,
})

// ============ EXPORTS ============
export { styles as designStyles }
