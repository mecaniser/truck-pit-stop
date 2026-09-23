/**
 * DB-076: decide when a long-lived tab may reload itself.
 *
 * A fleet manager keeps the board open on an iPad for days. DB-074 only
 * catches a dead chunk; FleetApp imports its views statically, so that tab
 * never requests new code and never learns it is stale. This polls the build
 * version instead.
 *
 * The riskiest behavior in the item is the silent reload: get it wrong and a
 * manager's typed work disappears. So "clean and idle" is defined narrowly and
 * every uncertainty resolves to NOT reloading. See the DB-076 contract in
 * docs/PROJECT_BOARD.md.
 */

/** Forms currently holding unsaved input. Counted, not boolean: two panels can be open. */
import { markStaleDeploy } from './staleDeploy'

let dirtyForms = 0

export function registerDirtyForm(): () => void {
  dirtyForms += 1
  let released = false
  return () => {
    // Guard against a double release driving the count negative, which would
    // make a genuinely dirty page look clean.
    if (released) return
    released = true
    dirtyForms = Math.max(0, dirtyForms - 1)
  }
}

export function isDirtyFormRegistered(): boolean {
  return dirtyForms > 0
}

export function resetStaleBuild(): void {
  dirtyForms = 0
}

/**
 * A page is safe to reload without asking only when nothing is being typed and
 * nothing is being saved. Anything else gets the DB-074 prompt instead.
 */
export function shouldReloadSilently(state: { mutationsInFlight: number; dirtyForms: number }): boolean {
  return state.mutationsInFlight === 0 && state.dirtyForms === 0
}

export type BuildCheck = 'current' | 'stale' | 'unknown'

/**
 * Ask the server which build it is serving.
 *
 * Every failure resolves to 'unknown', never 'stale'. Offline is not
 * staleness, and the SPA catch-all answers an unmatched path with index.html,
 * so a JSON parse failure is an expected misconfiguration rather than a signal
 * to reload. 'unknown' means do nothing.
 */
export async function checkBuildVersion(runningSha: string | null): Promise<BuildCheck> {
  if (!runningSha) return 'unknown'
  try {
    const res = await fetch('/build-version', { cache: 'no-store' })
    if (!res.ok) return 'unknown'
    const body = (await res.json()) as { sha?: unknown }
    if (typeof body?.sha !== 'string' || body.sha.length === 0) return 'unknown'
    return body.sha === runningSha ? 'current' : 'stale'
  } catch {
    return 'unknown'
  }
}

/** The sha the server is currently serving, or null when it cannot be known. */
async function fetchServedSha(): Promise<string | null> {
  try {
    const res = await fetch('/build-version', { cache: 'no-store' })
    if (!res.ok) return null
    const body = (await res.json()) as { sha?: unknown }
    return typeof body?.sha === 'string' && body.sha ? body.sha : null
  } catch {
    return null
  }
}

type WatchOptions = {
  intervalMs?: number
  reload?: () => void
  mutationsInFlight?: () => number
}

/**
 * Poll the served build and act when it changes.
 *
 * The running build's own sha is not compiled in: `isLocalRuntimeServe` in
 * vite.config.ts deliberately keeps runtime identity out of production client
 * code, and widening that guard to leak a sha would be the wrong trade. Instead
 * the first response is adopted as "what this tab is running" — it is served by
 * the same deployment that served this tab's HTML — and later responses are
 * compared against it. A first poll therefore never reloads.
 */
export function startStaleBuildWatch({
  intervalMs = 60_000,
  reload = () => window.location.reload(),
  mutationsInFlight = () => 0,
}: WatchOptions = {}): () => void {
  let runningSha: string | null = null
  let stopped = false

  const poll = async () => {
    if (stopped) return
    const served = await fetchServedSha()
    if (stopped || served === null) return

    if (runningSha === null) {
      // Adoption pass: this response came from the deployment that served this
      // tab, so it is what the tab is running. Decide nothing yet.
      runningSha = served
      return
    }

    if (served === runningSha) return

    if (shouldReloadSilently({ mutationsInFlight: mutationsInFlight(), dirtyForms })) {
      reload()
      return
    }
    // Work would be lost, so ask instead of taking it. Reuses the DB-074 notice.
    markStaleDeploy()
  }

  void poll()
  const timer = setInterval(() => void poll(), intervalMs)
  // An iPad parked for days fires this the moment it is picked back up, which
  // is the realistic moment a stale tab is used again.
  const onVisible = () => { if (document.visibilityState === 'visible') void poll() }
  document.addEventListener('visibilitychange', onVisible)

  return () => {
    stopped = true
    clearInterval(timer)
    document.removeEventListener('visibilitychange', onVisible)
  }
}
