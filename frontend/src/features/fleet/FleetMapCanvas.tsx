import { useEffect, useRef, useState } from 'react'
import type { Map as MapboxMap, Marker as MapboxMarker } from 'mapbox-gl'
import type { BoardTruck } from './types'
import { fleetUnitLabel, STATUS_META } from './helpers'
import { truckCoordinates } from './telemetry'
import { recentPosition } from './proximity'
import 'mapbox-gl/dist/mapbox-gl.css'

interface Pin { id: string; label: string; status: BoardTruck['status']; point: [number, number]; recent: boolean }
interface Props { trucks: BoardTruck[]; focusId?: string; nearbyIds: string[]; now: number; recenter: number; onFocus: (id: string) => void }

export default function FleetMapCanvas({ trucks, focusId, nearbyIds, now, recenter, onFocus }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapboxMap>()
  const moduleRef = useRef<typeof import('mapbox-gl').default>()
  const markers = useRef<MapboxMarker[]>([])
  const [ready, setReady] = useState(false)
  const [error, setError] = useState(false)
  const framing = useRef('')
  const selectRef = useRef(onFocus)
  selectRef.current = onFocus
  const token = import.meta.env.VITE_MAPBOX_TOKEN || ''
  const pinData = JSON.stringify(trucks.flatMap(truck => {
    const point = truckCoordinates(truck, now)
    return point ? [{ id: truck.id, label: fleetUnitLabel(truck), status: truck.status, point, recent: recentPosition(truck, now) }] : []
  }))
  const comparisonData = JSON.stringify(nearbyIds)
  useEffect(() => {
    if (!token || !container.current) return
    let cancelled = false
    let map: MapboxMap | undefined
    let observer: ResizeObserver | undefined
    setError(false)
    void import('mapbox-gl').then(({ default: mb }) => {
      if (cancelled || !container.current) return
      map = new mb.Map({ container: container.current, accessToken: token, style: 'mapbox://styles/mapbox/streets-v12', center: [-98, 39], zoom: 3, attributionControl: true })
      map.on('error', () => { if (!cancelled) setError(true) })
      map.on('load', () => { if (!cancelled) setReady(true) })
      map.addControl(new mb.NavigationControl(), 'top-right')
      mapRef.current = map; moduleRef.current = mb
      if (typeof ResizeObserver !== 'undefined') { observer = new ResizeObserver(() => map?.resize()); observer.observe(container.current) }
    }).catch(() => { if (!cancelled) setError(true) })
    return () => { cancelled = true; observer?.disconnect(); markers.current.forEach(marker => marker.remove()); markers.current = []; map?.remove(); mapRef.current = undefined; framing.current = '' }
  }, [token])

  useEffect(() => {
    const map = mapRef.current, mb = moduleRef.current
    if (!map || !mb || !ready) return
    const pins = JSON.parse(pinData) as Pin[]
    const nearby = JSON.parse(comparisonData) as string[]
    const focus = pins.find(pin => pin.id === focusId)
    const neighbors = pins.filter(pin => nearby.includes(pin.id))
    markers.current.forEach(marker => marker.remove()); markers.current = []
    const groups = new Map<string, Pin[]>()
    pins.forEach(pin => { const key = pin.point.join(','); groups.set(key, [...(groups.get(key) || []), pin]) })
    groups.forEach(members => {
      const selected = members.find(pin => pin.id === focusId)
      const representative = selected || members.find(pin => pin.status === 'out_of_service') || members[0]
      const button = document.createElement('button')
      button.type = 'button'
      button.className = `proximity-pin${selected ? ' is-selected' : ''}${members.every(pin => !pin.recent) ? ' is-last-known' : ''}${focus && !selected && !members.some(pin => nearby.includes(pin.id)) ? ' is-dimmed' : ''}`
      button.style.setProperty('--pin-status', STATUS_META[representative.status].dot)
      button.textContent = members.length > 1 ? `${members.length} trucks` : representative.label
      button.setAttribute('aria-label', members.length > 1 ? `${members.length} trucks at this position` : `${representative.label}, ${STATUS_META[representative.status].label}${representative.recent ? '' : ', last-known position'}`)
      button.setAttribute('aria-pressed', String(!!selected))
      const marker = new mb.Marker({ element: button }).setLngLat(representative.point)
      if (members.length === 1) button.addEventListener('click', () => selectRef.current(representative.id))
      else {
        const content = document.createElement('div'); content.className = 'proximity-popup'
        members.forEach(pin => {
          const option = document.createElement('button'); option.type = 'button'
          option.textContent = `${pin.label} · ${STATUS_META[pin.status].label}${pin.recent ? '' : ' · Last known'}`
          option.addEventListener('click', () => { selectRef.current(pin.id); marker.getPopup()?.remove() })
          content.append(option)
        })
        marker.setPopup(new mb.Popup({ offset: 24 }).setDOMContent(content))
      }
      markers.current.push(marker.addTo(map))
    })
    const sourceId = 'fleet-proximity-lines'
    const data: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: focus ? neighbors.map(pin => ({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: [focus.point, pin.point] } })) : [] }
    const source = map.getSource(sourceId) as import('mapbox-gl').GeoJSONSource | undefined
    if (source) source.setData(data)
    else {
      map.addSource(sourceId, { type: 'geojson', data })
      map.addLayer({ id: sourceId, type: 'line', source: sourceId, paint: { 'line-color': '#b77900', 'line-width': 2, 'line-dasharray': [2, 2] } })
    }
    // Polling updates positions without stealing the manager's pan/zoom.
    const frameKey = `${focusId || 'fleet'}:${recenter}:${pins.length ? 'located' : 'empty'}:${nearby.join(',')}`
    if (frameKey !== framing.current && pins.length) {
      const points = focus ? [focus, ...neighbors] : pins
      const bounds = new mb.LngLatBounds()
      points.forEach(pin => bounds.extend(pin.point))
      map.fitBounds(bounds, { padding: 65, maxZoom: focus ? 12 : 10, duration: 0 })
      framing.current = frameKey
    }
  }, [pinData, comparisonData, focusId, recenter, ready])

  return <>
    {(!token || error) && <div className="proximity-map-unavailable" role="status"><strong>Map unavailable</strong><span>{!token ? 'Mapbox access is not configured.' : 'Map could not load.'} Truck selection and distances remain available.</span></div>}
    {token && <div ref={container} className="proximity-canvas" hidden={error} aria-label="Geographic truck positions" />}
  </>
}
