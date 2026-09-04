import { forwardRef, useEffect, useId, useImperativeHandle, useState, useRef } from 'react'
import { Spinner } from '@/components/ui'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { AxiosError } from 'axios'
import toast from 'react-hot-toast'
import {
  X, Pencil, AlertTriangle, ClipboardCheck, CheckCircle2, XCircle, Plus, ClipboardList, Trash2, UserRound, Calendar,
  Check, Minus, RotateCcw, Wrench, Camera, Search, ChevronDown, ShieldCheck,
} from 'lucide-react'
import api from '../../lib/api'
import SlidePanel from '@/components/SlidePanel'
import MapboxAddressInput from '@/components/MapboxAddressInput'
import { useAuthStore } from '../../stores/authStore'
import type {
  BoardTruck, TruckDetail, Inspection, InspectionDetail, InspectionItem, InspectionItemResult, InspectionResult, IncidentSeverity, IncidentEntry,
  PMServiceEntry, DriverProfile, LegacyDriverContact, VehicleDriverAssignment,
} from './types'
import { fleetUnitLabel, fmtDate, fmt } from './helpers'
import { isSupportedPhotoFile, runPhotoUploadQueue, uploadDirectPhoto, type PhotoUploadStatus } from '@/lib/photoUpload'
import { formatUSPhone } from '@/utils/phone'
import { duplicateVinConflict, duplicateVinTruckLabel, type DuplicateVinConflict } from './duplicateVin'
import type { QueryClient } from '@tanstack/react-query'
import { getWorkOSCapabilities, startWorkOSLogin } from '../../lib/workosAuth'

/**
 * Fleet work orders ARE repair orders — creating/completing/deleting one changes
 * the owner's Shop Cockpit work queue too, not just the fleet board. Invalidate
 * both.
 *
 * The cockpit refetches when it is revisited, so Fleet does not make a
 * background action-queue request for an unmounted dashboard.
 */
export function invalidateFleetAndCockpit(qc: QueryClient) {
  qc.invalidateQueries({ queryKey: ['fleet-board'] })
  qc.invalidateQueries({ queryKey: ['dashboard-action-queue'] })
  for (const key of ['repair-orders', 'mechanic-board-team', 'mechanic-board-detail']) {
    qc.invalidateQueries({ queryKey: [key], refetchType: 'all' })
  }
}

/* shared modal shell (fleet design system) */
let openFleetModalCount = 0
let bodyOverflowBeforeFleetModal = ''
let rootOverflowBeforeFleetModal = ''

export function Modal({ title, icon, onClose, children, width = 480, scrollable = true, dismissDisabled = false }: {
  title: string
  icon: React.ReactNode
  onClose: () => void
  children: React.ReactNode
  width?: number
  scrollable?: boolean
  dismissDisabled?: boolean
}) {
  const titleId = useId()
  const dialogRef = useRef<HTMLDivElement>(null)
  const onCloseRef = useRef(onClose)
  const dismissDisabledRef = useRef(dismissDisabled)
  onCloseRef.current = onClose
  dismissDisabledRef.current = dismissDisabled

  const requestClose = () => {
    if (!dismissDisabledRef.current) onCloseRef.current()
  }

  useEffect(() => {
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
    if (openFleetModalCount === 0) {
      bodyOverflowBeforeFleetModal = document.body.style.overflow
      rootOverflowBeforeFleetModal = document.documentElement.style.overflow
      document.body.style.overflow = 'hidden'
      document.documentElement.style.overflow = 'hidden'
    }
    openFleetModalCount += 1

    const focusFrame = window.requestAnimationFrame(() => dialogRef.current?.focus())
    const handleKeyDown = (event: KeyboardEvent) => {
      const dialog = dialogRef.current
      if (!dialog) return
      if (event.key === 'Escape') {
        event.preventDefault()
        if (!dismissDisabledRef.current) onCloseRef.current()
        return
      }
      if (event.key !== 'Tab') return

      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )).filter((element) => element.getAttribute('aria-hidden') !== 'true')

      if (!focusable.length) {
        event.preventDefault()
        dialog.focus()
        return
      }

      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement
      if (!dialog.contains(active)) {
        event.preventDefault()
        ;(event.shiftKey ? last : first).focus()
      } else if (event.shiftKey && (active === first || active === dialog)) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && (active === last || active === dialog)) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', handleKeyDown)

    return () => {
      window.cancelAnimationFrame(focusFrame)
      document.removeEventListener('keydown', handleKeyDown)
      openFleetModalCount = Math.max(0, openFleetModalCount - 1)
      if (openFleetModalCount === 0) {
        document.body.style.overflow = bodyOverflowBeforeFleetModal
        document.documentElement.style.overflow = rootOverflowBeforeFleetModal
      }
      if (previouslyFocused?.isConnected) previouslyFocused.focus()
    }
  }, [])

  return (
    <div
      // 80: above SlidePanel's 70, so a confirm raised from inside Truck
      // details is not rendered behind the panel that raised it; below
      // BaseSelect's 100, so a dropdown inside this modal still opens over it.
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.6)', zIndex: 80, display: 'grid', placeItems: 'center' }}
      onClick={(event) => { if (event.target === event.currentTarget) requestClose() }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-busy={dismissDisabled || undefined}
        tabIndex={-1}
        className="dsec"
        style={{
          width,
          maxWidth: '92vw',
          maxHeight: '88vh',
          overflowY: scrollable ? 'auto' : 'hidden',
          overflowX: 'hidden',
        }}
      >
        <div className="dsec-head">
          <div className="dsec-title">{icon}<h3 id={titleId}>{title}</h3></div>
          <button type="button" className="person-call" aria-label={`Close ${title}`} onClick={requestClose} disabled={dismissDisabled}><X size={18} /></button>
        </div>
        {children}
      </div>
    </div>
  )
}

/** Persistent task shell for fleet workflows. Centered Modal is reserved for
 * destructive confirmation and other protected-focus decisions. */
export type FleetSidekickVariant = 'quick' | 'builder' | 'checklist' | 'reference'
export type FleetSidekickTone = 'neutral' | 'maintenance' | 'repair' | 'inspection' | 'safety'

export function SidekickPanel({
  title,
  subtitle,
  icon,
  onClose,
  children,
  footer,
  headerExtra,
  width = 'max-w-xl',
  variant = 'quick',
  tone = 'neutral',
}: {
  title: string
  subtitle?: string
  icon: React.ReactNode
  onClose: () => void
  children: React.ReactNode
  footer?: React.ReactNode
  headerExtra?: React.ReactNode
  width?: string
  variant?: FleetSidekickVariant
  tone?: FleetSidekickTone
}) {
  const usesSectionSurface = variant === 'quick' || variant === 'reference'
  return (
    <SlidePanel
      isOpen
      dark
      title={title}
      subtitle={subtitle}
      headerIcon={icon}
      headerExtra={headerExtra}
      onClose={onClose}
      footer={footer}
      width={width}
      panelClassName={`fleet-sidekick-shell fleet-sidekick-shell-${variant} fleet-sidekick-shell-tone-${tone}`}
    >
      <div
        className={`${usesSectionSurface ? 'dsec ' : ''}fleet-sidekick-body fleet-sidekick-${variant} fleet-sidekick-tone-${tone}`}
        data-sidekick-variant={variant}
        data-sidekick-tone={tone}
      >
        {children}
      </div>
    </SlidePanel>
  )
}

/* Centered confirmation modal (styled — replaces window.confirm). */
/**
 * Confirm a destructive action, optionally requiring a written reason.
 *
 * `prompt` turns the dialog into one that will not proceed on a click alone:
 * the reason it collects is the record of why the thing happened, which is the
 * whole point when the action removes something from a shared board.
 */
export function ConfirmModal({ title, message, confirmLabel = 'Delete', pending, prompt, onConfirm, onClose }: {
  title: string; message: string; confirmLabel?: string; pending?: boolean
  prompt?: { label: string; placeholder?: string }
  onConfirm: (reason: string) => void; onClose: () => void
}) {
  const [reason, setReason] = useState('')
  const missingReason = !!prompt && !reason.trim()
  return (
    <Modal title={title} icon={<Trash2 size={17} />} onClose={onClose} width={420}>
      <p style={{ fontSize: 14, color: 'var(--muted)', lineHeight: 1.5, marginBottom: prompt ? 16 : 20 }}>{message}</p>
      {prompt && (
        <div style={{ marginBottom: 20 }}>
          <Field label={prompt.label}>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={prompt.placeholder}
              maxLength={500}
              rows={3}
              autoFocus
              style={{
                width: '100%', background: 'var(--ink)', border: '1px solid var(--line)',
                borderRadius: 9, color: 'var(--text)', fontFamily: 'inherit', fontSize: 13.5,
                padding: 10, outline: 'none', resize: 'vertical',
              }}
            />
          </Field>
        </div>
      )}
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
        <button className="dbtn dbtn-ghost" onClick={onClose} disabled={pending}>Cancel</button>
        <button
          onClick={() => onConfirm(reason.trim())}
          disabled={pending || missingReason}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 8, height: 42, padding: '0 17px',
            borderRadius: 10, fontSize: 13.5, fontWeight: 700, border: 'none',
            background: 'var(--red)', color: '#fff',
            cursor: pending || missingReason ? 'not-allowed' : 'pointer',
            opacity: pending || missingReason ? 0.6 : 1,
          }}
        >
          {pending ? <Spinner size="sm" /> : <Trash2 size={15} />} {confirmLabel}
        </button>
      </div>
    </Modal>
  )
}

function Field({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  return (
    <label style={{ display: 'block', gridColumn: full ? '1 / -1' : undefined }}>
      <span className="id-k" style={{ display: 'block', marginBottom: 5 }}>{label}</span>
      {children}
    </label>
  )
}

function FieldGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <fieldset className="fleet-field-group">
      <legend className="id-k">{label}</legend>
      {children}
    </fieldset>
  )
}

const yellowBtn = 'dbtn dbtn-yellow'
const ghostBtn = 'dbtn dbtn-ghost'

/* ---------- Edit truck (odometer / driver / PM / manual location) ---------- */

export function TruckEditModal({ truck, detail, onClose }: { truck: BoardTruck; detail: TruckDetail; onClose: () => void }) {
  const qc = useQueryClient()
  const [editingBilling, setEditingBilling] = useState(false)
  const [f, setF] = useState({
    unit_number: truck.unit_number || '',
    vin: truck.vin || '',
    make: truck.make || '',
    model: truck.model || '',
    year: truck.year?.toString() || '',
    license_plate: truck.plate || '',
    odometer: truck.odometer?.toString() || '',
    driver_name: truck.driver_name || '',
    driver_phone: detail.driver_phone ? formatUSPhone(detail.driver_phone) : '',
    bill_to_company_name: detail.bill_to_company_name || '',
    bill_to_first_name: detail.bill_to_first_name || '',
    bill_to_last_name: detail.bill_to_last_name || '',
    bill_to_email: detail.bill_to_email || '',
    bill_to_phone: detail.bill_to_phone ? formatUSPhone(detail.bill_to_phone) : '',
    bill_to_billing_address_line1: detail.bill_to_billing_address_line1 || '',
    bill_to_billing_address_line2: detail.bill_to_billing_address_line2 || '',
    bill_to_billing_city: detail.bill_to_billing_city || '',
    bill_to_billing_state: detail.bill_to_billing_state || '',
    bill_to_billing_zip: detail.bill_to_billing_zip || '',
    bill_to_billing_country: detail.bill_to_billing_country || 'USA',
    bill_labor_at_customer_rate: detail.bill_labor_at_customer_rate,
    pm_interval_miles: truck.pm_interval_miles?.toString() || '25000',
    next_pm_miles: truck.next_pm_miles?.toString() || '',
    location_label: truck.location_label || '',
    location_city: truck.location_city || '',
    lat: truck.lat?.toString() || '',
    lng: truck.lng?.toString() || '',
    speed_mph: truck.speed_mph?.toString() || '',
    heading: truck.heading || '',
  })
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF((p) => ({ ...p, [k]: e.target.value }))
  const cancelBillingEdit = () => {
    setF((p) => ({
      ...p,
      bill_to_company_name: detail.bill_to_company_name || '',
      bill_to_first_name: detail.bill_to_first_name || '',
      bill_to_last_name: detail.bill_to_last_name || '',
      bill_to_email: detail.bill_to_email || '',
      bill_to_phone: detail.bill_to_phone ? formatUSPhone(detail.bill_to_phone) : '',
      bill_to_billing_address_line1: detail.bill_to_billing_address_line1 || '',
      bill_to_billing_address_line2: detail.bill_to_billing_address_line2 || '',
      bill_to_billing_city: detail.bill_to_billing_city || '',
      bill_to_billing_state: detail.bill_to_billing_state || '',
      bill_to_billing_zip: detail.bill_to_billing_zip || '',
      bill_to_billing_country: detail.bill_to_billing_country || 'USA',
    }))
    setEditingBilling(false)
  }
  const [decodingVin, setDecodingVin] = useState(false)
  const [vinConflict, setVinConflict] = useState<DuplicateVinConflict | null>(null)
  const lastDecodedVin = useRef((truck.vin || '').trim().toUpperCase())
  const numOrUndef = (v: string) => (v.trim() === '' ? undefined : Number(v))

  const handleLocationSelect = ({ formatted, feature }: Parameters<NonNullable<React.ComponentProps<typeof MapboxAddressInput>['onAddressSelect']>>[0]) => {
    const props = feature?.properties as Record<string, unknown> | undefined
    const coordinates = feature?.geometry?.type === 'Point' ? feature.geometry.coordinates : undefined
    const city = [props?.place, props?.address_level2, props?.locality, props?.neighborhood]
      .find((value) => typeof value === 'string' && value.trim()) as string | undefined

    setF((p) => ({
      ...p,
      location_label: formatted || p.location_label,
      location_city: city || p.location_city,
      lng: typeof coordinates?.[0] === 'number' ? String(coordinates[0]) : p.lng,
      lat: typeof coordinates?.[1] === 'number' ? String(coordinates[1]) : p.lat,
    }))
  }

  const decodeVin = async (raw: string, options: { quiet?: boolean } = {}) => {
    const vin = raw.trim().toUpperCase()
    if (vin.length < 11) {
      if (!options.quiet) toast.error('VIN must be at least 11 characters')
      return
    }

    setDecodingVin(true)
    try {
      const { data } = await api.get(`/customers/vin/decode/${encodeURIComponent(vin)}`)
      if (data.error_code && data.error_code !== '0') {
        if (!options.quiet) toast.error(data.error_text || 'Failed to decode VIN')
        return
      }
      setF((p) => ({
        ...p,
        vin: data.vin || vin || p.vin,
        make: data.make || p.make,
        model: data.model || p.model,
        year: data.year ? String(data.year) : p.year,
      }))
      lastDecodedVin.current = vin
      const decodedLabel = [data.year, data.make, data.model].filter(Boolean).join(' ')
      toast.success(decodedLabel ? `VIN decoded: ${decodedLabel}` : 'VIN decoded')
    } catch (e: any) {
      if (!options.quiet) toast.error(e.response?.data?.detail || 'Failed to decode VIN')
    } finally {
      setDecodingVin(false)
    }
  }

  const handleVinChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const vin = e.target.value.toUpperCase()
    setF((p) => ({ ...p, vin }))
    setVinConflict(null)
    const trimmedVin = vin.trim()
    if (trimmedVin.length === 17 && trimmedVin !== lastDecodedVin.current) {
      void decodeVin(trimmedVin, { quiet: true })
    }
  }

  const save = useMutation({
    mutationFn: async () => (await api.patch(`/fleet/trucks/${truck.id}`, {
      unit_number: f.unit_number,
      vin: f.vin,
      make: f.make,
      model: f.model,
      year: numOrUndef(f.year),
      license_plate: f.license_plate,
      odometer: numOrUndef(f.odometer),
      driver_name: f.driver_name,
      driver_phone: f.driver_phone,
      bill_labor_at_customer_rate: f.bill_labor_at_customer_rate,
      bill_to_customer: detail.bill_to_customer_id ? {
        customer_id: detail.bill_to_customer_id,
        company_name: f.bill_to_company_name,
        first_name: f.bill_to_first_name,
        last_name: f.bill_to_last_name,
        email: f.bill_to_email,
        phone: f.bill_to_phone,
        billing_address_line1: f.bill_to_billing_address_line1,
        billing_address_line2: f.bill_to_billing_address_line2,
        billing_city: f.bill_to_billing_city,
        billing_state: f.bill_to_billing_state,
        billing_zip: f.bill_to_billing_zip,
        billing_country: f.bill_to_billing_country,
      } : undefined,
      pm_interval_miles: numOrUndef(f.pm_interval_miles),
      next_pm_miles: numOrUndef(f.next_pm_miles),
      location_label: f.location_label,
      location_city: f.location_city,
      lat: numOrUndef(f.lat),
      lng: numOrUndef(f.lng),
      speed_mph: numOrUndef(f.speed_mph),
      heading: f.heading,
    })).data,
    onSuccess: () => {
      toast.success('Truck updated')
      qc.invalidateQueries({ queryKey: ['fleet-truck', truck.id] })
      qc.invalidateQueries({ queryKey: ['customers'] })
      qc.invalidateQueries({ queryKey: ['fleet-companies'] })
      qc.invalidateQueries({ queryKey: ['vehicle-account-relationships', truck.id] })
      invalidateFleetAndCockpit(qc)
      onClose()
    },
    onError: (e: any) => {
      const conflict = duplicateVinConflict(e)
      if (conflict) {
        setVinConflict(conflict)
        toast.error('This VIN is already assigned to another truck.')
        return
      }
      toast.error(e.response?.data?.detail || 'Failed to update')
    },
  })

  return (
    <SidekickPanel
      title={fleetUnitLabel(truck)} subtitle="Edit truck" icon={<Pencil size={18} className="text-[var(--yellow)]" />}
      onClose={onClose} width="max-w-[560px]" tone="neutral"
      footer={(
        <div className="fleet-sidekick-actions">
          <button type="button" className="dbtn dbtn-ghost" disabled={save.isPending} onClick={onClose}>Cancel</button>
          <button className={yellowBtn} disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? <Spinner size="sm" /> : <Pencil size={15} />} Save changes
          </button>
        </div>
      )}
    >
      <div className="dmap-side-h" style={{ marginBottom: 8 }}>Identity</div>
      <div className="fleet-form-grid fleet-form-grid-2 fleet-form-grid-spaced">
        <Field label="Unit #"><input value={f.unit_number} onChange={set('unit_number')} placeholder="TPS-109" /></Field>
        <Field label="Plate"><input value={f.license_plate} onChange={set('license_plate')} placeholder="ABC-1234" /></Field>
        <Field label="Make"><input value={f.make} onChange={set('make')} /></Field>
        <Field label="Model"><input value={f.model} onChange={set('model')} /></Field>
        <Field label="Year"><input value={f.year} onChange={set('year')} inputMode="numeric" /></Field>
        <Field label="VIN">
          <div style={{ display: 'flex', gap: 8 }}>
            <input value={f.vin} onChange={handleVinChange} placeholder="17-character VIN" maxLength={17} style={{ minWidth: 0, flex: 1, textTransform: 'uppercase' }} />
            <button className="dbtn dbtn-ghost" type="button" onClick={() => decodeVin(f.vin)} disabled={decodingVin || f.vin.trim().length < 11}>
              {decodingVin ? <Spinner size="xs" /> : 'Decode'}
            </button>
          </div>
          {vinConflict?.vehicle && (
            <div style={{ marginTop: 8, border: '1px solid rgba(239, 68, 68, .55)', borderRadius: 8, padding: '9px 10px', background: 'rgba(127, 29, 29, .18)', display: 'grid', gap: 3 }}>
              <strong style={{ color: '#fecaca', fontSize: 12 }}>VIN already assigned to {duplicateVinTruckLabel(vinConflict.vehicle)}</strong>
              <span style={{ color: 'var(--muted-2)', fontSize: 12 }}>{vinConflict.vehicle.owner_lessor_name ? `Owner / lessor: ${vinConflict.vehicle.owner_lessor_name}` : 'Owner / lessor not assigned'}</span>
              {vinConflict.vehicle.operating_authority_name && <span style={{ color: 'var(--muted-2)', fontSize: 12 }}>Operating authority: {vinConflict.vehicle.operating_authority_name}</span>}
              {vinConflict.vehicle.license_plate && <span style={{ color: 'var(--muted-2)', fontSize: 12 }}>Plate: {vinConflict.vehicle.license_plate}</span>}
            </div>
          )}
        </Field>
      </div>
      <div className="dmap-side-h" style={{ marginBottom: 8 }}>Operations & location</div>
      <div className="fleet-form-grid fleet-form-grid-2">
        <Field label="Odometer (mi)"><input value={f.odometer} onChange={set('odometer')} inputMode="numeric" /></Field>
        <Field label="PM interval (mi)"><input value={f.pm_interval_miles} onChange={set('pm_interval_miles')} inputMode="numeric" /></Field>
        <Field label="Next PM at (mi)"><input value={f.next_pm_miles} onChange={set('next_pm_miles')} inputMode="numeric" placeholder="odometer + interval" /></Field>
        <div />
        <Field label="Driver name"><input value={f.driver_name} onChange={set('driver_name')} /></Field>
        <Field label="Driver phone"><input value={f.driver_phone} onChange={(e) => setF((p) => ({ ...p, driver_phone: formatUSPhone(e.target.value) }))} placeholder="(704) 555-1234" /></Field>
        <Field label="Location" full>
          <MapboxAddressInput
            value={f.location_label}
            onChange={set('location_label')}
            autoComplete="street-address"
            placeholder="TPS Yard, Matthews NC or I-85 mile 42"
            options={{ language: 'en', country: 'US' }}
            onAddressSelect={handleLocationSelect}
          />
        </Field>
      </div>
      <div className="dmap-side-h" style={{ margin: '18px 0 4px' }}>
        Default invoice recipient{detail.bill_to_relationship_type ? ` · ${detail.bill_to_relationship_type.replace('_', ' ')}` : ''}
      </div>
      {detail.bill_to_customer_id ? (
        <>
          <div style={{ background: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 9, padding: '11px 12px', display: 'grid', gap: 5 }}>
            <strong style={{ color: 'var(--text)', fontSize: 14 }}>{f.bill_to_company_name || 'Unnamed company'}</strong>
            <span style={{ color: 'var(--muted-2)', fontSize: 12 }}>{[f.bill_to_first_name, f.bill_to_last_name].filter(Boolean).join(' ') || 'No contact name'}</span>
            <span style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 14px', fontSize: 12 }}>
              {f.bill_to_email && <a href={`mailto:${f.bill_to_email}`} style={{ color: 'var(--text)' }}>{f.bill_to_email}</a>}
              {f.bill_to_phone && <a href={`tel:${f.bill_to_phone}`} style={{ color: 'var(--text)' }}>{f.bill_to_phone}</a>}
            </span>
            <span style={{ color: detail.bill_to_is_internal ? 'var(--yellow)' : 'var(--muted-2)', fontSize: 11 }}>
              {detail.bill_to_is_internal
                ? `Internal fleet pricing · parts at garage cost · labor at ${f.bill_labor_at_customer_rate ? 'customer rate' : 'garage cost'}`
                : 'External invoice recipient · standard customer pricing'}
            </span>
            {!editingBilling && (
              <button type="button" className={ghostBtn} style={{ justifySelf: 'start', marginTop: 4, height: 32, padding: '0 10px', fontSize: 12 }} onClick={() => setEditingBilling(true)}>
                <Pencil size={13} /> Edit billing details
              </button>
            )}
          </div>
          {editingBilling && (
            <div style={{ marginTop: 10, padding: 12, background: 'var(--panel-2)', border: '1px solid var(--line)', borderRadius: 9 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 10 }}>
                <p style={{ margin: 0, fontSize: 12, color: 'var(--muted-2)' }}>These edits update the same customer on the Main Dashboard.</p>
                <button type="button" className={ghostBtn} style={{ height: 30, padding: '0 9px', fontSize: 12, flexShrink: 0 }} onClick={cancelBillingEdit}>Cancel</button>
              </div>
              <div className="fleet-form-grid fleet-form-grid-2">
                <Field label="Company name" full><input value={f.bill_to_company_name} onChange={set('bill_to_company_name')} /></Field>
                <Field label="First name *"><input required value={f.bill_to_first_name} onChange={set('bill_to_first_name')} /></Field>
                <Field label="Last name *"><input required value={f.bill_to_last_name} onChange={set('bill_to_last_name')} /></Field>
                <Field label="Email *"><input required type="email" value={f.bill_to_email} onChange={set('bill_to_email')} /></Field>
                <Field label="Phone"><input value={f.bill_to_phone} onChange={(e) => setF((prev) => ({ ...prev, bill_to_phone: formatUSPhone(e.target.value) }))} /></Field>
                <Field label="Billing address line 1" full><input value={f.bill_to_billing_address_line1} onChange={set('bill_to_billing_address_line1')} /></Field>
                <Field label="Billing address line 2" full><input value={f.bill_to_billing_address_line2} onChange={set('bill_to_billing_address_line2')} /></Field>
                <Field label="City"><input value={f.bill_to_billing_city} onChange={set('bill_to_billing_city')} /></Field>
                <Field label="State"><input value={f.bill_to_billing_state} onChange={set('bill_to_billing_state')} /></Field>
                <Field label="ZIP"><input value={f.bill_to_billing_zip} onChange={set('bill_to_billing_zip')} /></Field>
                <Field label="Country"><input value={f.bill_to_billing_country} onChange={set('bill_to_billing_country')} /></Field>
              </div>
            </div>
          )}
        </>
      ) : (
        <div style={{ background: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 9, padding: '11px 12px', color: 'var(--muted-2)', fontSize: 12 }}>
          No active bill-to company is connected to this truck.
        </div>
      )}
      {detail.bill_to_customer_id === detail.fleet_account_customer_id && (
        <p style={{ margin: '7px 0 0', color: 'var(--muted-3)', fontSize: 11 }}>This customer is also the current fleet authority account.</p>
      )}

      {detail.fleet_account_company_name && detail.fleet_account_customer_id !== detail.bill_to_customer_id && (
        <div style={{ marginTop: 12, background: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 9, padding: '11px 12px', display: 'grid', gap: 4 }}>
          <span style={{ color: 'var(--muted-2)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '.08em' }}>Fleet authority account</span>
          <strong style={{ color: 'var(--text)', fontSize: 14 }}>{detail.fleet_account_company_name}</strong>
          <span style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 14px', fontSize: 12 }}>
            {detail.fleet_account_email && <a href={`mailto:${detail.fleet_account_email}`} style={{ color: 'var(--text)' }}>{detail.fleet_account_email}</a>}
            {detail.fleet_account_phone && <a href={`tel:${detail.fleet_account_phone}`} style={{ color: 'var(--text)' }}>{formatUSPhone(detail.fleet_account_phone)}</a>}
          </span>
        </div>
      )}

      {detail.bill_to_is_internal && (
        <>
          <div className="dmap-side-h" style={{ margin: '18px 0 4px' }}>Internal pricing</div>
          <label style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 13, color: 'var(--text)', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={f.bill_labor_at_customer_rate}
              onChange={(e) => setF((prev) => ({ ...prev, bill_labor_at_customer_rate: e.target.checked }))}
              style={{ width: 'auto', marginTop: 2 }}
            />
            <span style={{ display: 'grid', gap: 3 }}>
              <span>Bill labor at customer rate</span>
              <span style={{ color: 'var(--muted-2)' }}>Parts use garage cost. This applies to new internal repair orders.</span>
            </span>
          </label>
        </>
      )}
    </SidekickPanel>
  )
}

/* ---------- New work order (corrective) ---------- */

interface VehicleAccountRelationship {
  id: string
  customer_id: string
  relationship_type: 'owner' | 'operator' | 'default_payer'
  effective_to?: string | null
  is_primary: boolean
  customer_company_name?: string | null
}

function useTruckBillToOptions(truckId: string) {
  const { data = [], isLoading } = useQuery<VehicleAccountRelationship[]>({
    queryKey: ['vehicle-account-relationships', truckId],
    queryFn: async () => (await api.get(`/vehicles/${truckId}/relationships`)).data,
  })
  const active = data.filter((item) => !item.effective_to)
  const byCustomer = new Map<string, VehicleAccountRelationship>()
  for (const relationship of active) {
    const current = byCustomer.get(relationship.customer_id)
    if (!current || relationship.relationship_type === 'default_payer' || relationship.is_primary) {
      byCustomer.set(relationship.customer_id, relationship)
    }
  }
  return { options: [...byCustomer.values()], isLoading }
}

const BILL_TO_RELATIONSHIP_LABEL: Record<VehicleAccountRelationship['relationship_type'], string> = {
  default_payer: 'Default payer',
  owner: 'Owner / lessor',
  operator: 'Operating authority',
}

/* Width of the work order drawer, matched to the garage-side repair order
   drawer so the same record reads the same on both sides of the product. */
export const WO_DRAWER_WIDTH = 'max-w-full sm:max-w-[94vw] lg:max-w-[760px] xl:max-w-[860px]'

/* ---------- Schedule PM (date + mileage) ---------- */

export function SchedulePMModal({ truck, onClose, onDone, createMode = false }: { truck: BoardTruck; onClose: () => void; onDone: () => void; createMode?: boolean }) {
  const qc = useQueryClient()
  const intervalMiles = truck.pm_interval_miles || 25000
  // Assumed average daily mileage — keeps the projected due date in step with
  // the odometer target so they don't contradict each other.
  const AVG_MILES_PER_DAY = 600
  // Project the due date from a target odometer: today + miles_remaining / 600.
  const projectDate = (targetMiles: number) => {
    const remaining = targetMiles - (truck.odometer || 0)
    const days = remaining > 0 ? Math.ceil(remaining / AVG_MILES_PER_DAY) : 0
    return new Date(Date.now() + days * 86400000).toISOString().slice(0, 10)
  }
  const initialMiles = truck.next_pm_miles ?? ((truck.odometer || 0) + intervalMiles)
  // Pre-fill the date from mileage (not the stale stored date), so the manager
  // sees a date that agrees with the odometer. They can still override it.
  const [dueDate, setDueDate] = useState(projectDate(initialMiles))
  const [dateEdited, setDateEdited] = useState(false)
  const [nextMiles, setNextMiles] = useState(String(initialMiles))
  // When opened from the card's "Create repair order" action, default to creating
  // the work order now so the manager picks services first, in one step.
  const [createWO, setCreateWO] = useState(createMode)
  const { options: billToOptions, isLoading: billToLoading } = useTruckBillToOptions(truck.id)
  const [billToCustomerId, setBillToCustomerId] = useState('')
  useEffect(() => {
    if (!billToCustomerId && billToOptions.length) {
      const preferred = billToOptions.find((item) => item.relationship_type === 'default_payer' && item.is_primary)
        || billToOptions.find((item) => item.relationship_type === 'operator')
        || billToOptions[0]
      setBillToCustomerId(preferred.customer_id)
    }
  }, [billToCustomerId, billToOptions])
  const rescheduling = !!truck.pm_due_date

  // Services for this PM, seeded from the truck's saved default package. The
  // manager can adjust them here and (optionally) save the new set as default.
  const [selected, setSelected] = useState<string[]>(() => (truck.pm_services || []).map((s) => s.service_id))
  const [saveAsDefault, setSaveAsDefault] = useState(false)
  const defaultIds = (truck.pm_services || []).map((s) => s.service_id)
  const changedFromDefault =
    selected.length !== defaultIds.length || selected.some((id) => !defaultIds.includes(id))

  // Only the PM-category services are offered when scoping a PM.
  const { data: services } = useQuery<PMServiceEntry[]>({
    queryKey: ['fleet-pm-catalog'],
    queryFn: async () => (await api.get('/fleet/pm-service-catalog')).data,
  })
  const activeServices = services || []
  // One PM, not a basket. A PM service already carries its own time, labor and
  // parts for a given truck; picking two would mean claiming a Freightliner
  // package and a Volvo one describe the same visit. The request stays
  // list-shaped so a composed package remains possible without a contract
  // change, but this control sends exactly one.
  const choose = (id: string) => setSelected([id])

  const save = useMutation({
    mutationFn: async () => (await api.post(`/fleet/trucks/${truck.id}/schedule-pm`, {
      // Create mode services the truck now: it must not touch the PM schedule —
      // the date/odometer roll forward when the work order completes (from the
      // real mileage-out). Only reschedule/schedule mode sets those fields.
      // Send an explicit due_date only when the manager overrode it; otherwise
      // leave it null so the backend projects it from the mileage target.
      due_date: createMode ? null : (dateEdited ? (dueDate || null) : null),
      next_pm_miles: createMode ? null : (nextMiles.trim() ? Number(nextMiles) : null),
      create_work_order: createWO,
      service_ids: selected,
      save_as_default: saveAsDefault,
      bill_to_customer_id: (createWO && billToCustomerId) ? billToCustomerId : undefined,
    })).data as BoardTruck,
    onSuccess: (updated) => {
      // Response is the BoardTruck; the PM work order's id IS the order number.
      const num = updated?.pm_work_order?.id || updated?.work_order?.id
      toast.success(
        createMode
          ? (num ? `PM repair order ${num} created` : 'PM repair order created')
          : (rescheduling ? 'PM rescheduled' : 'PM scheduled')
      )
      qc.invalidateQueries({ queryKey: ['fleet-truck', truck.id] })
      invalidateFleetAndCockpit(qc)
      onDone(); onClose()
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to schedule PM'),
  })

  const taskLabel = createMode
    ? 'Create PM repair order'
    : `${rescheduling ? 'Reschedule' : 'Schedule'} PM`
  const footer = (
    <div className="fleet-sidekick-actions">
      <button className={ghostBtn} disabled={save.isPending} onClick={onClose}>Cancel</button>
      <button className={yellowBtn}
        disabled={save.isPending || (createWO && (billToLoading || !billToCustomerId))} onClick={() => save.mutate()}>
        {save.isPending ? <Spinner size="sm" /> : (createMode ? <ClipboardCheck size={15} /> : <Calendar size={15} />)}
        {createMode ? 'Create repair order' : (createWO ? `${rescheduling ? 'Reschedule' : 'Schedule'} + create repair order` : 'Save schedule')}
      </button>
    </div>
  )
  return (
    <SidekickPanel
      title={fleetUnitLabel(truck)}
      subtitle={taskLabel}
      icon={createMode ? <ClipboardCheck size={18} className="text-[var(--yellow)]" /> : <Calendar size={18} className="text-[var(--yellow)]" />}
      onClose={onClose}
      width="max-w-[520px]"
      footer={footer}
      tone="maintenance"
    >
      <div style={{ display: 'grid', gap: 12 }}>
        {/* Schedule fields belong to planning (reschedule), not to servicing the
            truck now. In create mode they're hidden: the next PM rolls forward
            automatically when this work order completes. */}
        {!createMode && (
          <>
            <Field label="Next PM at odometer (mi)">
              <input
                value={nextMiles}
                onChange={(e) => {
                  setNextMiles(e.target.value)
                  // Keep the date in step with the odometer target unless the
                  // manager has explicitly overridden it.
                  const n = Number(e.target.value)
                  if (!dateEdited && e.target.value.trim() && !Number.isNaN(n)) {
                    setDueDate(projectDate(n))
                  }
                }}
                inputMode="numeric"
                placeholder={`${intervalMiles} mi interval`}
              />
            </Field>
            <Field label="Next PM due date">
              <input type="date" value={dueDate} onChange={(e) => { setDueDate(e.target.value); setDateEdited(true) }} />
              <p className="id-k" style={{ textTransform: 'none', letterSpacing: 0, marginTop: 6 }}>
                {dateEdited
                  ? 'Custom date — overrides the mileage estimate.'
                  : `Estimated from mileage (~${AVG_MILES_PER_DAY} mi/day). Edit to override.`}
              </p>
            </Field>
          </>
        )}
        {createWO && (
          <Field label="Invoice this visit to">
            <select value={billToCustomerId} onChange={(event) => setBillToCustomerId(event.target.value)}>
              <option value="" disabled>{billToLoading ? 'Loading connected companies…' : 'Select invoice recipient…'}</option>
              {billToOptions.map((relationship) => (
                <option key={relationship.customer_id} value={relationship.customer_id}>
                  {relationship.customer_company_name || 'Company'} — {BILL_TO_RELATIONSHIP_LABEL[relationship.relationship_type]}
                </option>
              ))}
            </select>
          </Field>
        )}

        <FieldGroup label="PM service">
          <div className="pm-svc-list" role="radiogroup" aria-label="PM service">
            {activeServices.length === 0 ? (
              <div className="pm-svc-empty">No PM services in the catalog yet.</div>
            ) : (
              activeServices.map((s) => {
                const on = selected.includes(s.service_id)
                return (
                  <button
                    type="button"
                    key={s.service_id}
                    role="radio"
                    aria-checked={on}
                    className={'pm-svc-row' + (on ? ' on' : '')}
                    onClick={() => choose(s.service_id)}
                  >
                    <span className="pm-svc-check pm-svc-radio">{on && <Check size={13} />}</span>
                    <span className="pm-svc-name">{s.name}</span>
                    {s.duration_minutes ? <span className="pm-svc-dur">{s.duration_minutes}m</span> : null}
                  </button>
                )
              })
            )}
          </div>
        </FieldGroup>

        {changedFromDefault && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text)', cursor: 'pointer' }}>
            <input type="checkbox" checked={saveAsDefault} onChange={(e) => setSaveAsDefault(e.target.checked)} style={{ width: 'auto' }} />
            Save this as this truck's default PM
          </label>
        )}
        {/* In create mode the work order is always created — no need to offer it
            as a toggle. */}
        {!createMode && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text)', cursor: 'pointer' }}>
            <input type="checkbox" checked={createWO} onChange={(e) => setCreateWO(e.target.checked)} style={{ width: 'auto' }} />
            Create the PM repair order now
          </label>
        )}
      </div>
      <p style={{ fontSize: 12, color: 'var(--muted-2)', marginTop: 10 }}>
        {createMode
          ? "Creates the maintenance repair order now. The next PM rolls forward automatically when this repair order is completed."
          : "PM shows as due when either the date or the odometer is reached. Completing a PM rolls both forward by the interval."}
      </p>
    </SidekickPanel>
  )
}

export const WO_STATUS_LABEL: Record<string, string> = {
  draft: 'Draft', assigned: 'Assigned', acknowledged: 'Acknowledged',
  in_progress: 'In progress', pending_review: 'Pending review',
  completed: 'Completed', invoiced: 'Invoiced', paid: 'Paid', cancelled: 'Cancelled',
}
/* ---------- Assign / change driver (focused, driver-only) ---------- */

export function AssignDriverModal({ truck, driverPhone, onClose }: { truck: BoardTruck; driverPhone?: string | null; onClose: () => void }) {
  const qc = useQueryClient()
  const legacyParts = (truck.driver_name || '').trim().split(/\s+/).filter(Boolean)
  const [search, setSearch] = useState('')
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState({
    first_name: legacyParts[0] || '',
    last_name: legacyParts.slice(1).join(' '),
    phone: driverPhone ? formatUSPhone(driverPhone) : '',
    email: '',
    employee_number: '',
  })
  const capabilities = useQuery({
    queryKey: ['workos-capabilities', '/fleet'],
    queryFn: () => getWorkOSCapabilities('/fleet'),
  })
  const current = useQuery<VehicleDriverAssignment | null>({
    queryKey: ['fleet-vehicle-driver', truck.id],
    queryFn: async () => (await api.get(`/fleet-identity/vehicles/${truck.id}/driver`)).data,
    enabled: capabilities.data?.session_provider === 'workos',
    retry: false,
  })
  const drivers = useQuery<DriverProfile[]>({
    queryKey: ['fleet-driver-profiles'],
    queryFn: async () => (await api.get('/fleet-identity/drivers')).data,
    enabled: capabilities.data?.session_provider === 'workos',
    retry: false,
  })
  const legacyContacts = useQuery<LegacyDriverContact[]>({
    queryKey: ['fleet-legacy-driver-contacts'],
    queryFn: async () => (await api.get('/fleet-identity/drivers/legacy-contacts')).data,
    enabled: capabilities.data?.session_provider === 'workos',
    retry: false,
  })
  const assign = useMutation({
    mutationFn: async (driver: DriverProfile) => (await api.put(`/fleet-identity/vehicles/${truck.id}/driver`, {
      driver_id: driver.id,
      vehicle_id: truck.id,
      start_odometer: truck.odometer ?? undefined,
    })).data,
    onSuccess: () => {
      toast.success('Driver profile assigned')
      qc.invalidateQueries({ queryKey: ['fleet-vehicle-driver', truck.id] })
      qc.invalidateQueries({ queryKey: ['fleet-truck', truck.id] })
      invalidateFleetAndCockpit(qc)
      onClose()
    },
    onError: (e: AxiosError<{ detail?: string }>) => toast.error(e.response?.data?.detail || 'Driver could not be assigned'),
  })
  const create = useMutation({
    mutationFn: async () => (await api.post('/fleet-identity/drivers', {
      first_name: draft.first_name.trim(),
      last_name: draft.last_name.trim(),
      phone: draft.phone.trim() || undefined,
      email: draft.email.trim() || undefined,
      employee_number: draft.employee_number.trim() || undefined,
    })).data as DriverProfile,
    onSuccess: (driver) => {
      qc.setQueryData<DriverProfile[]>(['fleet-driver-profiles'], (items = []) => [...items, driver])
      assign.mutate(driver)
    },
    onError: (e: AxiosError<{ detail?: string }>) => toast.error(e.response?.data?.detail || 'Driver profile could not be created'),
  })
  const remove = useMutation({
    mutationFn: async () => api.delete(`/fleet-identity/vehicles/${truck.id}/driver`),
    onSuccess: () => {
      toast.success('Driver released from this truck')
      qc.setQueryData(['fleet-vehicle-driver', truck.id], null)
      qc.invalidateQueries({ queryKey: ['fleet-truck', truck.id] })
      invalidateFleetAndCockpit(qc)
      onClose()
    },
    onError: (e: AxiosError<{ detail?: string }>) => toast.error(e.response?.data?.detail || 'Driver could not be released'),
  })
  const filteredDrivers = (drivers.data || []).filter((driver) => {
    if (driver.employment_status !== 'active') return false
    const haystack = `${driver.first_name} ${driver.last_name} ${driver.email || ''} ${driver.phone || ''} ${driver.employee_number || ''}`.toLowerCase()
    return haystack.includes(search.trim().toLowerCase())
  })
  const filteredLegacyContacts = (legacyContacts.data || []).filter((contact) => {
    const haystack = `${contact.name} ${contact.phone || ''}`.toLowerCase()
    return haystack.includes(search.trim().toLowerCase())
  })
  const chooseLegacyContact = (contact: LegacyDriverContact) => {
    const parts = contact.name.trim().split(/\s+/).filter(Boolean)
    setDraft({
      first_name: parts[0] || '',
      last_name: parts.slice(1).join(' '),
      phone: contact.phone ? formatUSPhone(contact.phone) : '',
      email: '',
      employee_number: '',
    })
    setCreating(true)
  }
  const busy = assign.isPending || create.isPending || remove.isPending
  const needsWorkOS = capabilities.data && capabilities.data.session_provider !== 'workos'

  return (
    <SidekickPanel
      title={fleetUnitLabel(truck)} subtitle="Driver assignment" icon={<UserRound size={18} className="text-[var(--yellow)]" />}
      onClose={onClose} width="max-w-[460px]" tone="neutral"
      footer={(
        <div className="fleet-sidekick-actions">
          {current.data && <button type="button" className="dbtn dbtn-danger" disabled={busy} onClick={() => remove.mutate()}>Release driver</button>}
          <button type="button" className="dbtn dbtn-ghost" disabled={busy} onClick={onClose}>Done</button>
        </div>
      )}
    >
      <div className="driver-assignment-flow">
        {needsWorkOS ? (
          <div className="driver-workos-gate">
            <ShieldCheck size={20} />
            <div><strong>Organization sign-in required</strong><span>Driver profiles and custody history are protected by your fleet permissions.</span></div>
            <button type="button" className={yellowBtn} onClick={() => startWorkOSLogin('/fleet', capabilities.data?.driver_invitation_management.reauth_path)}>Continue with WorkOS</button>
          </div>
        ) : (
          <>
            {current.data && (
              <div className="driver-current-assignment">
                <span className="avatar">{`${current.data.driver.first_name[0] || ''}${current.data.driver.last_name[0] || ''}`}</span>
                <div><small>Currently assigned</small><strong>{current.data.driver.first_name} {current.data.driver.last_name}</strong><span>{current.data.custody_acknowledged_at ? 'Driver confirmed custody' : 'Waiting for driver confirmation'}</span></div>
              </div>
            )}
            <div className="driver-assignment-heading">
              <div><h3>{current.data ? 'Choose a replacement' : 'Choose a driver profile'}</h3><p>The selected profile begins a new custody period. Earlier assignments remain in history.</p></div>
              <button type="button" className="dbtn dbtn-ghost" onClick={() => setCreating((value) => !value)}>{creating ? 'Choose existing' : 'New profile'}</button>
            </div>
            {creating ? (
              <div className="driver-profile-form">
                <div className="driver-profile-name-row">
                  <Field label="First name"><input autoFocus value={draft.first_name} onChange={(e) => setDraft({ ...draft, first_name: e.target.value })} /></Field>
                  <Field label="Last name"><input value={draft.last_name} onChange={(e) => setDraft({ ...draft, last_name: e.target.value })} /></Field>
                </div>
                <Field label="Email for Driver Portal"><input type="email" value={draft.email} onChange={(e) => setDraft({ ...draft, email: e.target.value })} placeholder="driver@company.com" /></Field>
                <Field label="Phone"><input value={draft.phone} onChange={(e) => setDraft({ ...draft, phone: formatUSPhone(e.target.value) })} placeholder="(704) 555-0123" /></Field>
                <Field label="Employee number (optional)"><input value={draft.employee_number} onChange={(e) => setDraft({ ...draft, employee_number: e.target.value })} /></Field>
                <p className="driver-profile-note">Creating a profile does not create a login. You can review the profile, then send a secure Driver Portal invitation from Truck details.</p>
                <button type="button" className={yellowBtn} disabled={busy || !draft.first_name.trim() || !draft.last_name.trim()} onClick={() => create.mutate()}>{busy ? <Spinner size="sm" /> : <UserRound size={15} />} Create and assign profile</button>
              </div>
            ) : (
              <>
                <label className="driver-profile-search"><Search size={16} /><input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search drivers" aria-label="Search driver profiles" /></label>
                <div className="driver-profile-list">
                  {(drivers.isLoading || legacyContacts.isLoading) && <div className="driver-profile-empty"><Spinner size="sm" /> Loading drivers…</div>}
                  {(drivers.isError || legacyContacts.isError) && <div className="driver-profile-empty">Driver records could not be loaded. Close this panel and try again.</div>}
                  {!drivers.isLoading && !legacyContacts.isLoading && !drivers.isError && !legacyContacts.isError && filteredDrivers.map((driver) => {
                    const selected = current.data?.driver.id === driver.id
                    return <button type="button" key={driver.id} className="driver-profile-option" disabled={busy || selected} onClick={() => assign.mutate(driver)}>
                      <span className="avatar avatar-sm">{`${driver.first_name[0] || ''}${driver.last_name[0] || ''}`}</span>
                      <span><strong>{driver.first_name} {driver.last_name}</strong><small>{driver.email || driver.phone || driver.employee_number || 'Profile ready'}</small></span>
                      <span className={selected ? 'driver-profile-state is-current' : 'driver-profile-state'}>{selected ? 'Current' : 'Assign'}</span>
                    </button>
                  })}
                  {!drivers.isLoading && !legacyContacts.isLoading && !drivers.isError && !legacyContacts.isError && filteredLegacyContacts.map((contact) => (
                    <button type="button" key={`legacy:${contact.name}:${contact.phone || ''}`} className="driver-profile-option is-legacy" disabled={busy} onClick={() => chooseLegacyContact(contact)}>
                      <span className="avatar avatar-sm">{contact.name.split(/\s+/).slice(0, 2).map((part) => part[0]).join('')}</span>
                      <span><strong>{contact.name}</strong><small>Legacy contact · {contact.vehicle_count} {contact.vehicle_count === 1 ? 'truck' : 'trucks'}{contact.phone ? ` · ${formatUSPhone(contact.phone)}` : ''}</small></span>
                      <span className="driver-profile-state">Create profile</span>
                    </button>
                  ))}
                  {!drivers.isLoading && !legacyContacts.isLoading && !drivers.isError && !legacyContacts.isError && filteredDrivers.length === 0 && filteredLegacyContacts.length === 0 && <div className="driver-profile-empty">No matching drivers. Create a profile to preserve this driver’s custody and incident history.</div>}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </SidekickPanel>
  )
}

/* ---------- Log incident ---------- */

const SEVS: IncidentSeverity[] = ['low', 'medium', 'high', 'critical']
const sevTint: Record<IncidentSeverity, string> = {
  low: 'var(--st-shop)', medium: 'var(--yellow)', high: '#fb923c', critical: 'var(--red)',
}

type IncidentPhotoUploadItem = {
  id: string
  file: File
  previewUrl: string
  name: string
  status: PhotoUploadStatus
  progress: number
  error?: string
}

export function LogIncidentModal({ vehicleId, truckId, onClose }: { vehicleId: string; truckId: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [description, setDescription] = useState('')
  const [location, setLocation] = useState('')
  const [severity, setSeverity] = useState<IncidentSeverity>('medium')
  const [attempted, setAttempted] = useState(false)
  const [photoUploads, setPhotoUploads] = useState<IncidentPhotoUploadItem[]>([])
  const photoUploadsRef = useRef<IncidentPhotoUploadItem[]>([])

  useEffect(() => {
    photoUploadsRef.current = photoUploads
  }, [photoUploads])

  useEffect(() => {
    return () => {
      photoUploadsRef.current.forEach((photo) => URL.revokeObjectURL(photo.previewUrl))
    }
  }, [])

  const clearPhotoUploads = () => {
    photoUploadsRef.current.forEach((photo) => URL.revokeObjectURL(photo.previewUrl))
    setPhotoUploads([])
  }

  const updatePhotoUpload = (id: string, patch: Partial<IncidentPhotoUploadItem>) => {
    setPhotoUploads((photos) => photos.map((photo) => photo.id === id ? { ...photo, ...patch } : photo))
  }

  const descError = description.trim() === '' ? 'Describe what happened before logging the incident.' : null

  const create = useMutation({
    mutationFn: async () => {
      const incident = (await api.post('/fleet/incidents', {
        vehicle_id: vehicleId, occurred_at: new Date().toISOString(),
        location: location || undefined, severity, description,
      })).data as IncidentEntry
      await runPhotoUploadQueue(photoUploads, async (photo) => {
        try {
          await uploadDirectPhoto({
            file: photo.file,
            signEndpoint: `/fleet/incidents/${incident.id}/photos/direct-upload-signature`,
            recordEndpoint: `/fleet/incidents/${incident.id}/photos/direct`,
            fallbackEndpoint: `/fleet/incidents/${incident.id}/photos`,
            onProgress: (progress) => updatePhotoUpload(photo.id, progress),
          })
        } catch (error: any) {
          updatePhotoUpload(photo.id, {
            status: 'error',
            error: error.response?.data?.detail || error.message || 'Failed',
          })
          throw error
        }
      })
      return incident
    },
    onSuccess: () => {
      toast.success('Road incident reported')
      clearPhotoUploads()
      qc.invalidateQueries({ queryKey: ['fleet-truck', truckId] })
      invalidateFleetAndCockpit(qc)
      onClose()
    },
    onError: (error: AxiosError<{ detail?: string }>) => toast.error(error.response?.data?.detail || 'The road incident could not be reported. Try again.'),
  })

  const submit = () => {
    setAttempted(true)
    if (descError) return
    create.mutate()
  }

  return (
    <SidekickPanel
      title="Report road incident" subtitle="Record the event while it is fresh" icon={<AlertTriangle size={18} className="text-[var(--red)]" />}
      onClose={onClose} width="max-w-[540px]" tone="safety"
      footer={(
        <div className="fleet-sidekick-actions">
          <button type="button" className="dbtn dbtn-ghost" disabled={create.isPending} onClick={onClose}>Cancel</button>
          <button className={yellowBtn} disabled={create.isPending} onClick={submit}>
            {create.isPending ? <Spinner size="sm" /> : <Plus size={15} />} Report incident
          </button>
        </div>
      )}
    >
      <div style={{ marginBottom: 12 }}>
        <span className="id-k" style={{ display: 'block', marginBottom: 6 }}>Severity</span>
        <div style={{ display: 'flex', gap: 8 }}>
          {SEVS.map((s) => (
            <button key={s} onClick={() => setSeverity(s)}
              style={{
                flex: 1, height: 44, borderRadius: 8, textTransform: 'capitalize', fontSize: 13, fontWeight: 600,
                border: '1px solid ' + (severity === s ? sevTint[s] : 'var(--line)'),
                background: severity === s ? `color-mix(in srgb, ${sevTint[s]} 16%, transparent)` : 'transparent',
                color: severity === s ? sevTint[s] : 'var(--muted)',
              }}>{s}</button>
          ))}
        </div>
      </div>
      <Field label="Location">
        <MapboxAddressInput
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          autoComplete="street-address"
          placeholder="I-85 mile 42, Charlotte NC"
          options={{ language: 'en', country: 'US' }}
          onAddressSelect={({ formatted }) => {
            if (formatted) setLocation(formatted)
          }}
        />
      </Field>
      <div style={{ marginTop: 12 }}>
        <span className="id-k" style={{ display: 'block', marginBottom: 5 }}>What happened? <span style={{ color: 'var(--red)' }}>*</span></span>
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={4}
          style={{ width: '100%', background: 'var(--ink)', border: '1px solid ' + (attempted && descError ? 'var(--red)' : 'var(--line)'), borderRadius: 9, color: 'var(--text)', fontFamily: 'inherit', fontSize: 13.5, padding: 10, outline: 'none' }}
          placeholder="Describe the incident" />
        {attempted && descError && (
          <span style={{ display: 'block', marginTop: 5, fontSize: 12, color: 'var(--red)' }}>{descError}</span>
        )}
      </div>
      <div style={{ marginTop: 12 }}>
        <span className="id-k" style={{ display: 'block', marginBottom: 6 }}>Photo</span>
        {photoUploads.length > 0 ? (
          <div style={{ border: '1px solid var(--line)', borderRadius: 12, padding: 8, background: 'var(--ink)' }}>
            <div style={{ position: 'relative' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(72px, 1fr))', gap: 8 }}>
                {photoUploads.map((photo) => (
                  <div key={photo.id} style={{ position: 'relative', overflow: 'hidden', borderRadius: 9, aspectRatio: '1 / 1', background: 'var(--surface-2)' }}>
                    <img src={photo.previewUrl} alt={photo.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    {(create.isPending || photo.status === 'error') && (
                      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', gap: 4, padding: 6, background: 'rgba(0,0,0,.38)' }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {photo.status === 'error' ? (photo.error || 'Failed') : `${photo.status} ${photo.progress}%`}
                        </span>
                        <span style={{ height: 5, borderRadius: 999, overflow: 'hidden', background: 'rgba(255,255,255,.25)' }}>
                          <span style={{ display: 'block', height: '100%', width: `${Math.max(6, photo.progress)}%`, background: photo.status === 'error' ? 'var(--red)' : 'var(--st-active)' }} />
                        </span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <button
                className={ghostBtn}
                style={{ position: 'absolute', top: 8, right: 8, height: 30, padding: '0 10px' }}
                onClick={() => {
                  clearPhotoUploads()
                }}
                disabled={create.isPending}
              >
                <X size={13} /> Remove
              </button>
            </div>
          </div>
        ) : (
          <label className={ghostBtn} style={{ height: 38, justifyContent: 'center', width: '100%', cursor: create.isPending ? 'not-allowed' : 'pointer' }}>
            <Camera size={14} /> Attach photo
            <input
              type="file"
              accept="image/*"
              multiple
              disabled={create.isPending}
              style={{ display: 'none' }}
              onChange={(e) => {
                const files = Array.from(e.target.files || [])
                e.target.value = ''
                const validFiles = files.filter((file) => {
                  if (!isSupportedPhotoFile(file)) { toast.error(`${file.name} is not an image file`); return false }
                  if (file.size > 10 * 1024 * 1024) { toast.error(`${file.name} is too large. Max 10MB`); return false }
                  return true
                })
                if (validFiles.length === 0) return
                clearPhotoUploads()
                setPhotoUploads(validFiles.map((file) => ({
                  id: crypto.randomUUID(),
                  file,
                  previewUrl: URL.createObjectURL(file),
                  name: file.name,
                  status: 'queued',
                  progress: 0,
                })))
              }}
            />
          </label>
        )}
      </div>
    </SidekickPanel>
  )
}

/* ---------- Edit incident (details, severity, location) ---------- */

export function EditIncidentModal({ incident, truckId, onClose }: { incident: IncidentEntry; truckId: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [description, setDescription] = useState(incident.note || '')
  const [location, setLocation] = useState(incident.location || '')
  const [severity, setSeverity] = useState<IncidentSeverity>(incident.severity)
  const [attempted, setAttempted] = useState(false)

  const descError = description.trim() === '' ? 'Describe what happened before saving.' : null

  const save = useMutation({
    mutationFn: async () => (await api.patch(`/fleet/incidents/${incident.id}`, {
      location: location || null, severity, description,
    })).data,
    onSuccess: () => {
      toast.success('Incident updated')
      qc.invalidateQueries({ queryKey: ['fleet-truck', truckId] })
      invalidateFleetAndCockpit(qc)
      onClose()
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const submit = () => {
    setAttempted(true)
    if (descError) return
    save.mutate()
  }

  return (
    <SidekickPanel
      title="Edit road incident" subtitle="Update incident details" icon={<Pencil size={18} className="text-[var(--red)]" />}
      onClose={onClose} width="max-w-[540px]" tone="safety"
      footer={(
        <div className="fleet-sidekick-actions">
          <button type="button" className="dbtn dbtn-ghost" disabled={save.isPending} onClick={onClose}>Cancel</button>
          <button className={yellowBtn} disabled={save.isPending} onClick={submit}>
            {save.isPending ? <Spinner size="sm" /> : <CheckCircle2 size={15} />} Save changes
          </button>
        </div>
      )}
    >
      <div style={{ marginBottom: 12 }}>
        <span className="id-k" style={{ display: 'block', marginBottom: 6 }}>Severity</span>
        <div style={{ display: 'flex', gap: 8 }}>
          {SEVS.map((s) => (
            <button key={s} onClick={() => setSeverity(s)}
              style={{
                flex: 1, height: 44, borderRadius: 8, textTransform: 'capitalize', fontSize: 13, fontWeight: 600,
                border: '1px solid ' + (severity === s ? sevTint[s] : 'var(--line)'),
                background: severity === s ? `color-mix(in srgb, ${sevTint[s]} 16%, transparent)` : 'transparent',
                color: severity === s ? sevTint[s] : 'var(--muted)',
              }}>{s}</button>
          ))}
        </div>
      </div>
      <Field label="Location">
        <MapboxAddressInput
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          autoComplete="street-address"
          placeholder="I-85 mile 42, Charlotte NC"
          options={{ language: 'en', country: 'US' }}
          onAddressSelect={({ formatted }) => {
            if (formatted) setLocation(formatted)
          }}
        />
      </Field>
      <div style={{ marginTop: 12 }}>
        <span className="id-k" style={{ display: 'block', marginBottom: 5 }}>What happened? <span style={{ color: 'var(--red)' }}>*</span></span>
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={4}
          style={{ width: '100%', background: 'var(--ink)', border: '1px solid ' + (attempted && descError ? 'var(--red)' : 'var(--line)'), borderRadius: 9, color: 'var(--text)', fontFamily: 'inherit', fontSize: 13.5, padding: 10, outline: 'none' }}
          placeholder="Describe the incident" />
        {attempted && descError && (
          <span style={{ display: 'block', marginTop: 5, fontSize: 12, color: 'var(--red)' }}>{descError}</span>
        )}
      </div>
    </SidekickPanel>
  )
}

/* ---------- Inspections: section + checklist ---------- */

export interface InspectionsSectionHandle {
  start: () => void
  open: (inspectionId: string) => void
}

export const InspectionsSection = forwardRef<InspectionsSectionHandle, {
  vehicleId: string
  truckId: string
  currentOdometer?: number | null
  className?: string
  hideWhenIdle?: boolean
  /** Land the manager in the repair-order builder for work this inspection found. */
  onOpenRepairOrder?: (repairOrderId: string) => void
}>(({ vehicleId, truckId, currentOdometer, className, hideWhenIdle = false, onOpenRepairOrder }, ref) => {
  const qc = useQueryClient()
  const { user } = useAuthStore()
  const isOwner = user?.role === 'garage_owner'  // only the owner may delete inspections
  const [openId, setOpenId] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<Inspection | null>(null)
  const inspectionsQuery = useQuery<Inspection[]>({
    queryKey: ['fleet-inspections', vehicleId],
    queryFn: async () => (await api.get('/fleet/inspections', { params: { vehicle_id: vehicleId } })).data,
  })
  const { data: inspections } = inspectionsQuery
  const start = useMutation({
    mutationFn: async () => (await api.post('/fleet/inspections', { vehicle_id: vehicleId })).data as InspectionDetail,
    onSuccess: (insp) => {
      qc.invalidateQueries({ queryKey: ['fleet-inspections', vehicleId] })
      setOpenId(insp.id)
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed'),
  })
  const del = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/fleet/inspections/${id}`)).data,
    onSuccess: () => {
      toast.success('Inspection deleted')
      setConfirmDelete(null)
      qc.invalidateQueries({ queryKey: ['fleet-inspections', vehicleId] })
      qc.invalidateQueries({ queryKey: ['fleet-truck', truckId] })
      invalidateFleetAndCockpit(qc)
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to delete'),
  })
  useImperativeHandle(ref, () => ({
    start: () => start.mutate(),
    open: (inspectionId: string) => setOpenId(inspectionId),
  }), [start])
  // Most recent completed reading, for the "previous odometer" reference in the checklist.
  const lastReading = (inspections || [])
    .filter((i) => i.status === 'completed' && i.odometer != null && i.performed_at)
    .sort((a, b) => (a.performed_at! < b.performed_at! ? 1 : -1))[0]
  const actionableInspections = (inspections || []).filter((inspection) => (
    inspection.status === 'scheduled'
    || (inspection.status === 'completed' && inspection.result === 'fail' && !inspection.repair_order_id)
  ))
  const visibleInspections = hideWhenIdle ? actionableInspections : (inspections || [])

  if (hideWhenIdle && inspections != null && visibleInspections.length === 0) {
    return (
      <>
        {openId && <InspectionChecklistModal inspectionId={openId} truckId={truckId} vehicleId={vehicleId} currentOdometer={currentOdometer} lastReadingDate={lastReading?.performed_at || null} onClose={() => setOpenId(null)} onOpenRepairOrder={onOpenRepairOrder} />}
      </>
    )
  }

  return (
    <section className={'dsec' + (className ? ` ${className}` : '')}>
      <div className="dsec-head">
        <div className="dsec-title"><ClipboardCheck size={17} /><h3>Weekly inspections</h3>
          {inspections != null && <span className="dsec-count">{visibleInspections.length}</span>}</div>
        <button className={ghostBtn + ' dsec-action'} style={{ height: 34 }} onClick={() => start.mutate()} disabled={start.isPending} title="Start inspection">
          {start.isPending ? <Spinner size="xs" /> : <Plus size={14} />} <span className="dbtn-label">Start inspection</span>
        </button>
      </div>
      {inspectionsQuery.isLoading ? (
        <div className="empty-note" role="status"><Spinner size="xs" /> Loading inspection schedule…</div>
      ) : inspectionsQuery.isError ? (
        <div className="query-failure query-failure--compact" role="alert">
          <AlertTriangle size={18} aria-hidden="true" />
          <div className="query-failure-copy">
            <strong>Inspections could not be loaded</strong>
            <span>No inspection records were changed. Try loading this section again.</span>
          </div>
          <button type="button" className="query-retry" onClick={() => { void inspectionsQuery.refetch() }} disabled={inspectionsQuery.isFetching}>
            {inspectionsQuery.isFetching ? <Spinner size="xs" /> : <RotateCcw size={14} />}
            {inspectionsQuery.isFetching ? 'Retrying…' : 'Try again'}
          </button>
        </div>
      ) : !visibleInspections.length ? (
        <div className="empty-note"><ClipboardCheck size={16} /> No inspections recorded. Start one when you are ready to check this truck.</div>
      ) : (
        <div className="inc-list">
          {visibleInspections.map((i) => {
            const dot = i.status === 'completed'
              ? (i.result === 'fail' ? 'var(--red)' : 'var(--st-active)')
              : i.status === 'missed' ? 'var(--red)' : 'var(--yellow)'
            const label = i.status === 'completed' ? (i.result || 'completed') : i.status
            const labelColor = (i.status === 'missed' || i.result === 'fail') ? 'var(--red)' : undefined
            const openable = i.status !== 'missed'  // missed markers have no checklist to open
            return (
              <div
                key={i.id}
                className="lrow"
                style={{ cursor: openable ? 'pointer' : 'default' }}
                onClick={openable ? () => setOpenId(i.id) : undefined}
              >
                <i className="lrow-dot" style={{ background: dot }} />
                <span className="lrow-tx">{fmtDate(i.performed_at || i.scheduled_for)}</span>
                <span className="lrow-r">
                  {i.odometer != null && <span className="lrow-tx" style={{ color: 'var(--muted)' }}>{fmt(i.odometer)} mi</span>}
                  <span className="lrow-st" style={{ textTransform: 'capitalize', color: labelColor }}>{label}</span>
                  {i.repair_order_id && (
                    <span title="Repair order created to fix flagged items" style={{ display: 'inline-flex', alignItems: 'center', gap: 3, color: 'var(--st-active)' }}>
                      <Wrench size={13} />
                    </span>
                  )}
                  {isOwner && (
                    <button
                      className="icon-hit"
                      onClick={(e) => { e.stopPropagation(); setConfirmDelete(i) }}
                      disabled={del.isPending}
                      title="Delete inspection (owner only)"
                      style={{ background: 'none', border: 'none', color: 'var(--muted-2)', cursor: 'pointer', padding: 2, display: 'inline-flex' }}
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </span>
              </div>
            )
          })}
        </div>
      )}
      {openId && <InspectionChecklistModal inspectionId={openId} truckId={truckId} vehicleId={vehicleId} currentOdometer={currentOdometer} lastReadingDate={lastReading?.performed_at || null} onClose={() => setOpenId(null)} onOpenRepairOrder={onOpenRepairOrder} />}
      {confirmDelete && (
        <ConfirmModal
          title="Delete inspection"
          message={`Permanently delete the ${fmtDate(confirmDelete.performed_at || confirmDelete.scheduled_for)} inspection? This removes the record and its checklist and cannot be undone.`}
          confirmLabel="Delete inspection"
          pending={del.isPending}
          onConfirm={() => del.mutate(confirmDelete.id)}
          onClose={() => setConfirmDelete(null)}
        />
      )}
    </section>
  )
})

InspectionsSection.displayName = 'InspectionsSection'

const CATEGORY_ORDER = ['Brakes', 'Fluids', 'Lights', 'Safety', 'Steering', 'Tires']

function InspectionChecklistModal({ inspectionId, truckId, vehicleId, currentOdometer, lastReadingDate, onClose, onOpenRepairOrder }: {
  inspectionId: string; truckId: string; vehicleId: string; currentOdometer?: number | null; lastReadingDate?: string | null
  onClose: () => void
  onOpenRepairOrder?: (repairOrderId: string) => void
}) {
  const qc = useQueryClient()
  const [odometer, setOdometer] = useState('')  // fresh reading; previous stays read-only
  const [confirming, setConfirming] = useState(false)
  const [showErrors, setShowErrors] = useState(false)
  const firstErrorRef = useRef<HTMLDivElement | null>(null)
  const odoRef = useRef<HTMLInputElement | null>(null)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const [userToggled, setUserToggled] = useState<Record<string, boolean>>({})
  const [noteDrafts, setNoteDrafts] = useState<Record<string, string>>({})
  const [compactChecklist, setCompactChecklist] = useState(false)
  const [savingNotes, setSavingNotes] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const media = window.matchMedia('(max-width: 1023px)')
    const sync = () => setCompactChecklist(media.matches)
    sync()
    media.addEventListener?.('change', sync)
    return () => media.removeEventListener?.('change', sync)
  }, [])

  const inspectionQuery = useQuery<InspectionDetail>({
    queryKey: ['fleet-inspection', inspectionId],
    queryFn: async () => (await api.get(`/fleet/inspections/${inspectionId}`)).data,
  })
  const { data: insp } = inspectionQuery
  const refreshLists = () => {
    qc.invalidateQueries({ queryKey: ['fleet-inspections', vehicleId] })
    qc.invalidateQueries({ queryKey: ['fleet-truck', truckId] })
    invalidateFleetAndCockpit(qc)
  }
  const patchItem = useMutation({
    mutationFn: async ({ itemId, result, note }: { itemId: string; result?: InspectionItemResult; note?: string }) =>
      (await api.patch(`/fleet/inspections/${inspectionId}/items/${itemId}`, { result, note })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['fleet-inspection', inspectionId] }),
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to save'),
  })
  const bulk = useMutation({
    mutationFn: async (result: InspectionItemResult) => {
      await Promise.all((insp?.items || []).map((it) =>
        api.patch(`/fleet/inspections/${inspectionId}/items/${it.id}`, { result })))
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['fleet-inspection', inspectionId] }),
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Some inspection results could not be saved. The checklist was refreshed.'),
  })
  const complete = useMutation({
    mutationFn: async () => (await api.post(`/fleet/inspections/${inspectionId}/complete`, { odometer: Number(odometer) })).data,
    onSuccess: () => { toast.success('Inspection completed'); refreshLists(); qc.invalidateQueries({ queryKey: ['fleet-inspection', inspectionId] }); onClose() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Could not complete'),
  })
  // The order arrives described by the failed items; the builder is where the
  // manager turns that into actual work.
  const createWO = useMutation({
    mutationFn: async () => (await api.post(`/fleet/inspections/${inspectionId}/create-work-order`)).data,
    onSuccess: (inspection: { repair_order_id?: string | null }) => {
      toast.success('Repair order created')
      refreshLists()
      qc.invalidateQueries({ queryKey: ['fleet-inspection', inspectionId] })
      if (inspection?.repair_order_id && onOpenRepairOrder) {
        onClose()
        onOpenRepairOrder(inspection.repair_order_id)
      }
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Could not create repair order'),
  })

  const items = insp?.items || []
  const done = insp?.status === 'completed'
  const total = items.length
  const doneCount = items.filter((i) => i.result !== 'pending').length
  const passCount = items.filter((i) => i.result === 'pass').length
  const failCount = items.filter((i) => i.result === 'fail').length
  const naCount = items.filter((i) => i.result === 'na').length
  const remaining = total - doneCount
  const computedResult: InspectionResult = failCount > 0 ? 'fail' : 'pass'
  const allMarked = total > 0 && remaining === 0
  const progressPct = total ? (doneCount / total) * 100 : 0

  const grouped = items.reduce((acc, it) => { (acc[it.category] ||= []).push(it); return acc }, {} as Record<string, InspectionItem[]>)
  const cats = Object.keys(grouped).sort((a, b) => {
    const ia = CATEGORY_ORDER.indexOf(a), ib = CATEGORY_ORDER.indexOf(b)
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b)
  })
  const secComplete = (cat: string) => grouped[cat].every((it) => it.result !== 'pending')
  const firstIncompleteCat = cats.find((cat) => !secComplete(cat))
  const isCollapsed = (cat: string) => (
    userToggled[cat]
      ? !!collapsed[cat]
      : secComplete(cat) || (compactChecklist && cat !== firstIncompleteCat)
  )
  const secSummary = (cat: string): { text: string; color: string } => {
    const its = grouped[cat]
    const d = its.filter((i) => i.result !== 'pending').length
    if (d < its.length) return { text: `${d}/${its.length}`, color: 'var(--muted-3)' }
    const f = its.filter((i) => i.result === 'fail').length
    const na = its.filter((i) => i.result === 'na').length
    const p = its.filter((i) => i.result === 'pass').length
    if (f > 0) return { text: `${f} flagged`, color: 'var(--red)' }
    if (na > 0) return { text: `${p} pass · ${na} N/A`, color: 'var(--st-active)' }
    return { text: 'All passed ✓', color: 'var(--st-active)' }
  }

  const odoNum = odometer.trim() ? Number(odometer) : null
  const odoValid = odoNum != null && Number.isFinite(odoNum) && odoNum >= 0
  const odoBackwards = odoValid && currentOdometer != null && (odoNum as number) < currentOdometer

  // Live-computed problems so highlights + message clear as each is fixed.
  const problems: string[] = []
  if (!allMarked) problems.push(`${remaining} item${remaining > 1 ? 's' : ''} still unmarked`)
  if (!odoValid) problems.push('enter the current odometer')
  else if (odoBackwards) problems.push('odometer is below the previous reading')
  const odoError = showErrors && (!odoValid || odoBackwards)

  // First unmarked item (in display order) — the scroll/highlight target.
  let firstPendingId: string | null = null
  let firstPendingCat: string | null = null
  for (const cat of cats) {
    for (const it of grouped[cat]) {
      if (it.result === 'pending') { firstPendingId = it.id; firstPendingCat = cat; break }
    }
    if (firstPendingId) break
  }

  const setStatus = (item: InspectionItem, result: InspectionItemResult) => {
    const next: InspectionItemResult = item.result === result ? 'pending' : result  // tap active to clear
    patchItem.mutate({ itemId: item.id, result: next })
  }
  const markAllPass = () => { bulk.mutate('pass'); setUserToggled({}); setCollapsed({}) }
  const resetAll = () => { bulk.mutate('pending'); setUserToggled({}); setCollapsed({}); setNoteDrafts({}) }
  const toggleSection = (cat: string) => {
    const nextCollapsed = !isCollapsed(cat)
    setUserToggled((u) => ({ ...u, [cat]: true }))
    setCollapsed((c) => ({ ...c, [cat]: nextCollapsed }))
  }

  const reviewAndComplete = async () => {
    if (patchItem.isPending || bulk.isPending || savingNotes) return
    if (problems.length) {
      setShowErrors(true)
      requestAnimationFrame(() => {
        if (firstPendingId && firstErrorRef.current) {
          firstErrorRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
        } else if (odoRef.current) {
          odoRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
          odoRef.current.focus()
        }
      })
      return
    }

    const dirtyNotes = items.filter((item) => (
      Object.prototype.hasOwnProperty.call(noteDrafts, item.id)
      && (noteDrafts[item.id] ?? '') !== (item.note || '')
    ))
    if (dirtyNotes.length) {
      setSavingNotes(true)
      try {
        await Promise.all(dirtyNotes.map((item) => api.patch(
          `/fleet/inspections/${inspectionId}/items/${item.id}`,
          { note: noteDrafts[item.id] ?? '' },
        )))
        await inspectionQuery.refetch()
      } catch (error) {
        const apiError = error as AxiosError<{ detail?: string }>
        toast.error(apiError.response?.data?.detail || 'Inspection notes could not be saved. Try again before completing.')
        return
      } finally {
        setSavingNotes(false)
      }
    }

    setShowErrors(false)
    setConfirming(true)
  }

  const hasUnit = !!insp?.vehicle_unit_number
  const unitLabel = insp ? (hasUnit ? insp.vehicle_unit_number! : `${insp.vehicle_make} ${insp.vehicle_model}`.trim()) : ''
  const makeModel = insp && hasUnit ? `${insp.vehicle_year ? `${insp.vehicle_year} ` : ''}${insp.vehicle_make} ${insp.vehicle_model}`.trim() : ''
  const statusText = !allMarked
    ? `${remaining} check${remaining === 1 ? '' : 's'} remaining`
    : failCount > 0 ? `${failCount} item${failCount === 1 ? '' : 's'} flagged — ready to review` : 'All clear — ready to submit'
  const inspectionIcon = !insp
    ? <Spinner size="sm" />
    : !done
      ? <ClipboardList size={18} className="text-[var(--yellow)]" />
      : insp.result === 'pass'
        ? <CheckCircle2 size={18} className="text-[var(--st-active)]" />
        : insp.result === 'fail'
          ? <AlertTriangle size={18} className="text-[var(--red)]" />
          : <ClipboardList size={18} className="text-[var(--muted-2)]" />

  const inspectionHeader = insp && !done ? (
    <div className="ip-sidekick-progress">
      <div className="ip-progress" role="progressbar" aria-label="Inspection progress" aria-valuemin={0} aria-valuemax={total} aria-valuenow={doneCount}>
        <div className="ip-track" aria-hidden="true"><div className="ip-fill" style={{ width: `${progressPct}%` }} /></div>
        <div className="ip-count">{doneCount}<span>/{total}</span></div>
      </div>
      <div className="ip-bulk">
        <button className="ip-markall" onClick={markAllPass} disabled={bulk.isPending}>
          <Check size={14} strokeWidth={3} /> MARK ALL PASS
        </button>
        <button className="ip-reset" onClick={resetAll} disabled={bulk.isPending} title="Reset all" aria-label="Reset all inspection results"><RotateCcw size={16} /></button>
      </div>
    </div>
  ) : undefined

  const inspectionFooter = !insp ? undefined : (
    <div className="ip-foot ip-foot-sidekick">
      {done ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {insp.repair_order_id ? (
            <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6, fontSize: 13, fontWeight: 600, color: 'var(--st-active)' }}>
              <Wrench size={15} /> Repair order created
            </span>
          ) : failCount > 0 ? (
            <button className="ip-cta" onClick={() => createWO.mutate()} disabled={createWO.isPending}>
              {createWO.isPending ? <Spinner size="sm" /> : <Wrench size={15} />} Create repair order · {failCount} item{failCount === 1 ? '' : 's'}
            </button>
          ) : null}
          <button className="ip-cta ip-cta-ghost" onClick={onClose}>Close</button>
        </div>
      ) : confirming ? (
        <>
          <div className={'ip-review ' + (computedResult === 'fail' ? 'is-fail' : 'is-pass')}>
            <div className="ip-review-title">
              {computedResult === 'fail' ? <XCircle size={17} /> : <CheckCircle2 size={17} />}
              Will be recorded as {computedResult === 'fail' ? 'FAILED' : 'PASSED'}
            </div>
            <div className="ip-review-meta">
              {passCount} passed · {failCount} failed · {naCount} N/A · odometer {fmt(odoNum)} mi
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="ip-cta ip-cta-ghost" style={{ flex: 1 }} disabled={complete.isPending} onClick={() => setConfirming(false)}>Back</button>
            <button className="ip-cta" style={{ flex: 2 }} disabled={complete.isPending} onClick={() => complete.mutate()}>
              {complete.isPending ? <Spinner size="sm" /> : <Check size={16} strokeWidth={3} />} Confirm &amp; submit
            </button>
          </div>
        </>
      ) : (
        <>
          <div className={'ip-status' + (showErrors && problems.length ? ' warn' : '')}>
            {showErrors && problems.length ? `Can't complete yet — ${problems.join(' · ')}.` : statusText}
          </div>
          <button className="ip-cta" onClick={() => { void reviewAndComplete() }} disabled={patchItem.isPending || bulk.isPending || savingNotes}>
            {(patchItem.isPending || bulk.isPending || savingNotes) ? <Spinner size="sm" /> : <Check size={16} strokeWidth={3} />}
            {(patchItem.isPending || bulk.isPending || savingNotes) ? 'Saving inspection…' : 'Review & complete'}
          </button>
        </>
      )}
    </div>
  )

  return (
    <SidekickPanel
      title={insp ? unitLabel : 'Weekly inspection'}
      subtitle={insp ? 'Weekly inspection' : 'Loading inspection'}
      icon={inspectionIcon}
      onClose={onClose}
      width="max-w-full sm:max-w-[94vw] lg:max-w-[760px]"
      headerExtra={inspectionHeader}
      footer={inspectionFooter}
      variant="checklist"
      tone={done && insp?.result === 'fail' ? 'safety' : 'inspection'}
    >
      <div className="ip-frame ip-frame-sidekick">
        {inspectionQuery.isLoading ? (
          <div className="loader" style={{ margin: 'auto' }}><Spinner size="md" /></div>
        ) : inspectionQuery.isError ? (
          <div className="query-failure ip-query-failure" role="alert">
            <AlertTriangle size={20} aria-hidden="true" />
            <div className="query-failure-copy">
              <strong>Inspection could not be loaded</strong>
              <span>No checklist results were changed. Check the connection and try again.</span>
            </div>
            <button type="button" className="query-retry" onClick={() => { void inspectionQuery.refetch() }} disabled={inspectionQuery.isFetching}>
              {inspectionQuery.isFetching ? <Spinner size="xs" /> : <RotateCcw size={14} />}
              {inspectionQuery.isFetching ? 'Retrying…' : 'Try again'}
            </button>
          </div>
        ) : !insp ? (
          <div className="empty-note">This inspection is no longer available.</div>
        ) : (
          <>
            <div className="ip-body">
              {makeModel && <div className="ip-context">{makeModel}</div>}
              {done && (
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '10px 2px 4px' }}>
                  <span className={'part-w ' + (insp.result === 'fail' ? 'w-off' : 'w-on')} style={{ textTransform: 'uppercase' }}>{insp.result || 'completed'}</span>
                  <span style={{ fontSize: 13, color: 'var(--muted)' }}>
                    {insp.odometer != null ? `${fmt(insp.odometer)} mi` : '—'} · {insp.performed_at ? fmtDate(insp.performed_at) : '—'}
                  </span>
                </div>
              )}
              {!done && (
                <div className="ip-odo">
                  <div className="ip-odo-card">
                    <span className="ip-odo-k">Previous odometer</span>
                    <span className="ip-odo-v">
                      {currentOdometer != null ? `${fmt(currentOdometer)} mi` : 'None on record'}
                      {lastReadingDate && <span> · {fmtDate(lastReadingDate)}</span>}
                    </span>
                  </div>
                  <label className="ip-odo-field" htmlFor={`inspection-odometer-${inspectionId}`}>
                    <span className="ip-odo-k ip-odo-label">Current odometer</span>
                    <input id={`inspection-odometer-${inspectionId}`} ref={odoRef} className={'ip-odo-input' + (odoError ? ' err' : '')}
                      value={odometer} inputMode="numeric" placeholder="Enter mileage"
                      aria-invalid={odoError || undefined}
                      onChange={(e) => setOdometer(e.target.value)} />
                  </label>
                  {odoBackwards && (
                    <p className="ip-odo-error">
                      Below the previous {fmt(currentOdometer as number)} mi — odometers don't go backwards, check the reading.
                    </p>
                  )}
                </div>
              )}
              {cats.map((cat) => {
                const its = grouped[cat]
                const complete = secComplete(cat)
                const catHasPending = its.some((i) => i.result === 'pending')
                // Force the section open when we're pointing out its unmarked items.
                const collapsedNow = !done && isCollapsed(cat) && !(showErrors && catHasPending && cat === firstPendingCat)
                const sum = secSummary(cat)
                const categoryPanelId = `inspection-${inspectionId}-${cat.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`
                return (
                  <div key={cat} className="ip-sec">
                    <button
                      type="button"
                      className={'ip-sec-head' + (complete ? ' done' : '')}
                      onClick={() => toggleSection(cat)}
                      aria-expanded={!collapsedNow}
                      aria-controls={categoryPanelId}
                    >
                      <span className="ip-sec-name">{cat}</span>
                      <span className="ip-sec-meta">
                        <span className="ip-sec-sum" style={{ color: sum.color }}>{sum.text}</span>
                        <ChevronDown className="ip-sec-chevron" size={16} aria-hidden="true" />
                      </span>
                    </button>
                    {!collapsedNow && (
                      <div className="ip-sec-body" id={categoryPanelId}>
                        {its.map((item) => {
                          const noteVal = noteDrafts[item.id] ?? (item.note || '')
                          const itemErr = showErrors && item.result === 'pending'
                          return (
                            <div key={item.id} className={'ip-item' + (itemErr ? ' err' : '')}
                              ref={item.id === firstPendingId ? firstErrorRef : undefined}>
                              <div className="ip-item-label">
                                {item.is_warning_light && (
                                  <span title="Dashboard warning light" style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 10, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--yellow)', background: 'rgba(245,179,1,.14)', border: '1px solid rgba(245,179,1,.35)', borderRadius: 999, padding: '1px 7px', marginRight: 8, verticalAlign: 'middle' }}>⚠ Light</span>
                                )}
                                {item.label}
                                {itemErr && <span style={{ color: 'var(--red)', fontWeight: 700, fontSize: 11, marginLeft: 8, letterSpacing: '.04em' }}>· NOT SET</span>}
                              </div>
                              {done ? (
                                <div style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase',
                                  color: item.result === 'fail' ? 'var(--red)' : item.result === 'na' ? 'var(--muted)' : 'var(--st-active)' }}>
                                  {item.result === 'na' ? 'N/A' : item.result}
                                  {item.note && <span style={{ display: 'block', fontWeight: 400, textTransform: 'none', color: 'var(--muted)', marginTop: 4 }}>{item.note}</span>}
                                </div>
                              ) : (
                                <>
                                  <div className={'ip-btns sel-' + item.result} role="group" aria-label={`${item.label} result`}>
                                    <button type="button" className={'ip-choice pass' + (item.result === 'pass' ? ' is-on' : '')} onClick={() => setStatus(item, 'pass')} title="Pass" aria-pressed={item.result === 'pass'} disabled={patchItem.isPending || bulk.isPending}>
                                      <Check size={16} strokeWidth={3} /> <span className="ip-choice-tx">PASS</span>
                                    </button>
                                    <button type="button" className={'ip-choice fail' + (item.result === 'fail' ? ' is-on' : '')} onClick={() => setStatus(item, 'fail')} title="Fail" aria-pressed={item.result === 'fail'} disabled={patchItem.isPending || bulk.isPending}>
                                      <X size={18} /> <span className="ip-choice-tx">FAIL</span>
                                    </button>
                                    <button type="button" className={'ip-choice na' + (item.result === 'na' ? ' is-on' : '')} onClick={() => setStatus(item, 'na')} title="N/A" aria-pressed={item.result === 'na'} disabled={patchItem.isPending || bulk.isPending}>
                                      <Minus size={18} /> <span className="ip-choice-tx">N/A</span>
                                    </button>
                                  </div>
                                  {item.result === 'fail' && (
                                    <div className="ip-flag">
                                      <input value={noteVal}
                                        onChange={(e) => setNoteDrafts((d) => ({ ...d, [item.id]: e.target.value }))}
                                        onBlur={() => { if ((noteDrafts[item.id] ?? '') !== (item.note || '')) patchItem.mutate({ itemId: item.id, note: noteDrafts[item.id] ?? '' }) }}
                                        placeholder="What's wrong? (quick note)" />
                                    </div>
                                  )}
                                </>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })}

            </div>

          </>
        )}
      </div>
    </SidekickPanel>
  )
}
