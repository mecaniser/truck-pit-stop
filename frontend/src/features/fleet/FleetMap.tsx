import { useState } from 'react'
import type { BoardTruck } from './types'
import { STATUS_META } from './helpers'

// Schematic regional map. Projects real lat/lng into a 0–100 field centered on the
// yard. When live telematics is connected this component can be swapped for Mapbox GL
// with the same props — the rest of the UI is unchanged.
const YARD = { lat: 35.1168, lng: -80.7237 } // Matthews, NC (Truck Pit Stop)
const HQ = { x: 50, y: 62 }
const SCALE = 26 // field-units per degree

const ROADS: { name: string; pts: [number, number][] }[] = [
  { name: 'I-77', pts: [[50, 0], [49, 30], [50, 62], [51, 100]] },
  { name: 'I-85', pts: [[0, 78], [28, 70], [50, 62], [74, 50], [100, 38]] },
  { name: 'I-485', pts: [[50, 62], [70, 64], [80, 50], [74, 34], [54, 30], [34, 38], [28, 56], [40, 68], [50, 62]] },
  { name: 'US-74', pts: [[0, 50], [26, 56], [50, 62], [72, 70], [100, 82]] },
  { name: 'I-40', pts: [[0, 18], [30, 22], [60, 16], [100, 22]] },
]
const pathD = (pts: [number, number][]) => pts.map((p, i) => (i === 0 ? 'M' : 'L') + p[0] + ' ' + p[1]).join(' ')
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v))

function project(t: BoardTruck, i: number): { x: number; y: number } {
  if (t.lat == null || t.lng == null) {
    // park near the yard with deterministic jitter
    const jx = ((i * 37) % 9) - 4
    const jy = ((i * 53) % 7) - 5
    return { x: HQ.x + jx, y: HQ.y + jy }
  }
  return {
    x: clamp(HQ.x + (t.lng - YARD.lng) * SCALE, 5, 95),
    y: clamp(HQ.y - (t.lat - YARD.lat) * SCALE, 5, 95),
  }
}

function haversine(a: BoardTruck, b: BoardTruck): number {
  if (a.lat == null || a.lng == null || b.lat == null || b.lng == null) return Infinity
  const R = 3958.8, toRad = (d: number) => (d * Math.PI) / 180
  const dLat = toRad(b.lat - a.lat), dLng = toRad(b.lng - a.lng)
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2
  return Math.round(2 * R * Math.asin(Math.sqrt(h)))
}

export default function FleetMap({
  trucks, focusId, onSelect, compact,
}: { trucks: BoardTruck[]; focusId?: string; onSelect?: (t: BoardTruck) => void; compact?: boolean }) {
  const [hover, setHover] = useState<string | null>(null)
  const pos = new Map(trucks.map((t, i) => [t.id, project(t, i)]))
  const focus = focusId ? trucks.find((t) => t.id === focusId) : null
  const near = focus
    ? trucks.filter((t) => t.id !== focus.id).map((t) => ({ t, miles: haversine(focus, t) }))
        .filter((n) => Number.isFinite(n.miles)).sort((a, b) => a.miles - b.miles).slice(0, 3)
    : []
  const nearIds = new Set(near.map((n) => n.t.id))

  return (
    <div className={'fmap' + (compact ? ' fmap--compact' : '')}>
      <div className="fmap-field">
        <svg className="fmap-svg" viewBox="0 0 100 100" preserveAspectRatio="none">
          {Array.from({ length: 11 }).map((_, i) => (
            <line key={'gx' + i} x1={i * 10} y1={0} x2={i * 10} y2={100} className="fmap-grid" />
          ))}
          {Array.from({ length: 11 }).map((_, i) => (
            <line key={'gy' + i} x1={0} y1={i * 10} x2={100} y2={i * 10} className="fmap-grid" />
          ))}
          {ROADS.map((r, i) => <path key={'r' + i} d={pathD(r.pts)} className="fmap-road" />)}
          {focus && near.map((n, i) => {
            const f = pos.get(focus.id)!, p = pos.get(n.t.id)!
            return <line key={'c' + i} x1={f.x} y1={f.y} x2={p.x} y2={p.y} className="fmap-link" />
          })}
        </svg>

        {!compact && <span className="fmap-rd-label" style={{ left: '51%', top: '8%' }}>I-77</span>}
        {!compact && <span className="fmap-rd-label" style={{ left: '12%', top: '70%' }}>I-85</span>}
        {!compact && <span className="fmap-rd-label" style={{ left: '82%', top: '78%' }}>US-74</span>}

        <div className="fmap-hq" style={{ left: HQ.x + '%', top: HQ.y + '%' }}>
          <div className="fmap-hq-diamond" />
          <span className="fmap-hq-label">TPS Yard</span>
        </div>

        {focus && near.map((n, i) => {
          const f = pos.get(focus.id)!, p = pos.get(n.t.id)!
          return (
            <span key={'d' + i} className="fmap-dist" style={{ left: (f.x + p.x) / 2 + '%', top: (f.y + p.y) / 2 + '%' }}>
              {n.miles} mi
            </span>
          )
        })}

        {trucks.map((t) => {
          const meta = STATUS_META[t.status]
          const p = pos.get(t.id)!
          const isFocus = !!focus && t.id === focus.id
          const dim = !!focus && !isFocus && !nearIds.has(t.id)
          return (
            <button
              key={t.id}
              className={'fmap-mk' + (isFocus ? ' is-focus' : '') + (dim ? ' is-dim' : '')}
              style={{ left: p.x + '%', top: p.y + '%', ['--mk' as any]: meta.dot }}
              onMouseEnter={() => setHover(t.id)}
              onMouseLeave={() => setHover(null)}
              onClick={() => onSelect && onSelect(t)}
              title={`${t.unit_number || ''} · ${meta.label}`}
            >
              <span className={'fmap-mk-dot' + (t.moving ? ' is-moving' : '')} />
              {(isFocus || hover === t.id || !compact) && (
                <span className="fmap-mk-tag">{(t.unit_number || '').replace('TPS-', '')}</span>
              )}
              {hover === t.id && (
                <span className="fmap-tip">
                  <b>{t.unit_number}</b> · {meta.label}<br />
                  {t.location_label || '—'}
                  {focus && t.id !== focus.id && (
                    <span className="fmap-tip-d">{haversine(focus, t)} mi from {focus.unit_number}</span>
                  )}
                </span>
              )}
            </button>
          )
        })}
      </div>

      <div className="fmap-legend">
        {(Object.keys(STATUS_META) as (keyof typeof STATUS_META)[]).map((k) => (
          <span key={k} className="fmap-leg"><i style={{ background: STATUS_META[k].dot }} />{STATUS_META[k].label}</span>
        ))}
        <span className="fmap-leg"><i className="leg-diamond" />Shop / yard</span>
      </div>
    </div>
  )
}
