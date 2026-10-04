import type { TripFilters } from './FleetTrips'

export type TripPreset = 'day' | 'week' | 'month' | 'year'
const localDate = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`

/** Calendar periods through today, in the same local timezone used by Trips. */
export function tripPreset(preset: TripPreset, today = new Date()): Pick<TripFilters, 'start' | 'end'> {
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  if (preset === 'week') start.setDate(start.getDate() - (start.getDay() + 6) % 7)
  if (preset === 'month') start.setDate(1)
  if (preset === 'year') start.setMonth(0, 1)
  return { start: localDate(start), end: localDate(today) }
}

export function initialTripFilters(): TripFilters {
  return { vehicleId: '', ...tripPreset('week'), preset: 'week' }
}

/** Disjoint Monday–Sunday windows, clipped to the selected inclusive dates. */
export function tripWeeks(start: string, end: string): { start: string; end: string }[] {
  const result: { start: string; end: string }[] = []
  const cursor = new Date(`${start}T12:00:00`)
  const last = new Date(`${end}T12:00:00`)
  while (cursor <= last) {
    const weekEnd = new Date(cursor)
    weekEnd.setDate(weekEnd.getDate() + (7 - weekEnd.getDay()) % 7)
    if (weekEnd > last) weekEnd.setTime(last.getTime())
    result.push({ start: localDate(cursor), end: localDate(weekEnd) })
    cursor.setTime(weekEnd.getTime())
    cursor.setDate(cursor.getDate() + 1)
  }
  return result
}
