import { Link } from 'react-router-dom'
import { Boxes, Clock, X, XCircle } from 'lucide-react'

interface AlertsBannerProps {
  lowStockCount: number
  overdueApprovals?: number
  staleDrafts?: number
  declinedQuotes?: number
  dismissedKeys: Set<string>
  exitingKey: string | null
  onDismiss: (key: string) => void
}

type Pill = {
  key: string
  to: string
  icon: typeof Boxes
  label: string
  tone: string
}

export default function AlertsBanner({
  lowStockCount,
  overdueApprovals = 0,
  staleDrafts = 0,
  declinedQuotes = 0,
  dismissedKeys,
  exitingKey,
  onDismiss,
}: AlertsBannerProps) {
  const pills: Pill[] = [
    lowStockCount > 0 && {
      key: 'lowStock',
      to: '/dashboard/garage/inventory',
      icon: Boxes,
      label: `${lowStockCount} Low Stock`,
      tone: 'bg-red-500/20 border-red-500/30 text-red-300 hover:bg-red-500/30',
    },
    overdueApprovals > 0 && {
      key: 'overdueApprovals',
      to: '/dashboard/repair-orders?status=quoted',
      icon: Clock,
      label: `${overdueApprovals} Overdue Approvals`,
      tone: 'bg-amber-500/20 border-amber-500/30 text-amber-300 hover:bg-amber-500/30',
    },
    staleDrafts > 0 && {
      key: 'staleDrafts',
      to: '/dashboard/repair-orders?status=draft',
      icon: Clock,
      label: `${staleDrafts} Stale Drafts`,
      tone: 'bg-gray-500/20 border-gray-500/30 text-gray-300 hover:bg-gray-500/30',
    },
    declinedQuotes > 0 && {
      key: 'declinedQuotes',
      to: '/dashboard/repair-orders?status=declined',
      icon: XCircle,
      label: `${declinedQuotes} Declined Quotes`,
      tone: 'bg-red-500/20 border-red-500/30 text-red-300 hover:bg-red-500/30',
    },
  ].filter((p): p is Pill => Boolean(p))

  const visiblePills = pills.filter(p => !dismissedKeys.has(p.key) || p.key === exitingKey)

  if (!visiblePills.length) return null

  return (
    <div className="flex flex-wrap gap-2">
      {visiblePills.map(({ key, to, icon: Icon, label, tone }) => (
        <div
          key={key}
          className={`flex items-center gap-1.5 pl-3 pr-1.5 py-1.5 border rounded-lg text-sm ${tone} ${key === exitingKey ? 'attention-pill-exit' : 'attention-pill-enter'}`}
        >
          <Link to={to} className="flex items-center gap-2">
            <Icon className="w-4 h-4" />
            <span>{label}</span>
          </Link>
          <button
            type="button"
            aria-label={`Dismiss ${label}`}
            onClick={() => onDismiss(key)}
            className="ml-1 rounded p-0.5 text-current opacity-60 hover:opacity-100 transition-opacity"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}
    </div>
  )
}
