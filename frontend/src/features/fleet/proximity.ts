import type { BoardTruck } from './types'
import { readingFreshness, truckCoordinates, truckLocation } from './telemetry'

export function recentPosition(truck: BoardTruck, now: number) {
  const location = truckLocation(truck, now)
  return !!location && !!truckCoordinates(truck, now) && ['fresh', 'delayed'].includes(readingFreshness(location, now))
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
