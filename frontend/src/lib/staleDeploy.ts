import { create } from 'zustand'

/**
 * A deploy replaces every content-hashed asset, so a tab still running the
 * previous build asks for chunk filenames that no longer exist. The first
 * symptom is a lazy route failing to import — the page is simply dead, with
 * only a console error to show for it. Nothing here can recover the old
 * assets; the honest remedy is to tell the person a new version shipped and
 * reload into it.
 */
export const useStaleDeploy = create<{ stale: boolean; handled: boolean }>(() => ({
  stale: false,
  // Set when a full-page boundary is already showing the message, so the
  // floating notice does not repeat it.
  handled: false,
}))

export function markStaleDeploy(): void {
  useStaleDeploy.setState({ stale: true })
}

export function resetStaleDeploy(): void {
  useStaleDeploy.setState({ stale: false, handled: false })
}

/** Claims the stale-deploy message for a full-page surface. */
export function markStaleDeployHandled(): void {
  useStaleDeploy.setState({ stale: true, handled: true })
}

// Each engine words the failure differently, and a stale stylesheet surfaces
// as a MIME-type refusal because missing assets fall through to the API, which
// answers JSON. Matching the wording is unavoidable: the browser gives no
// structured reason for a failed module import.
const STALE_CHUNK_PATTERNS = [
  /failed to fetch dynamically imported module/i,
  /error loading dynamically imported module/i,
  /importing a module script failed/i,
  /is not a supported stylesheet mime type/i,
]

export function isStaleChunkError(error: unknown): boolean {
  const message = typeof error === 'string' ? error : (error as { message?: unknown })?.message
  if (typeof message !== 'string') return false
  return STALE_CHUNK_PATTERNS.some((pattern) => pattern.test(message))
}

/**
 * Vite fires `vite:preloadError` for a failed chunk preload. A dynamic import
 * that fails outside that path still rejects, so the unhandled rejection is
 * covered too — otherwise a failed route import during navigation is missed.
 */
export function startStaleDeployWatch(): () => void {
  const onPreloadError = () => markStaleDeploy()
  const onUnhandledRejection = (event: Event) => {
    const reason = (event as PromiseRejectionEvent).reason ?? (event as CustomEvent).detail
    if (isStaleChunkError(reason)) markStaleDeploy()
  }
  window.addEventListener('vite:preloadError', onPreloadError)
  window.addEventListener('unhandledrejection', onUnhandledRejection)
  return () => {
    window.removeEventListener('vite:preloadError', onPreloadError)
    window.removeEventListener('unhandledrejection', onUnhandledRejection)
  }
}

/**
 * `React.lazy` catches the import rejection and re-throws it during render, so
 * a dead route chunk never reaches `unhandledrejection`, and `vite:preloadError`
 * only covers preloads. Wrapping the loader is the one place the rejection is
 * observable. The error is re-thrown unchanged so Suspense and any error
 * boundary behave exactly as before.
 */
export function lazyRouteLoader<T>(load: () => Promise<T>): () => Promise<T> {
  return () => load().catch((error: unknown) => {
    if (isStaleChunkError(error)) markStaleDeploy()
    throw error
  })
}
