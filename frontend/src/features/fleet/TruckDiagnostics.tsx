import { Popover, PopoverButton, PopoverPanel } from '@headlessui/react'
import { useQuery } from '@tanstack/react-query'
import { Activity, RotateCcw, X } from 'lucide-react'
import api from '@/lib/api'
import { readingCaption, retained, useTelemetryClock, type FleetTelemetry } from './telemetry'
import './truckDiagnostics.css'

export interface DiagnosticCode {
  code: string | null
  spn: string | null
  fmi: string | null
  description: string | null
  severity: string | null
  network: string | null
  source_address: string | null
  occurrence_count: number | null
  first_detected_text: string | null
  last_observed_text: string | null
  timezone_basis: string
}

export interface DiagnosticsResponse {
  last_checked_at: string | null
  coverage: 'unknown' | 'partial' | 'complete'
  explicit_empty: boolean | null
  codes: DiagnosticCode[]
}

function checkedTime(value: string) {
  return new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export default function TruckDiagnostics({ truckId, telemetry }: { truckId: string; telemetry?: FleetTelemetry | null }) {
  return <Popover className="truck-health">
    <PopoverButton className="dbtn dbtn-ghost dhead-health"><Activity size={15} aria-hidden="true" /> View health</PopoverButton>
    <PopoverPanel className="truck-health-panel" focus>
      <div className="truck-health-heading"><h2>Truck health</h2><PopoverButton className="truck-health-close" aria-label="Close truck health"><X size={18} aria-hidden="true" /></PopoverButton></div>
      <HealthVitals telemetry={telemetry} /><TruckDiagnosticsContent truckId={truckId} />
    </PopoverPanel>
  </Popover>
}

function TruckDiagnosticsContent({ truckId }: { truckId: string }) {
  const query = useQuery<DiagnosticsResponse>({
    queryKey: ['fleet-truck-diagnostics', truckId],
    queryFn: async () => (await api.get(`/fleet/trucks/${truckId}/diagnostics`)).data,
  })
  const data = query.data
  return <div className="diagnostics-body">
      {query.isLoading ? <p role="status">Loading fault codes…</p>
        : query.isError ? <div role="alert"><p>Fault codes could not be loaded.</p><button type="button" className="btn" onClick={() => void query.refetch()} disabled={query.isFetching}><RotateCcw size={14} />Try again</button></div>
        : !data?.last_checked_at ? <p>No verified dashboard check is available for this truck.</p>
        : <>
          <p className="diagnostics-meta">Motive · Dashboard checked <time dateTime={data.last_checked_at}>{checkedTime(data.last_checked_at)}</time></p>
          {data.coverage === 'partial' && <p>Partial capture. Some codes may be unavailable.</p>}
          {data.explicit_empty && data.coverage === 'complete' && !data.codes.length
            ? <p>No current fault codes were reported at this check.</p>
            : !data.codes.length ? <p>Fault-code details are unavailable.</p>
            : <ul className="diagnostics-codes">{data.codes.map((code, index) => <li key={`${code.spn}-${code.fmi}-${code.code}-${index}`}>
              <div className="diagnostics-code-title"><strong>{code.spn ? `SPN ${code.spn}` : code.code || 'Code unavailable'}{code.fmi ? ` · FMI ${code.fmi}` : ''}</strong>{code.severity && <span>{code.severity}</span>}</div>
              <p className="diagnostics-cause">{code.description || 'Description unavailable'}</p>
              <dl>
                <div><dt>First detected</dt><dd>{code.first_detected_text || 'Unknown'}</dd></div>
                <div><dt>Last observed</dt><dd>{code.last_observed_text || 'Unknown'}</dd></div>
                {code.occurrence_count != null && <div><dt>Occurrences</dt><dd>{code.occurrence_count}</dd></div>}
                {code.network && <div><dt>Network</dt><dd>{code.network}</dd></div>}
              </dl>
            </li>)}</ul>}
          <p className="diagnostics-meta">Codes reflect the last dashboard check. Missing codes do not confirm a repair.</p>
        </>}
  </div>
}

function HealthVitals({ telemetry }: { telemetry?: FleetTelemetry | null }) {
  const now = useTelemetryClock()
  return <dl className="health-vitals">{([
    ['odometer', 'Mileage', 'mi'], ['engine_hours', 'Engine hours', 'h'],
  ] as const).map(([field, label, unit]) => {
    const reading = retained(telemetry?.[field], now)
    return <div key={field}><dt>{label}</dt><dd>{reading ? `${reading.value.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${unit}` : 'Unavailable'}</dd>{reading && <small>{reading.source === 'motive_api' ? 'Motive API' : 'Motive dashboard'} · {readingCaption(reading)}{!reading.observed_at && ' · Observation time unknown'}</small>}</div>
  })}</dl>
}
