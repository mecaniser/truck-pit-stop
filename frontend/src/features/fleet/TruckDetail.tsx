import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  ArrowLeft, Gauge, Calendar, Wrench, AlertTriangle, History, Truck, User, Box, Map as MapIcon,
  Shield, Phone, ClipboardList, Loader2, Pencil, Plus, CheckCircle2, ChevronDown, Check, Info, Trash2,
} from 'lucide-react'
import api from '../../lib/api'
import type { BoardTruck, TruckDetail as TruckDetailData, IncidentSeverity, IncidentEntry } from './types'
import { STATUS_META, fmt, money, fmtDate, pmState, initials } from './helpers'
import FleetMap from './FleetMap'
import { TruckEditModal, LogIncidentModal, EditIncidentModal, InspectionsSection, NewWorkOrderModal, WorkOrderPanel, AssignDriverModal, SchedulePMModal, Modal, invalidateFleetAndCockpit } from './FleetModals'

const sevClass: Record<IncidentSeverity, string> = {
  critical: 'inc-high', high: 'inc-high', medium: 'inc-med', low: 'inc-low',
}

// Manual idle-status options. 'auto' clears the override (back to derived).
const STATUS_OPTIONS: { value: string; label: string; dot: string }[] = [
  { value: 'auto', label: 'Auto (on the road / PM due)', dot: '#22c55e' },
  { value: 'active', label: 'On the road', dot: '#22c55e' },
  { value: 'available', label: 'Available', dot: '#14b8a6' },
  { value: 'yard', label: 'In the yard', dot: '#64748b' },
  { value: 'out_of_service', label: 'Out of service', dot: '#ef4444' },
]

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
    // Fleet WOs are repair orders — keep the owner's cockpit queue in sync too.
    invalidateFleetAndCockpit(qc)
  }
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
  const deleteIncident = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/fleet/incidents/${id}`)).data,
    onSuccess: () => { toast.success('Incident deleted'); refresh() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to delete incident'),
  })
  const [editing, setEditing] = useState(false)
  const [logging, setLogging] = useState(false)
  const [editingIncident, setEditingIncident] = useState<IncidentEntry | null>(null)
  const [armedDeleteIncidentId, setArmedDeleteIncidentId] = useState<string | null>(null)
  const [newWOOpen, setNewWOOpen] = useState(false)
  const [woPanelId, setWoPanelId] = useState<string | null>(null)
  const [assigningDriver, setAssigningDriver] = useState(false)
  const [schedulePMOpen, setSchedulePMOpen] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [statusMenuOpen, setStatusMenuOpen] = useState(false)
  const setStatus = useMutation({
    mutationFn: async (value: string) => (await api.patch(`/fleet/trucks/${truckId}`, { status_override: value })).data,
    onSuccess: () => { toast.success('Status updated'); setStatusMenuOpen(false); refresh() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to set status'),
  })

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
              <div style={{ position: 'relative' }}>
                <button
                  className="dbadge"
                  style={{ ['--st' as any]: meta.dot, cursor: 'pointer', border: 'none', font: 'inherit' }}
                  onClick={() => setStatusMenuOpen((o) => !o)}
                  title="Change status"
                >
                  <i className={t.moving ? 'is-moving' : ''} />{meta.label}
                  <ChevronDown size={12} style={{ marginLeft: 5, opacity: 0.7 }} />
                </button>
                {statusMenuOpen && (
                  <>
                    <div onClick={() => setStatusMenuOpen(false)} style={{ position: 'fixed', inset: 0, zIndex: 40 }} />
                    <div style={{ position: 'absolute', top: 'calc(100% + 6px)', left: 0, zIndex: 41, background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 10, padding: 6, minWidth: 230, boxShadow: '0 10px 28px rgba(0,0,0,.45)' }}>
                      {t.open_work_order_count > 0 && (
                        <div className="id-k" style={{ textTransform: 'none', letterSpacing: 0, padding: '4px 8px 6px', color: 'var(--muted-2)' }}>
                          A work order is open, so the board shows that until it's done — this applies once it closes.
                        </div>
                      )}
                      {STATUS_OPTIONS.map((opt) => {
                        const current = (t.status_override || 'auto') === opt.value
                        return (
                          <button
                            key={opt.value}
                            onClick={() => setStatus.mutate(opt.value)}
                            disabled={setStatus.isPending}
                            style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%', padding: '7px 8px', background: current ? 'var(--surface-2)' : 'transparent', border: 'none', borderRadius: 7, color: 'var(--text)', cursor: 'pointer', fontSize: 13, textAlign: 'left' }}
                          >
                            <span style={{ width: 8, height: 8, borderRadius: 99, background: opt.dot, flexShrink: 0 }} />
                            {opt.label}
                            {current && <Check size={14} style={{ marginLeft: 'auto', color: 'var(--yellow)' }} />}
                          </button>
                        )
                      })}
                    </div>
                  </>
                )}
              </div>
              <button
                className="dbtn dbtn-ghost dhead-details"
                style={{ height: 30, padding: '0 12px', fontSize: 12.5 }}
                onClick={() => setDetailsOpen(true)}
                title="Details"
              >
                <Info size={14} /> <span className="dbtn-label">Details</span>
              </button>
            </div>
            <div className="dhead-sub">
              {`${t.year || ''} ${t.make} ${t.model}`.trim()}{t.body_type ? ` · ${t.body_type}` : ''}
              <span style={{ marginLeft: 8, display: 'inline-flex', alignItems: 'center', gap: 4, color: 'var(--muted)' }}>
                · <User size={12} /> {t.driver_name || 'No driver'}
              </span>
            </div>
          </div>
          <div className="dhead-stats">
            <div className="dhead-stat">
              <span className="dhead-stat-ic"><Gauge size={17} /></span>
              <span className="dhead-stat-k">Odometer</span>
              <span className="dhead-stat-v">{fmt(t.odometer)} <span className="dhead-stat-u">mi</span></span>
            </div>
            <div className="dhead-stat-div" />
            <div className="dhead-stat has-note">
              <span className="dhead-stat-ic"><Calendar size={17} /></span>
              <span className="dhead-stat-k">Next PM</span>
              <span className="dhead-stat-v">
                {t.next_pm_miles != null ? <>{fmt(t.next_pm_miles)} <span className="dhead-stat-u">mi</span></> : '—'}
              </span>
              <span className={'dhead-stat-note ' + pm.cls}>{pm.label}</span>
            </div>
          </div>
          <div className="dhead-r">
            <button className="dbtn dbtn-ghost" onClick={() => setEditing(true)} title="Edit">
              <Pencil size={15} /> <span className="dbtn-label">Edit</span>
            </button>
            <button className="dbtn dbtn-ghost" onClick={() => setNewWOOpen(true)} title="New work order">
              <ClipboardList size={15} /> <span className="dbtn-label">New work order</span><span className="dbtn-abbr">WO</span>
            </button>
            <button className="dbtn dbtn-yellow" onClick={() => setSchedulePMOpen(true)} title={t.pm_due_date ? 'Reschedule PM' : 'Schedule PM'}>
              <Calendar size={15} /> <span className="dbtn-label">{t.pm_due_date ? 'Reschedule PM' : 'Schedule PM'}</span><span className="dbtn-abbr">PM</span>
            </button>
          </div>
        </div>
      </div>

      {t.warning_lights && t.warning_lights.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', margin: '0 0 16px', padding: '10px 14px', borderRadius: 12, background: 'rgba(230,57,70,.12)', border: '1px solid rgba(230,57,70,.35)' }}>
          <AlertTriangle size={16} style={{ color: 'var(--red)', flexShrink: 0 }} />
          <strong style={{ fontSize: 13, color: 'var(--red)' }}>
            Dashboard warning{t.warning_lights.length > 1 ? 's' : ''} on:
          </strong>
          {t.warning_lights.map((w) => (
            <span key={w} style={{ fontSize: 12.5, background: 'rgba(230,57,70,.15)', border: '1px solid rgba(230,57,70,.3)', borderRadius: 999, padding: '2px 10px', color: 'var(--text)' }}>{w}</span>
          ))}
        </div>
      )}

      <div className="dcol">
          <InspectionsSection vehicleId={t.id} truckId={t.id} currentOdometer={t.odometer} />

          <Section
            title="Incidents on the road"
            icon={<AlertTriangle size={17} />}
            count={data.incidents.length}
            right={
              <button className="dbtn dbtn-ghost dsec-action" style={{ height: 34 }} onClick={() => setLogging(true)} title="Log incident">
                <Plus size={14} /> <span className="dbtn-label">Log incident</span>
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
                        <button className="dbtn dbtn-ghost" style={{ height: 30, fontSize: 12 }}
                          onClick={() => setEditingIncident(inc)}>
                          <Pencil size={12} /> Edit
                        </button>
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
                        {/* Delete is only available when no repair order was spawned
                            from this incident; the backend blocks it otherwise. */}
                        {!inc.repair_order_id && (
                          armedDeleteIncidentId === inc.id ? (
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                              <span style={{ fontSize: 12, color: 'var(--muted)' }}>Delete this incident?</span>
                              <button className="dbtn dbtn-ghost" style={{ height: 30, fontSize: 12 }}
                                disabled={deleteIncident.isPending} onClick={() => setArmedDeleteIncidentId(null)}>
                                Cancel
                              </button>
                              <button className="dbtn dbtn-ghost" style={{ height: 30, fontSize: 12, color: 'var(--red)' }}
                                disabled={deleteIncident.isPending}
                                onClick={() => deleteIncident.mutate(inc.id, { onSuccess: () => setArmedDeleteIncidentId(null) })}>
                                {deleteIncident.isPending ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />} Delete
                              </button>
                            </span>
                          ) : (
                            <button className="dbtn dbtn-ghost" style={{ height: 30, fontSize: 12, color: 'var(--red)' }}
                              onClick={() => setArmedDeleteIncidentId(inc.id)}>
                              <Trash2 size={12} /> Delete
                            </button>
                          )
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

          <Section title="Open work orders" icon={<ClipboardList size={17} />} count={data.open_work_orders.length}>
            {data.open_work_orders.length === 0 ? (
              <div className="empty-note"><ClipboardList size={16} /> No open work orders.</div>
            ) : (
              <div className="list-rows">
                {data.open_work_orders.map((wo) => (
                  <button key={wo.repair_order_id} className="lrow" onClick={() => setWoPanelId(wo.repair_order_id)}>
                    <span className="lrow-mono">{wo.id}</span>
                    <span className="lrow-tx">{wo.summary || '—'}</span>
                    <span className="lrow-r">
                      <span className="lrow-st">{wo.status}</span>
                      <span className="lrow-tx">{wo.mechanic || 'Unassigned'}</span>
                    </span>
                  </button>
                ))}
              </div>
            )}
          </Section>

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
      </div>

      {detailsOpen && <TruckDetailsModal truck={t} detail={data} onChangeDriver={() => setAssigningDriver(true)} onClose={() => setDetailsOpen(false)} />}
      {editing && <TruckEditModal truck={t} detail={data} onClose={() => setEditing(false)} />}
      {schedulePMOpen && <SchedulePMModal truck={t} onClose={() => setSchedulePMOpen(false)} onDone={refresh} />}
      {assigningDriver && <AssignDriverModal truck={t} driverPhone={data.driver_phone} onClose={() => setAssigningDriver(false)} />}
      {logging && <LogIncidentModal vehicleId={t.id} truckId={t.id} onClose={() => setLogging(false)} />}
      {editingIncident && <EditIncidentModal incident={editingIncident} truckId={t.id} onClose={() => setEditingIncident(null)} />}
      {newWOOpen && <NewWorkOrderModal truckId={t.id} unitNumber={t.unit_number} onClose={() => setNewWOOpen(false)} onCreated={refresh} />}
      {woPanelId && <WorkOrderPanel repairOrderId={woPanelId} onClose={() => setWoPanelId(null)} onChanged={refresh} />}
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

/* Combined truck identity + driver & crew, behind the "Details" button. */
function TruckDetailsModal({ truck, detail, onChangeDriver, onClose }: {
  truck: BoardTruck; detail: TruckDetailData; onChangeDriver: () => void; onClose: () => void
}) {
  return (
    <Modal title={`Details · ${truck.unit_number || 'Truck'}`} icon={<Truck size={17} />} onClose={onClose} width={520}>
      <div className="dmap-side-h" style={{ marginBottom: 8 }}>Identity</div>
      <div className="id-grid">
        <Stat label="VIN" value={truck.vin || '—'} mono />
        <Stat label="Plate" value={truck.plate || '—'} mono />
        <Stat label="Year" value={truck.year ?? '—'} mono />
        <Stat label="Body type" value={truck.body_type || '—'} />
        <Stat label="Make" value={truck.make} />
        <Stat label="Model" value={truck.model} />
      </div>

      <div className="dmap-side-h" style={{ margin: '18px 0 8px' }}>Service record</div>
      <div className="id-grid">
        <Stat label="Lifetime service spend" value={money(detail.lifetime_spend)} />
        <Stat label="Incidents on record" value={detail.incidents_count || '—'} />
      </div>

      <div className="dmap-side-h" style={{ margin: '18px 0 8px' }}>Driver & crew</div>
      <div className="person person-driver">
        <div className="avatar">{initials(truck.driver_name)}</div>
        <div>
          <div className="person-name">{truck.driver_name || 'Unassigned'}</div>
          <div className="person-role">Assigned driver</div>
        </div>
        {detail.driver_phone && (
          <a className="person-call" href={`tel:${detail.driver_phone}`}><Phone size={15} /></a>
        )}
        <button
          className="dbtn dbtn-ghost"
          style={{ height: 34, padding: '0 12px', fontSize: 12.5, marginLeft: detail.driver_phone ? 8 : 'auto' }}
          onClick={onChangeDriver}
        >
          {truck.driver_name ? 'Change driver' : 'Assign driver'}
        </button>
      </div>
      {truck.assigned_mechanic && (
        <div className="person">
          <div className="avatar avatar-mech">{initials(truck.assigned_mechanic)}</div>
          <div>
            <div className="person-name">{truck.assigned_mechanic}</div>
            <div className="person-role">Lead mechanic on file</div>
          </div>
        </div>
      )}
      {detail.crew.filter((m) => m !== truck.assigned_mechanic).slice(0, 3).map((m) => (
        <div key={m} className="person person-sm">
          <div className="avatar avatar-sm">{initials(m)}</div>
          <div>
            <div className="person-name">{m}</div>
            <div className="person-role">Worked on this truck</div>
          </div>
        </div>
      ))}
    </Modal>
  )
}
