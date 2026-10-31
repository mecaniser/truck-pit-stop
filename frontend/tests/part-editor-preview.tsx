/** Development-only QA fixture: actual editor/CSS, all API requests stay in memory. */
import React, { useState } from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import api from '../src/lib/api'
import { useAuthStore } from '../src/stores/authStore'
import PartsInventoryWorkspace, { type PartRecord } from '../src/features/inventory/PartsInventoryWorkspace'
import '../src/index.css'
if (!import.meta.env.DEV) throw new Error('Development fixture only')
useAuthStore.persist.setOptions({ name: 'part-editor-fixture-auth', storage: { getItem: () => null, setItem: () => {}, removeItem: () => {} } })
useAuthStore.setState({ token: null, refreshToken: null, authProvider: null, user: { id: 'fixture-owner', role: 'garage_owner', tenant_id: 'fixture-shop', tenant_name: 'Synthetic Shop' } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']>, isAuthenticated: true })
let record = { id: 'fixture-part', sku: 'QA-FITTING', name: 'Fitting', category: 'Air systems', description: 'Synthetic editor QA fixture', location: 'A-12', unit_type: 'each', cost: '10.00', core_charge: '2.00', selling_price: '15.00', supplier_name: '', supplier_contact: '', on_order_quantity: 5, pricing_version: 1, image_url: null as string | null }
let slow = false
let failNext = false
let announce: (message: string) => void = () => {}
const part = (): PartRecord => ({ ...record, available_packages: 3, needed_for_open_repairs: 0, reorder_level: 5, incoming_packages: 0, recommended_order_packages: 2, average_unit_cost: record.cost, is_archived: false, is_placeholder: false, preferred_source: null, supplier_sources: [], repair_sources: [], incoming_sources: [] })
const page = (items: unknown[]) => ({ items, total: items.length, skip: 0, limit: 50, has_more: false })
api.defaults.adapter = async config => {
  let data: unknown
  const url = config.url || ''
  if (config.method === 'put' && url === '/inventory/fixture-part') {
    const patch = JSON.parse(config.data as string)
    announce('Saving synthetic record…')
    if (slow) await new Promise(resolve => setTimeout(resolve, 2500))
    if (failNext) { failNext = false; throw new Error('Synthetic save failure. Try again.') }
    record = { ...record, ...patch, pricing_version: record.pricing_version + 1 }
    data = { ...record }
    announce(`Saved: ${JSON.stringify(patch)}`)
  } else if (config.method === 'get' && url === '/auth/tenant-branding') data = { name: 'Synthetic Shop', logo_url: null }
  else if (config.method === 'get' && url === '/parts-operations/parts') data = page([part()])
  else if (config.method === 'get' && url === '/parts-operations/parts/fixture-part') data = { ...part(), recent_receipts: [], recent_movements: [] }
  else if (config.method === 'get' && url === '/inventory/fixture-part') data = { ...record }
  else if (config.method === 'get' && url.endsWith('/lifecycle-summary')) data = { inventory_id: record.id, as_of: new Date().toISOString(), repairs: { units_used: '0', repair_order_count: 0, last_used_at: null }, purchasing: { units_received: 0, receipt_count: 0, units_returned_to_vendor: 0, open_core_obligations: 0 }, sales: { units_sold: 0, units_returned: 0, net_units: 0, gross_item_revenue: '0', discounts: '0', refunds: '0', net_item_revenue: '0', last_sold_at: null }, activity: { event_count: 0, last_event_at: null } }
  else if (config.method === 'get' && url === '/parts-operations/activity-events') data = { items: [], next_cursor: null }
  else if (config.method === 'get' && url.endsWith('/pricing-policy')) data = { policy: { inventory_id: record.id, pricing_version: record.pricing_version, fixed_sales_price: false, pricing_cost_floor: null, minimum_sale_price: null } }
  else throw new Error(`Fixture blocks network: ${config.method} ${url}`)
  return { data, status: 200, statusText: 'OK', headers: {}, config }
}
export default function Preview() {
  const [message, setMessage] = useState('No synthetic writes yet.')
  announce = setMessage
  return <div className="db-presentation-new"><main className="db-staff-content" style={{ background: 'var(--surface-canvas)', color: 'var(--text-primary)', fontFamily: 'system-ui', fontSize: 16, height: '100dvh', display: 'flex', flexDirection: 'column', padding: 12, gap: 8 }}>
    <div style={{ flexShrink: 0, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
      <strong>Synthetic part editor QA · no backend</strong>
      <label><input type="checkbox" onChange={event => { slow = event.target.checked }} /> Slow save</label>
      <button onClick={() => { failNext = true; setMessage('Next synthetic save will fail.') }}>Fail next save</button>
      <button onClick={() => { record = { ...record, name: 'Fresh fitting', cost: '20.00', pricing_version: record.pricing_version + 1 }; setMessage('Synthetic server record changed. Reopen editor to fetch it.') }}>Change saved record</button>
      <output aria-label="Fixture writes" style={{ width: '100%', overflowWrap: 'anywhere' }}>{message}</output>
    </div>
    <PartsInventoryWorkspace summary={{ needs_reorder_count: 1, low_stock_count: 1, open_purchase_order_count: 0, total_stock_value: '36.00' }} />
  </main></div>
}
const root = ReactDOM.createRoot(document.getElementById('root')!)
if (import.meta.hot) import.meta.hot.dispose(() => root.unmount())
root.render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><MemoryRouter initialEntries={['/dashboard/garage/inventory?selected=fixture-part']}><Preview /></MemoryRouter></QueryClientProvider>)
