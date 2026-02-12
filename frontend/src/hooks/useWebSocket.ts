/**
 * WebSocket hook for real-time updates.
 * 
 * Connects to the backend WebSocket endpoint and automatically
 * invalidates React Query caches when relevant events are received.
 * 
 * Notifications are routed through the onNotification callback for
 * centralized handling via useNotificationManager.
 */
import { useEffect, useRef, useCallback, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../stores/authStore'
import { requestTokenRefresh } from '../lib/authRefresh'
import { isTokenExpiredOrNearExpiry } from '../lib/authTokens'
import type { NotificationEvent } from './useNotificationManager'

// Event types from backend
export type WSEventType = 
  | 'repair_order_update'
  | 'quote_created'
  | 'quote_approved'
  | 'quote_declined'
  | 'invoice_created'
  | 'payment_received'
  | 'sms_message_created'
  | 'sms_thread_updated'

export interface WSMessage {
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
  thread_id?: string
  message_id?: string
  customer_id?: string
  delivery_status?: string
}

interface UseWebSocketOptions {
  /** Callback for notification events (use with useNotificationManager) */
  onNotification?: (event: NotificationEvent) => void
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
  const { onNotification, debug = false } = options
  const ws = useRef<WebSocket | null>(null)
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pingInterval = useRef<ReturnType<typeof setInterval> | null>(null)
  const authRecoveryAttempted = useRef(false)
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

  const refreshAccessToken = useCallback(async (): Promise<string | null> => {
    const state = useAuthStore.getState()
    try {
      const { access_token, refresh_token } = await requestTokenRefresh(state.refreshToken)
      useAuthStore.getState().setTokens(access_token, refresh_token)
      return access_token
    } catch (error) {
      log('Token refresh failed for WebSocket connection')
      void useAuthStore.getState().logout()
      return null
    }
  }, [log])
  
  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const data: WSMessage = JSON.parse(event.data)
      log('Received message:', data)
      
      // Invalidate relevant queries based on event type
      // Note: Backend sends both specific events AND repair_order_update for most actions.
      // Notifications are routed through onNotification callback for centralized handling.
      switch (data.type) {
        case 'repair_order_update':
          queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
          queryClient.invalidateQueries({ queryKey: ['repair-order-detail'] })
          queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
          queryClient.invalidateQueries({ queryKey: ['mechanic-history'] })
          queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
          
          // Route to notification manager
          if (onNotification && data.order_number && data.status) {
            onNotification({
              type: 'repair_order_update',
              orderId: data.order_id,
              orderNumber: data.order_number,
              status: data.status,
            })
          }
          break
          
        case 'quote_created':
          queryClient.invalidateQueries({ queryKey: ['quotes'] })
          queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
          if (onNotification && data.quote_number) {
            onNotification({
              type: 'quote_created',
              orderId: data.order_id,
              quoteNumber: data.quote_number,
            })
          }
          break
          
        case 'quote_approved':
          queryClient.invalidateQueries({ queryKey: ['quotes'] })
          queryClient.invalidateQueries({ queryKey: ['quote'] })
          queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
          queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
          if (onNotification && data.quote_number) {
            onNotification({
              type: 'quote_approved',
              orderId: data.order_id,
              quoteNumber: data.quote_number,
            })
          }
          break
          
        case 'quote_declined':
          queryClient.invalidateQueries({ queryKey: ['quotes'] })
          queryClient.invalidateQueries({ queryKey: ['quote'] })
          queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
          if (onNotification && data.quote_number) {
            onNotification({
              type: 'quote_declined',
              orderId: data.order_id,
              quoteNumber: data.quote_number,
            })
          }
          break
          
        case 'invoice_created':
          queryClient.invalidateQueries({ queryKey: ['invoices'] })
          queryClient.invalidateQueries({ queryKey: ['invoice'] })
          queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
          if (onNotification && data.invoice_number) {
            onNotification({
              type: 'invoice_created',
              orderId: data.order_id,
              invoiceNumber: data.invoice_number,
              totalAmount: data.total_amount,
            })
          }
          break
          
        case 'payment_received':
          queryClient.invalidateQueries({ queryKey: ['invoices'] })
          queryClient.invalidateQueries({ queryKey: ['invoice'] })
          queryClient.invalidateQueries({ queryKey: ['payments'] })
          queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
          queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
          if (onNotification) {
            onNotification({
              type: 'payment_received',
              orderId: data.order_id,
            })
          }
          break

        case 'sms_message_created':
        case 'sms_thread_updated':
          queryClient.invalidateQueries({ queryKey: ['message-threads'] })
          queryClient.invalidateQueries({ queryKey: ['thread-messages'] })
          break
      }
    } catch (err) {
      log('Failed to parse message:', err)
    }
  }, [queryClient, onNotification, log])
  
  const connect = useCallback(async () => {
    const state = useAuthStore.getState()
    if (!state.token || !state.isAuthenticated) {
      log('No token or not authenticated, skipping connection')
      return
    }

    let activeToken = state.token
    if (isTokenExpiredOrNearExpiry(activeToken)) {
      log('Access token expired/near expiry, refreshing before WebSocket connect')
      const refreshedToken = await refreshAccessToken()
      if (!refreshedToken) {
        log('Unable to refresh token for WebSocket connection')
        return
      }
      activeToken = refreshedToken
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
      wsUrl = apiUrl.replace(/^http/, 'ws') + `/ws?token=${encodeURIComponent(activeToken)}`
    } else if (apiUrl.startsWith('/')) {
      // Relative path - use current host
      wsUrl = `${wsProtocol}//${window.location.host}${apiUrl}/ws?token=${encodeURIComponent(activeToken)}`
    } else {
      // No API URL - use current host with /api/v1
      wsUrl = `${wsProtocol}//${window.location.host}/api/v1/ws?token=${encodeURIComponent(activeToken)}`
    }
    
    log('Connecting to:', wsUrl.replace(encodeURIComponent(activeToken), '[TOKEN]'))
    
    try {
      ws.current = new WebSocket(wsUrl)
      
      ws.current.onopen = () => {
        log('Connected')
        setIsConnected(true)
        authRecoveryAttempted.current = false
        
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
        
        // If auth failed, attempt one refresh + reconnect before giving up.
        if (shouldReconnect.current && event.code === 4001 && !authRecoveryAttempted.current) {
          authRecoveryAttempted.current = true
          void (async () => {
            const refreshedToken = await refreshAccessToken()
            if (refreshedToken && shouldReconnect.current) {
              reconnectTimeout.current = setTimeout(() => {
                void connect()
              }, 500)
            }
          })()
          return
        }

        // Reconnect after delay if not intentionally closed and not auth failure.
        if (shouldReconnect.current && event.code !== 4001) {
          const delay = event.code === 1006 ? 5000 : 3000 // Longer delay for abnormal closure
          log(`Reconnecting in ${delay}ms...`)
          reconnectTimeout.current = setTimeout(() => {
            void connect()
          }, delay)
        }
      }
      
      ws.current.onerror = (error) => {
        log('Error:', error)
      }
    } catch (err) {
      log('Failed to create WebSocket:', err)
    }
  }, [handleMessage, log, isTokenExpiredOrNearExpiry, refreshAccessToken])
  
  const reconnect = useCallback(() => {
    shouldReconnect.current = true
    void connect()
  }, [connect])
  
  // Connect when authenticated
  useEffect(() => {
    if (isAuthenticated && token) {
      shouldReconnect.current = true
      void connect()
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
