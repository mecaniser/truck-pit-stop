import { useId, useState } from 'react'
import { ChevronDown, Gauge, MapPin } from 'lucide-react'
import type { BoardTruck } from './types'
import { readingCaption, readingSummary, retained, useTelemetryClock, type NumericReading, type ReadingProvenance } from './telemetry'
import './telemetry.css'

const provenanceKey = (reading: ReadingProvenance) => JSON.stringify([reading.source, reading.observed_at, reading.captured_at, reading.source_age_text])
const valueLabel = (reading: NumericReading) => `${reading.value.toLocaleString(undefined, { maximumFractionDigits: 1 })}${reading.unit === 'percent' ? '%' : reading.unit === 'count' ? '' : ` ${reading.unit}`}`

export default function TelemetrySummary({ truck, compact = false }: { truck: BoardTruck; compact?: boolean }) {
  const now = useTelemetryClock()
  const [expanded, setExpanded] = useState(false)
  const detailsId = useId()
  const location = retained(truck.telemetry?.location, now)
  const fields = [
    ['Motive odometer', truck.telemetry?.odometer, 'odometer'], ['Engine hours', truck.telemetry?.engine_hours, 'hours'],
    ['Speed', truck.telemetry?.speed, 'speed'], ['Fuel', truck.telemetry?.fuel, 'fuel'], ['Open faults', truck.telemetry?.fault_count, 'faults'],
  ] as const
  const readings = fields.flatMap(([label, raw, kind]) => {
    const reading = retained(raw, now)
    return reading && (!compact || kind === 'speed') ? [{ label, reading, kind }] : []
  })
  const provenance = [...(location ? [{ label: 'Location', reading: location }] : []), ...readings]
  const shared = provenance.length && provenance.every(({ reading }) => provenanceKey(reading) === provenanceKey(provenance[0].reading)) ? provenance[0].reading : null
  if (!provenance.length) return compact ? null : <p className="telemetry-muted">No truck readings yet.</p>
  const locationLabel = location && (location.label || (location.lat != null && location.lng != null ? `${location.lat.toFixed(5)}, ${location.lng.toFixed(5)}` : 'Location unavailable'))
  return <section className={`telemetry-summary${compact ? ' telemetry-summary--compact' : ''}`} aria-label="Reported truck readings">
    {location && <div className="telemetry-location" title={readingCaption(location, now)}>
      <MapPin size={15} aria-hidden="true" /><div><strong>{locationLabel}</strong>{!shared && <small>{readingSummary(location, now)}</small>}</div>
    </div>}
    {readings.length > 0 && <dl className="telemetry-metrics">{readings.map(({ label, reading, kind }) => <div className={`telemetry-metric telemetry-metric--${kind}`} key={kind} title={readingCaption(reading, now)}>
      <dt>{kind === 'speed' && <Gauge size={13} aria-hidden="true" />}{label}</dt>
      <dd>{valueLabel(reading)}</dd>
      {!shared && <small>{readingSummary(reading, now)}</small>}
    </div>)}</dl>}
    <div className="telemetry-footer">
      {shared && <small title={readingCaption(shared, now)}>{readingSummary(shared, now)}</small>}
      {!compact && <button type="button" className="telemetry-disclosure" aria-expanded={expanded} aria-controls={detailsId} onClick={() => setExpanded(!expanded)}>Reading details <ChevronDown size={14} aria-hidden="true" style={{ transform: expanded ? 'rotate(180deg)' : undefined }} /></button>}
    </div>
    {!compact && expanded && <div id={detailsId} className="telemetry-provenance">
      {provenance.map(({ label, reading }) => <div key={label}><strong>{label}{'basis' in reading && reading.basis ? ` · ${reading.basis === 'dashboard_unspecified' ? 'dashboard' : reading.basis}` : ''}</strong><small>{readingCaption(reading, now)}</small></div>)}
    </div>}
  </section>
}
