import { useState } from 'react'
import { Wrench, Gauge, ClipboardList, MapPin, User, Search, ChevronDown, ChevronRight, Check, AlertTriangle, X } from 'lucide-react'
import type { BoardTruck, FleetBoard as FleetBoardData, TruckStatus } from './types'
import { STATUS_META, fleetUnitLabel, fmt, pmState, rank } from './helpers'
import { formatUSPhone } from '@/utils/phone'
import FleetActivity from './FleetActivity'

type QueueFilter = 'pm_planning' | 'open_work_orders'
type Filter = 'all' | TruckStatus | QueueFilter
type Sort = 'attention' | 'unit' | 'pm' | 'odo'

const FILTER_COPY: Partial<Record<Filter, { title: string; detail: string }>> = {
  pm_planning: { title: 'PM to plan', detail: 'Maintenance that is due soon or has not been scheduled.' },
  open_work_orders: { title: 'Open repair orders', detail: 'Trucks with active repair work.' },
  shop: { title: 'In the shop', detail: 'Units currently assigned to the service bay.' },
}

function ActionQueue({ icon, value, label, detail, tone, active, onClick }: {
  icon: React.ReactNode; value: number; label: string; detail: string; tone: string; active: boolean; onClick: () => void
}) {
  return (
    <button className={'action-queue' + (active ? ' is-active' : '')} style={{ ['--queue' as any]: tone }} onClick={onClick}>
      <span className="action-queue-icon">{icon}</span>
      <span className="action-queue-copy">
        <span className="action-queue-label">{label}</span>
        <span className="action-queue-detail">{detail}</span>
      </span>
      <span className="action-queue-count">{value}</span>
      <ChevronRight className="action-queue-go" size={18} />
    </button>
  )
}

function SectionHeading({ title, count, detail }: { title: string; count?: number; detail: string }) {
  return (
    <div className="board-section-heading">
      <div>
        <h2>{title}</h2>
        <p>{detail}</p>
      </div>
      {count != null && <span className="board-section-count">{count}</span>}
    </div>
  )
}

function TruckCard({ t, onOpen, onOpenRepairOrder }: { t: BoardTruck; onOpen: (t: BoardTruck) => void; onOpenRepairOrder: (repairOrderId: string) => void }) {
  const meta = STATUS_META[t.status]
  const pm = pmState(t)
  return (
    <article
      className="tcard"
      style={{ ['--st' as any]: meta.dot }}
      role="button"
      tabIndex={0}
      onClick={() => onOpen(t)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onOpen(t)
        }
      }}
      aria-label={`Open ${fleetUnitLabel(t)} truck details`}
    >
      <div className="tcard-top">
        <div className="tcard-id">
          <span className="tcard-unit">{fleetUnitLabel(t)}</span>
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
        <button
          type="button"
          className="tcard-wo tcard-wo--action"
          onClick={(event) => { event.stopPropagation(); onOpenRepairOrder(t.work_order!.repair_order_id) }}
          aria-label={`Open work order ${t.work_order.id} for ${fleetUnitLabel(t)}`}
        >
          <Wrench size={13} />
          <span className="tcard-wo-id">{t.work_order.id}</span>
          <span className="tcard-wo-st">{t.work_order.status}</span>
          {t.open_work_order_count > 1 && <span className="tcard-wo-st">+{t.open_work_order_count - 1} more</span>}
          <ChevronRight className="tcard-wo-go" size={15} aria-hidden="true" />
        </button>
      ) : (
        <div className="tcard-wo tcard-wo--clear"><Check size={13} /><span>No open repair orders</span></div>
      )}
      {t.warning_lights && t.warning_lights.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6, color: 'var(--red)', fontSize: 12 }}
          title={t.warning_lights.join(', ')}>
          <AlertTriangle size={13} />
          <span>{t.warning_lights.length === 1 ? t.warning_lights[0] : `${t.warning_lights.length} warning lights`}</span>
        </div>
      )}
    </article>
  )
}

export default function FleetBoard({
  data, onOpen, onOpenRepairOrder, filter, setFilter, query, setQuery, sort, setSort,
}: {
  data: FleetBoardData; onOpen: (t: BoardTruck) => void
  onOpenRepairOrder: (repairOrderId: string) => void
  filter: Filter; setFilter: (f: Filter) => void
  query: string; setQuery: (q: string) => void
  sort: Sort; setSort: (s: Sort) => void
}) {
  const { trucks, stats } = data
  // The board answers "what is happening now"; the activity tab answers "what
  // happened". Board-local state: it is a way of reading this screen, not a
  // separate destination, so it stays out of the rail and out of the URL.
  const [tab, setTab] = useState<'trucks' | 'activity'>('trucks')
  let list = trucks
  const isPmOverdue = (t: BoardTruck) => (t.pm_remaining != null && t.pm_remaining <= 0) || (t.pm_days_remaining != null && t.pm_days_remaining < 0)
  const needsPmPlanning = (t: BoardTruck) => (t.pm_remaining == null && t.pm_days_remaining == null) || pmState(t).cls === 'pm-soon'
  if (filter === 'pm_planning') {
    list = list.filter(needsPmPlanning)
  } else if (filter === 'open_work_orders') {
    list = list.filter((t) => !!t.work_order || t.open_work_order_count > 0)
  } else if (filter !== 'all') {
    list = list.filter((t) => t.status === filter)
  }
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
  // Action Now sits above the tab toggle, so it stays put across a tab switch:
  // gating it on the tab would shift the toggle out from under the pointer that
  // just clicked it. Only what is below the toggle changes.
  const showActionLane = filter === 'all' && !query.trim()
  const needsAction = list.filter((t) => {
    return isPmOverdue(t) || t.status === 'shop' || t.status === 'parts' || !!t.open_incident_count || !!t.warning_lights?.length
  })
  const actionIds = new Set(needsAction.map((t) => t.id))
  const planning = list.filter((t) => !actionIds.has(t.id) && needsPmPlanning(t))
  const planningIds = new Set(planning.map((t) => t.id))
  const remaining = list.filter((t) => !actionIds.has(t.id) && !planningIds.has(t.id))
  const pmPlanning = trucks.filter(needsPmPlanning).length
  const activeFilter = filter === 'all' ? null : FILTER_COPY[filter] || { title: STATUS_META[filter as TruckStatus]?.label || 'Filtered trucks', detail: 'Filtered fleet results.' }

  return (
    <div className="fleet-board">
      {showActionLane && (
        <section className="action-lane" aria-label="Action queues">
          <SectionHeading title="Action now" detail="Work that needs a decision or follow-through." />
          <div className="action-queues">
            <ActionQueue icon={<Wrench size={20} />} value={stats.shop} label="In the shop" detail="Units at the service bay" tone="var(--st-shop)" active={false} onClick={() => setFilter('shop')} />
            <ActionQueue icon={<ClipboardList size={20} />} value={stats.open_wo} label="Open repair orders" detail="Review active repair work" tone="var(--st-parts)" active={false} onClick={() => { setFilter('open_work_orders'); setSort('attention') }} />
            <ActionQueue icon={<Gauge size={20} />} value={pmPlanning} label="PM to plan" detail="Due soon or not scheduled" tone="var(--yellow)" active={false} onClick={() => setFilter('pm_planning')} />
          </div>
        </section>
      )}

      <div className="board-bar">
          <div className="board-bar-l">
            <div className="board-tabs" role="tablist" aria-label="Board view">
              {(['trucks', 'activity'] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  role="tab"
                  aria-selected={tab === value}
                  className={'board-tab' + (tab === value ? ' is-on' : '')}
                  onClick={() => setTab(value)}
                >
                  {value === 'trucks' ? 'Trucks' : 'Activity'}
                </button>
              ))}
            </div>
            {tab === 'trucks' && (
            <>
            <div className="fld-search">
              <Search size={16} />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search unit, VIN, plate, driver, make…" />
            </div>
            {activeFilter && (
              <button className="active-filter" onClick={() => setFilter('all')} aria-label={`Clear ${activeFilter.title} filter`}>
                <span className="active-filter-label">{activeFilter.title}</span>
                <span className="active-filter-clear" aria-hidden="true"><X size={13} strokeWidth={2.5} /></span>
              </button>
            )}
            </>
            )}
        </div>
        {tab === 'trucks' && (
        <div className="board-bar-r">
          <span className="board-sort-lbl">Sort</span>
          <div className="board-sort-select">
            <select className="fld-sel" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
              <option value="attention">Needs attention</option>
              <option value="unit">Unit number</option>
              <option value="pm">PM soonest</option>
              <option value="odo">Highest mileage</option>
            </select>
            <ChevronDown size={16} aria-hidden="true" />
          </div>
        </div>
        )}
      </div>

      {tab === 'activity' && <FleetActivity />}

      {tab === 'trucks' && showActionLane && needsAction.length > 0 && (
        <section className="board-section">
          <SectionHeading title="Needs attention" count={needsAction.length} detail="Prioritized by service and PM urgency." />
          <div className="tgrid tgrid-attention">{needsAction.map((t) => <TruckCard key={t.id} t={t} onOpen={onOpen} onOpenRepairOrder={onOpenRepairOrder} />)}</div>
        </section>
      )}
      {tab === 'trucks' && showActionLane && planning.length > 0 && (
        <section className="board-section">
          <SectionHeading title="Maintenance to plan" count={planning.length} detail="Schedule these before they become service interruptions." />
          <div className="tgrid">{planning.map((t) => <TruckCard key={t.id} t={t} onOpen={onOpen} onOpenRepairOrder={onOpenRepairOrder} />)}</div>
        </section>
      )}
      {tab === 'trucks' && (
      <section className="board-section">
        <SectionHeading title={showActionLane ? 'Fleet overview' : activeFilter?.title || 'Matching trucks'} count={showActionLane ? remaining.length : list.length} detail={showActionLane ? 'Units without an immediate action queue.' : activeFilter?.detail || 'Search and filter results.'} />
        <div className="tgrid">
          {(showActionLane ? remaining : list).map((t) => <TruckCard key={t.id} t={t} onOpen={onOpen} onOpenRepairOrder={onOpenRepairOrder} />)}
          {list.length === 0 && <div className="tgrid-empty">No trucks match.</div>}
        </div>
      </section>
      )}
    </div>
  )
}
