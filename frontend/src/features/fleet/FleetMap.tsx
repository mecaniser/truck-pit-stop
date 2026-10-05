import { memo, useEffect, useRef, useState } from 'react'
import { ArrowUpRight, ChevronDown, Home, LocateFixed, Search, X } from 'lucide-react'
import type { BoardTruck } from './types'
import { fleetUnitLabel, STATUS_META } from './helpers'
import { truckCoordinates, truckLocation, useTelemetryClock } from './telemetry'
import { formatDistance, positionAge, recentPosition } from './proximity'
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
  const clusterCardRef = useRef<HTMLElement>(null)
  const moveFocus = useRef(false)
  const [selection, setSelection] = useState(focusId)
  const [query, setQuery] = useState('')
  const [clusterIds, setClusterIds] = useState<string[]>([])
  const clusterTrucks = trucks.filter(truck => clusterIds.includes(truck.id) && truckCoordinates(truck, now))
  const [includeLastKnown, setIncludeLastKnown] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [recenter, setRecenter] = useState(0)
  useEffect(() => {
    if (clusterIds.length) { clusterCardRef.current?.focus({ preventScroll: true }); clusterCardRef.current?.scrollIntoView?.({ block: 'nearest' }) }
  }, [clusterIds])
  const selectedId = onFocusChange ? focusId : selection
  const focus = trucks.find(truck => truck.id === selectedId)
  const select = (id: string | undefined) => {
    moveFocus.current = true
    setClusterIds([]); setSelection(id); onFocusChange?.(id); setQuery(''); setExpanded(false)
  }
  useEffect(() => {
    if (moveFocus.current) { (headingRef.current || searchRef.current)?.focus(); moveFocus.current = false }
  }, [focus?.id, query])
  const [retry, setRetry] = useState(0)
  const road = useRoadProximity(trucks, focus, now, includeLastKnown, retry, !focus ? home.point : undefined)
  const nearby = road.nearby
  const visibleNearby = expanded ? nearby : nearby.slice(0, 3)
  const located = trucks.filter(truck => truckCoordinates(truck, now))
  const recentCount = located.filter(truck => recentPosition(truck, now)).length
  const searching = !!query.trim()
  const matches = trucks.filter(truck => `${fleetUnitLabel(truck)} ${truck.driver_name || ''} ${truckLocation(truck, now)?.label || ''}`.toLowerCase().includes(query.trim().toLowerCase()))
  const overviewRows = [...nearby, ...trucks.filter(truck => !nearby.some(row => row.truck.id === truck.id)).map(truck => ({ truck, miles: undefined, seconds: undefined }))]
  const rows = searching ? overviewRows.filter(row => matches.some(truck => truck.id === row.truck.id)) : !focus ? overviewRows : visibleNearby
  const missingOrigin = focus && !truckCoordinates(focus, now)
  const oldOrigin = focus && !missingOrigin && !recentPosition(focus, now) && !includeLastKnown
  const comparisonIds = visibleNearby.map(({ truck }) => truck.id)

  return <section className={`proximity${compact ? ' proximity--compact' : ''}`} aria-label="Fleet proximity map">
    <header className="proximity-toolbar">
      <div><strong>Fleet map</strong><span>{located.length} located · {trucks.length - located.length} without coordinates</span></div>
      <div className="proximity-map-controls">{homeAddress && <button type="button" title={homeAddress} disabled={!home.point} onClick={() => { select(undefined); setHomeVisit(value => value + 1) }}><Home size={16} />Home</button>}<button type="button" onClick={() => setRecenter(value => value + 1)}><LocateFixed size={16} />Recenter</button></div>
    </header>
    <div className="proximity-workspace">
      <div className="proximity-geography">
        <FleetMapCanvas trucks={trucks} focusId={focus?.id} nearbyIds={comparisonIds} route={road.geometry} now={now} recenter={recenter} homePoint={home.point} homeVisit={homeVisit} onFocus={select} onClusterOpen={ids => { setClusterIds(ids); setQuery('') }} />
        <div className="proximity-legend" aria-label="Map legend">
          {[...new Set(located.map(truck => truck.status))].map(status => <span key={status}><i style={{ background: STATUS_META[status].dot }} />{STATUS_META[status].label}</span>)}
          <span className="proximity-last-known-key"><i />Last known</span>
        </div>
      </div>
      <aside className="proximity-panel" aria-label="Truck proximity">
        <label className="proximity-search"><Search size={17} /><input ref={searchRef} type="search" aria-label="Find truck" placeholder="Find truck or driver" value={query} onChange={event => setQuery(event.target.value)} /></label>
        {clusterTrucks.length > 0 && <section ref={clusterCardRef} tabIndex={-1} className="proximity-cluster-card" aria-label="Trucks in selected cluster">
          <header><span>{clusterTrucks.length} overlapping positions</span><button type="button" aria-label="Close cluster" onClick={() => setClusterIds([])}><X size={15} /></button></header>
          {clusterTrucks.map(truck => <button type="button" className="proximity-popup-row" key={truck.id} onClick={() => select(truck.id)}>
            <i style={{ background: STATUS_META[truck.status].dot }} aria-hidden="true" /><strong>{fleetUnitLabel(truck)}</strong>
            <span className="proximity-popup-detail"><span>{STATUS_META[truck.status].label}</span>{!recentPosition(truck, now) && <small>Last known</small>}</span>
            <span className="proximity-popup-arrow" aria-hidden="true">›</span>
          </button>)}
        </section>}
        {focus && <div className="proximity-focus">
          <div className="proximity-focus-heading"><span>Comparing from</span><button type="button" aria-label="Clear selected truck" onClick={() => select(undefined)}><X size={17} /></button></div>
          <strong ref={headingRef} tabIndex={-1} className="proximity-unit">{fleetUnitLabel(focus)}</strong>
          <Status truck={focus} />
          <p>{truckLocation(focus, now)?.label || 'Location unavailable'}</p>
          <small>{positionAge(focus, now)}</small>
          {nearby[0] && <div className="proximity-route-summary" role="region" aria-label="Closest road route">
            <span className="proximity-route-caption">Closest by road</span>
            <div className="proximity-route-endpoints"><strong>{fleetUnitLabel(focus)}</strong><span aria-label="to">→</span><strong>{fleetUnitLabel(nearby[0].truck)}</strong></div>
            <div className="proximity-route-metrics"><strong>{formatDistance(nearby[0].miles)}</strong><span>{formatDriveTime(nearby[0].seconds)}<small>est. drive</small></span></div>
            <small>{road.geometryFailed ? 'Route preview unavailable' : road.geometry ? 'Blue route on map' : 'Loading route…'}</small>
          </div>}
          {road.phase === 'loading' && <div className="proximity-route-summary" role="status">Calculating road distances…</div>}
          {focus.driver_name && <p className="proximity-driver">{focus.driver_name}</p>}
          <div className="proximity-actions">
            {onSelect && <button type="button" onClick={() => onSelect(focus)}>Truck details<ArrowUpRight size={15} /></button>}
            {focus.driver_phone && /^[+\d\s().-]+$/.test(focus.driver_phone) && <a href={`tel:${focus.driver_phone.replace(/[^+\d]/g, '')}`}>Call driver</a>}
          </div>
        </div>}
        <div className="proximity-list-heading"><h3>{searching ? 'Search results' : focus ? 'Nearby trucks' : homeAddress ? 'Closest to home' : 'Select a truck'}</h3><span>{searching ? matches.length : focus ? nearby.length : trucks.length}</span></div>
        {!focus && homeAddress && <div className="proximity-home-summary">
          <button type="button" disabled={!home.point} onClick={() => setHomeVisit(value => value + 1)}>{homeAddress}</button>
          <div className="proximity-basis">{home.failed ? 'Home location unavailable.' : !home.point ? 'Locating home…' : road.phase === 'loading' ? 'Calculating road miles…' : road.phase === 'error' ? 'Road distances unavailable.' : 'Road miles from home · includes last-known positions'}</div>
        </div>}
        {focus && !searching && <>
          <div className="proximity-basis">Road miles · fastest driving routes · {includeLastKnown ? 'last-known positions included' : 'positions ≤15 min old'}</div>
          <label className="proximity-toggle"><input type="checkbox" checked={includeLastKnown} onChange={event => { setIncludeLastKnown(event.target.checked); setExpanded(false) }} />Include last-known</label>
          {missingOrigin ? <p className="proximity-empty">This truck has no verified coordinates. Distance is unavailable.</p> : oldOrigin ? <p className="proximity-empty">This truck’s position is old or undated. Include last-known to compare recorded positions.</p> : road.phase === 'loading' ? null : road.phase === 'unconfigured' ? <p className="proximity-empty" role="status">Road routing is not configured.</p> : road.phase === 'error' ? <p className="proximity-empty" role="status">Road distances unavailable. <button type="button" onClick={() => setRetry(value => value + 1)}>Retry routing</button></p> : road.phase === 'ready' && nearby.length === 0 ? <p className="proximity-empty">No road routes found.</p> : nearby.length === 0 ? <p className="proximity-empty">No other {includeLastKnown ? 'located' : 'recently located'} trucks.</p> : null}
          {road.unreachable > 0 && <p className="proximity-empty">{road.unreachable} truck{road.unreachable === 1 ? '' : 's'} without a road route.</p>}
        </>}
        <div className="proximity-rows">
          {rows.map(({ truck, miles, seconds }) => <button type="button" className="proximity-row" key={truck.id} aria-pressed={focus?.id === truck.id} onClick={() => select(truck.id)}>
            <span className="proximity-row-unit"><strong>{fleetUnitLabel(truck)}</strong><i role="img" aria-label={STATUS_META[truck.status].label} title={STATUS_META[truck.status].label} style={{ background: STATUS_META[truck.status].dot }} /></span>
            <span className="proximity-row-location" title={truckLocation(truck, now)?.label || 'Location unavailable'}>{truckLocation(truck, now)?.label || 'Location unavailable'}</span>
            <small className="proximity-row-age" title={positionAge(truck, now)}>{positionAge(truck, now)}</small>
            {miles != null && <><b className="proximity-row-miles">{formatDistance(miles)}</b><span className="proximity-row-time" title={`${formatDriveTime(seconds!)} estimated drive`}>{formatDriveTime(seconds!).replace(' hr', 'h').replace(' min', 'm')}</span></>}
          </button>)}
        </div>
        {focus && !searching && nearby.length > 3 && <button className="proximity-more" type="button" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>{expanded ? 'Closest 3' : `Show all ${nearby.length}`}<ChevronDown size={16} style={{ transform: expanded ? 'rotate(180deg)' : undefined }} /></button>}
        {searching && !matches.length && <p className="proximity-empty">No trucks match your search.</p>}
        {!trucks.length && <p className="proximity-empty">No trucks in this view.</p>}
        <footer>{focus ? 'Driving estimates · truck restrictions not applied.' : `${recentCount} recent · ${located.length - recentCount} last-known positions`}</footer>
      </aside>
    </div>
  </section>
}

function Status({ truck }: { truck: BoardTruck }) {
  const meta = STATUS_META[truck.status]
  return <span className="proximity-status"><i style={{ background: meta.dot }} />{meta.label}</span>
}
export default memo(FleetMap)
