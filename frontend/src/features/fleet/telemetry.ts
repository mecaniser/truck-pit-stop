import { useEffect, useState } from 'react'
import type { BoardTruck } from './types'

export interface ReadingProvenance {
  source: 'motive_api' | 'motive_dashboard_manual' | 'manual_location'
  observed_at: string | null
  captured_at: string | null
  freshness: 'fresh' | 'delayed' | 'stale' | 'unknown'
  snapshot_id: string | null
  source_age_text: string | null
}
export interface NumericReading extends ReadingProvenance { value: number; unit: 'mph' | 'mi' | 'h' | 'percent' | 'count'; basis: 'calibrated' | 'virtual' | 'dashboard_unspecified' | null }
export interface LocationReading extends ReadingProvenance { lat: number | null; lng: number | null; label: string | null }
export interface FleetTelemetry { location: LocationReading | null; speed: NumericReading | null; odometer: NumericReading | null; engine_hours: NumericReading | null; fuel: NumericReading | null; fault_count: NumericReading | null; motion: 'moving' | 'stopped' | 'unknown' }
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
export function readingCaption(reading: ReadingProvenance, now = Date.now()) {
  const source = reading.source === 'motive_api' ? 'Motive API' : reading.source === 'motive_dashboard_manual' ? 'Motive dashboard · manual capture' : 'Manual location'
  const stamp = reading.observed_at ?? reading.captured_at
  const time = stamp && Number.isFinite(Date.parse(stamp)) ? new Date(stamp).toLocaleString() : 'Time unavailable'
  return `${source} · ${reading.observed_at ? `Observed ${time} · ${readingFreshness(reading, now)}` : `Captured ${time} · observation time unknown`}${reading.source_age_text ? ` · source displayed ${reading.source_age_text}` : ''}`
}
/** Compact age describes the observed reading, or explicitly the manual save. */
export function readingSummary(reading: ReadingProvenance, now = Date.now()) {
  const source = reading.source === 'motive_api' ? 'Motive' : 'Manual'
  const stamp = Date.parse(reading.observed_at ?? reading.captured_at ?? '')
  if (!Number.isFinite(stamp)) return `${source} · time unknown`
  const minutes = Math.max(0, Math.floor((now - stamp) / 60000))
  const age = minutes < 1 ? 'just now' : minutes < 60 ? `${minutes}m ago` : minutes < 1440 ? `${Math.floor(minutes / 60)}h ago` : `${Math.floor(minutes / 1440)}d ago`
  return reading.observed_at
    ? `${source} · ${age}${readingFreshness(reading, now) === 'fresh' ? '' : ` · ${readingFreshness(reading, now)}`}`
    : `${source} · saved ${age} · time unknown`
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
