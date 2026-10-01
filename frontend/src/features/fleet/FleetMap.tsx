import { memo, useEffect, useRef, useState } from 'react'
import type { Map as MapboxMap, Marker as MapboxMarker } from 'mapbox-gl'
import type { BoardTruck } from './types'
import { fleetUnitLabel } from './helpers'
import { readingCaption, retained, truckCoordinates, truckLocation } from './telemetry'
import 'mapbox-gl/dist/mapbox-gl.css'
import './telemetry.css'

function FleetMap({ trucks, focusId, onSelect, compact }: { trucks: BoardTruck[]; focusId?: string; onSelect?: (t: BoardTruck) => void; compact?: boolean }) {
  const container = useRef<HTMLDivElement>(null)
  const [now, setNow] = useState(Date.now)
  const [error, setError] = useState(false)
  const [ready, setReady] = useState(0)
  const mapRef = useRef<MapboxMap>()
  const moduleRef = useRef<typeof import('mapbox-gl').default>()
  const markers = useRef<MapboxMarker[]>([])
  const captions = useRef<{ node: HTMLElement; reading: Parameters<typeof readingCaption>[0]; prefix: string }[]>([])
  const fitted = useRef(false)
  const focusRef = useRef<string | undefined>()
  const locationData = JSON.stringify(trucks.map((truck) => ({ ...truck, telemetry: {
    ...truck.telemetry, location: truckLocation(truck, now), speed: retained(truck.telemetry?.speed, now),
  } })))
  const token = import.meta.env.VITE_MAPBOX_TOKEN || ''
  const onSelectRef = useRef(onSelect)
  onSelectRef.current = onSelect
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 30000); return () => window.clearInterval(timer) }, [])
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
      map.addControl(new mb.NavigationControl(), 'top-right')
      mapRef.current = map
      moduleRef.current = mb
      setReady((value) => value + 1)
      if (typeof ResizeObserver !== 'undefined') { observer = new ResizeObserver(() => map?.resize()); observer.observe(container.current) }
    }).catch(() => { if (!cancelled) setError(true) })
    return () => { cancelled = true; observer?.disconnect(); markers.current.forEach((marker) => marker.remove()); markers.current = []; map?.remove(); mapRef.current = undefined; fitted.current = false }
  }, [token])
  useEffect(() => {
    const map = mapRef.current
    const mb = moduleRef.current
    if (!map || !mb) return
    const trucks = JSON.parse(locationData) as BoardTruck[]
    const now = Date.now()
    markers.current.forEach((marker) => marker.remove())
    markers.current = []
    captions.current = []
    const groups = new Map<string, { point: [number, number]; trucks: BoardTruck[] }>()
    trucks.forEach((truck) => {
      const point = truckCoordinates(truck, now)
      if (!point) return
      const key = point.join(',')
      const group = groups.get(key) || { point, trucks: [] }
      group.trucks.push(truck); groups.set(key, group)
    })
    const bounds = new mb.LngLatBounds()
    groups.forEach(({ point, trucks: members }) => {
      bounds.extend(point)
      const button = document.createElement('button')
      button.className = 'fleet-map-marker'
      button.type = 'button'
      button.textContent = members.length > 1 ? String(members.length) : fleetUnitLabel(members[0])
      button.setAttribute('aria-label', members.length > 1 ? `${members.length} trucks at this reported position` : `Reported position for ${fleetUnitLabel(members[0])}`)
      const content = document.createElement('div'); content.className = 'fleet-map-popup'
      members.forEach((truck) => {
        const select = document.createElement('button'); select.type = 'button'
        select.textContent = `${fleetUnitLabel(truck)} · ${truck.board_membership_company_name || 'Fleet unavailable'} · ${truckLocation(truck, now)?.label || 'Reported coordinates'}`
        select.addEventListener('click', () => onSelectRef.current?.(truck))
        const source = document.createElement('small'); source.textContent = readingCaption(truckLocation(truck, now)!)
        content.append(select, source)
        captions.current.push({ node: source, reading: truckLocation(truck, now)!, prefix: '' })
        const speed = retained(truck.telemetry?.speed, now)
        if (speed) { const metric = document.createElement('small'); metric.textContent = `Reported speed ${speed.value} mph · ${readingCaption(speed)}`; content.append(metric); captions.current.push({ node: metric, reading: speed, prefix: `Reported speed ${speed.value} mph · ` }) }
      })
      markers.current.push(new mb.Marker({ element: button }).setLngLat(point).setPopup(new mb.Popup({ offset: 20 }).setDOMContent(content)).addTo(map))
    })
    const focus = trucks.find((truck) => truck.id === focusId)
    const focusPoint = focus && truckCoordinates(focus, now)
    if (focusPoint && (!fitted.current || focusRef.current !== focusId)) map.jumpTo({ center: focusPoint, zoom: 10 })
    else if (groups.size && !fitted.current) map.fitBounds(bounds, { padding: 55, maxZoom: 11, duration: 0 })
    fitted.current = groups.size > 0
    focusRef.current = focusId
  }, [locationData, focusId, ready])
  useEffect(() => {
    captions.current.forEach(({ node, reading, prefix }) => { node.textContent = prefix + readingCaption(reading) })
  }, [now])
  return <section aria-label="Fleet geographic map">
    {!token || error ? <p role="status">{!token ? 'Map unavailable: Mapbox access is not configured.' : 'Map could not load. Reported locations remain available below.'}</p> : null}
    {token && <div ref={container} className={`fleet-geographic-map${compact ? ' fleet-geographic-map--compact' : ''}`} style={error ? { display: 'none' } : undefined} aria-label="Geographic truck positions" />}
    <p className="telemetry-muted">Last reported positions. Source and age are shown for each truck.</p>
    <div className="fleet-map-list">{trucks.map((truck) => {
      const location = truckLocation(truck, now)
      const coords = truckCoordinates(truck, now)
      const speed = retained(truck.telemetry?.speed, now)
      return <button type="button" key={truck.id} aria-current={focusId === truck.id ? 'true' : undefined} onClick={() => onSelect?.(truck)}>
        <strong>{fleetUnitLabel(truck)}</strong> · {truck.board_membership_company_name || 'Fleet unavailable'} · {location?.label || (coords ? `${coords[1].toFixed(5)}, ${coords[0].toFixed(5)}` : 'Location unknown')}
        {!coords && <small>No verified coordinates · no map pin</small>}
        {location && <small>{readingCaption(location)}</small>}
        {speed && <small>Reported speed {speed.value} mph · {readingCaption(speed)}</small>}
      </button>
    })}</div>
    {!trucks.length && <p>No trucks in this view.</p>}
  </section>
}
export default memo(FleetMap)
