import { useEffect, useMemo, useRef, useState } from 'react'
import { Spinner } from '@/components/ui'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  ArrowLeft, Gauge, Calendar, Wrench, AlertTriangle, History, Truck, User, Box, Map as MapIcon,
  Shield, Phone, ClipboardList, Pencil, Plus, CheckCircle2, ChevronDown, Check, Info, Trash2, Camera, MoreHorizontal,
} from 'lucide-react'
import api from '../../lib/api'
import { isSupportedPhotoFile, runPhotoUploadQueue, uploadDirectPhoto, type PhotoUploadStatus } from '@/lib/photoUpload'
import type { BoardTruck, TruckDetail as TruckDetailData, IncidentSeverity, IncidentEntry, FleetPhoto, HistoryEntry, PartEntry } from './types'
import { STATUS_META, fleetUnitLabel, fmt, money, fmtDate, pmState, initials } from './helpers'
import { formatUSPhone } from '@/utils/phone'
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
const incidentStatePillStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 5,
  height: 30,
  padding: '0 10px',
  fontSize: 12,
  color: 'var(--st-active)',
}
const incidentMenuItemStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  width: '100%',
  minHeight: 34,
  padding: '8px 10px',
  background: 'transparent',
  border: 'none',
  borderRadius: 7,
  color: 'var(--text)',
  cursor: 'pointer',
  font: 'inherit',
  fontSize: 12.5,
  textAlign: 'left',
}
const MAX_FLEET_PHOTO_BYTES = 10 * 1024 * 1024

function haversineMiles(aLat: number, aLng: number, bLat: number, bLng: number) {
  const radius = 3958.8
  const phi1 = aLat * Math.PI / 180
  const phi2 = bLat * Math.PI / 180
  const deltaPhi = (bLat - aLat) * Math.PI / 180
  const deltaLambda = (bLng - aLng) * Math.PI / 180
  const h = Math.sin(deltaPhi / 2) ** 2
    + Math.cos(phi1) * Math.cos(phi2) * Math.sin(deltaLambda / 2) ** 2
  return Math.round(2 * radius * Math.asin(Math.sqrt(h)))
}

interface PendingIncidentPhoto {
  id: string
  incidentId: string
  previewUrl: string
  file: File
  status: PhotoUploadStatus
  progress: number
  error?: string
}

function validFleetPhoto(file: File) {
  if (!isSupportedPhotoFile(file)) {
    toast.error('Please select an image file')
    return false
  }
  if (file.size > MAX_FLEET_PHOTO_BYTES) {
    toast.error('Image too large. Max 10MB')
    return false
  }
  return true
}

function Section({ title, icon, count, right, children, className }: {
  title: string; icon: React.ReactNode; count?: number; right?: React.ReactNode; children: React.ReactNode; className?: string
}) {
  return (
    <section className={'dsec' + (className ? ` ${className}` : '')}>
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
  const [historyOpen, setHistoryOpen] = useState(false)
  const [partsOpen, setPartsOpen] = useState(false)
  const { data } = useQuery<TruckDetailData>({
    queryKey: ['fleet-truck', truckId],
    queryFn: async () => (await api.get(`/fleet/trucks/${truckId}`)).data,
  })
  const incidentsQuery = useQuery<IncidentEntry[]>({
    queryKey: ['fleet-truck-incidents', truckId],
    queryFn: async () => (await api.get(`/fleet/trucks/${truckId}/incidents`)).data,
    enabled: Boolean(data),
  })
  const historyQuery = useQuery<HistoryEntry[]>({
    queryKey: ['fleet-truck-history', truckId],
    queryFn: async () => (await api.get(`/fleet/trucks/${truckId}/history`)).data,
    enabled: Boolean(data && historyOpen),
  })
  const partsQuery = useQuery<PartEntry[]>({
    queryKey: ['fleet-truck-parts', truckId],
    queryFn: async () => (await api.get(`/fleet/trucks/${truckId}/parts`)).data,
    enabled: Boolean(data && partsOpen),
  })
  const incidents = incidentsQuery.data || []
  const history = historyQuery.data || []
  const parts = partsQuery.data || []

  useEffect(() => {
    setHistoryOpen(false)
    setPartsOpen(false)
  }, [truckId])

  const nearestUnits = useMemo(() => {
    const truck = data?.truck
    if (!truck || truck.lat == null || truck.lng == null) return []

    return trucks
      .filter((candidate) => candidate.id !== truck.id && candidate.lat != null && candidate.lng != null)
      .map((candidate) => ({
        id: candidate.id,
        unit_number: candidate.display_unit_number || candidate.unit_number,
        city: candidate.location_city,
        status: candidate.status,
        miles: haversineMiles(truck.lat!, truck.lng!, candidate.lat!, candidate.lng!),
      }))
      .sort((a, b) => a.miles - b.miles)
      .slice(0, 3)
  }, [data?.truck, trucks])

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['fleet-truck', truckId] })
    qc.invalidateQueries({ queryKey: ['fleet-truck-incidents', truckId] })
    qc.invalidateQueries({ queryKey: ['fleet-truck-history', truckId] })
    qc.invalidateQueries({ queryKey: ['fleet-truck-parts', truckId] })
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
  const deleteIncidentPhoto = useMutation({
    mutationFn: async ({ incidentId, photoId }: { incidentId: string; photoId: string }) => {
      await api.delete(`/fleet/incidents/${incidentId}/photos/${photoId}`)
      return { incidentId, photoId }
    },
    onSuccess: ({ incidentId, photoId }) => {
      toast.success('Photo removed')
      qc.setQueryData<IncidentEntry[]>(['fleet-truck-incidents', truckId], (current) => {
        if (!current) return current
        return current.map((inc) => (
          inc.id === incidentId
            ? { ...inc, photos: (inc.photos || []).filter((photo) => photo.id !== photoId) }
            : inc
        ))
      })
      refresh()
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to remove photo'),
  })
  const [editing, setEditing] = useState(false)
  const [logging, setLogging] = useState(false)
  const [editingIncident, setEditingIncident] = useState<IncidentEntry | null>(null)
  const [armedDeleteIncidentId, setArmedDeleteIncidentId] = useState<string | null>(null)
  const [incidentMenuOpenId, setIncidentMenuOpenId] = useState<string | null>(null)
  const [pendingIncidentPhotos, setPendingIncidentPhotos] = useState<PendingIncidentPhoto[]>([])
  const pendingIncidentPhotosRef = useRef<PendingIncidentPhoto[]>([])
  const [newWOOpen, setNewWOOpen] = useState(false)
  const [woPanelId, setWoPanelId] = useState<string | null>(null)
  const [assigningDriver, setAssigningDriver] = useState(false)
  const [schedulePMOpen, setSchedulePMOpen] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [statusMenuOpen, setStatusMenuOpen] = useState(false)
  const setStatus = useMutation({
    mutationFn: async (value: string) => (await api.patch(`/fleet/trucks/${truckId}`, { status_override: value })).data as BoardTruck,
    onSuccess: (updated, value) => {
      // Paint the new status straight from the response so the badge and the
      // menu's checkmark move on click instead of waiting on the refetch.
      qc.setQueryData<TruckDetailData>(['fleet-truck', truckId], (current) => (
        current ? { ...current, truck: { ...current.truck, ...updated } } : current
      ))
      // An open work order outranks the manual status on the board, so say that
      // plainly rather than claiming a change the badge is not going to show.
      const label = STATUS_OPTIONS.find((opt) => opt.value === value)?.label
      if (updated.status_override && updated.status !== updated.status_override) {
        toast.success(`Saved — the board shows "${STATUS_META[updated.status].label}" until the open work order closes`)
      } else {
        toast.success(value === 'auto' ? 'Manual status cleared' : `Status set to ${label}`)
      }
      setStatusMenuOpen(false)
      refresh()
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to set status'),
  })

  useEffect(() => {
    pendingIncidentPhotosRef.current = pendingIncidentPhotos
  }, [pendingIncidentPhotos])

  useEffect(() => () => {
    pendingIncidentPhotosRef.current.forEach((photo) => URL.revokeObjectURL(photo.previewUrl))
  }, [])

  const pendingIncidentUploadCount = pendingIncidentPhotos.filter((photo) => !['done', 'error'].includes(photo.status)).length

  const updatePendingIncidentPhoto = (id: string, patch: Partial<PendingIncidentPhoto>) => {
    setPendingIncidentPhotos((photos) => photos.map((photo) => photo.id === id ? { ...photo, ...patch } : photo))
  }

  const uploadIncidentPhotos = async (items: PendingIncidentPhoto[]) => {
    let uploadedCount = 0
    await runPhotoUploadQueue(items, async (item) => {
      try {
        const photo = await uploadDirectPhoto<FleetPhoto>({
          file: item.file,
          signEndpoint: `/fleet/incidents/${item.incidentId}/photos/direct-upload-signature`,
          recordEndpoint: `/fleet/incidents/${item.incidentId}/photos/direct`,
          fallbackEndpoint: `/fleet/incidents/${item.incidentId}/photos`,
          onProgress: (progress) => updatePendingIncidentPhoto(item.id, progress),
        })
        uploadedCount += 1
        qc.setQueryData<IncidentEntry[]>(['fleet-truck-incidents', truckId], (current) => {
          if (!current) return current
          return current.map((inc) => (
            inc.id === item.incidentId
              ? { ...inc, photos: [photo, ...(inc.photos || [])] }
              : inc
          ))
        })
        setPendingIncidentPhotos((photos) => photos.filter((photo) => photo.id !== item.id))
        URL.revokeObjectURL(item.previewUrl)
      } catch (error: any) {
        updatePendingIncidentPhoto(item.id, {
          status: 'error',
          error: error.response?.data?.detail || error.message || 'Failed',
        })
      }
    })
    if (uploadedCount > 0) {
      toast.success(`${uploadedCount} photo${uploadedCount === 1 ? '' : 's'} uploaded`)
      refresh()
    }
  }

  const t = data?.truck || trucks.find((truck) => truck.id === truckId)
  if (!t) return <div className="loader"><Spinner size="md" /></div>

  const meta = STATUS_META[t.status]
  // An open work order outranks the manual status, so surface the saved choice
  // instead of leaving the badge silently contradicting the "saved" toast.
  const suppressedOverride = t.status_override && t.status !== t.status_override
    ? STATUS_META[t.status_override as keyof typeof STATUS_META]
    : null
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
              <h1 className="dhead-unit">{fleetUnitLabel(t)}</h1>
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
              {suppressedOverride && (
                <span
                  className="dbadge"
                  style={{ ['--st' as any]: suppressedOverride.dot, opacity: 0.75, fontSize: 11.5 }}
                  title="Manual status saved — it takes over once the open work order closes"
                >
                  <i />{suppressedOverride.label} after WO
                </span>
              )}
              <button
                className="dbtn dbtn-ghost dhead-details"
                onClick={() => setDetailsOpen(true)}
                title="Details"
                disabled={!data}
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

      {data ? (
      <div className="dcol detail-flow">
          <section className="detail-workflow" aria-labelledby="operate-now-heading">
            <div className="detail-group-head">
              <div>
                <h2 id="operate-now-heading">Operate now</h2>
                <p>Resolve active work, road incidents, and required inspections.</p>
              </div>
              <button className="dbtn dbtn-ghost dsec-action" style={{ height: 34 }} onClick={() => setLogging(true)} title="Log incident">
                <Plus size={14} /> <span className="dbtn-label">Log incident</span>
              </button>
            </div>
            <div className="detail-operation-stack">
              <InspectionsSection vehicleId={t.id} truckId={t.id} currentOdometer={t.odometer} className="dsec-operation dsec-inspections" />

          {(incidentsQuery.isLoading || incidentsQuery.isError || incidents.length > 0) && <Section
            title="Incidents on the road"
            icon={<AlertTriangle size={17} />}
            count={data.incidents_count}
            className="dsec-operation dsec-incidents"
          >
            {incidentsQuery.isLoading ? (
              <div className="empty-note"><Spinner size="xs" /> Loading recent incidents...</div>
            ) : incidents.length ? (
              <div className="inc-list">
                {incidents.map((inc) => {
                  const pendingPhotos = pendingIncidentPhotos.filter((photo) => photo.incidentId === inc.id)
                  const visiblePhotos = (inc.photos || []).slice(0, Math.max(0, 4 - pendingPhotos.length))
                  const hiddenPhotoCount = Math.max(0, (inc.photos?.length || 0) - visiblePhotos.length)
                  return (
                  <div key={inc.id} className={'inc ' + sevClass[inc.severity]}>
                    <div className="inc-sev" />
                    <div className="inc-body">
                      <div className="inc-row1"><b>{inc.type}</b><span className="inc-date">{fmtDate(inc.date)}</span></div>
                      {inc.location && <div className="inc-loc"><MapIcon size={12} /> {inc.location}</div>}
                      <div className="inc-note">{inc.note}</div>
                      {(pendingPhotos.length > 0 || !!inc.photos?.length) && (
                        <div style={{ display: 'flex', gap: 7, marginTop: 10, flexWrap: 'wrap' }}>
                          {pendingPhotos.map((photo) => (
                            <div key={photo.id} style={{ position: 'relative', width: 54, height: 54, borderRadius: 9, overflow: 'hidden', border: '1px solid var(--line)', background: 'var(--surface-2)' }}>
                              <img src={photo.previewUrl} alt="Incident upload pending" style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.45, filter: 'saturate(.6)' }} />
                              <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', gap: 3, padding: 4, background: 'rgba(0,0,0,.34)' }}>
                                <span style={{ fontSize: 9, fontWeight: 700, color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                  {photo.status === 'error' ? (photo.error || 'Failed') : `${photo.progress}%`}
                                </span>
                                <span style={{ height: 4, borderRadius: 999, overflow: 'hidden', background: 'rgba(255,255,255,.28)' }}>
                                  <span style={{ display: 'block', height: '100%', width: `${Math.max(6, photo.progress)}%`, background: photo.status === 'error' ? 'var(--red)' : 'var(--st-active)' }} />
                                </span>
                              </div>
                            </div>
                          ))}
                          {visiblePhotos.map((photo) => (
                            <div key={photo.id} style={{ position: 'relative', width: 54, height: 54 }}>
                              <a href={photo.image_url} target="_blank" rel="noreferrer" title="Open photo">
                                <img src={photo.image_url} alt="Incident" style={{ width: 54, height: 54, objectFit: 'cover', borderRadius: 9, border: '1px solid var(--line)' }} />
                              </a>
                              <button
                                type="button"
                                aria-label="Remove incident photo"
                                title="Remove photo"
                                disabled={deleteIncidentPhoto.isPending}
                                onClick={() => deleteIncidentPhoto.mutate({ incidentId: inc.id, photoId: photo.id })}
                                style={{
                                  position: 'absolute',
                                  top: -6,
                                  right: -6,
                                  width: 22,
                                  height: 22,
                                  display: 'grid',
                                  placeItems: 'center',
                                  borderRadius: 999,
                                  border: '1px solid rgba(248,113,113,.55)',
                                  background: 'rgba(15,17,21,.94)',
                                  color: 'var(--red)',
                                  boxShadow: '0 6px 14px rgba(0,0,0,.35)',
                                }}
                              >
                                {deleteIncidentPhoto.isPending ? <Spinner size="xs" /> : <Trash2 size={12} />}
                              </button>
                            </div>
                          ))}
                          {hiddenPhotoCount > 0 && <span className="dsec-count">+{hiddenPhotoCount}</span>}
                        </div>
                      )}
                      <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8, marginTop: 9 }}>
                        {inc.repair_order_id ? (
                          <span style={incidentStatePillStyle}>
                            <Wrench size={12} /> Repair linked
                          </span>
                        ) : null}
                        {inc.status === 'resolved' && (
                          <span style={incidentStatePillStyle}>
                            <CheckCircle2 size={12} /> Resolved
                          </span>
                        )}
                        <div style={{ position: 'relative', marginLeft: 'auto' }}>
                          <button
                            className="dbtn dbtn-ghost"
                            style={{ height: 38, width: 46, padding: 0, justifyContent: 'center' }}
                            onClick={() => {
                              setArmedDeleteIncidentId(null)
                              setIncidentMenuOpenId((openId) => openId === inc.id ? null : inc.id)
                            }}
                            aria-label="Incident actions"
                            aria-expanded={incidentMenuOpenId === inc.id}
                            title="Actions"
                          >
                            <MoreHorizontal size={19} />
                          </button>
                          {incidentMenuOpenId === inc.id && (
                            <>
                              <div onClick={() => { setIncidentMenuOpenId(null); setArmedDeleteIncidentId(null) }} style={{ position: 'fixed', inset: 0, zIndex: 40 }} />
                              <div style={{ position: 'absolute', top: 'calc(100% + 6px)', right: 0, zIndex: 41, minWidth: 190, padding: 6, background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 10, boxShadow: '0 10px 28px rgba(0,0,0,.45)' }}>
                                <button
                                  style={incidentMenuItemStyle}
                                  onClick={() => {
                                    setEditingIncident(inc)
                                    setIncidentMenuOpenId(null)
                                  }}
                                >
                                  <Pencil size={13} /> Edit
                                </button>
                                <label style={{ ...incidentMenuItemStyle, cursor: pendingIncidentUploadCount > 0 ? 'not-allowed' : 'pointer' }}>
                                  {pendingIncidentUploadCount > 0 ? <Spinner size="xs" /> : <Camera size={13} />} Upload photo
                                  <input
                                    type="file"
                                    accept="image/*"
                                    multiple
                                    disabled={pendingIncidentUploadCount > 0}
                                    style={{ display: 'none' }}
                                    onChange={(e) => {
                                      const files = Array.from(e.target.files || [])
                                      e.target.value = ''
                                      const validFiles = files.filter(validFleetPhoto)
                                      const pendingPhotos = validFiles.map((file, index) => {
                                        const previewUrl = URL.createObjectURL(file)
                                        const pendingId = `${inc.id}-${Date.now()}-${index}`
                                        return { id: pendingId, incidentId: inc.id, file, previewUrl, status: 'queued' as PhotoUploadStatus, progress: 0 }
                                      })
                                      if (pendingPhotos.length > 0) {
                                        setPendingIncidentPhotos((photos) => [...photos, ...pendingPhotos])
                                        setIncidentMenuOpenId(null)
                                        void uploadIncidentPhotos(pendingPhotos)
                                      }
                                    }}
                                  />
                                </label>
                                {!inc.repair_order_id && (
                                  <button
                                    style={incidentMenuItemStyle}
                                    onClick={() => {
                                      repairFromIncident.mutate(inc.id)
                                      setIncidentMenuOpenId(null)
                                    }}
                                    disabled={repairFromIncident.isPending}
                                  >
                                    <Wrench size={13} /> Create repair
                                  </button>
                                )}
                                {inc.status !== 'resolved' && (
                                  <button
                                    style={incidentMenuItemStyle}
                                    onClick={() => {
                                      resolveIncident.mutate(inc.id)
                                      setIncidentMenuOpenId(null)
                                    }}
                                    disabled={resolveIncident.isPending}
                                  >
                                    <CheckCircle2 size={13} /> Resolve
                                  </button>
                                )}
                                {!inc.repair_order_id && (
                                  armedDeleteIncidentId === inc.id ? (
                                    <div style={{ padding: '7px 8px 4px' }}>
                                      <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 7 }}>Delete this incident?</div>
                                      <div style={{ display: 'flex', gap: 6 }}>
                                        <button className="dbtn dbtn-ghost" style={{ height: 30, flex: 1, fontSize: 12 }}
                                          disabled={deleteIncident.isPending} onClick={() => setArmedDeleteIncidentId(null)}>
                                          Cancel
                                        </button>
                                        <button className="dbtn dbtn-ghost" style={{ height: 30, flex: 1, fontSize: 12, color: 'var(--red)' }}
                                          disabled={deleteIncident.isPending}
                                          onClick={() => deleteIncident.mutate(inc.id, { onSuccess: () => { setArmedDeleteIncidentId(null); setIncidentMenuOpenId(null) } })}>
                                          {deleteIncident.isPending ? <Spinner size="xs" /> : <Trash2 size={12} />} Delete
                                        </button>
                                      </div>
                                    </div>
                                  ) : (
                                    <button
                                      style={{ ...incidentMenuItemStyle, color: 'var(--red)' }}
                                      onClick={() => setArmedDeleteIncidentId(inc.id)}
                                    >
                                      <Trash2 size={13} /> Delete
                                    </button>
                                  )
                                )}
                              </div>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                  )
                })}
              </div>
            ) : incidentsQuery.isError ? (
              <div className="empty-note"><AlertTriangle size={16} /> Incident records could not be loaded.</div>
            ) : (
              <div className="empty-note"><Shield size={16} /> No incidents recorded for this unit.</div>
            )}
          </Section>}

          {data.open_work_orders.length > 0 && <Section title="Open work orders" icon={<ClipboardList size={17} />} count={data.open_work_orders.length} className="dsec-operation dsec-work-orders">
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
          </Section>}
            </div>
          </section>

          <section className="dsec dsec-record" aria-labelledby="service-record-heading">
            <div className="dsec-head">
              <div className="dsec-title"><History size={17} /><h3 id="service-record-heading">Service record</h3></div>
            </div>
            <div className="record-disclosures">
              <div className={'record-disclosure' + (historyOpen ? ' is-open' : '')}>
                <button className="record-disclosure-trigger" onClick={() => setHistoryOpen((open) => !open)} aria-expanded={historyOpen}>
                  <span className="record-disclosure-icon"><History size={17} /></span>
                  <span className="record-disclosure-copy"><b>Service history</b><small>Completed maintenance and repair timeline</small></span>
                  {historyQuery.data?.length != null && <span className="record-disclosure-count">{historyQuery.data.length}</span>}
                  <ChevronDown size={17} />
                </button>
                {historyOpen && (
                  <div className="record-disclosure-content">
                    {historyQuery.isLoading ? <div className="empty-note"><Spinner size="xs" /> Loading service history...</div>
                      : history.length === 0 ? <div className="empty-note"><History size={16} /> No service history yet.</div>
                      : <div className="timeline">
                        {history.map((h) => (
                          <div key={h.id} className={'tl-item tl-' + h.kind.toLowerCase()}>
                            <div className="tl-marker" />
                            <div className="tl-body">
                              <div className="tl-row1"><span className={'tl-kind tl-kind-' + h.kind.toLowerCase()}>{h.kind}</span><span className="tl-date">{fmtDate(h.date)}</span><span className="tl-odo">{fmt(h.odometer)} mi</span></div>
                              <div className="tl-summary">{h.summary || '—'}</div>
                              <div className="tl-meta"><span><User size={12} /> {h.mechanic || 'Unassigned'}</span>{h.cost != null && <span className="tl-cost">{money(h.cost)}</span>}</div>
                            </div>
                          </div>
                        ))}
                      </div>}
                  </div>
                )}
              </div>
              <div className={'record-disclosure' + (partsOpen ? ' is-open' : '')}>
                <button className="record-disclosure-trigger" onClick={() => setPartsOpen((open) => !open)} aria-expanded={partsOpen}>
                  <span className="record-disclosure-icon"><Box size={17} /></span>
                  <span className="record-disclosure-copy"><b>Parts & warranty</b><small>Installed parts and active coverage</small></span>
                  {partsQuery.data?.length != null && <span className="record-disclosure-count">{partsQuery.data.length}</span>}
                  <ChevronDown size={17} />
                </button>
                {partsOpen && (
                  <div className="record-disclosure-content">
                    {partsQuery.isLoading ? <div className="empty-note"><Spinner size="xs" /> Loading parts and warranty...</div>
                      : parts.length === 0 ? <div className="empty-note"><Box size={16} /> No parts on record.</div>
                      : <div className="parts">{parts.map((p) => (
                        <div key={p.id} className="part">
                          <div><div className="part-name">{p.name}</div><div className="part-meta">{fmtDate(p.date)} · {fmt(p.odometer)} mi</div></div>
                          <span className={'part-w ' + (p.active ? 'w-on' : 'w-off')}>{p.active ? 'Warranty to ' + fmtDate(p.warranty_until) : (p.warranty_until ? 'Expired' : 'No warranty')}</span>
                        </div>
                      ))}</div>}
                  </div>
                )}
              </div>
            </div>
          </section>

          <Section
            title="Current location & nearby units"
            className="dsec-context"
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
            {nearestUnits.length === 0 && <div className="empty-note">No located units nearby.</div>}
            {nearestUnits.map((n) => (
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
      ) : (
        <div className="loader flex-col gap-3 text-sm text-slate-500">
          <Spinner size="md" />
          <span>Loading truck activity...</span>
        </div>
      )}

      {data && detailsOpen && <TruckDetailsModal truck={t} detail={data} onChangeDriver={() => setAssigningDriver(true)} onEdit={() => { setDetailsOpen(false); setEditing(true) }} onClose={() => setDetailsOpen(false)} />}
      {data && editing && <TruckEditModal truck={t} detail={data} onClose={() => setEditing(false)} />}
      {schedulePMOpen && <SchedulePMModal truck={t} onClose={() => setSchedulePMOpen(false)} onDone={refresh} />}
      {assigningDriver && <AssignDriverModal truck={t} driverPhone={t.driver_phone} onClose={() => setAssigningDriver(false)} />}
      {logging && <LogIncidentModal vehicleId={t.id} truckId={t.id} onClose={() => setLogging(false)} />}
      {editingIncident && <EditIncidentModal incident={editingIncident} truckId={t.id} onClose={() => setEditingIncident(null)} />}
      {newWOOpen && <NewWorkOrderModal truckId={t.id} unitNumber={fleetUnitLabel(t)} onClose={() => setNewWOOpen(false)} onCreated={refresh} />}
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

/* The detail view is the source of truth for the truck's relationships and
   service context. Editing deliberately starts from here, not from the board. */
function TruckDetailsModal({ truck, detail, onChangeDriver, onEdit, onClose }: {
  truck: BoardTruck; detail: TruckDetailData; onChangeDriver: () => void; onEdit: () => void; onClose: () => void
}) {
  return (
    <Modal title={`Details · ${fleetUnitLabel(truck)}`} icon={<Truck size={17} />} onClose={onClose} width={520}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 8 }}>
        <div className="dmap-side-h" style={{ margin: 0 }}>Identity</div>
        <button className="dbtn dbtn-ghost" style={{ height: 34, padding: '0 12px', fontSize: 12.5 }} onClick={onEdit}>
          <Pencil size={14} /> Edit truck
        </button>
      </div>
      <div className="id-grid">
        <Stat label="VIN" value={truck.vin || '—'} mono />
        <Stat label="Plate" value={truck.plate || '—'} mono />
        <Stat label="Year" value={truck.year ?? '—'} mono />
        <Stat label="Body type" value={truck.body_type || '—'} />
        <Stat label="Make" value={truck.make} />
        <Stat label="Model" value={truck.model} />
        <Stat label="Truck owner / lessor" value={truck.owner_company_name || truck.fleet_company_name || '—'} />
        <Stat label="Operating authority" value={truck.fleet_company_name || '—'} />
        <Stat label="Default invoice recipient" value={detail.bill_to_company_name || detail.bill_to_contact_name || '—'} />
        <Stat
          label="Pricing for new work"
          value={detail.bill_to_is_internal
            ? `Internal · parts at garage cost · labor at ${detail.bill_labor_at_customer_rate ? 'customer rate' : 'garage cost'}`
            : 'Standard customer pricing'}
        />
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
          <div className="person-role">{detail.driver_phone ? formatUSPhone(detail.driver_phone) : 'Assigned driver'}</div>
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
      {detail.crew.filter((member) => member !== truck.assigned_mechanic).slice(0, 3).map((member) => (
        <div key={member} className="person person-sm">
          <div className="avatar avatar-sm">{initials(member)}</div>
          <div>
            <div className="person-name">{member}</div>
            <div className="person-role">Worked on this truck</div>
          </div>
        </div>
      ))}
    </Modal>
  )
}
