import type { BoardTruck } from './types'
import { readingFreshness, truckCoordinates, truckLocation } from './telemetry'

export function recentPosition(truck: BoardTruck, now: number) {
  const location = truckLocation(truck, now)
  return !!location && !!truckCoordinates(truck, now) && ['fresh', 'delayed'].includes(readingFreshness(location, now))
}

export function distanceMiles(a: [number, number], b: [number, number]) {
  const rad = Math.PI / 180
  const h = Math.sin((b[1] - a[1]) * rad / 2) ** 2
    + Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin((b[0] - a[0]) * rad / 2) ** 2
  return 7917.6 * Math.asin(Math.sqrt(Math.min(1, Math.max(0, h))))
}

export function nearbyTrucks(trucks: BoardTruck[], focus: BoardTruck | undefined, now: number, includeLastKnown: boolean) {
  const origin = focus && truckCoordinates(focus, now)
  if (!origin || (!includeLastKnown && !recentPosition(focus!, now))) return []
  return trucks.flatMap(truck => {
    const point = truckCoordinates(truck, now)
    return truck.id !== focus!.id && point && (includeLastKnown || recentPosition(truck, now))
      ? [{ truck, miles: distanceMiles(origin, point) }] : []
  }).sort((a, b) => a.miles - b.miles || a.truck.id.localeCompare(b.truck.id))
}

export function positionAge(truck: BoardTruck, now: number) {
  const location = truckLocation(truck, now)
  if (!location || !truckCoordinates(truck, now)) return 'No coordinates'
  if (!location.observed_at || readingFreshness(location, now) === 'unknown') return 'Time unknown'
  const minutes = Math.max(0, Math.floor((now - Date.parse(location.observed_at)) / 60000))
  const age = minutes < 1 ? 'Just now' : minutes < 60 ? `${minutes}m ago` : minutes < 1440 ? `${Math.floor(minutes / 60)}h ago` : `${Math.floor(minutes / 1440)}d ago`
  return recentPosition(truck, now) ? age : `Last known · ${age}`
}

export function formatDistance(miles: number) {
  return miles > 0 && miles < 0.1 ? '<0.1 mi' : `${miles.toLocaleString('en-US', { maximumFractionDigits: 1 })} mi`
}
