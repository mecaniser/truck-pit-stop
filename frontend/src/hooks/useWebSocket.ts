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
import { requestTokenRefresh, requestWorkOSSessionRefresh } from '../lib/authRefresh'
import type { NotificationEvent } from './useNotificationManager'
import type { RepairOrder, RepairOrderDetail } from '../types'

const BASE_RECONNECT_DELAY_MS = 1000
const MAX_RECONNECT_DELAY_MS = 30000
const TERMINAL_CLOSE_CODES = new Set([1000, 1008, 1009, 4002, 4003, 4008])

function getReconnectDelay(attempt: number): number {
  const exponentialDelay = Math.min(
    MAX_RECONNECT_DELAY_MS,
    BASE_RECONNECT_DELAY_MS * (2 ** Math.max(0, attempt))
  )
  const jitter = 0.75 + (Math.random() * 0.5)
  return Math.min(MAX_RECONNECT_DELAY_MS, Math.round(exponentialDelay * jitter))
}

function getWebSocketUrl(): string {
  const apiUrl = String(import.meta.env.VITE_API_URL || '/api/v1').replace(/\/+$/, '')
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'

  if (/^https?:\/\//.test(apiUrl)) {
    return `${apiUrl.replace(/^http/, 'ws')}/ws`
  }

  const apiPath = apiUrl.startsWith('/') ? apiUrl : '/api/v1'
  return `${wsProtocol}//${window.location.host}${apiPath}/ws`
}

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
  | 'mechanic_timer_update'
  | 'mechanic_attendance_update'
  | 'mechanic_break_update'
  | 'mechanic_idle_alert'

export interface WSMessage {
  type: WSEventType
  order_id?: string
  order_number?: string
  status?: string
  hold_reason?: string | null
  held_at?: string | null
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
  mechanic_id?: string
  session_id?: string
  attendance_session_id?: string
  break_session_id?: string
  action?: string
  idle_minutes?: number
  local_date?: string
  mechanic_name?: string
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
  const reconnectAttempt = useRef(0)
  const onNotificationRef = useRef(onNotification)
  const queryClient = useQueryClient()
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  const [isConnected, setIsConnected] = useState(false)
  
  // Track if we should reconnect (false when intentionally disconnecting)
  const shouldReconnect = useRef(true)

  // Notification handlers can legitimately change as a page rerenders. Keep the
  // current callback without making the socket lifecycle depend on its identity.
  onNotificationRef.current = onNotification
  
  const log = useCallback((message: string, ...args: unknown[]) => {
    if (debug) {
      console.log(`[WebSocket] ${message}`, ...args)
    }
  }, [debug])

  const refreshSession = useCallback(async (): Promise<boolean> => {
    const state = useAuthStore.getState()
    try {
      if (state.authProvider === 'workos') {
        await requestWorkOSSessionRefresh()
        return true
      }

      if (state.authProvider !== 'legacy' && !state.refreshToken) {
        log('Session refresh is unavailable')
        return false
      }

      const { access_token, refresh_token } = await requestTokenRefresh(state.refreshToken)
      useAuthStore.getState().setTokens(access_token, refresh_token)
      return true
    } catch {
      log('Session refresh failed')
      return false
    }
  }, [log])
  
  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const data: WSMessage = JSON.parse(event.data)
      log('Received message', data.type)
      
      // Invalidate relevant queries based on event type
      // Note: Backend sends both specific events AND repair_order_update for most actions.
      // Notifications are routed through onNotification callback for centralized handling.
      switch (data.type) {
        case 'repair_order_update':
          if (data.order_id && data.status) {
            queryClient.setQueryData<RepairOrder[] | undefined>(['repair-orders'], (previous) => {
              if (!previous) return previous
              return previous.map((order) => {
                if (order.id !== data.order_id) return order
                const shouldSetHoldReason = Object.prototype.hasOwnProperty.call(data, 'hold_reason')
                const shouldSetHeldAt = Object.prototype.hasOwnProperty.call(data, 'held_at')
                return {
                  ...order,
                  status: data.status as RepairOrder['status'],
                  updated_at: data.updated_at || order.updated_at,
                  hold_reason: shouldSetHoldReason ? (data.hold_reason ?? null) : (order.hold_reason ?? null),
                  held_at: shouldSetHeldAt ? (data.held_at ?? null) : (order.held_at ?? null),
                }
              })
            })
            queryClient.setQueriesData<RepairOrderDetail | undefined>({ queryKey: ['repair-order-detail'] }, (previous) => {
              if (!previous || previous.id !== data.order_id) return previous
              const shouldSetHoldReason = Object.prototype.hasOwnProperty.call(data, 'hold_reason')
              const shouldSetHeldAt = Object.prototype.hasOwnProperty.call(data, 'held_at')
              return {
                ...previous,
                status: data.status as RepairOrderDetail['status'],
                updated_at: data.updated_at || previous.updated_at,
                hold_reason: shouldSetHoldReason ? (data.hold_reason ?? null) : (previous.hold_reason ?? null),
                held_at: shouldSetHeldAt ? (data.held_at ?? null) : (previous.held_at ?? null),
              }
            })
          }
          queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
          queryClient.invalidateQueries({ queryKey: ['repair-order-detail'] })
          queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
          queryClient.invalidateQueries({ queryKey: ['mechanic-history'] })
          // Keep an unmounted dashboard stale without making its queue request
          // from the repair-order workspace. DashboardHome refetches on mount.
          queryClient.invalidateQueries({ queryKey: ['dashboard-action-queue'] })
          queryClient.invalidateQueries({ queryKey: ['activity-feed'] })

          // Route to notification manager
          if (onNotificationRef.current && data.order_number && data.status) {
            onNotificationRef.current({
              type: 'repair_order_update',
              orderId: data.order_id,
              orderNumber: data.order_number,
              status: data.status,
              holdReason: data.hold_reason ?? null,
              heldAt: data.held_at ?? null,
            })
          }
          break
          
        case 'quote_created':
          queryClient.invalidateQueries({ queryKey: ['quotes'] })
          queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
          queryClient.invalidateQueries({ queryKey: ['activity-feed'] })
          if (onNotificationRef.current && data.quote_number) {
            onNotificationRef.current({
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
          queryClient.invalidateQueries({ queryKey: ['dashboard-action-queue'] })
          queryClient.invalidateQueries({ queryKey: ['activity-feed'] })
          if (onNotificationRef.current && data.quote_number) {
            onNotificationRef.current({
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
          queryClient.invalidateQueries({ queryKey: ['dashboard-action-queue'] })
          if (onNotificationRef.current && data.quote_number) {
            onNotificationRef.current({
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
          queryClient.invalidateQueries({ queryKey: ['dashboard-action-queue'] })
          queryClient.invalidateQueries({ queryKey: ['activity-feed'] })
          if (onNotificationRef.current && data.invoice_number) {
            onNotificationRef.current({
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
          queryClient.invalidateQueries({ queryKey: ['dashboard-action-queue'] })
          queryClient.invalidateQueries({ queryKey: ['activity-feed'] })
          if (onNotificationRef.current) {
            onNotificationRef.current({
              type: 'payment_received',
              orderId: data.order_id,
            })
          }
          break

        case 'sms_message_created':
        case 'sms_thread_updated':
          // Inbox pages manage thread/message lists locally; keep global unread summary fresh.
          queryClient.invalidateQueries({ queryKey: ['messages-unread-summary'] })
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('dieselbridge:sms-event', { detail: data }))
          }
          break

        case 'mechanic_timer_update':
          queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
          queryClient.invalidateQueries({ queryKey: ['mechanic-day-summary'] })
          queryClient.invalidateQueries({ queryKey: ['mechanic-board-team'] })
          queryClient.invalidateQueries({ queryKey: ['mechanic-board-detail'] })
          queryClient.invalidateQueries({ queryKey: ['dashboard-action-queue'] })
          break

        case 'mechanic_attendance_update':
        case 'mechanic_break_update':
          queryClient.invalidateQueries({ queryKey: ['mechanic-day-summary'] })
          queryClient.invalidateQueries({ queryKey: ['mechanic-board-team'] })
          queryClient.invalidateQueries({ queryKey: ['mechanic-board-detail'] })
          queryClient.invalidateQueries({ queryKey: ['dashboard-action-queue'] })
          break

        case 'mechanic_idle_alert':
          if (onNotificationRef.current) {
            onNotificationRef.current({
              type: 'mechanic_idle_alert',
              mechanicId: data.mechanic_id,
              mechanicName: data.mechanic_name,
              idleMinutes: data.idle_minutes,
              localDate: data.local_date,
            })
          }
          queryClient.invalidateQueries({ queryKey: ['mechanic-day-summary'] })
          queryClient.invalidateQueries({ queryKey: ['mechanic-board-team'] })
          queryClient.invalidateQueries({ queryKey: ['mechanic-board-detail'] })
          break
      }
    } catch {
      log('Failed to parse message')
    }
  }, [queryClient, log])
  
  const connect = useCallback(() => {
    const state = useAuthStore.getState()
    if (!state.isAuthenticated || !shouldReconnect.current) {
      log('No authenticated session, skipping connection')
      return
    }

    const existingSocket = ws.current
    if (existingSocket && (
      existingSocket.readyState === WebSocket.OPEN
      || existingSocket.readyState === WebSocket.CONNECTING
    )) {
      return
    }

    if (reconnectTimeout.current) {
      clearTimeout(reconnectTimeout.current)
      reconnectTimeout.current = null
    }

    const scheduleReconnect = (code: number, minimumDelay = 0) => {
      if (!shouldReconnect.current || reconnectTimeout.current) return
      const delay = Math.max(getReconnectDelay(reconnectAttempt.current), minimumDelay)
      reconnectAttempt.current += 1
      log(`Connection closed (${code}); retrying in ${delay}ms`)
      reconnectTimeout.current = setTimeout(() => {
        reconnectTimeout.current = null
        connect()
      }, delay)
    }

    log('Connecting')
    
    try {
      const socket = new WebSocket(getWebSocketUrl())
      let hasOpened = false
      ws.current = socket

      socket.onopen = () => {
        if (ws.current !== socket) return
        hasOpened = true
        log('Connected')
        setIsConnected(true)
        authRecoveryAttempted.current = false
        reconnectAttempt.current = 0
        
        // Start ping interval to keep connection alive
        if (pingInterval.current) {
          clearInterval(pingInterval.current)
        }
        pingInterval.current = setInterval(() => {
          if (ws.current === socket && socket.readyState === WebSocket.OPEN) {
            socket.send('ping')
          }
        }, 30000) // Ping every 30 seconds
      }

      socket.onmessage = (event) => {
        if (ws.current === socket) handleMessage(event)
      }

      socket.onclose = (event) => {
        // A deliberately replaced socket must not schedule a second reconnect.
        if (ws.current !== socket) return
        ws.current = null
        log(`Disconnected (${event.code})`)
        setIsConnected(false)
        
        // Clear ping interval
        if (pingInterval.current) {
          clearInterval(pingInterval.current)
          pingInterval.current = null
        }
        
        if (!shouldReconnect.current) return

        // A connection gets one provider-aware refresh recovery. If the
        // recovered connection cannot authenticate before opening, stop.
        if (event.code === 4001 && !authRecoveryAttempted.current) {
          authRecoveryAttempted.current = true
          void (async () => {
            const refreshed = await refreshSession()
            if (
              refreshed
              && shouldReconnect.current
              && useAuthStore.getState().isAuthenticated
            ) {
              connect()
              return
            }
            shouldReconnect.current = false
            useAuthStore.getState().clearSession()
          })()
          return
        }

        if (event.code === 4001) {
          shouldReconnect.current = false
          useAuthStore.getState().clearSession()
          return
        }

        if (TERMINAL_CLOSE_CODES.has(event.code)) {
          shouldReconnect.current = false
          return
        }

        // A browser can report a rejected pre-upgrade Origin as 1006 instead
        // of exposing the server's 4003. Slow-start that ambiguous path so an
        // origin/configuration error cannot create an immediate retry storm.
        scheduleReconnect(event.code, event.code === 1006 && !hasOpened ? 5000 : 0)
      }
      
      socket.onerror = () => {
        // ErrorEvent can include the attempted URL. The close code controls
        // recovery, so never forward the raw browser event to a logger.
        log('Connection error')
      }
    } catch {
      log('Connection could not be created')
      scheduleReconnect(1006, 5000)
    }
  }, [handleMessage, log, refreshSession])
  
  const reconnect = useCallback(() => {
    if (!useAuthStore.getState().isAuthenticated) return
    shouldReconnect.current = true
    authRecoveryAttempted.current = false
    reconnectAttempt.current = 0
    if (reconnectTimeout.current) {
      clearTimeout(reconnectTimeout.current)
      reconnectTimeout.current = null
    }
    if (pingInterval.current) {
      clearInterval(pingInterval.current)
      pingInterval.current = null
    }
    const socket = ws.current
    ws.current = null
    socket?.close()
    setIsConnected(false)
    connect()
  }, [connect])
  
  // Connect when authenticated
  useEffect(() => {
    if (isAuthenticated) {
      shouldReconnect.current = true
      connect()
    }
    
    return () => {
      shouldReconnect.current = false
      
      if (reconnectTimeout.current) {
        clearTimeout(reconnectTimeout.current)
        reconnectTimeout.current = null
      }
      if (pingInterval.current) {
        clearInterval(pingInterval.current)
        pingInterval.current = null
      }
      const socket = ws.current
      ws.current = null
      socket?.close()
      setIsConnected(false)
    }
  }, [isAuthenticated, connect])
  
  // Handle visibility change - reconnect when tab becomes visible
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (!document.hidden && isAuthenticated && !isConnected) {
        log('Tab visible, reconnecting...')
        connect()
      }
    }
    
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [isAuthenticated, isConnected, connect, log])
  
  return { isConnected, reconnect }
}
