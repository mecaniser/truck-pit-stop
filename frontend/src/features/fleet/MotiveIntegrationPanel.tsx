import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link2, RefreshCw, Unplug } from 'lucide-react'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { SidekickPanel } from './FleetModals'
import type { BoardTruck } from './types'
import './motive.css'
import { MotiveGrants, MotiveWebhook } from './MotiveManagement'
import { useMotiveCompanies } from './motiveQueries'
import { motiveError } from './motiveErrors'

export interface MotiveConnection {
  fleet_customer_id: string
  configured: boolean
  can_connect: boolean
  can_manage_grants?: boolean
  webhook_status?: string
  last_webhook_at?: string | null
  last_reconciled_at?: string | null
  status: 'not_configured' | 'disconnected' | 'connected' | 'reconnect_required' | 'provider_error'
  company: { id: string; name: string | null } | null
  last_sync_at: string | null
  next_sync_at?: string | null
  last_sync_error_code: string | null
  last_sync_counts: { discovered: number; mapped: number; updated: number; rejected: number } | null
}
interface RemoteVehicle {
  provider_vehicle_id: string
  number: string | null
  vin: string | null
  gateway_id: string | null
  gateway_identifier?: string | null
  gateway_model?: string | null
  metrics?: { odometer_miles: number | null; virtual_odometer_miles: number | null; engine_hours: number | null; virtual_engine_hours: number | null; observed_at: string; received_at: string; source: string } | null
  faults?: { id: string; code: string | null; code_label: string | null; description: string | null; status: string; first_observed_at: string | null; last_observed_at: string | null; fmi: string | null }[]
  faults_synced_at?: string | null
  vehicle_id: string | null
  match_candidates: { vehicle_id: string; unit_number: string | null }[]
  mapping_state: string
  telemetry?: { location: { lat: number; lng: number; located_at: string; received_at: string }; speed_mph: number | null; bearing_degrees: number | null; state: 'fresh' | 'delayed' | 'stale'; source: 'motive' } | null
}
interface TruckChoice { id: string; unit_number: string | null; vin: string | null }
const labels: Record<MotiveConnection['status'], string> = {
  not_configured: 'Setup pending', disconnected: 'Not connected', connected: 'Connected',
  reconnect_required: 'Reconnect needed', provider_error: 'Sync interrupted',
}
function time(value: string | null) {
  if (!value) return 'Not synced yet'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Time unavailable' : date.toLocaleString()
}
export function MotiveConnectionCard({ companyId, trucks = [], canManageGrants = false }: { companyId: string; trucks?: BoardTruck[]; canManageGrants?: boolean }) {
  const actor = useAuthStore((s) => s.user)
  const scope = [actor?.id, actor?.tenant_id]
  const qc = useQueryClient()
  const [notice, setNotice] = useState('')
  const [confirmDisconnect, setConfirmDisconnect] = useState(false)
  const [selections, setSelections] = useState<Record<string, string>>({})
  const params = { fleet_customer_id: companyId }
  const connection = useQuery<MotiveConnection>({
    queryKey: ['motive-connection', companyId, ...scope],
    queryFn: async ({ signal }) => (await api.get('/fleet/motive/connection', { params, signal })).data,
    retry: false, refetchInterval: 60000,
  })
  const connected = Boolean(connection.data?.company) && connection.data?.status !== 'disconnected'
  const vehicles = useQuery<{ items: RemoteVehicle[]; synced_at: string | null }>({
    queryKey: ['motive-vehicles', companyId, ...scope],
    queryFn: async ({ signal }) => (await api.get('/fleet/motive/vehicles', { params, signal })).data,
    enabled: connected, retry: false, refetchInterval: 60000,
  })
  const scopedTrucks = useQuery<{ items: TruckChoice[] }>({
    queryKey: ['motive-trucks', companyId, ...scope],
    queryFn: async ({ signal }) => (await api.get('/fleet/motive/trucks', { params, signal })).data,
    enabled: connected, retry: false,
  })
  const refresh = async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ['motive-connection', companyId] }),
      qc.invalidateQueries({ queryKey: ['motive-vehicles', companyId] }),
      qc.invalidateQueries({ queryKey: ['motive-trucks', companyId] }),
    ])
  }
  const connect = useMutation({
    mutationFn: async () => {
      const { data } = await api.post('/fleet/motive/connect', params)
      const url = new URL(data.authorization_url)
      if (url.origin !== 'https://gomotive.com' || url.pathname !== '/oauth/authorize' || url.username || url.password) {
        throw new Error('Unexpected authorization destination')
      }
      window.location.assign(url.href)
    },
    onError: (error) => setNotice(motiveError(error)),
  })
  const sync = useMutation({
    mutationFn: async () => (await api.post('/fleet/motive/sync', params)).data,
    onSuccess: async (data) => {
      setNotice(data.status === 'connected' ? data.completed_at ? `Sync finished. ${data.counts.updated} truck readings updated.` : 'Sync in progress. Remaining trucks continue automatically.' : 'Sync needs attention. Check the connection status.')
      await refresh()
    },
    onError: async (error) => { setNotice(motiveError(error)); await refresh() },
  })
  const disconnect = useMutation({
    mutationFn: () => api.delete('/fleet/motive/connection', { params }),
    onSuccess: async () => {
      setConfirmDisconnect(false)
      setSelections({})
      qc.removeQueries({ queryKey: ['motive-vehicles', companyId] })
      setNotice('Motive disconnected. New data collection has stopped.')
      await refresh()
    },
    onError: (error) => setNotice(motiveError(error)),
  })
  const binding = useMutation({
    mutationFn: ({ remoteId, vehicleId }: { remoteId: string; vehicleId: string }) => vehicleId
      ? api.put(`/fleet/motive/bindings/${encodeURIComponent(remoteId)}`, { ...params, vehicle_id: vehicleId })
      : api.delete(`/fleet/motive/bindings/${encodeURIComponent(remoteId)}`, { params }),
    onSuccess: async () => { setNotice('Truck mapping saved. New readings will arrive on the next sync.'); setSelections({}); await refresh() },
    onError: async (error) => { setNotice(motiveError(error)); await refresh() },
  })
  const busy = connect.isPending || sync.isPending || disconnect.isPending || binding.isPending
  const data = connection.data
  const catchingUp = data?.last_sync_error_code === 'reconciliation_incomplete'
  const [clock, setClock] = useState(Date.now)
  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 30000)
    return () => window.clearInterval(timer)
  }, [])
  const availableAt = data?.next_sync_at ? Date.parse(data.next_sync_at) : 0
  const coolingDown = Number.isFinite(availableAt) && availableAt > clock
  useEffect(() => {
    if (!availableAt || availableAt <= Date.now()) { setClock(Date.now()); return }
    const timer = window.setTimeout(() => setClock(Date.now()), Math.min(availableAt - Date.now() + 50, 2_147_483_647))
    return () => window.clearTimeout(timer)
  }, [availableAt])
  // Staff prop remains accepted for compatibility; mapping choices always come
  // from the exact-company endpoint, including in the customer portal.
  void trucks
  const eligibleTrucks = scopedTrucks.isError ? [] : scopedTrucks.data?.items ?? []
  return <section className="motive-card" aria-label="Motive connection">
    <div className="motive-heading"><div><h3>Motive</h3><p>Connect your fleet’s truck devices.</p></div><span className="motive-status">{connection.isPending ? 'Loading…' : data ? catchingUp ? 'Sync in progress' : labels[data.status] : 'Unavailable'}</span></div>
    {connection.isError && <div role="alert"><p>{motiveError(connection.error)}</p><button className="dbtn dbtn-ghost" onClick={() => connection.refetch()}>Retry</button></div>}
    {data && !connection.isError && <>
      {data.status === 'not_configured' && <p>We’re completing Motive setup. You can connect this company once access is ready.</p>}
      {data.company && <p>Connected company: <strong>{data.company.name || data.company.id}</strong></p>}
      {!catchingUp && (data.status === 'reconnect_required' || data.status === 'provider_error') && <p role="alert">{data.status === 'reconnect_required' ? 'Motive authorization needs to be renewed. Reconnect to resume collecting data.' : 'The last sync could not finish. Previously collected readings may be out of date.'}</p>}
      {catchingUp && <p className="motive-muted">Collecting the remaining truck data. Progress is saved and collection continues automatically.</p>}
      {connected && <p className="motive-muted">Last successful sync: {time(data.last_sync_at)}</p>}
      {data.last_reconciled_at && <p className="motive-muted">Last complete reconciliation: {time(data.last_reconciled_at)}</p>}
      <div className="motive-actions">
        {(data.status !== 'connected' && data.status !== 'provider_error') && <button className="dbtn dbtn-yellow" disabled={!data.can_connect || busy} onClick={() => { setNotice(''); connect.mutate() }}><Link2 size={16} />{data.status === 'reconnect_required' ? 'Reconnect Motive' : 'Connect Motive'}</button>}
        {connected && <>
          <button className="dbtn dbtn-ghost" disabled={busy || coolingDown || !data.configured || data.status === 'reconnect_required'} onClick={() => { setNotice(''); sync.mutate() }}><RefreshCw size={16} />{sync.isPending ? 'Syncing…' : 'Sync now'}</button>
          <button className="dbtn dbtn-ghost" disabled={busy} onClick={() => setConfirmDisconnect(true)}><Unplug size={16} />Disconnect</button>
        </>}
      </div>
      {connected && coolingDown && <p className="motive-muted">Next sync available: {time(data.next_sync_at ?? null)}</p>}
      {confirmDisconnect && <div className="motive-confirm" role="group" aria-label="Confirm disconnect">
        <p>Disconnect Motive for this company? New data collection will stop. Saved readings follow the data retention policy.</p>
        <div className="motive-actions"><button className="dbtn dbtn-ghost" disabled={busy} onClick={() => setConfirmDisconnect(false)}>Keep connected</button><button className="dbtn dbtn-yellow" disabled={busy} onClick={() => disconnect.mutate()}>Confirm disconnect</button></div>
      </div>}
      {data.last_sync_counts && <p className="motive-muted">{data.last_sync_counts.discovered} Motive vehicles · {data.last_sync_counts.mapped} mapped · {data.last_sync_counts.updated} readings updated{data.last_sync_counts.rejected > 0 ? ` · ${data.last_sync_counts.rejected} readings unavailable` : ''}</p>}
      {connected && <div className="motive-trucks"><h4>Truck mappings</h4><p>Review the Motive vehicles and their installed devices, then confirm each truck match.</p>
        {scopedTrucks.isError && <p role="alert">Could not load this company’s trucks. <button className="dbtn dbtn-ghost" onClick={() => scopedTrucks.refetch()}>Retry mapping options</button></p>}
        {vehicles.isPending && <p role="status">Loading trucks…</p>}
        {vehicles.isError && <p role="alert">Could not load Motive trucks. <button className="dbtn dbtn-ghost" onClick={() => vehicles.refetch()}>Retry trucks</button></p>}
        {vehicles.data?.items.length === 0 && <p>No Motive vehicles discovered yet. Select Sync now to retrieve them.</p>}
        {!vehicles.isError && vehicles.data?.items.map((remote) => {
          const selected = selections[remote.provider_vehicle_id] ?? remote.vehicle_id ?? ''
          const label = remote.number || remote.provider_vehicle_id
          const age = remote.telemetry ? (clock - Date.parse(remote.telemetry.location.located_at)) / 1000 : Infinity
          const reading = age <= 30 * 86400 ? remote.telemetry : null
          const freshness = age <= 300 ? 'fresh' : age <= 900 ? 'delayed' : 'stale'
          return <div className="motive-truck" key={remote.provider_vehicle_id}>
            <strong>Motive truck {label}</strong><span className="motive-muted">VIN: {remote.vin || 'Unavailable'} · Device: {remote.gateway_identifier || remote.gateway_id || 'Not reported'}{remote.gateway_model ? ` · ${remote.gateway_model}` : ''}</span>
            <label htmlFor={`motive-truck-${remote.provider_vehicle_id}`}>DieselBridge truck</label>
            <div className="motive-mapping"><select id={`motive-truck-${remote.provider_vehicle_id}`} aria-label={`DieselBridge truck for ${label}`} value={selected} disabled={busy || scopedTrucks.isError || scopedTrucks.isPending} onChange={(event) => setSelections((previous) => ({ ...previous, [remote.provider_vehicle_id]: event.target.value }))}>
              <option value="">Not mapped</option>
              {remote.vehicle_id && !eligibleTrucks.some((truck) => truck.id === remote.vehicle_id) && <option value={remote.vehicle_id} disabled>Previous truck (no longer in fleet)</option>}
              {eligibleTrucks.map((truck) => <option key={truck.id} value={truck.id}>{truck.unit_number || truck.vin || truck.id}{remote.match_candidates.some((candidate) => candidate.vehicle_id === truck.id) ? ' (VIN match)' : ''}</option>)}
            </select><button className="dbtn dbtn-ghost" disabled={busy || scopedTrucks.isError || scopedTrucks.isPending || selected === (remote.vehicle_id ?? '')} onClick={() => binding.mutate({ remoteId: remote.provider_vehicle_id, vehicleId: selected })}>Save mapping</button></div>
            {remote.vehicle_id && !eligibleTrucks.some((truck) => truck.id === remote.vehicle_id) && <p role="alert">The mapped truck is no longer in this fleet. Remove or update its mapping.</p>}
            {remote.vehicle_id && <p className="motive-muted">{reading
              ? <>Motive location · {freshness} · {time(reading.location.located_at)}<br />{reading.location.lat.toFixed(5)}, {reading.location.lng.toFixed(5)}{reading.speed_mph != null ? ` · ${reading.speed_mph.toFixed(1)} mph` : ''}</>
              : 'No current reading for this mapping yet.'}</p>}
            {remote.vehicle_id && remote.mapping_state !== 'membership_ended' && <MotiveReadings remote={remote} clock={clock} />}
          </div>
        })}
      </div>}
      {connected && !connection.isError && <MotiveWebhook key={`webhook:${companyId}`} companyId={companyId} />}
      {(canManageGrants || data.can_manage_grants) && !connection.isError && <MotiveGrants key={`grants:${companyId}`} companyId={companyId} />}
    </>}
    {notice && <p role="status" className="motive-notice">{notice}</p>}
  </section>
}
function MotiveReadings({ remote, clock }: { remote: RemoteVehicle; clock: number }) {
  const metrics = remote.metrics && clock - Date.parse(remote.metrics.observed_at) <= 30 * 86400000 ? remote.metrics : null
  const age = metrics ? (clock - Date.parse(metrics.observed_at)) / 1000 : Infinity
  const format = (value: number | null | undefined, unit: string) => value == null ? 'Not reported' : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} ${unit}`
  return <div className="motive-readings">
    <h4>Maintenance readings</h4>
    {metrics ? <><dl className="motive-metrics">
      <div><dt>Calibrated odometer</dt><dd>{format(metrics.odometer_miles, 'mi')}</dd></div>
      <div><dt>Virtual odometer</dt><dd>{format(metrics.virtual_odometer_miles, 'mi')}</dd></div>
      <div><dt>Calibrated engine hours</dt><dd>{format(metrics.engine_hours, 'h')}</dd></div>
      <div><dt>Virtual engine hours</dt><dd>{format(metrics.virtual_engine_hours, 'h')}</dd></div>
    </dl><p className="motive-muted">Motive · {age <= 300 ? 'fresh' : age <= 900 ? 'delayed' : 'stale'} · {time(metrics.observed_at)}</p></> : <p className="motive-muted">No current maintenance reading.</p>}
    <h4>Fault codes</h4>
    {!remote.faults_synced_at ? <p className="motive-muted">Fault codes have not been checked yet.</p> : <>
      <p className="motive-muted">Motive · Last checked {time(remote.faults_synced_at)}</p>
      {!remote.faults?.length && <p>No fault codes reported at the last check.</p>}
      <ul className="motive-faults">{remote.faults?.map((fault) => <li key={fault.id}><strong>{fault.code_label || fault.code || 'Fault code'}</strong> · {fault.status}<p>{fault.description || 'Description unavailable'}</p>{fault.last_observed_at && <p className="motive-muted">Last observed {time(fault.last_observed_at)}</p>}</li>)}</ul>
    </>}
  </div>
}

export function MotiveIntegrationWorkspace({ initialCompanyId = '' }: { initialCompanyId?: string }) {
  const user = useAuthStore((state) => state.user)
  const allowed = ['garage_owner', 'garage_admin', 'customer'].includes(user?.role ?? '')
  const [companyId, setCompanyId] = useState(initialCompanyId)
  const companies = useMotiveCompanies()
  const options = !companies.isError ? companies.data?.items?.filter((company) => company.fleet_enabled || company.is_internal_fleet) ?? [] : []
  const selected = options.some((company) => company.id === companyId) ? companyId : options.length === 1 ? options[0].id : ''
  return !allowed ? <p>Ask your company administrator to manage integrations.</p> : <div className="motive-panel">
    <label htmlFor="motive-company">Fleet company</label>
    <select id="motive-company" value={selected} onChange={(event) => setCompanyId(event.target.value)}>
      <option value="">Choose a company</option>{options.map((company) => <option key={company.id} value={company.id}>{company.company_name}</option>)}
    </select>
    {companies.isPending && <p role="status">Loading companies…</p>}
    {companies.isError && <p role="alert">Could not load your authorized companies. <button className="dbtn dbtn-ghost" onClick={() => companies.refetch()}>Retry</button></p>}
    {companies.isSuccess && options.length === 0 && <p>{user?.role === 'customer' ? 'Ask your shop administrator to grant Motive access for your fleet company.' : 'Enable a fleet company before connecting Motive.'}</p>}
    {selected && <MotiveConnectionCard key={`${user?.id}:${user?.tenant_id}:${selected}`} companyId={selected} canManageGrants={Boolean(options.find((c) => c.id === selected)?.can_manage_grants)} />}
  </div>
}

export default function MotiveIntegrationPanel({ onClose, initialCompanyId = '' }: { onClose: () => void; trucks: BoardTruck[]; initialCompanyId?: string }) {
  return <SidekickPanel title="Integrations" subtitle="Truck data" icon={<Link2 size={18} />} onClose={onClose} width="max-w-[680px]"><MotiveIntegrationWorkspace initialCompanyId={initialCompanyId} /></SidekickPanel>
}
