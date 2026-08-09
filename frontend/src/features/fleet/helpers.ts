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

  // Overdue on either axis.
  if ((r != null && r <= 0) || (d != null && d < 0)) {
    const label = r != null && r <= 0 ? `OVERDUE ${fmt(Math.abs(r))} mi` : `OVERDUE ${Math.abs(d as number)} d`
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
