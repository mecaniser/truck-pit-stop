/**
 * WebSocket hook for real-time updates.
 * 
 * Connects to the backend WebSocket endpoint and automatically
 * invalidates React Query caches when relevant events are received.
 */
import { useEffect, useRef, useCallback, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../stores/authStore'
import toast from 'react-hot-toast'

// Event types from backend
type WSEventType = 
  | 'repair_order_update'
  | 'quote_created'
  | 'quote_approved'
  | 'quote_declined'
  | 'invoice_created'
  | 'payment_received'

interface WSMessage {
  type: WSEventType
  order_id?: string
  order_number?: string
  status?: string
  quote_id?: string
  quote_number?: string
  invoice_id?: string
  invoice_number?: string
  total_amount?: string
  updated_at?: string
}

interface UseWebSocketOptions {
  /** Show toast notifications for events (default: false) */
  showToasts?: boolean
  /** Enable debug logging (default: false) */
  debug?: boolean
}

interface UseWebSocketReturn {
  /** Whether the WebSocket is currently connected */
  isConnected: boolean
  /** Manually reconnect the WebSocket */
  reconnect: () => void
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const { showToasts = false, debug = false } = options
  const ws = useRef<WebSocket | null>(null)
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pingInterval = useRef<ReturnType<typeof setInterval> | null>(null)
  const queryClient = useQueryClient()
  const { token, isAuthenticated } = useAuthStore()
  const [isConnected, setIsConnected] = useState(false)
  
  // Track if we should reconnect (false when intentionally disconnecting)
  const shouldReconnect = useRef(true)
  
  const log = useCallback((message: string, ...args: unknown[]) => {
    if (debug) {
      console.log(`[WebSocket] ${message}`, ...args)
    }
  }, [debug])
  
  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const data: WSMessage = JSON.parse(event.data)
      log('Received message:', data)
      
      // Invalidate relevant queries based on event type
      // Note: Backend sends both specific events AND repair_order_update for most actions.
      // We show toasts only for specific events to avoid duplicates.
      switch (data.type) {
        case 'repair_order_update':
          queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
          queryClient.invalidateQueries({ queryKey: ['repair-order-detail'] })
          queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
          queryClient.invalidateQueries({ queryKey: ['mechanic-history'] })
          queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
          
          // Only show toast for statuses that don't have their own specific event
          // (invoiced/paid have invoice_created/payment_received events)
          if (showToasts && data.order_number && data.status) {
            const statusLabels: Record<string, string> = {
              assigned: 'Job assigned',
              acknowledged: 'Job acknowledged',
              in_progress: 'Work started',
              pending_review: 'Work completed',
              completed: 'Work approved',
              // Skip these - they have dedicated events
              // invoiced: handled by invoice_created
              // paid: handled by payment_received
              // approved: handled by quote_approved
              // declined: handled by quote_declined
            }
            const label = statusLabels[data.status]
            if (label) {
              toast.success(`${data.order_number}: ${label}`)
            }
          }
          break
          
        case 'quote_created':
          queryClient.invalidateQueries({ queryKey: ['quotes'] })
          queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
          if (showToasts && data.quote_number) {
            toast.success(`Quote ${data.quote_number} ready for review`)
          }
          break
          
        case 'quote_approved':
          queryClient.invalidateQueries({ queryKey: ['quotes'] })
          queryClient.invalidateQueries({ queryKey: ['quote'] })
          queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
          queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
          if (showToasts && data.quote_number) {
            toast.success(`Quote ${data.quote_number} approved`)
          }
          break
          
        case 'quote_declined':
          queryClient.invalidateQueries({ queryKey: ['quotes'] })
          queryClient.invalidateQueries({ queryKey: ['quote'] })
          queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
          if (showToasts && data.quote_number) {
            toast(`Quote ${data.quote_number} declined`, { icon: '⚠️' })
          }
          break
          
        case 'invoice_created':
          queryClient.invalidateQueries({ queryKey: ['invoices'] })
          queryClient.invalidateQueries({ queryKey: ['invoice'] })
          queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
          if (showToasts && data.invoice_number) {
            toast.success(`Invoice ${data.invoice_number} ready`)
          }
          break
          
        case 'payment_received':
          queryClient.invalidateQueries({ queryKey: ['invoices'] })
          queryClient.invalidateQueries({ queryKey: ['invoice'] })
          queryClient.invalidateQueries({ queryKey: ['payments'] })
          queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
          queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
          if (showToasts) {
            toast.success('Payment confirmed!')
          }
          break
      }
    } catch (err) {
      log('Failed to parse message:', err)
    }
  }, [queryClient, showToasts, log])
  
  const connect = useCallback(() => {
    if (!token || !isAuthenticated) {
      log('No token or not authenticated, skipping connection')
      return
    }
    
    // Close existing connection if any
    if (ws.current) {
      ws.current.close()
    }
    
    // Clear any pending reconnect
    if (reconnectTimeout.current) {
      clearTimeout(reconnectTimeout.current)
      reconnectTimeout.current = null
    }
    
    // Build WebSocket URL
    const apiUrl = import.meta.env.VITE_API_URL || ''
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    
    let wsUrl: string
    if (apiUrl.startsWith('http')) {
      // Full URL provided - convert to WebSocket
      wsUrl = apiUrl.replace(/^http/, 'ws') + `/ws?token=${token}`
    } else if (apiUrl.startsWith('/')) {
      // Relative path - use current host
      wsUrl = `${wsProtocol}//${window.location.host}${apiUrl}/ws?token=${token}`
    } else {
      // No API URL - use current host with /api/v1
      wsUrl = `${wsProtocol}//${window.location.host}/api/v1/ws?token=${token}`
    }
    
    log('Connecting to:', wsUrl.replace(token, '[TOKEN]'))
    
    try {
      ws.current = new WebSocket(wsUrl)
      
      ws.current.onopen = () => {
        log('Connected')
        setIsConnected(true)
        
        // Start ping interval to keep connection alive
        if (pingInterval.current) {
          clearInterval(pingInterval.current)
        }
        pingInterval.current = setInterval(() => {
          if (ws.current?.readyState === WebSocket.OPEN) {
            ws.current.send('ping')
          }
        }, 30000) // Ping every 30 seconds
      }
      
      ws.current.onmessage = handleMessage
      
      ws.current.onclose = (event) => {
        log('Disconnected:', event.code, event.reason)
        setIsConnected(false)
        
        // Clear ping interval
        if (pingInterval.current) {
          clearInterval(pingInterval.current)
          pingInterval.current = null
        }
        
        // Reconnect after delay if not intentionally closed
        if (shouldReconnect.current && event.code !== 4001) {
          const delay = event.code === 1006 ? 5000 : 3000 // Longer delay for abnormal closure
          log(`Reconnecting in ${delay}ms...`)
          reconnectTimeout.current = setTimeout(connect, delay)
        }
      }
      
      ws.current.onerror = (error) => {
        log('Error:', error)
      }
    } catch (err) {
      log('Failed to create WebSocket:', err)
    }
  }, [token, isAuthenticated, handleMessage, log])
  
  const reconnect = useCallback(() => {
    shouldReconnect.current = true
    connect()
  }, [connect])
  
  // Connect when authenticated
  useEffect(() => {
    if (isAuthenticated && token) {
      shouldReconnect.current = true
      connect()
    }
    
    return () => {
      shouldReconnect.current = false
      
      if (reconnectTimeout.current) {
        clearTimeout(reconnectTimeout.current)
      }
      if (pingInterval.current) {
        clearInterval(pingInterval.current)
      }
      if (ws.current) {
        ws.current.close()
      }
    }
  }, [isAuthenticated, token, connect])
  
  // Handle visibility change - reconnect when tab becomes visible
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (!document.hidden && isAuthenticated && !isConnected) {
        log('Tab visible, reconnecting...')
        reconnect()
      }
    }
    
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [isAuthenticated, isConnected, reconnect, log])
  
  return { isConnected, reconnect }
}
