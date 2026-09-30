import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link2, RefreshCw, Unplug } from 'lucide-react'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { SidekickPanel } from './FleetModals'
import type { BoardTruck } from './types'
import './motive.css'
import { motiveError } from './motiveErrors'

export interface MotiveConnection {
  fleet_customer_id: string
  configured: boolean
  can_connect: boolean
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
  vehicle_id: string | null
  match_candidates: { vehicle_id: string; unit_number: string | null }[]
  mapping_state: string
  telemetry?: { location: { lat: number; lng: number; located_at: string; received_at: string }; speed_mph: number | null; bearing_degrees: number | null; state: 'fresh' | 'delayed' | 'stale'; source: 'motive' } | null
}
interface Company { id: string; company_name: string; fleet_enabled: boolean; is_internal_fleet?: boolean }
const labels: Record<MotiveConnection['status'], string> = {
  not_configured: 'Setup pending', disconnected: 'Not connected', connected: 'Connected',
  reconnect_required: 'Reconnect needed', provider_error: 'Sync interrupted',
}
function time(value: string | null) {
  if (!value) return 'Not synced yet'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Time unavailable' : date.toLocaleString()
}
export function MotiveConnectionCard({ companyId, trucks }: { companyId: string; trucks: BoardTruck[] }) {
  const qc = useQueryClient()
  const [notice, setNotice] = useState('')
  const [confirmDisconnect, setConfirmDisconnect] = useState(false)
  const [selections, setSelections] = useState<Record<string, string>>({})
  const params = { fleet_customer_id: companyId }
  const connection = useQuery<MotiveConnection>({
    queryKey: ['motive-connection', companyId],
    queryFn: async ({ signal }) => (await api.get('/fleet/motive/connection', { params, signal })).data,
    retry: false, refetchInterval: 60000,
  })
  const connected = Boolean(connection.data?.company) && connection.data?.status !== 'disconnected'
  const vehicles = useQuery<{ items: RemoteVehicle[]; synced_at: string | null }>({
    queryKey: ['motive-vehicles', companyId],
    queryFn: async ({ signal }) => (await api.get('/fleet/motive/vehicles', { params, signal })).data,
    enabled: connected, retry: false, refetchInterval: 60000,
  })
  const refresh = async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ['motive-connection', companyId] }),
      qc.invalidateQueries({ queryKey: ['motive-vehicles', companyId] }),
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
      setNotice(data.status === 'connected' ? `Sync finished. ${data.counts.updated} truck readings updated.` : 'Sync needs attention. Check the connection status.')
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
  const eligibleTrucks = trucks.filter((truck) => truck.fleet_customer_id === companyId)
  return <section className="motive-card" aria-label="Motive connection">
    <div className="motive-heading"><div><h3>Motive</h3><p>Connect your fleet’s truck devices.</p></div><span className="motive-status">{connection.isPending ? 'Loading…' : data ? labels[data.status] : 'Unavailable'}</span></div>
    {connection.isError && <div role="alert"><p>{motiveError(connection.error)}</p><button className="dbtn dbtn-ghost" onClick={() => connection.refetch()}>Retry</button></div>}
    {data && <>
      {data.status === 'not_configured' && <p>We’re completing Motive setup. You can connect this company once access is ready.</p>}
      {data.company && <p>Connected company: <strong>{data.company.name || data.company.id}</strong></p>}
      {(data.status === 'reconnect_required' || data.status === 'provider_error') && <p role="alert">{data.status === 'reconnect_required' ? 'Motive authorization needs to be renewed. Reconnect to resume collecting data.' : 'The last sync could not finish. Previously collected readings may be out of date.'}</p>}
      {connected && <p className="motive-muted">Last successful sync: {time(data.last_sync_at)}</p>}
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
      {connected && <div className="motive-trucks"><h4>Truck mappings</h4><p>Supported Motive Vehicle Gateway trucks appear here. Review each match before collecting data.</p>
        {vehicles.isPending && <p role="status">Loading trucks…</p>}
        {vehicles.isError && <p role="alert">Could not load Motive trucks. <button className="dbtn dbtn-ghost" onClick={() => vehicles.refetch()}>Retry trucks</button></p>}
        {vehicles.data?.items.length === 0 && <p>No Motive vehicles discovered yet. Select Sync now to retrieve them.</p>}
        {vehicles.data?.items.map((remote) => {
          const selected = selections[remote.provider_vehicle_id] ?? remote.vehicle_id ?? ''
          const label = remote.number || remote.provider_vehicle_id
          const age = remote.telemetry ? (clock - Date.parse(remote.telemetry.location.located_at)) / 1000 : Infinity
          const reading = age <= 30 * 86400 ? remote.telemetry : null
          const freshness = age <= 300 ? 'fresh' : age <= 900 ? 'delayed' : 'stale'
          return <div className="motive-truck" key={remote.provider_vehicle_id}>
            <strong>Motive truck {label}</strong><span className="motive-muted">VIN: {remote.vin || 'Unavailable'} · Device: {remote.gateway_id || 'Not reported'}</span>
            <label htmlFor={`motive-truck-${remote.provider_vehicle_id}`}>DieselBridge truck</label>
            <div className="motive-mapping"><select id={`motive-truck-${remote.provider_vehicle_id}`} aria-label={`DieselBridge truck for ${label}`} value={selected} disabled={busy} onChange={(event) => setSelections((previous) => ({ ...previous, [remote.provider_vehicle_id]: event.target.value }))}>
              <option value="">Not mapped</option>
              {remote.vehicle_id && !eligibleTrucks.some((truck) => truck.id === remote.vehicle_id) && <option value={remote.vehicle_id} disabled>Previous truck (no longer in fleet)</option>}
              {eligibleTrucks.map((truck) => <option key={truck.id} value={truck.id}>{truck.unit_number || truck.vin || truck.id}{remote.match_candidates.some((candidate) => candidate.vehicle_id === truck.id) ? ' (VIN match)' : ''}</option>)}
            </select><button className="dbtn dbtn-ghost" disabled={busy || selected === (remote.vehicle_id ?? '')} onClick={() => binding.mutate({ remoteId: remote.provider_vehicle_id, vehicleId: selected })}>Save mapping</button></div>
            {remote.vehicle_id && !eligibleTrucks.some((truck) => truck.id === remote.vehicle_id) && <p role="alert">The mapped truck is no longer in this fleet. Remove or update its mapping.</p>}
            {remote.vehicle_id && <p className="motive-muted">{reading
              ? <>Motive location · {freshness} · {time(reading.location.located_at)}<br />{reading.location.lat.toFixed(5)}, {reading.location.lng.toFixed(5)}{reading.speed_mph != null ? ` · ${reading.speed_mph.toFixed(1)} mph` : ''}</>
              : 'No current reading for this mapping yet.'}</p>}
          </div>
        })}
      </div>}
    </>}
    {notice && <p role="status" className="motive-notice">{notice}</p>}
  </section>
}
export default function MotiveIntegrationPanel({ onClose, trucks, initialCompanyId = '' }: { onClose: () => void; trucks: BoardTruck[]; initialCompanyId?: string }) {
  const user = useAuthStore((state) => state.user)
  const allowed = user?.role === 'garage_owner' || user?.role === 'garage_admin'
  const [companyId, setCompanyId] = useState(initialCompanyId)
  const companies = useQuery<Company[]>({ queryKey: ['fleet-companies'], queryFn: async () => (await api.get('/fleet/companies')).data, enabled: allowed })
  const options = companies.data?.filter((company) => (company.fleet_enabled || company.is_internal_fleet)) ?? []
  const selected = options.some((company) => company.id === companyId) ? companyId : options.length === 1 ? options[0].id : ''
  return <SidekickPanel title="Integrations" subtitle="Truck data" icon={<Link2 size={18} />} onClose={onClose} width="max-w-[680px]">
    {!allowed ? <p>Ask your company administrator to manage integrations.</p> : <div className="motive-panel">
      <label htmlFor="motive-company">Fleet company</label>
      <select id="motive-company" value={selected} onChange={(event) => setCompanyId(event.target.value)}>
        <option value="">Choose a company</option>{options.map((company) => <option key={company.id} value={company.id}>{company.company_name}</option>)}
      </select>
      {companies.isPending && <p role="status">Loading companies…</p>}
      {companies.isError && <p role="alert">Could not load companies. <button className="dbtn dbtn-ghost" onClick={() => companies.refetch()}>Retry</button></p>}
      {companies.isSuccess && options.length === 0 && <p>Enable a fleet company before connecting Motive.</p>}
      {selected && <MotiveConnectionCard key={selected} companyId={selected} trucks={trucks} />}
    </div>}
  </SidekickPanel>
}
