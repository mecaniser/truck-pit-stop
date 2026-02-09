import { ReactNode } from 'react'

interface GlassNoirCardProps {
  children: ReactNode
  className?: string
  hover?: boolean
  padding?: 'sm' | 'md' | 'lg'
}

const paddingClasses = {
  sm: 'p-4',
  md: 'p-6',
  lg: 'p-8',
}

export function GlassNoirCard({ 
  children, 
  className = '', 
  hover = false,
  padding = 'md' 
}: GlassNoirCardProps) {
  return (
    <div
      className={`
        bg-black/40 backdrop-blur-xl 
        border border-gold-500/20 
        rounded-xl
        ${paddingClasses[padding]}
        ${hover ? 'transition-all duration-300 hover:border-gold-500/40 hover:shadow-lg hover:shadow-gold-500/10' : ''}
        ${className}
      `}
    >
      {children}
    </div>
  )
}

interface GlassNoirButtonProps {
  children: ReactNode
  onClick?: () => void
  variant?: 'primary' | 'secondary' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
  className?: string
  disabled?: boolean
  type?: 'button' | 'submit'
}

const buttonVariants = {
  primary: 'bg-gold-500 hover:bg-gold-400 text-black font-semibold shadow-lg shadow-gold-500/20',
  secondary: 'bg-gold-500/10 hover:bg-gold-500/20 text-gold-400 border border-gold-500/30',
  ghost: 'hover:bg-gold-500/10 text-gold-400',
}

const buttonSizes = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-4 py-2',
  lg: 'px-6 py-3 text-lg',
}

export function GlassNoirButton({
  children,
  onClick,
  variant = 'primary',
  size = 'md',
  className = '',
  disabled = false,
  type = 'button',
}: GlassNoirButtonProps) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`
        ${buttonVariants[variant]}
        ${buttonSizes[size]}
        rounded-lg transition-all duration-200
        disabled:opacity-50 disabled:cursor-not-allowed
        ${className}
      `}
    >
      {children}
    </button>
  )
}

// Header component for GlassNoir pages
interface GlassNoirHeaderProps {
  title: string
  subtitle?: string
  icon?: ReactNode
  actions?: ReactNode
}

export function GlassNoirHeader({ title, subtitle, icon, actions }: GlassNoirHeaderProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 sm:mb-8">
      <div className="flex items-center gap-3 sm:gap-4 min-w-0">
        {icon && (
          <div className="p-2.5 sm:p-3 bg-gold-500/10 rounded-xl border border-gold-500/20 flex-shrink-0">
            {icon}
          </div>
        )}
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-white truncate">{title}</h1>
          {subtitle && <p className="text-sm sm:text-base text-gray-400 mt-0.5 sm:mt-1 truncate">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex items-center gap-3">{actions}</div>}
    </div>
  )
}

// Stat card for metrics
interface GlassNoirStatProps {
  label: string
  value: string | number
  icon?: ReactNode
  trend?: { value: number; positive: boolean }
  className?: string
}

export function GlassNoirStat({ label, value, icon, trend, className = '' }: GlassNoirStatProps) {
  return (
    <GlassNoirCard hover className={className}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-gray-400 text-sm">{label}</p>
          <p className="text-2xl font-bold text-white mt-1">{value}</p>
          {trend && (
            <p className={`text-sm mt-2 ${trend.positive ? 'text-green-400' : 'text-red-400'}`}>
              {trend.positive ? '↑' : '↓'} {Math.abs(trend.value)}%
            </p>
          )}
        </div>
        {icon && (
          <div className="p-2 bg-gold-500/10 rounded-lg text-gold-400">
            {icon}
          </div>
        )}
      </div>
    </GlassNoirCard>
  )
}

// Badge component
interface GlassNoirBadgeProps {
  children: ReactNode
  variant?: 'gold' | 'success' | 'warning' | 'error' | 'info'
}

const badgeVariants = {
  gold: 'bg-gold-500/10 text-gold-400 border-gold-500/30',
  success: 'bg-green-500/10 text-green-400 border-green-500/30',
  warning: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  error: 'bg-red-500/10 text-red-400 border-red-500/30',
  info: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
}

export function GlassNoirBadge({ children, variant = 'gold' }: GlassNoirBadgeProps) {
  return (
    <span className={`px-2.5 py-1 text-xs font-medium rounded-full border ${badgeVariants[variant]}`}>
      {children}
    </span>
  )
}
