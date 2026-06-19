import { Truck, Navigation, Wrench, Gauge, Box, ClipboardList, MapPin, User, Search, ChevronRight, Check } from 'lucide-react'
import type { BoardTruck, FleetBoard as FleetBoardData, TruckStatus } from './types'
import { STATUS_META, fmt, pmState, rank } from './helpers'

type Filter = 'all' | TruckStatus
type Sort = 'attention' | 'unit' | 'pm' | 'odo'

function Kpi({ icon, value, label, accent, active, onClick }: {
  icon: React.ReactNode; value: number; label: string; accent: string; active: boolean; onClick: () => void
}) {
  return (
    <button className={'kpi' + (active ? ' is-active' : '')} style={{ ['--ac' as any]: accent }} onClick={onClick}>
      <div className="kpi-ic">{icon}</div>
      <div>
        <div className="kpi-val">{value}</div>
        <div className="kpi-lbl">{label}</div>
      </div>
    </button>
  )
}

function TruckCard({ t, onOpen }: { t: BoardTruck; onOpen: (t: BoardTruck) => void }) {
  const meta = STATUS_META[t.status]
  const pm = pmState(t)
  return (
    <button className="tcard" style={{ ['--st' as any]: meta.dot }} onClick={() => onOpen(t)}>
      <div className="tcard-top">
        <div className="tcard-id">
          <span className="tcard-unit">{t.unit_number || `${t.make}`}</span>
          <span className="tcard-mm">{`${t.year || ''} ${t.make} ${t.model}`.trim()}</span>
        </div>
        <span className="tcard-badge"><i className={'tcard-bdot' + (t.moving ? ' is-moving' : '')} />{meta.short}</span>
      </div>
      {t.body_type && <div className="tcard-type">{t.body_type}</div>}
      <div className="tcard-row">
        <span className="tcard-row-ic"><MapPin size={14} /></span>
        <span className="tcard-row-tx">{t.location_label || 'Location unknown'}</span>
      </div>
      <div className="tcard-row">
        <span className="tcard-row-ic"><User size={14} /></span>
        <span className="tcard-row-tx">{t.driver_name || 'Unassigned'}</span>
        {!!t.speed_mph && <span className="tcard-mph">{t.speed_mph} mph {t.heading || ''}</span>}
      </div>
      <div className="tcard-odo">
        <span>ODO</span><b>{fmt(t.odometer)}</b><span>mi</span>
      </div>
      <div className="tcard-pm">
        <div className="tcard-pm-track">
          <div className={'tcard-pm-fill ' + pm.cls} style={{ width: Math.max(4, Math.min(100, pm.pct)) + '%' }} />
        </div>
        <div className={'tcard-pm-lbl ' + pm.cls}>{pm.label}</div>
      </div>
      {t.work_order ? (
        <div className="tcard-wo">
          <Wrench size={13} />
          <span className="tcard-wo-id">{t.work_order.id}</span>
          <span className="tcard-wo-st">{t.work_order.status}</span>
        </div>
      ) : (
        <div className="tcard-wo tcard-wo--clear"><Check size={13} /><span>No open work orders</span></div>
      )}
      <span className="tcard-go"><ChevronRight size={16} /></span>
    </button>
  )
}

function chip(key: Filter, label: string, filter: Filter, setFilter: (f: Filter) => void, dot?: string) {
  return (
    <button key={key} className={'chip' + (filter === key ? ' is-on' : '')} onClick={() => setFilter(key)}>
      {dot && <i className="chip-dot" style={{ background: dot }} />}{label}
    </button>
  )
}

export default function FleetBoard({
  data, onOpen, filter, setFilter, query, setQuery, sort, setSort,
}: {
  data: FleetBoardData; onOpen: (t: BoardTruck) => void
  filter: Filter; setFilter: (f: Filter) => void
  query: string; setQuery: (q: string) => void
  sort: Sort; setSort: (s: Sort) => void
}) {
  const { trucks, stats } = data
  let list = trucks
  if (filter !== 'all') list = list.filter((t) => t.status === filter)
  if (query.trim()) {
    const q = query.toLowerCase()
    list = list.filter((t) =>
      `${t.unit_number || ''} ${t.make} ${t.model} ${t.driver_name || ''} ${t.vin || ''} ${t.plate || ''} ${t.body_type || ''}`
        .toLowerCase().includes(q))
  }
  const sorters: Record<Sort, (a: BoardTruck, b: BoardTruck) => number> = {
    attention: (a, b) => rank(b) - rank(a),
    unit: (a, b) => (a.unit_number || '').localeCompare(b.unit_number || ''),
    pm: (a, b) => (a.pm_remaining ?? 1e9) - (b.pm_remaining ?? 1e9),
    odo: (a, b) => (b.odometer ?? 0) - (a.odometer ?? 0),
  }
  list = [...list].sort(sorters[sort])

  return (
    <div>
      <div className="kpis">
        <Kpi icon={<Truck size={19} />} value={stats.total} label="Trucks in fleet" accent="var(--yellow)" active={filter === 'all'} onClick={() => setFilter('all')} />
        <Kpi icon={<Navigation size={19} />} value={stats.active} label="On the road" accent={STATUS_META.active.dot} active={filter === 'active'} onClick={() => setFilter('active')} />
        <Kpi icon={<Wrench size={19} />} value={stats.shop} label="In the shop" accent={STATUS_META.shop.dot} active={filter === 'shop'} onClick={() => setFilter('shop')} />
        <Kpi icon={<Gauge size={19} />} value={stats.pm} label="PM due soon" accent={STATUS_META.pm.dot} active={filter === 'pm'} onClick={() => setFilter('pm')} />
        <Kpi icon={<Box size={19} />} value={stats.parts} label="Awaiting parts" accent={STATUS_META.parts.dot} active={filter === 'parts'} onClick={() => setFilter('parts')} />
        <Kpi icon={<ClipboardList size={19} />} value={stats.open_wo} label="Open work orders" accent="var(--muted)" active={false} onClick={() => setFilter('all')} />
      </div>

      <div className="board-bar">
        <div className="board-bar-l">
          <div className="fld-search">
            <Search size={16} />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search unit, VIN, plate, driver, make…" />
          </div>
          <div className="chips">
            {chip('all', 'All', filter, setFilter)}
            {chip('active', STATUS_META.active.label, filter, setFilter, STATUS_META.active.dot)}
            {chip('shop', STATUS_META.shop.label, filter, setFilter, STATUS_META.shop.dot)}
            {chip('pm', STATUS_META.pm.label, filter, setFilter, STATUS_META.pm.dot)}
            {chip('parts', STATUS_META.parts.label, filter, setFilter, STATUS_META.parts.dot)}
          </div>
        </div>
        <div className="board-bar-r">
          <span className="board-sort-lbl">Sort</span>
          <select className="fld-sel" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
            <option value="attention">Needs attention</option>
            <option value="unit">Unit number</option>
            <option value="pm">PM soonest</option>
            <option value="odo">Highest mileage</option>
          </select>
        </div>
      </div>

      <div className="tgrid">
        {list.map((t) => <TruckCard key={t.id} t={t} onOpen={onOpen} />)}
        {list.length === 0 && <div className="tgrid-empty">No trucks match.</div>}
      </div>
    </div>
  )
}
