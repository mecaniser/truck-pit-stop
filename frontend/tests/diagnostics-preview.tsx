import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import TruckDiagnostics, { type DiagnosticsResponse } from '../src/features/fleet/TruckDiagnostics'
import '../src/index.css'
import '../src/features/fleet/fleet.css'
if (!import.meta.env.DEV) throw new Error('Development fixture only')
const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } })
const examples: Record<string, DiagnosticsResponse> = {
  codes: { last_checked_at: '2026-10-07T20:00:00Z', coverage: 'complete', explicit_empty: false, codes: [{ code: null, spn: '0012', fmi: '00', description: 'Example communication circuit diagnostic', severity: 'High', network: 'J1939', source_address: null, occurrence_count: 0, first_detected_text: 'Oct 6, 2026, 8:15 AM', last_observed_text: 'Oct 7, 2026, 3:12 PM', timezone_basis: 'unverified' }] },
  empty: { last_checked_at: '2026-10-07T20:00:00Z', coverage: 'complete', explicit_empty: true, codes: [] },
  unknown: { last_checked_at: null, coverage: 'unknown', explicit_empty: null, codes: [] },
}
for (const [id, data] of Object.entries(examples)) client.setQueryData(['fleet-truck-diagnostics', id], data)
export function Preview() {
  const [scenario, setScenario] = React.useState('codes')
  return <QueryClientProvider client={client}><div className="fleet-root" style={{ overflow: 'auto', padding: 24, position: 'fixed' }}><main style={{ maxWidth: 800, width: '100%', margin: '0 auto' }}>
    <p style={{ color: 'var(--muted)', marginBottom: 16 }}>Synthetic diagnostic preview · no fleet connection</p>
    <label>Scenario <select value={scenario} onChange={event => setScenario(event.target.value)} style={{ color: '#111', marginBottom: 16 }}><option value="codes">Reported codes</option><option value="empty">Explicit empty</option><option value="unknown">Unknown</option></select></label>
    <TruckDiagnostics key={scenario} truckId={scenario} />
  </main></div></QueryClientProvider>
}
ReactDOM.createRoot(document.getElementById('root')!).render(<Preview />)
