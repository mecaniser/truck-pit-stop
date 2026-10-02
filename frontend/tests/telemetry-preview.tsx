/** Development-only presentation fixture; never connects to a backend/provider. */
import React, { useState, type ComponentProps } from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import api from '../src/lib/api'
import { useAuthStore } from '../src/stores/authStore'
import FleetBoard from '../src/features/fleet/FleetBoard'
import TruckDetail from '../src/features/fleet/TruckDetail'
import type { BoardTruck } from '../src/features/fleet/types'
import type { ReadingProvenance } from '../src/features/fleet/telemetry'
import '../src/index.css'
import '../src/features/fleet/fleet.css'
if (!import.meta.env.DEV) throw new Error('Development fixture only')
api.defaults.adapter = async (config) => {
  let data: unknown = {}
  if (config.method === 'get' && config.url === '/fleet/motive/connection') data = { configured: false, status: 'not_configured', company: null }
  else if (config.method === 'get' && config.url === '/fleet/trucks/synthetic-truck') data = { truck, open_work_orders: [], bill_labor_at_customer_rate: false, lifetime_spend: 0, incidents_count: 0, crew: [], history: [], parts: [], incidents: [], nearest: [] }
  else if (config.method === 'get' && ['/fleet/trucks/synthetic-truck/incidents', '/fleet/inspections'].includes(config.url || '')) data = []
  else if (config.method !== 'post' || config.url !== '/fleet/trucks/synthetic-truck/telemetry-snapshots') throw new Error(`Fixture blocks network: ${config.url}`)
  return { data, status: 201, statusText: 'Created', headers: {}, config }
}
useAuthStore.persist.setOptions({ name: 'telemetry-fixture-auth', storage: { getItem: () => null, setItem: () => {}, removeItem: () => {} } })
useAuthStore.setState({ token: null, refreshToken: null, authProvider: null, user: { id: 'fixture-owner', role: 'garage_owner' } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']>, isAuthenticated: true })
const source: ReadingProvenance = { source: 'motive_dashboard_manual', observed_at: null, captured_at: new Date(Date.now() - 120000).toISOString(), freshness: 'unknown', snapshot_id: 'fixture', source_age_text: '12s ago' }
const truck = {
  id: 'synthetic-truck', unit_number: '101', vin: '1TEST234567890123', year: 2020, make: 'VOLVO', model: 'VNR', body_type: 'Truck-Tractor',
  board_membership_customer_id: 'synthetic-company', board_membership_company_name: 'Example Fleet', owner_company_name: 'Example Fleet',
  status: 'active', odometer: 120000, pm_remaining: 20433, next_pm_miles: 145000, driver_name: 'Example Driver', open_work_order_count: 0,
  telemetry: {
    location: { ...source, label: 'Charleston, WV', lat: null, lng: null },
    speed: { ...source, value: 65, unit: 'mph', basis: null }, odometer: { ...source, value: 124567, unit: 'mi', basis: 'dashboard_unspecified' },
    engine_hours: { ...source, value: 4567, unit: 'h', basis: 'dashboard_unspecified' }, fuel: { ...source, value: 38, unit: 'percent', basis: null },
    fault_count: null, motion: 'unknown',
  },
} as BoardTruck
export default function Preview() {
  const [filter, setFilter] = useState<ComponentProps<typeof FleetBoard>['filter']>('all')
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<ComponentProps<typeof FleetBoard>['sort']>('attention')
  const [detail, setDetail] = useState(false)
  return <main className="fleet-root" style={{ overflow: 'auto', padding: 20 }}>
    <p style={{ marginBottom: 16 }}>Synthetic UI preview · no live collection</p>
    {detail ? <><button className="dbtn" onClick={() => setDetail(false)}>Back to fleet</button><TruckDetail truckId={truck.id} trucks={[truck]} onOpen={() => {}} /></> :
      <FleetBoard data={{ trucks: [truck], stats: { total: 1, active: 1, shop: 0, pm: 0, parts: 0, open_wo: 0, incidents_total: 0 } }} filter={filter} setFilter={setFilter} query={query} setQuery={setQuery} sort={sort} setSort={setSort} onOpen={() => setDetail(true)} onOpenRepairOrder={() => {}} />}
  </main>
}
ReactDOM.createRoot(document.getElementById('root')!).render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><Preview /></MemoryRouter></QueryClientProvider>)
