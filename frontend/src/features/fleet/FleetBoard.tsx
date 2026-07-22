import { Truck, Navigation, Wrench, Gauge, Box, ClipboardList, MapPin, User, Search, ChevronRight, Check, AlertTriangle } from 'lucide-react'
import type { BoardTruck, FleetBoard as FleetBoardData, TruckStatus } from './types'
import { STATUS_META, fleetUnitLabel, fmt, pmState, rank } from './helpers'
import { formatUSPhone } from '@/utils/phone'

type Filter = 'all' | TruckStatus
type Sort = 'attention' | 'unit' | 'pm' | 'odo'

function Kpi({ icon, value, label, short, accent, active, onClick }: {
  icon: React.ReactNode; value: number; label: string; short?: string; accent: string; active: boolean; onClick: () => void
}) {
  return (
    <button className={'kpi' + (active ? ' is-active' : '')} style={{ ['--ac' as any]: accent }} onClick={onClick} title={label}>
      <div className="kpi-ic">{icon}</div>
      <div className="kpi-tx">
        <div className="kpi-val">{value}</div>
        <div className="kpi-lbl">{short || label}</div>
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
          <span className="tcard-unit">{fleetUnitLabel(t)}</span>
          <span className="tcard-mm">{`${t.year || ''} ${t.make} ${t.model}`.trim()}</span>
        </div>
        <span className="tcard-badge"><i className={'tcard-bdot' + (t.moving ? ' is-moving' : '')} />{meta.short}</span>
      </div>
      {(t.owner_company_name || t.fleet_company_name) && (
        <div>
          <div className="tcard-type">Listing company: {t.owner_company_name || t.fleet_company_name}</div>
          <div className="tcard-type">Operating authority: {t.fleet_company_name || 'Not assigned'}</div>
        </div>
      )}
      {t.body_type && <div className="tcard-type">{t.body_type}</div>}
      <div className="tcard-row">
        <span className="tcard-row-ic"><MapPin size={14} /></span>
        <span className="tcard-row-tx">{t.location_label || 'Location unknown'}</span>
      </div>
      <div className="tcard-row">
        <span className="tcard-row-ic"><User size={14} /></span>
        <span className="tcard-row-tx">
          {t.driver_name || 'Unassigned'}
          {t.driver_phone && <span className="tcard-row-sub"> · {formatUSPhone(t.driver_phone)}</span>}
        </span>
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
          {t.open_work_order_count > 1 && <span className="tcard-wo-st">+{t.open_work_order_count - 1} more</span>}
        </div>
      ) : (
        <div className="tcard-wo tcard-wo--clear"><Check size={13} /><span>No open work orders</span></div>
      )}
      {t.warning_lights && t.warning_lights.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6, color: 'var(--red)', fontSize: 12 }}
          title={t.warning_lights.join(', ')}>
          <AlertTriangle size={13} />
          <span>{t.warning_lights.length === 1 ? t.warning_lights[0] : `${t.warning_lights.length} warning lights`}</span>
        </div>
      )}
      <span className="tcard-go"><ChevronRight size={16} /></span>
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
    // Multi-keyword, separator-agnostic: every word must match somewhere, and
    // squashed (alphanumeric-only) comparison lets "ABC1234" find "ABC-1234"
    // plates/VINs regardless of dash/space formatting.
    const squash = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '')
    const words = query.toLowerCase().trim().split(/\s+/)
    list = list.filter((t) => {
      const haystack =
        `${fleetUnitLabel(t)} ${t.unit_number || ''} ${t.make} ${t.model} ${t.driver_name || ''} ${t.vin || ''} ${t.plate || ''} ${t.body_type || ''} ${t.fleet_company_name || ''} ${t.owner_company_name || ''}`.toLowerCase()
      const squashedHaystack = squash(haystack)
      return words.every((word) => {
        if (haystack.includes(word)) return true
        const squashedWord = squash(word)
        return squashedWord !== '' && squashedHaystack.includes(squashedWord)
      })
    })
  }
  const sorters: Record<Sort, (a: BoardTruck, b: BoardTruck) => number> = {
    attention: (a, b) => rank(b) - rank(a),
    unit: (a, b) => fleetUnitLabel(a).localeCompare(fleetUnitLabel(b)),
    pm: (a, b) => (a.pm_remaining ?? 1e9) - (b.pm_remaining ?? 1e9),
    odo: (a, b) => (b.odometer ?? 0) - (a.odometer ?? 0),
  }
  list = [...list].sort(sorters[sort])

  return (
    <div>
      <div className="kpis">
        <Kpi icon={<Truck size={18} />} value={stats.total} label="Trucks in fleet" short="Fleet" accent="var(--yellow)" active={filter === 'all'} onClick={() => setFilter('all')} />
        <Kpi icon={<Navigation size={18} />} value={stats.active} label="On the road" short="OTR" accent={STATUS_META.active.dot} active={filter === 'active'} onClick={() => setFilter('active')} />
        <Kpi icon={<Wrench size={18} />} value={stats.shop} label="In the shop" short="Shop" accent={STATUS_META.shop.dot} active={filter === 'shop'} onClick={() => setFilter('shop')} />
        <Kpi icon={<Gauge size={18} />} value={stats.pm} label="PM due soon" short="PM" accent={STATUS_META.pm.dot} active={filter === 'pm'} onClick={() => setFilter('pm')} />
        <Kpi icon={<Box size={18} />} value={stats.parts} label="Awaiting parts" short="Parts" accent={STATUS_META.parts.dot} active={filter === 'parts'} onClick={() => setFilter('parts')} />
        <Kpi icon={<ClipboardList size={18} />} value={stats.open_wo} label="Open work orders" short="Open WO" accent="var(--muted)" active={false} onClick={() => setFilter('all')} />
      </div>

      <div className="board-bar">
        <div className="board-bar-l">
          <div className="fld-search">
            <Search size={16} />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search unit, VIN, plate, driver, make…" />
          </div>
          {/* Status filters live in the KPI pills above; duplicate chips removed. */}
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
