import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  X, Loader2, Pencil, AlertTriangle, ClipboardCheck, CheckCircle2, XCircle, Plus, ClipboardList, Trash2, UserRound, Play, Flag, Calendar,
  Check, Minus, RotateCcw,
} from 'lucide-react'
import api from '../../lib/api'
import type {
  BoardTruck, TruckDetail, Inspection, InspectionDetail, InspectionItem, InspectionItemResult, InspectionResult, IncidentSeverity, IncidentEntry,
} from './types'
import { fmtDate, money, fmt } from './helpers'

/* shared modal shell (fleet design system) */
export function Modal({ title, icon, onClose, children, width = 480 }: {
  title: string; icon: React.ReactNode; onClose: () => void; children: React.ReactNode; width?: number
}) {
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.6)', zIndex: 60, display: 'grid', placeItems: 'center' }} onClick={onClose}>
      <div className="dsec" style={{ width, maxWidth: '92vw', maxHeight: '88vh', overflowY: 'auto' }} onClick={(e) => e.stopPropagation()}>
        <div className="dsec-head">
          <div className="dsec-title">{icon}<h3>{title}</h3></div>
          <button className="person-call" onClick={onClose}><X size={15} /></button>
        </div>
        {children}
      </div>
    </div>
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
        {pending ? <Loader2 size={13} className="animate-spin" /> : null} {confirmLabel}
      </button>
    </span>
  )
}

/* ---------- Edit truck (odometer / driver / PM / manual location) ---------- */

export function TruckEditModal({ truck, detail, onClose }: { truck: BoardTruck; detail: TruckDetail; onClose: () => void }) {
  const qc = useQueryClient()
  const [f, setF] = useState({
    unit_number: truck.unit_number || '',
    vin: truck.vin || '',
    make: truck.make || '',
    model: truck.model || '',
    year: truck.year?.toString() || '',
    license_plate: truck.plate || '',
    odometer: truck.odometer?.toString() || '',
    driver_name: truck.driver_name || '',
    driver_phone: detail.driver_phone || '',
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
  const numOrUndef = (v: string) => (v.trim() === '' ? undefined : Number(v))

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
      qc.invalidateQueries({ queryKey: ['fleet-board'] })
      onClose()
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to update'),
  })

  return (
    <Modal title={`Edit ${truck.unit_number || 'truck'}`} icon={<Pencil size={17} />} onClose={onClose} width={520}>
      <div className="dmap-side-h" style={{ marginBottom: 8 }}>Identity</div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
        <Field label="Unit #"><input value={f.unit_number} onChange={set('unit_number')} placeholder="TPS-109" /></Field>
        <Field label="Plate"><input value={f.license_plate} onChange={set('license_plate')} placeholder="ABC-1234" /></Field>
        <Field label="Make"><input value={f.make} onChange={set('make')} /></Field>
        <Field label="Model"><input value={f.model} onChange={set('model')} /></Field>
        <Field label="Year"><input value={f.year} onChange={set('year')} inputMode="numeric" /></Field>
        <Field label="VIN"><input value={f.vin} onChange={set('vin')} placeholder="17-character VIN" /></Field>
      </div>
      <div className="dmap-side-h" style={{ marginBottom: 8 }}>Operations & location</div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <Field label="Odometer (mi)"><input value={f.odometer} onChange={set('odometer')} inputMode="numeric" /></Field>
        <Field label="PM interval (mi)"><input value={f.pm_interval_miles} onChange={set('pm_interval_miles')} inputMode="numeric" /></Field>
        <Field label="Next PM at (mi)"><input value={f.next_pm_miles} onChange={set('next_pm_miles')} inputMode="numeric" placeholder="odometer + interval" /></Field>
        <div />
        <Field label="Driver name"><input value={f.driver_name} onChange={set('driver_name')} /></Field>
        <Field label="Driver phone"><input value={f.driver_phone} onChange={set('driver_phone')} placeholder="+1 704 555 1234" /></Field>
        <Field label="Location label" full><input value={f.location_label} onChange={set('location_label')} placeholder="I-85 N · Charlotte, NC  or  TPS Yard · Bay 3" /></Field>
        <Field label="City"><input value={f.location_city} onChange={set('location_city')} /></Field>
        <Field label="Heading"><input value={f.heading} onChange={set('heading')} placeholder="NE" /></Field>
        <Field label="Latitude"><input value={f.lat} onChange={set('lat')} inputMode="decimal" placeholder="35.11" /></Field>
        <Field label="Longitude"><input value={f.lng} onChange={set('lng')} inputMode="decimal" placeholder="-80.72" /></Field>
        <Field label="Speed (mph)"><input value={f.speed_mph} onChange={set('speed_mph')} inputMode="numeric" placeholder="0 = parked" /></Field>
      </div>
      <p style={{ fontSize: 12, color: 'var(--muted-2)', marginTop: 10 }}>
        Manual entry until a telematics provider is connected — then odometer & location sync automatically.
      </p>
      <button className={yellowBtn} style={{ marginTop: 14, width: '100%', justifyContent: 'center' }} disabled={save.isPending} onClick={() => save.mutate()}>
        {save.isPending ? <Loader2 size={15} className="animate-spin" /> : <Pencil size={15} />} Save changes
      </button>
    </Modal>
  )
}

/* ---------- New work order (corrective) ---------- */

export function NewWorkOrderModal({ truckId, unitNumber, onClose, onCreated }: {
  truckId: string; unitNumber?: string | null; onClose: () => void; onCreated: () => void
}) {
  const [description, setDescription] = useState('')

  const create = useMutation({
    mutationFn: async () => (await api.post(`/fleet/trucks/${truckId}/work-order`, {
      description: description.trim(),
    })).data,
    onSuccess: () => { toast.success('Work order created'); onCreated(); onClose() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to create work order'),
  })

  return (
    <Modal title={`New work order${unitNumber ? ` · ${unitNumber}` : ''}`} icon={<ClipboardList size={17} />} onClose={onClose} width={460}>
      <Field label="What's the work / complaint?">
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={4}
          placeholder="e.g. Air leak on front brake chamber; DOT inspection due; check engine light"
          style={{
            width: '100%', background: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 9,
            color: 'var(--text)', padding: '10px 12px', font: 'inherit', resize: 'vertical',
          }}
        />
      </Field>
      <p style={{ fontSize: 12, color: 'var(--muted-2)', marginTop: 8 }}>
        Creates an internal (in-house cost) work order in Draft. A description is required.
      </p>
      <button className={yellowBtn} style={{ marginTop: 14, width: '100%', justifyContent: 'center' }}
        disabled={create.isPending || !description.trim()} onClick={() => create.mutate()}>
        {create.isPending ? <Loader2 size={15} className="animate-spin" /> : <ClipboardList size={15} />} Create work order
      </button>
    </Modal>
  )
}

/* ---------- Schedule PM (date + mileage) ---------- */

export function SchedulePMModal({ truck, onClose, onDone }: { truck: BoardTruck; onClose: () => void; onDone: () => void }) {
  const qc = useQueryClient()
  // Default cadence when the truck has no configured interval: 10 weeks (70 days).
  const intervalDays = truck.pm_interval_days || 70
  const intervalMiles = truck.pm_interval_miles || 25000
  const defaultDate = () => {
    const base = truck.pm_due_date ? new Date(truck.pm_due_date) : new Date(Date.now() + intervalDays * 86400000)
    return base.toISOString().slice(0, 10)
  }
  const [dueDate, setDueDate] = useState(defaultDate())
  const [nextMiles, setNextMiles] = useState(String(truck.next_pm_miles ?? ((truck.odometer || 0) + intervalMiles)))
  const [createWO, setCreateWO] = useState(false)
  const rescheduling = !!truck.pm_due_date

  const save = useMutation({
    mutationFn: async () => (await api.post(`/fleet/trucks/${truck.id}/schedule-pm`, {
      due_date: dueDate || null,
      next_pm_miles: nextMiles.trim() ? Number(nextMiles) : null,
      create_work_order: createWO,
    })).data,
    onSuccess: () => {
      toast.success(createWO ? 'PM rescheduled and work order created' : (rescheduling ? 'PM rescheduled' : 'PM scheduled'))
      qc.invalidateQueries({ queryKey: ['fleet-truck', truck.id] })
      qc.invalidateQueries({ queryKey: ['fleet-board'] })
      onDone(); onClose()
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to schedule PM'),
  })

  return (
    <Modal title={`${rescheduling ? 'Reschedule' : 'Schedule'} PM${truck.unit_number ? ` · ${truck.unit_number}` : ''}`} icon={<Calendar size={17} />} onClose={onClose} width={440}>
      <div style={{ display: 'grid', gap: 12 }}>
        <Field label="Next PM due date">
          <input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
        </Field>
        <Field label="Next PM at odometer (mi)">
          <input value={nextMiles} onChange={(e) => setNextMiles(e.target.value)} inputMode="numeric" placeholder={`${intervalMiles} mi interval`} />
        </Field>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text)', cursor: 'pointer' }}>
          <input type="checkbox" checked={createWO} onChange={(e) => setCreateWO(e.target.checked)} style={{ width: 'auto' }} />
          Create the PM work order now
        </label>
      </div>
      <p style={{ fontSize: 12, color: 'var(--muted-2)', marginTop: 10 }}>
        PM shows as due when either the date or the odometer is reached. Completing a PM rolls both forward by the interval.
      </p>
      <button className={yellowBtn} style={{ marginTop: 14, width: '100%', justifyContent: 'center' }} disabled={save.isPending} onClick={() => save.mutate()}>
        {save.isPending ? <Loader2 size={15} className="animate-spin" /> : <Calendar size={15} />} {createWO ? `${rescheduling ? 'Reschedule' : 'Schedule'} + create work order` : 'Save schedule'}
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
interface WOPart { id: string; inventory_name: string; quantity: number; unit_price: number | string; total_price: number | string }
interface WODetail {
  id: string; order_number: string; status: string; description?: string | null
  assigned_mechanic_id?: string | null
  total_parts_cost: number | string; total_labor_cost: number | string; total_cost: number | string
  is_pm?: boolean
  labor_items: WOLabor[]; parts_usage: WOPart[]
}

interface WOInventory { id: string; name: string; sku: string; cost: number | string; selling_price: number | string; stock_quantity: number }

const toNum = (v: number | string | null | undefined) => (v == null ? 0 : Number(v))
const costInput: React.CSSProperties = {
  height: 34, background: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 8,
  color: 'var(--text)', padding: '0 8px', font: 'inherit', fontSize: 13,
}
const iconBtn: React.CSSProperties = { background: 'none', border: 'none', cursor: 'pointer', display: 'grid', placeItems: 'center', padding: 4 }

function LaborAddRow({ roId, internalRate, onChanged }: { roId: string; internalRate: number; onChanged: () => void }) {
  const [desc, setDesc] = useState('')
  const [hours, setHours] = useState('')
  const add = useMutation({
    mutationFn: async () => (await api.post(`/repair-orders/${roId}/labor`, {
      description: desc.trim() || undefined, hours: Number(hours), hourly_rate: internalRate,
    })).data,
    onSuccess: () => { toast.success('Labor added'); setDesc(''); setHours(''); onChanged() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to add labor'),
  })
  const valid = hours !== '' && Number(hours) > 0
  return (
    <div style={{ marginTop: 6 }}>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <input style={{ ...costInput, flex: 1 }} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Labor description" />
        <input style={{ ...costInput, width: 60 }} value={hours} onChange={(e) => setHours(e.target.value)} inputMode="decimal" placeholder="hrs" />
        {/* Rate is the configured in-house labor cost — read-only. */}
        <span style={{ ...costInput, width: 72, display: 'grid', alignItems: 'center', color: 'var(--muted)' }} title="In-house labor rate (set in garage settings)">{money(internalRate)}/h</span>
        <button className={ghostBtn} style={{ height: 34, padding: '0 10px', fontSize: 12.5 }} disabled={!valid || add.isPending} onClick={() => add.mutate()}>
          {add.isPending ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
        </button>
      </div>
      {internalRate <= 0 && (
        <p className="id-k" style={{ textTransform: 'none', letterSpacing: 0, marginTop: 5, color: '#fb923c' }}>
          In-house labor rate is $0 — set it in garage settings (owner/admin) so labor is costed.
        </p>
      )}
    </div>
  )
}

function LaborRow({ roId, line, onChanged }: { roId: string; line: WOLabor; onChanged: () => void }) {
  const [hours, setHours] = useState(String(toNum(line.hours)))
  const dirty = Number(hours) !== toNum(line.hours)
  const save = useMutation({
    mutationFn: async () => (await api.put(`/repair-orders/${roId}/labor/${line.id}`, { hours: Number(hours) })).data,
    onSuccess: () => { toast.success('Labor updated'); onChanged() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to update'),
  })
  const del = useMutation({
    mutationFn: async () => (await api.delete(`/repair-orders/${roId}/labor/${line.id}`)).data,
    onSuccess: () => { toast.success('Labor removed'); onChanged() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to remove'),
  })
  return (
    <div style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13 }}>
      <span style={{ flex: 1, color: 'var(--text)' }}>{line.description || 'Labor'}</span>
      <input style={{ ...costInput, width: 60 }} value={hours} onChange={(e) => setHours(e.target.value)} inputMode="decimal" />
      <span style={{ width: 72, textAlign: 'right', color: 'var(--muted)' }} title="In-house labor rate">{money(toNum(line.hourly_rate))}/h</span>
      {dirty && (
        <button style={iconBtn} title="Save" disabled={save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={15} color="var(--yellow)" />}
        </button>
      )}
      <button style={iconBtn} title="Remove" disabled={del.isPending} onClick={() => del.mutate()}>
        <XCircle size={15} color="var(--red)" />
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
    <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 6 }}>
      <select style={{ ...costInput, flex: 1, height: 34 }} value={invId} onChange={(e) => setInvId(e.target.value)}>
        <option value="">Add part from inventory…</option>
        {/* Internal fleet repairs are costed at the part's cost, not list price. */}
        {inventory.map((i) => <option key={i.id} value={i.id}>{i.name} ({i.sku}) · {money(toNum(i.cost))} cost</option>)}
      </select>
      <input style={{ ...costInput, width: 60 }} value={qty} onChange={(e) => setQty(e.target.value)} inputMode="numeric" placeholder="qty" />
      <button className={ghostBtn} style={{ height: 34, padding: '0 10px', fontSize: 12.5 }} disabled={!valid || add.isPending} onClick={() => add.mutate()}>
        {add.isPending ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
      </button>
    </div>
  )
}

function PartRow({ roId, line, onChanged }: { roId: string; line: WOPart; onChanged: () => void }) {
  const [qty, setQty] = useState(String(line.quantity))
  const dirty = Number(qty) !== line.quantity
  const save = useMutation({
    mutationFn: async () => (await api.patch(`/repair-orders/${roId}/parts/${line.id}`, { quantity: Number(qty) })).data,
    onSuccess: () => { toast.success('Part updated'); onChanged() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to update'),
  })
  const del = useMutation({
    mutationFn: async () => (await api.delete(`/repair-orders/${roId}/parts/${line.id}`)).data,
    onSuccess: () => { toast.success('Part removed'); onChanged() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to remove'),
  })
  return (
    <div style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13 }}>
      <span style={{ flex: 1, color: 'var(--text)' }}>{line.inventory_name} · {money(toNum(line.unit_price))}</span>
      <input style={{ ...costInput, width: 60 }} value={qty} onChange={(e) => setQty(e.target.value)} inputMode="numeric" />
      <strong style={{ width: 64, textAlign: 'right', color: 'var(--text)' }}>{money(toNum(line.total_price))}</strong>
      {dirty && (
        <button style={iconBtn} title="Save" disabled={save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={15} color="var(--yellow)" />}
        </button>
      )}
      <button style={iconBtn} title="Remove" disabled={del.isPending} onClick={() => del.mutate()}>
        <XCircle size={15} color="var(--red)" />
      </button>
    </div>
  )
}

export function WorkOrderPanel({ repairOrderId, onClose, onChanged }: {
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
  const { data: fleetSettings } = useQuery<{ internal_labor_rate: number }>({
    queryKey: ['fleet-settings'],
    queryFn: async () => (await api.get('/fleet/settings')).data,
  })
  const internalRate = toNum(fleetSettings?.internal_labor_rate)

  const [description, setDescription] = useState('')
  const [descDirty, setDescDirty] = useState(false)
  // Seed the editable description once the work order loads.
  if (wo && !descDirty && description === '') {
    if (wo.description) setDescription(wo.description)
  }

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['fleet-wo', repairOrderId] })
    qc.invalidateQueries({ queryKey: ['fleet-board'] })
    onChanged()
  }

  const saveDesc = useMutation({
    mutationFn: async () => (await api.put(`/repair-orders/${repairOrderId}`, { description: description.trim() })).data,
    onSuccess: () => { toast.success('Work order updated'); setDescDirty(false); refresh() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to update'),
  })
  const assign = useMutation({
    mutationFn: async (mechanicId: string) => (await api.post(`/repair-orders/${repairOrderId}/assign-mechanic`, { mechanic_id: mechanicId })).data,
    onSuccess: () => { toast.success('Mechanic assigned'); refresh() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to assign'),
  })
  const del = useMutation({
    mutationFn: async () => (await api.delete(`/repair-orders/${repairOrderId}`)).data,
    onSuccess: () => { toast.success('Work order deleted'); qc.invalidateQueries({ queryKey: ['fleet-board'] }); onChanged(); onClose() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to delete work order'),
  })
  const startWO = useMutation({
    mutationFn: async () => (await api.post(`/fleet/work-orders/${repairOrderId}/start`)).data,
    onSuccess: () => { toast.success('Work order in progress'); refresh() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to start work order'),
  })
  const completeWO = useMutation({
    mutationFn: async () => (await api.post(`/fleet/work-orders/${repairOrderId}/complete`)).data,
    onSuccess: () => { toast.success('Work order completed'); refresh(); onClose() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to complete work order'),
  })

  // Internal fleet work orders can be deleted at any status. The confirmation
  // warns when work has already started, since deleting discards that progress.
  const workStarted = wo ? !['draft', 'quoted'].includes(wo.status) : false
  const title = wo ? `${wo.order_number}${wo.is_pm ? ' · PM' : ''}` : 'Work order'

  return (
    <Modal title={title} icon={<ClipboardList size={17} />} onClose={onClose} width={560}>
      {isLoading || !wo ? (
        <div className="loader"><Loader2 size={18} className="animate-spin" /></div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
            <div className="id-k" style={{ textTransform: 'none', letterSpacing: 0 }}>
              Status: <strong style={{ color: 'var(--text)' }}>{WO_STATUS_LABEL[wo.status] || wo.status}</strong>
              <span style={{ marginLeft: 8, color: 'var(--muted-3)' }}>· internal (in-house cost)</span>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              {['draft', 'assigned', 'acknowledged'].includes(wo.status) && (
                <button className={ghostBtn} style={{ height: 34, padding: '0 12px', fontSize: 12.5 }}
                  disabled={startWO.isPending} onClick={() => startWO.mutate()}>
                  {startWO.isPending ? <Loader2 size={13} className="animate-spin" /> : <Play size={14} />} Start work
                </button>
              )}
              {['in_progress', 'pending_review'].includes(wo.status) && (
                <InlineConfirm
                  message="Complete & generate an internal invoice?"
                  confirmLabel="Complete"
                  pending={completeWO.isPending}
                  onConfirm={() => completeWO.mutate()}
                  renderTrigger={(arm) => (
                    <button className={yellowBtn} style={{ height: 34, padding: '0 12px', fontSize: 12.5 }}
                      disabled={completeWO.isPending} onClick={arm}>
                      <Flag size={14} /> Mark completed
                    </button>
                  )}
                />
              )}
              {wo.status === 'completed' && (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--yellow)', fontSize: 13 }}>
                  <CheckCircle2 size={15} /> Completed
                </span>
              )}
            </div>
          </div>

          <Field label="Work / complaint">
            <textarea
              value={description}
              onChange={(e) => { setDescription(e.target.value); setDescDirty(true) }}
              rows={3}
              style={{ width: '100%', background: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 9, color: 'var(--text)', padding: '10px 12px', font: 'inherit', resize: 'vertical' }}
            />
            {descDirty && (
              <button className={ghostBtn} style={{ marginTop: 8, height: 34, padding: '0 12px', fontSize: 12.5 }}
                disabled={saveDesc.isPending} onClick={() => saveDesc.mutate()}>
                {saveDesc.isPending ? <Loader2 size={13} className="animate-spin" /> : null} Save description
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

          <div>
            <div className="dmap-side-h" style={{ marginBottom: 8 }}>Labor ({wo.labor_items.length})</div>
            <div style={{ display: 'grid', gap: 6 }}>
              {wo.labor_items.map((l) => <LaborRow key={l.id} roId={repairOrderId} line={l} onChanged={refresh} />)}
            </div>
            <LaborAddRow roId={repairOrderId} internalRate={internalRate} onChanged={refresh} />
          </div>

          <div>
            <div className="dmap-side-h" style={{ marginBottom: 8 }}>Parts ({wo.parts_usage.length})</div>
            <div style={{ display: 'grid', gap: 6 }}>
              {wo.parts_usage.map((p) => <PartRow key={p.id} roId={repairOrderId} line={p} onChanged={refresh} />)}
            </div>
            <PartAddRow roId={repairOrderId} inventory={inventory || []} onChanged={refresh} />
          </div>

          <div style={{ borderTop: '1px solid var(--line)', paddingTop: 12, display: 'grid', gap: 4, fontSize: 13 }}>
            <Row k="Labor" v={money(num(wo.total_labor_cost))} />
            <Row k="Parts" v={money(num(wo.total_parts_cost))} />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 15, marginTop: 4 }}>
              <strong style={{ color: 'var(--text)' }}>Internal cost</strong>
              <strong style={{ color: 'var(--yellow)' }}>{money(num(wo.total_cost))}</strong>
            </div>
          </div>

          <div style={{ borderTop: '1px solid var(--line)', paddingTop: 12 }}>
            <InlineConfirm
              danger
              message={workStarted
                ? "Work has started — deleting discards all logged labor and parts. This can't be undone."
                : "Delete this work order? This can't be undone."}
              confirmLabel="Delete"
              pending={del.isPending}
              onConfirm={() => del.mutate()}
              renderTrigger={(arm) => (
                <button
                  className={ghostBtn}
                  style={{ color: 'var(--red)', height: 34, padding: '0 12px', fontSize: 12.5 }}
                  disabled={del.isPending}
                  onClick={arm}
                >
                  <Trash2 size={14} /> Delete work order
                </button>
              )}
            />
          </div>
        </div>
      )}
    </Modal>
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
  const [phone, setPhone] = useState(driverPhone || '')
  const hadDriver = Boolean(truck.driver_name)

  const save = useMutation({
    mutationFn: async () => (await api.patch(`/fleet/trucks/${truck.id}`, {
      driver_name: name.trim(),
      driver_phone: phone.trim(),
    })).data,
    onSuccess: () => {
      toast.success(name.trim() ? 'Driver assigned' : 'Driver removed')
      qc.invalidateQueries({ queryKey: ['fleet-truck', truck.id] })
      qc.invalidateQueries({ queryKey: ['fleet-board'] })
      onClose()
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to save driver'),
  })

  return (
    <Modal title={hadDriver ? 'Change driver' : 'Assign driver'} icon={<UserRound size={17} />} onClose={onClose} width={420}>
      <div style={{ display: 'grid', gap: 12 }}>
        <Field label="Driver name"><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Full name" /></Field>
        <Field label="Driver phone"><input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="(704) 555-0123" /></Field>
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
          {save.isPending ? <Loader2 size={15} className="animate-spin" /> : <UserRound size={15} />} {hadDriver ? 'Save driver' : 'Assign driver'}
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

export function LogIncidentModal({ vehicleId, truckId, onClose }: { vehicleId: string; truckId: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [description, setDescription] = useState('')
  const [location, setLocation] = useState('')
  const [severity, setSeverity] = useState<IncidentSeverity>('medium')

  const create = useMutation({
    mutationFn: async () => (await api.post('/fleet/incidents', {
      vehicle_id: vehicleId, occurred_at: new Date().toISOString(),
      location: location || undefined, severity, description,
    })).data,
    onSuccess: () => {
      toast.success('Incident logged')
      qc.invalidateQueries({ queryKey: ['fleet-truck', truckId] })
      qc.invalidateQueries({ queryKey: ['fleet-board'] })
      onClose()
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed'),
  })

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
      <Field label="Location"><input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="I-85 mile 42, Charlotte NC" /></Field>
      <div style={{ marginTop: 12 }}>
        <span className="id-k" style={{ display: 'block', marginBottom: 5 }}>What happened?</span>
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={4}
          style={{ width: '100%', background: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 9, color: 'var(--text)', fontFamily: 'inherit', fontSize: 13.5, padding: 10, outline: 'none' }}
          placeholder="Describe the incident" />
      </div>
      <button className={yellowBtn} style={{ marginTop: 14, width: '100%', justifyContent: 'center' }}
        disabled={!description.trim() || create.isPending} onClick={() => create.mutate()}>
        {create.isPending ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />} Log incident
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

  const save = useMutation({
    mutationFn: async () => (await api.patch(`/fleet/incidents/${incident.id}`, {
      location: location || null, severity, description,
    })).data,
    onSuccess: () => {
      toast.success('Incident updated')
      qc.invalidateQueries({ queryKey: ['fleet-truck', truckId] })
      qc.invalidateQueries({ queryKey: ['fleet-board'] })
      onClose()
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed'),
  })

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
      <Field label="Location"><input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="I-85 mile 42, Charlotte NC" /></Field>
      <div style={{ marginTop: 12 }}>
        <span className="id-k" style={{ display: 'block', marginBottom: 5 }}>What happened?</span>
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={4}
          style={{ width: '100%', background: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 9, color: 'var(--text)', fontFamily: 'inherit', fontSize: 13.5, padding: 10, outline: 'none' }}
          placeholder="Describe the incident" />
      </div>
      <button className={yellowBtn} style={{ marginTop: 14, width: '100%', justifyContent: 'center' }}
        disabled={!description.trim() || save.isPending} onClick={() => save.mutate()}>
        {save.isPending ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />} Save changes
      </button>
    </Modal>
  )
}

/* ---------- Inspections: section + checklist ---------- */

export function InspectionsSection({ vehicleId, truckId, currentOdometer }: { vehicleId: string; truckId: string; currentOdometer?: number | null }) {
  const qc = useQueryClient()
  const [openId, setOpenId] = useState<string | null>(null)
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
  // Most recent completed reading, for the "previous odometer" reference in the checklist.
  const lastReading = (inspections || [])
    .filter((i) => i.status === 'completed' && i.odometer != null && i.performed_at)
    .sort((a, b) => (a.performed_at! < b.performed_at! ? 1 : -1))[0]

  return (
    <section className="dsec">
      <div className="dsec-head">
        <div className="dsec-title"><ClipboardCheck size={17} /><h3>Weekly inspections</h3>
          {inspections != null && <span className="dsec-count">{inspections.length}</span>}</div>
        <button className={ghostBtn} style={{ height: 34 }} onClick={() => start.mutate()} disabled={start.isPending}>
          {start.isPending ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} Start inspection
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
            const row = (
              <>
                <i className="lrow-dot" style={{ background: dot }} />
                <span className="lrow-tx">{fmtDate(i.performed_at || i.scheduled_for)}</span>
                <span className="lrow-r">
                  {i.odometer != null && <span className="lrow-tx" style={{ color: 'var(--muted)' }}>{fmt(i.odometer)} mi</span>}
                  <span className="lrow-st" style={{ textTransform: 'capitalize', color: labelColor }}>{label}</span>
                </span>
              </>
            )
            // Missed markers have no checklist to open.
            return i.status === 'missed'
              ? <div key={i.id} className="lrow" style={{ cursor: 'default' }}>{row}</div>
              : <button key={i.id} className="lrow" onClick={() => setOpenId(i.id)}>{row}</button>
          })}
        </div>
      )}
      {openId && <InspectionChecklistModal inspectionId={openId} truckId={truckId} vehicleId={vehicleId} currentOdometer={currentOdometer} lastReadingDate={lastReading?.performed_at || null} onClose={() => setOpenId(null)} />}
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
    qc.invalidateQueries({ queryKey: ['fleet-board'] })
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
          <div className="loader" style={{ margin: 'auto' }}><Loader2 size={20} className="animate-spin" /></div>
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
                              <div className="ip-item-label">{item.label}
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
                                  <div className="ip-btns">
                                    <button className={'ip-pass' + (item.result === 'pass' ? ' is-on' : '')} onClick={() => setStatus(item, 'pass')}>
                                      <Check size={16} strokeWidth={3} /> PASS
                                    </button>
                                    <button className={'ip-sm fail' + (item.result === 'fail' ? ' is-on' : '')} onClick={() => setStatus(item, 'fail')} title="Fail"><X size={18} /></button>
                                    <button className={'ip-sm na' + (item.result === 'na' ? ' is-on' : '')} onClick={() => setStatus(item, 'na')} title="N/A"><Minus size={18} /></button>
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
                <button className="ip-cta ip-cta-ghost" onClick={onClose}>Close</button>
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
                      {complete.isPending ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} strokeWidth={3} />} Confirm &amp; submit
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
