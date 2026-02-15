import { useState, useRef, ReactNode } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

// ============ Segmented Control ============
// Touch-friendly filter buttons for mutually exclusive options
// Updated to match hybrid industrial-organic design system

interface SegmentOption {
  id: string
  label: string
  shortLabel?: string // For mobile
  count?: number
  icon?: ReactNode
  color?: 'default' | 'accent' | 'green' | 'red' | 'blue' | 'gold'
}

interface SegmentedControlProps {
  options: SegmentOption[]
  value: string
  onChange: (value: string) => void
  size?: 'sm' | 'md'
}

const colorClasses = {
  default: {
    active: 'bg-zinc-800/80 text-zinc-100 border-zinc-600/50',
    inactive: 'text-zinc-500 border-transparent hover:text-zinc-300 hover:bg-zinc-800/40',
  },
  accent: {
    active: 'bg-[var(--accent-500)]/20 text-[var(--accent-400)] border-[var(--accent-500)]/50',
    inactive: 'text-zinc-500 border-transparent hover:text-zinc-300 hover:bg-zinc-800/40',
  },
  green: {
    active: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/50',
    inactive: 'text-zinc-500 border-transparent hover:text-zinc-300 hover:bg-zinc-800/40',
  },
  red: {
    active: 'bg-red-500/20 text-red-400 border-red-500/50',
    inactive: 'text-zinc-500 border-transparent hover:text-zinc-300 hover:bg-zinc-800/40',
  },
  blue: {
    active: 'bg-blue-500/20 text-blue-400 border-blue-500/50',
    inactive: 'text-zinc-500 border-transparent hover:text-zinc-300 hover:bg-zinc-800/40',
  },
  gold: {
    active: 'bg-amber-500/20 text-amber-400 border-amber-500/50',
    inactive: 'text-zinc-500 border-transparent hover:text-zinc-300 hover:bg-zinc-800/40',
  },
}

export function SegmentedControl({ options, value, onChange, size = 'md' }: SegmentedControlProps) {
  const padding = size === 'sm' ? 'px-3 py-2' : 'px-4 py-2.5'
  const text = size === 'sm' ? 'text-xs' : 'text-sm'
  
  return (
    <div className="flex bg-zinc-900/80 border border-zinc-700/50 rounded-2xl p-1.5 overflow-x-auto scrollbar-hide backdrop-blur-sm">
      {options.map((option) => {
        const isActive = value === option.id
        const color = option.color || 'default'
        const classes = isActive ? colorClasses[color].active : colorClasses[color].inactive
        
        return (
          <button
            key={option.id}
            onClick={() => onChange(option.id)}
            className={`flex items-center justify-center gap-2 ${padding} ${text} font-medium rounded-xl border transition-all whitespace-nowrap flex-shrink-0 min-w-[80px] ${classes}`}
          >
            {option.icon && <span className="flex-shrink-0">{option.icon}</span>}
            <span className="hidden sm:inline">{option.label}</span>
            <span className="sm:hidden">{option.shortLabel || option.label}</span>
            {option.count !== undefined && (
              <span className={`font-semibold ${isActive ? '' : 'text-zinc-100'}`}>{option.count}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}


// ============ Stat Scroll Row ============
// Horizontal scrolling stats with snap points for mobile

interface StatItem {
  label: string
  value: string | number
  icon?: ReactNode
  color?: 'default' | 'accent' | 'green' | 'red' | 'blue' | 'gold'
  sublabel?: string
}

interface StatScrollRowProps {
  stats: StatItem[]
  size?: 'sm' | 'md'
}

const statColorClasses = {
  default: 'border-zinc-700/50 bg-zinc-800/40',
  accent: 'border-[var(--accent-500)]/30 bg-[var(--accent-500)]/10',
  green: 'border-emerald-500/30 bg-emerald-500/10',
  red: 'border-red-500/30 bg-red-500/10',
  blue: 'border-blue-500/30 bg-blue-500/10',
  gold: 'border-amber-500/30 bg-amber-500/10',
}

const statValueColors = {
  default: 'text-zinc-100',
  accent: 'text-[var(--accent-400)]',
  green: 'text-emerald-400',
  red: 'text-red-400',
  blue: 'text-blue-400',
  gold: 'text-amber-400',
}

export function StatScrollRow({ stats, size = 'md' }: StatScrollRowProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const padding = size === 'sm' ? 'px-3 py-2' : 'px-4 py-3'
  
  return (
    <div 
      ref={scrollRef}
      className="flex gap-3 overflow-x-auto scrollbar-hide snap-x snap-mandatory pb-1 -mx-4 px-4 sm:mx-0 sm:px-0"
      style={{ WebkitOverflowScrolling: 'touch' }}
    >
      {stats.map((stat, i) => {
        const color = stat.color || 'default'
        return (
          <div
            key={i}
            className={`flex-shrink-0 snap-start ${padding} rounded-2xl border ${statColorClasses[color]} min-w-[120px] sm:min-w-0 sm:flex-1`}
          >
            <div className="flex items-center gap-2 mb-1">
              {stat.icon && <span className="text-zinc-400">{stat.icon}</span>}
              <span className="text-xs text-zinc-400 truncate">{stat.label}</span>
            </div>
            <div className={`text-lg sm:text-xl font-bold ${statValueColors[color]}`}>
              {stat.value}
            </div>
            {stat.sublabel && (
              <div className="text-xs text-zinc-500 mt-0.5">{stat.sublabel}</div>
            )}
          </div>
        )
      })}
    </div>
  )
}


// ============ Collapsible Stats Section ============
// Shows summary on mobile, expands to show all

interface CollapsibleStatsProps {
  title?: string
  summary: ReactNode // Always visible summary
  children: ReactNode // Expanded content
  defaultExpanded?: boolean
}

export function CollapsibleStats({ title, summary, children, defaultExpanded = false }: CollapsibleStatsProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  
  return (
    <div className="bg-zinc-900/80 border border-zinc-700/50 rounded-2xl overflow-hidden backdrop-blur-sm">
      {/* Summary - always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-zinc-800/60 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0">
          {title && <span className="text-xs text-zinc-500 uppercase tracking-wide flex-shrink-0">{title}</span>}
          <div className="text-sm text-zinc-300 truncate">{summary}</div>
        </div>
        <div className="flex-shrink-0 ml-2">
          {expanded ? (
            <ChevronDown className="w-4 h-4 text-zinc-400" />
          ) : (
            <ChevronRight className="w-4 h-4 text-zinc-400" />
          )}
        </div>
      </button>
      
      {/* Expanded content */}
      {expanded && (
        <div className="px-4 pb-4 pt-2 border-t border-zinc-800/50">
          {children}
        </div>
      )}
    </div>
  )
}


// ============ Inline Stats ============
// Compact inline stats for headers/summaries

interface InlineStatProps {
  items: Array<{ label: string; value: string | number; color?: string }>
  separator?: string
}

export function InlineStats({ items, separator = '·' }: InlineStatProps) {
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
      {items.map((item, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && <span className="text-zinc-600 mr-1">{separator}</span>}
          <span className="text-zinc-400">{item.label}</span>
          <span className={`font-semibold ${item.color || 'text-zinc-100'}`}>{item.value}</span>
        </span>
      ))}
    </div>
  )
}


// ============ Stat Pill ============
// Single stat pill with better touch target

interface StatPillProps {
  label: string
  value: string | number
  icon?: ReactNode
  color?: 'default' | 'accent' | 'green' | 'red' | 'blue' | 'gold'
  onClick?: () => void
  active?: boolean
}

export function StatPill({ label, value, icon, color = 'default', onClick, active }: StatPillProps) {
  const baseClasses = 'flex items-center gap-2 px-4 py-3 rounded-2xl border transition-all text-sm'
  const colorClass = active 
    ? colorClasses[color].active 
    : `bg-zinc-800/40 border-zinc-700/50 text-zinc-400 ${onClick ? 'hover:bg-zinc-800/60 cursor-pointer' : ''}`
  
  const Component = onClick ? 'button' : 'div'
  
  return (
    <Component onClick={onClick} className={`${baseClasses} ${colorClass}`}>
      {icon && <span className="flex-shrink-0">{icon}</span>}
      <span>{label}</span>
      <span className={`font-semibold ${active ? '' : 'text-zinc-100'}`}>{value}</span>
    </Component>
  )
}
