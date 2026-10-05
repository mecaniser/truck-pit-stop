import type { BoardTruck } from './types'

/** Map badges show the actual unit identifier, never the company-prefixed display label. */
export function mapUnitLabel(truck: Pick<BoardTruck, 'unit_number'>) {
  return truck.unit_number?.trim() || '—'
}

/** Extract city from provider address labels; never substitute a street or guess a city. */
export function mapCity(label?: string | null) {
  if (!label) return 'Location unavailable'
  const parts = label.split(',').map(part => part.trim()).filter(Boolean)
  if (/^(USA|US|United States(?: of America)?)$/i.test(parts[parts.length - 1] || '')) parts.pop()
  const region = /^(?:[A-Z]{2}|North Carolina|South Carolina|Tennessee|Mississippi)(?:\s+\d{5}(?:-\d{4})?)?$/i
  if (parts.length > 1 && region.test(parts[parts.length - 1]!)) parts.pop()
  const city = parts[parts.length - 1]
  if (!city || /\d|\b(?:Rd|Road|St|Street|Dr|Drive|Hwy|Highway|Blvd|Boulevard|Fwy|Freeway|Ln|Lane|Ct|Court|Ave|Avenue)\b/i.test(city)) return 'City unavailable'
  return city
}
