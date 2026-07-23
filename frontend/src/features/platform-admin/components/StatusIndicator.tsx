interface StatusIndicatorProps {
  status: 'healthy' | 'warning' | 'error' | 'unknown'
  label: string
  sublabel?: string
  compactOnMobile?: boolean
}

export default function StatusIndicator({ status, label, sublabel, compactOnMobile = false }: StatusIndicatorProps) {
  const colors = {
    healthy: 'bg-green-500',
    warning: 'bg-yellow-500',
    error: 'bg-red-500',
    unknown: 'bg-gray-500',
  }

  const textColors = {
    healthy: 'text-green-400',
    warning: 'text-yellow-400',
    error: 'text-red-400',
    unknown: 'text-gray-400',
  }

  return (
    <div className={`flex items-center ${compactOnMobile ? 'gap-2 sm:gap-3' : 'gap-3'}`}>
      <div className="relative shrink-0">
        <div className={`${compactOnMobile ? 'w-2.5 h-2.5 sm:w-3 sm:h-3' : 'w-3 h-3'} rounded-full ${colors[status]}`} />
        {status === 'healthy' && (
          <div className={`absolute inset-0 ${compactOnMobile ? 'w-2.5 h-2.5 sm:w-3 sm:h-3' : 'w-3 h-3'} rounded-full ${colors[status]} animate-ping opacity-75`} />
        )}
      </div>
      <div className="min-w-0">
        <div className={`${compactOnMobile ? 'truncate text-sm sm:text-base' : ''} font-medium ${textColors[status]}`}>{label}</div>
        {sublabel && <div className="text-xs text-gray-500">{sublabel}</div>}
      </div>
    </div>
  )
}
