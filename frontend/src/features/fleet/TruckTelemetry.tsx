import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { MapPin, RefreshCw } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { useAuthStore } from '../../stores/authStore'
import type { BoardTruck } from './types'
import { readingCaption, readingSummary, retained, useTelemetryClock, type ReadingProvenance } from './telemetry'
import TelemetryCapture from './TelemetryCapture'
import './telemetry.css'

/** Touch, pointer and keyboard access to the provenance of an individual reading. */
function ReadingInfo({ label, reading, children, className = '' }: { label: string; reading: ReadingProvenance; children: ReactNode; className?: string }) {
  const [open, setOpen] = useState(false)
  const [pinned, setPinned] = useState(false)
  const [position, setPosition] = useState({ left: 8, top: 8 })
  const button = useRef<HTMLButtonElement>(null)
  const id = useId()
  const now = useTelemetryClock()
  useEffect(() => {
    if (!open) return
    const positionTip = () => {
      const rect = button.current?.getBoundingClientRect()
      if (rect) setPosition({ left: Math.max(8, Math.min(rect.left, window.innerWidth - 308)), top: Math.max(8, Math.min(rect.bottom + 6, window.innerHeight - 160)) })
    }
    const dismiss = (event: PointerEvent) => { if (!button.current?.contains(event.target as Node)) { setOpen(false); setPinned(false) } }
    positionTip()
    document.addEventListener('pointerdown', dismiss)
    window.addEventListener('resize', positionTip)
    window.addEventListener('scroll', positionTip, true)
    return () => { document.removeEventListener('pointerdown', dismiss); window.removeEventListener('resize', positionTip); window.removeEventListener('scroll', positionTip, true) }
  }, [open])
  return <>
    <button ref={button} type="button" className={`truck-reading ${className}`} aria-label={`${label}: reading information`} aria-expanded={open} aria-describedby={open ? id : undefined}
      onClick={() => { setPinned(!pinned); setOpen(!pinned) }}
      onPointerEnter={(event) => { if (event.pointerType === 'mouse') setOpen(true) }} onPointerLeave={() => { if (!pinned) setOpen(false) }}
      onBlur={() => { setOpen(false); setPinned(false) }} onKeyDown={(event) => { if (event.key === 'Escape') { setOpen(false); setPinned(false); event.stopPropagation() } }}>
      {children}
    </button>
    {open && createPortal(<div id={id} role="tooltip" className="truck-reading-tooltip" style={position}><strong>{label}</strong><div>{readingCaption(reading, now)}</div>{'basis' in reading && reading.basis ? <div>Basis: {reading.basis === 'dashboard_unspecified' ? 'Motive dashboard' : String(reading.basis)}</div> : null}</div>, document.body)}
  </>
}

export function TruckTelemetryLocation({ truck }: { truck: BoardTruck }) {
  const now = useTelemetryClock()
  const location = retained(truck.telemetry?.location, now)
  if (!location) return null
  const label = location.label || (location.lat != null && location.lng != null ? `${location.lat.toFixed(5)}, ${location.lng.toFixed(5)}` : 'Location unavailable')
  return <ReadingInfo label="Last location" reading={location} className="truck-header-location"><MapPin size={15} aria-hidden="true" /><span><strong>{label}</strong><small>{readingSummary(location, now)}</small></span></ReadingInfo>
}

export function TruckTelemetryValue({ truck, field, label, className = '' }: { truck: BoardTruck; field: 'odometer' | 'speed' | 'fuel' | 'engine_hours' | 'fault_count'; label: string; className?: string }) {
  const now = useTelemetryClock()
  const reading = retained(truck.telemetry?.[field], now)
  if (!reading) return null
  const value = `${reading.value.toLocaleString(undefined, { maximumFractionDigits: 1 })}${reading.unit === 'percent' ? '%' : reading.unit === 'count' ? '' : ` ${reading.unit}`}`
  return <ReadingInfo label={label} reading={reading} className={`truck-reading--${field} ${className}`}><span className="truck-reading-label">{label}</span><strong>{value}</strong></ReadingInfo>
}

export function PullMotiveReading({ truck }: { truck: BoardTruck }) {
  const role = useAuthStore((state) => state.user?.role)
  const qc = useQueryClient()
  const [notice, setNotice] = useState('')
  const companyId = truck.board_membership_customer_id
  const pull = useMutation({
    mutationFn: async () => {
      if (!companyId) throw new Error('missing-company')
      const params = { fleet_customer_id: companyId }
      const { data } = await api.get<{ configured: boolean; status: string; company: unknown; next_sync_at: string | null }>('/fleet/motive/connection', { params })
      if (!data.configured || !data.company || !['connected', 'provider_error'].includes(data.status)) {
        return 'Motive connection required. Until access is approved, use Add reading for a manual import.'
      }
      if (data.next_sync_at && Date.parse(data.next_sync_at) > Date.now()) return `Next refresh available at ${new Date(data.next_sync_at).toLocaleTimeString()}.`
      const result = await api.post('/fleet/motive/sync', params)
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['fleet-board'] }), qc.invalidateQueries({ queryKey: ['fleet-truck', truck.id] }),
        qc.invalidateQueries({ queryKey: ['motive-connection', companyId] }), qc.invalidateQueries({ queryKey: ['motive-vehicles', companyId] }),
      ])
      if (result.data.status !== 'connected') return 'Motive sync needs attention. Check the connection in Integrations.'
      return result.data.completed_at ? 'Company sync completed. Available truck readings refreshed.' : 'Company sync started. Remaining trucks will continue automatically.'
    },
    onSuccess: setNotice,
    onError: () => setNotice('Could not refresh Motive. Check your connection and access in Integrations, then retry.'),
  })
  if (!['garage_owner', 'garage_admin'].includes(role || '') || !companyId) return null
  return <div className="truck-motive-pull"><button type="button" className="dbtn dbtn-ghost" disabled={pull.isPending} onClick={() => { setNotice(''); pull.mutate() }}><RefreshCw size={14} />{pull.isPending ? 'Checking Motive…' : 'Pull from Motive'}</button>{notice && <p role="status" className="telemetry-muted">{notice}</p>}</div>
}

export function TruckVitals({ truck }: { truck: BoardTruck }) {
  return <section className="fleet-reference-section"><h3 className="dmap-side-h">Truck vitals</h3><div className="truck-vitals-grid">
    <TruckTelemetryValue truck={truck} field="engine_hours" label="Engine hours" />
    <TruckTelemetryValue truck={truck} field="fault_count" label="Open faults" />
  </div><PullMotiveReading key={`${truck.id}:${truck.board_membership_customer_id}`} truck={truck} /><TelemetryCapture key={truck.id} truck={truck} /></section>
}
