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
