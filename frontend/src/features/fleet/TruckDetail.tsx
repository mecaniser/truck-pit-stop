import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  ArrowLeft, Gauge, Calendar, Wrench, AlertTriangle, History, Truck, User, Box, Map as MapIcon,
  Shield, Phone, ClipboardList, Loader2, Pencil, Plus, CheckCircle2,
} from 'lucide-react'
import api from '../../lib/api'
import type { BoardTruck, TruckDetail as TruckDetailData, IncidentSeverity } from './types'
import { STATUS_META, fmt, money, fmtDate, pmState, initials } from './helpers'
import FleetMap from './FleetMap'
import { TruckEditModal, LogIncidentModal, InspectionsSection, AssignDriverModal } from './FleetModals'

const sevClass: Record<IncidentSeverity, string> = {
  critical: 'inc-high', high: 'inc-high', medium: 'inc-med', low: 'inc-low',
}

function Section({ title, icon, count, right, children }: {
  title: string; icon: React.ReactNode; count?: number; right?: React.ReactNode; children: React.ReactNode
}) {
  return (
    <section className="dsec">
      <div className="dsec-head">
        <div className="dsec-title">{icon}<h3>{title}</h3>{count != null && <span className="dsec-count">{count}</span>}</div>
        {right}
      </div>
      {children}
    </section>
  )
}

function Metric({ icon, label, value, unit, note, noteCls }: {
  icon: React.ReactNode; label: string; value: React.ReactNode; unit?: string; note?: string; noteCls?: string
}) {
  return (
    <div className="metric">
      <div className="metric-ic">{icon}</div>
      <div>
        <div className="metric-lbl">{label}</div>
        <div className="metric-val">{value}{unit && <span className="metric-unit"> {unit}</span>}</div>
        {note && <div className={'metric-note ' + (noteCls || '')}>{note}</div>}
      </div>
    </div>
  )
}

export default function TruckDetail({
  truckId, trucks, onBack, onOpen,
}: { truckId: string; trucks: BoardTruck[]; onBack: () => void; onOpen: (id: string) => void }) {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery<TruckDetailData>({
    queryKey: ['fleet-truck', truckId],
    queryFn: async () => (await api.get(`/fleet/trucks/${truckId}`)).data,
  })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['fleet-truck', truckId] })
    qc.invalidateQueries({ queryKey: ['fleet-board'] })
  }
  const newWO = useMutation({
    mutationFn: async () => (await api.post(`/fleet/trucks/${truckId}/work-order`)).data,
    onSuccess: () => { toast.success('Work order created'); refresh() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed'),
  })
  const schedulePM = useMutation({
    mutationFn: async () => (await api.post(`/fleet/trucks/${truckId}/schedule-pm`)).data,
    onSuccess: () => { toast.success('PM work order scheduled'); refresh() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed'),
  })
  const resolveIncident = useMutation({
    mutationFn: async (id: string) => (await api.patch(`/fleet/incidents/${id}`, { status: 'resolved' })).data,
    onSuccess: () => { toast.success('Incident resolved'); refresh() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed'),
  })
  const repairFromIncident = useMutation({
    mutationFn: async (id: string) => (await api.post(`/fleet/incidents/${id}/create-repair`)).data,
    onSuccess: () => { toast.success('Internal repair order created'); refresh() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed'),
  })
  const [editing, setEditing] = useState(false)
  const [logging, setLogging] = useState(false)
  const [assigningDriver, setAssigningDriver] = useState(false)

  if (isLoading || !data) return <div className="loader"><Loader2 size={20} className="animate-spin" /></div>

  const t = data.truck
  const meta = STATUS_META[t.status]
  const pm = pmState(t)
  // map trucks: ensure the focused truck (fresh coords) is represented
  const mapTrucks = trucks.some((x) => x.id === t.id) ? trucks : [...trucks, t]

  return (
    <div className="detail">
      <div className="dhead">
        <button className="dback" onClick={onBack}><ArrowLeft size={16} /> Fleet board</button>
        <div className="dhead-main">
          <div>
            <div className="dhead-unit-row">
              <h1 className="dhead-unit">{t.unit_number}</h1>
              <span className="dbadge" style={{ ['--st' as any]: meta.dot }}>
                <i className={t.moving ? 'is-moving' : ''} />{meta.label}
              </span>
            </div>
            <div className="dhead-sub">{`${t.year || ''} ${t.make} ${t.model}`.trim()}{t.body_type ? ` · ${t.body_type}` : ''}</div>
          </div>
          <div className="dhead-r">
            <button className="dbtn dbtn-ghost" onClick={() => setEditing(true)}>
              <Pencil size={15} /> Edit
            </button>
            <button className="dbtn dbtn-ghost" onClick={() => newWO.mutate()} disabled={newWO.isPending}>
              <ClipboardList size={15} /> New work order
            </button>
            <button className="dbtn dbtn-yellow" onClick={() => schedulePM.mutate()} disabled={schedulePM.isPending}>
              <Calendar size={15} /> Schedule PM
            </button>
          </div>
        </div>
      </div>

      <div className="dmetrics">
        <Metric icon={<Gauge size={18} />} label="Odometer" value={fmt(t.odometer)} unit="mi" />
        <Metric icon={<Calendar size={18} />} label="Next PM" value={fmt(t.next_pm_miles)} unit="mi" note={pm.label} noteCls={pm.cls} />
        <Metric icon={<Wrench size={18} />} label="Lifetime service spend" value={money(data.lifetime_spend)} />
        <Metric icon={<AlertTriangle size={18} />} label="Incidents on record" value={data.incidents_count} note={data.incidents_count ? 'see log' : 'clean'} />
      </div>

      <div className="dgrid">
        <div className="dcol">
          <Section title="Service history" icon={<History size={17} />} count={data.history.length}>
            {data.history.length === 0 ? (
              <div className="empty-note"><History size={16} /> No service history yet.</div>
            ) : (
              <div className="timeline">
                {data.history.map((h) => (
                  <div key={h.id} className={'tl-item tl-' + h.kind.toLowerCase()}>
                    <div className="tl-marker" />
                    <div className="tl-body">
                      <div className="tl-row1">
                        <span className={'tl-kind tl-kind-' + h.kind.toLowerCase()}>{h.kind}</span>
                        <span className="tl-date">{fmtDate(h.date)}</span>
                        <span className="tl-odo">{fmt(h.odometer)} mi</span>
                      </div>
                      <div className="tl-summary">{h.summary || '—'}</div>
                      <div className="tl-meta">
                        <span><User size={12} /> {h.mechanic || 'Unassigned'}</span>
                        {h.cost != null && <span className="tl-cost">{money(h.cost)}</span>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section
            title="Incidents on the road"
            icon={<AlertTriangle size={17} />}
            count={data.incidents.length}
            right={
              <button className="dbtn dbtn-ghost" style={{ height: 34 }} onClick={() => setLogging(true)}>
                <Plus size={14} /> Log incident
              </button>
            }
          >
            {data.incidents.length ? (
              <div className="inc-list">
                {data.incidents.map((inc) => (
                  <div key={inc.id} className={'inc ' + sevClass[inc.severity]}>
                    <div className="inc-sev" />
                    <div className="inc-body">
                      <div className="inc-row1"><b>{inc.type}</b><span className="inc-date">{fmtDate(inc.date)}</span></div>
                      {inc.location && <div className="inc-loc"><MapIcon size={12} /> {inc.location}</div>}
                      <div className="inc-note">{inc.note}</div>
                      <div style={{ display: 'flex', gap: 8, marginTop: 9 }}>
                        {inc.repair_order_id ? (
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--st-active)' }}>
                            <Wrench size={12} /> Repair linked
                          </span>
                        ) : (
                          <button className="dbtn dbtn-ghost" style={{ height: 30, fontSize: 12 }}
                            onClick={() => repairFromIncident.mutate(inc.id)} disabled={repairFromIncident.isPending}>
                            <Wrench size={12} /> Create repair
                          </button>
                        )}
                        {inc.status !== 'resolved' && (
                          <button className="dbtn dbtn-ghost" style={{ height: 30, fontSize: 12 }}
                            onClick={() => resolveIncident.mutate(inc.id)} disabled={resolveIncident.isPending}>
                            <CheckCircle2 size={12} /> Resolve
                          </button>
                        )}
                        {inc.status === 'resolved' && (
                          <span style={{ fontSize: 12, color: 'var(--st-active)' }}>Resolved</span>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-note"><Shield size={16} /> No incidents recorded for this unit.</div>
            )}
          </Section>

          <InspectionsSection vehicleId={t.id} truckId={t.id} />
        </div>

        <div className="dcol">
          <Section title="Truck identity" icon={<Truck size={17} />}>
            <div className="id-grid">
              <Stat label="VIN" value={t.vin || '—'} mono />
              <Stat label="Plate" value={t.plate || '—'} mono />
              <Stat label="Year" value={t.year ?? '—'} mono />
              <Stat label="Body type" value={t.body_type || '—'} />
              <Stat label="Make" value={t.make} />
              <Stat label="Model" value={t.model} />
            </div>
          </Section>

          <Section title="Driver & crew" icon={<User size={17} />}>
            <div>
              <div className="person person-driver">
                <div className="avatar">{initials(t.driver_name)}</div>
                <div>
                  <div className="person-name">{t.driver_name || 'Unassigned'}</div>
                  <div className="person-role">Assigned driver</div>
                </div>
                {data.driver_phone && (
                  <a className="person-call" href={`tel:${data.driver_phone}`}><Phone size={15} /></a>
                )}
                <button
                  className="dbtn dbtn-ghost"
                  style={{ height: 34, padding: '0 12px', fontSize: 12.5, marginLeft: data.driver_phone ? 8 : 'auto' }}
                  onClick={() => setAssigningDriver(true)}
                >
                  {t.driver_name ? 'Change driver' : 'Assign driver'}
                </button>
              </div>
              {t.assigned_mechanic && (
                <div className="person">
                  <div className="avatar avatar-mech">{initials(t.assigned_mechanic)}</div>
                  <div>
                    <div className="person-name">{t.assigned_mechanic}</div>
                    <div className="person-role">Lead mechanic on file</div>
                  </div>
                </div>
              )}
              {data.crew.filter((m) => m !== t.assigned_mechanic).slice(0, 3).map((m) => (
                <div key={m} className="person person-sm">
                  <div className="avatar avatar-sm">{initials(m)}</div>
                  <div>
                    <div className="person-name">{m}</div>
                    <div className="person-role">Worked on this truck</div>
                  </div>
                </div>
              ))}
            </div>
          </Section>

          <Section title="Parts & warranty" icon={<Box size={17} />} count={data.parts.length}>
            {data.parts.length === 0 ? (
              <div className="empty-note"><Box size={16} /> No parts on record.</div>
            ) : (
              <div className="parts">
                {data.parts.map((p) => (
                  <div key={p.id} className="part">
                    <div>
                      <div className="part-name">{p.name}</div>
                      <div className="part-meta">{fmtDate(p.date)} · {fmt(p.odometer)} mi</div>
                    </div>
                    <span className={'part-w ' + (p.active ? 'w-on' : 'w-off')}>
                      {p.active ? 'Warranty to ' + fmtDate(p.warranty_until) : (p.warranty_until ? 'Expired' : 'No warranty')}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Section>
        </div>
      </div>

      <Section
        title="Current location & nearby units"
        icon={<MapIcon size={17} />}
        right={
          <div className="loc-now">
            <i className={'loc-dot' + (t.moving ? ' is-moving' : '')} style={{ background: meta.dot }} />
            {t.location_label || 'Location unknown'}
            {t.speed_mph ? <span className="loc-mph"> · {t.speed_mph} mph {t.heading || ''}</span> : <span className="loc-mph"> · parked</span>}
          </div>
        }
      >
        <div className="dmap-wrap">
          <FleetMap trucks={mapTrucks} focusId={t.id} onSelect={(tr) => tr.id !== t.id && onOpen(tr.id)} />
          <div className="dmap-side">
            <div className="dmap-side-h">Nearest units</div>
            {data.nearest.length === 0 && <div className="empty-note">No located units nearby.</div>}
            {data.nearest.map((n) => (
              <button key={n.id} className="near-row" onClick={() => onOpen(n.id)}>
                <i className="near-dot" style={{ background: STATUS_META[n.status].dot }} />
                <span className="near-unit">{n.unit_number}</span>
                <span className="near-loc">{n.city || '—'}</span>
                <span className="near-mi">{n.miles} mi</span>
              </button>
            ))}
          </div>
        </div>
      </Section>

      {editing && <TruckEditModal truck={t} detail={data} onClose={() => setEditing(false)} />}
      {assigningDriver && <AssignDriverModal truck={t} driverPhone={data.driver_phone} onClose={() => setAssigningDriver(false)} />}
      {logging && <LogIncidentModal vehicleId={t.id} truckId={t.id} onClose={() => setLogging(false)} />}
    </div>
  )
}

function Stat({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="id-cell">
      <div className="id-k">{label}</div>
      <div className={'id-v' + (mono ? ' mono' : '')}>{value}</div>
    </div>
  )
}
