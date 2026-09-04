/**
 * How long ago something happened, in the shop's house format.
 *
 * The arithmetic was written twice — `timeAgo` in DashboardHome and
 * `updatedLabel` in ShopCockpitActionLedger — and the fleet board needed it a
 * third time. It lives here once; callers supply the phrasing, because the
 * phrasing is the part that differs and matters:
 *
 *   "Updated 2h ago"  — recency. Someone touched this recently.
 *   "Open 44d"        — age. This visit never closed.
 *
 * A stale repair order shows a reassuring recency the moment anyone glances at
 * it, which is exactly why the fleet board measures age instead.
 */

/**
 * Milliseconds since `iso`, or null when it is missing or unparseable.
 *
 * The value is signed: a future timestamp means clock skew, and callers
 * differ on what to say about it — the cockpit calls it "recently", the fleet
 * board treats it as fresh. Deciding here would take that choice away.
 */
export function elapsedSince(iso: string | null | undefined): number | null {
  if (!iso) return null
  const then = new Date(iso).getTime()
  if (!Number.isFinite(then)) return null
  return Date.now() - then
}

/** Coarse duration: `45m`, `6h`, `44d`. One unit, never a compound. */
export function shortDuration(ms: number): string {
  const minutes = Math.max(Math.floor(ms / 60_000), 0)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h`
  return `${Math.floor(hours / 24)}d`
}

/** Whole days since `iso`, for thresholds. Null when the input is unusable. */
export function daysSince(iso: string | null | undefined): number | null {
  const elapsed = elapsedSince(iso)
  return elapsed == null ? null : Math.max(Math.floor(elapsed / 86_400_000), 0)
}
