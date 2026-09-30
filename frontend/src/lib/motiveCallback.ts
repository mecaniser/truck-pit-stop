/** Authorization return data lives only in memory until the callback consumes it. */
interface MotiveReturn { state: string | null; code: string | null; error: string | null }
let pending: MotiveReturn | null = null
export function captureMotiveCallback(): void {
  if (window.location.pathname !== '/fleet/motive/callback' || !window.location.search) return
  const search = new URLSearchParams(window.location.search)
  pending = { state: search.get('state'), code: search.get('code'), error: search.get('error') }
  window.history.replaceState(window.history.state, '', '/fleet/motive/callback')
}
export function takeMotiveCallback(): MotiveReturn {
  captureMotiveCallback()
  const result = pending ?? { state: null, code: null, error: null }
  pending = null
  return result
}
