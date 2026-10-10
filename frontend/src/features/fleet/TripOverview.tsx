import { useState, useRef, useEffect, type ReactNode } from 'react'
import { Popover, PopoverButton, PopoverPanel } from '@headlessui/react'
import { ArrowLeft, ArrowUpRight, Trophy, Info, X, ChevronDown } from 'lucide-react'
import type { FleetTrip, FleetTripsResponse } from './FleetTrips'
import ActivityChart from './ActivityChart'
import SourceFuel from './SourceFuel'
import DriverRecord from './DriverRecord'
import { LocalDriverContact } from './CurrentDriver'
import { currentDriverName } from './driverIdentity'
import { summarizeFuel, type FuelDaily } from './fuelDaily'
import type { BoardTruck } from './types'
import { fleetUnitLabel } from './helpers'
import { activityRanking, routeMovementSummary, tripFuel, groupTripDays, summarizeTrips } from './tripAggregation'

const num = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 1 })
const hours = (n: number) => `${(n / 3600).toFixed(1)}h`
const label = (date: string) => new Date(`${date}T12:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
export default function TripOverview({ data, trucks, timezone, selected, onSelectTruck, renderDetails, preset, fuelRecords = [], fuelStatus = 'ready', fuelSummary }: {
  fuelSummary?: ReactNode;
  fuelStatus?: 'loading' | 'error' | 'ready'; fuelRecords?: FuelDaily[]; preset?: string; data: FleetTripsResponse; trucks: BoardTruck[]; timezone: string; selected: boolean
  onSelectTruck: (id: string) => void; renderDetails: (items: FleetTrip[], endpoints?: { first?: string; last?: string }) => ReactNode
}) {
  const panel = useRef<HTMLDivElement>(null)
  const detailBack = useRef<HTMLButtonElement>(null)
  const routeTrigger = useRef<HTMLButtonElement | null>(null)
  const [metric, setMetric] = useState<'miles' | 'seconds'>('miles')
  const [pattern, setPattern] = useState(false)
  const [showMissing, setShowMissing] = useState(false)
  const [focusVehicle, setFocusVehicle] = useState<string | null>(null)
  const [showAllMovements, setShowAllMovements] = useState(false)
  const [focusEnd, setFocusEnd] = useState<string | null>(null)
  const [focusDay, setFocusDay] = useState<string | null>(null)
  useEffect(() => { setShowAllMovements(false); if (focusDay) detailBack.current?.focus({ preventScroll: true }) }, [focusDay, focusVehicle, focusEnd])
  const days = groupTripDays(data.items, timezone)
  const rows = trucks.map(truck => {
    const trips = data.items.filter(t => t.vehicle_id === truck.id)
    return { truck, trips, fuel: tripFuel(trips), ...summarizeTrips(trips), days: groupTripDays(trips, timezone) }
  }).sort((a, b) => b[metric] - a[metric] || fleetUnitLabel(a.truck).localeCompare(fleetUnitLabel(b.truck)))
  const ranks = activityRanking(rows.map(row => ({ id: row.truck.id, value: row[metric], count: row.count })))
  const reporting = rows.filter(row => row.count > 0)
  const missing = rows.filter(row => !row.count && !summarizeFuel(fuelRecords, row.truck.id))
  const visibleRows = showMissing ? rows : rows.filter(row => row.count || summarizeFuel(fuelRecords, row.truck.id))
  const fuelHeading = 'Diesel · gal'
  const medianOf = (values: number[]) => {
    const sorted = [...values].sort((a, b) => a - b)
    const mid = Math.floor(sorted.length / 2)
    return sorted.length ? sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2 : 0
  }
  const median = medianOf(reporting.map(row => row[metric]))
  const medianHours = medianOf(reporting.map(row => row.seconds))
  const medianMiles = medianOf(reporting.map(row => row.miles))
  const identity = (truck: BoardTruck) => {
    const ranking = ranks.get(truck.id)
    const row = rows.find(item => item.truck.id === truck.id)!
    const sourceFuel = summarizeFuel(fuelRecords, truck.id)
    const fuel = row.fuel
    const comparableFuel = reporting.flatMap(peer => peer.fuel && peer.fuel.kind === fuel?.kind && peer.fuel.miles > 0 ? [peer.fuel] : [])
    const rate = fuel && fuel.miles > 0 ? fuel.gallons / fuel.miles * 100 : null
    const medianRate = medianOf(comparableFuel.map(item => item.gallons / item.miles * 100))
    const canCompareFuel = !fuelRecords.length && rate !== null && comparableFuel.length > 1 && medianRate > 0
    const measure = metric === 'miles' ? 'distance' : 'driving hours'
    return <div className="otr-truck-identity">
      <div className="otr-driver-identity"><button onClick={() => onSelectTruck(truck.id)}><span className="otr-identity"><span className="otr-unit-driver"><strong className="otr-truck-number"><span className="sr-only">{fleetUnitLabel(truck)} </span><span aria-hidden="true">{truck.unit_number || '—'}</span></strong><span className="otr-driver" aria-label={`Current driver: ${currentDriverName(truck) || 'Unassigned'}`}>{currentDriverName(truck) || 'Unassigned'}</span></span></span><ArrowUpRight size={15} /></button>
      <DriverRecord truck={truck} />
      <LocalDriverContact truck={truck} /></div>
      <Popover className="otr-activity-explanation" key={metric}>
        <PopoverButton className="otr-rank-trigger" aria-label={`Explain activity for ${fleetUnitLabel(truck)}`}>
          {ranking?.leader ? <Trophy size={17} className="otr-leader" /> : <Info size={16} />}
          {pattern && ranking && <span className="otr-relative"><span key={metric} style={{ animationDelay: `${Math.min(rows.findIndex(peer => peer.truck.id === truck.id), 15) * 35}ms` }}><i style={{ width: `${ranking.ratio * 100}%` }} /></span><small>{Math.round(ranking.ratio * 100)}%</small></span>}
        </PopoverButton>
        <PopoverPanel anchor={{ to: 'bottom start', gap: 8, padding: 12 }} className="otr-activity-popover" role="dialog" aria-label={`Activity criteria for ${fleetUnitLabel(truck)}`}>
          {({ close }) => <>
            <header><div><small>Truck {truck.unit_number} · {label(data.start_date)} – {label(data.end_date)}</small><h4>{measure === 'distance' ? 'Distance comparison' : 'Driving time comparison'}</h4></div><button aria-label="Close activity explanation" onClick={() => close()}><X size={18} /></button></header>
            {row.count > 0 && reporting.length > 1 ? <>
              <div className="otr-comparison-verdict">{value(row[metric])}<small>{Math.abs(row[metric] - median) < .05 ? 'Matches fleet median' : median > 0 ? `${num(Math.abs((row[metric] / median - 1) * 100))}% ${row[metric] > median ? 'above' : 'below'} fleet median` : 'Above zero fleet median'}</small></div>
              <table className="otr-facts"><thead><tr><th></th><th>Truck {truck.unit_number}</th><th>Fleet median</th></tr></thead><tbody>
                <tr><th>Distance</th><td>{num(row.miles)} mi</td><td>{num(medianMiles)} mi</td></tr>
                <tr><th>Driving</th><td>{hours(row.seconds)}</td><td>{hours(medianHours)}</td></tr>
                <tr><th>Days with trips</th><td>{row.days.length}</td><td>{num(medianOf(reporting.map(peer => peer.days.length)))}</td></tr>
              </tbody></table>
              <div className="otr-delta-baseline">{reporting.length} reporting trucks · partial imported history</div>
            </> : <p className="otr-no-comparison">{row.count ? 'No other reporting trucks to compare.' : 'No imported trips. Check import coverage.'}</p>}
            {sourceFuel && <div className="otr-fuel-evidence"><span>Motive fuel · source report dates</span><SourceFuel records={fuelRecords} vehicleId={truck.id} /></div>}
            <div className="otr-fuel-evidence"><span>{fuel?.kind === 'Est.' ? 'Calculated estimate · 30-day MPG model' : 'Measured fuel'}</span>
              {fuel ? <>
                <div className="otr-delta-grid"><div><strong>{num(fuel.gallons)}<small> gal</small></strong><span>{fuel.count < row.count ? 'Covered trips only' : 'Period total'}</span></div>{!sourceFuel && <div><strong>{rate !== null ? num(rate) : '—'}<small> gal/100 mi</small></strong><span>{fuel.kind === 'Est.' ? 'Modeled consumption' : 'Consumption rate'}</span></div>}</div>
                {canCompareFuel ? <strong className="otr-fuel-difference">{num(Math.abs((rate! / medianRate - 1) * 100))}% {rate! <= medianRate ? 'lower' : 'higher'} {fuel.kind === 'Est.' ? 'modeled' : 'measured'} fuel / mile <small>vs median {num(medianRate)} gal/100 mi · {comparableFuel.length} trucks</small></strong> : !sourceFuel && <small>No comparable fuel baseline</small>}
                <small>{fuel.count}/{row.count} trips · {num(fuel.miles)} covered mi{fuel.kind === 'Est.' ? ' · weekly fuel performance unverified' : ''}</small>
              </> : <strong>No fuel data</strong>}
            </div>
            <p className="otr-popover-note">Imported activity · current driver only</p>
            <button className="otr-popover-route" onClick={() => { close(); onSelectTruck(truck.id) }}>Review truck routes <ArrowUpRight size={16} /></button>
          </>}
        </PopoverPanel>
      </Popover>
    </div>
  }
  const max = Math.max(1, ...rows.map(r => r[metric]))
  const maxCell = Math.max(1, ...rows.flatMap(r => r.days.map(d => d[metric])))
  const active = focusDay && focusEnd ? { date: focusDay, trips: days.filter(d => d.date >= focusDay && d.date <= focusEnd).flatMap(d => d.trips) } : days.find(d => d.date === focusDay)
  const detailTrips = active?.trips.filter(t => !focusVehicle || t.vehicle_id === focusVehicle) || []
  const detailTotals = summarizeTrips(detailTrips)
  const fleetPeriodRows = trucks.map(truck => ({ truck, sourceFuel: summarizeFuel(fuelRecords, truck.id, focusDay || undefined, focusEnd || focusDay || undefined), ...summarizeTrips(active?.trips.filter(t => t.vehicle_id === truck.id) || []) })).filter(row => row.count > 0 || row.sourceFuel).sort((a, b) => b[metric] - a[metric] || fleetUnitLabel(a.truck).localeCompare(fleetUnitLabel(b.truck)))
  const contributionExplanation = (amount: number) => detailTotals[metric] > 0
    ? `${num(amount / detailTotals[metric] * 100)}% of the fleet’s recorded ${metric === 'miles' ? 'distance' : 'driving time'} for ${label(focusDay!)}${focusEnd && focusEnd !== focusDay ? ` – ${label(focusEnd)}` : ''}: ${value(amount)} out of ${value(detailTotals[metric])} across ${fleetPeriodRows.length} reporting trucks.`
    : 'No recorded total to calculate a share.'
  const fleetPeriodMax = Math.max(1, ...fleetPeriodRows.map(row => row[metric]))
  const movement = routeMovementSummary(detailTrips)
  const truckDay = !!focusVehicle || selected
  const periodTrips = truckDay ? data.items.filter(t => selected || t.vehicle_id === focusVehicle).slice().sort((a, b) => Date.parse(a.started_at) - Date.parse(b.started_at)) : []
  const firstRecorded = periodTrips[0]
  const lastRecorded = periodTrips.reduce<FleetTrip | undefined>((last, trip) => !last || Date.parse(trip.ended_at) > Date.parse(last.ended_at) ? trip : last, undefined)
  const shownTrips = truckDay && !showAllMovements && movement.travel.length ? movement.travel : detailTrips
  const value = (n: number) => metric === 'miles' ? `${num(n)} mi` : hours(n)
  return <div className="otr-overview" data-metric={metric} ref={panel} tabIndex={-1}>
    <div className="otr-section-heading"><div className="otr-context"><span>{selected ? 'Truck operations' : 'OTR operations'}</span><strong>{metric === 'miles' ? 'Distance traveled' : 'Time on the road'}</strong></div>
      <div className="otr-control-groups">
        {!selected && <div className="otr-control-set"><div className="otr-metric" role="group" aria-label="View"><button aria-pressed={!pattern} onClick={() => setPattern(false)}>Comparison</button><button aria-pressed={pattern} onClick={() => setPattern(true)}>Daily pattern</button></div></div>}
        <div className="otr-control-set"><div className="otr-metric" role="group" aria-label="Measure"><button aria-pressed={metric === 'miles'} onClick={() => setMetric('miles')}>Miles</button><button aria-pressed={metric === 'seconds'} onClick={() => setMetric('seconds')}>Driving hours</button></div></div>
      </div>
    </div>
    {(selected || pattern) && fuelSummary}
    <div className={`otr-workspace${!selected ? " is-fleet" : ""}`}>
      {active && <section className={`otr-detail otr-panel-detail${truckDay ? ' is-truck-day' : ''}`} aria-label={truckDay ? "Selected day routes" : "Fleet period breakdown"}><div className="otr-panel-heading"><button ref={detailBack} className="dbtn" onClick={() => { if (focusVehicle && focusEnd && !selected) { setFocusVehicle(null) } else { setFocusDay(null); setFocusEnd(null); setFocusVehicle(null); requestAnimationFrame(() => routeTrigger.current?.focus({ preventScroll: true })) } }}><ArrowLeft size={16} /> {selected ? 'Overview' : focusVehicle && focusEnd ? 'Back to fleet period' : 'Back to comparison'}</button><h3>{focusVehicle ? `${fleetUnitLabel(trucks.find(t => t.id === focusVehicle)!)} · ` : ''}{label(active.date)}{focusEnd && focusEnd !== active.date ? ` – ${label(focusEnd)}` : ''}</h3><p>{detailTrips.length} trips · {num(detailTotals.miles)} mi · {hours(detailTotals.seconds)}</p></div>{truckDay ? <div className="otr-panel-routes" key={`${focusVehicle}-${focusDay}-${showAllMovements}`}>{renderDetails(shownTrips, { first: firstRecorded?.id, last: lastRecorded?.id })}</div> : <div className="otr-fleet-period">
        <div className="otr-period-intro"><h4>{metric === 'miles' ? 'Distance by truck' : 'Driving hours by truck'}</h4><span>{fleetPeriodRows.length} trucks · share of period {metric === 'miles' ? 'distance' : 'driving'}</span></div>
        <div className="otr-contributions" role="group" aria-label="Truck contributions">{fleetPeriodRows.map((row, index) => <button key={`${row.truck.id}-${metric}-${focusDay}-${focusEnd}`} style={{ animationDelay: `${Math.min(index, 15) * 35}ms` }} aria-label={`${fleetUnitLabel(row.truck)}: ${value(row[metric])}. ${contributionExplanation(row[metric])} ${row.sourceFuel ? `Motive driving fuel ${row.sourceFuel.driving === null ? 'unavailable' : num(row.sourceFuel.driving) + ' gallons'}; idling fuel ${row.sourceFuel.idling === null ? 'unavailable' : num(row.sourceFuel.idling) + ' gallons'}. ` : ''}View truck routes for this period`} onClick={() => setFocusVehicle(row.truck.id)}>
          <span className="otr-contribution-truck"><strong>{row.truck.unit_number || fleetUnitLabel(row.truck)}</strong><span>{row.truck.driver_name || 'Unassigned'}{row.sourceFuel && <small className="otr-contribution-fuel">Driving {row.sourceFuel.driving === null ? '—' : num(row.sourceFuel.driving)} · Idling {row.sourceFuel.idling === null ? '—' : num(row.sourceFuel.idling)} gal</small>}</span></span>
          <span key={`${metric}-${focusDay}-${focusEnd}`} className="otr-contribution-track" aria-hidden="true" style={{ animationDelay: `${Math.min(index, 15) * 35}ms` }}><i style={{ width: `${row[metric] / fleetPeriodMax * 100}%` }} /></span>
          <strong>{value(row[metric])}</strong><span className="otr-contribution-share" title={contributionExplanation(row[metric])}>{detailTotals[metric] > 0 ? `${num(row[metric] / detailTotals[metric] * 100)}%` : '—'}</span><ArrowUpRight size={16} />
        </button>)}</div>
      </div>}
      {truckDay && fuelRecords.length > 0 && <div className="otr-route-fuel"><span>Motive fuel · selected report dates</span><SourceFuel records={fuelRecords} vehicleId={focusVehicle || (selected ? trucks[0]?.id : undefined)} start={focusDay || undefined} end={focusEnd || focusDay || undefined} /></div>}
      {truckDay && <footer className="otr-route-footer" aria-label="Route summary">
        <div className="otr-footer-stat"><span>Travel · {movement.travel.length} trips</span><strong>{num(movement.travelTotals.miles)} <small>mi</small></strong></div>
        {movement.longest && movement.travel.length > 0 && detailTotals.miles > 0 && <div className="otr-footer-stat"><span>Longest trip</span><strong>{num(movement.longest.distance_miles)} <small>mi · {Math.round(movement.longest.distance_miles / detailTotals.miles * 100)}%</small></strong></div>}
        {movement.short.length > 0 && <div className="otr-footer-stat"><span>Short movements · {movement.short.length}</span><strong>{num(movement.shortTotals.miles)} <small>mi · {Math.round(movement.shortTotals.seconds / 60)} min</small></strong></div>}
        <div className="otr-footer-actions">{movement.short.length > 0 && movement.travel.length > 0 && <button className="otr-show-movements" aria-pressed={showAllMovements} onClick={() => setShowAllMovements(!showAllMovements)}>{showAllMovements ? 'Focus on travel' : `Show all ${detailTrips.length} movements`}</button>}
        <Popover><PopoverButton className="otr-summary-info" aria-label="How routes are grouped"><Info size={17} /></PopoverButton><PopoverPanel anchor={{ to: 'top end', gap: 8, padding: 12 }} className="otr-activity-popover" role="dialog" aria-label="Route grouping"><h4>Route grouping</h4><p>Short movements: at most 1 mile and 15 minutes. Their purpose is unknown.</p><p>Trips belong to their departure date, including overnight trips. Totals include all movements.</p></PopoverPanel></Popover></div>
      </footer>}
      </section>}
      {!selected && !pattern && <div hidden={!!active} className="otr-comparison" tabIndex={0} aria-label="Truck activity comparison"><div className="otr-panel-heading"><h3>OTR fleet comparison</h3><p>Recorded output · ranked by selected measure</p><div className="otr-fleet-benchmarks">{reporting.length > 1 && <span className="otr-median-key"><b aria-hidden="true">│</b> Fleet median {value(median)}</span>}{fuelSummary}</div></div><table><thead><tr><th scope="col">Truck / current driver</th><th scope="col">{metric === 'miles' ? 'Distance' : 'Driving'}</th><th scope="col">{metric === 'miles' ? 'Driving' : 'Distance'}</th><th scope="col">{fuelHeading}</th><th scope="col">Days with trips</th></tr></thead><tbody>{visibleRows.map((row, index) => <tr key={`${row.truck.id}-${metric}`} style={{ animationDelay: `${Math.min(index, 15) * 35}ms` }}>
        <th scope="row">{identity(row.truck)}</th>
        <td>{row.count ? <div className="otr-bar-value"><span key={metric} className="otr-bar-track" style={{ animationDelay: `${Math.min(index, 15) * 35}ms` }} role="img" aria-label={`${Math.round((ranks.get(row.truck.id)?.ratio || 0) * 100)}% of highest ${metric === 'miles' ? 'distance' : 'driving hours'}; fleet median ${value(median)}`}><i style={{ width: `${row[metric] / max * 100}%` }} />{reporting.length > 1 && <b className="otr-median-tick" style={{ left: `${median / max * 100}%` }} title={`Fleet median: ${value(median)}`} />}</span><strong>{value(row[metric])}</strong></div> : <span className="otr-missing">No imported trips</span>}</td>
        <td>{row.count ? metric === 'miles' ? hours(row.seconds) : `${num(row.miles)} mi` : '—'}</td><td>{fuelStatus === 'ready' ? <SourceFuel records={fuelRecords} vehicleId={row.truck.id} /> : <span className="otr-fuel-missing">{fuelStatus === 'error' ? 'Fuel reports unavailable' : 'Loading fuel…'}</span>}{row.fuel && <span className="otr-fuel"><strong>{num(row.fuel.gallons)} gal</strong><small>{row.fuel.kind === 'Used' ? 'Reported trip fuel' : 'Calculated estimate'} · {row.miles > 0 ? `${num(row.fuel.miles / row.miles * 100)}% of trip miles` : 'Mileage coverage unavailable'}</small></span>}</td><td>{row.count ? row.days.length : '—'}</td>
      </tr>)}</tbody></table>{missing.length > 0 && <button className="otr-missing-toggle" aria-expanded={showMissing} onClick={() => setShowMissing(!showMissing)}><ChevronDown size={16} style={{ transform: showMissing ? 'rotate(180deg)' : undefined }} />{showMissing ? 'Hide' : 'Show'} {missing.length} {missing.length === 1 ? 'truck' : 'trucks'} without imported trips</button>}</div>}
      {!selected && pattern && <div hidden={!!active} className="otr-comparison otr-pattern" tabIndex={0} aria-label="Daily truck activity"><div className="otr-panel-heading"><h3>OTR fleet comparison</h3><p>Trips by start date · overnight trips stay on their start day</p><span className="otr-pattern-key">0 = recorded zero · — = no records · brighter = more</span></div><table><thead><tr><th scope="col">Truck / current driver</th>{days.map(day => <th scope="col" key={day.date}>{label(day.date)}</th>)}</tr></thead><tbody>{visibleRows.map((row, index) => <tr key={`${row.truck.id}-${metric}`} style={{ animationDelay: `${Math.min(index, 15) * 35}ms` }}><th scope="row">{identity(row.truck)}</th>{days.map(day => {
        const cell = row.days.find(d => d.date === day.date)
        return <td key={day.date}>{cell ? <button style={{ backgroundColor: `rgba(233,190,72,${0.04 + cell[metric] / maxCell * 0.22})` }} aria-label={`${fleetUnitLabel(row.truck)}, ${label(day.date)}: ${value(cell[metric])}. View routes`} onClick={event => { routeTrigger.current = event.currentTarget; setFocusEnd(null); setFocusVehicle(row.truck.id); setFocusDay(day.date) }}>{value(cell[metric])}</button> : <span aria-label="No imported trips">—</span>}</td>
      })}</tr>)}</tbody></table>{missing.length > 0 && <button className="otr-missing-toggle" aria-expanded={showMissing} onClick={() => setShowMissing(!showMissing)}><ChevronDown size={16} style={{ transform: showMissing ? 'rotate(180deg)' : undefined }} />{showMissing ? 'Hide' : 'Show'} {missing.length} {missing.length === 1 ? 'truck' : 'trucks'} without imported trips</button>}</div>}
      <ActivityChart data={data} timezone={timezone} metric={metric} selected={selected} preset={preset} onOpen={(start, end, trigger) => { routeTrigger.current = trigger; setFocusVehicle(null); setFocusEnd(end); setFocusDay(start) }} />
      {selected && !active && <div className="otr-day-list">{days.map(day => <button key={day.date} onClick={event => { routeTrigger.current = event.currentTarget; setFocusEnd(null); setFocusVehicle(null); setFocusDay(day.date) }}><strong>{label(day.date)}</strong><span>{num(day.miles)} mi</span><span>{hours(day.seconds)} driving</span><span>{day.count} segments</span><ArrowUpRight size={16} /></button>)}</div>}
      <p className="otr-footnote">Leader = highest imported {metric === 'miles' ? 'distance' : 'driving hours'} in this period; ties share the trophy. Bars compare against that value. This is activity, not profitability. Missing imports may affect comparisons. Motive fuel uses source report dates, whose timezone is unverified; trip distance may differ. Fuel marked Est. is calculated separately.</p>
    </div>
  </div>
}
