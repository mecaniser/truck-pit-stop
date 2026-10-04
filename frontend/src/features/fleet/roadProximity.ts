import { useEffect, useState } from 'react'
import type { BoardTruck } from './types'
import { truckCoordinates } from './telemetry'
import { recentPosition } from './proximity'

export interface RoadPoint { id: string; point: [number, number] }
export interface RoadDistance { id: string; miles: number; seconds: number }
interface RoadResult { routes: RoadDistance[]; unreachable: number }
type Phase = 'idle' | 'loading' | 'ready' | 'error' | 'unconfigured'
interface State extends RoadResult { key: string; phase: Phase; geometry?: GeoJSON.LineString; geometryFailed?: boolean }
const validNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0

export function roadCandidates(trucks: BoardTruck[], focus: BoardTruck | undefined, now: number, includeLastKnown: boolean): RoadPoint[] {
  if (!focus || !truckCoordinates(focus, now) || (!includeLastKnown && !recentPosition(focus, now))) return []
  return trucks.flatMap(truck => {
    const point = truckCoordinates(truck, now)
    return truck.id !== focus.id && point && (includeLastKnown || recentPosition(truck, now)) ? [{ id: truck.id, point }] : []
  }).sort((a, b) => a.id.localeCompare(b.id))
}

async function request(path: string, params: Record<string, string>, token: string, signal: AbortSignal) {
  const controller = new AbortController()
  const abort = () => controller.abort()
  signal.addEventListener('abort', abort, { once: true })
  if (signal.aborted) controller.abort()
  const timeout = setTimeout(abort, 15000)
  try {
    const response = await fetch(`https://api.mapbox.com/${path}?${new URLSearchParams({ ...params, access_token: token })}`, { signal: controller.signal, credentials: 'omit' })
    if (!response.ok) throw new Error('Routing unavailable')
    return await response.json()
  } finally { clearTimeout(timeout); signal.removeEventListener('abort', abort) }
}

export async function fetchRoadDistances(origin: [number, number], candidates: RoadPoint[], token: string, signal: AbortSignal): Promise<RoadResult> {
  const routes: RoadDistance[] = []
  let unreachable = 0
  // Compare every eligible truck. Aerial shortlists can miss the closest road route.
  for (let start = 0; start < candidates.length; start += 24) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    const batch = candidates.slice(start, start + 24)
    const coordinates = [origin, ...batch.map(row => row.point)].map(point => point.join(',')).join(';')
    const body = await request(`directions-matrix/v1/mapbox/driving/${coordinates}`, {
      sources: '0', destinations: batch.map((_, index) => String(index + 1)).join(';'), annotations: 'distance,duration',
    }, token, signal)
    if (body.code === 'NoRoute') { unreachable += batch.length; continue }
    const distances = body.distances?.[0], durations = body.durations?.[0]
    if (body.code !== 'Ok' || !Array.isArray(distances) || !Array.isArray(durations) || distances.length !== batch.length || durations.length !== batch.length) throw new Error('Invalid routing response')
    batch.forEach((candidate, index) => {
      const meters = distances[index], seconds = durations[index]
      if (meters === null || seconds === null) { unreachable++; return }
      if (!validNumber(meters) || !validNumber(seconds)) throw new Error('Invalid routing distance')
      routes.push({ id: candidate.id, miles: meters / 1609.344, seconds })
    })
  }
  return { routes: routes.sort((a, b) => a.miles - b.miles || a.id.localeCompare(b.id)), unreachable }
}

export async function fetchRoadGeometry(origin: [number, number], destination: [number, number], token: string, signal: AbortSignal): Promise<GeoJSON.LineString> {
  const body = await request(`directions/v5/mapbox/driving/${origin.join(',')};${destination.join(',')}`, { geometries: 'geojson', overview: 'full', steps: 'false', alternatives: 'false' }, token, signal)
  const geometry = body.routes?.[0]?.geometry
  if (body.code !== 'Ok' || geometry?.type !== 'LineString' || !Array.isArray(geometry.coordinates) || geometry.coordinates.length < 2 || !geometry.coordinates.every((point: unknown) => Array.isArray(point) && point.length === 2 && point.every(Number.isFinite) && Math.abs(point[0]) <= 180 && Math.abs(point[1]) <= 90)) throw new Error('Route preview unavailable')
  return geometry
}

export function useRoadProximity(trucks: BoardTruck[], focus: BoardTruck | undefined, now: number, includeLastKnown: boolean, retry: number) {
  const token = import.meta.env.VITE_MAPBOX_TOKEN || ''
  const candidates = roadCandidates(trucks, focus, now, includeLastKnown)
  const origin = focus && truckCoordinates(focus, now)
  const key = JSON.stringify({ origin, focus: focus?.id, candidates, includeLastKnown, retry })
  const active = !!origin && candidates.length > 0
  const [state, setState] = useState<State>({ key: '', phase: 'idle', routes: [], unreachable: 0 })
  useEffect(() => {
    if (!active || !token) return
    const input = JSON.parse(key) as { origin: [number, number]; candidates: RoadPoint[] }
    const controller = new AbortController()
    // Avoid provider calls for selections that are immediately superseded.
    const timer = setTimeout(() => {
      void (async () => {
        try {
          const result = await fetchRoadDistances(input.origin, input.candidates, token, controller.signal)
          if (controller.signal.aborted) return
          setState({ ...result, key, phase: 'ready' })
          const closest = input.candidates.find(candidate => candidate.id === result.routes[0]?.id)
          if (!closest) return
          try {
            const geometry = await fetchRoadGeometry(input.origin, closest.point, token, controller.signal)
            if (!controller.signal.aborted) setState({ ...result, key, phase: 'ready', geometry })
          } catch {
            if (!controller.signal.aborted) setState({ ...result, key, phase: 'ready', geometryFailed: true })
          }
        } catch {
          if (!controller.signal.aborted) setState({ key, phase: 'error', routes: [], unreachable: 0 })
        }
      })()
    }, 250)
    return () => { clearTimeout(timer); controller.abort() }
  }, [key, active, token])
  // Never expose results from a previous origin, position or tenant-scoped truck set.
  const current: State = !active ? { key, phase: 'idle', routes: [], unreachable: 0 }
    : !token ? { key, phase: 'unconfigured', routes: [], unreachable: 0 }
      : state.key === key ? state : { key, phase: 'loading', routes: [], unreachable: 0 }
  return { ...current, candidates: candidates.length, nearby: current.routes.flatMap(route => {
    const truck = trucks.find(item => item.id === route.id)
    return truck ? [{ truck, miles: route.miles, seconds: route.seconds }] : []
  }) }
}

export function formatDriveTime(seconds: number) {
  const minutes = Math.ceil(seconds / 60)
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} hr${minutes % 60 ? ` ${minutes % 60} min` : ''}`
}
