// Only the tab that started organization sign-in may try its cookie session
// again after explicit sign-out. The callback echoes the nonce on success.
const attemptKey = 'db.workos-login-attempt'
const completionParam = 'db_login_completed'
let authorizedReturn: { session: string | null } | undefined

export function beginSignedOutLogin(target: string, session: string | null): string {
  const nonce = crypto.randomUUID()
  sessionStorage.setItem(attemptKey, JSON.stringify({ session, nonce }))
  const url = new URL(target, window.location.origin)
  url.searchParams.set('browser_attempt', nonce)
  return url.href
}

export function captureWorkOSLoginReturn() {
  authorizedReturn = undefined
  const url = new URL(window.location.href)
  const values = url.searchParams.getAll(completionParam)
  if (!values.length) return
  url.searchParams.delete(completionParam)
  window.history.replaceState(window.history.state, '', url)
  try {
    const raw = sessionStorage.getItem(attemptKey)
    sessionStorage.removeItem(attemptKey)
    if (!raw || values.length !== 1 || !values[0]) return
    const attempt = JSON.parse(raw)
    if (attempt.nonce === values[0] && (attempt.session === null || typeof attempt.session === 'string')) {
      authorizedReturn = { session: attempt.session }
    }
  } catch { /* No matching tab-owned sign-in attempt. Keep the sign-out boundary. */ }
}

export function mayResumeSignedOutLogin(session: string | null) {
  return authorizedReturn !== undefined && authorizedReturn.session === session
}
