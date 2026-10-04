import type { FleetTrip, FleetTripsResponse } from './FleetTrips'

export const tripDay = (stamp: string, timezone: string) => new Intl.DateTimeFormat('en-CA', {
  timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date(stamp))
export function summarizeTrips(items: FleetTrip[]) {
  return { count: items.length, miles: items.reduce((n, t) => n + t.distance_miles, 0), seconds: items.reduce((n, t) => n + t.driving_seconds, 0) }
}
export function groupTripDays(items: FleetTrip[], timezone: string) {
  const groups = new Map<string, FleetTrip[]>()
  for (const trip of items) {
    const key = tripDay(trip.started_at, timezone)
    groups.set(key, [...(groups.get(key) || []), trip])
  }
  return [...groups].sort(([a], [b]) => a.localeCompare(b)).map(([date, trips]) => ({ date, trips, ...summarizeTrips(trips) }))
}

// Never publish a first-page comparison as a fleet-wide result. Each page must
// reconcile with the same summary; concurrent imports require a fresh read.
export async function loadTripOverview(fetchPage: (offset: number) => Promise<FleetTripsResponse>) {
  const first = await fetchPage(0)
  const rows = [...first.items]
  const sameSummary = (page: FleetTripsResponse) => page.total === first.total &&
    page.summary.trip_count === first.summary.trip_count && page.summary.truck_count === first.summary.truck_count &&
    page.summary.distance_miles === first.summary.distance_miles && page.summary.driving_seconds === first.summary.driving_seconds
  if (!Number.isInteger(first.total) || first.total < 0 || first.total > 100000) throw new Error('Invalid trip count')
  while (rows.length < first.total) {
    const page = await fetchPage(rows.length)
    if (!sameSummary(page) || !page.items.length || page.offset !== rows.length) throw new Error('Trip history changed; retry')
    rows.push(...page.items)
  }
  const totals = summarizeTrips(rows)
  if (rows.length !== first.total || new Set(rows.map(t => t.id)).size !== first.total ||
      totals.count !== first.summary.trip_count || new Set(rows.map(t => t.vehicle_id)).size !== first.summary.truck_count ||
      Math.abs(totals.miles - first.summary.distance_miles) > 0.01 || totals.seconds !== first.summary.driving_seconds) {
    throw new Error('Trip totals did not reconcile; retry')
  }
  return { ...first, items: rows }
}

/** Competition ranks preserve ties; missing/zero activity has no leader. */
export function activityRanking(values: { id: string; value: number; count: number }[]) {
  const reporting = values.filter(v => v.count > 0 && Number.isFinite(v.value) && v.value >= 0)
  const top = Math.max(0, ...reporting.map(v => v.value))
  return new Map(values.map(v => [v.id, !reporting.includes(v) || top === 0 ? null : {
    rank: 1 + reporting.filter(peer => peer.value > v.value).length,
    ratio: v.value / top,
    leader: v.value === top,
  }]))
}

export function tripFuel(trips: FleetTrip[]) {
  const measured = trips.filter(t => t.metrics?.fuel_used_gallons != null && Number.isFinite(t.metrics.fuel_used_gallons) && t.metrics.fuel_used_gallons >= 0)
  if (measured.length) return { kind: 'Used', count: measured.length, miles: measured.reduce((n, t) => n + t.distance_miles, 0), gallons: measured.reduce((n, t) => n + t.metrics!.fuel_used_gallons!, 0) }
  const estimated = trips.filter(t => t.metrics?.estimated_fuel_gallons != null && Number.isFinite(t.metrics.estimated_fuel_gallons) && t.metrics.estimated_fuel_gallons >= 0 && t.metrics.estimate_baseline_period === 'last_30_days' && (t.metrics.estimate_baseline_mpg || 0) > 0)
  return estimated.length ? { kind: 'Est.', count: estimated.length, miles: estimated.reduce((n, t) => n + t.distance_miles, 0), gallons: estimated.reduce((n, t) => n + t.metrics!.estimated_fuel_gallons!, 0) } : null
}

/** Display grouping only, never a provider trip definition or inferred stop purpose. */
export function routeMovementSummary(items: FleetTrip[]) {
  const short = items.filter(t => t.distance_miles >= 0 && t.distance_miles <= 1 && t.driving_seconds >= 0 && t.driving_seconds <= 900)
  const ids = new Set(short.map(t => t.id))
  const travel = items.filter(t => !ids.has(t.id))
  const longest = items.reduce<FleetTrip | null>((best, t) => !best || t.distance_miles > best.distance_miles ? t : best, null)
  return { short, travel, shortTotals: summarizeTrips(short), travelTotals: summarizeTrips(travel), longest }
}
