import { useAuthStore } from '../stores/authStore'
import { decodeJwtPayload } from './authTokens'
import { requestTokenRefresh, requestWorkOSSessionRefresh } from './authRefresh'

/**
 * Proactive session keep-alive.
 *
 * The workspace is meant to stay open all day. Both auth systems hand the
 * browser only a short-lived local access credential (a ~15-minute WorkOS
 * access cookie, or a ~30-minute legacy access token) backed by a multi-day
 * server session. Historically the app only renewed *reactively* on a 401, so
 * an idle-but-focused tab would ride an expired credential and the first action
 * after the gap could bounce the user to the login screen.
 *
 * This scheduler renews the credential well before it expires, and also on tab
 * refocus and network recovery. It is single-flight within the tab and across
 * tabs (via BroadcastChannel), so a browser with five tabs open performs one
 * renewal, not five racing ones.
 */

// Renew when this fraction of the access-credential lifetime has elapsed.
const RENEW_AT_LIFETIME_FRACTION = 0.65
// Fallback cadence when we cannot read an expiry from the token (e.g. the
// WorkOS access cookie is HttpOnly and invisible to JS).
const DEFAULT_WORKOS_ACCESS_SECONDS = 15 * 60
const DEFAULT_LEGACY_ACCESS_SECONDS = 30 * 60
// Never schedule further out than this, and never sooner than this.
const MAX_DELAY_MS = 20 * 60 * 1000
const MIN_DELAY_MS = 20 * 1000
// After a failed renewal, retry on this backoff before giving up.
const RETRY_BACKOFF_MS = [5_000, 15_000, 45_000]

const CHANNEL_NAME = 'db-session-keepalive'

let timer: ReturnType<typeof setTimeout> | null = null
let running = false
let inFlight: Promise<void> | null = null
let retryIndex = 0
let channel: BroadcastChannel | null = null
let lastRenewAtMs = 0

function now(): number {
  return Date.now()
}

function getChannel(): BroadcastChannel | null {
  if (channel) return channel
  if (typeof BroadcastChannel === 'undefined') return null
  try {
    channel = new BroadcastChannel(CHANNEL_NAME)
    channel.onmessage = (event: MessageEvent) => {
      if (event.data?.type === 'renewed' && typeof event.data.at === 'number') {
        // Another tab just renewed the shared cookie. Reset our schedule so we
        // don't also hit the server.
        lastRenewAtMs = event.data.at
        retryIndex = 0
        scheduleNext()
      }
    }
  } catch {
    channel = null
  }
  return channel
}

function announceRenewed(): void {
  lastRenewAtMs = now()
  try {
    getChannel()?.postMessage({ type: 'renewed', at: lastRenewAtMs })
  } catch {
    // ignore
  }
}

function accessTokenSecondsRemaining(): number | null {
  const token = useAuthStore.getState().token
  if (!token) return null
  const payload = decodeJwtPayload(token)
  if (!payload?.exp) return null
  return payload.exp - Math.floor(now() / 1000)
}

function computeDelayMs(): number {
  const provider = useAuthStore.getState().authProvider
  const remaining = accessTokenSecondsRemaining()

  if (remaining != null) {
    // We can see the legacy access token: renew at the configured fraction of
    // whatever life is left, clamped.
    const lifetime = provider === 'workos' ? DEFAULT_WORKOS_ACCESS_SECONDS : DEFAULT_LEGACY_ACCESS_SECONDS
    const renewAfter = Math.min(remaining, lifetime) * RENEW_AT_LIFETIME_FRACTION
    return clampDelay(renewAfter * 1000)
  }

  // No visible expiry (WorkOS HttpOnly cookie). Use a fixed fraction of the
  // assumed lifetime, measured from the last known renewal.
  const assumedLifetime =
    provider === 'workos' ? DEFAULT_WORKOS_ACCESS_SECONDS : DEFAULT_LEGACY_ACCESS_SECONDS
  const elapsedSinceRenew = lastRenewAtMs ? (now() - lastRenewAtMs) / 1000 : 0
  const renewAfter = assumedLifetime * RENEW_AT_LIFETIME_FRACTION - elapsedSinceRenew
  return clampDelay(renewAfter * 1000)
}

function clampDelay(ms: number): number {
  if (!Number.isFinite(ms)) return MIN_DELAY_MS
  return Math.max(MIN_DELAY_MS, Math.min(MAX_DELAY_MS, ms))
}

function clearTimer(): void {
  if (timer) {
    clearTimeout(timer)
    timer = null
  }
}

function scheduleNext(delayMs?: number): void {
  if (!running) return
  clearTimer()
  const delay = delayMs ?? computeDelayMs()
  timer = setTimeout(() => {
    // The scheduled tick may coincide with another tab's renewal; honor the
    // cross-tab "renewed very recently" skip only on this path.
    void renewNow({ respectRecentRenewal: true })
  }, delay)
}

async function performRenewal(): Promise<void> {
  const provider = useAuthStore.getState().authProvider
  if (provider === 'workos') {
    await requestWorkOSSessionRefresh()
    return
  }
  const refreshToken = useAuthStore.getState().refreshToken
  const { access_token, refresh_token } = await requestTokenRefresh(refreshToken)
  useAuthStore.getState().setTokens(access_token, refresh_token)
}

async function renewNow(options: { respectRecentRenewal?: boolean } = {}): Promise<void> {
  if (!running) return
  if (!useAuthStore.getState().isAuthenticated) return
  if (useAuthStore.getState().logoutInProgress) return

  // Single-flight within this tab.
  if (inFlight) return inFlight

  // Timer-driven ticks defer to a sibling tab that just renewed the shared
  // cookie. Explicit triggers (focus, network recovery, manual recovery) always
  // proceed.
  if (options.respectRecentRenewal && lastRenewAtMs && now() - lastRenewAtMs < MIN_DELAY_MS) {
    scheduleNext()
    return
  }

  inFlight = (async () => {
    try {
      await performRenewal()
      retryIndex = 0
      announceRenewed()
      scheduleNext()
    } catch (error) {
      const status = getErrorStatus(error)
      if (status === 401 || status === 403) {
        // The server session itself is gone. Hand off to the app's normal
        // logout/redirect path; the 401 interceptor handles UX.
        stopSessionKeepAlive()
        void useAuthStore.getState().logout()
        return
      }
      // Transient (network blip, 5xx, rate limit). Back off and retry rather
      // than logging the user out of an all-day workspace.
      if (retryIndex < RETRY_BACKOFF_MS.length) {
        const backoff = RETRY_BACKOFF_MS[retryIndex]
        retryIndex += 1
        scheduleNext(backoff)
      } else {
        retryIndex = 0
        scheduleNext()
      }
    } finally {
      inFlight = null
    }
  })()

  return inFlight
}

function getErrorStatus(error: unknown): number | undefined {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const response = (error as { response?: { status?: number } }).response
    return response?.status
  }
  return undefined
}

/**
 * True when enough of the access credential's life has elapsed that we should
 * renew now rather than wait for the scheduled tick. For the WorkOS path (no
 * JS-visible expiry) this is time-since-last-renewal against the assumed
 * lifetime; for legacy it reads the token's `exp`.
 */
function isDueForRenewal(): boolean {
  const provider = useAuthStore.getState().authProvider
  const remaining = accessTokenSecondsRemaining()
  const assumedLifetime =
    provider === 'workos' ? DEFAULT_WORKOS_ACCESS_SECONDS : DEFAULT_LEGACY_ACCESS_SECONDS

  if (remaining != null) {
    return remaining <= assumedLifetime * (1 - RENEW_AT_LIFETIME_FRACTION)
  }
  if (!lastRenewAtMs) return true
  const elapsed = (now() - lastRenewAtMs) / 1000
  return elapsed >= assumedLifetime * RENEW_AT_LIFETIME_FRACTION
}

function onVisibilityChange(): void {
  // Only renew on refocus if the credential is actually aging out. Alt-tabbing
  // every few minutes must not trigger a refresh storm.
  if (document.visibilityState === 'visible' && isDueForRenewal()) {
    void renewNow()
  }
}

function onOnline(): void {
  if (isDueForRenewal()) {
    void renewNow()
  }
}

/**
 * Start the scheduler. Idempotent. Call after a successful login or session
 * bootstrap. `initialRenewAtMs` seeds "last renewal" so the first proactive
 * renewal is timed from when the session was actually established.
 */
export function startSessionKeepAlive(initialRenewAtMs: number = now()): void {
  if (running) {
    // Already running; just re-baseline and reschedule.
    lastRenewAtMs = initialRenewAtMs
    retryIndex = 0
    scheduleNext()
    return
  }
  running = true
  lastRenewAtMs = initialRenewAtMs
  retryIndex = 0
  getChannel()
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onVisibilityChange)
  }
  if (typeof window !== 'undefined') {
    window.addEventListener('online', onOnline)
  }
  scheduleNext()
}

/** Stop the scheduler and detach listeners. Idempotent. */
export function stopSessionKeepAlive(): void {
  running = false
  clearTimer()
  inFlight = null
  retryIndex = 0
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', onVisibilityChange)
  }
  if (typeof window !== 'undefined') {
    window.removeEventListener('online', onOnline)
  }
}

/** Force an immediate renewal (used by tests and manual recovery paths). */
export function renewSessionNow(): Promise<void> {
  return renewNow()
}

/** Test-only: report whether the scheduler is active. */
export function isSessionKeepAliveRunning(): boolean {
  return running
}
