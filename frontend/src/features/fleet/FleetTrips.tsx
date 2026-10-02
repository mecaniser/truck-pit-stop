import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, ChevronDown, Clock3, MapPin, Route } from 'lucide-react'
import api from '@/lib/api'
import DatePicker from '@/components/DatePicker'
import { validDay } from '@/components/calendarGrid'
import { tripPreset, type TripPreset } from './tripFilters'
import type { BoardTruck } from './types'
import { fleetUnitLabel } from './helpers'
import './trips.css'

export interface FleetTrip {
  id: string; vehicle_id: string; unit_number: string | null
  fleet_customer_id: string; fleet_name: string | null
  started_at: string; ended_at: string; origin_label: string; destination_label: string
  distance_miles: number; driving_seconds: number; captured_at: string
  source: 'motive_dashboard_manual'
  stops: { location_label: string; arrived_at: string | null; departed_at: string | null; idle_seconds: number | null }[] | null
}
export interface FleetTripsResponse {
  items: FleetTrip[]; summary: { trip_count: number; distance_miles: number; driving_seconds: number }
  total: number; limit: number; offset: number; timezone: string; start_date: string; end_date: string
}
export interface TripFilters { vehicleId: string; start: string; end: string; preset?: TripPreset | 'custom' }
const number = (value: number) => value.toLocaleString(undefined, { maximumFractionDigits: 1 })
function duration(seconds: number) {
  const minutes = Math.round(seconds / 60)
  return minutes >= 60 ? `${Math.floor(minutes / 60)}h ${minutes % 60}m` : `${minutes}m`
}

export default function FleetTrips({ trucks, filters, onFilters, onOpenTruck }: {
  trucks: BoardTruck[]; filters: TripFilters; onFilters: (filters: TripFilters) => void; onOpenTruck: (id: string) => void
}) {
  const [offset, setOffset] = useState(0)
  const [expanded, setExpanded] = useState<string | null>(null)
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  const dateSpan = (Date.parse(filters.end) - Date.parse(filters.start)) / 86400000
  const validDates = validDay(filters.start) && validDay(filters.end) && Number.isFinite(dateSpan) && dateSpan >= 0 && dateSpan < 31
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
  const update = (next: Partial<TripFilters>) => { setOffset(0); setExpanded(null); onFilters({ ...filters, ...next }) }
  const time = (value: string) => new Date(value).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit', timeZone: timezone })
  const day = (value: string) => new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: timezone })
  return (
    <section className="fleet-trips" aria-label="Trip history">
      <div className="trips-heading">
        <div><h2>Trip history</h2><p>Imported trips · {timezone.replace(/_/g, ' ')}</p></div>
        {selectedTruck && <button type="button" className="dbtn dbtn-ghost" onClick={() => onOpenTruck(selectedTruck.id)}><ArrowLeft size={15} /> Back to truck {selectedTruck.unit_number}</button>}
      </div>
      <div className="trips-presets" role="group" aria-label="Trip time span">
        {([['day', 'Day', 'Today'], ['week', 'Week', 'Monday through today'], ['month', 'Month', 'This month through today']] as const).map(([preset, label, title]) => <button key={preset} type="button" title={title} aria-pressed={filters.preset === preset} onClick={() => update({ ...tripPreset(preset), preset })}>{label}</button>)}
        <button type="button" aria-pressed={!filters.preset || filters.preset === 'custom'} onClick={() => { update({ preset: 'custom' }); document.getElementById('trip-start')?.focus() }}>Custom</button>
      </div>
      <div className="trips-filters">
        <label>Truck<select value={filters.vehicleId} onChange={e => update({ vehicleId: e.target.value })}>
          <option value="">All trucks</option>
          {trucks.map(t => <option key={t.id} value={t.id}>{fleetUnitLabel(t)}</option>)}
        </select></label>
        <DatePicker showDayDetails={false} id="trip-start" label="From" value={filters.start} max={validDay(filters.end) ? filters.end : undefined} onChange={start => update({ start, preset: 'custom' })} />
        <DatePicker showDayDetails={false} id="trip-end" label="To" value={filters.end} min={validDay(filters.start) ? filters.start : undefined} onChange={end => update({ end, preset: 'custom' })} className="trips-end-date" />
      </div>
      {!validDates ? <p role="alert">Choose a date range of up to 31 days.</p> : !validVehicle ? <p role="alert">This truck is no longer available. Select another truck.</p> : query.isPending ? <p role="status" className="trips-message">Loading trips…</p> : query.isError ? <div role="alert" className="trips-message">Trips could not be loaded. <button type="button" className="dbtn" onClick={() => query.refetch()}>Retry</button></div> : query.data && <>
        <div className="trips-totals" aria-label="Imported trip totals">
          <div><Route size={18} /><span><strong>{number(query.data.summary.trip_count)}</strong><small>Trips</small></span></div>
          <div><MapPin size={18} /><span><strong>{number(query.data.summary.distance_miles)} <em>mi</em></strong><small>Distance</small></span></div>
          <div><Clock3 size={18} /><span><strong>{duration(query.data.summary.driving_seconds)}</strong><small>Driving</small></span></div>
        </div>
        {query.data.total === 0 ? <div className="trips-empty"><Route size={28} /><h3>No imported trips</h3><p>No trip history has been imported for this selection.</p></div> : <>
          <div className="trips-list">
            {query.data.items.map(trip => {
              const open = expanded === trip.id
              const truck = trucks.find(t => t.id === trip.vehicle_id)
              const label = truck ? fleetUnitLabel(truck) : `${trip.fleet_name || 'Truck'} ${trip.unit_number || ''}`
              return <article className={`trip-card${open ? ' is-open' : ''}`} key={trip.id}>
                <button className="trip-summary" type="button" aria-expanded={open} aria-controls={`trip-${trip.id}`} onClick={() => setExpanded(open ? null : trip.id)}>
                  <span className="trip-unit">{label}<small>{day(trip.started_at)} · {time(trip.started_at)}–{day(trip.ended_at) !== day(trip.started_at) ? `${day(trip.ended_at)} ` : ''}{time(trip.ended_at)}</small></span>
                  <span className="trip-route"><span>{trip.origin_label}</span><ArrowRight size={15} /><span>{trip.destination_label}</span></span>
                  <span className="trip-metrics"><strong>{number(trip.distance_miles)} <small>mi</small></strong><span>{duration(trip.driving_seconds)}</span></span>
                  <ChevronDown size={18} className={`trip-chevron${open ? ' is-open' : ''}`} />
                </button>
                {open && <div className="trip-expanded" id={`trip-${trip.id}`}>
                  <ol className="trip-timeline">
                    <li><span className="trip-timeline-dot" /><div><small>Departure · {time(trip.started_at)}</small><strong>{trip.origin_label}</strong></div></li>
                    {trip.stops?.map((stop, i) => <li key={i}><span className="trip-timeline-dot stop" /><div><small>Stop{stop.arrived_at ? ` · ${time(stop.arrived_at)}` : ''}{stop.departed_at ? `–${time(stop.departed_at)}` : ''}{stop.idle_seconds != null ? ` · ${duration(stop.idle_seconds)} idle` : ''}</small><strong>{stop.location_label}</strong></div></li>)}
                    <li><span className="trip-timeline-dot end" /><div><small>Arrival · {time(trip.ended_at)}</small><strong>{trip.destination_label}</strong></div></li>
                  </ol>
                  <div className="trip-footer"><span>{trip.stops === null ? 'Stop details unavailable' : `${trip.stops.length} stops`} · Captured {new Date(trip.captured_at).toLocaleString()}</span><button type="button" className="dbtn dbtn-ghost" onClick={() => onOpenTruck(trip.vehicle_id)}>View truck <ArrowRight size={14} /></button></div>
                </div>}
              </article>
            })}
          </div>
          {query.data.total > 50 && <div className="trips-pagination"><button type="button" className="dbtn" disabled={offset === 0} onClick={() => { setOffset(Math.max(0, offset - 50)); setExpanded(null) }}>Previous</button><span>{offset + 1}–{Math.min(offset + 50, query.data.total)} of {query.data.total}</span><button type="button" className="dbtn" disabled={offset + 50 >= query.data.total} onClick={() => { setOffset(offset + 50); setExpanded(null) }}>Next</button></div>}
        </>}
      </>}
    </section>
  )
}
