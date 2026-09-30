/** Development-only browser acceptance fixture. All HTTP is handled in memory. */
import React from 'react'
import ReactDOM from 'react-dom/client'
import { AxiosError } from 'axios'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import api from '../src/lib/api'
import { useAuthStore } from '../src/stores/authStore'
import MotiveIntegrationPanel from '../src/features/fleet/MotiveIntegrationPanel'
import type { BoardTruck } from '../src/features/fleet/types'
import '../src/index.css'
import '../src/features/fleet/fleet.css'
if (!import.meta.env.DEV) throw new Error('Fixture preview is development-only')
const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const companyId = '11111111-1111-4111-8111-111111111111'
let status = 'not_configured'
let mapped: string | null = null
let synced = false
let failSync = false
let nextSync: string | null = null
const company = { id: companyId, company_name: 'Example Fleet', fleet_enabled: true }
const truckId = '22222222-2222-4222-8222-222222222222'
const trucks = [{ id: truckId, unit_number: '101', vin: 'EXAMPLEVIN00000001', fleet_customer_id: companyId }] as BoardTruck[]
api.defaults.adapter = async (config) => {
  let data: unknown
  const path = config.url
  const method = config.method
  if (path === '/fleet/companies') data = [company]
  else if (path === '/fleet/motive/connection' && method === 'get') data = {
    fleet_customer_id: companyId, configured: status !== 'not_configured', can_connect: status !== 'not_configured', status,
    company: ['connected', 'provider_error'].includes(status) ? { id: 'fixture-company', name: 'Example Fleet' } : null,
    next_sync_at: nextSync, last_sync_at: synced ? new Date().toISOString() : null, last_sync_error_code: null,
    last_sync_counts: synced ? { discovered: 1, mapped: mapped ? 1 : 0, updated: mapped ? 1 : 0, rejected: 0 } : null,
  }
  else if (path === '/fleet/motive/vehicles') data = { items: [{
    provider_vehicle_id: 'fixture-101', number: '101', vin: 'EXAMPLEVIN00000001', gateway_id: null,
    vehicle_id: mapped, mapping_state: mapped ? 'mapped' : 'unmapped', match_candidates: [{ vehicle_id: truckId, unit_number: '101' }],
    telemetry: mapped && synced ? { location: { lat: 35, lng: -81, located_at: new Date().toISOString(), received_at: new Date().toISOString() }, speed_mph: 0, bearing_degrees: null, state: 'fresh', source: 'motive' } : null,
  }], synced_at: null }
  else if (path === '/fleet/motive/bindings/fixture-101') { mapped = method === 'put' ? JSON.parse(config.data).vehicle_id : null; synced = false; data = {} }
  else if (path === '/fleet/motive/sync') {
    if (failSync) {
      status = 'provider_error'
      throw new AxiosError('Synthetic provider failure', 'ERR_BAD_RESPONSE', config, undefined, { status: 503, statusText: 'Unavailable', data: {}, headers: {}, config })
    }
    status = 'connected'; synced = true; nextSync = new Date(Date.now() + 300000).toISOString(); data = { status, counts: { discovered: 1, mapped: mapped ? 1 : 0, updated: mapped ? 1 : 0, rejected: 0 }, completed_at: new Date().toISOString() }
  } else if (path === '/fleet/motive/connection' && method === 'delete') { status = 'disconnected'; mapped = null; synced = false; nextSync = null; data = {} }
  else throw new Error(`Fixture blocks network: ${method} ${path}`)
  return { data, status: method === 'delete' ? 204 : 200, statusText: 'OK', headers: {}, config }
}
// Keep synthetic identity out of the normal app's persisted session.
useAuthStore.persist.setOptions({ name: 'db036-fixture-auth', storage: { getItem: () => null, setItem: () => {}, removeItem: () => {} } })
useAuthStore.setState({ token: null, refreshToken: null, authProvider: null, user: { id: 'fixture-owner', tenant_id: 'fixture-tenant', role: 'garage_owner' } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']>, isAuthenticated: true })
export default function Preview() {
  const [open, setOpen] = React.useState(true)
  const change = (next: string, fail = false) => { status = next; failSync = fail; nextSync = null; client.invalidateQueries(); setOpen(true) }
  return <div className="fleet-root" style={{ minHeight: '100vh' }}>
    <div style={{ padding: 24, maxWidth: 500 }}><h1>Isolated Motive UI fixture</h1><p>Synthetic data only. No backend or provider requests.</p>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 20 }}>
        <button className="dbtn dbtn-ghost" onClick={() => change('not_configured')}>Preview setup pending</button>
        <button className="dbtn dbtn-ghost" onClick={() => change('connected')}>Preview connected</button>
        <button className="dbtn dbtn-ghost" onClick={() => change('connected', true)}>Preview sync failure</button>
      </div>
    </div>
    {open && <MotiveIntegrationPanel trucks={trucks} onClose={() => setOpen(false)} />}
  </div>
}
ReactDOM.createRoot(document.getElementById('root')!).render(<QueryClientProvider client={client}><MemoryRouter><Preview /></MemoryRouter></QueryClientProvider>)
