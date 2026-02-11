/**
 * NotificationBanner Component
 * 
 * Displays contextual, dismissible notification banners for medium-priority events.
 * Used instead of toasts for status updates that benefit from on-screen persistence.
 */
import { X, CheckCircle, Clock, Wrench, FileText, CreditCard, AlertTriangle } from 'lucide-react'
import { useEffect } from 'react'

export interface BannerAction {
  label: string
  onClick: () => void
}

export interface NotificationBannerItem {
  id: string
  orderId: string
  orderNumber: string
  message: string
  type: string
  status?: string
  timestamp: number
}

interface NotificationBannerProps {
  banners: NotificationBannerItem[]
  onDismiss: (id: string) => void
  onDismissAll?: () => void
  /** Optional action buttons per banner type */
  actions?: Record<string, BannerAction>
  /** Auto-dismiss after ms (0 = never) */
  autoDismissMs?: number
}

// Get icon based on event type/status
function getBannerIcon(type: string, status?: string) {
  if (type === 'repair_order_update') {
    switch (status) {
      case 'assigned':
        return <Wrench className="w-4 h-4" />
      case 'acknowledged':
      case 'in_progress':
        return <Clock className="w-4 h-4" />
      case 'pending_review':
      case 'completed':
        return <CheckCircle className="w-4 h-4" />
      default:
        return <FileText className="w-4 h-4" />
    }
  }
  
  switch (type) {
    case 'quote_created':
    case 'quote_approved':
      return <FileText className="w-4 h-4" />
    case 'quote_declined':
      return <AlertTriangle className="w-4 h-4" />
    case 'invoice_created':
      return <FileText className="w-4 h-4" />
    case 'payment_received':
      return <CreditCard className="w-4 h-4" />
    default:
      return <CheckCircle className="w-4 h-4" />
  }
}

// Get banner color scheme based on type/status
function getBannerColors(type: string, status?: string): string {
  if (type === 'quote_declined') {
    return 'bg-amber-500/10 border-amber-500/30 text-amber-300'
  }
  
  if (type === 'repair_order_update') {
    switch (status) {
      case 'pending_review':
      case 'completed':
        return 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
      case 'in_progress':
        return 'bg-blue-500/10 border-blue-500/30 text-blue-300'
      default:
        return 'bg-purple-500/10 border-purple-500/30 text-purple-300'
    }
  }
  
  if (type === 'payment_received') {
    return 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
  }
  
  return 'bg-purple-500/10 border-purple-500/30 text-purple-300'
}

export default function NotificationBanner({
  banners,
  onDismiss,
  onDismissAll,
  actions,
  autoDismissMs = 10000,
}: NotificationBannerProps) {
  // Auto-dismiss banners after their remaining display time.
  useEffect(() => {
    if (autoDismissMs > 0) {
      const timers = banners.map(banner => {
        const age = Date.now() - banner.timestamp
        const remaining = Math.max(0, autoDismissMs - age)
        return setTimeout(() => onDismiss(banner.id), remaining)
      })
      
      return () => timers.forEach(clearTimeout)
    }
  }, [banners, autoDismissMs, onDismiss])
  
  if (banners.length === 0) return null
  
  return (
    <div className="space-y-2 mb-4">
      {banners.length > 1 && onDismissAll && (
        <div className="flex justify-end">
          <button
            onClick={onDismissAll}
            className="text-xs text-gray-400 hover:text-white transition-colors"
          >
            Dismiss all
          </button>
        </div>
      )}
      
      {banners.map(banner => {
        const colors = getBannerColors(banner.type, banner.status)
        const icon = getBannerIcon(banner.type, banner.status)
        const action = actions?.[banner.type] || actions?.[banner.status || '']
        
        return (
          <div
            key={banner.id}
            className={`flex items-center justify-between gap-3 px-4 py-3 rounded-lg border ${colors} animate-in slide-in-from-top-2 duration-200`}
          >
            <div className="flex items-center gap-3 min-w-0">
              {icon}
              <div className="min-w-0">
                <span className="font-medium">{banner.orderNumber}</span>
                <span className="mx-2 opacity-50">·</span>
                <span className="opacity-90">{banner.message}</span>
              </div>
            </div>
            
            <div className="flex items-center gap-2 shrink-0">
              {action && (
                <button
                  onClick={action.onClick}
                  className="px-3 py-1 text-sm bg-white/10 hover:bg-white/20 rounded-md transition-colors"
                >
                  {action.label}
                </button>
              )}
              <button
                onClick={() => onDismiss(banner.id)}
                className="p-1 hover:bg-white/10 rounded transition-colors"
                aria-label="Dismiss"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
