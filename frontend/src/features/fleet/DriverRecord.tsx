import type { ReactNode } from 'react'
import { Popover, PopoverButton, PopoverPanel } from '@headlessui/react'
import { useQuery } from '@tanstack/react-query'
import { Clock3, RotateCcw, X } from 'lucide-react'
import api from '@/lib/api'
import type { BoardTruck } from './types'
import type { DriverRecordDetail, DriverRecordResponse, DriverRecordSection, DriverSafetyBand } from './driverRecordTypes'
import './driverRecord.css'

type DriverTruck = Pick<BoardTruck, 'id' | 'driver_name' | 'driver_record' | 'board_membership_customer_id'>
const number = (value: number) => value.toLocaleString(undefined, { maximumFractionDigits: 1 })
const checkedTime = (value: string) => new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })

function SafetyDashes({ band }: { band: DriverSafetyBand }) {
  return <span className="driver-safety-dashes" data-band={band} aria-hidden="true">{(['red', 'yellow', 'green'] as const).map(tone => <i key={tone} className={tone === band ? `is-${tone}` : ''} />)}</span>
}

/** Only use with the truck's current assigned driver, never a historical trip driver. */
export default function DriverRecord({ truck, displayName }: { truck: DriverTruck; displayName?: string | null }) {
  const name = displayName ?? truck.driver_name
  if (!name || (displayName && displayName.trim() !== truck.driver_name?.trim())) return null
  const summary = truck.driver_record?.driver_name.trim() === name.trim() ? truck.driver_record : null
  const score = summary?.safety_score
  const band = summary?.stale ? 'unknown' : summary?.safety_band ?? 'unknown'
  const description = score == null ? 'Safety score unavailable' : `Safety score ${number(score)}`
  const label = `Driver record for ${name}. ${description}${summary?.safety_band_label ? `, ${summary.safety_band_label}` : ''}${summary?.stale ? ', stale capture' : ''}`
  return <Popover as="span" className="driver-record" onClick={event => event.stopPropagation()} onKeyDown={event => event.stopPropagation()}>
    <PopoverButton className="driver-record-trigger" aria-label={label} title={label}>
      <SafetyDashes band={band} /><span className="driver-record-score">{score == null ? '—' : number(score)}</span>
      {summary?.stale && <Clock3 size={12} aria-hidden="true" />}
    </PopoverButton>
    <PopoverPanel anchor={{ to: 'bottom start', gap: 8, padding: 12 }} portal focus className="driver-record-panel" role="dialog" aria-label={`Driver record for ${name}`}>
      <header className="driver-record-heading"><div><small>Motive · Driver record</small><h2>{name}</h2></div><PopoverButton className="driver-record-close" aria-label="Close driver record"><X size={18} aria-hidden="true" /></PopoverButton></header>
      <DriverRecordContent truck={truck} />
    </PopoverPanel>
  </Popover>
}

function DriverRecordContent({ truck }: { truck: DriverTruck }) {
  const query = useQuery<DriverRecordResponse>({
    queryKey: ['fleet-driver-record', truck.id, truck.board_membership_customer_id, truck.driver_record?.provider_driver_id, truck.driver_record?.capture_id, truck.driver_name],
    gcTime: 0,
    queryFn: async () => {
      const data: DriverRecordResponse = (await api.get(`/fleet/trucks/${truck.id}/driver-record`)).data
      if (data.vehicle_id !== truck.id || (data.record && (data.record.driver_name.trim() !== truck.driver_name?.trim() || (truck.driver_record && data.record.provider_driver_id !== truck.driver_record.provider_driver_id)))) throw new Error('Driver assignment changed')
      return data
    },
  })
  if (query.isLoading || query.isFetching) return <p className="driver-record-message" role="status">Loading driver record…</p>
  if (query.isError) return <div className="driver-record-message" role="alert"><p>Driver record could not be loaded.</p><button type="button" className="driver-record-retry" onClick={() => void query.refetch()} disabled={query.isFetching}><RotateCcw size={14} aria-hidden="true" />Try again</button></div>
  const data = query.data
  if (data?.availability === 'assignment_unverified') return <p className="driver-record-message">Motive has not verified the current driver assignment for this truck.</p>
  if (data?.availability !== 'available' || !data.record) return <p className="driver-record-message">No verified Motive record is available for this driver.</p>
  return <RecordDetails record={data.record} />
}

function Section({ title, period, state, children }: { title: string; period?: string | null; state: DriverRecordSection; children: ReactNode }) {
  return <section className="driver-record-section"><div className="driver-record-section-heading"><h3>{title}</h3>{period && <span>{period}</span>}</div>
    {state === 'unavailable' ? <p className="driver-record-muted">Not available in this capture.</p> : state === 'empty' ? <p className="driver-record-muted">None reported at this check.</p> : children}
  </section>
}

function RecordDetails({ record }: { record: DriverRecordDetail }) {
  const { safety, fuel, coaching, recent_events: events, sections } = record
  return <div className="driver-record-body">
    <div className="driver-record-provenance"><span>Checked <time dateTime={record.last_checked_at}>{checkedTime(record.last_checked_at)}</time></span>{record.stale && <strong><Clock3 size={12} aria-hidden="true" />Stale capture</strong>}{record.coverage === 'partial' && <span>Partial capture</span>}</div>
    <Section title="Safety score" period={safety.period_text} state={sections.safety}>
      <div className="driver-safety-summary"><strong>{safety.score == null ? '—' : number(safety.score)}</strong><div><SafetyDashes band={record.stale ? 'unknown' : safety.band} /><span>{safety.band_label || 'Rating unavailable'}</span></div>{safety.coaching_label && <span className="driver-safety-coaching">{safety.coaching_label}</span>}</div>
      {safety.top_behaviors.length > 0 && <><h4>Behaviors impacting score</h4><dl className="driver-record-facts">{safety.top_behaviors.map((behavior, index) => <div key={`${behavior.behavior}-${index}`}><dt>{behavior.behavior}</dt><dd>{behavior.score_impact == null ? '—' : `${behavior.score_impact > 0 ? '+' : ''}${number(behavior.score_impact)}`}</dd></div>)}</dl></>}
      {safety.history.length > 0 && <><h4>Score history</h4><dl className="driver-record-facts">{safety.history.map((point, index) => <div key={`${point.period_text}-${index}`}><dt>{point.period_text}</dt><dd>{point.score == null ? '—' : number(point.score)}</dd></div>)}</dl></>}
    </Section>
    <Section title="Fuel performance" period={fuel.period_text} state={sections.fuel}>
      <div className="driver-fuel-summary"><strong>{fuel.utilization_percent == null ? '—' : `${number(fuel.utilization_percent)}%`}</strong><span>Utilization</span></div>
      {fuel.utilization_percent != null && <div className="driver-fuel-track" role="meter" aria-label="Driver utilization" aria-valuenow={fuel.utilization_percent} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${Math.max(0, Math.min(100, fuel.utilization_percent))}%` }} /></div>}
      <dl className="driver-record-facts"><div><dt>Active time</dt><dd>{fuel.active_time_text ?? '—'}</dd></div><div><dt>Idle time</dt><dd>{fuel.idle_time_text ?? '—'}</dd></div>{fuel.metrics.map((metric, index) => <div key={`${metric.label}-${index}`}><dt>{metric.label}</dt><dd>{metric.value}{metric.unit ? ` ${metric.unit}` : ''}</dd></div>)}</dl>
    </Section>
    <Section title="Coaching" state={sections.coaching}>
      <dl className="driver-record-facts"><div><dt>Status</dt><dd>{coaching.status_label ?? '—'}</dd></div><div><dt>Open items</dt><dd>{coaching.open_count ?? '—'}</dd></div><div><dt>Last coached</dt><dd>{coaching.last_coached_text ?? '—'}</dd></div></dl>
    </Section>
    <Section title="Recent safety events" state={sections.recent_events}>
      {events.length ? <ul className="driver-record-events">{events.map((event, index) => <li key={`${event.occurred_at_text}-${index}`}><div><strong>{event.behavior}</strong>{event.status && <span className="driver-event-status">{event.status}</span>}</div><p>{event.occurred_at_text ?? 'Time unavailable'}{event.vehicle_label ? ` · ${event.vehicle_label}` : ''}</p>{event.location && <p>{event.location}</p>}{event.severity && <p>Severity · {event.severity}</p>}</li>)}</ul> : <p className="driver-record-muted">Event details unavailable.</p>}
    </Section>
    {record.unavailable_reasons.length > 0 && <ul className="driver-record-gaps">{record.unavailable_reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>}
  </div>
}
