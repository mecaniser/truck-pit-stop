import { LucideIcon } from 'lucide-react'

interface MetricCardProps {
  icon: LucideIcon
  iconColor?: string
  iconBg?: string
  label: string
  value: string | number
  sublabel?: string
  compactOnMobile?: boolean
  trend?: {
    value: number
    direction: 'up' | 'down'
  }
}

export default function MetricCard({
  icon: Icon,
  iconColor = 'text-amber-400',
  iconBg = 'bg-amber-500/10',
  label,
  value,
  sublabel,
  compactOnMobile = false,
  trend,
}: MetricCardProps) {
  return (
    <div className={`min-w-0 bg-gray-800/50 border border-gray-700/50 rounded-lg ${compactOnMobile ? 'p-3 sm:p-4' : 'p-4'}`}>
      <div className={`flex justify-between ${compactOnMobile ? 'items-center mb-2 sm:items-start sm:mb-3' : 'items-start mb-3'}`}>
        <div className={compactOnMobile ? 'flex min-w-0 items-center gap-2 sm:block' : ''}>
          <div className={`${compactOnMobile ? 'p-1.5 sm:p-2' : 'p-2'} ${iconBg} rounded-lg`}>
            <Icon className={`${compactOnMobile ? 'w-4 h-4 sm:w-5 sm:h-5' : 'w-5 h-5'} ${iconColor}`} />
          </div>
          {compactOnMobile && (
            <p className="truncate text-gray-400 text-[11px] leading-4 sm:hidden">{label}</p>
          )}
        </div>
        {trend && (
          <div className={`text-xs font-medium ${trend.direction === 'up' ? 'text-green-400' : 'text-red-400'}`}>
            {trend.direction === 'up' ? '↑' : '↓'} {Math.abs(trend.value)}%
          </div>
        )}
      </div>
      <p className={`text-gray-400 text-xs mb-1 ${compactOnMobile ? 'hidden sm:block' : ''}`}>{label}</p>
      <p className={`${compactOnMobile ? 'text-lg sm:text-xl' : 'text-xl'} leading-tight font-bold text-white`}>{value}</p>
      {sublabel && (
        <p className={`${compactOnMobile ? 'hidden sm:block sm:text-xs' : 'text-xs'} text-gray-500 mt-1`}>
          {sublabel}
        </p>
      )}
    </div>
  )
}
