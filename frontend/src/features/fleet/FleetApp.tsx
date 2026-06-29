import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  Truck, LayoutGrid, Map as MapIcon, CalendarRange, ClipboardList, Users,
  Bell, LogOut, Plus, Loader2, X, Wrench, ArrowLeft,
} from 'lucide-react'
import api from '../../lib/api'
import { useAuthStore } from '../../stores/authStore'
import type { BoardTruck, FleetBoard as FleetBoardData } from './types'
import { STATUS_META, fmt, pmState, initials } from './helpers'
import FleetBoard from './FleetBoard'
import TruckDetail from './TruckDetail'
import FleetMap from './FleetMap'
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
  const [clock, setClock] = useState(() => new Date())

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

  const railItems: [View, React.ReactNode, string][] = [
    ['board', <LayoutGrid size={20} />, 'Fleet board'],
    ['map', <MapIcon size={20} />, 'Live map'],
    ['schedule', <CalendarRange size={20} />, 'PM schedule'],
    ['orders', <ClipboardList size={20} />, 'Work orders'],
    ['drivers', <Users size={20} />, 'Drivers'],
  ]
  const titles: Record<View, string> = {
    board: 'Fleet Board', map: 'Live Map', schedule: 'PM Schedule',
    orders: 'Work Orders', drivers: 'Drivers', detail: 'Truck Detail',
  }

  // Exit the immersive fleet workspace back to the main dashboard shell.
  // Fleet managers land on /dashboard/repair-orders because /dashboard
  // redirects them straight back to /fleet.
  const backToDashboard = () =>
    navigate(user?.role === 'fleet_manager' ? '/dashboard/repair-orders' : '/dashboard')

  return (
    <div className="fleet-root">
      <div className="app">
        <nav className="rail">
          <div className="rail-mark"><Truck /></div>
          <button className="rail-btn rail-btn-back" onClick={backToDashboard}>
            <ArrowLeft size={20} /><span className="rail-tip">Back to dashboard</span>
          </button>
          <div className="rail-div" />
          {railItems.map(([v, icon, tip]) => (
            <button key={v} className={'rail-btn' + (view === v || (v === 'board' && view === 'detail') ? ' is-on' : '')} onClick={() => goView(v)}>
              {icon}<span className="rail-tip">{tip}</span>
            </button>
          ))}
          <div className="rail-sp" />
          <button className="rail-btn" onClick={async () => { try { await logout() } finally { navigate('/login', { replace: true }) } }}>
            <LogOut size={20} /><span className="rail-tip">Log out</span>
          </button>
          <div className="rail-av">{initials(`${user?.first_name || ''} ${user?.last_name || ''}`)}</div>
        </nav>

        <div className="main">
          <header className="topbar">
            <div className="topbar-l">
              <span className="topbar-title">{titles[view]}</span>
              <span className="topbar-sub">{user?.tenant_name || 'Truck Pit Stop'} · internal fleet</span>
            </div>
            <div className="topbar-r">
              <span className="topbar-clock">{clock.toLocaleString('en-US', { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</span>
              <button className="dbtn dbtn-yellow" onClick={() => setAdding(true)}><Plus size={15} /> Add truck</button>
              <button className="topbar-icbtn"><Bell size={17} />{!!data?.stats.incidents_total && <span className="dot" />}</button>
              <div className="topbar-user">
                <div>
                  <div className="nm">{`${user?.first_name || ''} ${user?.last_name || ''}`.trim() || 'Fleet Manager'}</div>
                  <div className="rl">Fleet manager</div>
                </div>
              </div>
            </div>
          </header>

          <div className="scroll">
            <div className="page-pad">
              {isLoading || !data ? (
                <div className="loader"><Loader2 size={20} className="animate-spin" /></div>
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
  const list = [...trucks].sort((a, b) => (a.pm_remaining ?? 1e9) - (b.pm_remaining ?? 1e9)).slice(0, 12)
  return (
    <div className="sgrid">
      {list.map((t) => {
        const pm = pmState(t)
        const ucls = pm.cls === 'pm-over' ? 'u-over' : pm.cls === 'pm-soon' ? 'u-soon' : 'u-ok'
        return (
          <button key={t.id} className="scard" onClick={() => onOpen(t.id)}>
            <div className="tcard-unit" style={{ fontSize: 20 }}>{t.unit_number}</div>
            <div className="tcard-mm">{`${t.year || ''} ${t.make} ${t.model}`.trim()}</div>
            <div className={'scard-urgency ' + ucls}>{pm.label}</div>
            <div className="tcard-odo" style={{ borderTop: 'none', paddingTop: 0 }}>
              <span>ODO</span><b>{fmt(t.odometer)}</b><span>mi · next at {fmt(t.next_pm_miles)}</span>
            </div>
          </button>
        )
      })}
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
  const [form, setForm] = useState({ make: '', model: '', year: '', unit_number: '', vin: '', license_plate: '', mileage: '' })
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const [decoding, setDecoding] = useState(false)

  // Decode a VIN against the NHTSA vPIC database to auto-fill make/model/year.
  // Plate and unit number are not in the VIN — the fleet manager enters those.
  const decodeVin = async (raw: string) => {
    const vin = raw.trim().toUpperCase()
    if (vin.length !== 17) return
    setDecoding(true)
    try {
      const { data } = await api.get(`/customers/vin/decode/${vin}`)
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
  const { data: fleetCustomer } = useQuery<{ id: string }>({
    queryKey: ['internal-fleet-customer'],
    queryFn: async () => (await api.get('/customers/internal-fleet')).data,
  })
  const create = useMutation({
    mutationFn: async () => {
      if (!fleetCustomer?.id) throw new Error('Fleet account not ready')
      return (await api.post('/vehicles', {
        customer_id: fleetCustomer.id,
        make: form.make.trim(), model: form.model.trim(),
        year: form.year ? parseInt(form.year, 10) : undefined,
        unit_number: form.unit_number.trim() || undefined,
        vin: form.vin.trim() || undefined,
        license_plate: form.license_plate.trim() || undefined,
        mileage: form.mileage ? parseInt(form.mileage, 10) : undefined,
      })).data
    },
    onSuccess: () => { toast.success('Truck added to fleet'); qc.invalidateQueries({ queryKey: ['fleet-board'] }); onClose() },
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
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div style={{ gridColumn: '1 / -1' }}>
            <span className="id-k" style={{ display: 'block', marginBottom: 5 }}>VIN — paste to auto-fill make / model / year</span>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                className={inp}
                value={form.vin}
                onChange={(e) => {
                  const v = e.target.value
                  setForm((f) => ({ ...f, vin: v }))
                  if (v.trim().length === 17) decodeVin(v)
                }}
                placeholder="17-character VIN"
              />
              <button className="dbtn dbtn-ghost" type="button" onClick={() => decodeVin(form.vin)} disabled={decoding || form.vin.trim().length !== 17}>
                {decoding ? <Loader2 size={14} className="animate-spin" /> : 'Decode'}
              </button>
            </div>
          </div>
          <Field label="Make *"><input className={inp} value={form.make} onChange={set('make')} placeholder="Freightliner" /></Field>
          <Field label="Model *"><input className={inp} value={form.model} onChange={set('model')} placeholder="Cascadia" /></Field>
          <Field label="Year"><input className={inp} value={form.year} onChange={set('year')} inputMode="numeric" placeholder="2021" /></Field>
          <Field label="Unit #"><input className={inp} value={form.unit_number} onChange={set('unit_number')} placeholder="TPS-109" /></Field>
          <Field label="Mileage"><input className={inp} value={form.mileage} onChange={set('mileage')} inputMode="numeric" placeholder="120000" /></Field>
          <Field label="Plate"><input className={inp} value={form.license_plate} onChange={set('license_plate')} placeholder="ABC-1234" /></Field>
        </div>
        <button className="dbtn dbtn-yellow" style={{ marginTop: 16, width: '100%', justifyContent: 'center' }}
          disabled={!form.make.trim() || !form.model.trim() || create.isPending} onClick={() => create.mutate()}>
          {create.isPending ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />} Add truck
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
