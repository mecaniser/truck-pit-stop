import type { FleetTrip, FleetTripsResponse } from './FleetTrips'

const dayFormatters = new Map<string, Intl.DateTimeFormat>()
export const tripDay = (stamp: string, timezone: string) => {
  if (!dayFormatters.has(timezone)) dayFormatters.set(timezone, new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
  }))
  return dayFormatters.get(timezone)!.format(new Date(stamp))
}
export function summarizeTrips(items: FleetTrip[]) {
  return { count: items.length, miles: items.reduce((n, t) => n + t.distance_miles, 0), seconds: items.reduce((n, t) => n + t.driving_seconds, 0) }
}
export function groupTripDays(items: FleetTrip[], timezone: string) {
  const groups = new Map<string, FleetTrip[]>()
  for (const trip of items) {
    const key = tripDay(trip.started_at, timezone)
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(trip)
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

export type ActivityInterval = 'day' | 'week' | 'month' | 'year'
const shiftDay = (day: string, amount: number) => new Date(Date.parse(day) + amount * 86400000).toISOString().slice(0, 10)
export function availableActivityIntervals(start: string, end: string, preset?: string): ActivityInterval[] {
  if (preset === 'day' || preset === 'week') return ['day']
  if (preset === 'month') return ['day', 'week']
  if (preset === 'year') return ['day', 'week', 'month']
  const days = (Date.parse(end) - Date.parse(start)) / 86400000 + 1
  return days <= 7 ? ['day'] : days <= 31 ? ['day', 'week'] : ['day', 'week', 'month']
}
export function defaultActivityInterval(start: string, end: string, preset?: string): ActivityInterval {
  if (preset === 'day' || preset === 'week') return 'day'
  if (preset === 'year') return 'month'
  if (preset === 'month') return 'week'
  const days = (Date.parse(end) - Date.parse(start)) / 86400000 + 1
  return days > 62 ? 'month' : days > 7 ? 'week' : 'day'
}
/** Calendar buckets retain empty periods as missing imports, never inferred zero activity. */
export function activityBuckets(items: FleetTrip[], timezone: string, start: string, end: string, interval: ActivityInterval) {
  const daily = new Map(groupTripDays(items, timezone).map(d => [d.date, d.trips]))
  const buckets: { start: string; end: string; trips: FleetTrip[]; count: number; miles: number; seconds: number }[] = []
  for (let cursor = start; cursor <= end;) {
    const date = new Date(cursor)
    let boundary = cursor
    if (interval === 'week') boundary = shiftDay(cursor, (7 - date.getUTCDay()) % 7)
    if (interval === 'month') boundary = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0)).toISOString().slice(0, 10)
    if (interval === 'year') boundary = `${date.getUTCFullYear()}-12-31`
    const last = boundary < end ? boundary : end
    const trips: FleetTrip[] = []
    for (let day = cursor; day <= last; day = shiftDay(day, 1)) trips.push(...(daily.get(day) || []))
    buckets.push({ start: cursor, end: last, trips, ...summarizeTrips(trips) })
    cursor = shiftDay(last, 1)
  }
  return buckets
}
/** Keep the existing API's inclusive 31-day bound; windows never overlap. */
export async function loadTripRange(start: string, end: string, fetchPage: (start: string, end: string, offset: number) => Promise<FleetTripsResponse>) {
  const span = (Date.parse(end) - Date.parse(start)) / 86400000
  if (!Number.isFinite(span) || span < 0 || span >= 366) throw new Error('Invalid trip range')
  const windows: FleetTripsResponse[] = []
  for (let cursor = start; cursor <= end;) {
    const last = shiftDay(cursor, 30) < end ? shiftDay(cursor, 30) : end
    windows.push(await loadTripOverview(offset => fetchPage(cursor, last, offset)))
    cursor = shiftDay(last, 1)
  }
  const items = windows.flatMap(w => w.items)
  if (new Set(items.map(t => t.id)).size !== items.length) throw new Error('Overlapping trip windows; retry')
  const sum = summarizeTrips(items)
  return { ...windows[0], start_date: start, end_date: end, items, total: items.length, offset: 0,
    summary: { ...windows[0].summary, truck_count: new Set(items.map(t => t.vehicle_id)).size, trip_count: sum.count, distance_miles: sum.miles, driving_seconds: sum.seconds } }
}
