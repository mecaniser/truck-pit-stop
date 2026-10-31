/** Development-only synthetic browser acceptance; no real network writes. */
import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import api from '../src/lib/api'
import TruckDiagnostics from '../src/features/fleet/TruckDiagnostics'
import type { FleetTelemetry } from '../src/features/fleet/telemetry'
import '../src/index.css'
import '../src/features/fleet/fleet.css'
if (!import.meta.env.DEV) throw new Error('Development fixture only')
const params = new URLSearchParams(location.search)
api.defaults.adapter = async (config) => {
  if (params.has('error')) throw new Error('Synthetic diagnostics error')
  return {config,status:200,statusText:'OK',headers:{},data:{last_checked_at:new Date().toISOString(),coverage:'complete',explicit_empty:false,codes:[{code:null,spn:'639',fmi:'2',description:'Synthetic network diagnostic',severity:'High',network:'J1939',source_address:null,occurrence_count:124,first_detected_text:'Oct 12, 2026, 9:04 AM',last_observed_text:'Oct 30, 2026, 7:59 PM',timezone_basis:'unverified'}]}}
}
const reading = {value:692224.14,unit:'mi',basis:'dashboard_unspecified',source:'motive_dashboard_manual' as const,observed_at:null,captured_at:new Date().toISOString(),freshness:'unknown' as const,snapshot_id:'fixture',source_age_text:null}
const telemetry: FleetTelemetry = {location:null,speed:null,fuel:null,fault_count:null,motion:'unknown',odometer:reading,engine_hours:{...reading,value:params.has('zero')?0:23520,unit:'h'}}
ReactDOM.createRoot(document.getElementById('root')!).render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><main className="fleet-root" style={{minHeight:'100vh',padding:'24px',display:'flex',justifyContent:'flex-end',alignItems:'flex-start'}}><TruckDiagnostics truckId="synthetic-truck" telemetry={params.has('missing')?null:telemetry}/></main></QueryClientProvider>)
