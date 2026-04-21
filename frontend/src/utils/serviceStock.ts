import type { Service } from '../types'

export type ServiceStockLevel = 'ok' | 'low' | 'out' | 'none'

export type ServiceStockStatus = {
  level: ServiceStockLevel
  dotClass: string | null
  tooltip: string
}

/**
 * Worst-case aggregation across a service's bundled parts:
 *   - "out"  if any part has stock_quantity = 0
 *   - "low"  if any part has 0 < stock_quantity < required qty
 *   - "ok"   if every part has enough stock
 *   - "none" if the service has no bundled parts (labor-only)
 */
export function getServiceStockStatus(service: Pick<Service, 'parts'>): ServiceStockStatus {
  const parts = service.parts || []
  if (parts.length === 0) {
    return { level: 'none', dotClass: null, tooltip: 'No parts required' }
  }

  let worst: ServiceStockLevel = 'ok'
  const problems: string[] = []
  for (const p of parts) {
    const have = p.stock_quantity ?? 0
    const need = p.quantity
    if (have === 0) {
      worst = 'out'
      problems.push(`${p.name}: out of stock (need ${need})`)
    } else if (have < need) {
      if (worst !== 'out') worst = 'low'
      problems.push(`${p.name}: ${have} in stock, need ${need}`)
    }
  }

  if (worst === 'ok') {
    return { level: 'ok', dotClass: 'bg-emerald-500', tooltip: 'All parts in stock' }
  }
  if (worst === 'low') {
    return { level: 'low', dotClass: 'bg-amber-500', tooltip: `Low stock — ${problems.join('; ')}` }
  }
  return { level: 'out', dotClass: 'bg-red-500', tooltip: `Out of stock — ${problems.join('; ')}` }
}
