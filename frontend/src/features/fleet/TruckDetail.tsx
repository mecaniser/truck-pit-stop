import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { Spinner } from '@/components/ui'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { AxiosError } from 'axios'
import toast from 'react-hot-toast'
import {
  Gauge, Calendar, Wrench, AlertTriangle, History, Truck, User, Box, Map as MapIcon,
  Shield, Phone, ClipboardList, ClipboardCheck, Pencil, CheckCircle2, ChevronDown, Check, Info, Trash2, Camera, MoreHorizontal,
  Archive, ArrowLeft, ArrowRight, Combine, RotateCcw,
} from 'lucide-react'
import api from '../../lib/api'
import { isSupportedPhotoFile, runPhotoUploadQueue, uploadDirectPhoto, type PhotoUploadStatus } from '@/lib/photoUpload'
import type {
  BoardTruck, TruckDetail as TruckDetailData, IncidentSeverity, IncidentEntry, FleetPhoto, HistoryEntry, PartEntry, Inspection,
  VehicleMergePreview, VehicleMergeResult, VehicleMergeSummary,
} from './types'
import { STATUS_META, fleetUnitLabel, fmt, money, fmtDate, pmState, initials } from './helpers'
import { formatUSPhone } from '@/utils/phone'
import FleetMap from './FleetMap'
import { TruckEditModal, LogIncidentModal, EditIncidentModal, InspectionsSection, NewWorkOrderModal, WorkOrderPanel, AssignDriverModal, SchedulePMModal, Modal, SidekickPanel, invalidateFleetAndCockpit, type InspectionsSectionHandle } from './FleetModals'
import { useAuthStore } from '../../stores/authStore'

const sevClass: Record<IncidentSeverity, string> = {
  critical: 'inc-high', high: 'inc-high', medium: 'inc-med', low: 'inc-low',
}

// Manual idle-status options. 'auto' clears the override (back to derived).
const STATUS_OPTIONS: { value: string; label: string; dot: string }[] = [
  { value: 'auto', label: 'Automatic — based on truck activity', dot: '#22c55e' },
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

function looksLikePreventiveMaintenance(entry: HistoryEntry) {
  return entry.kind === 'Repair' && /\bpm\b|preventive maintenance/i.test(entry.summary || '')
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

function QueryFailure({ title, detail, onRetry, retrying = false, compact = false }: {
  title: string
  detail: string
  onRetry: () => void
  retrying?: boolean
  compact?: boolean
}) {
  return (
    <div className={'query-failure' + (compact ? ' query-failure--compact' : '')} role="alert">
      <AlertTriangle size={18} aria-hidden="true" />
      <div className="query-failure-copy">
        <strong>{title}</strong>
        <span>{detail}</span>
      </div>
      <button type="button" className="query-retry" onClick={onRetry} disabled={retrying}>
        {retrying ? <Spinner size="xs" /> : <RotateCcw size={14} />}
        {retrying ? 'Retrying…' : 'Try again'}
      </button>
    </div>
  )
}

function truckLoadFailureDetail(error: unknown) {
  const status = (error as AxiosError)?.response?.status
  if (status === 401) return 'Your session is no longer active. Sign in again, then reopen this truck.'
  if (status === 403) return 'Your account does not have permission to view this truck’s activity.'
  if (status === 404) return 'This truck is no longer available. Return to the Fleet Board and choose another unit.'
  if (status === 429) return 'The server is receiving too many requests. Wait a moment, then try again.'
  return 'The truck record could not be reached. Check the connection and try again.'
}

export default function TruckDetail({
  truckId, trucks, onOpen,
}: { truckId: string; trucks: BoardTruck[]; onOpen: (id: string) => void }) {
  const qc = useQueryClient()
  const { user } = useAuthStore()
  const [historyOpen, setHistoryOpen] = useState(false)
  const [recognizingPm, setRecognizingPm] = useState<HistoryEntry | null>(null)
  const [partsOpen, setPartsOpen] = useState(false)
  const [locationOpen, setLocationOpen] = useState(false)
  const truckQuery = useQuery<TruckDetailData>({
    queryKey: ['fleet-truck', truckId],
    queryFn: async () => (await api.get(`/fleet/trucks/${truckId}`)).data,
  })
  const { data } = truckQuery
  const incidentsQuery = useQuery<IncidentEntry[]>({
    queryKey: ['fleet-truck-incidents', truckId],
    queryFn: async () => (await api.get(`/fleet/trucks/${truckId}/incidents`)).data,
    enabled: Boolean(data),
  })
  const inspectionsQuery = useQuery<Inspection[]>({
    queryKey: ['fleet-inspections', truckId],
    queryFn: async () => (await api.get('/fleet/inspections', { params: { vehicle_id: truckId } })).data,
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
    setLocationOpen(false)
    setRecognizingPm(null)
    setStatusMenuOpen(false)
  }, [truckId])

  const nearestUnits = useMemo(() => {
    const truck = data?.truck
    if (!locationOpen || !truck || truck.lat == null || truck.lng == null) return []

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
  }, [data?.truck, locationOpen, trucks])

  const mapTrucks = useMemo(() => {
    if (!locationOpen) return []
    const truck = data?.truck
    if (!truck || trucks.some((candidate) => candidate.id === truck.id)) return trucks
    return [...trucks, truck]
  }, [data?.truck, locationOpen, trucks])

  const handleMapSelect = useCallback((truck: BoardTruck) => {
    if (truck.id !== truckId) onOpen(truck.id)
  }, [onOpen, truckId])

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
  const [mergeOpen, setMergeOpen] = useState(false)
  const [statusMenuOpen, setStatusMenuOpen] = useState(false)
  const [yardToolsHelpOpen, setYardToolsHelpOpen] = useState(false)
  const statusTriggerRef = useRef<HTMLButtonElement>(null)
  const statusMenuRef = useRef<HTMLDivElement>(null)
  const statusMenuId = useId()
  const yardToolsHelpId = useId()
  const inspectionsRef = useRef<InspectionsSectionHandle>(null)
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
        toast.success(`Saved. The board will show “${STATUS_META[updated.status].label}” until the open repair order closes.`)
      } else {
        toast.success(value === 'auto' ? 'Status now follows truck activity' : `Truck status set to ${label}`)
      }
      setStatusMenuOpen(false)
      requestAnimationFrame(() => statusTriggerRef.current?.focus())
      refresh()
    },
    onError: (error: AxiosError<{ detail?: string }>) => toast.error(error.response?.data?.detail || 'Truck status could not be changed. Try again.'),
  })

  useEffect(() => {
    if (!statusMenuOpen) return
    const items = statusMenuRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]')
    const current = Array.from(items || []).find((item) => item.getAttribute('aria-checked') === 'true')
    requestAnimationFrame(() => (current || items?.[0])?.focus())
  }, [statusMenuOpen])

  const closeStatusMenu = (restoreFocus = false) => {
    setStatusMenuOpen(false)
    if (restoreFocus) requestAnimationFrame(() => statusTriggerRef.current?.focus())
  }

  const handleStatusMenuKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const items = Array.from(statusMenuRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]') || [])
      .filter((item) => !item.disabled)
    if (!items.length) return
    const currentIndex = Math.max(0, items.indexOf(document.activeElement as HTMLButtonElement))
    if (event.key === 'Escape') {
      event.preventDefault()
      closeStatusMenu(true)
      return
    }
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const nextIndex = event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? items.length - 1
        : event.key === 'ArrowDown'
          ? (currentIndex + 1) % items.length
          : (currentIndex - 1 + items.length) % items.length
    items[nextIndex]?.focus()
  }

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
  if (!t) {
    if (truckQuery.isError) {
      return (
        <QueryFailure
          title="Truck details are unavailable"
          detail={truckLoadFailureDetail(truckQuery.error)}
          onRetry={() => { void truckQuery.refetch() }}
          retrying={truckQuery.isFetching}
        />
      )
    }
    return <div className="loader" role="status"><Spinner size="md" /> Loading truck details…</div>
  }

  const meta = STATUS_META[t.status]
  // An open work order outranks the manual status, so surface the saved choice
  // instead of leaving the badge silently contradicting the "saved" toast.
  const suppressedOverride = t.status_override && t.status !== t.status_override
    ? STATUS_META[t.status_override as keyof typeof STATUS_META]
    : null
  const pm = pmState(t)
  const pmDisplayClass = t.pm_remaining == null && t.pm_days_remaining == null ? 'pm-none' : pm.cls
  const inspections = inspectionsQuery.data || []
  const scheduledInspection = inspections.find((inspection) => inspection.status === 'scheduled')
  const failedInspection = inspections.find((inspection) => (
    inspection.status === 'completed' && inspection.result === 'fail' && !inspection.repair_order_id
  ))
  const unresolvedIncidents = incidents.filter((incident) => incident.status !== 'resolved')
  const safetyIncident = unresolvedIncidents.find((incident) => incident.severity === 'critical' || incident.severity === 'high')
  const primaryWorkOrder = data?.open_work_orders[0]
  const hasSafetyIssue = t.status === 'out_of_service' || Boolean(t.warning_lights?.length) || Boolean(safetyIncident) || Boolean(failedInspection)
  const pmNeedsAttention = (
    (t.pm_remaining != null && t.pm_remaining <= 2500)
    || (t.pm_days_remaining != null && t.pm_days_remaining <= 14)
  )

  const nextAction = (() => {
    if (hasSafetyIssue && primaryWorkOrder) {
      return {
        kind: 'repair',
        label: primaryWorkOrder.status === 'Draft' ? 'Continue safety repair draft' : 'Continue safety repair',
        reason: 'This truck has a safety condition and repair work is already open.',
        icon: <Wrench size={20} />,
        onClick: () => setWoPanelId(primaryWorkOrder.repair_order_id),
        tone: 'danger',
      }
    }
    if (hasSafetyIssue) {
      return {
        kind: failedInspection ? 'inspection' : 'repair',
        label: failedInspection ? 'Review failed inspection' : 'Add safety repair work',
        reason: failedInspection
          ? 'A failed inspection needs a repair decision before this truck returns to service.'
          : 'A warning or road incident needs attention before normal operation.',
        icon: <AlertTriangle size={20} />,
        onClick: failedInspection
          ? () => inspectionsRef.current?.open(failedInspection.id)
          : () => setNewWOOpen(true),
        tone: 'danger',
      }
    }
    if (primaryWorkOrder) {
      return {
        kind: 'repair',
        label: primaryWorkOrder.status === 'Draft' ? 'Continue repair draft' : `Open ${primaryWorkOrder.status.toLowerCase()}`,
        reason: `${primaryWorkOrder.id} is the current repair order for this truck.`,
        icon: <ClipboardList size={20} />,
        onClick: () => setWoPanelId(primaryWorkOrder.repair_order_id),
        tone: 'work',
      }
    }
    if (scheduledInspection) {
      return {
        kind: 'inspection',
        label: 'Open scheduled inspection',
        reason: `The inspection scheduled for ${fmtDate(scheduledInspection.scheduled_for)} is ready to complete.`,
        icon: <ClipboardCheck size={20} />,
        onClick: () => inspectionsRef.current?.open(scheduledInspection.id),
        tone: 'inspection',
      }
    }
    if (pmNeedsAttention) {
      return {
        kind: 'pm',
        label: t.pm_due_date ? 'Review scheduled PM' : 'Schedule PM',
        reason: pm.label,
        icon: <Calendar size={20} />,
        onClick: () => setSchedulePMOpen(true),
        tone: 'maintenance',
      }
    }
    return {
      kind: 'inspection',
      label: 'Start yard inspection',
      reason: 'Walk this truck and record its condition before it returns to service.',
      icon: <ClipboardCheck size={20} />,
      onClick: () => inspectionsRef.current?.start(),
      tone: 'inspection',
    }
  })()
  const detailOverlayOpen = Boolean(
    editing
    || logging
    || editingIncident
    || newWOOpen
    || woPanelId
    || assigningDriver
    || schedulePMOpen
    || detailsOpen
    || mergeOpen
    || recognizingPm
  )
  return (
    <div className="detail">
      <div className="dhead">
        <div className="dhead-main">
          <div>
            <div className="dhead-unit-row">
              <div style={{ position: 'relative' }}>
                <button
                  ref={statusTriggerRef}
                  type="button"
                  className="dbadge"
                  style={{ ['--st' as any]: meta.dot, cursor: 'pointer', border: 'none', font: 'inherit' }}
                  onClick={() => setStatusMenuOpen((o) => !o)}
                  title="Change status"
                  aria-label={`Change truck status. Current status: ${meta.label}`}
                  aria-haspopup="menu"
                  aria-expanded={statusMenuOpen}
                  aria-controls={statusMenuOpen ? statusMenuId : undefined}
                >
                  <i className={t.moving ? 'is-moving' : ''} />{meta.label}
                  <ChevronDown size={12} style={{ marginLeft: 5, opacity: 0.7 }} />
                </button>
                {statusMenuOpen && (
                  <>
                    <div aria-hidden="true" onClick={() => closeStatusMenu()} style={{ position: 'fixed', inset: 0, zIndex: 40 }} />
                    <div
                      ref={statusMenuRef}
                      id={statusMenuId}
                      role="menu"
                      className="status-menu"
                      aria-label="Set truck status"
                      aria-busy={setStatus.isPending || undefined}
                      onKeyDown={handleStatusMenuKeyDown}
                      style={{ position: 'absolute', top: 'calc(100% + 6px)', left: 0, zIndex: 41, background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 10, padding: 6, minWidth: 230, boxShadow: '0 10px 28px rgba(0,0,0,.45)' }}
                    >
                      {t.open_work_order_count > 0 && (
                        <div className="id-k" style={{ textTransform: 'none', letterSpacing: 0, padding: '4px 8px 6px', color: 'var(--muted-2)' }}>
                          A repair order is open, so the board shows that until it is completed. This choice applies afterward.
                        </div>
                      )}
                      {STATUS_OPTIONS.map((opt) => {
                        const current = (t.status_override || 'auto') === opt.value
                        return (
                          <button
                            key={opt.value}
                            type="button"
                            role="menuitemradio"
                            className="status-menu-item"
                            aria-checked={current}
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
                  title="Manual status saved — it takes over once the open repair order closes"
                >
                  <i />Next: {suppressedOverride.label}
                </span>
              )}
              <button
                className="dbtn dbtn-ghost dhead-details"
                onClick={() => setDetailsOpen(true)}
                title="Truck details"
                aria-label="Open truck details"
                disabled={!data}
              >
                <Info size={14} /> <span className="dbtn-label">Truck details</span>
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
              <span className={'dhead-stat-note ' + pmDisplayClass}>{pm.label}</span>
            </div>
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
      <>
        <div className="dcol detail-flow">
          <section className={`next-action next-action--${nextAction.tone}`} aria-labelledby="next-action-heading">
            <div className="next-action-copy">
              <span className="next-action-icon" aria-hidden="true">{nextAction.icon}</span>
              <div>
                <h2 id="next-action-heading">{nextAction.label}</h2>
                <p>{nextAction.reason}</p>
              </div>
            </div>
            <button className="next-action-button" onClick={nextAction.onClick}>
              {nextAction.label}<ArrowRight size={18} />
            </button>
          </section>

          <section className="yard-tools" aria-label="Yard tools">
            <div className="yard-tool-actions">
              <button className="yard-tool" onClick={() => scheduledInspection
                ? inspectionsRef.current?.open(scheduledInspection.id)
                : inspectionsRef.current?.start()}>
                <ClipboardCheck size={17} />
                <span>{scheduledInspection ? 'Open scheduled inspection' : 'Start inspection'}</span>
              </button>
              <button className="yard-tool" onClick={() => primaryWorkOrder
                ? setWoPanelId(primaryWorkOrder.repair_order_id)
                : setNewWOOpen(true)}>
                <Wrench size={17} />
                <span>{primaryWorkOrder ? 'Continue repair order' : 'Create repair order'}</span>
              </button>
              <button className="yard-tool" onClick={() => setLogging(true)}>
                <AlertTriangle size={17} />
                <span>Report road incident</span>
              </button>
              <button
                className={'yard-tool yard-tool-pm' + (pmNeedsAttention ? ' is-attention' : '')}
                onClick={() => setSchedulePMOpen(true)}
              >
                <Calendar size={17} />
                <span>{t.pm_due_date ? 'Review scheduled PM' : 'Schedule PM'}</span>
              </button>
            </div>
            <div
              className="yard-tools-help"
              data-open={yardToolsHelpOpen || undefined}
              onBlur={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget)) setYardToolsHelpOpen(false)
              }}
            >
              <button
                type="button"
                className="yard-tools-help-button"
                aria-label="About yard tools"
                aria-describedby={yardToolsHelpId}
                aria-expanded={yardToolsHelpOpen}
                onClick={() => setYardToolsHelpOpen((open) => !open)}
              >
                <Info size={17} />
              </button>
              <div id={yardToolsHelpId} className="yard-tools-tooltip" role="tooltip">
                <strong>Yard tools</strong>
                <span>Inspect the truck, create or continue repair work, or report a road incident while you are at the unit.</span>
              </div>
            </div>
          </section>

          <section className="detail-workflow" aria-labelledby="attention-heading">
            <div className="detail-group-head">
              <div>
                <h2 id="attention-heading">Needs attention today</h2>
                <p>Open and unresolved work, ordered by what can be acted on now.</p>
              </div>
            </div>
            <div className="detail-operation-stack">
          {data.open_work_orders.length > 0 && <Section title="Open repair orders" icon={<ClipboardList size={17} />} count={data.open_work_orders.length} className="dsec-operation dsec-work-orders">
              <div className="list-rows">
                {data.open_work_orders.map((wo) => (
                  <button key={wo.repair_order_id} className="lrow lrow-action" onClick={() => setWoPanelId(wo.repair_order_id)}>
                    <span className="lrow-mono">{wo.id}</span>
                    <span className="lrow-tx">{wo.summary || 'No complaint recorded'}</span>
                    <span className="lrow-r">
                      <span className="lrow-action-label">{wo.status === 'Draft' ? 'Continue draft' : `Open ${wo.status.toLowerCase()}`}</span>
                      <ArrowRight size={16} />
                    </span>
                  </button>
                ))}
              </div>
          </Section>}

          {(incidentsQuery.isLoading || incidentsQuery.isError || unresolvedIncidents.length > 0) && <Section
            title="Unresolved road incidents"
            icon={<AlertTriangle size={17} />}
            count={unresolvedIncidents.length}
            className="dsec-operation dsec-incidents"
          >
            {incidentsQuery.isLoading ? (
              <div className="empty-note"><Spinner size="xs" /> Loading road incidents…</div>
            ) : unresolvedIncidents.length ? (
              <div className="inc-list">
                {unresolvedIncidents.map((inc) => {
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
                                className="icon-hit-pad"
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
                            className="dbtn dbtn-ghost inc-menu-btn"
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
              <QueryFailure
                compact
                title="Road incidents could not be loaded"
                detail="The rest of this truck remains available. Retry this section when the connection is stable."
                onRetry={() => { void incidentsQuery.refetch() }}
                retrying={incidentsQuery.isFetching}
              />
            ) : (
              <div className="empty-note"><Shield size={16} /> No incidents recorded for this unit.</div>
            )}
          </Section>}

              <InspectionsSection ref={inspectionsRef} vehicleId={t.id} truckId={t.id} currentOdometer={t.odometer} className="dsec-operation dsec-inspections" hideWhenIdle />
            </div>
          </section>

          <section className="detail-station-section dsec-record" aria-labelledby="service-record-heading">
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
                    {historyQuery.isLoading ? <div className="empty-note" role="status"><Spinner size="xs" /> Loading service history...</div>
                      : historyQuery.isError ? <QueryFailure compact title="Service history could not be loaded" detail="No records were removed. Try loading the history again." onRetry={() => { void historyQuery.refetch() }} retrying={historyQuery.isFetching} />
                      : history.length === 0 ? <div className="empty-note"><History size={16} /> No completed service has been recorded for this truck.</div>
                      : <div className="timeline">
                        {history.map((h) => (
                          <div key={h.id} className={'tl-item tl-' + h.kind.toLowerCase()}>
                            <div className="tl-marker" />
                            <div className="tl-body">
                              <div className="tl-row1"><span className={'tl-kind tl-kind-' + h.kind.toLowerCase()}>{h.kind}</span><span className="tl-date">{fmtDate(h.date)}</span><span className="tl-odo">{fmt(h.odometer)} mi</span></div>
                              <div className="tl-summary">{h.summary || '—'}</div>
                              <div className="tl-meta">
                                <span><User size={12} /> {h.mechanic || 'Unassigned'}</span>
                                <span className="tl-meta-actions">
                                  {h.cost != null && <span className="tl-cost">{money(h.cost)}</span>}
                                  {looksLikePreventiveMaintenance(h) && (
                                    <button type="button" className="tl-pm-action" onClick={() => setRecognizingPm(h)}>
                                      <CheckCircle2 size={13} /> Recognize as PM
                                    </button>
                                  )}
                                </span>
                              </div>
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
                    {partsQuery.isLoading ? <div className="empty-note" role="status"><Spinner size="xs" /> Loading parts and warranty...</div>
                      : partsQuery.isError ? <QueryFailure compact title="Parts and warranty could not be loaded" detail="No records were removed. Try loading this section again." onRetry={() => { void partsQuery.refetch() }} retrying={partsQuery.isFetching} />
                      : parts.length === 0 ? <div className="empty-note"><Box size={16} /> No installed parts or warranty records have been added.</div>
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
            className={`detail-station-section dsec-context${locationOpen ? ' is-open' : ' is-collapsed'}`}
            icon={<MapIcon size={17} />}
            right={
              <div className="location-head-actions">
                <div className="loc-now">
                  <i className={'loc-dot' + (t.moving ? ' is-moving' : '')} style={{ background: meta.dot }} />
                  <span className="loc-label" title={t.location_label || 'Location unknown'}>
                    {t.location_label || 'Location unknown'}
                  </span>
                  {t.speed_mph ? <span className="loc-mph"> · {t.speed_mph} mph {t.heading || ''}</span> : <span className="loc-mph"> · parked</span>}
                </div>
                <button
                  type="button"
                  className="map-disclosure-toggle"
                  aria-expanded={locationOpen}
                  onClick={() => setLocationOpen((open) => !open)}
                >
                  {locationOpen ? 'Hide map' : 'Show map'}
                  <ChevronDown size={16} aria-hidden="true" />
                </button>
              </div>
            }
          >
            {locationOpen && (
              <div className="dmap-wrap">
                <FleetMap trucks={mapTrucks} focusId={t.id} onSelect={handleMapSelect} />
                <div className="dmap-side">
                  <div className="dmap-side-h">Nearest units</div>
                  {nearestUnits.length === 0 && <div className="empty-note">No located units nearby.</div>}
                  {nearestUnits.map((nearby) => (
                    <button key={nearby.id} className="near-row" onClick={() => onOpen(nearby.id)}>
                      <i className="near-dot" style={{ background: STATUS_META[nearby.status].dot }} />
                      <span className="near-unit">{nearby.unit_number}</span>
                      <span className="near-loc">{nearby.city || '—'}</span>
                      <span className="near-mi">{nearby.miles} mi</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </Section>
        </div>
        {!detailOverlayOpen && (
          <button
            type="button"
            className={`next-action-dock next-action-dock--${nextAction.tone}`}
            onClick={nextAction.onClick}
            aria-label={`Next action: ${nextAction.label}`}
          >
            <span className="next-action-dock-icon" aria-hidden="true">{nextAction.icon}</span>
            <span className="next-action-dock-copy">
              <small>Next action</small>
              <strong>{nextAction.label}</strong>
            </span>
            <ArrowRight size={20} aria-hidden="true" />
          </button>
        )}
      </>
      ) : truckQuery.isError ? (
        <QueryFailure
          title="Truck activity could not be loaded"
          detail={truckLoadFailureDetail(truckQuery.error)}
          onRetry={() => { void truckQuery.refetch() }}
          retrying={truckQuery.isFetching}
        />
      ) : (
        <div className="loader flex-col gap-3 text-sm text-slate-500">
          <Spinner size="md" />
          <span role="status">Loading repair orders, inspections, and service details…</span>
        </div>
      )}

      {data && detailsOpen && <TruckDetailsModal
        truck={t}
        detail={data}
        canMerge={user?.role === 'garage_owner' || user?.role === 'garage_admin'}
        onChangeDriver={() => setAssigningDriver(true)}
        onEdit={() => { setDetailsOpen(false); setEditing(true) }}
        onMerge={() => { setDetailsOpen(false); setMergeOpen(true) }}
        onClose={() => setDetailsOpen(false)}
      />}
      {mergeOpen && <MergeTruckModal
        truck={t}
        onClose={() => setMergeOpen(false)}
        onMerged={(canonicalId) => {
          setMergeOpen(false)
          refresh()
          qc.invalidateQueries({ queryKey: ['vehicle-merge-candidates'] })
          if (canonicalId !== t.id) onOpen(canonicalId)
        }}
      />}
      {data && editing && <TruckEditModal truck={t} detail={data} onClose={() => setEditing(false)} />}
      {schedulePMOpen && <SchedulePMModal truck={t} onClose={() => setSchedulePMOpen(false)} onDone={refresh} />}
      {recognizingPm && (
        <RecognizePMModal
          entry={recognizingPm}
          truck={t}
          onClose={() => setRecognizingPm(null)}
          onDone={refresh}
        />
      )}
      {assigningDriver && <AssignDriverModal truck={t} driverPhone={t.driver_phone} onClose={() => setAssigningDriver(false)} />}
      {logging && <LogIncidentModal vehicleId={t.id} truckId={t.id} onClose={() => setLogging(false)} />}
      {editingIncident && <EditIncidentModal incident={editingIncident} truckId={t.id} onClose={() => setEditingIncident(null)} />}
      {newWOOpen && (
        <NewWorkOrderModal
          truck={t}
          onClose={() => setNewWOOpen(false)}
          onCreated={() => refresh()}
        />
      )}
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

function RecognizePMModal({ entry, truck, onClose, onDone }: {
  entry: HistoryEntry
  truck: BoardTruck
  onClose: () => void
  onDone: () => void
}) {
  const initialDate = entry.date?.slice(0, 10) || new Date().toISOString().slice(0, 10)
  const initialOdometer = entry.odometer ?? truck.odometer ?? 0
  const [performedOn, setPerformedOn] = useState(initialDate)
  const [odometer, setOdometer] = useState(String(initialOdometer || ''))
  const parsedOdometer = Number(odometer)
  const nextPmMiles = Number.isFinite(parsedOdometer) && parsedOdometer >= 0
    ? parsedOdometer + (truck.pm_interval_miles || 25_000)
    : null

  const recognize = useMutation({
    mutationFn: async () => (await api.post(`/fleet/trucks/${truck.id}/recognize-pm`, {
      repair_order_id: entry.id,
      performed_on: performedOn,
      odometer: parsedOdometer,
    })).data as { next_pm_miles?: number | null; pm_due_date?: string | null; schedule_advanced: boolean },
    onSuccess: (result) => {
      toast.success(
        result.schedule_advanced && result.next_pm_miles != null
          ? `PM recorded · next at ${fmt(result.next_pm_miles)} mi`
          : 'PM recorded in service history'
      )
      onDone()
      onClose()
    },
    onError: (error: AxiosError<{ detail?: string }>) => toast.error(error.response?.data?.detail || 'Failed to recognize PM service'),
  })

  const invalid = !performedOn || !odometer.trim() || !Number.isFinite(parsedOdometer) || parsedOdometer < 0
  return (
    <SidekickPanel
      title="Recognize prior PM"
      subtitle={fleetUnitLabel(truck)}
      icon={<CheckCircle2 size={18} className="text-[var(--yellow)]" />}
      onClose={onClose}
      width="max-w-[520px]"
      tone="maintenance"
      footer={(
        <div className="fleet-sidekick-actions">
          <button type="button" className="dbtn dbtn-ghost" disabled={recognize.isPending} onClick={onClose}>Cancel</button>
          <button type="button" className="dbtn dbtn-yellow" disabled={invalid || recognize.isPending} onClick={() => recognize.mutate()}>
            {recognize.isPending ? <Spinner size="xs" /> : <CheckCircle2 size={15} />} Record PM completion
          </button>
        </div>
      )}
    >
      <div className="recognize-pm-summary">
        <span>Existing repair order</span>
        <strong>{entry.summary || 'Completed repair'}</strong>
        <small>{fmtDate(entry.date)} · No new repair order or invoice will be created.</small>
      </div>

      <div className="recognize-pm-fields">
        <label>
          <span>PM performed date</span>
          <input type="date" value={performedOn} max={new Date().toISOString().slice(0, 10)} onChange={(event) => setPerformedOn(event.target.value)} />
        </label>
        <label>
          <span>Odometer at service</span>
          <input inputMode="numeric" value={odometer} onChange={(event) => setOdometer(event.target.value.replace(/[^0-9]/g, ''))} placeholder="Enter service mileage" />
        </label>
      </div>

      <div className="recognize-pm-impact">
        <Info size={15} />
        <span>
          This repair order will become the truck’s PM record.
          {nextPmMiles != null && <> The next PM will be set to <strong>{fmt(nextPmMiles)} mi</strong> using the truck’s {fmt(truck.pm_interval_miles || 25_000)} mi interval.</>}
        </span>
      </div>

    </SidekickPanel>
  )
}

/* The detail view is the source of truth for the truck's relationships and
   service context. Editing deliberately starts from here, not from the board. */
function TruckDetailsModal({ truck, detail, canMerge, onChangeDriver, onEdit, onMerge, onClose }: {
  truck: BoardTruck; detail: TruckDetailData; canMerge: boolean; onChangeDriver: () => void; onEdit: () => void; onMerge: () => void; onClose: () => void
}) {
  return (
    <SidekickPanel
      title={fleetUnitLabel(truck)}
      subtitle="Truck details"
      icon={<Truck size={18} className="text-[var(--yellow)]" />}
      onClose={onClose}
      width="max-w-[560px]"
      variant="reference"
      tone="neutral"
    >
      <section className="fleet-reference-section">
        <div className="fleet-reference-heading">
          <h3 className="dmap-side-h">Identity</h3>
          <button className="dbtn dbtn-ghost" onClick={onEdit}>
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
        </div>
        <h4 className="fleet-reference-subhead">Relationships &amp; billing</h4>
        <div className="id-grid">
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
      </section>

      <section className="fleet-reference-section">
        <h3 className="dmap-side-h">Driver &amp; crew</h3>
        <div className="person person-driver">
          <div className="avatar">{initials(truck.driver_name)}</div>
          <div>
            <div className="person-name">{truck.driver_name || 'Unassigned'}</div>
            <div className="person-role">{detail.driver_phone ? formatUSPhone(detail.driver_phone) : 'Assigned driver'}</div>
          </div>
          {detail.driver_phone && (
            <a className="person-call" href={`tel:${detail.driver_phone}`} aria-label={`Call ${truck.driver_name || 'driver'}`}><Phone size={15} /></a>
          )}
          <button className="dbtn dbtn-ghost fleet-reference-driver-action" onClick={onChangeDriver}>
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
      </section>
      <section className="fleet-reference-section">
        <h3 className="dmap-side-h">Service record</h3>
        <div className="id-grid">
          <Stat label="Lifetime service spend" value={money(detail.lifetime_spend)} />
          <Stat label="Incidents on record" value={detail.incidents_count || '—'} />
        </div>
      </section>
      {canMerge && (
        <div className="truck-cleanup-actions">
          <div>
            <strong>Record maintenance</strong>
            <span>Merge another record only when it represents this same physical truck.</span>
          </div>
          <button type="button" className="dbtn dbtn-ghost" onClick={onMerge}>
            <Combine size={15} /> Merge duplicate
          </button>
        </div>
      )}
    </SidekickPanel>
  )
}

function mergeRecordLabel(record: VehicleMergeSummary) {
  return record.unit_number ? `Unit ${record.unit_number}` : `${record.customer_name} truck`
}

function MergeRecordCard({ record, action }: { record: VehicleMergeSummary; action: 'keep' | 'archive' }) {
  return (
    <section className={`merge-record-card merge-record-${action}`} aria-label={`${action === 'keep' ? 'Keep' : 'Archive'} ${mergeRecordLabel(record)}`}>
      <div className="merge-record-heading">
        <span>{action === 'keep' ? <CheckCircle2 size={15} /> : <Archive size={15} />}{action === 'keep' ? 'Keep' : 'Archive'}</span>
        <strong>{mergeRecordLabel(record)}</strong>
        <small>{record.customer_name}</small>
      </div>
      <dl className="merge-record-facts">
        <div><dt>VIN</dt><dd>{record.vin || 'Not recorded'}</dd></div>
        <div><dt>Mileage</dt><dd>{record.mileage == null ? 'Not recorded' : `${record.mileage.toLocaleString()} mi`}</dd></div>
        <div><dt>Plate</dt><dd>{record.license_plate || 'Not recorded'}</dd></div>
        <div><dt>Repair history</dt><dd>{record.repair_order_count} repair order{record.repair_order_count === 1 ? '' : 's'}</dd></div>
      </dl>
    </section>
  )
}

export function MergeTruckModal({ truck, onClose, onMerged }: {
  truck: BoardTruck; onClose: () => void; onMerged: (canonicalId: string) => void
}) {
  const qc = useQueryClient()
  const [duplicateId, setDuplicateId] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [stage, setStage] = useState<'select' | 'review'>('select')
  const candidatesQuery = useQuery<VehicleMergeSummary[]>({
    queryKey: ['vehicle-merge-candidates', truck.id, 'fleet-unit'],
    queryFn: async () => (await api.get(`/vehicles/${truck.id}/duplicate-candidates`, {
      params: { include_unit_matches: true },
    })).data,
  })
  const previewQuery = useQuery<VehicleMergePreview>({
    queryKey: ['vehicle-merge-preview', truck.id, duplicateId],
    queryFn: async () => (await api.get(`/vehicles/${truck.id}/merge-preview/${duplicateId}`)).data,
    enabled: Boolean(duplicateId),
  })
  const preview = previewQuery.data
  useEffect(() => {
    if (candidatesQuery.data?.length === 1 && !duplicateId) {
      setDuplicateId(candidatesQuery.data[0].id)
    }
  }, [candidatesQuery.data, duplicateId])

  const merge = useMutation({
    mutationFn: async () => {
      if (!preview || !duplicateId) throw new Error('Choose the duplicate truck first')
      const canonicalId = preview.recommended_canonical_id
      const archivedId = canonicalId === truck.id ? duplicateId : truck.id
      const confirmation = preview.match_basis === 'vin'
        ? { confirm_vin: preview.match_value }
        : { confirm_unit_number: preview.match_value }
      return (await api.post<VehicleMergeResult>(`/vehicles/${canonicalId}/merge`, {
        duplicate_vehicle_id: archivedId,
        ...confirmation,
      })).data
    },
    onSuccess: (result) => {
      const movedHistory = (result.moved.repair_orders || 0)
        + (result.moved.inspections || 0)
        + (result.moved.incidents || 0)
      const keptLabel = recommended ? mergeRecordLabel(recommended) : 'Canonical truck'
      const archivedLabel = archived ? mergeRecordLabel(archived) : 'Duplicate truck'
      toast.success(`${keptLabel} kept; ${archivedLabel} archived. ${movedHistory} service record${movedHistory === 1 ? '' : 's'} moved.`)
      qc.invalidateQueries({ queryKey: ['fleet-board'] })
      qc.invalidateQueries({ queryKey: ['fleet-truck', truck.id] })
      onMerged(result.canonical_vehicle.id)
    },
    onError: (error: AxiosError<{ detail?: string }>) => {
      toast.error(error.response?.data?.detail || error.message || 'Failed to merge trucks')
    },
  })

  const identityLabel = preview?.match_basis === 'vin' ? 'VIN' : 'unit number'
  const recommended = preview
    ? (preview.recommended_canonical_id === preview.canonical.id ? preview.canonical : preview.duplicate)
    : null
  const archived = preview
    ? (preview.recommended_canonical_id === preview.canonical.id ? preview.duplicate : preview.canonical)
    : null
  const historySummary = preview ? [
    { label: 'repair orders', count: preview.canonical.repair_order_count + preview.duplicate.repair_order_count },
    { label: 'inspections', count: preview.canonical.inspection_count + preview.duplicate.inspection_count },
    { label: 'incidents', count: preview.canonical.incident_count + preview.duplicate.incident_count },
    { label: 'appointments', count: preview.canonical.appointment_count + preview.duplicate.appointment_count },
  ].filter((item) => item.count > 0) : []
  const selectedCandidate = candidatesQuery.data?.find((candidate) => candidate.id === duplicateId)
  const mergeError = merge.error as AxiosError<{ detail?: string }> | null

  const selectCandidate = (candidateId: string) => {
    if (merge.isPending) return
    setDuplicateId(candidateId)
    setConfirmed(false)
    setStage('select')
    merge.reset()
  }

  const returnToSelection = () => {
    if (merge.isPending) return
    setStage('select')
    setConfirmed(false)
    merge.reset()
  }

  const reviewSelection = () => {
    if (!preview || previewQuery.isError) return
    setConfirmed(false)
    setStage('review')
  }

  return (
    <Modal title="Merge duplicate truck" icon={<Combine size={17} />} onClose={onClose} width={760} scrollable={false} dismissDisabled={merge.isPending}>
      <div className="merge-flow">
        <div className="merge-body">
          {stage === 'select' ? (
            <>
              <div className="merge-current">
                <div>
                  <span>Current record</span>
                  <strong>{fleetUnitLabel(truck)}</strong>
                </div>
                <small>{[truck.year, truck.make, truck.model].filter(Boolean).join(' ') || 'Truck details not recorded'} · {truck.odometer == null ? 'Mileage not recorded' : `${truck.odometer.toLocaleString()} mi`} · {truck.vin ? `VIN ${truck.vin}` : 'VIN not recorded'}</small>
              </div>

              <div className="merge-section-copy">
                <strong>Select the duplicate record</strong>
                <span>Choose the other database record that represents this same physical truck. Nothing changes until the review is confirmed.</span>
              </div>

              {candidatesQuery.isLoading ? (
                <div className="merge-empty"><Spinner size="xs" /> Checking possible duplicates…</div>
              ) : candidatesQuery.isError ? (
                <div className="merge-empty merge-error">
                  <span>Possible duplicates could not be loaded.</span>
                  <button type="button" className="dbtn dbtn-ghost" onClick={() => candidatesQuery.refetch()}><RotateCcw size={14} /> Retry</button>
                </div>
              ) : !candidatesQuery.data?.length ? (
                <div className="merge-empty">No safe VIN or unit-number matches were found. Add the missing identity information first, then try again.</div>
              ) : (
                <div className="merge-candidates" aria-label="Possible duplicate truck records">
                  {candidatesQuery.data.map((candidate) => {
                    const selected = duplicateId === candidate.id
                    const exactVin = Boolean(truck.vin && candidate.vin && truck.vin.trim().toUpperCase() === candidate.vin.trim().toUpperCase())
                    return (
                      <button
                        key={candidate.id}
                        type="button"
                        aria-pressed={selected}
                        className={'merge-candidate' + (selected ? ' is-selected' : '')}
                        onClick={() => selectCandidate(candidate.id)}
                      >
                        <span className="merge-choice-mark" aria-hidden="true">{selected && <Check size={15} />}</span>
                        <span className="merge-candidate-copy">
                          <span className="merge-candidate-title">
                            <strong>{mergeRecordLabel(candidate)}</strong>
                            <em>{exactVin ? 'Exact VIN' : 'Same unit number'}</em>
                          </span>
                          <small>{candidate.customer_name} · {[candidate.year, candidate.make, candidate.model].filter(Boolean).join(' ') || 'Truck details not recorded'}</small>
                          <small>{candidate.vin ? `VIN ${candidate.vin}` : 'VIN not recorded'} · {candidate.mileage == null ? 'Mileage not recorded' : `${candidate.mileage.toLocaleString()} mi`} · {candidate.repair_order_count} repair order{candidate.repair_order_count === 1 ? '' : 's'}</small>
                        </span>
                      </button>
                    )
                  })}
                </div>
              )}

              {duplicateId && previewQuery.isLoading && (
                <div className="merge-preview-status"><Spinner size="xs" /> Building the Keep versus Archive comparison…</div>
              )}
              {duplicateId && previewQuery.isError && (
                <div className="merge-empty merge-error">
                  <span>The comparison could not be built. The selected records have not changed.</span>
                  <button type="button" className="dbtn dbtn-ghost" onClick={() => previewQuery.refetch()}><RotateCcw size={14} /> Retry</button>
                </div>
              )}
            </>
          ) : recommended && archived && preview ? (
            <>
              <div className="merge-review-intro">
                <strong>Review which truck stays</strong>
                <span>The stronger record is recommended using VIN, repair history, mileage, plate, and other truck details.</span>
              </div>

              <div className="merge-comparison">
                <MergeRecordCard record={archived} action="archive" />
                <ArrowRight className="merge-direction" size={22} aria-hidden="true" />
                <MergeRecordCard record={recommended} action="keep" />
              </div>

              <section className="merge-preserved" aria-label="History preserved by this merge">
                <CheckCircle2 size={18} aria-hidden="true" />
                <div>
                  <strong>Service history stays with the surviving truck</strong>
                  <span>
                    {historySummary.length
                      ? historySummary.map((item) => `${item.count} ${item.label}`).join(' · ')
                      : 'No linked repair orders, inspections, incidents, or appointments were found.'}
                  </span>
                  <small>Completed work and past invoice recipients remain unchanged.</small>
                </div>
              </section>

              {preview.warnings.length > 0 && (
                <div className="merge-warnings">
                  {preview.warnings.map((warning) => <span key={warning}><AlertTriangle size={14} />{warning}</span>)}
                </div>
              )}

              <button
                type="button"
                role="checkbox"
                aria-checked={confirmed}
                className={'merge-confirm' + (confirmed ? ' is-confirmed' : '')}
                onClick={() => { setConfirmed((current) => !current); merge.reset() }}
                disabled={merge.isPending}
              >
                <span className="merge-confirm-box" aria-hidden="true">{confirmed && <Check size={15} />}</span>
                <span>I verified {mergeRecordLabel(recommended)} and {mergeRecordLabel(archived)} are the same physical truck with {identityLabel} <strong>{preview.match_value}</strong>.</span>
              </button>

              {merge.isError && (
                <div className="merge-empty merge-error" role="alert">
                  <span>{mergeError?.response?.data?.detail || mergeError?.message || 'The trucks could not be merged. Nothing was changed.'}</span>
                  <span>Review the records and try again.</span>
                </div>
              )}
            </>
          ) : (
            <div className="merge-empty merge-error">The comparison is no longer available. Return and select the duplicate again.</div>
          )}
        </div>

        <div className="merge-actions">
          {stage === 'review' ? (
            <button type="button" className="dbtn dbtn-ghost" onClick={returnToSelection} disabled={merge.isPending}><ArrowLeft size={15} /> Back</button>
          ) : (
            <button type="button" className="dbtn dbtn-ghost" onClick={onClose}>Cancel</button>
          )}
          {stage === 'review' && <button type="button" className="dbtn dbtn-ghost merge-cancel" onClick={onClose} disabled={merge.isPending}>Cancel</button>}
          {stage === 'select' ? (
            <button type="button" className="dbtn dbtn-yellow" onClick={reviewSelection} disabled={!selectedCandidate || !preview || previewQuery.isLoading || previewQuery.isError}>
              {previewQuery.isLoading ? <Spinner size="xs" /> : <ArrowRight size={15} />} Review merge
            </button>
          ) : (
            <button type="button" className="dbtn dbtn-danger" onClick={() => merge.mutate()} disabled={!preview || !confirmed || merge.isPending}>
              {merge.isPending ? <Spinner size="xs" /> : <Combine size={15} />} {merge.isPending ? 'Merging records…' : `Merge into ${recommended ? mergeRecordLabel(recommended) : 'recommended truck'}`}
            </button>
          )}
        </div>
      </div>
    </Modal>
  )
}
