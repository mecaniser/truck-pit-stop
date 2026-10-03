import { Fragment, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, ChevronDown, Clock3, MapPin, Route, Truck } from 'lucide-react'
import api from '@/lib/api'
import DatePicker from '@/components/DatePicker'
import BaseSelect from '@/components/BaseSelect'
import { validDay } from '@/components/calendarGrid'
import { tripPreset, tripWeeks, type TripPreset } from './tripFilters'
import type { BoardTruck } from './types'
import { fleetUnitLabel } from './helpers'
import './trips.css'

export interface TripMetrics {
  fuel_used_gallons: number | null; trip_mpg: number | null
  estimated_fuel_gallons: number | null; idle_seconds: number | null
  fuel_start_percent: number | null; fuel_end_percent: number | null
  estimate_baseline_mpg: number | null; estimate_baseline_captured_at: string | null
  estimate_baseline_period: 'last_30_days' | null
}
export interface FleetTrip {
  id: string; vehicle_id: string; unit_number: string | null
  fleet_customer_id: string; fleet_name: string | null
  started_at: string; ended_at: string; origin_label: string; destination_label: string
  distance_miles: number; driving_seconds: number; captured_at: string
  timestamp_precision?: 'second' | 'minute'
  metrics?: TripMetrics | null
  source: 'motive_dashboard_manual'
  stops: { location_label: string; arrived_at: string | null; departed_at: string | null; idle_seconds: number | null }[] | null
}
export interface FleetTripsResponse {
  imported_start?: string | null; imported_end?: string | null
  items: FleetTrip[]; summary: { truck_count: number; trip_count: number; distance_miles: number; driving_seconds: number; coverage: 'partial' }
  total: number; limit: number; offset: number; timezone: string; start_date: string; end_date: string
}
export interface TripFilters { vehicleId: string; start: string; end: string; preset?: TripPreset | 'custom' }
const number = (value: number) => value.toLocaleString(undefined, { maximumFractionDigits: 1 })
function duration(seconds: number) {
  if (seconds > 0 && seconds < 60) return `${seconds}s`
  const minutes = Math.round(seconds / 60)
  return minutes >= 60 ? `${Math.floor(minutes / 60)}h ${minutes % 60}m` : `${minutes}m`
}

export default function FleetTrips({ trucks, filters, onFilters, onOpenTruck }: {
  trucks: BoardTruck[]; filters: TripFilters; onFilters: (filters: TripFilters) => void; onOpenTruck: (id: string) => void
}) {
  const [offset, setOffset] = useState(0)
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  const dateSpan = (Date.parse(filters.end) - Date.parse(filters.start)) / 86400000
  const validDates = validDay(filters.start) && validDay(filters.end) && Number.isFinite(dateSpan) && dateSpan >= 0 && dateSpan < 31
  const weeks = validDates ? tripWeeks(filters.start, filters.end) : []
  const custom = !filters.preset || filters.preset === 'custom'
  const selectedTruck = trucks.find(t => t.id === filters.vehicleId)
  const validVehicle = !filters.vehicleId || !!selectedTruck
  const query = useQuery<FleetTripsResponse>({
    queryKey: ['fleet-trips', filters.vehicleId, filters.start, filters.end, timezone, offset],
    queryFn: async () => (await api.get('/fleet/trips', { params: {
      start_date: filters.start, end_date: filters.end, timezone,
      vehicle_id: filters.vehicleId || undefined, limit: 50, offset,
    } })).data,
    enabled: validDates && validVehicle,
  })
  const update = (next: Partial<TripFilters>) => { setOffset(0); onFilters({ ...filters, ...next }) }
  const day = (value: string) => new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: timezone })
  const importedDay = (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
  return (
    <section className={`fleet-trips${selectedTruck ? ' trips-selected-truck' : ''}`} aria-label="Trip history">
      <div className="trips-heading">
        <div><h2>{selectedTruck ? fleetUnitLabel(selectedTruck) : 'Trip history'}</h2><p>{timezone.replace(/_/g, ' ')}</p></div>
      </div>
      <div className="trips-time-controls">
        <div className="trips-presets" role="group" aria-label="Trip time span">
          {([['day', 'Day', 'Today'], ['week', 'Week', 'Monday through today'], ['month', 'Month', 'This month through today']] as const).map(([preset, label, title]) => <button key={preset} type="button" title={title} aria-pressed={filters.preset === preset} onClick={() => update({ ...tripPreset(preset), preset })}>{label}</button>)}
          <button type="button" aria-pressed={custom} aria-expanded={custom} aria-controls="trip-custom-dates" onClick={() => update({ preset: 'custom' })}>Custom</button>
        </div>
        {custom && <div className="trips-custom-dates" id="trip-custom-dates">
          <DatePicker compact showDayDetails={false} id="trip-start" label="From" value={filters.start} max={validDay(filters.end) ? filters.end : undefined} onChange={start => update({ start, preset: 'custom' })} />
          <DatePicker compact showDayDetails={false} id="trip-end" label="To" value={filters.end} min={validDay(filters.start) ? filters.start : undefined} onChange={end => update({ end, preset: 'custom' })} className="trips-end-date" />
        </div>}
      </div>
      <div className="trips-filters">
        <label>Truck<BaseSelect variant="dark" heightClass="h-11" optionHeightClass="min-h-11" value={filters.vehicleId} options={[{ value: '', label: 'All trucks' }, ...trucks.map(t => ({ value: t.id, label: fleetUnitLabel(t) }))]} onChange={vehicleId => update({ vehicleId })} /></label>
        <span className="trips-range-label">{day(`${filters.start}T12:00:00`)} – {day(`${filters.end}T12:00:00`)}</span>
      </div>
      {!validDates ? <p role="alert">Choose a date range of up to 31 days.</p> : !validVehicle ? <p role="alert">This truck is no longer available. Select another truck.</p> : query.isPending ? <p role="status" className="trips-message">Loading trips…</p> : query.isError ? <div role="alert" className="trips-message">Trips could not be loaded. <button type="button" className="dbtn" onClick={() => query.refetch()}>Retry</button></div> : query.data && <>
        <p className="trips-coverage" title="Dates show the earliest and latest imported departures. Gaps may remain.">Imported {query.data.imported_start && query.data.imported_end ? `${importedDay(query.data.imported_start)}–${importedDay(query.data.imported_end)}` : 'trips'} <span>· Partial</span></p>
        <div className="trips-totals" aria-label="Imported trip totals">
          <div><Truck size={18} />{selectedTruck ? <button type="button" className="trip-truck-link" onClick={() => onOpenTruck(selectedTruck.id)}><strong>Truck {selectedTruck.unit_number}</strong><small>View truck <ArrowRight size={14} /></small></button> : <span><strong>{number(query.data.summary.truck_count)}</strong><small>Trucks with trips</small></span>}</div>
          <div><Route size={18} /><span><strong>{number(query.data.summary.trip_count)}</strong><small>Trips</small></span></div>
          <div><MapPin size={18} /><span><strong>{number(query.data.summary.distance_miles)} <em>mi</em></strong><small>Distance</small></span></div>
          <div><Clock3 size={18} /><span><strong>{duration(query.data.summary.driving_seconds)}</strong><small>Driving</small></span></div>
        </div>
        {query.data.total === 0 ? <div className="trips-empty"><Route size={28} /><h3>No imported trips</h3><p>No trip history has been imported for this selection.</p></div> : <>
          {weeks.length > 1 ? <div className="trips-weeks">{weeks.map(week => <TripWeek key={`${filters.vehicleId}:${week.start}:${week.end}`} {...week} filters={filters} timezone={timezone} trucks={trucks} />)}</div> : <TripList key={`${filters.vehicleId}:${filters.start}:${filters.end}`} data={query.data} trucks={trucks} selected={!!selectedTruck} timezone={timezone} offset={offset} setOffset={setOffset} />}
        </>}
      </>}
    </section>
  )
}


interface TripListProps {
  data: FleetTripsResponse; trucks: BoardTruck[]; selected: boolean; timezone: string
  offset: number; setOffset: (offset: number) => void
}
function TripList({ data, trucks, selected, timezone, offset, setOffset }: TripListProps) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const time = (value: string) => new Date(value).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit', timeZone: timezone })
  const day = (value: string) => new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: timezone })
  return <>
          <div className="trips-list">
            {data.items.map((trip, index) => {
              const hasStops = !!trip.stops?.length
              const Summary = hasStops ? 'button' : 'div'
              const open = hasStops && expanded === trip.id
              const truck = trucks.find(t => t.id === trip.vehicle_id)
              const label = truck ? fleetUnitLabel(truck) : `${trip.fleet_name || 'Truck'} ${trip.unit_number || ''}`
              return <Fragment key={trip.id}>
                {(index === 0 || day(data.items[index - 1].started_at) !== day(trip.started_at)) && <h3 className="trip-day">{day(trip.started_at)}</h3>}
                <article aria-label={`${selected ? `Leg ${offset + index + 1}` : label} · ${trip.origin_label} → ${trip.destination_label}`} className={`trip-card${open ? ' is-open' : ''}`}>
                <Summary className={`trip-summary${hasStops ? '' : ' trip-static'}`} title={`Captured ${new Date(trip.captured_at).toLocaleString()}`} type={hasStops ? 'button' : undefined} aria-expanded={hasStops ? open : undefined} aria-controls={hasStops ? `trip-${trip.id}` : undefined} onClick={hasStops ? () => setExpanded(open ? null : trip.id) : undefined}>
                  <span className="trip-unit">{selected ? `Leg ${offset + index + 1}` : label}</span>
                  <span className="trip-route">
                    <span className="trip-point trip-departure"><time>{time(trip.started_at)}</time><i aria-hidden="true" /><span><small>Departure</small><strong>{trip.origin_label}</strong></span></span>
                    <span className="trip-point trip-arrival"><time>{day(trip.ended_at) !== day(trip.started_at) ? `${day(trip.ended_at)} ` : ''}{time(trip.ended_at)}</time><i aria-hidden="true" /><span><small>Arrival</small><strong>{trip.destination_label}</strong></span></span>
                  </span>
                  <span className="trip-readings"><span className="trip-metrics"><strong>{number(trip.distance_miles)} <small>mi</small></strong><span>{duration(trip.driving_seconds)}</span></span><TripVitals metrics={trip.metrics} /></span>
                  {hasStops && <ChevronDown size={18} className={`trip-chevron${open ? ' is-open' : ''}`} />}
                </Summary>
                {open && <div className="trip-expanded" id={`trip-${trip.id}`}>
                  {!!trip.stops?.length && <ol className="trip-timeline">
                    {trip.stops?.map((stop, i) => <li key={i}><span className="trip-timeline-dot stop" /><div><small>Stop{stop.arrived_at ? ` · ${time(stop.arrived_at)}` : ''}{stop.departed_at ? `–${time(stop.departed_at)}` : ''}{stop.idle_seconds != null ? ` · ${duration(stop.idle_seconds)} idle` : ''}</small><strong>{stop.location_label}</strong></div></li>)}
                  </ol>}
                  <div className="trip-footer"><span>{trip.stops?.length} stops · Captured {new Date(trip.captured_at).toLocaleString()}</span></div>
                </div>}
              </article></Fragment>
            })}
          </div>
          {data.total > 50 && <div className="trips-pagination"><button type="button" className="dbtn" disabled={offset === 0} onClick={() => { setOffset(Math.max(0, offset - 50)); setExpanded(null) }}>Previous</button><span>{offset + 1}–{Math.min(offset + 50, data.total)} of {data.total}</span><button type="button" className="dbtn" disabled={offset + 50 >= data.total} onClick={() => { setOffset(offset + 50); setExpanded(null) }}>Next</button></div>}
  </>
}

function TripWeek({ start, end, filters, timezone, trucks }: {
  start: string; end: string; filters: TripFilters; timezone: string; trucks: BoardTruck[]
}) {
  const [offset, setOffset] = useState(0)
  const query = useQuery<FleetTripsResponse>({
    queryKey: ['fleet-trips', filters.vehicleId, start, end, timezone, offset],
    queryFn: async () => (await api.get('/fleet/trips', { params: { start_date: start, end_date: end, timezone, vehicle_id: filters.vehicleId || undefined, limit: 50, offset } })).data,
  })
  const label = (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  const title = `${label(start)} – ${label(end)}`
  return <section className="trip-week" aria-label={`Week ${title}`}>
    <header className="trip-week-heading"><h3>{title}</h3>
      {query.data && <div className="trip-week-totals"><span>{number(query.data.total)} trips</span><strong>{number(query.data.summary.distance_miles)} <small>mi</small></strong><span>{duration(query.data.summary.driving_seconds)}</span></div>}
    </header>
    <div className="trip-week-body" tabIndex={0} aria-label={`Trips ${title}`}>
      {query.isPending ? <p role="status">Loading trips…</p> : query.isError ? <div role="alert">Trips could not be loaded. <button type="button" className="dbtn" onClick={() => query.refetch()}>Retry</button></div> : query.data && (query.data.total === 0 ? <p className="trip-week-empty">No imported trips</p> : <TripList key={`${filters.vehicleId}:${start}:${end}`} data={query.data} trucks={trucks} selected={!!filters.vehicleId} timezone={timezone} offset={offset} setOffset={setOffset} />)}
    </div>
  </section>
}

function TripVitals({ metrics: m }: { metrics?: TripMetrics | null }) {
  if (!m) return null
  const known = (value: number | null) => value != null && Number.isFinite(value) && value >= 0
  const actualFuel = known(m.fuel_used_gallons)
  const estimatedFuel = !actualFuel && known(m.estimated_fuel_gallons) && known(m.estimate_baseline_mpg) && m.estimate_baseline_mpg! > 0 && m.estimate_baseline_period === 'last_30_days'
  const mpg = actualFuel && m.fuel_used_gallons! > 0 && known(m.trip_mpg)
  const idle = known(m.idle_seconds)
  const start = known(m.fuel_start_percent); const end = known(m.fuel_end_percent)
  if (!actualFuel && !estimatedFuel && !mpg && !idle && !start && !end) return null
  return <span role="group" className="trip-vitals" aria-label="Trip fuel and efficiency">
    {actualFuel && <span className="trip-vital-fuel"><span className="trip-vital-label">Fuel used</span><span className="trip-vital-value">{number(m.fuel_used_gallons!)} <small>gal</small></span></span>}
    {estimatedFuel && <span className="trip-vital-fuel" title={`Estimated using ${number(m.estimate_baseline_mpg!)} MPG · 30-day average`}><span className="trip-vital-label">Est. fuel</span><span className="trip-vital-value">{number(m.estimated_fuel_gallons!)} <small>gal</small></span><small className="sr-only">Based on {number(m.estimate_baseline_mpg!)} MPG · 30-day avg</small></span>}
    {mpg && <span className="trip-vital-mpg"><span className="trip-vital-label">Trip efficiency</span><span className="trip-vital-value">{number(m.trip_mpg!)} <small>MPG</small></span></span>}
    {idle && <span className="trip-vital-idle"><span className="trip-vital-label">Idle time</span><span className="trip-vital-value">{duration(m.idle_seconds!)}</span></span>}
    {(start || end) && <span className="trip-vital-level"><span className="trip-vital-label">{start && end ? 'Fuel level' : start ? 'Fuel at start' : 'Fuel at end'}</span><span className="trip-vital-value">{start ? `${number(m.fuel_start_percent!)}%` : ''}{start && end ? ' → ' : ''}{end ? `${number(m.fuel_end_percent!)}%` : ''}</span>{start && end && <small>Start → End</small>}</span>}
  </span>
}
