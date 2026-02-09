import { LucideIcon } from 'lucide-react'

interface MetricCardProps {
  icon: LucideIcon
  iconColor?: string
  iconBg?: string
  label: string
  value: string | number
  sublabel?: string
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
  trend,
}: MetricCardProps) {
  return (
    <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-4">
      <div className="flex items-start justify-between mb-3">
        <div className={`p-2 ${iconBg} rounded-lg`}>
          <Icon className={`w-5 h-5 ${iconColor}`} />
        </div>
        {trend && (
          <div className={`text-xs font-medium ${trend.direction === 'up' ? 'text-green-400' : 'text-red-400'}`}>
            {trend.direction === 'up' ? '↑' : '↓'} {Math.abs(trend.value)}%
          </div>
        )}
      </div>
      <p className="text-gray-400 text-xs mb-1">{label}</p>
      <p className="text-xl font-bold text-white">{value}</p>
      {sublabel && <p className="text-gray-500 text-xs mt-1">{sublabel}</p>}
    </div>
  )
}
