import type { PartsUsage } from '../../types'

const PART_UNIT_LABELS: Record<string, string> = {
  each: 'ea',
  gallon: 'gal',
  quart: 'qt',
  liter: 'L',
}

export function buildPartHistoryEvents(parts: PartsUsage[]) {
  return parts.map((part) => ({
    id: `part-${part.id}`,
    label: part.stock_shortage_override ? 'Part added with stock override' : 'Part added to repair order',
    at: part.created_at,
    detail: `${part.inventory_name} · ${part.quantity} ${PART_UNIT_LABELS[part.unit_type] || part.unit_type}`,
  }))
}
