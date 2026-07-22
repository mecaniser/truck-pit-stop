import { useEffect, useState } from 'react'
import { Spinner } from '@/components/ui'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  Truck, LayoutGrid, Map as MapIcon, CalendarRange, ClipboardList, Users,
  Bell, LogOut, Plus, X, Wrench, ArrowLeft, Settings, UserRound, KeyRound, Eye, EyeOff,
  Calendar, Play, Flag, ClipboardCheck, ChevronsLeft, ChevronsRight, Pencil,
} from 'lucide-react'
import api from '../../lib/api'
import { useAuthStore } from '../../stores/authStore'
import { getPasswordValidationError } from '../../lib/passwordPolicy'
import type { BoardTruck, FleetBoard as FleetBoardData } from './types'
import { STATUS_META, fmt, pmState, initials } from './helpers'
import { formatUSPhone } from '@/utils/phone'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import FleetBoard from './FleetBoard'
import TruckDetail from './TruckDetail'
import FleetMap from './FleetMap'
import { SchedulePMModal, WorkOrderPanel, invalidateFleetAndCockpit } from './FleetModals'
import './fleet.css'

type View = 'board' | 'map' | 'schedule' | 'orders' | 'drivers' | 'detail'
const STORAGE_KEY = 'tps-fleet-state'

interface Persisted { view: View; selId: string | null; filter: any; sort: any }
function loadState(): Persisted {
  try { return { view: 'board', selId: null, filter: 'all', sort: 'attention', ...JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') } }
  catch { return { view: 'board', selId: null, filter: 'all', sort: 'attention' } }
}

export default function FleetApp() {
  const navigate = useNavigate()
  const { user, logout } = useAuthStore()
  const init = loadState()
  const [view, setView] = useState<View>(init.view === 'detail' && init.selId ? 'detail' : init.view)
  const [selId, setSelId] = useState<string | null>(init.selId)
  const [filter, setFilter] = useState(init.filter)
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState(init.sort)
  const [adding, setAdding] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [clock, setClock] = useState(() => new Date())
  const [railExpanded, setRailExpanded] = useState(() => localStorage.getItem('tps-fleet-rail') === '1')

  useEffect(() => {
    const id = setInterval(() => setClock(new Date()), 30000)
    return () => clearInterval(id)
  }, [])
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ view, selId, filter, sort }))
  }, [view, selId, filter, sort])

  const { data, isLoading } = useQuery<FleetBoardData>({
    queryKey: ['fleet-board'],
    queryFn: async () => (await api.get('/fleet/board')).data,
    refetchInterval: 60000,
  })
  const trucks = data?.trucks || []

  const openTruck = (id: string) => { setSelId(id); setView('detail'); document.querySelector('.fleet-root .scroll')?.scrollTo(0, 0) }
  const goView = (v: View) => { setView(v); if (v !== 'detail') setSelId(null) }
  const toggleRail = () => setRailExpanded((v) => { localStorage.setItem('tps-fleet-rail', v ? '0' : '1'); return !v })

  const railItems: [View, React.ReactNode, string, string][] = [
    ['board', <LayoutGrid size={20} />, 'Fleet board', 'FB'],
    ['map', <MapIcon size={20} />, 'Live map', 'MAP'],
    ['schedule', <CalendarRange size={20} />, 'PM schedule', 'PM'],
    ['orders', <ClipboardList size={20} />, 'Work orders', 'WO'],
    ['drivers', <Users size={20} />, 'Drivers', 'DRV'],
  ]
  const titles: Record<View, string> = {
    board: 'Fleet Board', map: 'Live Map', schedule: 'PM Schedule',
    orders: 'Work Orders', drivers: 'Drivers', detail: 'Truck Detail',
  }

  // Only owner/admin reach the fleet board from their garage dashboard, so only
  // they get an exit back to it. The fleet manager is a standalone role whose
  // entire app IS this board -- there is no dashboard to return to.
  const canReturnToDashboard = user?.role === 'garage_owner' || user?.role === 'garage_admin'

  return (
    <div className="fleet-root">
      <div className="app">
        <nav className={'rail' + (railExpanded ? ' is-expanded' : '')}>
          <div className="rail-mark"><Truck /></div>
          {canReturnToDashboard && (
            <>
              <button className="rail-btn rail-btn-back" onClick={() => navigate('/dashboard')}>
                <ArrowLeft size={20} /><span className="rail-abbr">Back</span><span className="rail-full">Back to dashboard</span><span className="rail-tip">Back to dashboard</span>
              </button>
              <div className="rail-div" />
            </>
          )}
          {railItems.map(([v, icon, tip, abbr]) => (
            <button key={v} className={'rail-btn' + (view === v || (v === 'board' && view === 'detail') ? ' is-on' : '')} onClick={() => goView(v)}>
              {icon}<span className="rail-abbr">{abbr}</span><span className="rail-full">{tip}</span><span className="rail-tip">{tip}</span>
            </button>
          ))}
          <div className="rail-sp" />
          <button className="rail-btn rail-btn-toggle" onClick={toggleRail} title={railExpanded ? 'Collapse' : 'Expand'}>
            {railExpanded ? <ChevronsLeft size={20} /> : <ChevronsRight size={20} />}
            <span className="rail-abbr">{railExpanded ? '«' : '»'}</span>
            <span className="rail-full">{railExpanded ? 'Collapse' : 'Expand'}</span>
            <span className="rail-tip">{railExpanded ? 'Collapse' : 'Expand'}</span>
          </button>
          <button className="rail-btn" onClick={() => setSettingsOpen(true)}>
            <Settings size={20} /><span className="rail-abbr">SET</span><span className="rail-full">Settings</span><span className="rail-tip">Settings</span>
          </button>
          <button className="rail-btn" onClick={async () => { try { await logout() } finally { navigate('/login', { replace: true }) } }}>
            <LogOut size={20} /><span className="rail-abbr">OUT</span><span className="rail-full">Log out</span><span className="rail-tip">Log out</span>
          </button>
          <button
            type="button"
            className="rail-av"
            onClick={() => setSettingsOpen(true)}
            title="Account settings"
            style={{ cursor: 'pointer', border: 'none' }}
          >
            {initials(`${user?.first_name || ''} ${user?.last_name || ''}`)}
          </button>
        </nav>

        <div className="main">
          <header className="topbar">
            <div className="topbar-l">
              <span className="topbar-title">{titles[view]}</span>
              <span className="topbar-sub">{user?.tenant_name || 'Truck Pit Stop'} · internal fleet</span>
            </div>
            <div className="topbar-r">
              <span className="topbar-clock" title={clock.toLocaleString('en-US', { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}>
                <span className="topbar-clock-full">{clock.toLocaleString('en-US', { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</span>
                <span className="topbar-clock-short">{clock.toLocaleString('en-US', { hour: 'numeric', minute: '2-digit' })}</span>
              </span>
              <button className="dbtn dbtn-yellow" onClick={() => setAdding(true)} title="Add truck"><Plus size={15} /> <span className="dbtn-label">Add truck</span></button>
              <button className="topbar-icbtn"><Bell size={17} />{!!data?.stats.incidents_total && <span className="dot" />}</button>
              <div className="topbar-user" title={`${user?.first_name || ''} ${user?.last_name || ''}`.trim() || 'Fleet Manager'}>
                <div className="topbar-user-av">{initials(`${user?.first_name || ''} ${user?.last_name || ''}`)}</div>
                <div className="topbar-user-txt">
                  <div className="nm">{`${user?.first_name || ''} ${user?.last_name || ''}`.trim() || 'Fleet Manager'}</div>
                  <div className="rl">Fleet manager</div>
                </div>
              </div>
            </div>
          </header>

          <div className="scroll">
            <div className="page-pad">
              {isLoading || !data ? (
                <div className="loader"><Spinner size="md" /></div>
              ) : view === 'detail' && selId ? (
                <TruckDetail truckId={selId} trucks={trucks} onBack={() => goView('board')} onOpen={openTruck} />
              ) : view === 'board' ? (
                <FleetBoard data={data} onOpen={(t) => openTruck(t.id)} filter={filter} setFilter={setFilter} query={query} setQuery={setQuery} sort={sort} setSort={setSort} />
              ) : view === 'map' ? (
                <MapPage trucks={trucks} onOpen={openTruck} />
              ) : view === 'schedule' ? (
                <SchedulePage trucks={trucks} onOpen={openTruck} />
              ) : view === 'orders' ? (
                <OrdersPage trucks={trucks} onOpen={openTruck} />
              ) : (
                <DriversPage trucks={trucks} onOpen={openTruck} />
              )}
            </div>
          </div>
        </div>
      </div>

      {adding && <AddTruckModal onClose={() => setAdding(false)} />}
      {settingsOpen && <FleetSettingsModal onClose={() => setSettingsOpen(false)} />}
    </div>
  )
}

/* ---- secondary views ---- */

function MapPage({ trucks, onOpen }: { trucks: BoardTruck[]; onOpen: (id: string) => void }) {
  return (
    <div className="mappage">
      <FleetMap trucks={trucks} onSelect={(t) => onOpen(t.id)} />
    </div>
  )
}

function SchedulePage({ trucks, onOpen }: { trucks: BoardTruck[]; onOpen: (id: string) => void }) {
  // Group by PM status so the trucks needing attention surface first: Overdue,
  // then Due soon, then the ones that are fine. Each group is sorted by how
  // close the PM is (fewest miles remaining first).
  const sorted = [...trucks].sort((a, b) => (a.pm_remaining ?? 1e9) - (b.pm_remaining ?? 1e9))
  const groups: { key: string; title: string; cls: string; trucks: BoardTruck[] }[] = [
    { key: 'over', title: 'Overdue', cls: 'u-over', trucks: [] },
    { key: 'soon', title: 'Due soon', cls: 'u-soon', trucks: [] },
    { key: 'ok', title: 'On track', cls: 'u-ok', trucks: [] },
  ]
  for (const t of sorted) {
    const cls = pmState(t).cls
    const g = cls === 'pm-over' ? groups[0] : cls === 'pm-soon' ? groups[1] : groups[2]
    g.trucks.push(t)
  }

  return (
    <div className="pm-groups">
      {groups.filter((g) => g.trucks.length > 0).map((g) => (
        <section key={g.key} className="pm-group">
          <h3 className="pm-group-h">
            <span className={'pm-group-dot ' + g.cls} />
            {g.title}
            <span className="pm-group-count">{g.trucks.length}</span>
          </h3>
          <div className="sgrid">
            {g.trucks.map((t) => (
              <PmCard key={t.id} truck={t} onOpen={onOpen} />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}

// The four PM lifecycle stages a schedule card can be in. The card exposes only
// the transitions valid from the current stage; the full work order (parts,
// labor, mechanic) still opens via the WorkOrderPanel.
type PmStage = 'none' | 'scheduled' | 'ready' | 'progress'

function pmStage(t: BoardTruck): PmStage {
  const wo = t.pm_work_order
  if (wo) {
    return ['in_progress', 'pending_review'].includes(wo.raw_status || '') ? 'progress' : 'ready'
  }
  // No PM work order yet: scheduled if a date or target odometer is set.
  if (t.pm_due_date || t.next_pm_miles != null) return 'scheduled'
  return 'none'
}

const STAGE_META: Record<PmStage, { label: string; cls: string }> = {
  none: { label: 'Not scheduled', cls: 'stg-none' },
  scheduled: { label: 'Scheduled', cls: '' },
  ready: { label: 'Work order ready', cls: 'stg-ready' },
  progress: { label: 'In progress', cls: 'stg-progress' },
}

function PmCard({ truck: t, onOpen }: { truck: BoardTruck; onOpen: (id: string) => void }) {
  const qc = useQueryClient()
  // null = closed; 'reschedule' = adjust schedule only; 'create' = pick services
  // and create the work order in one step (Schedule PM modal pre-set to create).
  const [scheduleMode, setScheduleMode] = useState<null | 'reschedule' | 'create'>(null)
  const [woPanelId, setWoPanelId] = useState<string | null>(null)

  const pm = pmState(t)
  const ucls = pm.cls === 'pm-over' ? 'u-over' : pm.cls === 'pm-soon' ? 'u-soon' : 'u-ok'
  const stage = pmStage(t)
  const stageMeta = STAGE_META[stage]
  // Starting/completing a PM changes the owner's cockpit queue too, not just the
  // fleet board — refresh both.
  const refresh = () => { invalidateFleetAndCockpit(qc); qc.invalidateQueries({ queryKey: ['fleet-truck', t.id] }) }

  const startPM = useMutation({
    mutationFn: async () => (await api.post(`/fleet/work-orders/${t.pm_work_order!.repair_order_id}/start`)).data,
    onSuccess: () => { toast.success('PM started'); refresh() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Failed to start PM'),
  })

  return (
    <div className="scard">
      <button className="scard-hd" onClick={() => onOpen(t.id)}>
        <div className="tcard-unit" style={{ fontSize: 20 }}>{t.unit_number}</div>
        <div className="tcard-mm">{`${t.year || ''} ${t.make} ${t.model}`.trim()}</div>
        <div className={'scard-urgency ' + ucls}>{pm.label}</div>
        <div className="tcard-odo" style={{ borderTop: 'none', paddingTop: 0 }}>
          <span>ODO</span><b>{fmt(t.odometer)}</b><span>mi</span>
        </div>
        {t.pm_services && t.pm_services.length > 0 && (
          <div className="scard-svcs" title={t.pm_services.map((s) => s.name).join(', ')}>
            {t.pm_services.map((s) => (
              <span key={s.service_id} className="scard-svc">{s.name}</span>
            ))}
          </div>
        )}
        <span className={'scard-stage ' + stageMeta.cls}>{stageMeta.label}</span>
      </button>

      {/* Green trucks with no open work order have no action — don't render an
          empty action bar for them. */}
      {(pm.cls !== 'pm-ok' || stage === 'ready' || stage === 'progress') && (
      <div className="scard-actions">
        {/* Scheduling actions only matter when the PM is actually approaching:
            green trucks (plenty of miles/time left) show no call to action.
            Reschedule = plan a future PM; Create work order = service it now. */}
        {stage === 'none' && pm.cls !== 'pm-ok' && (
          <button className="sbtn sbtn-yellow" onClick={() => setScheduleMode('reschedule')}>
            <Calendar size={14} /> Schedule PM
          </button>
        )}
        {stage === 'scheduled' && pm.cls !== 'pm-ok' && (
          <>
            <button className="sbtn" onClick={() => setScheduleMode('reschedule')}>
              <Calendar size={14} /> Reschedule
            </button>
            <button className="sbtn sbtn-yellow" onClick={() => setScheduleMode('create')}>
              <ClipboardCheck size={14} /> Create work order
            </button>
          </>
        )}
        {stage === 'ready' && (
          <>
            <button className="sbtn" onClick={() => setWoPanelId(t.pm_work_order!.repair_order_id)}>
              <Wrench size={14} /> Open WO
            </button>
            <button className="sbtn sbtn-yellow" disabled={startPM.isPending} onClick={() => startPM.mutate()}>
              {startPM.isPending ? <Spinner size="xs" /> : <Play size={14} />} Start PM
            </button>
          </>
        )}
        {stage === 'progress' && (
          <button className="sbtn sbtn-yellow" onClick={() => setWoPanelId(t.pm_work_order!.repair_order_id)}>
            <Flag size={14} /> Complete PM
          </button>
        )}
      </div>
      )}

      {scheduleMode && (
        <SchedulePMModal
          truck={t}
          createMode={scheduleMode === 'create'}
          onClose={() => setScheduleMode(null)}
          onDone={refresh}
        />
      )}
      {woPanelId && <WorkOrderPanel repairOrderId={woPanelId} onClose={() => setWoPanelId(null)} onChanged={refresh} />}
    </div>
  )
}

function OrdersPage({ trucks, onOpen }: { trucks: BoardTruck[]; onOpen: (id: string) => void }) {
  const list = trucks.filter((t) => t.work_order)
  if (!list.length) return <div className="tgrid-empty">No open work orders.</div>
  return (
    <div className="list-rows">
      {list.map((t) => (
        <button key={t.id} className="lrow" onClick={() => onOpen(t.id)}>
          <i className="lrow-dot" style={{ background: STATUS_META[t.status].dot }} />
          <span className="lrow-unit">{t.unit_number}</span>
          <span className="lrow-mono">{t.work_order!.id}</span>
          <span className="lrow-tx">{t.work_order!.summary || '—'}</span>
          <span className="lrow-r">
            <span className="lrow-st">{t.work_order!.status}</span>
            <span className="lrow-tx">{t.work_order!.mechanic || 'Unassigned'}</span>
          </span>
        </button>
      ))}
    </div>
  )
}

function DriversPage({ trucks, onOpen }: { trucks: BoardTruck[]; onOpen: (id: string) => void }) {
  return (
    <div className="sgrid">
      {trucks.map((t) => (
        <button key={t.id} className="scard" onClick={() => onOpen(t.id)} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div className="avatar">{initials(t.driver_name)}</div>
          <div style={{ textAlign: 'left', minWidth: 0 }}>
            <div className="person-name">{t.driver_name || 'Unassigned'}</div>
            <div className="person-role">{t.unit_number} · {`${t.make} ${t.model}`}</div>
            {t.driver_phone && <div className="person-role">{formatUSPhone(t.driver_phone)}</div>}
          </div>
          <i className="lrow-dot" style={{ background: STATUS_META[t.status].dot, marginLeft: 'auto' }} />
        </button>
      ))}
    </div>
  )
}

/* ---- add truck ---- */

function AddTruckModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [mode, setMode] = useState<'new' | 'existing'>('new')
  const [customerId, setCustomerId] = useState('')
  const [vehicleSearch, setVehicleSearch] = useState('')
  const debouncedVehicleSearch = useDebouncedValue(vehicleSearch, 250)
  const [existingVehicleId, setExistingVehicleId] = useState('')
  const [form, setForm] = useState({ make: '', model: '', year: '', unit_number: '', vin: '', license_plate: '', mileage: '', driver_name: '', driver_phone: '' })
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const [decoding, setDecoding] = useState(false)

  // Decode a VIN against the NHTSA vPIC database to auto-fill make/model/year.
  // Plate and unit number are not in the VIN — the fleet manager enters those.
  const decodeVin = async (raw: string) => {
    const vin = raw.trim().toUpperCase()
    if (vin.length !== 17) return
    setDecoding(true)
    try {
      const { data } = await api.get(`/customers/vin/decode/${encodeURIComponent(vin)}`)
      if (!data.make && !data.model) {
        toast.error(data.error_text || 'No match found for that VIN')
        return
      }
      setForm((f) => ({
        ...f,
        make: data.make || f.make,
        model: data.model || f.model,
        year: data.year ? String(data.year) : f.year,
      }))
      toast.success(`Decoded: ${[data.year, data.make, data.model].filter(Boolean).join(' ')}`)
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Failed to decode VIN')
    } finally {
      setDecoding(false)
    }
  }
  const { data: companies = [] } = useQuery<Array<{ id: string; company_name: string; fleet_enabled: boolean; is_internal_fleet: boolean }>>({
    queryKey: ['fleet-companies'],
    queryFn: async () => (await api.get('/fleet/companies')).data,
  })
  const { data: vehicleCandidates = [] } = useQuery<Array<{ id: string; make: string; model: string; year?: number | null; unit_number?: string | null; vin?: string | null }>>({
    queryKey: ['fleet-vehicle-candidates', debouncedVehicleSearch],
    queryFn: async () => (await api.get('/fleet/vehicle-candidates', { params: { q: debouncedVehicleSearch || undefined, limit: 50 } })).data,
    enabled: mode === 'existing',
  })
  const create = useMutation({
    mutationFn: async () => {
      if (!customerId) throw new Error('Select the company that operates this truck')
      if (mode === 'existing') {
        if (!existingVehicleId) throw new Error('Select an existing truck')
        return (await api.post('/fleet/memberships', {
          vehicle_id: existingVehicleId,
          fleet_customer_id: customerId,
        })).data
      }
      return (await api.post('/fleet/trucks', {
          customer_id: customerId,
          make: form.make.trim(), model: form.model.trim(),
          year: form.year ? parseInt(form.year, 10) : undefined,
          unit_number: form.unit_number.trim() || undefined,
          vin: form.vin.trim() || undefined,
          license_plate: form.license_plate.trim() || undefined,
          mileage: form.mileage ? parseInt(form.mileage, 10) : undefined,
          driver_name: form.driver_name.trim() || undefined,
          driver_phone: form.driver_phone.trim() || undefined,
        })).data
    },
    onSuccess: () => {
      toast.success(mode === 'existing' ? 'Existing truck linked to fleet' : 'Truck added to fleet')
      qc.invalidateQueries({ queryKey: ['fleet-board'] })
      qc.invalidateQueries({ queryKey: ['fleet-companies'] })
      onClose()
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || e.message || 'Failed to add truck'),
  })
  const inp = 'w-full'
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.6)', zIndex: 60, display: 'grid', placeItems: 'center' }} onClick={onClose}>
      <div className="dsec" style={{ width: 480, maxWidth: '92vw' }} onClick={(e) => e.stopPropagation()}>
        <div className="dsec-head">
          <div className="dsec-title"><Wrench size={17} /><h3>Add truck</h3></div>
          <button className="person-call" onClick={onClose}><X size={15} /></button>
        </div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
          <button type="button" className={`dbtn ${mode === 'new' ? 'dbtn-yellow' : 'dbtn-ghost'}`} onClick={() => setMode('new')}>New truck</button>
          <button type="button" className={`dbtn ${mode === 'existing' ? 'dbtn-yellow' : 'dbtn-ghost'}`} onClick={() => setMode('existing')}>Link existing truck</button>
        </div>
        <Field label="Operating company / fleet *">
          <select className="w-full" value={customerId} onChange={(e) => setCustomerId(e.target.value)}>
            <option value="">Select company…</option>
            {companies.map((company) => (
              <option key={company.id} value={company.id}>
                {company.company_name}{company.is_internal_fleet ? ' (internal)' : ''}
              </option>
            ))}
          </select>
        </Field>
        {mode === 'existing' ? (
          <div style={{ display: 'grid', gap: 12, marginTop: 12 }}>
            <Field label="Find truck by VIN, unit, plate, make, or model">
              <input className="w-full" value={vehicleSearch} onChange={(e) => setVehicleSearch(e.target.value)} placeholder="Search existing trucks…" />
            </Field>
            <Field label="Existing truck *">
              <select className="w-full" value={existingVehicleId} onChange={(e) => setExistingVehicleId(e.target.value)}>
                <option value="">Select truck…</option>
                {vehicleCandidates.map((vehicle) => (
                  <option key={vehicle.id} value={vehicle.id}>
                    {[vehicle.unit_number ? `Unit ${vehicle.unit_number}` : null, vehicle.year, vehicle.make, vehicle.model, vehicle.vin ? `VIN …${vehicle.vin.slice(-6)}` : null].filter(Boolean).join(' · ')}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div style={{ gridColumn: '1 / -1' }}>
            <span className="id-k" style={{ display: 'block', marginBottom: 5 }}>VIN — paste to auto-fill make / model / year</span>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                className={inp}
                value={form.vin}
                onChange={(e) => {
                  const v = e.target.value.toUpperCase()
                  setForm((f) => ({ ...f, vin: v }))
                  if (v.trim().length === 17) decodeVin(v)
                }}
                placeholder="17-character VIN"
                maxLength={17}
              />
              <button className="dbtn dbtn-ghost" type="button" onClick={() => decodeVin(form.vin)} disabled={decoding || form.vin.trim().length !== 17}>
                {decoding ? <Spinner size="xs" /> : 'Decode'}
              </button>
            </div>
          </div>
          <Field label="Make *"><input className={inp} value={form.make} onChange={set('make')} placeholder="Freightliner" /></Field>
          <Field label="Model *"><input className={inp} value={form.model} onChange={set('model')} placeholder="Cascadia" /></Field>
          <Field label="Year"><input className={inp} value={form.year} onChange={set('year')} inputMode="numeric" placeholder="2021" /></Field>
          <Field label="Unit #"><input className={inp} value={form.unit_number} onChange={set('unit_number')} placeholder="TPS-109" /></Field>
          <Field label="Mileage"><input className={inp} value={form.mileage} onChange={set('mileage')} inputMode="numeric" placeholder="120000" /></Field>
          <Field label="Plate"><input className={inp} value={form.license_plate} onChange={set('license_plate')} placeholder="ABC-1234" /></Field>
          <Field label="Driver"><input className={inp} value={form.driver_name} onChange={set('driver_name')} placeholder="Driver name (optional)" /></Field>
          <Field label="Driver phone"><input className={inp} value={form.driver_phone} onChange={(e) => setForm((f) => ({ ...f, driver_phone: formatUSPhone(e.target.value) }))} placeholder="(704) 555-0123" /></Field>
        </div>
        )}
        <button className="dbtn dbtn-yellow" style={{ marginTop: 16, width: '100%', justifyContent: 'center' }}
          disabled={!customerId || (mode === 'new' ? (!form.make.trim() || !form.model.trim()) : !existingVehicleId) || create.isPending} onClick={() => create.mutate()}>
          {create.isPending ? <Spinner size="sm" /> : <Plus size={15} />} {mode === 'existing' ? 'Link truck' : 'Add truck'}
        </button>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'block' }}>
      <span className="id-k" style={{ display: 'block', marginBottom: 5 }}>{label}</span>
      {children}
    </label>
  )
}

/* ---- account settings (fleet manager self-service) ---- */

function FleetSettingsModal({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()
  const { user, setUser, logout } = useAuthStore()

  const [profile, setProfile] = useState({
    first_name: user?.first_name || '',
    last_name: user?.last_name || '',
    phone: user?.phone || '',
    email: user?.email || '',
  })
  const setP = (k: keyof typeof profile) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setProfile((p) => ({ ...p, [k]: e.target.value }))
  const emailChanged = profile.email.trim() !== (user?.email || '')

  const [pwd, setPwd] = useState({ current_password: '', new_password: '' })
  const [showPwd, setShowPwd] = useState(false)
  const [pwdOpen, setPwdOpen] = useState(false)
  // Close the password sub-panel and clear its fields.
  const closePwd = () => { setPwdOpen(false); setShowPwd(false); setPwd({ current_password: '', new_password: '' }) }
  const [saving, setSaving] = useState(false)

  const [profileEditing, setProfileEditing] = useState(false)
  const cancelProfileEdit = () => {
    setProfileEditing(false)
    setProfile({
      first_name: user?.first_name || '',
      last_name: user?.last_name || '',
      phone: user?.phone || '',
      email: user?.email || '',
    })
    closePwd()
  }

  // Current password serves double duty: required to change email, and it's the
  // "current password" for a password change. Email-change and password-change
  // both need it, so a single field feeds both.
  const wantsPasswordChange = pwd.new_password.trim() !== ''


  const save = async () => {
    if (!profile.first_name.trim() || !profile.last_name.trim()) {
      toast.error('First and last name are required')
      return
    }
    if ((emailChanged || wantsPasswordChange) && !pwd.current_password) {
      toast.error('Enter your current password to save these changes')
      return
    }
    if (wantsPasswordChange) {
      const err = getPasswordValidationError(pwd.new_password)
      if (err) { toast.error(err); return }
    }
    try {
      setSaving(true)
      const payload: Record<string, unknown> = {
        first_name: profile.first_name.trim(),
        last_name: profile.last_name.trim(),
        phone: profile.phone.trim() || null,
        email: profile.email.trim(),
      }
      if (emailChanged) payload.password = pwd.current_password
      const res = await api.put('/auth/me', payload)
      if (res.data?.user) setUser(res.data.user)

      if (wantsPasswordChange) {
        // Changing the password invalidates all sessions — force a fresh login.
        await api.post('/auth/change-password', {
          current_password: pwd.current_password,
          new_password: pwd.new_password,
        })
        toast.success('Profile saved. Password changed — please log in again.')
        try { await logout() } finally { navigate('/login', { replace: true }) }
        return
      }
      // Email changes return a verification message; name/phone return the user.
      toast.success(res.data?.message || 'Profile updated')
      closePwd()
      setProfileEditing(false)
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Failed to save changes')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.6)', zIndex: 60, display: 'grid', placeItems: 'center', padding: 16 }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ width: 520, maxWidth: '92vw', maxHeight: '90vh', overflowY: 'auto', display: 'grid', gap: 14 }}
      >
        {/* Account */}
        <div className="dsec">
          <div className="dsec-head">
            <div className="dsec-title"><UserRound size={17} /><h3>My account</h3></div>
            <div style={{ display: 'flex', gap: 8 }}>
              {!profileEditing && (
                <button className="person-call" onClick={() => setProfileEditing(true)} aria-label="Edit account">
                  <Pencil size={15} />
                </button>
              )}
              <button className="person-call" onClick={onClose}><X size={15} /></button>
            </div>
          </div>

          {!profileEditing ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <Field label="First name"><div className="id-v">{profile.first_name || '—'}</div></Field>
              <Field label="Last name"><div className="id-v">{profile.last_name || '—'}</div></Field>
              <Field label="Phone"><div className="id-v">{profile.phone || '—'}</div></Field>
              <Field label="Email"><div className="id-v">{profile.email || '—'}</div></Field>
            </div>
          ) : (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <Field label="First name"><input value={profile.first_name} onChange={setP('first_name')} /></Field>
                <Field label="Last name"><input value={profile.last_name} onChange={setP('last_name')} /></Field>
                <Field label="Phone"><input value={profile.phone} onChange={setP('phone')} placeholder="(704) 555-0123" /></Field>
                <Field label="Email"><input value={profile.email} onChange={setP('email')} type="email" /></Field>
                {emailChanged && (
                  <div style={{ gridColumn: '1 / -1' }}>
                    <Field label="Current password (required to change email)">
                      <input value={pwd.current_password} onChange={(e) => setPwd((p) => ({ ...p, current_password: e.target.value }))} type="password" />
                    </Field>
                    <p className="id-k" style={{ marginTop: 6, textTransform: 'none', letterSpacing: 0 }}>
                      We'll send a verification link to the new address; your email changes once you confirm it.
                    </p>
                  </div>
                )}
              </div>

              {/* Password */}
              <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border, rgba(255,255,255,.08))' }}>
                <div className="dsec-title" style={{ marginBottom: 12 }}><KeyRound size={17} /><h3>Password</h3></div>
                {!pwdOpen ? (
                  <button className="dbtn dbtn-ghost" style={{ width: '100%', justifyContent: 'center' }} onClick={() => setPwdOpen(true)}>
                    <KeyRound size={15} /> Change password
                  </button>
                ) : (
                  <div style={{ display: 'grid', gap: 12 }}>
                    <Field label="Current password">
                      <input value={pwd.current_password} onChange={(e) => setPwd((p) => ({ ...p, current_password: e.target.value }))} type="password" autoFocus />
                    </Field>
                    <Field label="New password">
                      <div style={{ position: 'relative' }}>
                        <input
                          value={pwd.new_password}
                          onChange={(e) => setPwd((p) => ({ ...p, new_password: e.target.value }))}
                          type={showPwd ? 'text' : 'password'}
                          style={{ paddingRight: 40 }}
                        />
                        <button
                          type="button"
                          onClick={() => setShowPwd((s) => !s)}
                          aria-label={showPwd ? 'Hide password' : 'Show password'}
                          style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer' }}
                        >
                          {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
                        </button>
                      </div>
                    </Field>
                    <button className="dbtn dbtn-ghost" style={{ justifyContent: 'center' }} disabled={saving} onClick={closePwd}>
                      Cancel password change
                    </button>
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
                <button className="dbtn dbtn-ghost" style={{ flex: 1, justifyContent: 'center' }} disabled={saving} onClick={cancelProfileEdit}>
                  Cancel
                </button>
                <button className="dbtn dbtn-yellow" style={{ flex: 1, justifyContent: 'center' }}
                  disabled={saving} onClick={save}>
                  {saving ? <Spinner size="sm" /> : <UserRound size={15} />} Save changes
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
