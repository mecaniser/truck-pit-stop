import { useCallback, useEffect, useMemo, useState } from 'react'
import { Spinner } from '@/components/ui'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  Truck, LayoutGrid, Map as MapIcon, Calendar, Play, Flag, ClipboardCheck, ArrowLeft,
  Bell, LogOut, Plus, Wrench, Warehouse, Settings, UserRound, KeyRound, Eye, EyeOff,
  ChevronsLeft, ChevronsRight, Pencil, Search, Check,
} from 'lucide-react'
import api from '../../lib/api'
import { useAuthStore } from '../../stores/authStore'
import { getPasswordValidationError } from '../../lib/passwordPolicy'
import type { BoardTruck, FleetBoard as FleetBoardData } from './types'
import { STATUS_META, fleetUnitLabel, fmt, pmState, initials } from './helpers'
import { formatUSPhone } from '@/utils/phone'
import { duplicateVinConflict, duplicateVinTruckLabel, type DuplicateVinConflict } from './duplicateVin'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import FleetBoard from './FleetBoard'
import TruckDetail from './TruckDetail'
import FleetMap from './FleetMap'
import { SchedulePMModal, SidekickPanel, WorkOrderPanel, invalidateFleetAndCockpit } from './FleetModals'
import './fleet.css'

type View = 'board' | 'map' | 'detail'
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
  const [woPanelId, setWoPanelId] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [railExpanded, setRailExpanded] = useState(() => localStorage.getItem('tps-fleet-rail') === '1')

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ view, selId, filter, sort }))
  }, [view, selId, filter, sort])

  const { data, isLoading, isError, refetch } = useQuery<FleetBoardData>({
    queryKey: ['fleet-board'],
    queryFn: async () => (await api.get('/fleet/board')).data,
    refetchInterval: 60000,
  })
  const trucks = data?.trucks || []
  const fleetStatusSummary = useMemo(() => [
    ['active', 'on road'],
    ['shop', 'in shop'],
    ['pm', 'PM due'],
    ['parts', 'awaiting parts'],
    ['draft', 'awaiting assignment'],
    ['yard', 'in yard'],
    ['available', 'available'],
    ['out_of_service', 'out of service'],
  ].map(([status, label]) => ({ status, label, count: trucks.filter((truck) => truck.status === status).length })).filter((item) => item.count > 0), [trucks])

  const detailTruck = selId ? trucks.find((truck) => truck.id === selId) : undefined

  const openTruck = useCallback((id: string) => { setSelId(id); setView('detail'); document.querySelector('.fleet-root .scroll')?.scrollTo(0, 0) }, [])
  const goView = (v: View) => { setView(v); if (v !== 'detail') setSelId(null) }
  const toggleRail = () => setRailExpanded((v) => { localStorage.setItem('tps-fleet-rail', v ? '0' : '1'); return !v })

  const railItems: [View, React.ReactNode, string, string][] = [
    ['board', <LayoutGrid size={20} />, 'Fleet board', 'FB'],
    ['map', <MapIcon size={20} />, 'Live map', 'MAP'],
  ]
  const titles: Record<View, string> = {
    board: 'Fleet Board', map: 'Live Map', detail: 'Truck Detail',
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
              <button className="rail-btn rail-btn-dashboard" onClick={() => navigate('/dashboard')}>
                <Warehouse size={20} /><span className="rail-abbr">SHOP</span><span className="rail-full">Shop</span><span className="rail-tip">Shop dashboard</span>
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
            className="rail-user"
            onClick={() => setSettingsOpen(true)}
            title="Account settings"
          >
            <span className="rail-av">{initials(`${user?.first_name || ''} ${user?.last_name || ''}`)}</span>
            <span className="rail-full">{`${user?.first_name || ''} ${user?.last_name || ''}`.trim() || 'Fleet manager'}</span>
            <span className="rail-tip">Account settings</span>
          </button>
        </nav>

        <div className="main">
          {/* Inside a truck, the bar belongs to that truck: fleet-wide counts and
              "Add truck" describe the board, not the unit in front of you. The
              detail page therefore owns the bar's title, and its back link
              lives here rather than inside the scrolling page body. */}
          <header className={'topbar' + (view === 'detail' ? ' topbar-detail' : '')}>
            <div className="topbar-l">
              {view === 'detail' ? (
                <>
                  <button className="topbar-back" onClick={() => goView('board')}>
                    <ArrowLeft size={17} /> <span>Fleet board</span>
                  </button>
                  <span className="topbar-title topbar-title-unit">{detailTruck ? fleetUnitLabel(detailTruck) : 'Truck'}</span>
                </>
              ) : (
                <>
                  <span className="topbar-title">{titles[view]}</span>
                  <span className="topbar-context">
                    <span className="topbar-tenant">{user?.tenant_name || 'Truck Pit Stop'}</span>
                    {data ? (
                      <span className="topbar-fleet-state" aria-label={`${data.stats.total} total units: ${fleetStatusSummary.map((item) => `${item.count} ${item.label}`).join(', ')}`}>
                        <span><b>{data.stats.total}</b> units</span>
                        <span className="topbar-fleet-breakdown">
                          {fleetStatusSummary.map((item) => <span key={item.status}><i /> <b>{item.count}</b> {item.label}</span>)}
                        </span>
                      </span>
                    ) : <span className="topbar-fleet-state">Internal fleet</span>}
                  </span>
                </>
              )}
            </div>
            {view !== 'detail' && (
              <div className="topbar-r">
                <button className="dbtn dbtn-yellow" onClick={() => setAdding(true)} title="Add truck"><Plus size={15} /> <span className="dbtn-label">Add truck</span></button>
                <div className="topbar-utilities">
                  <button className="topbar-icbtn" title="Notifications" aria-label="Notifications"><Bell size={17} />{!!data?.stats.incidents_total && <span className="dot" />}</button>
                </div>
              </div>
            )}
          </header>

          <div className="scroll">
            <div className="page-pad">
              {isLoading ? (
                <div className="loader"><Spinner size="md" /></div>
              ) : isError || !data ? (
                <div className="loader flex-col gap-3 text-center text-sm text-slate-500">
                  <span>The Fleet Board could not be loaded.</span>
                  <button type="button" className="dbtn dbtn-yellow" onClick={() => refetch()}>
                    Retry
                  </button>
                </div>
              ) : view === 'detail' && selId ? (
                <TruckDetail truckId={selId} trucks={trucks} onOpen={openTruck} />
              ) : view === 'board' ? (
                <FleetBoard data={data} onOpen={(t) => openTruck(t.id)} onOpenWorkOrder={setWoPanelId} filter={filter} setFilter={setFilter} query={query} setQuery={setQuery} sort={sort} setSort={setSort} />
              ) : view === 'map' ? (
                <MapPage trucks={trucks} onOpen={openTruck} />
              ) : (
                <FleetBoard data={data} onOpen={(t) => openTruck(t.id)} onOpenWorkOrder={setWoPanelId} filter={filter} setFilter={setFilter} query={query} setQuery={setQuery} sort={sort} setSort={setSort} />
              )}
            </div>
          </div>
        </div>
      </div>

      {adding && <AddTruckModal onClose={() => setAdding(false)} />}
      {settingsOpen && <FleetSettingsModal onClose={() => setSettingsOpen(false)} />}
      {woPanelId && <WorkOrderPanel repairOrderId={woPanelId} onClose={() => setWoPanelId(null)} onChanged={refetch} />}
    </div>
  )
}

/* ---- secondary views ---- */

function MapPage({ trucks, onOpen }: { trucks: BoardTruck[]; onOpen: (id: string) => void }) {
  const handleSelect = useCallback((truck: BoardTruck) => onOpen(truck.id), [onOpen])
  return (
    <div className="mappage">
      <FleetMap trucks={trucks} onSelect={handleSelect} />
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
  ready: { label: 'Repair order ready', cls: 'stg-ready' },
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
        <div className="tcard-unit" style={{ fontSize: 20 }}>{fleetUnitLabel(t)}</div>
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
            Reschedule = plan a future PM; Create repair order = service it now. */}
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
              <ClipboardCheck size={14} /> Create repair order
            </button>
          </>
        )}
        {stage === 'ready' && (
          <>
            <button className="sbtn" onClick={() => setWoPanelId(t.pm_work_order!.repair_order_id)}>
              <Wrench size={14} /> Open RO
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
  if (!list.length) return <div className="tgrid-empty">No open repair orders.</div>
  return (
    <div className="list-rows">
      {list.map((t) => (
        <button key={t.id} className="lrow" onClick={() => onOpen(t.id)}>
          <i className="lrow-dot" style={{ background: STATUS_META[t.status].dot }} />
          <span className="lrow-unit">{fleetUnitLabel(t)}</span>
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
            <div className="person-role">{fleetUnitLabel(t)} · {`${t.make} ${t.model}`}</div>
            {t.driver_phone && <div className="person-role">{formatUSPhone(t.driver_phone)}</div>}
          </div>
          <i className="lrow-dot" style={{ background: STATUS_META[t.status].dot, marginLeft: 'auto' }} />
        </button>
      ))}
    </div>
  )
}

// These internal components remain available for a future contextual panel,
// but are no longer standalone navigation destinations.
void SchedulePage
void OrdersPage
void DriversPage

/* ---- add truck ---- */

type FleetCompanyOption = { id: string; company_name: string; fleet_enabled: boolean; is_internal_fleet: boolean }

function AuthorityPicker({ companies, value, onChange, defaultAuthorityId }: {
  companies: FleetCompanyOption[]
  value: string
  onChange: (id: string) => void
  defaultAuthorityId?: string | null
}) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const selected = companies.find((company) => company.id === value)
  const normalized = query.trim().toLowerCase()
  const showResults = open && normalized.length > 0
  const matches = companies
    .filter((company) => !normalized || company.company_name.toLowerCase().includes(normalized))
    .sort((a, b) => {
      if (a.id === defaultAuthorityId) return -1
      if (b.id === defaultAuthorityId) return 1
      return a.company_name.localeCompare(b.company_name)
    })
  const choose = (company: FleetCompanyOption) => {
    onChange(company.id)
    setQuery(company.company_name)
    setOpen(false)
  }

  return (
    <div className="authority-picker">
      <div className={'authority-combobox' + (open ? ' is-open' : '')}>
        <Search size={17} aria-hidden="true" />
        <input
          value={query || (open ? '' : selected?.company_name || '')}
          onFocus={(event) => { setQuery(selected?.company_name || ''); setOpen(true); requestAnimationFrame(() => event.currentTarget.select()) }}
          onChange={(event) => { setQuery(event.target.value); setOpen(true) }}
          onBlur={() => window.setTimeout(() => setOpen(false), 120)}
          placeholder="Search operating authority…"
          aria-label="Search operating authorities"
          aria-expanded={open}
          aria-controls="authority-options"
          role="combobox"
          autoComplete="off"
        />
        {selected?.id === defaultAuthorityId && <span className="authority-picker-default">Default</span>}
      </div>
      {showResults && (
        <div id="authority-options" className="authority-picker-menu" role="listbox" aria-label="Operating authorities">
          {matches.map((company) => {
            const isSelected = company.id === value
            const isDefault = company.id === defaultAuthorityId
            return (
              <button key={company.id} type="button" className={'authority-picker-option' + (isSelected ? ' is-selected' : '')} onMouseDown={(event) => event.preventDefault()} onClick={() => choose(company)} role="option" aria-selected={isSelected}>
                <span className="authority-picker-option-copy">
                  <span>{company.company_name}</span>
                  <small>{isDefault ? 'Default operating authority' : company.is_internal_fleet ? 'Internal shop fleet' : 'Fleet Board authority'}</small>
                </span>
                {isDefault && !isSelected && <span className="authority-picker-default">Default</span>}
                {isSelected && <Check className="authority-picker-check" size={17} aria-hidden="true" />}
              </button>
            )
          })}
          {!matches.length && <div className="authority-picker-empty">No operating authority matches that search.</div>}
        </div>
      )}
    </div>
  )
}

function AddTruckModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [mode, setMode] = useState<'new' | 'existing'>('new')
  const [customerId, setCustomerId] = useState('')
  const [vehicleSearch, setVehicleSearch] = useState('')
  const debouncedVehicleSearch = useDebouncedValue(vehicleSearch, 250)
  const [existingVehicleId, setExistingVehicleId] = useState('')
  const [vinConflict, setVinConflict] = useState<DuplicateVinConflict | null>(null)
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
  const { data: companies = [] } = useQuery<FleetCompanyOption[]>({
    queryKey: ['fleet-companies'],
    queryFn: async () => (await api.get('/fleet/companies')).data,
  })
  const { data: fleetSettings } = useQuery<{ default_fleet_authority_customer_id: string | null }>({
    queryKey: ['fleet-settings'],
    queryFn: async () => (await api.get('/fleet/settings')).data,
  })
  useEffect(() => {
    if (!customerId && fleetSettings?.default_fleet_authority_customer_id) {
      setCustomerId(fleetSettings.default_fleet_authority_customer_id)
    }
  }, [customerId, fleetSettings?.default_fleet_authority_customer_id])
  const { data: vehicleCandidates = [] } = useQuery<Array<{ id: string; make: string; model: string; year?: number | null; unit_number?: string | null; vin?: string | null }>>({
    queryKey: ['fleet-vehicle-candidates', debouncedVehicleSearch],
    queryFn: async () => (await api.get('/fleet/vehicle-candidates', { params: { q: debouncedVehicleSearch || undefined, limit: 50 } })).data,
    enabled: mode === 'existing' && !!debouncedVehicleSearch.trim(),
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
    onError: (e: any) => {
      const conflict = duplicateVinConflict(e)
      if (conflict) {
        setVinConflict(conflict)
        toast.error('This VIN is already assigned to an existing truck.')
        return
      }
      toast.error(e.response?.data?.detail || e.message || 'Failed to add truck')
    },
  })
  const inp = 'w-full'
  return (
    <SidekickPanel
      title="Add or link truck"
      subtitle="Choose how this truck joins the Fleet Board"
      icon={<Truck size={18} className="text-[var(--yellow)]" />}
      onClose={onClose}
      width="max-w-[540px]"
    >
      <div className="add-truck-modal">
        <div className="add-truck-mode" style={{ display: 'flex', gap: 8, marginBottom: 18 }}>
          <button type="button" className={`dbtn ${mode === 'new' ? 'dbtn-yellow' : 'dbtn-ghost'}`} onClick={() => { setMode('new'); setVinConflict(null) }}>New truck</button>
          <button type="button" className={`dbtn ${mode === 'existing' ? 'dbtn-yellow' : 'dbtn-ghost'}`} onClick={() => setMode('existing')}>Link existing truck</button>
        </div>
        <Field label="Operating authority *">
          <AuthorityPicker
            companies={companies}
            value={customerId}
            onChange={setCustomerId}
            defaultAuthorityId={fleetSettings?.default_fleet_authority_customer_id}
          />
        </Field>
        {mode === 'existing' ? (
          <div style={{ display: 'grid', gap: 12, marginTop: 12 }}>
            <Field label="Find truck by VIN, unit, plate, make, or model">
              <input className="w-full" value={vehicleSearch} onChange={(e) => { setVehicleSearch(e.target.value); setExistingVehicleId('') }} placeholder="Search existing trucks…" />
            </Field>
            <div className="vehicle-candidate-picker" aria-label="Existing truck">
              <span className="id-k" style={{ display: 'block', marginBottom: 5 }}>Existing truck *</span>
              {!vehicleSearch.trim() ? (
                <div className="vehicle-candidate-empty">Search to find the truck you want to link.</div>
              ) : vehicleCandidates.length ? (
                <div className="vehicle-candidate-list" role="listbox" aria-label="Existing truck results">
                  {vehicleCandidates.map((vehicle) => {
                    const selected = vehicle.id === existingVehicleId
                    return (
                      <button
                        key={vehicle.id}
                        type="button"
                        role="option"
                        aria-selected={selected}
                        className={'vehicle-candidate' + (selected ? ' is-selected' : '')}
                        onClick={() => setExistingVehicleId(vehicle.id)}
                      >
                        <span className="vehicle-candidate-copy">
                          <strong>{[vehicle.unit_number ? `Unit ${vehicle.unit_number}` : null, vehicle.year, vehicle.make, vehicle.model].filter(Boolean).join(' · ')}</strong>
                          <small>{vehicle.vin ? `VIN …${vehicle.vin.slice(-6)}` : 'VIN not recorded'}</small>
                        </span>
                        {selected && <Check size={18} aria-hidden="true" />}
                      </button>
                    )
                  })}
                </div>
              ) : (
                <div className="vehicle-candidate-empty">No trucks match that search.</div>
              )}
            </div>
          </div>
        ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 18 }}>
          <div className="vin-autofill" style={{ gridColumn: '1 / -1' }}>
            <div className="vin-autofill-label">
              <span className="id-k">VIN</span>
              <span>Paste a full VIN to fill vehicle details</span>
            </div>
            <div className="vin-autofill-control">
              <input
                value={form.vin}
                onChange={(e) => {
                  const v = e.target.value.toUpperCase()
                  setForm((f) => ({ ...f, vin: v }))
                  setVinConflict(null)
                  if (v.trim().length === 17) decodeVin(v)
                }}
                placeholder="17-character VIN"
                maxLength={17}
                aria-label="Vehicle identification number"
              />
              <button className="vin-decode" type="button" onClick={() => decodeVin(form.vin)} disabled={decoding || form.vin.trim().length !== 17}>
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
        {mode === 'new' && vinConflict?.vehicle && (
          <div style={{ marginTop: 14, border: '1px solid rgba(239, 68, 68, .55)', borderRadius: 8, padding: '10px 11px', background: 'rgba(127, 29, 29, .18)', display: 'grid', gap: 5 }}>
            <strong style={{ color: '#fecaca', fontSize: 13 }}>VIN already assigned to {duplicateVinTruckLabel(vinConflict.vehicle)}</strong>
            <span style={{ color: 'var(--muted-2)', fontSize: 12 }}>{vinConflict.vehicle.owner_lessor_name ? `Owner / lessor: ${vinConflict.vehicle.owner_lessor_name}` : 'Owner / lessor not assigned'}</span>
            {vinConflict.vehicle.operating_authority_name && <span style={{ color: 'var(--muted-2)', fontSize: 12 }}>Operating authority: {vinConflict.vehicle.operating_authority_name}</span>}
            <button type="button" className="dbtn dbtn-ghost" style={{ justifySelf: 'start', marginTop: 2 }} onClick={() => {
              setMode('existing')
              setExistingVehicleId(vinConflict.vehicle!.id)
              setVehicleSearch(vinConflict.vehicle!.vin || '')
              setVinConflict(null)
            }}>
              Link this existing truck
            </button>
          </div>
        )}
        <button className="dbtn dbtn-yellow" style={{ marginTop: 16, width: '100%', justifyContent: 'center' }}
          disabled={!customerId || (mode === 'new' ? (!form.make.trim() || !form.model.trim()) : !existingVehicleId) || create.isPending} onClick={() => create.mutate()}>
          {create.isPending ? <Spinner size="sm" /> : <Plus size={15} />} {mode === 'existing' ? 'Link truck' : 'Add truck'}
        </button>
      </div>
    </SidekickPanel>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="fleet-form-field" role="group" aria-label={label}>
      <span className="id-k" style={{ display: 'block', marginBottom: 5 }}>{label}</span>
      {children}
    </div>
  )
}

/* ---- account settings (fleet manager self-service) ---- */

function FleetSettingsModal({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()
  const { user, setUser, logout } = useAuthStore()

  const [profile, setProfile] = useState({
    first_name: user?.first_name || '',
    last_name: user?.last_name || '',
    phone: formatUSPhone(user?.phone || ''),
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
      phone: formatUSPhone(user?.phone || ''),
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
    <SidekickPanel
      title="My account"
      subtitle="Fleet manager settings"
      icon={<UserRound size={18} className="text-[var(--yellow)]" />}
      onClose={onClose}
      width="max-w-[560px]"
    >
      <div>
        {!profileEditing && (
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14 }}>
            <button className="dbtn dbtn-ghost" onClick={() => setProfileEditing(true)}>
              <Pencil size={15} /> Edit account
            </button>
          </div>
        )}

          {!profileEditing ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <Field label="First name"><div className="id-v">{profile.first_name || '—'}</div></Field>
              <Field label="Last name"><div className="id-v">{profile.last_name || '—'}</div></Field>
              <Field label="Phone"><div className="id-v">{formatUSPhone(profile.phone) || '—'}</div></Field>
              <Field label="Email"><div className="id-v">{profile.email || '—'}</div></Field>
            </div>
          ) : (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <Field label="First name"><input value={profile.first_name} onChange={setP('first_name')} /></Field>
                <Field label="Last name"><input value={profile.last_name} onChange={setP('last_name')} /></Field>
                <Field label="Phone"><input value={profile.phone} onChange={(e) => setProfile((p) => ({ ...p, phone: formatUSPhone(e.target.value) }))} placeholder="(704) 555-0123" inputMode="tel" autoComplete="tel" /></Field>
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
    </SidekickPanel>
  )
}
