import { useState } from 'react'
import { ChartColumn, ChartLine } from 'lucide-react'
import BaseSelect from '@/components/BaseSelect'
import type { FleetTripsResponse } from './FleetTrips'
import { activityBuckets, activityPeriodNote, availableActivityIntervals, defaultActivityInterval, type ActivityInterval } from './tripAggregation'

const dateLabel = (date: string) => new Date(`${date}T12:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
const number = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 1 })
export default function ActivityChart({ data, timezone, metric, selected, preset, onOpen }: {
  data: FleetTripsResponse; timezone: string; metric: 'miles' | 'seconds'; selected: boolean; preset?: string
  onOpen: (start: string, end: string, trigger: HTMLButtonElement) => void
}) {
  const [chosenInterval, setInterval] = useState<ActivityInterval>(() => defaultActivityInterval(data.start_date, data.end_date, preset))
  const intervals = availableActivityIntervals(data.start_date, data.end_date, preset)
  const interval = intervals.includes(chosenInterval) ? chosenInterval : defaultActivityInterval(data.start_date, data.end_date, preset)
  const [style, setStyle] = useState<'columns' | 'line'>('columns')
  const calendarBuckets = activityBuckets(data.items, timezone, data.start_date, data.end_date, interval)
  const firstRecorded = calendarBuckets.findIndex(bucket => bucket.count > 0)
  const buckets = firstRecorded < 0 ? [] : calendarBuckets.slice(firstRecorded)
  const max = Math.max(1, ...buckets.map(b => b[metric]))
  const value = (n: number) => metric === 'miles' ? `${number(n)} mi` : `${(n / 3600).toFixed(1)}h`
  const compactValue = (n: number) => `${new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(metric === 'miles' ? n : n / 3600)}${metric === 'miles' ? ' mi' : 'h'}`
  const caption = (start: string, end: string) => interval === 'year' ? start.slice(0, 4) : interval === 'month' ? new Date(`${start}T12:00:00`).toLocaleDateString(undefined, { month: 'short', ...(data.start_date.slice(0, 4) !== data.end_date.slice(0, 4) ? { year: '2-digit' as const } : {}) }) : start === end ? dateLabel(start) : `${dateLabel(start)}–${dateLabel(end)}`
  const x = (i: number) => (i + .5) / buckets.length * 1000
  const y = (v: number) => 160 - v / max * 150
  // Break the line at missing imports instead of fabricating a zero or continuity.
  const path = buckets.map((b, i) => !b.count ? '' : `${i > 0 && buckets[i - 1].count ? 'L' : 'M'}${x(i)},${y(b[metric])}`).join(' ')
  return <section className="otr-daily" aria-label="Daily activity chart">
    <div className="otr-panel-heading otr-chart-heading">
      <div className="otr-chart-title"><h3>{selected ? 'Truck activity' : 'Fleet activity'}</h3>
        {intervals.length > 1 ? <label className="otr-interval"><span className="sr-only">Activity grouping</span><BaseSelect value={interval} onChange={v => setInterval(v as ActivityInterval)} options={intervals.map(v => ({ value: v, label: `By ${v}` }))} searchable={false} variant="dark" heightClass="h-11" optionHeightClass="min-h-11" /></label> : <span className="otr-fixed-grouping">{data.start_date === data.end_date ? 'Day total' : 'By day'}</span>}
        <div className="otr-chart-style" role="group" aria-label="Chart style"><button aria-label="Columns" title="Columns" aria-pressed={style === 'columns'} onClick={() => setStyle('columns')}><ChartColumn size={18} /></button><button aria-label="Line" title="Line" aria-pressed={style === 'line'} onClick={() => setStyle('line')}><ChartLine size={18} /></button></div>
      </div>
      <p>{metric === 'miles' ? 'Distance' : 'Driving hours'} · trips by start date · {selected ? 'select a period for routes' : 'select a period to compare trucks'}</p>
    </div>
    {buckets.length === 0 && <p className="otr-chart-missing">No imported trips in this period</p>}
    <div className="otr-period-scroll"><div className={`otr-period-chart is-${style}`} style={{ minWidth: buckets.length * (interval === 'week' ? 108 : interval === 'day' ? 66 : 52) }}>
      {style === 'line' && <svg className="otr-trend" viewBox="0 0 1000 170" preserveAspectRatio="none" aria-hidden="true"><path d={path} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" /></svg>}
      {buckets.map(b => <button key={b.start} disabled={!b.count} title={`${dateLabel(b.start)} – ${dateLabel(b.end)}: ${b.count ? `${value(b[metric])} · ${b.count} segments` : 'No imported trips'}`} aria-label={b.count ? `${dateLabel(b.start)}${b.start !== b.end ? ` – ${dateLabel(b.end)}` : ''}: ${number(b.miles)} miles, ${(b.seconds / 3600).toFixed(1)}h driving. ${selected ? 'View routes' : 'Compare trucks'}` : `${caption(b.start, b.end)}: No imported trips`} onClick={e => onOpen(b.start, b.end, e.currentTarget)}>
        <strong>{b.count ? compactValue(b[metric]) : '—'}</strong>
        <span className="otr-period-track">{b.count > 0 && (style === 'columns' ? <i style={{ height: `${b[metric] / max * 150}px` }} /> : <i className="otr-trend-dot" style={{ top: `${y(b[metric])}px` }} />)}</span>
        <span className="otr-period-label">{caption(b.start, b.end)}</span>
        {!selected && <small className="otr-reporting-count">{b.count ? `${new Set(b.trips.map(trip => trip.vehicle_id)).size} reporting` : 'No records'}</small>}
        {activityPeriodNote(b.start, b.end, interval, timezone) && <small className="otr-period-note">{activityPeriodNote(b.start, b.end, interval, timezone)}</small>}
      </button>)}
    </div></div>
    {buckets.some(b => !b.count) && <p className="otr-chart-missing">— No imported trips</p>}
  </section>
}
