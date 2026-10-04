import { useState, useRef, useEffect, type ReactNode } from 'react'
import { Popover, PopoverButton, PopoverPanel } from '@headlessui/react'
import { ArrowLeft, ArrowUpRight, Trophy, Info, X } from 'lucide-react'
import type { FleetTrip, FleetTripsResponse } from './FleetTrips'
import type { BoardTruck } from './types'
import { fleetUnitLabel } from './helpers'
import { activityRanking, routeMovementSummary, tripFuel, groupTripDays, summarizeTrips } from './tripAggregation'

const num = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 1 })
const hours = (n: number) => `${(n / 3600).toFixed(1)}h`
const label = (date: string) => new Date(`${date}T12:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
export default function TripOverview({ data, trucks, timezone, selected, onSelectTruck, renderDetails }: {
  data: FleetTripsResponse; trucks: BoardTruck[]; timezone: string; selected: boolean
  onSelectTruck: (id: string) => void; renderDetails: (items: FleetTrip[], endpoints?: { first?: string; last?: string }) => ReactNode
}) {
  const panel = useRef<HTMLDivElement>(null)
  const detailBack = useRef<HTMLButtonElement>(null)
  const routeTrigger = useRef<HTMLButtonElement | null>(null)
  const [metric, setMetric] = useState<'miles' | 'seconds'>('miles')
  const [pattern, setPattern] = useState(false)
  const [focusVehicle, setFocusVehicle] = useState<string | null>(null)
  const [showAllMovements, setShowAllMovements] = useState(false)
  const [focusDay, setFocusDay] = useState<string | null>(null)
  useEffect(() => { setShowAllMovements(false); if (focusDay) detailBack.current?.focus({ preventScroll: true }) }, [focusDay, focusVehicle])
  const days = groupTripDays(data.items, timezone)
  const rows = trucks.map(truck => {
    const trips = data.items.filter(t => t.vehicle_id === truck.id)
    return { truck, trips, fuel: tripFuel(trips), ...summarizeTrips(trips), days: groupTripDays(trips, timezone) }
  }).sort((a, b) => b[metric] - a[metric] || fleetUnitLabel(a.truck).localeCompare(fleetUnitLabel(b.truck)))
  const ranks = activityRanking(rows.map(row => ({ id: row.truck.id, value: row[metric], count: row.count })))
  const reporting = rows.filter(row => row.count > 0)
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
    const fuel = row.fuel
    const comparableFuel = reporting.flatMap(peer => peer.fuel && peer.fuel.kind === fuel?.kind && peer.fuel.miles > 0 ? [peer.fuel] : [])
    const rate = fuel && fuel.miles > 0 ? fuel.gallons / fuel.miles * 100 : null
    const medianRate = medianOf(comparableFuel.map(item => item.gallons / item.miles * 100))
    const canCompareFuel = rate !== null && comparableFuel.length > 1 && medianRate > 0
    const measure = metric === 'miles' ? 'distance' : 'driving hours'
    return <div className="otr-truck-identity">
      <button onClick={() => onSelectTruck(truck.id)}><span className="otr-identity"><span className="otr-unit-driver"><strong className="otr-truck-number"><span className="sr-only">{fleetUnitLabel(truck)} </span><span aria-hidden="true">{truck.unit_number || '—'}</span></strong><span className="otr-driver" aria-label={`Current driver: ${truck.driver_name || 'Unassigned'}`}>{truck.driver_name || 'Unassigned'}</span></span></span><ArrowUpRight size={15} /></button>
      <Popover className="otr-activity-explanation" key={metric}>
        <PopoverButton className="otr-rank-trigger" aria-label={`Explain activity for ${fleetUnitLabel(truck)}`}>
          {ranking?.leader ? <Trophy size={17} className="otr-leader" /> : <Info size={16} />}
          {pattern && ranking && <span className="otr-relative"><span><i style={{ transform: `scaleX(${ranking.ratio})` }} /></span><small>{Math.round(ranking.ratio * 100)}%</small></span>}
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
            <div className="otr-fuel-evidence"><span>{fuel?.kind === 'Est.' ? 'Fuel estimate · 30-day MPG model' : 'Measured fuel'}</span>
              {fuel ? <>
                <div className="otr-delta-grid"><div><strong>{num(fuel.gallons)}<small> gal</small></strong><span>{fuel.count < row.count ? 'Covered trips only' : 'Period total'}</span></div><div><strong>{rate !== null ? num(rate) : '—'}<small> gal/100 mi</small></strong><span>{fuel.kind === 'Est.' ? 'Modeled consumption' : 'Consumption rate'}</span></div></div>
                {canCompareFuel ? <strong className="otr-fuel-difference">{num(Math.abs((rate! / medianRate - 1) * 100))}% {rate! <= medianRate ? 'lower' : 'higher'} {fuel.kind === 'Est.' ? 'modeled' : 'measured'} fuel / mile <small>vs median {num(medianRate)} gal/100 mi · {comparableFuel.length} trucks</small></strong> : <small>No comparable fuel baseline</small>}
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
  const maxDay = Math.max(1, ...days.map(d => d[metric]))
  const active = days.find(d => d.date === focusDay)
  const detailTrips = active?.trips.filter(t => !focusVehicle || t.vehicle_id === focusVehicle) || []
  const detailTotals = summarizeTrips(detailTrips)
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
        {!selected && <div className="otr-control-set"><span>View</span><div className="otr-metric" role="group" aria-label="View"><button aria-pressed={!pattern} onClick={() => setPattern(false)}>Comparison</button><button aria-pressed={pattern} onClick={() => setPattern(true)}>Daily pattern</button></div></div>}
        <div className="otr-control-set"><span>Measure</span><div className="otr-metric" role="group" aria-label="Measure"><button aria-pressed={metric === 'miles'} onClick={() => setMetric('miles')}>Miles</button><button aria-pressed={metric === 'seconds'} onClick={() => setMetric('seconds')}>Driving hours</button></div></div>
      </div>
    </div>
    <div className={`otr-workspace${!selected ? " is-fleet" : ""}`}>
      {active && <section className={`otr-detail otr-panel-detail${truckDay ? ' is-truck-day' : ''}`} aria-label="Selected day routes"><div className="otr-panel-heading"><button ref={detailBack} className="dbtn" onClick={() => { setFocusDay(null); setFocusVehicle(null); requestAnimationFrame(() => routeTrigger.current?.focus({ preventScroll: true })) }}><ArrowLeft size={16} /> {selected ? 'Overview' : 'Back to comparison'}</button><h3>{focusVehicle ? `${fleetUnitLabel(trucks.find(t => t.id === focusVehicle)!)} · ` : ''}{label(active.date)}</h3><p>{detailTrips.length} trips · {num(detailTotals.miles)} mi · {hours(detailTotals.seconds)}</p></div><div className="otr-panel-routes" key={`${focusVehicle}-${focusDay}-${showAllMovements}`}>{renderDetails(shownTrips, { first: firstRecorded?.id, last: lastRecorded?.id })}</div>
      {truckDay && <footer className="otr-route-footer" aria-label="Route summary">
        <div className="otr-footer-stat"><span>Travel · {movement.travel.length} trips</span><strong>{num(movement.travelTotals.miles)} <small>mi</small></strong></div>
        {movement.longest && movement.travel.length > 0 && detailTotals.miles > 0 && <div className="otr-footer-stat"><span>Longest trip</span><strong>{num(movement.longest.distance_miles)} <small>mi · {Math.round(movement.longest.distance_miles / detailTotals.miles * 100)}%</small></strong></div>}
        {movement.short.length > 0 && <div className="otr-footer-stat"><span>Short movements · {movement.short.length}</span><strong>{num(movement.shortTotals.miles)} <small>mi · {Math.round(movement.shortTotals.seconds / 60)} min</small></strong></div>}
        <div className="otr-footer-actions">{movement.short.length > 0 && movement.travel.length > 0 && <button className="otr-show-movements" aria-pressed={showAllMovements} onClick={() => setShowAllMovements(!showAllMovements)}>{showAllMovements ? 'Focus on travel' : `Show all ${detailTrips.length} movements`}</button>}
        <Popover><PopoverButton className="otr-summary-info" aria-label="How routes are grouped"><Info size={17} /></PopoverButton><PopoverPanel anchor={{ to: 'top end', gap: 8, padding: 12 }} className="otr-activity-popover" role="dialog" aria-label="Route grouping"><h4>Route grouping</h4><p>Short movements: at most 1 mile and 15 minutes. Their purpose is unknown.</p><p>Trips belong to their departure date, including overnight trips. Totals include all movements.</p></PopoverPanel></Popover></div>
      </footer>}
      </section>}
      {!selected && !pattern && <div hidden={!!active} className="otr-comparison" tabIndex={0} aria-label="Truck activity comparison"><div className="otr-panel-heading"><h3>OTR fleet comparison</h3><p>Who covered the most · ranked by selected measure</p></div><table><thead><tr><th scope="col">Truck / current driver</th><th scope="col">{metric === 'miles' ? 'Distance' : 'Driving'}</th><th scope="col">{metric === 'miles' ? 'Driving' : 'Distance'}</th><th scope="col">Diesel</th><th scope="col">Days with trips</th></tr></thead><tbody>{rows.map(row => <tr key={row.truck.id}>
        <th scope="row">{identity(row.truck)}</th>
        <td>{row.count ? <div className="otr-bar-value"><span className="otr-bar-track" role="img" aria-label={`${Math.round((ranks.get(row.truck.id)?.ratio || 0) * 100)}% of highest ${metric === 'miles' ? 'distance' : 'driving hours'}`}><i style={{ transform: `scaleX(${row[metric] / max})` }} /></span><strong>{value(row[metric])}</strong></div> : <span className="otr-missing">No imported trips</span>}</td>
        <td>{row.count ? metric === 'miles' ? hours(row.seconds) : `${num(row.miles)} mi` : '—'}</td><td>{row.fuel ? <span className="otr-fuel"><strong>{num(row.fuel.gallons)} gal</strong><small>{row.fuel.kind}{row.fuel.count < row.count ? ` · ${row.fuel.count}/${row.count} segments` : ''}</small></span> : <span title="No fuel consumption data imported">—</span>}</td><td>{row.count ? row.days.length : '—'}</td>
      </tr>)}</tbody></table></div>}
      {!selected && pattern && <div hidden={!!active} className="otr-comparison otr-pattern" tabIndex={0} aria-label="Daily truck activity"><div className="otr-panel-heading"><h3>OTR fleet comparison</h3><p>When trucks moved · brighter = more · — = no imported trips</p></div><table><thead><tr><th scope="col">Truck / current driver</th>{days.map(day => <th scope="col" key={day.date}>{label(day.date)}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.truck.id}><th scope="row">{identity(row.truck)}</th>{days.map(day => {
        const cell = row.days.find(d => d.date === day.date)
        return <td key={day.date}>{cell ? <button style={{ backgroundColor: `rgba(233,190,72,${0.04 + cell[metric] / maxCell * 0.22})` }} aria-label={`${fleetUnitLabel(row.truck)}, ${label(day.date)}: ${value(cell[metric])}. View routes`} onClick={event => { routeTrigger.current = event.currentTarget; setFocusVehicle(row.truck.id); setFocusDay(day.date) }}>{value(cell[metric])}</button> : <span aria-label="No imported trips">—</span>}</td>
      })}</tr>)}</tbody></table></div>}
      <section className="otr-daily" aria-label="Daily activity chart"><div className="otr-panel-heading"><h3>{selected ? 'Daily activity' : 'Fleet activity by day'}</h3><p>Daily fleet volume · by departure date</p></div>
        <div className="otr-chart">{days.map(day => <button key={day.date} onClick={event => { routeTrigger.current = event.currentTarget; setFocusVehicle(null); setFocusDay(day.date) }} aria-label={`${label(day.date)}: ${num(day.miles)} miles, ${hours(day.seconds)} driving. View routes`}><strong>{value(day[metric])}</strong><span className="otr-chart-track"><i style={{ transform: `scaleY(${Math.max(.02, day[metric] / maxDay)})` }} /></span><span>{label(day.date)}</span></button>)}</div>
      </section>
      {selected && !active && <div className="otr-day-list">{days.map(day => <button key={day.date} onClick={event => { routeTrigger.current = event.currentTarget; setFocusVehicle(null); setFocusDay(day.date) }}><strong>{label(day.date)}</strong><span>{num(day.miles)} mi</span><span>{hours(day.seconds)} driving</span><span>{day.count} segments</span><ArrowUpRight size={16} /></button>)}</div>}
      <p className="otr-footnote">Leader = highest imported {metric === 'miles' ? 'distance' : 'driving hours'} in this period; ties share the trophy. Bars compare against that value. This is activity, not profitability. Missing imports may affect comparisons. Fuel marked Est. is calculated.</p>
    </div>
  </div>
}
