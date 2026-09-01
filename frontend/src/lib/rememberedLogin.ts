/**
 * "Remember me" convenience storage.
 *
 * This deliberately stores ONLY the email address and the checkbox state, never
 * the password. Persisting a password in the browser would put it in reach of
 * any script on the page; the browser's own password manager (via the form's
 * autoComplete attributes) is the right place for credential re-fill.
 *
 * What "Remember me" actually buys the user:
 *  - a longer server session (7 -> 30 days for legacy), so on return within the
 *    window they land straight in the app with no login screen at all; and
 *  - if the session did lapse, the login form opens with their email already
 *    filled in and the box already checked.
 */

const EMAIL_KEY = 'db.login.rememberedEmail'
const FLAG_KEY = 'db.login.rememberMe'
const METHOD_KEY = 'db.login.lastMethod'

export type LastLoginMethod = 'password' | 'workos'

function safeGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function safeSet(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // Private mode / storage disabled - "remember me" simply won't persist.
  }
}

function safeRemove(key: string): void {
  try {
    window.localStorage.removeItem(key)
  } catch {
    // ignore
  }
}

export interface RememberedLogin {
  email: string
  rememberMe: boolean
}

export function getRememberedLogin(): RememberedLogin {
  const rememberMe = safeGet(FLAG_KEY) === '1'
  const email = rememberMe ? safeGet(EMAIL_KEY) ?? '' : ''
  return { email, rememberMe }
}

/**
 * Persist or clear the remembered email based on the submitted form. Call on a
 * successful password login.
 */
export function updateRememberedLogin(email: string, rememberMe: boolean): void {
  if (rememberMe && email) {
    safeSet(EMAIL_KEY, email)
    safeSet(FLAG_KEY, '1')
  } else {
    safeRemove(EMAIL_KEY)
    safeRemove(FLAG_KEY)
  }
}

export function getLastLoginMethod(): LastLoginMethod | null {
  const value = safeGet(METHOD_KEY)
  return value === 'password' || value === 'workos' ? value : null
}

export function setLastLoginMethod(method: LastLoginMethod): void {
  safeSet(METHOD_KEY, method)
}
