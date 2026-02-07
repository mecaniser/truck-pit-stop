import { Link } from 'react-router-dom'
import { AlertTriangle, Boxes, Clock, X, XCircle } from 'lucide-react'
import { useState } from 'react'

interface AlertsBannerProps {
  lowStockCount: number
  overdueApprovals?: number
  staleDrafts?: number
  declinedQuotes?: number
}

export default function AlertsBanner({
  lowStockCount,
  overdueApprovals = 0,
  staleDrafts = 0,
  declinedQuotes = 0,
}: AlertsBannerProps) {
  const [dismissed, setDismissed] = useState(false)

  const hasAlerts = lowStockCount > 0 || overdueApprovals > 0 || staleDrafts > 0 || declinedQuotes > 0

  if (!hasAlerts || dismissed) return null

  return (
    <div className="bg-gradient-to-r from-amber-500/10 via-red-500/10 to-amber-500/10 border border-amber-500/20 rounded-xl p-3 sm:p-4">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 text-amber-400">
          <AlertTriangle className="w-5 h-5 shrink-0" />
          <span className="text-sm font-medium">Attention Required</span>
        </div>
        <button
          onClick={() => setDismissed(true)}
          className="text-gray-400 hover:text-white transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex flex-wrap gap-3 mt-3">
        {lowStockCount > 0 && (
          <Link
            to="/dashboard/garage/inventory"
            className="flex items-center gap-2 px-3 py-1.5 bg-red-500/20 border border-red-500/30 rounded-lg text-sm text-red-300 hover:bg-red-500/30 transition-colors"
          >
            <Boxes className="w-4 h-4" />
            <span>{lowStockCount} Low Stock</span>
          </Link>
        )}

        {overdueApprovals > 0 && (
          <Link
            to="/dashboard/repair-orders?status=quoted"
            className="flex items-center gap-2 px-3 py-1.5 bg-amber-500/20 border border-amber-500/30 rounded-lg text-sm text-amber-300 hover:bg-amber-500/30 transition-colors"
          >
            <Clock className="w-4 h-4" />
            <span>{overdueApprovals} Overdue Approvals</span>
          </Link>
        )}

        {staleDrafts > 0 && (
          <Link
            to="/dashboard/repair-orders?status=draft"
            className="flex items-center gap-2 px-3 py-1.5 bg-gray-500/20 border border-gray-500/30 rounded-lg text-sm text-gray-300 hover:bg-gray-500/30 transition-colors"
          >
            <Clock className="w-4 h-4" />
            <span>{staleDrafts} Stale Drafts</span>
          </Link>
        )}

        {declinedQuotes > 0 && (
          <Link
            to="/dashboard/repair-orders?status=declined"
            className="flex items-center gap-2 px-3 py-1.5 bg-red-500/20 border border-red-500/30 rounded-lg text-sm text-red-300 hover:bg-red-500/30 transition-colors"
          >
            <XCircle className="w-4 h-4" />
            <span>{declinedQuotes} Declined Quotes</span>
          </Link>
        )}
      </div>
    </div>
  )
}
