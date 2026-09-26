import { elapsedSince, shortDuration } from '@/lib/elapsed'
import type { TruckStatus, BoardTruck } from './types'

export const STATUS_META: Record<TruckStatus, { label: string; short: string; dot: string; cssVar: string }> = {
  active: { label: 'On the road', short: 'On road', dot: '#22c55e', cssVar: 'var(--st-active)' },
  shop: { label: 'In the shop', short: 'In shop', dot: '#38bdf8', cssVar: 'var(--st-shop)' },
  pm: { label: 'PM due soon', short: 'PM due', dot: '#f5b301', cssVar: 'var(--st-pm)' },
  parts: { label: 'Awaiting parts', short: 'Parts', dot: '#a78bfa', cssVar: 'var(--st-parts)' },
  draft: { label: 'Repair order draft', short: 'RO draft', dot: '#94a3b8', cssVar: 'var(--st-shop)' },
  yard: { label: 'In the yard', short: 'Yard', dot: '#64748b', cssVar: 'var(--st-shop)' },
  available: { label: 'Available', short: 'Available', dot: '#14b8a6', cssVar: 'var(--st-active)' },
  out_of_service: { label: 'Out of service', short: 'Out', dot: '#ef4444', cssVar: 'var(--st-parts)' },
}

export const fmt = (n?: number | null) => (n == null ? '—' : n.toLocaleString('en-US'))
export const money = (n?: number | null) =>
  (n == null ? '—' : '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))

/** Fleet-facing label: listing/owning company plus the truck's raw unit number. */
export function fleetUnitLabel(t: Pick<BoardTruck, 'display_unit_number' | 'unit_number' | 'make'>): string {
  return t.display_unit_number || t.unit_number || t.make || 'Truck'
}

/**
 * The two halves of a truck's identity, for a card that shows the company as a
 * heading and the unit number as the large glanceable mark.
 *
 * `display_unit_number` arrives pre-joined ("77 CARGO LLC 01"), so the parts
 * are taken from the source fields rather than split back out of it. The
 * backend omits the company prefix when the unit already begins with it; this
 * mirrors that rule with the same normalize comparison, so the card never
 * prints the company twice.
 */
export function fleetIdentity(
  t: Pick<BoardTruck, 'display_unit_number' | 'unit_number' | 'make' | 'fleet_company_name' | 'owner_company_name'>,
): { company: string | null; unit: string } {
  const unit = (t.unit_number || '').trim()
  // Owner is the listing/leasing company; the operating authority is the
  // fallback for legacy fleet rows with no owner relationship.
  const company = (t.owner_company_name || t.fleet_company_name || '').trim()
  const normalize = (value: string) => value.toLowerCase().replace(/[^a-z0-9]/g, '')

  if (!unit) return { company: company || null, unit: fleetUnitLabel(t) }
  if (!company) return { company: null, unit }
  // Already self-identifying: showing the company again would duplicate it.
  if (normalize(unit).startsWith(normalize(company))) return { company: null, unit }
  return { company, unit }
}

export function fmtDate(s?: string | null) {
  if (!s) return '—'
  return new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export interface PmState { label: string; cls: 'pm-ok' | 'pm-soon' | 'pm-over'; pct: number }

export function pmState(t: Pick<BoardTruck, 'pm_remaining' | 'pm_interval_miles' | 'pm_days_remaining'>): PmState {
  const r = t.pm_remaining          // miles remaining (may be negative)
  const d = t.pm_days_remaining     // days remaining (may be negative)
  const interval = t.pm_interval_miles || 25000
  const milePct = r != null ? 100 - (r / interval) * 100 : 100

  if (r == null && d == null) return { label: 'PM not scheduled', cls: 'pm-over', pct: 100 }

  // Overdue on either axis. Due *today* counts here too: the PM is owed now,
  // so it belongs with the work that needs a decision, not with planning. It
  // reads "Due today" rather than "OVERDUE 0 d", which is both wrong and
  // alarming.
  if ((r != null && r <= 0) || (d != null && d <= 0)) {
    if (r != null && r <= 0) return { label: `OVERDUE ${fmt(Math.abs(r))} mi`, cls: 'pm-over', pct: 100 }
    const days = d as number
    const label = days === 0 ? 'Due today' : `OVERDUE ${Math.abs(days)} d`
    return { label, cls: 'pm-over', pct: 100 }
  }
  // Due soon on either axis.
  const mileSoon = r != null && r < 2500
  const dateSoon = d != null && d <= 14
  if (mileSoon || dateSoon) {
    const label = mileSoon ? `Due in ${fmt(r as number)} mi` : `Due in ${d} d`
    return { label, cls: 'pm-soon', pct: milePct }
  }
  const label = r != null ? `${fmt(r)} mi to PM` : `${d} d to PM`
  return { label, cls: 'pm-ok', pct: r != null ? milePct : 50 }
}

/**
 * How soon this truck needs its PM, as one comparable number: lower is more
 * urgent. Sorting on miles alone sank a truck due *today* below trucks with
 * weeks of road left, because its remaining mileage was large.
 *
 * Miles and days are different units, so they are converted to a common one -
 * days - using the same average the scheduler projects with. Whichever axis is
 * closer wins, matching `pmState`, which shows whichever fires first.
 * Unscheduled trucks sort last: they need planning, but a truck already
 * overdue needs it more.
 */
export const PM_AVG_MILES_PER_DAY = 600

export function pmUrgency(
  t: Pick<BoardTruck, 'pm_remaining' | 'pm_days_remaining'>,
): number {
  const byMiles = t.pm_remaining != null ? t.pm_remaining / PM_AVG_MILES_PER_DAY : null
  const byDays = t.pm_days_remaining != null ? t.pm_days_remaining : null
  if (byMiles == null && byDays == null) return Number.MAX_SAFE_INTEGER
  if (byMiles == null) return byDays as number
  if (byDays == null) return byMiles
  return Math.min(byMiles, byDays)
}

export function rank(t: BoardTruck): number {
  if (t.status === 'shop') return t.work_order && t.work_order.status === 'Awaiting parts' ? 4 : 5
  if (t.status === 'parts') return 4.5
  if (t.status === 'pm') return (t.pm_remaining ?? 0) <= 0 ? 6 : 3
  return 1
}

export function initials(name?: string | null): string {
  if (!name) return '—'
  return name.split(/\s+/).map((p) => p[0]).join('').slice(0, 2).toUpperCase()
}

/**
 * A visit is a stop at the shop, so an order still open after this long has
 * almost certainly finished without anyone closing it. The board carries it
 * either way — and so does the shop's cockpit, since both read one table.
 *
 * Three days rather than one: a truck can legitimately sit over a weekend
 * waiting on a part.
 */
export const VISIT_STALE_AFTER_DAYS = 3

/** How long this visit has been open, or null when the age is unknown. */
export function visitAge(openedAt?: string | null): { label: string; days: number } | null {
  const elapsed = elapsedSince(openedAt)
  if (elapsed == null) return null
  return { label: shortDuration(elapsed), days: Math.max(Math.floor(elapsed / 86_400_000), 0) }
}

export function visitIsStale(openedAt?: string | null): boolean {
  const age = visitAge(openedAt)
  return age != null && age.days >= VISIT_STALE_AFTER_DAYS
}
