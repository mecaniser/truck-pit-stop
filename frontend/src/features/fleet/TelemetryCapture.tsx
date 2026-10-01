import { useId, useRef, useState, type FormEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ChevronDown } from 'lucide-react'
import api from '../../lib/api'
import { useAuthStore } from '../../stores/authStore'
import type { BoardTruck } from './types'
import './telemetry.css'

const numericFields = [
  ['speed_mph', 'Speed (mph)', undefined], ['odometer_miles', 'Dashboard odometer (mi)', undefined],
  ['engine_hours', 'Engine hours', undefined], ['fuel_percent', 'Fuel (%)', 100], ['fault_count', 'Open fault count', undefined],
] as const
export default function TelemetryCapture({ truck }: { truck: BoardTruck }) {
  const role = useAuthStore((s) => s.user?.role)
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const formId = useId()
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const attempt = useRef<{ payload: string; id: string } | null>(null)
  const pending = useRef(false)
  if (role !== 'garage_owner' && role !== 'garage_admin') return null
  const company = truck.board_membership_customer_id
  const vin = truck.vin?.trim().toUpperCase() || ''
  const eligible = Boolean(company && /^[A-HJ-NPR-Z0-9]{17}$/.test(vin))
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending.current || !eligible) return
    const form = event.currentTarget
    const fields = new FormData(form)
    const value = (key: string) => String(fields.get(key) || '').trim()
    if (value('confirm_vin').toUpperCase() !== vin) { setMessage('Enter the exact VIN shown in Motive for this truck.'); return }
    const observed = value('observed_at')
    if (observed && (!/(Z|[+-]\d{2}:\d{2})$/i.test(observed) || !Number.isFinite(Date.parse(observed)) || Date.parse(observed) > Date.now() + 300000)) { setMessage('Use an exact observation timestamp with timezone, or leave it blank.'); return }
    const payload: Record<string, string | number | null> = { fleet_customer_id: company!, vin, observed_at: observed ? new Date(observed).toISOString() : null }
    for (const key of ['source_age_text', 'provider_company_label', 'provider_vehicle_id', 'provider_vehicle_number', 'location_label', 'evidence_note']) payload[key] = value(key) || null
    for (const key of ['lat', 'lng', ...numericFields.map(([key]) => key)]) payload[key] = value(key) === '' ? null : Number(value(key))
    if ((payload.lat == null) !== (payload.lng == null)) { setMessage('Enter both verified coordinates, or leave both blank.'); return }
    if (!payload.location_label && payload.lat == null && !numericFields.some(([key]) => payload[key] != null)) { setMessage('Enter at least one reading actually shown in Motive.'); return }
    const serialized = JSON.stringify(payload)
    if (attempt.current?.payload !== serialized) attempt.current = { payload: serialized, id: crypto.randomUUID() }
    pending.current = true
    setBusy(true); setMessage('')
    try {
      await api.post(`/fleet/trucks/${truck.id}/telemetry-snapshots`, { ...payload, client_request_id: attempt.current!.id })
      attempt.current = null
      form.reset()
      setMessage('Motive dashboard snapshot saved.')
      setOpen(false)
      await Promise.all([queryClient.invalidateQueries({ queryKey: ['fleet-board'] }), queryClient.invalidateQueries({ queryKey: ['fleet-truck', truck.id] })])
    } catch (error) {
      const status = (error as { response?: { status?: number } }).response?.status
      setMessage(status === 403 ? 'Your access to capture this truck has changed. Refresh the fleet.' : status === 404 || status === 409 ? 'The truck identity or fleet membership changed. Refresh and verify the VIN and fleet.' : status === 422 ? 'Check the readings, VIN, fleet and observation timestamp.' : 'Snapshot could not be saved. Retry to safely reuse this capture request.')
    } finally { pending.current = false; setBusy(false) }
  }
  return <section className={`telemetry-capture${open ? ' telemetry-capture--open' : ''}`}>
    <button type="button" className="dbtn" aria-expanded={open} aria-controls={formId} disabled={busy} onClick={() => setOpen(!open)}>Add reading <ChevronDown size={16} style={{ transform: open ? 'rotate(180deg)' : undefined }} /></button>
    {open && <div id={formId}>
      <h3>Manual Motive reading</h3>
      <p>Fleet: <strong>{truck.board_membership_company_name || 'Fleet membership unavailable'}</strong> · VIN: <strong>{vin || 'Missing'}</strong></p>
      {!eligible ? <p role="status">A selected fleet membership and valid truck VIN are required.</p> : <form className="telemetry-form" onSubmit={save}>
        <p className="telemetry-muted">Copy a new reading from Motive. Leave unknown values blank; service mileage stays unchanged.</p>
        <fieldset disabled={busy} style={{ border: 0, padding: 0 }}>
          <div className="telemetry-form-grid">
            <label>VIN verified in Motive<input name="confirm_vin" required maxLength={17} autoComplete="off" /></label>
            <label>Exact observation time (optional)<input name="observed_at" placeholder="2026-10-01T12:00:00-04:00" /></label>
            <label>Source age text (if displayed)<input name="source_age_text" maxLength={120} placeholder="e.g. 41s ago" /></label>
            <label>Motive company label<input name="provider_company_label" maxLength={255} /></label>
            <label>Motive vehicle number<input name="provider_vehicle_number" maxLength={120} /></label>
            <label>Motive vehicle ID (optional)<input name="provider_vehicle_id" maxLength={120} /></label>
            <label>Reported location label<input name="location_label" maxLength={500} /></label>
            {numericFields.map(([key, label, max]) => <label key={key}>{label}<input name={key} type="number" min={0} max={max} step={key === 'fault_count' ? 1 : 'any'} /></label>)}
            <label>Verified truck latitude<input name="lat" type="number" min={-90} max={90} step="any" /></label>
            <label>Verified truck longitude<input name="lng" type="number" min={-180} max={180} step="any" /></label>
          </div>
          <p className="telemetry-muted">Use exact truck coordinates only. A map center or nearby place is not a truck position. Relative age does not establish an exact observation time.</p>
          <label>Evidence note (optional)<textarea name="evidence_note" maxLength={1000} /></label>
          <button className="dbtn" type="submit">{busy ? 'Saving…' : 'Save dashboard snapshot'}</button>
        </fieldset>
      </form>}
    </div>}
    {message && <p role="status">{message}</p>}
  </section>
}
