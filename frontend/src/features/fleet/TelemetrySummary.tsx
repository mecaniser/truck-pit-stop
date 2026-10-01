import { useEffect, useState } from 'react'
import type { BoardTruck } from './types'
import { readingCaption, retained } from './telemetry'
import './telemetry.css'

export default function TelemetrySummary({ truck, compact = false }: { truck: BoardTruck; compact?: boolean }) {
  const [now, setNow] = useState(Date.now)
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 30000); return () => window.clearInterval(timer) }, [])
  const location = retained(truck.telemetry?.location, now)
  const fields = [
    ['Reported odometer', truck.telemetry?.odometer], ['Engine hours', truck.telemetry?.engine_hours],
    ['Reported speed', truck.telemetry?.speed], ['Fuel', truck.telemetry?.fuel], ['Open faults', truck.telemetry?.fault_count],
  ] as const
  const readings = fields.flatMap(([label, raw]) => { const reading = retained(raw, now); return reading ? [{ label, reading }] : [] })
  if (!location && !readings.length) return compact ? null : <p className="telemetry-muted">No reported truck readings.</p>
  return <div className={`telemetry-summary${compact ? ' telemetry-summary--compact' : ''}`} aria-label="Reported truck readings">
    {location && <div><strong>{location.label || (location.lat != null && location.lng != null ? `${location.lat.toFixed(5)}, ${location.lng.toFixed(5)}` : 'Location unavailable')}</strong><small>{readingCaption(location, now)}</small></div>}
    <dl>{(compact ? readings.filter((r) => ['Reported odometer', 'Reported speed'].includes(r.label)) : readings).map(({ label, reading }) => <div key={label}><dt>{label}{reading.basis === 'calibrated' ? ' · calibrated' : reading.basis === 'virtual' ? ' · virtual' : reading.basis === 'dashboard_unspecified' ? ' · dashboard' : ''}</dt><dd>{reading.value.toLocaleString(undefined, { maximumFractionDigits: 1 })}{reading.unit === 'percent' ? '%' : reading.unit === 'count' ? '' : ` ${reading.unit}`}</dd><small>{readingCaption(reading, now)}</small></div>)}</dl>
  </div>
}
