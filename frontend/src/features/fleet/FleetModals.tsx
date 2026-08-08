import { useEffect, useState, useRef } from 'react'
import { Spinner } from '@/components/ui'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  X, Pencil, AlertTriangle, ClipboardCheck, CheckCircle2, XCircle, Plus, ClipboardList, Trash2, UserRound, Play, Flag, Calendar,
  Check, Minus, RotateCcw, Wrench, Camera, Search, ChevronDown,
} from 'lucide-react'
import api from '../../lib/api'
import SlidePanel from '@/components/SlidePanel'
import BaseSelect from '@/components/BaseSelect'
import QuantityStepper from '@/components/QuantityStepper'
import DurationStepper from '@/components/DurationStepper'
import SuggestingTextarea from '@/components/SuggestingTextarea'
import MapboxAddressInput from '@/components/MapboxAddressInput'
import { useAuthStore } from '../../stores/authStore'
import type {
  BoardTruck, TruckDetail, Inspection, InspectionDetail, InspectionItem, InspectionItemResult, InspectionResult, IncidentSeverity, IncidentEntry,
  PMServiceEntry,
} from './types'
import { fleetUnitLabel, fmtDate, money, fmt } from './helpers'
import { formatHoursMinutes } from '@/lib/durationFormat'
import { isSupportedPhotoFile, runPhotoUploadQueue, uploadDirectPhoto, type PhotoUploadStatus } from '@/lib/photoUpload'
import { formatUSPhone } from '@/utils/phone'
import { duplicateVinConflict, duplicateVinTruckLabel, type DuplicateVinConflict } from './duplicateVin'
import type { QueryClient } from '@tanstack/react-query'

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
export function Modal({ title, icon, onClose, children, width = 480, scrollable = true }: {
  title: string; icon: React.ReactNode; onClose: () => void; children: React.ReactNode; width?: number; scrollable?: boolean
}) {
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.6)', zIndex: 60, display: 'grid', placeItems: 'center' }} onClick={onClose}>
      <div
        className="dsec"
        style={{
          width,
          maxWidth: '92vw',
          maxHeight: scrollable ? '88vh' : undefined,
          overflowY: scrollable ? 'auto' : 'visible',
          overflowX: 'hidden',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="dsec-head">
          <div className="dsec-title">{icon}<h3>{title}</h3></div>
          <button className="person-call" onClick={onClose}><X size={18} /></button>
        </div>
        {children}
      </div>
    </div>
  )
}

/* Centered confirmation modal (styled — replaces window.confirm). */
export function ConfirmModal({ title, message, confirmLabel = 'Delete', pending, onConfirm, onClose }: {
  title: string; message: string; confirmLabel?: string; pending?: boolean; onConfirm: () => void; onClose: () => void
}) {
  return (
    <Modal title={title} icon={<Trash2 size={17} />} onClose={onClose} width={420}>
      <p style={{ fontSize: 14, color: 'var(--muted)', lineHeight: 1.5, marginBottom: 20 }}>{message}</p>
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
        <button className="dbtn dbtn-ghost" onClick={onClose} disabled={pending}>Cancel</button>
        <button
          onClick={onConfirm}
          disabled={pending}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 8, height: 42, padding: '0 17px',
            borderRadius: 10, fontSize: 13.5, fontWeight: 700, border: 'none',
            background: 'var(--red)', color: '#fff', cursor: 'pointer', opacity: pending ? 0.6 : 1,
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

const yellowBtn = 'dbtn dbtn-yellow'
const ghostBtn = 'dbtn dbtn-ghost'

/* Two-step inline confirmation — replaces a browser confirm() pop-up. The
   caller renders its own trigger button via renderTrigger(arm). */
function InlineConfirm({ renderTrigger, message, confirmLabel, onConfirm, pending, danger }: {
  renderTrigger: (arm: () => void) => React.ReactNode
  message: string
  confirmLabel: string
  onConfirm: () => void
  pending?: boolean
  danger?: boolean
}) {
  const [armed, setArmed] = useState(false)
  if (!armed) return <>{renderTrigger(() => setArmed(true))}</>
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>{message}</span>
      <button className={ghostBtn} style={{ height: 30, padding: '0 10px', fontSize: 12 }} disabled={pending} onClick={() => setArmed(false)}>
        Cancel
      </button>
      <button
        className={ghostBtn}
        style={{ height: 30, padding: '0 10px', fontSize: 12, color: danger ? 'var(--red)' : 'var(--yellow)' }}
        disabled={pending}
        onClick={onConfirm}
      >
        {pending ? <Spinner size="xs" /> : null} {confirmLabel}
      </button>
    </span>
  )
}

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
    <Modal title={`Edit ${fleetUnitLabel(truck)}`} icon={<Pencil size={17} />} onClose={onClose} width={520}>
      <div className="dmap-side-h" style={{ marginBottom: 8 }}>Identity</div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
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
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
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
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
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
      <button className={yellowBtn} style={{ marginTop: 14, width: '100%', justifyContent: 'center' }} disabled={save.isPending} onClick={() => save.mutate()}>
        {save.isPending ? <Spinner size="sm" /> : <Pencil size={15} />} Save changes
      </button>
    </Modal>
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
  const { data = [] } = useQuery<VehicleAccountRelationship[]>({
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
  return [...byCustomer.values()]
}

/* Width of the work order drawer, matched to the garage-side repair order
   drawer so the same record reads the same on both sides of the product. */
const WO_DRAWER_WIDTH = 'max-w-full sm:max-w-[94vw] lg:max-w-[760px] xl:max-w-[860px]'

/* Complaints a fleet manager types over and over, standing at the truck. Tapping
   one beats spelling it out on a tablet keyboard; they stay editable after. */
const COMPLAINT_CHIPS = [
  'Air leak', 'Brakes', 'Check engine light', 'DOT inspection due', 'Tires',
  'Lights out', 'Coolant leak', 'A/C not cooling', "Won't start", 'Oil leak',
]

/**
 * Creating a work order used to end at a toast: the modal closed, and the
 * manager had to walk back into the truck and reopen the order to assign it,
 * scope it, or start it. This drawer is one surface with two states — scope it,
 * then keep working in the same panel once it exists.
 */
export function NewWorkOrderModal({ truck, onClose, onCreated }: {
  truck: BoardTruck; onClose: () => void; onCreated: (repairOrderId?: string) => void
}) {
  const qc = useQueryClient()
  const [description, setDescription] = useState('')
  const [selectedServices, setSelectedServices] = useState<string[]>([])
  const [serviceQuery, setServiceQuery] = useState('')
  const [mechanicId, setMechanicId] = useState('')
  const [billingOpen, setBillingOpen] = useState(false)
  // Once created, the same drawer becomes the live work order — no close, no
  // reopen, no hunting for it on the truck.
  const [created, setCreated] = useState<{ repairOrderId: string; orderNumber: string } | null>(null)

  const billToOptions = useTruckBillToOptions(truck.id)
  const [billToCustomerId, setBillToCustomerId] = useState('')
  useEffect(() => {
    if (!billToCustomerId && billToOptions.length) {
      const preferred = billToOptions.find((item) => item.relationship_type === 'default_payer' && item.is_primary)
        || billToOptions.find((item) => item.relationship_type === 'operator')
        || billToOptions[0]
      setBillToCustomerId(preferred.customer_id)
    }
  }, [billToCustomerId, billToOptions])

  const { data: services } = useQuery<PMServiceEntry[]>({
    queryKey: ['fleet-service-catalog'],
    queryFn: async () => (await api.get('/fleet/service-catalog')).data,
  })
  const { data: mechanics } = useQuery<WOMechanic[]>({
    queryKey: ['fleet-mechanics'],
    queryFn: async () => (await api.get('/fleet/mechanics')).data,
  })
  const catalog = services || []
  const normalizedQuery = serviceQuery.trim().toLowerCase()
  const visibleServices = normalizedQuery
    ? catalog.filter((service) => service.name.toLowerCase().includes(normalizedQuery))
    : catalog
  const toggleService = (id: string) =>
    setSelectedServices((current) => current.includes(id) ? current.filter((x) => x !== id) : [...current, id])

  const appendComplaint = (chip: string) =>
    setDescription((current) => (current.trim() ? `${current.replace(/[;\s]+$/, '')}; ${chip}` : chip))

  const billToLabel = billToOptions.find((item) => item.customer_id === billToCustomerId)?.customer_company_name
    || 'Truck default'

  const create = useMutation({
    mutationFn: async () => (await api.post(`/fleet/trucks/${truck.id}/work-order`, {
      description: description.trim(),
      bill_to_customer_id: billToCustomerId || undefined,
      service_ids: selectedServices.length ? selectedServices : undefined,
    })).data as BoardTruck & { created_work_order?: { id: string; repair_order_id: string } },
    onSuccess: async (result) => {
      const madeOrder = result.created_work_order
      if (!madeOrder) {
        // Older API without the created order — fall back to the old behavior
        // rather than stranding the manager on a drawer with nothing in it.
        toast.success('Repair order created')
        invalidateFleetAndCockpit(qc)
        onCreated()
        onClose()
        return
      }
      // Assigning uses the same endpoint the panel does, so one code path owns
      // assignment and this drawer never drifts from it.
      if (mechanicId) {
        try {
          await api.post(`/repair-orders/${madeOrder.repair_order_id}/assign-mechanic`, { mechanic_id: mechanicId })
        } catch (error) {
          const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
          toast.error(detail || 'Repair order created, but assigning the mechanic failed')
        }
      }
      toast.success(`Work order ${madeOrder.id} created`)
      invalidateFleetAndCockpit(qc)
      onCreated(madeOrder.repair_order_id)
      setCreated({ repairOrderId: madeOrder.repair_order_id, orderNumber: madeOrder.id })
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to create repair order'),
  })

  const scopeFooter = (
    <div className="wo-drawer-actions">
      <button className={ghostBtn} onClick={onClose} disabled={create.isPending}>Cancel</button>
      <button
        className={yellowBtn}
        disabled={create.isPending || !description.trim()}
        onClick={() => create.mutate()}
      >
        {create.isPending ? <Spinner size="sm" /> : <ClipboardList size={15} />} Create repair order
      </button>
    </div>
  )

  return (
    <SlidePanel
      isOpen
      dark
      onClose={onClose}
      width={WO_DRAWER_WIDTH}
      subtitle={created ? fleetUnitLabel(truck) : 'New repair order'}
      title={created ? created.orderNumber : fleetUnitLabel(truck)}
      headerIcon={<ClipboardList size={18} className="text-[var(--yellow)]" />}
      footer={created ? (
        <div className="wo-drawer-actions">
          <button className={yellowBtn} onClick={onClose}>Done</button>
        </div>
      ) : scopeFooter}
    >
      {created ? (
        <div className="wo-drawer-body wo-state-enter" key="live">
          <WorkOrderBody repairOrderId={created.repairOrderId} onClose={onClose} onChanged={() => onCreated()} />
        </div>
      ) : (
        <div className="wo-drawer-body wo-state-enter" key="scope">
          {/* The drawer's header already names the truck. Repeating it here put
              the same string on screen twice, 90px apart — the strip carries
              only what the header cannot: the vehicle and its odometer. */}
          <div className="wo-truckstrip">
            <span>{[truck.year, truck.make, truck.model].filter(Boolean).join(' ') || 'Truck'}</span>
            {truck.odometer != null && <span>{fmt(truck.odometer)} mi</span>}
          </div>

          <div className="wo-scope">
            <section className="wo-scope-main">
              <Field label="What's the work / complaint?">
                <SuggestingTextarea
                  value={description}
                  onChange={setDescription}
                  rows={4}
                  placeholder="e.g. Air leak on front brake chamber; DOT inspection due; check engine light"
                  style={{
                    width: '100%', background: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 9,
                    color: 'var(--text)', padding: '12px 14px', font: 'inherit', resize: 'vertical', minHeight: 104,
                  }}
                />
                <div className="wo-chips">
                  {COMPLAINT_CHIPS.map((chip) => (
                    <button type="button" key={chip} className="wo-chip" onClick={() => appendComplaint(chip)}>
                      <Plus size={13} /> {chip}
                    </button>
                  ))}
                </div>
              </Field>
            </section>

            <section className="wo-scope-side">
              <Field label={`Services${selectedServices.length ? ` · ${selectedServices.length} selected` : ' (optional)'}`}>
                {catalog.length > 8 && (
                  <div className="wo-svc-search">
                    <Search size={16} aria-hidden="true" />
                    <input
                      value={serviceQuery}
                      onChange={(event) => setServiceQuery(event.target.value)}
                      placeholder="Filter services…"
                      aria-label="Filter services"
                    />
                  </div>
                )}
                <div className="pm-svc-list wo-svc-list">
                  {catalog.length === 0 ? (
                    <div className="pm-svc-empty">No services in the catalog yet — you can add labor and parts once the order is open.</div>
                  ) : visibleServices.length === 0 ? (
                    <div className="pm-svc-empty">No service matches “{serviceQuery.trim()}”.</div>
                  ) : (
                    visibleServices.map((service) => {
                      const on = selectedServices.includes(service.service_id)
                      return (
                        <button
                          type="button"
                          key={service.service_id}
                          className={'pm-svc-row' + (on ? ' on' : '')}
                          onClick={() => toggleService(service.service_id)}
                          aria-pressed={on}
                        >
                          <span className="pm-svc-check">{on && <Check size={13} />}</span>
                          <span className="pm-svc-name">{service.name}</span>
                          {service.duration_minutes ? <span className="pm-svc-dur">{service.duration_minutes}m</span> : null}
                        </button>
                      )
                    })
                  )}
                </div>
                <p className="wo-hint">Each service adds its labor time and parts to the order, so it opens costed.</p>
              </Field>
            </section>

            <section className="wo-scope-main-b">
              <Field label="Assign a mechanic (optional)">
                <select value={mechanicId} onChange={(event) => setMechanicId(event.target.value)} className="wo-select">
                  <option value="">Leave unassigned</option>
                  {(mechanics || []).map((mechanic) => (
                    <option key={mechanic.id} value={mechanic.id}>{mechanic.name}</option>
                  ))}
                </select>
                <p className="wo-hint">You can start and finish an internal order without assigning anyone.</p>
              </Field>

              {/* Billing already defaults correctly and rarely changes; asking
                  for it every time taxes the case that never needs it. */}
              <div className="wo-billing">
                <button type="button" className="wo-billing-toggle" onClick={() => setBillingOpen((open) => !open)} aria-expanded={billingOpen}>
                  <span>
                    <span className="id-k">Invoice to</span>
                    <strong>{billToLabel}</strong>
                  </span>
                  <ChevronDown size={16} className={billingOpen ? 'wo-billing-caret is-open' : 'wo-billing-caret'} />
                </button>
                {billingOpen && (
                  <div className="wo-billing-body">
                    <select value={billToCustomerId} onChange={(event) => setBillToCustomerId(event.target.value)} className="wo-select">
                      <option value="">Use truck default</option>
                      {billToOptions.map((relationship) => (
                        <option key={relationship.customer_id} value={relationship.customer_id}>
                          {relationship.customer_company_name || 'Company'}
                        </option>
                      ))}
                    </select>
                    <p className="wo-hint">
                      The truck keeps one service history. Pricing and invoicing follow the company selected for this visit.
                    </p>
                  </div>
                )}
              </div>
            </section>
          </div>
        </div>
      )}
    </SlidePanel>
  )
}

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
  const billToOptions = useTruckBillToOptions(truck.id)
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
  const toggle = (id: string) =>
    setSelected((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]))

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

  const modalTitle = createMode
    ? `Create PM work order · ${fleetUnitLabel(truck)}`
    : `${rescheduling ? 'Reschedule' : 'Schedule'} PM · ${fleetUnitLabel(truck)}`
  return (
    <Modal title={modalTitle} icon={createMode ? <ClipboardCheck size={17} /> : <Calendar size={17} />} onClose={onClose} width={460}>
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
              <option value="">Use truck default</option>
              {billToOptions.map((relationship) => (
                <option key={relationship.customer_id} value={relationship.customer_id}>
                  {relationship.customer_company_name || 'Company'}
                </option>
              ))}
            </select>
          </Field>
        )}

        <Field label={`PM services${selected.length ? ` · ${selected.length} selected` : ''}`}>
          <div className="pm-svc-list">
            {activeServices.length === 0 ? (
              <div className="pm-svc-empty">No PM services in the catalog yet.</div>
            ) : (
              activeServices.map((s) => {
                const on = selected.includes(s.service_id)
                return (
                  <button
                    type="button"
                    key={s.service_id}
                    className={'pm-svc-row' + (on ? ' on' : '')}
                    onClick={() => toggle(s.service_id)}
                  >
                    <span className="pm-svc-check">{on && <Check size={13} />}</span>
                    <span className="pm-svc-name">{s.name}</span>
                    {s.duration_minutes ? <span className="pm-svc-dur">{s.duration_minutes}m</span> : null}
                  </button>
                )
              })
            )}
          </div>
        </Field>

        {changedFromDefault && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text)', cursor: 'pointer' }}>
            <input type="checkbox" checked={saveAsDefault} onChange={(e) => setSaveAsDefault(e.target.checked)} style={{ width: 'auto' }} />
            Save these services as this truck's default PM package
          </label>
        )}
        {/* In create mode the work order is always created — no need to offer it
            as a toggle. */}
        {!createMode && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text)', cursor: 'pointer' }}>
            <input type="checkbox" checked={createWO} onChange={(e) => setCreateWO(e.target.checked)} style={{ width: 'auto' }} />
            Create the PM work order now
          </label>
        )}
      </div>
      <p style={{ fontSize: 12, color: 'var(--muted-2)', marginTop: 10 }}>
        {createMode
          ? "Creates the maintenance repair order now. The next PM rolls forward automatically when this repair order is completed."
          : "PM shows as due when either the date or the odometer is reached. Completing a PM rolls both forward by the interval."}
      </p>
      <button className={yellowBtn} style={{ marginTop: 14, width: '100%', justifyContent: 'center' }} disabled={save.isPending} onClick={() => save.mutate()}>
        {save.isPending ? <Spinner size="sm" /> : (createMode ? <ClipboardCheck size={15} /> : <Calendar size={15} />)} {createMode ? 'Create repair order' : (createWO ? `${rescheduling ? 'Reschedule' : 'Schedule'} + create repair order` : 'Save schedule')}
      </button>
    </Modal>
  )
}

/* ---------- Work order panel (view / describe / assign mechanic / cost) ---------- */

const WO_STATUS_LABEL: Record<string, string> = {
  draft: 'Draft', assigned: 'Assigned', acknowledged: 'Acknowledged',
  in_progress: 'In progress', pending_review: 'Pending review',
  completed: 'Completed', invoiced: 'Invoiced', paid: 'Paid', cancelled: 'Cancelled',
}

interface WOMechanic { id: string; name: string }
interface WOLabor { id: string; description: string; hours: number | string; hourly_rate: number | string; total_cost: number | string }
interface WOPart { id: string; inventory_name: string; quantity: number | string; unit_price: number | string; total_price: number | string }
interface WODetail {
  id: string; order_number: string; status: string; description?: string | null
  assigned_mechanic_id?: string | null
  total_parts_cost: number | string; total_labor_cost: number | string; total_cost: number | string
  is_pm?: boolean
  bill_labor_at_customer_rate?: boolean
  mileage_in?: number | null; mileage_out?: number | null
  labor_items: WOLabor[]; parts_usage: WOPart[]
}

interface WOInventory { id: string; name: string; sku: string; cost: number | string; selling_price: number | string; stock_quantity: number }

const toNum = (v: number | string | null | undefined) => (v == null ? 0 : Number(v))
const costInput: React.CSSProperties = {
  height: 34, background: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 8,
  color: 'var(--text)', padding: '0 8px', font: 'inherit', fontSize: 13,
}
// Row remove/delete button — sized as a proper touch target (gloved shop hands),
// matching the 42px controls in the same rows.
const iconBtn: React.CSSProperties = {
  background: 'rgba(248,113,113,0.10)', border: '1px solid rgba(248,113,113,0.28)', borderRadius: 8,
  cursor: 'pointer', display: 'grid', placeItems: 'center', width: 42, height: 42, flex: 'none',
}

function LaborAddRow({ roId, laborRate, onChanged }: { roId: string; laborRate: number; onChanged: () => void }) {
  const [desc, setDesc] = useState('')
  const [hours, setHours] = useState(0.5) // sensible starting duration; step from here
  const add = useMutation({
    mutationFn: async () => (await api.post(`/repair-orders/${roId}/labor`, {
      description: desc.trim() || undefined, hours, hourly_rate: laborRate,
    })).data,
    onSuccess: () => { toast.success('Labor added'); setDesc(''); setHours(0.5); onChanged() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to add labor'),
  })
  const valid = hours > 0
  return (
    <div style={{ marginTop: 6 }}>
      <div className="wo-addrow">
        <input style={{ ...costInput, flex: 1, minWidth: 0, height: 42 }} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Labor description" />
        {/* Local-only until "Add" — no per-click server write, so no debounce.
            Rate isn't shown on the row; it follows the repair order's snapshot,
            surfaced as a tooltip instead of taking a column. */}
        <span title={`Billed at ${money(laborRate)}/h`} style={{ display: 'inline-flex' }}>
          <DurationStepper
            hours={hours}
            onChange={setHours}
            stepMinutes={15}
            minMinutes={15}
            ariaLabel="Labor duration"
            theme="dark"
          size="lg"
          />
        </span>
        {/* Labeled so it reads as "add this line" — not another stepper +. */}
        <button className={ghostBtn} style={{ height: 42, padding: '0 16px', fontSize: 13, fontWeight: 600 }} disabled={!valid || add.isPending} onClick={() => add.mutate()}>
          {add.isPending ? <Spinner size="xs" /> : 'Add'}
        </button>
      </div>
      {laborRate <= 0 && (
        <p className="id-k" style={{ textTransform: 'none', letterSpacing: 0, marginTop: 5, color: '#fb923c' }}>
          This work order's labor rate is $0 — set the applicable shop rate before billing.
        </p>
      )}
    </div>
  )
}

function LaborRow({ roId, line, onChanged, showPrices = true }: { roId: string; line: WOLabor; onChanged: () => void; showPrices?: boolean }) {
  // Read-only summary: the duration was set when the line was added (via the add
  // row's stepper, or fixed by the service). To change it, delete and re-add.
  const del = useMutation({
    mutationFn: async () => (await api.delete(`/repair-orders/${roId}/labor/${line.id}`)).data,
    onSuccess: () => { toast.success('Labor removed'); onChanged() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to remove'),
  })
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 14 }}>
      <span style={{ flex: 1, color: 'var(--text)' }}>{line.description || 'Labor'}</span>
      {/* Rate is a tooltip, not a column. */}
      <span
        title={showPrices ? `Billed at ${money(toNum(line.hourly_rate))}/h (in-house labor rate)` : undefined}
        style={{ color: 'var(--muted)', fontVariantNumeric: 'tabular-nums' }}
      >
        {formatHoursMinutes(toNum(line.hours))}
      </span>
      {showPrices && <strong style={{ width: 78, textAlign: 'right', color: 'var(--text)', fontSize: 15 }}>{money(toNum(line.total_cost))}</strong>}
      {/* Deleting the whole repair order asks twice; removing a costed line used
          to ask nothing, though it edits a record that feeds invoicing. */}
      <InlineConfirm
        danger
        message="Remove this labor line?"
        confirmLabel="Remove"
        pending={del.isPending}
        onConfirm={() => del.mutate()}
        renderTrigger={(arm) => (
          <button style={iconBtn} className="icon-hit" title="Remove" disabled={del.isPending} onClick={arm}>
            <Trash2 size={18} color="var(--muted-2)" />
          </button>
        )}
      />
    </div>
  )
}

function ServiceAddRow({ roId, onChanged }: { roId: string; onChanged: () => void }) {
  const [serviceId, setServiceId] = useState('')
  const { data: services } = useQuery<PMServiceEntry[]>({
    queryKey: ['fleet-service-catalog'],
    queryFn: async () => (await api.get('/fleet/service-catalog')).data,
  })
  const add = useMutation({
    mutationFn: async () => (await api.post(`/fleet/work-orders/${roId}/add-service`, { service_id: serviceId })).data,
    onSuccess: () => { toast.success('Service added'); setServiceId(''); onChanged() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to add service'),
  })
  return (
    <div className="wo-addrow" style={{ marginTop: 6 }}>
      {/* Searchable so a long service catalog is filterable by name. */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <BaseSelect
          variant="dark"
          placeholder="Add service from catalog…"
          value={serviceId}
          onChange={setServiceId}
          options={(services || []).map((s) => ({
            value: s.service_id,
            label: s.name,
            subLabel: s.duration_minutes ? `${s.duration_minutes}m` : undefined,
          }))}
        />
      </div>
      <button className={ghostBtn} style={{ height: 42, padding: '0 16px', fontSize: 13, fontWeight: 600 }} disabled={serviceId === '' || add.isPending} onClick={() => add.mutate()}>
        {add.isPending ? <Spinner size="xs" /> : 'Add'}
      </button>
    </div>
  )
}

function PartAddRow({ roId, inventory, onChanged }: { roId: string; inventory: WOInventory[]; onChanged: () => void }) {
  const [invId, setInvId] = useState('')
  const [qty, setQty] = useState('1')
  const add = useMutation({
    mutationFn: async () => (await api.post(`/repair-orders/${roId}/parts`, { inventory_id: invId, quantity: Number(qty) })).data,
    onSuccess: () => { toast.success('Part added'); setInvId(''); setQty('1'); onChanged() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to add part'),
  })
  const valid = invId !== '' && Number(qty) > 0
  return (
    <div className="wo-addrow" style={{ marginTop: 6 }}>
      {/* Searchable so a long inventory is findable by name or SKU. Internal fleet
          repairs are costed at the part's cost, not list price. (This BaseSelect
          replaces the earlier native <select> overflow fix — it manages its own
          width and portals the menu, so it can't grow a scrollbar either.) */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <BaseSelect
          variant="dark"
          placeholder="Add part from inventory…"
          value={invId}
          onChange={setInvId}
          options={inventory.map((i) => ({
            value: i.id,
            label: i.name,
            subLabel: `${i.sku} · ${money(toNum(i.cost))} cost`,
            searchText: i.sku,
          }))}
        />
      </div>
      {/* Local-only until "Add" is clicked — no per-click server write, so no debounce.
          Disabled until a part is chosen: no point setting a quantity for nothing. */}
      <QuantityStepper
        value={Number(qty) || 1}
        onChange={(n) => setQty(String(Math.max(1, n)))}
        min={1}
        step={1}
        unitLabel=""
        ariaLabel="Part quantity"
        align="start"
        theme="dark"
        size="lg"
        disabled={invId === ''}
      />
      <button className={ghostBtn} style={{ height: 42, padding: '0 16px', fontSize: 13, fontWeight: 600 }} disabled={!valid || add.isPending} onClick={() => add.mutate()}>
        {add.isPending ? <Spinner size="xs" /> : 'Add'}
      </button>
    </div>
  )
}

function PartRow({ roId, line, onChanged, showPrices = true }: { roId: string; line: WOPart; onChanged: () => void; showPrices?: boolean }) {
  // Read-only summary: quantity was set when the part was added (via the add
  // row's stepper). To change it, remove the line and re-add with the new qty.
  const del = useMutation({
    mutationFn: async () => (await api.delete(`/repair-orders/${roId}/parts/${line.id}`)).data,
    onSuccess: () => { toast.success('Part removed'); onChanged() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to remove'),
  })
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 14 }}>
      <span style={{ flex: 1, color: 'var(--text)' }}>{line.inventory_name}{showPrices ? ` · ${money(toNum(line.unit_price))}` : ''}</span>
      <span style={{ color: 'var(--muted)', fontVariantNumeric: 'tabular-nums' }}>×{toNum(line.quantity)}</span>
      {showPrices && <strong style={{ width: 78, textAlign: 'right', color: 'var(--text)', fontSize: 15 }}>{money(toNum(line.total_price))}</strong>}
      <InlineConfirm
        danger
        message="Remove this part from the order?"
        confirmLabel="Remove"
        pending={del.isPending}
        onConfirm={() => del.mutate()}
        renderTrigger={(arm) => (
          <button style={iconBtn} className="icon-hit" title="Remove" disabled={del.isPending} onClick={arm}>
            <Trash2 size={18} color="var(--muted-2)" />
          </button>
        )}
      />
    </div>
  )
}

/* ---------- PM services picker (draft PM work orders only) ----------
   The services drive the PM: saving re-seeds the labor + parts cost lines, so a
   PM work order is scoped by picking services, not by hand-adding parts. */
function PMServicesSection({ roId, onChanged }: { roId: string; onChanged: () => void }) {
  // Only PM-category services are offered.
  const { data: services } = useQuery<PMServiceEntry[]>({
    queryKey: ['fleet-pm-catalog'],
    queryFn: async () => (await api.get('/fleet/pm-service-catalog')).data,
  })
  const { data: current } = useQuery<{ service_id: string }[]>({
    queryKey: ['fleet-wo-pm-services', roId],
    queryFn: async () => (await api.get(`/fleet/work-orders/${roId}/pm-services`)).data,
  })
  const [selected, setSelected] = useState<string[] | null>(null)
  // Seed the selection from the saved set once it loads.
  const sel = selected ?? (current ? current.map((s) => s.service_id) : [])
  const savedIds = (current || []).map((s) => s.service_id)
  const dirty = selected != null && (
    sel.length !== savedIds.length || sel.some((id) => !savedIds.includes(id))
  )
  const toggle = (id: string) =>
    setSelected(() => (sel.includes(id) ? sel.filter((x) => x !== id) : [...sel, id]))

  const save = useMutation({
    mutationFn: async () => (await api.put(`/fleet/work-orders/${roId}/pm-services`, { service_ids: sel })).data,
    onSuccess: () => { toast.success('PM services updated'); setSelected(null); onChanged() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to update PM services'),
  })

  const active = services || []
  return (
    <Field label={`PM services${sel.length ? ` · ${sel.length} selected` : ''}`}>
      <div className="pm-svc-list">
        {active.length === 0 ? (
          <div className="pm-svc-empty">No PM services in the catalog yet.</div>
        ) : (
          active.map((s) => {
            const on = sel.includes(s.service_id)
            return (
              <button type="button" key={s.service_id} className={'pm-svc-row' + (on ? ' on' : '')} onClick={() => toggle(s.service_id)}>
                <span className="pm-svc-check">{on && <Check size={13} />}</span>
                <span className="pm-svc-name">{s.name}</span>
                {s.duration_minutes ? <span className="pm-svc-dur">{s.duration_minutes}m</span> : null}
              </button>
            )
          })
        )}
      </div>
      <p className="id-k" style={{ textTransform: 'none', letterSpacing: 0, marginTop: 6 }}>
        Selected services seed the labor &amp; parts below at in-house cost.
      </p>
      {dirty && (
        <button className={yellowBtn} style={{ marginTop: 8, height: 34, padding: '0 12px', fontSize: 12.5 }}
          disabled={save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? <Spinner size="xs" /> : <ClipboardCheck size={14} />} Save PM services
        </button>
      )}
    </Field>
  )
}

/**
 * The live work order, as content rather than as a window. Kept separate from
 * its shell so the create flow can resolve into it in place — the manager never
 * closes one surface to open the same order in another.
 */
function WorkOrderBody({ repairOrderId, onClose, onChanged }: {
  repairOrderId: string; onClose: () => void; onChanged: () => void
}) {
  const qc = useQueryClient()
  const num = (v: number | string | null | undefined) => (v == null ? 0 : Number(v))

  const { data: wo, isLoading } = useQuery<WODetail>({
    queryKey: ['fleet-wo', repairOrderId],
    queryFn: async () => (await api.get(`/repair-orders/${repairOrderId}/detail`)).data,
  })
  const { data: mechanics } = useQuery<WOMechanic[]>({
    queryKey: ['fleet-mechanics'],
    queryFn: async () => (await api.get('/fleet/mechanics')).data,
  })
  const { data: inventory } = useQuery<WOInventory[]>({
    queryKey: ['fleet-inventory'],
    queryFn: async () => (await api.get('/inventory', { params: { limit: 100 } })).data,
  })
  const { data: fleetSettings } = useQuery<{ internal_labor_rate: number; labor_rate: number }>({
    queryKey: ['fleet-settings'],
    queryFn: async () => (await api.get('/fleet/settings')).data,
  })
  const internalRate = toNum(fleetSettings?.internal_labor_rate)
  const laborRate = wo?.bill_labor_at_customer_rate
    ? toNum(fleetSettings?.labor_rate)
    : internalRate

  const [description, setDescription] = useState('')
  const [descDirty, setDescDirty] = useState(false)
  const [mileageOut, setMileageOut] = useState('')
  const [armComplete, setArmComplete] = useState(false)
  // Seed the editable description once the work order loads.
  if (wo && !descDirty && description === '') {
    if (wo.description) setDescription(wo.description)
  }

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['fleet-wo', repairOrderId] })
    qc.invalidateQueries({ queryKey: ['fleet-wo-pm-services', repairOrderId] })
    invalidateFleetAndCockpit(qc)
    onChanged()
  }

  const saveDesc = useMutation({
    mutationFn: async () => (await api.put(`/repair-orders/${repairOrderId}`, { description: description.trim() })).data,
    onSuccess: () => { toast.success('Repair order updated'); setDescDirty(false); refresh() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to update'),
  })
  const assign = useMutation({
    mutationFn: async (mechanicId: string) => (await api.post(`/repair-orders/${repairOrderId}/assign-mechanic`, { mechanic_id: mechanicId })).data,
    onSuccess: () => { toast.success('Mechanic assigned'); refresh() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to assign'),
  })
  const del = useMutation({
    mutationFn: async () => (await api.delete(`/repair-orders/${repairOrderId}`)).data,
    onSuccess: () => {
      toast.success(wo?.order_number ? `Repair order ${wo.order_number} deleted` : 'Repair order deleted')
      invalidateFleetAndCockpit(qc)
      onChanged()
      onClose()
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to delete repair order'),
  })
  const startWO = useMutation({
    mutationFn: async () => (await api.post(`/fleet/work-orders/${repairOrderId}/start`)).data,
    onSuccess: () => { toast.success('Repair order in progress'); refresh() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to start repair order'),
  })
  const completeWO = useMutation({
    mutationFn: async (mileageOut?: number | null) =>
      (await api.post(`/fleet/work-orders/${repairOrderId}/complete`,
        { mileage_out: mileageOut ?? null })).data,
    onSuccess: () => {
      toast.success(wo?.order_number ? `Repair order ${wo.order_number} completed` : 'Repair order completed')
      refresh()
      onClose()
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to complete repair order'),
  })

  // Internal fleet work orders can be deleted at any status. The confirmation
  // warns when work has already started, since deleting discards that progress.
  const workStarted = wo ? !['draft', 'quoted'].includes(wo.status) : false

  // Internal cost is owner/admin territory. Fleet managers see the parts &
  // labor that make up the PM (names + quantities) but not the prices.
  const { user } = useAuthStore()
  const showPrices = user?.role === 'garage_owner' || user?.role === 'garage_admin'

  return (
    <>
      {isLoading || !wo ? (
        <div className="loader"><Spinner size="sm" /></div>
      ) : (
        <div className="wo-live">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
            <div className="id-k" style={{ textTransform: 'none', letterSpacing: 0 }}>
              Status: <strong style={{ color: 'var(--text)' }}>{WO_STATUS_LABEL[wo.status] || wo.status}</strong>
              <span style={{ marginLeft: 8, color: 'var(--muted-3)' }}>
                · fleet · {wo.bill_labor_at_customer_rate ? 'customer labor rate' : 'garage labor cost'} · parts at cost
              </span>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              {['draft', 'assigned', 'acknowledged'].includes(wo.status) && (
                <button className={ghostBtn} style={{ height: 34, padding: '0 12px', fontSize: 12.5 }}
                  disabled={startWO.isPending} onClick={() => startWO.mutate()}>
                  {startWO.isPending ? <Spinner size="xs" /> : <Play size={14} />} Start work
                </button>
              )}
              {['in_progress', 'pending_review'].includes(wo.status) && !armComplete && (
                <button className={yellowBtn} style={{ height: 34, padding: '0 12px', fontSize: 12.5 }}
                  disabled={completeWO.isPending}
                  onClick={() => { setMileageOut(wo.mileage_in != null ? String(wo.mileage_in) : ''); setArmComplete(true) }}>
                  <Flag size={14} /> Mark completed
                </button>
              )}
              {wo.status === 'completed' && (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--yellow)', fontSize: 13 }}>
                  <CheckCircle2 size={15} /> Completed
                </span>
              )}
            </div>
          </div>

          {armComplete && (
            <div style={{ border: '1px solid var(--line)', borderRadius: 10, padding: 12, display: 'grid', gap: 8 }}>
              <div className="id-k" style={{ textTransform: 'none', letterSpacing: 0 }}>
                Enter the truck's odometer at completion, then complete the repair order.
              </div>
              <label style={{ display: 'grid', gap: 4 }}>
                <span className="id-k">Mileage out</span>
                <input
                  style={{ ...costInput, height: 38 }}
                  value={mileageOut}
                  inputMode="numeric"
                  onChange={(e) => { const v = e.target.value; if (v === '' || /^\d+$/.test(v)) setMileageOut(v) }}
                  placeholder={wo.mileage_in != null ? `In: ${wo.mileage_in.toLocaleString()} mi` : 'Odometer at completion'}
                />
              </label>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button className={ghostBtn} style={{ height: 34, padding: '0 12px', fontSize: 12.5 }}
                  disabled={completeWO.isPending} onClick={() => setArmComplete(false)}>
                  Cancel
                </button>
                <button className={yellowBtn} style={{ height: 34, padding: '0 12px', fontSize: 12.5 }}
                  disabled={completeWO.isPending}
                  onClick={() => completeWO.mutate(mileageOut.trim() === '' ? null : Number(mileageOut))}>
                  {completeWO.isPending ? <Spinner size="xs" /> : <Flag size={14} />} Complete repair order
                </button>
              </div>
            </div>
          )}

          <div className="wo-live-cols">
            <section className="wo-live-side-a">
              <Field label="Work / complaint">
                <SuggestingTextarea
                  value={description}
                  onChange={(v) => { setDescription(v); setDescDirty(true) }}
                  rows={3}
                  style={{ width: '100%', background: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 9, color: 'var(--text)', padding: '10px 12px', font: 'inherit', resize: 'vertical' }}
                />
                {descDirty && (
                  <button className={ghostBtn} style={{ marginTop: 8, height: 34, padding: '0 12px', fontSize: 12.5 }}
                    disabled={saveDesc.isPending} onClick={() => saveDesc.mutate()}>
                    {saveDesc.isPending ? <Spinner size="xs" /> : null} Save description
                  </button>
                )}
              </Field>

              <Field label="Assigned mechanic">
                <select
                  value={wo.assigned_mechanic_id || ''}
                  onChange={(e) => e.target.value && assign.mutate(e.target.value)}
                  disabled={assign.isPending}
                  style={{ width: '100%', height: 40, background: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 9, color: 'var(--text)', padding: '0 10px' }}
                >
                  <option value="">Unassigned — choose a mechanic…</option>
                  {(mechanics || []).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                </select>
                <p className="id-k" style={{ textTransform: 'none', letterSpacing: 0, marginTop: 6 }}>
                  Optional — you can run this internal work order start to finish without assigning a mechanic.
                </p>
              </Field>
            </section>

            <section className="wo-live-main">
              {/* PM work orders are scoped by picking services (which seed the cost
                  lines), so the manual add rows are hidden for them. The picker is
                  only editable while the PM is still a draft. */}
              {wo.is_pm && wo.status === 'draft' && (
                <PMServicesSection roId={repairOrderId} onChanged={refresh} />
              )}

              <div>
                <div className="dmap-side-h" style={{ marginBottom: 8 }}>Labor ({wo.labor_items.length})</div>
                <div style={{ display: 'grid', gap: 6 }}>
                  {wo.labor_items.map((l) => <LaborRow key={l.id} roId={repairOrderId} line={l} onChanged={refresh} showPrices={showPrices} />)}
                </div>
                {!wo.is_pm && (
                  <>
                    <ServiceAddRow roId={repairOrderId} onChanged={refresh} />
                    <LaborAddRow roId={repairOrderId} laborRate={laborRate} onChanged={refresh} />
                  </>
                )}
              </div>

              <div>
                <div className="dmap-side-h" style={{ marginBottom: 8 }}>Parts ({wo.parts_usage.length})</div>
                <div style={{ display: 'grid', gap: 6 }}>
                  {wo.parts_usage.map((p) => <PartRow key={p.id} roId={repairOrderId} line={p} onChanged={refresh} showPrices={showPrices} />)}
                </div>
                {!wo.is_pm && <PartAddRow roId={repairOrderId} inventory={inventory || []} onChanged={refresh} />}
              </div>
            </section>

            <section className="wo-live-side-b">
              {/* Cost breakdown is owner/admin only — fleet managers don't see prices. */}
              {showPrices && (
                <div style={{ borderTop: '1px solid var(--line)', paddingTop: 12, display: 'grid', gap: 6, fontSize: 14 }}>
                  <Row k="Labor" v={money(num(wo.total_labor_cost))} />
                  <Row k="Parts" v={money(num(wo.total_parts_cost))} />
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 17, marginTop: 4 }}>
                    <strong style={{ color: 'var(--text)' }}>Repair order total</strong>
                    <strong style={{ color: 'var(--yellow)' }}>{money(num(wo.total_cost))}</strong>
                  </div>
                </div>
              )}

              <div style={{ borderTop: '1px solid var(--line)', paddingTop: 12 }}>
                <InlineConfirm
                  danger
                  message={workStarted
                    ? "Work has started — deleting discards all logged labor and parts. This can't be undone."
                    : "Delete this repair order? This can't be undone."}
                  confirmLabel="Delete"
                  pending={del.isPending}
                  onConfirm={() => del.mutate()}
                  renderTrigger={(arm) => (
                    <button
                      className={ghostBtn}
                      style={{ color: 'var(--red)', height: 42, padding: '0 16px', fontSize: 13, fontWeight: 600 }}
                      disabled={del.isPending}
                      onClick={arm}
                    >
                      <Trash2 size={16} /> Delete repair order
                    </button>
                  )}
                />
              </div>
            </section>
          </div>
        </div>
      )}
    </>
  )
}

/** The live work order opened on its own, from a board card or the truck's list. */
export function WorkOrderPanel({ repairOrderId, onClose, onChanged }: {
  repairOrderId: string; onClose: () => void; onChanged: () => void
}) {
  // Shares the body's query key, so this reads the cache rather than refetching.
  const { data: wo } = useQuery<WODetail>({
    queryKey: ['fleet-wo', repairOrderId],
    queryFn: async () => (await api.get(`/repair-orders/${repairOrderId}/detail`)).data,
  })
  return (
    <SlidePanel
      isOpen
      dark
      onClose={onClose}
      width={WO_DRAWER_WIDTH}
      subtitle="Repair order"
      title={wo ? `${wo.order_number}${wo.is_pm ? ' · PM' : ''}` : 'Repair order'}
      headerIcon={<ClipboardList size={18} className="text-[var(--yellow)]" />}
    >
      <div className="wo-drawer-body">
        <WorkOrderBody repairOrderId={repairOrderId} onClose={onClose} onChanged={onChanged} />
      </div>
    </SlidePanel>
  )
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
      <span style={{ color: 'var(--muted-2)' }}>{k}</span>
      <span style={{ color: 'var(--text)' }}>{v}</span>
    </div>
  )
}

/* ---------- Assign / change driver (focused, driver-only) ---------- */

export function AssignDriverModal({ truck, driverPhone, onClose }: { truck: BoardTruck; driverPhone?: string | null; onClose: () => void }) {
  const qc = useQueryClient()
  const [name, setName] = useState(truck.driver_name || '')
  const [phone, setPhone] = useState(driverPhone ? formatUSPhone(driverPhone) : '')
  const hadDriver = Boolean(truck.driver_name)

  const save = useMutation({
    mutationFn: async () => (await api.patch(`/fleet/trucks/${truck.id}`, {
      driver_name: name.trim(),
      driver_phone: phone.trim(),
    })).data,
    onSuccess: () => {
      toast.success(name.trim() ? 'Driver assigned' : 'Driver removed')
      qc.invalidateQueries({ queryKey: ['fleet-truck', truck.id] })
      invalidateFleetAndCockpit(qc)
      onClose()
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to save driver'),
  })

  return (
    <Modal title={hadDriver ? 'Change driver' : 'Assign driver'} icon={<UserRound size={17} />} onClose={onClose} width={420}>
      <div style={{ display: 'grid', gap: 12 }}>
        <Field label="Driver name"><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Full name" /></Field>
        <Field label="Driver phone"><input value={phone} onChange={(e) => setPhone(formatUSPhone(e.target.value))} placeholder="(704) 555-0123" /></Field>
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
        {hadDriver && (
          <button
            className={ghostBtn}
            disabled={save.isPending}
            onClick={() => { setName(''); setPhone(''); save.mutate() }}
            style={{ color: 'var(--red)' }}
          >
            Remove
          </button>
        )}
        <button className={yellowBtn} style={{ flex: 1, justifyContent: 'center' }} disabled={save.isPending || !name.trim()} onClick={() => save.mutate()}>
          {save.isPending ? <Spinner size="sm" /> : <UserRound size={15} />} {hadDriver ? 'Save driver' : 'Assign driver'}
        </button>
      </div>
    </Modal>
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
      toast.success('Incident logged')
      clearPhotoUploads()
      qc.invalidateQueries({ queryKey: ['fleet-truck', truckId] })
      invalidateFleetAndCockpit(qc)
      onClose()
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const submit = () => {
    setAttempted(true)
    if (descError) return
    create.mutate()
  }

  return (
    <Modal title="Log incident" icon={<AlertTriangle size={17} />} onClose={onClose}>
      <div style={{ marginBottom: 12 }}>
        <span className="id-k" style={{ display: 'block', marginBottom: 6 }}>Severity</span>
        <div style={{ display: 'flex', gap: 8 }}>
          {SEVS.map((s) => (
            <button key={s} onClick={() => setSeverity(s)}
              style={{
                flex: 1, height: 36, borderRadius: 8, textTransform: 'capitalize', fontSize: 13, fontWeight: 600,
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
      <button className={yellowBtn} style={{ marginTop: 14, width: '100%', justifyContent: 'center' }}
        disabled={create.isPending} onClick={submit}>
        {create.isPending ? <Spinner size="sm" /> : <Plus size={15} />} Log incident
      </button>
    </Modal>
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
    <Modal title="Edit incident" icon={<Pencil size={17} />} onClose={onClose}>
      <div style={{ marginBottom: 12 }}>
        <span className="id-k" style={{ display: 'block', marginBottom: 6 }}>Severity</span>
        <div style={{ display: 'flex', gap: 8 }}>
          {SEVS.map((s) => (
            <button key={s} onClick={() => setSeverity(s)}
              style={{
                flex: 1, height: 36, borderRadius: 8, textTransform: 'capitalize', fontSize: 13, fontWeight: 600,
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
      <button className={yellowBtn} style={{ marginTop: 14, width: '100%', justifyContent: 'center' }}
        disabled={save.isPending} onClick={submit}>
        {save.isPending ? <Spinner size="sm" /> : <CheckCircle2 size={15} />} Save changes
      </button>
    </Modal>
  )
}

/* ---------- Inspections: section + checklist ---------- */

export function InspectionsSection({ vehicleId, truckId, currentOdometer, className }: { vehicleId: string; truckId: string; currentOdometer?: number | null; className?: string }) {
  const qc = useQueryClient()
  const { user } = useAuthStore()
  const isOwner = user?.role === 'garage_owner'  // only the owner may delete inspections
  const [openId, setOpenId] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<Inspection | null>(null)
  const { data: inspections } = useQuery<Inspection[]>({
    queryKey: ['fleet-inspections', vehicleId],
    queryFn: async () => (await api.get('/fleet/inspections', { params: { vehicle_id: vehicleId } })).data,
  })
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
  // Most recent completed reading, for the "previous odometer" reference in the checklist.
  const lastReading = (inspections || [])
    .filter((i) => i.status === 'completed' && i.odometer != null && i.performed_at)
    .sort((a, b) => (a.performed_at! < b.performed_at! ? 1 : -1))[0]

  return (
    <section className={'dsec' + (className ? ` ${className}` : '')}>
      <div className="dsec-head">
        <div className="dsec-title"><ClipboardCheck size={17} /><h3>Weekly inspections</h3>
          {inspections != null && <span className="dsec-count">{inspections.length}</span>}</div>
        <button className={ghostBtn + ' dsec-action'} style={{ height: 34 }} onClick={() => start.mutate()} disabled={start.isPending} title="Start inspection">
          {start.isPending ? <Spinner size="xs" /> : <Plus size={14} />} <span className="dbtn-label">Start inspection</span>
        </button>
      </div>
      {!inspections?.length ? (
        <div className="empty-note"><ClipboardCheck size={16} /> No inspections yet.</div>
      ) : (
        <div className="inc-list">
          {inspections.map((i) => {
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
      {openId && <InspectionChecklistModal inspectionId={openId} truckId={truckId} vehicleId={vehicleId} currentOdometer={currentOdometer} lastReadingDate={lastReading?.performed_at || null} onClose={() => setOpenId(null)} />}
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
}

const CATEGORY_ORDER = ['Brakes', 'Fluids', 'Lights', 'Safety', 'Steering', 'Tires']

function InspectionChecklistModal({ inspectionId, truckId, vehicleId, currentOdometer, lastReadingDate, onClose }: {
  inspectionId: string; truckId: string; vehicleId: string; currentOdometer?: number | null; lastReadingDate?: string | null; onClose: () => void
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

  const { data: insp } = useQuery<InspectionDetail>({
    queryKey: ['fleet-inspection', inspectionId],
    queryFn: async () => (await api.get(`/fleet/inspections/${inspectionId}`)).data,
  })
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
    onSuccess: () => qc.invalidateQueries({ queryKey: ['fleet-inspection', inspectionId] }),
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed'),
  })
  const complete = useMutation({
    mutationFn: async () => (await api.post(`/fleet/inspections/${inspectionId}/complete`, { odometer: Number(odometer) })).data,
    onSuccess: () => { toast.success('Inspection completed'); refreshLists(); qc.invalidateQueries({ queryKey: ['fleet-inspection', inspectionId] }); onClose() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Could not complete'),
  })
  const createWO = useMutation({
    mutationFn: async () => (await api.post(`/fleet/inspections/${inspectionId}/create-work-order`)).data,
    onSuccess: () => { toast.success('Repair order created'); refreshLists(); qc.invalidateQueries({ queryKey: ['fleet-inspection', inspectionId] }) },
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
  const isCollapsed = (cat: string) => (userToggled[cat] ? !!collapsed[cat] : secComplete(cat))
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
  for (const cat of cats) { for (const it of grouped[cat]) { if (it.result === 'pending') { firstPendingId = it.id; break } } if (firstPendingId) break }

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

  const reviewAndComplete = () => {
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
    setShowErrors(false); setConfirming(true)
  }

  const hasUnit = !!insp?.vehicle_unit_number
  const unitLabel = insp ? (hasUnit ? insp.vehicle_unit_number! : `${insp.vehicle_make} ${insp.vehicle_model}`.trim()) : ''
  const makeModel = insp && hasUnit ? `${insp.vehicle_year ? `${insp.vehicle_year} ` : ''}${insp.vehicle_make} ${insp.vehicle_model}`.trim() : ''
  const statusText = !allMarked
    ? `${remaining} check${remaining === 1 ? '' : 's'} remaining`
    : failCount > 0 ? `${failCount} item${failCount === 1 ? '' : 's'} flagged — ready to review` : 'All clear — ready to submit'

  return (
    <div className="ip-overlay" onClick={onClose}>
      <div className="ip-frame" onClick={(e) => e.stopPropagation()}>
        {!insp ? (
          <div className="loader" style={{ margin: 'auto' }}><Spinner size="md" /></div>
        ) : (
          <>
            <div className="ip-head">
              <div className="ip-head-row">
                <div className="ip-brand">
                  <span className="ip-brand-sq"><Check size={19} strokeWidth={3} /></span>
                  <div style={{ minWidth: 0 }}>
                    <div className="ip-eyebrow">Weekly Inspection</div>
                    <div className="ip-unit">{unitLabel}</div>
                    {makeModel && <div className="ip-sub">{makeModel}</div>}
                  </div>
                </div>
                <button className="ip-close" onClick={onClose} title="Close"><X size={15} /></button>
              </div>
              {!done && (
                <>
                  <div className="ip-progress">
                    <div className="ip-track"><div className="ip-fill" style={{ width: `${progressPct}%` }} /></div>
                    <div className="ip-count">{doneCount}<span>/{total}</span></div>
                  </div>
                  <div className="ip-bulk">
                    <button className="ip-markall" onClick={markAllPass} disabled={bulk.isPending}>
                      <Check size={14} strokeWidth={3} /> MARK ALL PASS
                    </button>
                    <button className="ip-reset" onClick={resetAll} disabled={bulk.isPending} title="Reset all"><RotateCcw size={16} /></button>
                  </div>
                </>
              )}
            </div>

            <div className="ip-body">
              {done && (
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '10px 2px 4px' }}>
                  <span className={'part-w ' + (insp.result === 'fail' ? 'w-off' : 'w-on')} style={{ textTransform: 'uppercase' }}>{insp.result || 'completed'}</span>
                  <span style={{ fontSize: 13, color: 'var(--muted)' }}>
                    {insp.odometer != null ? `${fmt(insp.odometer)} mi` : '—'} · {insp.performed_at ? fmtDate(insp.performed_at) : '—'}
                  </span>
                </div>
              )}
              {cats.map((cat) => {
                const its = grouped[cat]
                const complete = secComplete(cat)
                const catHasPending = its.some((i) => i.result === 'pending')
                // Force the section open when we're pointing out its unmarked items.
                const collapsedNow = !done && isCollapsed(cat) && !(showErrors && catHasPending)
                const sum = secSummary(cat)
                return (
                  <div key={cat} className="ip-sec">
                    <div className={'ip-sec-head' + (complete ? ' done' : '')} onClick={() => toggleSection(cat)}>
                      <span className="ip-sec-name">{cat}</span>
                      <span className="ip-sec-sum" style={{ color: sum.color }}>{sum.text}</span>
                    </div>
                    {!collapsedNow && (
                      <div className="ip-sec-body">
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
                                  <div className={'ip-btns sel-' + item.result}>
                                    <button className={'ip-choice pass' + (item.result === 'pass' ? ' is-on' : '')} onClick={() => setStatus(item, 'pass')} title="Pass">
                                      <Check size={16} strokeWidth={3} /> <span className="ip-choice-tx">PASS</span>
                                    </button>
                                    <button className={'ip-choice fail' + (item.result === 'fail' ? ' is-on' : '')} onClick={() => setStatus(item, 'fail')} title="Fail">
                                      <X size={18} /> <span className="ip-choice-tx">FAIL</span>
                                    </button>
                                    <button className={'ip-choice na' + (item.result === 'na' ? ' is-on' : '')} onClick={() => setStatus(item, 'na')} title="N/A">
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

              {!done && (
                <div className="ip-odo">
                  <div className="ip-odo-card">
                    <span className="ip-odo-k">Previous odometer</span>
                    <span className="ip-odo-v">
                      {currentOdometer != null ? `${fmt(currentOdometer)} mi` : 'None on record'}
                      {lastReadingDate && <span> · {fmtDate(lastReadingDate)}</span>}
                    </span>
                  </div>
                  <div className="ip-odo-k" style={{ marginTop: 10, color: odoError ? 'var(--red)' : undefined }}>New odometer (mi)</div>
                  <input ref={odoRef} className={'ip-odo-input' + (odoError ? ' err' : '')}
                    value={odometer} inputMode="numeric" placeholder="Enter current reading"
                    onChange={(e) => setOdometer(e.target.value)} />
                  {odoBackwards && (
                    <p style={{ fontSize: 12, color: 'var(--red)', marginTop: 6 }}>
                      Below the previous {fmt(currentOdometer as number)} mi — odometers don't go backwards, check the reading.
                    </p>
                  )}
                </div>
              )}
            </div>

            <div className="ip-foot">
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
                  <div style={{
                    borderRadius: 11, padding: '11px 13px', marginBottom: 10,
                    border: '1px solid ' + (computedResult === 'fail' ? 'var(--red)' : 'var(--st-active)'),
                    background: `color-mix(in srgb, ${computedResult === 'fail' ? 'var(--red)' : 'var(--st-active)'} 12%, transparent)`,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, fontWeight: 800, color: computedResult === 'fail' ? 'var(--red)' : 'var(--st-active)' }}>
                      {computedResult === 'fail' ? <XCircle size={17} /> : <CheckCircle2 size={17} />}
                      Will be recorded as {computedResult === 'fail' ? 'FAILED' : 'PASSED'}
                    </div>
                    <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 6 }}>
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
                  <button className="ip-cta" onClick={reviewAndComplete}>
                    <Check size={16} strokeWidth={3} /> Review &amp; complete
                  </button>
                </>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
