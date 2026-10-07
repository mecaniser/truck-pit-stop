import { useEffect, useState } from 'react'
import type { BoardTruck } from './types'

export interface ReadingProvenance {
  source: 'motive_api' | 'motive_dashboard_manual' | 'manual_location'
  observed_at: string | null
  /** Minute observations represent [observed_at, observed_at + 60 seconds). */
  observed_precision?: 'second' | 'minute' | null
  captured_at: string | null
  freshness: 'fresh' | 'delayed' | 'stale' | 'unknown'
  snapshot_id: string | null
  source_age_text: string | null
}
export interface NumericReading extends ReadingProvenance { value: number; unit: 'mph' | 'mi' | 'h' | 'percent' | 'count' | 'mpg'; basis: 'calibrated' | 'virtual' | 'dashboard_unspecified' | null }
export interface FuelEconomyReading extends NumericReading { unit: 'mpg'; period: 'last_30_days' }
export interface LocationReading extends ReadingProvenance { lat: number | null; lng: number | null; label: string | null }
export interface FleetTelemetry { location: LocationReading | null; speed: NumericReading | null; odometer: NumericReading | null; engine_hours: NumericReading | null; fuel: NumericReading | null; fuel_economy?: FuelEconomyReading | null; fault_count: NumericReading | null; motion: 'moving' | 'stopped' | 'unknown' }
export function retained<T extends ReadingProvenance>(reading: T | null | undefined, now = Date.now()): T | null {
  if (!reading) return null
  const stamp = Date.parse(reading.observed_at ?? reading.captured_at ?? '')
  if (!Number.isFinite(stamp) || stamp > now + 300000 || now - stamp > 30 * 86400000) return null
  return reading
}
export function readingFreshness(reading: ReadingProvenance, now = Date.now()) {
  if (!reading.observed_at) return 'unknown'
  const age = now - Date.parse(reading.observed_at)
  return !Number.isFinite(age) || age < -300000 ? 'unknown' : age <= 300000 ? 'fresh' : age <= 900000 ? 'delayed' : 'stale'
}
/** Keep approximate observations distinct from the exact capture time. */
export function readingCaption(reading: ReadingProvenance) {
  if (reading.observed_precision === 'minute' && reading.observed_at && Number.isFinite(Date.parse(reading.observed_at))) {
    const observed = new Date(reading.observed_at).toLocaleString(undefined, { year: 'numeric', month: 'numeric', day: 'numeric', hour: 'numeric', minute: '2-digit' })
    const captured = reading.captured_at && Number.isFinite(Date.parse(reading.captured_at)) ? ` · Captured ${new Date(reading.captured_at).toLocaleString()}` : ''
    return `Observed around ${observed}${captured}`
  }
  const stamp = reading.captured_at ?? reading.observed_at
  if (!stamp || !Number.isFinite(Date.parse(stamp))) return ''
  return `${reading.captured_at ? 'Captured' : 'Updated'} ${new Date(stamp).toLocaleString()}`
}
/** API age uses the observation; manually captured readings use their save time. */
export function readingSummary(reading: ReadingProvenance, now = Date.now()) {
  const stamp = Date.parse(reading.observed_at ?? reading.captured_at ?? '')
  if (!Number.isFinite(stamp)) return ''
  const minutes = Math.max(0, Math.floor((now - stamp) / 60000))
  const approximate = reading.observed_precision === 'minute' && !!reading.observed_at
  if (minutes < 1) return approximate ? 'Updated within the last minute' : 'Updated just now'
  const count = minutes < 60 ? minutes : minutes < 1440 ? Math.floor(minutes / 60) : Math.floor(minutes / 1440)
  const unit = minutes < 60 ? 'minute' : minutes < 1440 ? 'hour' : 'day'
  return `Updated ${approximate ? 'about ' : ''}${count} ${unit}${count === 1 ? '' : 's'} ago`
}

export function truckLocation(truck: BoardTruck, now = Date.now()) { return retained(truck.telemetry?.location, now) }
export function truckCoordinates(truck: BoardTruck, now = Date.now()): [number, number] | null {
  const value = truckLocation(truck, now)
  if (!value || value.lat == null || value.lng == null || !Number.isFinite(value.lat) || !Number.isFinite(value.lng) || Math.abs(value.lat) > 90 || Math.abs(value.lng) > 180) return null
  return [value.lng, value.lat]
}
export function truckMotion(truck: BoardTruck, now = Date.now()) {
  const speed = retained(truck.telemetry?.speed, now)
  return speed && readingFreshness(speed, now) === 'fresh' ? speed.value > 0 ? 'moving' : 'stopped' : 'unknown'
}

/** Refresh age labels and motion while a fleet view stays open. */
export function useTelemetryClock() {
  const [now, setNow] = useState(Date.now)
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 30000); return () => window.clearInterval(timer) }, [])
  return now
}
