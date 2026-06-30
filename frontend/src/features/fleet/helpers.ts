import type { TruckStatus, BoardTruck } from './types'

export const STATUS_META: Record<TruckStatus, { label: string; short: string; dot: string; cssVar: string }> = {
  active: { label: 'On the road', short: 'On road', dot: '#22c55e', cssVar: 'var(--st-active)' },
  shop: { label: 'In the shop', short: 'In shop', dot: '#38bdf8', cssVar: 'var(--st-shop)' },
  pm: { label: 'PM due soon', short: 'PM due', dot: '#f5b301', cssVar: 'var(--st-pm)' },
  parts: { label: 'Awaiting parts', short: 'Parts', dot: '#a78bfa', cssVar: 'var(--st-parts)' },
  draft: { label: 'Work order draft', short: 'WO draft', dot: '#94a3b8', cssVar: 'var(--st-shop)' },
}

export const fmt = (n?: number | null) => (n == null ? '—' : n.toLocaleString('en-US'))
export const money = (n?: number | null) => (n == null ? '—' : '$' + n.toLocaleString('en-US', { maximumFractionDigits: 0 }))

export function fmtDate(s?: string | null) {
  if (!s) return '—'
  return new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export interface PmState { label: string; cls: 'pm-ok' | 'pm-soon' | 'pm-over'; pct: number }

export function pmState(t: Pick<BoardTruck, 'pm_remaining' | 'pm_interval_miles'>): PmState {
  const r = t.pm_remaining
  const interval = t.pm_interval_miles || 25000
  if (r == null) return { label: 'PM not scheduled', cls: 'pm-over', pct: 100 }
  if (r <= 0) return { label: `OVERDUE ${fmt(Math.abs(r))} mi`, cls: 'pm-over', pct: 100 }
  if (r < 2500) return { label: `Due in ${fmt(r)} mi`, cls: 'pm-soon', pct: 100 - (r / interval) * 100 }
  return { label: `${fmt(r)} mi to PM`, cls: 'pm-ok', pct: 100 - (r / interval) * 100 }
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
