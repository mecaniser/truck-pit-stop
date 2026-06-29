import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  Truck, LayoutGrid, Map as MapIcon, CalendarRange, ClipboardList, Users,
  Bell, LogOut, Plus, Loader2, X, Wrench, ArrowLeft, Settings, UserRound, KeyRound, Eye, EyeOff,
} from 'lucide-react'
import api from '../../lib/api'
import { useAuthStore } from '../../stores/authStore'
import { getPasswordValidationError } from '../../lib/passwordPolicy'
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
  const [settingsOpen, setSettingsOpen] = useState(false)
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

  // Only owner/admin reach the fleet board from their garage dashboard, so only
  // they get an exit back to it. The fleet manager is a standalone role whose
  // entire app IS this board -- there is no dashboard to return to.
  const canReturnToDashboard = user?.role === 'garage_owner' || user?.role === 'garage_admin'

  return (
    <div className="fleet-root">
      <div className="app">
        <nav className="rail">
          <div className="rail-mark"><Truck /></div>
          {canReturnToDashboard && (
            <>
              <button className="rail-btn rail-btn-back" onClick={() => navigate('/dashboard')}>
                <ArrowLeft size={20} /><span className="rail-tip">Back to dashboard</span>
              </button>
              <div className="rail-div" />
            </>
          )}
          {railItems.map(([v, icon, tip]) => (
            <button key={v} className={'rail-btn' + (view === v || (v === 'board' && view === 'detail') ? ' is-on' : '')} onClick={() => goView(v)}>
              {icon}<span className="rail-tip">{tip}</span>
            </button>
          ))}
          <div className="rail-sp" />
          <button className="rail-btn" onClick={() => setSettingsOpen(true)}>
            <Settings size={20} /><span className="rail-tip">Settings</span>
          </button>
          <button className="rail-btn" onClick={async () => { try { await logout() } finally { navigate('/login', { replace: true }) } }}>
            <LogOut size={20} /><span className="rail-tip">Log out</span>
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
  const [emailPassword, setEmailPassword] = useState('')
  const [savingProfile, setSavingProfile] = useState(false)

  const [pwd, setPwd] = useState({ current_password: '', new_password: '' })
  const [showPwd, setShowPwd] = useState(false)
  const [savingPwd, setSavingPwd] = useState(false)

  const saveProfile = async () => {
    if (!profile.first_name.trim() || !profile.last_name.trim()) {
      toast.error('First and last name are required')
      return
    }
    if (emailChanged && !emailPassword) {
      toast.error('Enter your current password to change your email')
      return
    }
    try {
      setSavingProfile(true)
      const payload: Record<string, unknown> = {
        first_name: profile.first_name.trim(),
        last_name: profile.last_name.trim(),
        phone: profile.phone.trim() || null,
        email: profile.email.trim(),
      }
      if (emailChanged) payload.password = emailPassword
      const res = await api.put('/auth/me', payload)
      if (res.data?.user) setUser(res.data.user)
      // Email changes return a verification message; name/phone return the user.
      toast.success(res.data?.message || 'Profile updated')
      setEmailPassword('')
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Failed to update profile')
    } finally {
      setSavingProfile(false)
    }
  }

  const savePassword = async () => {
    if (!pwd.current_password) {
      toast.error('Enter your current password')
      return
    }
    const err = getPasswordValidationError(pwd.new_password)
    if (err) {
      toast.error(err)
      return
    }
    try {
      setSavingPwd(true)
      await api.post('/auth/change-password', {
        current_password: pwd.current_password,
        new_password: pwd.new_password,
      })
      // Changing the password invalidates all sessions — force a fresh login.
      toast.success('Password changed. Please log in again.')
      try { await logout() } finally { navigate('/login', { replace: true }) }
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Failed to change password')
    } finally {
      setSavingPwd(false)
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
        {/* Profile */}
        <div className="dsec">
          <div className="dsec-head">
            <div className="dsec-title"><UserRound size={17} /><h3>My account</h3></div>
            <button className="person-call" onClick={onClose}><X size={15} /></button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Field label="First name"><input value={profile.first_name} onChange={setP('first_name')} /></Field>
            <Field label="Last name"><input value={profile.last_name} onChange={setP('last_name')} /></Field>
            <Field label="Phone"><input value={profile.phone} onChange={setP('phone')} placeholder="(704) 555-0123" /></Field>
            <Field label="Email"><input value={profile.email} onChange={setP('email')} type="email" /></Field>
            {emailChanged && (
              <div style={{ gridColumn: '1 / -1' }}>
                <Field label="Current password (required to change email)">
                  <input value={emailPassword} onChange={(e) => setEmailPassword(e.target.value)} type="password" />
                </Field>
                <p className="id-k" style={{ marginTop: 6, textTransform: 'none', letterSpacing: 0 }}>
                  We'll send a verification link to the new address; your email changes once you confirm it.
                </p>
              </div>
            )}
          </div>
          <button className="dbtn dbtn-yellow" style={{ marginTop: 16, width: '100%', justifyContent: 'center' }}
            disabled={savingProfile} onClick={saveProfile}>
            {savingProfile ? <Loader2 size={15} className="animate-spin" /> : <UserRound size={15} />} Save profile
          </button>
        </div>

        {/* Password */}
        <div className="dsec">
          <div className="dsec-head">
            <div className="dsec-title"><KeyRound size={17} /><h3>Password</h3></div>
          </div>
          <div style={{ display: 'grid', gap: 12 }}>
            <Field label="Current password">
              <input value={pwd.current_password} onChange={(e) => setPwd((p) => ({ ...p, current_password: e.target.value }))} type="password" />
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
          </div>
          <button className="dbtn dbtn-yellow" style={{ marginTop: 16, width: '100%', justifyContent: 'center' }}
            disabled={savingPwd} onClick={savePassword}>
            {savingPwd ? <Loader2 size={15} className="animate-spin" /> : <KeyRound size={15} />} Change password
          </button>
        </div>
      </div>
    </div>
  )
}
