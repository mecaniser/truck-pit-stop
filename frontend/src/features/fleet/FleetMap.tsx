import { memo, useEffect, useRef, useState } from 'react'
import { ArrowUpRight, ChevronDown, Home, LocateFixed, Search, X } from 'lucide-react'
import type { BoardTruck } from './types'
import { STATUS_META } from './helpers'
import { mapUnitLabel, mapCity } from './mapLabels'
import { truckCoordinates, truckLocation, useTelemetryClock } from './telemetry'
import { formatDistance, positionAge, recentPosition } from './proximity'
import { distanceColor } from './distanceColor'
import { formatDriveTime, useRoadProximity } from './roadProximity'
import { useFleetHome } from './fleetHome'
import FleetMapCanvas from './FleetMapCanvas'
import './proximity.css'

interface Props {
  trucks: BoardTruck[]
  focusId?: string
  onFocusChange?: (id: string | undefined) => void
  onSelect?: (truck: BoardTruck) => void
  homeAddress?: string
  compact?: boolean
}

function FleetMap({ trucks, focusId, onFocusChange, onSelect, compact, homeAddress }: Props) {
  const home = useFleetHome(homeAddress)
  const [homeVisit, setHomeVisit] = useState(0)
  const now = useTelemetryClock()
  const headingRef = useRef<HTMLElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const moveFocus = useRef(false)
  const [selection, setSelection] = useState(focusId)
  const [query, setQuery] = useState('')
  const [includeLastKnown, setIncludeLastKnown] = useState(true)
  const [expanded, setExpanded] = useState(false)
  const [recenter, setRecenter] = useState(0)
  const selectedId = onFocusChange ? focusId : selection
  const focus = trucks.find(truck => truck.id === selectedId)
  const select = (id: string | undefined) => {
    moveFocus.current = true
    setSelection(id); onFocusChange?.(id); setQuery(''); setExpanded(false)
  }
  useEffect(() => {
    if (moveFocus.current) { (headingRef.current || searchRef.current)?.focus(); moveFocus.current = false }
  }, [focus?.id, query])
  const [retry, setRetry] = useState(0)
  const road = useRoadProximity(trucks, focus, now, includeLastKnown, retry, home.point)
  const recommended = road.recommendation
  const nearby = road.nearby
  const visibleNearby = expanded ? nearby : nearby.slice(0, 3)
  const located = trucks.filter(truck => truckCoordinates(truck, now))
  const searching = !!query.trim()
  const matches = trucks.filter(truck => `${mapUnitLabel(truck)} ${truck.driver_name || ''} ${truckLocation(truck, now)?.label || ''}`.toLowerCase().includes(query.trim().toLowerCase()))
  const overviewRows = [...nearby, ...trucks.filter(truck => !nearby.some(row => row.truck.id === truck.id)).map(truck => ({ truck, miles: undefined, seconds: undefined }))]
  const rows = searching ? overviewRows.filter(row => matches.some(truck => truck.id === row.truck.id)) : !focus ? overviewRows : visibleNearby
  const homeMiles = !focus && homeAddress ? nearby.map(row => row.miles).filter(value => Number.isFinite(value) && value >= 0) : []
  const minMiles = Math.min(...homeMiles), maxMiles = Math.max(...homeMiles)
  const homeStatus = home.failed ? 'Home location unavailable' : !home.point ? 'Locating home…' : road.phase === 'loading' ? 'Calculating road miles…' : road.phase === 'error' ? 'Road distances unavailable' : road.phase === 'unconfigured' ? 'Road routing unavailable' : null
  const missingOrigin = focus && !truckCoordinates(focus, now)
  const oldOrigin = focus && !missingOrigin && !recentPosition(focus, now) && !includeLastKnown
  const comparisonIds = visibleNearby.map(({ truck }) => truck.id)

  return <section className={`proximity${compact ? ' proximity--compact' : ''}`} aria-label="Fleet proximity map">
    <header className="proximity-toolbar">
      <div className="proximity-map-toolbar"><div className="proximity-map-title"><strong>Fleet map</strong><span>{located.length} located · {trucks.length - located.length} without coordinates</span></div>
      <div className="proximity-map-controls">{homeAddress && <button type="button" title={homeAddress} disabled={!home.point} onClick={() => { select(undefined); setHomeVisit(value => value + 1) }}><Home size={16} />Home</button>}<button type="button" onClick={() => setRecenter(value => value + 1)}><LocateFixed size={16} />Recenter</button></div>
      </div>
      <div className="proximity-search-toolbar">
        <label className="proximity-search"><Search size={17} /><input ref={searchRef} type="search" aria-label="Find truck" placeholder="Find truck or driver" value={query} onChange={event => setQuery(event.target.value)} /></label>
      </div>
    </header>
    <div className="proximity-workspace">
      <div className="proximity-geography">
        <FleetMapCanvas trucks={trucks} focusId={focus?.id} nearbyIds={comparisonIds} route={road.geometry} now={now} recenter={recenter} homePoint={home.point} homeVisit={homeVisit} onFocus={select} />
        <div className="proximity-legend" aria-label="Map legend">
          {[...new Set(located.map(truck => truck.status))].map(status => <span key={status}><i style={{ background: STATUS_META[status].dot }} />{STATUS_META[status].label}</span>)}
          <span className="proximity-last-known-key"><i />Last known</span>
        </div>
      </div>
      <aside className="proximity-panel" aria-label="Truck proximity">
        <div className="proximity-panel-content">
        {focus && <div className="proximity-focus">
          <span className="sr-only">Comparing from</span>
          <div className="proximity-focus-heading">
            <strong ref={headingRef} tabIndex={-1} className="proximity-unit">{mapUnitLabel(focus)}</strong>
            {onSelect && <button className="proximity-details" type="button" onClick={() => onSelect(focus)}>Truck details<ArrowUpRight size={15} /></button>}
            <button className="proximity-clear" type="button" aria-label="Clear selected truck" onClick={() => select(undefined)}><X size={17} /></button>
          </div>
          <div className="proximity-focus-meta"><Status truck={focus} /><small>{positionAge(focus, now)}</small></div>
          <p className="proximity-focus-location">{mapCity(truckLocation(focus, now)?.label)}</p>
          {recommended && <div className="proximity-route-summary" role="region" aria-label="Closest road route">
            <span className="proximity-route-caption">{recommended.kind === 'shop' ? 'Shop is closest' : 'Closest truck by road'}</span>
            <div className="proximity-route-endpoints">
              <strong>{recommended.kind === 'shop' ? 'Shop' : mapUnitLabel(focus)}</strong>
              <div className="proximity-route-metrics"><strong>{formatDistance(recommended.distance.miles)}</strong><span aria-hidden="true">→</span><small>{formatDriveTime(recommended.distance.seconds)}</small></div>
              <strong>{recommended.kind === 'shop' ? mapUnitLabel(focus) : mapUnitLabel(nearby[0].truck)}</strong>
            </div>
            {(road.geometryFailed || !road.geometry) && <small role="status">{road.geometryFailed ? 'Route preview unavailable' : 'Loading route…'}</small>}
          </div>}
          {road.phase === 'loading' && <div className="proximity-route-summary" role="status">Calculating road distances…</div>}
          {focus.driver_name && <p className="proximity-driver">{focus.driver_name}</p>}
          {focus.driver_phone && /^[+\d\s().-]+$/.test(focus.driver_phone) && <div className="proximity-actions"><a href={`tel:${focus.driver_phone.replace(/[^+\d]/g, '')}`}>Call driver</a></div>}
        </div>}
        {(searching || focus || !homeAddress) && <div className="proximity-list-heading"><h3>{searching ? 'Search results' : focus ? 'Nearby trucks' : 'Select a truck'}</h3><span>{searching ? matches.length : focus ? nearby.length : trucks.length}</span></div>}
        {!focus && homeAddress && homeStatus && <div className="proximity-basis" role="status">{homeStatus}</div>}
        {focus && !searching && <>
          <label className="proximity-toggle"><input type="checkbox" checked={includeLastKnown} onChange={event => { setIncludeLastKnown(event.target.checked); setExpanded(false) }} />Include last-known</label>
          {missingOrigin ? <p className="proximity-empty">This truck has no verified coordinates. Distance is unavailable.</p> : oldOrigin ? <p className="proximity-empty">This truck’s position is old or undated. Include last-known to compare recorded positions.</p> : road.phase === 'loading' ? null : road.phase === 'unconfigured' ? <p className="proximity-empty" role="status">Road routing is not configured.</p> : road.phase === 'error' ? <p className="proximity-empty" role="status">Road distances unavailable. <button type="button" onClick={() => setRetry(value => value + 1)}>Retry routing</button></p> : road.phase === 'ready' && nearby.length === 0 ? <p className="proximity-empty">No road routes to other trucks.</p> : nearby.length === 0 ? <p className="proximity-empty">No other {includeLastKnown ? 'located' : 'recently located'} trucks.</p> : null}
          {road.unreachable > 0 && <p className="proximity-empty">{road.unreachable} truck{road.unreachable === 1 ? '' : 's'} without a road route.</p>}
        </>}
        <div className="proximity-rows">
          {rows.map(({ truck, miles, seconds }) => <button type="button" className="proximity-row" key={truck.id} aria-pressed={focus?.id === truck.id} onClick={() => select(truck.id)}>
            <span className="proximity-row-unit"><strong>{mapUnitLabel(truck)}</strong><i role="img" aria-label={STATUS_META[truck.status].label} title={STATUS_META[truck.status].label} style={{ background: STATUS_META[truck.status].dot }} /></span>
            <span className="proximity-row-location" title={mapCity(truckLocation(truck, now)?.label)}>{mapCity(truckLocation(truck, now)?.label)}</span>
            <small className="proximity-row-age" title={positionAge(truck, now)}>{positionAge(truck, now).startsWith('Last known') ? 'Last known' : positionAge(truck, now)}</small>
            {miles != null && <><b className="proximity-row-miles" style={{ color: homeMiles.length ? distanceColor(miles, minMiles, maxMiles) : undefined }}>{formatDistance(miles)}</b><span className="proximity-row-time" title={`${formatDriveTime(seconds!)} estimated drive`}>{formatDriveTime(seconds!).replace(' hr', 'h').replace(' min', 'm')}</span></>}
          </button>)}
        </div>
        {focus && !searching && nearby.length > 3 && <button className="proximity-more" type="button" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>{expanded ? 'Closest 3' : `Show all ${nearby.length}`}<ChevronDown size={16} style={{ transform: expanded ? 'rotate(180deg)' : undefined }} /></button>}
        {searching && !matches.length && <p className="proximity-empty">No trucks match your search.</p>}
        {!trucks.length && <p className="proximity-empty">No trucks in this view.</p>}
        </div>
        <footer className={!focus && homeAddress ? 'proximity-home-footer' : undefined}>
          {!focus && homeAddress && <div className="proximity-distance-legend" aria-label="Road distance to home color legend">
            <span className="proximity-distance-scale" aria-hidden="true" />
            <div><span>Nearest to home</span><span>Farthest from home</span></div>
          </div>}
          {focus && 'Driving estimates · truck restrictions not applied.'}
        </footer>
      </aside>
    </div>
  </section>
}

function Status({ truck }: { truck: BoardTruck }) {
  const meta = STATUS_META[truck.status]
  return <span className="proximity-status"><i style={{ background: meta.dot }} />{meta.label}</span>
}
export default memo(FleetMap)
