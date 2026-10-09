/** Synthetic real-component fixture. Its adapter blocks every live request. */
import React, { useState, type ComponentProps } from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import api from '../src/lib/api'
import { useAuthStore } from '../src/stores/authStore'
import FleetBoard from '../src/features/fleet/FleetBoard'
import TruckDetail from '../src/features/fleet/TruckDetail'
import type { BoardTruck } from '../src/features/fleet/types'
import type { DriverRecordDetail } from '../src/features/fleet/driverRecordTypes'
import { driverRecord, driverResponse, driverTruck } from '../src/features/fleet/__tests__/driverRecordFixture'
import '../src/index.css'
import '../src/features/fleet/fleet.css'
if (!import.meta.env.DEV) throw new Error('Development fixture only')
const sourceRecord: DriverRecordDetail = { ...driverRecord, safety: { ...driverRecord.safety, history: [] }, fuel: { ...driverRecord.fuel, metrics: [] } }
let scenario = 'source'
function recordForScenario(): DriverRecordDetail | null {
  if (scenario === 'unknown') return null
  if (scenario === 'stale') return { ...sourceRecord, stale: true }
  if (scenario === 'zero') return { ...driverRecord, safety_score: 0, safety_band: 'unknown', safety_band_label: null, safety: { ...driverRecord.safety, score: 0, band: 'unknown', band_label: null }, fuel: { ...driverRecord.fuel, utilization_percent: 0 }, coaching: { ...driverRecord.coaching, open_count: 0 } }
  return sourceRecord
}
const previewTruck = (): BoardTruck => ({ ...driverTruck, driver_record: recordForScenario() })
api.defaults.adapter = async config => {
  if (config.method !== 'get') throw new Error(`Fixture blocks mutation: ${config.url}`)
  let data: unknown
  if (config.url === '/fleet/trucks/synthetic-truck/driver-record') {
    if (scenario === 'error') throw new Error('Synthetic read failure')
    data = { ...driverResponse, availability: scenario === 'unknown' ? 'unknown' : 'available', record: recordForScenario() }
  } else if (config.url === '/fleet/trucks/synthetic-truck') data = { truck: previewTruck(), open_work_orders: [], bill_labor_at_customer_rate: false, lifetime_spend: 0, incidents_count: 0, crew: [], history: [], parts: [], incidents: [], nearest: [] }
  else if (config.url === '/fleet/motive/connection') data = { configured: false, status: 'not_configured', company: null }
  else if (['/fleet/trucks/synthetic-truck/incidents', '/fleet/inspections'].includes(config.url || '')) data = []
  else throw new Error(`Fixture blocks network: ${config.url}`)
  return { data, status: 200, statusText: 'OK', headers: {}, config }
}
useAuthStore.persist.setOptions({ name: 'driver-record-fixture-auth', storage: { getItem: () => null, setItem: () => {}, removeItem: () => {} } })
useAuthStore.setState({ token: null, refreshToken: null, authProvider: null, user: { id: 'fixture-owner', role: 'garage_owner' } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']>, isAuthenticated: true })
const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
export default function Preview() {
  const [filter, setFilter] = useState<ComponentProps<typeof FleetBoard>['filter']>('all')
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<ComponentProps<typeof FleetBoard>['sort']>('attention')
  const [detail, setDetail] = useState(false)
  const [selected, setSelected] = useState(scenario)
  const truck = previewTruck()
  return <main className="fleet-root" style={{ overflow: 'auto', padding: 20 }}>
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 16, marginBottom: 16 }}><p style={{ color: 'var(--muted)' }}>Synthetic driver records · no fleet connection</p><label>Scenario <select value={selected} onChange={event => { scenario = event.target.value; client.clear(); setSelected(scenario) }} style={{ background: '#263442', padding: 8, borderRadius: 6 }}><option value="source">Captured detail</option><option value="unknown">Unknown</option><option value="stale">Stale</option><option value="zero">Zero / unrated</option><option value="error">Read failure</option></select></label></div>
    {detail ? <><button className="dbtn" onClick={() => setDetail(false)}>Back to fleet</button><TruckDetail key={selected} truckId={truck.id} trucks={[truck]} onOpen={() => {}} /></> : <FleetBoard key={selected} data={{ trucks: [truck], stats: { total: 1, active: 1, shop: 0, pm: 0, parts: 0, open_wo: 0, incidents_total: 0 } }} filter={filter} setFilter={setFilter} query={query} setQuery={setQuery} sort={sort} setSort={setSort} onOpen={() => setDetail(true)} onOpenRepairOrder={() => {}} />}
  </main>
}
ReactDOM.createRoot(document.getElementById('root')!).render(<QueryClientProvider client={client}><MemoryRouter><Preview /></MemoryRouter></QueryClientProvider>)
