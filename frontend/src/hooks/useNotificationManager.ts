/**
 * Notification Manager Hook
 * 
 * Provides queued, deduplicated, role-filtered notifications.
 * - Queue: Process one toast at a time with delay between
 * - Deduplication: Same order_id within window replaces previous
 * - Role filtering: Mechanics only see job events, not financial
 */
import { useCallback, useRef, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { useAuthStore } from '../stores/authStore'

// Event types that can trigger notifications
export type NotificationEventType =
  | 'repair_order_update'
  | 'quote_created'
  | 'quote_approved'
  | 'quote_declined'
  | 'invoice_created'
  | 'payment_received'
  | 'mechanic_idle_alert'

export type NotificationPriority = 'high' | 'medium' | 'low'

export interface NotificationEvent {
  type: NotificationEventType
  orderId?: string
  orderNumber?: string
  status?: string
  quoteNumber?: string
  invoiceNumber?: string
  totalAmount?: string
  mechanicId?: string
  mechanicName?: string
  idleMinutes?: number
  localDate?: string
}

interface QueuedNotification {
  id: string
  message: string
  priority: NotificationPriority
  orderId?: string
  timestamp: number
  icon?: string
}

interface BannerNotification {
  id: string
  orderId: string
  orderNumber: string
  message: string
  type: NotificationEventType
  status?: string
  timestamp: number
}

interface UseNotificationManagerOptions {
  /** Enable toast notifications (default: true) */
  showToasts?: boolean
  /** Delay between queued toasts in ms (default: 800) */
  toastDelay?: number
  /** Deduplication window in ms (default: 2000) */
  dedupeWindow?: number
}

interface UseNotificationManagerReturn {
  /** Process an incoming notification event */
  notify: (event: NotificationEvent) => void
  /** Current banner notifications for contextual display */
  banners: BannerNotification[]
  /** Dismiss a banner by id */
  dismissBanner: (id: string) => void
  /** Clear all banners */
  clearBanners: () => void
}

// Status labels for repair order updates
const STATUS_LABELS: Record<string, string> = {
  assigned: 'Job assigned',
  acknowledged: 'Job acknowledged',
  in_progress: 'Work started',
  pending_review: 'Work completed',
  completed: 'Work approved',
}

// Events that mechanics should NOT see (financial/administrative)
const MECHANIC_EXCLUDED_EVENTS: NotificationEventType[] = [
  'quote_created',
  'quote_approved',
  'quote_declined',
  'invoice_created',
  'payment_received',
]

// Statuses that mechanics should NOT see
const MECHANIC_EXCLUDED_STATUSES = ['invoiced', 'paid', 'approved', 'declined']

export function useNotificationManager(
  options: UseNotificationManagerOptions = {}
): UseNotificationManagerReturn {
  const { showToasts = true, toastDelay = 800, dedupeWindow = 2000 } = options
  
  const { user } = useAuthStore()
  const isMechanic = user?.role === 'mechanic'
  
  // Queue state
  const queue = useRef<QueuedNotification[]>([])
  const isProcessing = useRef(false)
  const processingTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)
  
  // Banner state
  const [banners, setBanners] = useState<BannerNotification[]>([])
  
  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (processingTimeout.current) {
        clearTimeout(processingTimeout.current)
      }
    }
  }, [])
  
  // Process the notification queue
  const processQueue = useCallback(() => {
    if (isProcessing.current || queue.current.length === 0) return
    
    isProcessing.current = true
    const notification = queue.current.shift()!
    
    // Show toast for high priority
    if (notification.priority === 'high' && showToasts) {
      if (notification.icon) {
        toast(notification.message, { 
          id: notification.id,
          icon: notification.icon,
        })
      } else {
        toast.success(notification.message, { id: notification.id })
      }
    }
    
    // Schedule next processing
    processingTimeout.current = setTimeout(() => {
      isProcessing.current = false
      processQueue()
    }, toastDelay)
  }, [showToasts, toastDelay])
  
  // Add notification to queue with deduplication
  const addToQueue = useCallback((notification: QueuedNotification) => {
    const now = Date.now()
    
    // Dedupe: if same orderId exists within window, replace it
    if (notification.orderId) {
      const existingIdx = queue.current.findIndex(
        n => n.orderId === notification.orderId && 
             now - n.timestamp < dedupeWindow
      )
      if (existingIdx >= 0) {
        queue.current[existingIdx] = notification
        return
      }
    }
    
    queue.current.push(notification)
    processQueue()
  }, [dedupeWindow, processQueue])
  
  // Add banner notification
  const addBanner = useCallback((banner: Omit<BannerNotification, 'id' | 'timestamp'>) => {
    const id = `${banner.orderId}-${banner.type}-${Date.now()}`
    setBanners(prev => {
      // Remove existing banner for same order if exists
      const filtered = prev.filter(b => b.orderId !== banner.orderId)
      return [...filtered, { ...banner, id, timestamp: Date.now() }]
    })
  }, [])
  
  // Dismiss a banner
  const dismissBanner = useCallback((id: string) => {
    setBanners(prev => prev.filter(b => b.id !== id))
  }, [])
  
  // Clear all banners
  const clearBanners = useCallback(() => {
    setBanners([])
  }, [])
  
  // Main notify function
  const notify = useCallback((event: NotificationEvent) => {
    // Filter out events mechanics shouldn't see
    if (isMechanic) {
      if (MECHANIC_EXCLUDED_EVENTS.includes(event.type)) {
        return
      }
      if (event.type === 'repair_order_update' && 
          event.status && 
          MECHANIC_EXCLUDED_STATUSES.includes(event.status)) {
        return
      }
    }
    
    const timestamp = Date.now()
    const orderId = event.orderId
    
    switch (event.type) {
      case 'repair_order_update': {
        if (!event.orderNumber || !event.status) return
        
        const label = STATUS_LABELS[event.status]
        if (!label) return // Skip statuses without labels (invoiced, paid, etc.)
        
        const message = `${event.orderNumber}: ${label}`
        
        // For mechanics: all job updates are high priority toasts
        // For owners: assigned/completed are toasts, others are banners
        if (isMechanic) {
          addToQueue({
            id: `${orderId}-${event.status}`,
            message,
            priority: 'high',
            orderId,
            timestamp,
          })
        } else {
          // Owner/admin: assigned and completed are toasts
          const isHighPriority = ['assigned', 'completed', 'pending_review'].includes(event.status)
          if (isHighPriority) {
            addToQueue({
              id: `${orderId}-${event.status}`,
              message,
              priority: 'high',
              orderId,
              timestamp,
            })
          } else {
            // Medium priority: add as banner
            addBanner({
              orderId: orderId || '',
              orderNumber: event.orderNumber,
              message: label,
              type: event.type,
              status: event.status,
            })
          }
        }
        break
      }
      
      case 'quote_created': {
        if (!event.quoteNumber) return
        addToQueue({
          id: `quote-${event.quoteNumber}`,
          message: `Quote ${event.quoteNumber} ready for review`,
          priority: 'high',
          orderId,
          timestamp,
        })
        break
      }
      
      // These events have corresponding API toasts, so no WebSocket toast needed.
      // WebSocket still triggers query invalidation in useWebSocket.ts for data freshness.
      case 'quote_approved':
      case 'quote_declined':
      case 'invoice_created':
      case 'payment_received':
        return

      case 'mechanic_idle_alert': {
        const idleMinutes = event.idleMinutes || 0
        const mechanicLabel = event.mechanicName || (event.mechanicId ? `Mechanic ${event.mechanicId.slice(0, 8)}` : 'Mechanic')
        const message = `${mechanicLabel} idle for ${idleMinutes}m`
        addToQueue({
          id: `idle-${event.mechanicId || 'unknown'}-${event.localDate || Date.now()}`,
          message,
          priority: 'high',
          timestamp,
        })
        break
      }
    }
  }, [isMechanic, addToQueue, addBanner])
  
  return {
    notify,
    banners,
    dismissBanner,
    clearBanners,
  }
}
