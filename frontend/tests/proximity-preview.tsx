import React from 'react'
import ReactDOM from 'react-dom/client'
import FleetMap from '../src/features/fleet/FleetMap'
import type { BoardTruck } from '../src/features/fleet/types'
import '../src/index.css'
import '../src/features/fleet/fleet.css'
if (!import.meta.env.DEV) throw new Error('Development fixture only')
const now = Date.now()
const trucks = [
  ['101', 'out_of_service', 35.2271, -80.8431, 1, 'Charlotte, NC'],
  ['204', 'available', 35.2621, -80.8601, 2, 'Charlotte, NC'],
  ['307', 'active', 35.4107, -80.8429, 4, 'Huntersville, NC'],
  ['408', 'shop', 35.5951, -80.8101, 6, 'Mooresville, NC'],
  ['509', 'yard', 35.9557, -80.0053, 10, 'High Point, NC'],
  ['610', 'available', 35.2281, -80.8441, 120, 'Charlotte, NC'],
  ['711', 'parts', null, null, 0, 'Location unavailable'],
].map(([id, status, lat, lng, age, label]) => ({ id, unit_number: id, fleet_company_name: '77 CARGO LLC', status, make: 'Test', model: 'Truck', driver_name: id === '101' ? 'Example driver' : null,
  telemetry: { location: { lat, lng, label, observed_at: new Date(now - Number(age) * 60000).toISOString(), captured_at: new Date(now).toISOString(), source: 'motive_api', freshness: 'fresh', snapshot_id: null, source_age_text: null }, speed: null, fuel: null, odometer: null, engine_hours: null, fault_count: null, motion: 'unknown' },
})) as BoardTruck[]
export function Preview() {
  const [focusId, setFocusId] = React.useState<string | undefined>('101')
  const [details, setDetails] = React.useState<BoardTruck>()
  return <div className="fleet-root" style={{ overflow: 'auto', padding: '24px', position: 'fixed' }}>
    <p style={{ color: '#93a3b2', fontSize: 12, marginBottom: 16 }}>Synthetic preview · no fleet connection</p>
    {details ? <div><h1>Truck {details.unit_number}</h1><button onClick={() => setDetails(undefined)}>Back to map</button></div> : <FleetMap trucks={trucks} focusId={focusId} onFocusChange={setFocusId} onSelect={setDetails} />}
  </div>
}
ReactDOM.createRoot(document.getElementById('root')!).render(<Preview />)
