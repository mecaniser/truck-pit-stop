import cargoMarkUrl from '../../assets/fleet/77-cargo-mark.svg'
import { useEffect, useRef, useState } from 'react'
import type { Map as MapboxMap, Marker as MapboxMarker } from 'mapbox-gl'
import type { BoardTruck } from './types'
import { STATUS_META } from './helpers'
import { mapUnitLabel } from './mapLabels'
import { truckCoordinates } from './telemetry'
import { recentPosition } from './proximity'
import 'mapbox-gl/dist/mapbox-gl.css'

interface Pin { id: string; label: string; company: string; status: BoardTruck['status']; point: [number, number]; recent: boolean }
interface Props { trucks: BoardTruck[]; focusId?: string; nearbyIds: string[]; route?: GeoJSON.LineString; now: number; recenter: number; homePoint?: [number, number]; homeVisit?: number; onFocus: (id: string) => void; onClusterOpen?: (ids: string[]) => void }

export default function FleetMapCanvas({ trucks, focusId, nearbyIds, route, now, recenter, homePoint, homeVisit = 0, onFocus, onClusterOpen }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapboxMap>()
  const moduleRef = useRef<typeof import('mapbox-gl').default>()
  const markers = useRef(new Map<string, { marker: MapboxMarker; button: HTMLButtonElement; contentKey: string; pointKey: string }>())
  const [ready, setReady] = useState(false)
  const [error, setError] = useState(false)
  const [viewportRevision, setViewportRevision] = useState(0)
  const homeFraming = useRef(0)
  const framing = useRef('')
  const selectRef = useRef(onFocus)
  selectRef.current = onFocus
  const clusterRef = useRef(onClusterOpen)
  clusterRef.current = onClusterOpen
  const token = import.meta.env.VITE_MAPBOX_TOKEN || ''
  const pinData = JSON.stringify(trucks.flatMap(truck => {
    const point = truckCoordinates(truck, now)
    return point ? [{ id: truck.id, label: mapUnitLabel(truck), company: truck.fleet_company_name || truck.board_membership_company_name || truck.owner_company_name || '', status: truck.status, point, recent: recentPosition(truck, now) }] : []
  }))
  const comparisonData = JSON.stringify(nearbyIds)
  const routeData = JSON.stringify(route || null)
  useEffect(() => {
    if (!token || !container.current) return
    const registry = markers.current
    let cancelled = false
    let map: MapboxMap | undefined
    let observer: ResizeObserver | undefined
    setError(false)
    setReady(false)
    void import('mapbox-gl').then(({ default: mb }) => {
      if (cancelled || !container.current) return
      map = new mb.Map({ container: container.current, accessToken: token, style: 'mapbox://styles/mapbox/streets-v12', center: [-98, 39], zoom: 3, attributionControl: true })
      map.on('error', () => { if (!cancelled) setError(true) })
      map.on('moveend', () => { if (!cancelled) setViewportRevision(value => value + 1) })
      map.on('resize', () => { if (!cancelled) setViewportRevision(value => value + 1) })
      map.on('load', () => { if (!cancelled) setReady(true) })
      map.addControl(new mb.NavigationControl(), 'top-right')
      mapRef.current = map; moduleRef.current = mb
      if (typeof ResizeObserver !== 'undefined') { observer = new ResizeObserver(() => map?.resize()); observer.observe(container.current) }
    }).catch(() => { if (!cancelled) setError(true) })
    return () => { cancelled = true; observer?.disconnect(); registry.forEach(entry => entry.marker.remove()); registry.clear(); map?.remove(); mapRef.current = undefined; framing.current = '' }
  }, [token])

  useEffect(() => {
    const map = mapRef.current, mb = moduleRef.current
    if (!map || !mb || !ready) return
    const pins = JSON.parse(pinData) as Pin[]
    const nearby = JSON.parse(comparisonData) as string[]
    const focus = pins.find(pin => pin.id === focusId)
    // Cluster by visible overlap, not exact GPS equality. Re-evaluate after zoom/pan.
    const projected = [...pins].sort((a, b) => a.id.localeCompare(b.id)).map(pin => ({ pin, pixel: map.project(pin.point) }))
    const remaining = new Set(projected)
    const groups: Pin[][] = []
    for (const seed of projected) {
      if (!remaining.delete(seed)) continue
      const connected = [seed]
      for (let index = 0; index < connected.length; index++) {
        const current = connected[index]
        for (const candidate of remaining) {
          if (Math.abs(current.pixel.x - candidate.pixel.x) < 96 && Math.abs(current.pixel.y - candidate.pixel.y) < 56) {
            connected.push(candidate); remaining.delete(candidate)
          }
        }
      }
      groups.push(connected.map(item => item.pin))
    }
    const liveKeys = new Set<string>()
    groups.forEach(group => {
      const members = [...group].sort((a, b) => a.id.localeCompare(b.id))
      // Identity follows group membership, not position or current selection.
      const key = JSON.stringify(members.map(pin => pin.id))
      liveKeys.add(key)
      const selected = members.find(pin => pin.id === focusId)
      const anchor = members[0].point
      const coincident = members.every(pin => pin.point.join(',') === anchor.join(','))
      const representative = selected || members.find(pin => pin.status === 'out_of_service') || members[0]
      let entry = markers.current.get(key)
      if (!entry) {
        const button = document.createElement('button'); button.type = 'button'
        const marker = new mb.Marker({ element: button }).setLngLat(anchor).addTo(map)

        entry = { marker, button, contentKey: '', pointKey: anchor.join(',') }
        markers.current.set(key, entry)
      }
      const { button, marker } = entry
      button.onclick = () => {
        if (members.length === 1) { selectRef.current(members[0].id); return }
        if (coincident || map.getZoom() >= 18) { clusterRef.current?.(members.map(pin => pin.id)); return }
        clusterRef.current?.([])
        const bounds = new mb.LngLatBounds()
        members.forEach(pin => bounds.extend(pin.point))
        const camera = map.cameraForBounds(bounds, { padding: 90, maxZoom: 18 })
        if (camera) map.easeTo({ ...camera, zoom: Math.min(18, Math.max(map.getZoom() + 1, camera.zoom ?? map.getZoom() + 2)), duration: 400 })
      }

      const pointKey = anchor.join(',')
      if (entry.pointKey !== pointKey) { marker.setLngLat(anchor); entry.pointKey = pointKey }
      // Mapbox owns positioning classes on this element; never replace className.
      button.classList.add('proximity-pin')
      button.classList.toggle('is-cluster', members.length > 1)
      button.classList.toggle('is-selected', !!selected)
      button.classList.toggle('is-last-known', members.every(pin => !pin.recent))
      button.classList.toggle('is-dimmed', !!focus && !selected && !members.some(pin => nearby.includes(pin.id)))
      button.style.setProperty('--pin-status', STATUS_META[representative.status].dot)
      const contentKey = JSON.stringify([representative.label, representative.company, members.map(pin => pin.company)])
      if (entry.contentKey !== contentKey) {
        const badge = document.createElement('span'); badge.className = 'proximity-pin-badge'
        const sameCompany = members.every(pin => pin.company.trim().toLowerCase() === representative.company.trim().toLowerCase())
        if (sameCompany && /^77\s*cargo(?:[\s,]+l\.?l\.?c\.?)?$/i.test(representative.company.trim())) {
          const mark = document.createElement('img'); mark.src = cargoMarkUrl; mark.alt = ''; mark.setAttribute('aria-hidden', 'true'); mark.className = 'proximity-pin-brand'
          badge.append(mark)
        }
        const label = document.createElement('span'); label.className = 'proximity-pin-label'
        label.textContent = members.length > 1 ? `${members.length} trucks` : representative.label
        const status = document.createElement('i'); status.className = 'proximity-pin-status'; status.setAttribute('aria-hidden', 'true')
        badge.append(label, status); button.replaceChildren(badge)
        if (members.length > 1) {
          const leader = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
          leader.classList.add('proximity-cluster-leader'); leader.setAttribute('aria-hidden', 'true')
          const line = document.createElementNS('http://www.w3.org/2000/svg', 'path')
          line.setAttribute('d', 'M0 0 L24 -28 L40 -28'); leader.append(line)
          const dot = document.createElement('span'); dot.className = 'proximity-cluster-anchor'; dot.setAttribute('aria-hidden', 'true')
          button.prepend(leader, dot)
        }
        button.title = `${representative.company ? `${representative.company} · ` : ''}${label.textContent}`
        entry.contentKey = contentKey
      }
      button.setAttribute('aria-label', members.length > 1 ? `${members.length} trucks ${coincident ? 'at this position' : 'nearby'}` : `${representative.label}, ${STATUS_META[representative.status].label}${representative.recent ? '' : ', last-known position'}`)
      button.setAttribute('role', 'button')
      button.setAttribute('aria-pressed', String(!!selected))

    })
    markers.current.forEach((entry, key) => {
      if (!liveKeys.has(key)) { entry.marker.remove(); markers.current.delete(key) }
    })
    const sourceId = 'fleet-proximity-lines'
    const geometry = JSON.parse(routeData) as GeoJSON.LineString | null
    const data: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: focus && geometry ? [{ type: 'Feature', properties: {}, geometry }] : [] }
    const source = map.getSource(sourceId) as import('mapbox-gl').GeoJSONSource | undefined
    if (source) source.setData(data)
    else {
      map.addSource(sourceId, { type: 'geojson', data })
      map.addLayer({ id: `${sourceId}-casing`, type: 'line', source: sourceId, layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#ffffff', 'line-width': 10, 'line-opacity': 0.95 } })
      map.addLayer({ id: sourceId, type: 'line', source: sourceId, layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#2563eb', 'line-width': 6, 'line-opacity': 1 } })
      map.addLayer({ id: `${sourceId}-direction`, type: 'symbol', source: sourceId, layout: { 'symbol-placement': 'line', 'symbol-spacing': 90, 'text-field': '▶', 'text-size': 13, 'text-rotation-alignment': 'map', 'text-keep-upright': false, 'text-allow-overlap': true }, paint: { 'text-color': '#ffffff', 'text-halo-color': '#1d4ed8', 'text-halo-width': 1 } })
    }
    // Initial fit and explicit recenter only; selection/routing never moves the camera.
    const frameKey = String(recenter)
    if (!pins.length) framing.current = ''
    if (frameKey !== framing.current && pins.length) {
      const bounds = new mb.LngLatBounds()
      pins.forEach(pin => bounds.extend(pin.point))
      map.fitBounds(bounds, { padding: 65, maxZoom: 10, duration: 0 })
      framing.current = frameKey
    }
  }, [pinData, comparisonData, routeData, focusId, recenter, ready, viewportRevision])

  const homeKey = homePoint?.join(',')
  useEffect(() => {
    const map = mapRef.current, mb = moduleRef.current
    if (!ready || !homeKey || !map || !mb) return
    const label = document.createElement('span')
    label.className = 'proximity-home-pin'
    label.textContent = '⌂ Home'
    label.setAttribute('aria-label', 'Home base')
    const marker = new mb.Marker({ element: label }).setLngLat(homeKey.split(',').map(Number) as [number, number]).addTo(map)
    return () => { marker.remove() }
  }, [ready, homeKey])
  useEffect(() => {
    if (!ready || !homeKey || !homeVisit || homeVisit === homeFraming.current) return
    mapRef.current?.easeTo({ center: homeKey.split(',').map(Number) as [number, number], zoom: 15, duration: 500 })
    homeFraming.current = homeVisit
  }, [ready, homeKey, homeVisit])

  return <>
    {(!token || error) && <div className="proximity-map-unavailable" role="status"><strong>Map unavailable</strong><span>{!token ? 'Mapbox access is not configured.' : 'Map could not load.'} Truck selection remains available.</span></div>}
    {token && <div ref={container} className="proximity-canvas" hidden={error} aria-label="Geographic truck positions" />}
  </>
}
