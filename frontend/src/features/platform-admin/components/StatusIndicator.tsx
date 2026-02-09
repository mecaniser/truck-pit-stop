interface StatusIndicatorProps {
  status: 'healthy' | 'warning' | 'error' | 'unknown'
  label: string
  sublabel?: string
}

export default function StatusIndicator({ status, label, sublabel }: StatusIndicatorProps) {
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
    <div className="flex items-center gap-3">
      <div className="relative">
        <div className={`w-3 h-3 rounded-full ${colors[status]}`} />
        {status === 'healthy' && (
          <div className={`absolute inset-0 w-3 h-3 rounded-full ${colors[status]} animate-ping opacity-75`} />
        )}
      </div>
      <div>
        <div className={`font-medium ${textColors[status]}`}>{label}</div>
        {sublabel && <div className="text-xs text-gray-500">{sublabel}</div>}
      </div>
    </div>
  )
}
