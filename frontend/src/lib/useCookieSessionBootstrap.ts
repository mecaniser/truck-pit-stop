import { useEffect, useState } from 'react'
import axios from 'axios'
import { mayResumeSignedOutLogin } from './workosLoginReturn'
import { syncStoredSession, useAuthStore } from '../stores/authStore'
import { isSessionRejection } from './sessionRecovery'

/** Revalidate HttpOnly credentials before rendering any protected workspace. */
export function useCookieSessionBootstrap() {
  const { isAuthenticated, explicitlySignedOut, browserSessionId, authSessionEpoch, establishCookieSession } = useAuthStore()
  const blocked = explicitlySignedOut && !mayResumeSignedOutLogin(browserSessionId)
  const [checkingSession, setCheckingSession] = useState(!isAuthenticated && !blocked)
  const [recovering, setRecovering] = useState(false)
  const [endReason, setEndReason] = useState('')
  useEffect(() => {
    if (isAuthenticated || blocked) {
      setCheckingSession(false)
      setRecovering(false)
      return
    }
    let active = true
    let retry: ReturnType<typeof setTimeout> | undefined
    const controller = new AbortController()
    const epoch = useAuthStore.getState().authSessionEpoch
    const current = () => {
      // A peer may have revoked the session before its storage event is delivered.
      syncStoredSession()
      const session = useAuthStore.getState()
      return active && session.authSessionEpoch === epoch && (!session.explicitlySignedOut || mayResumeSignedOutLogin(session.browserSessionId))
    }
    const apiBase = String(import.meta.env.VITE_API_URL || '/api/v1').replace(/\/$/, '')
    const client = axios.create({ withCredentials: true, timeout: 15_000, signal: controller.signal })
    const bootstrap = async () => {
      try {
        const result = await client.get(`${apiBase}/auth/workos/me`).catch(async error => {
          if (!current() || !axios.isAxiosError(error) || error.response?.status !== 401) throw error
          await client.post(`${apiBase}/auth/workos/session/refresh`, {})
          if (!current()) throw error
          return client.get(`${apiBase}/auth/workos/me`)
        })
        if (current()) {
          setRecovering(false)
          establishCookieSession(result.data)
          setCheckingSession(false)
        }
      } catch (error) {
        if (!current() || axios.isCancel(error)) return
        if (isSessionRejection(error)) {
          const detail = (error as { response?: { data?: { detail?: { code?: string } | string } } }).response?.data?.detail
          const code = typeof detail === 'object' ? detail?.code : undefined
          setEndReason(code === 'session_expired' || code === 'session_ended' ? code : '')
          setRecovering(false)
          setCheckingSession(false)
        } else {
          setRecovering(true)
          retry = setTimeout(() => { void bootstrap() }, 5_000)
        }
      }
    }
    void bootstrap()
    return () => { active = false; clearTimeout(retry); controller.abort() }
  }, [establishCookieSession, isAuthenticated, blocked, authSessionEpoch])
  return { checkingSession, recovering, endReason }
}
