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

/** Navigate complete past periods; the current period ends today, never in the future. */
export function adjacentTripPeriod(preset: 'week' | 'month', start: string, direction: -1 | 1, today = new Date()): Pick<TripFilters, 'start' | 'end'> {
  const current = tripPreset(preset, today)
  const anchor = new Date(`${start}T12:00:00`)
  const first = new Date(`${tripPreset(preset, anchor).start}T12:00:00`)
  if (preset === 'week') first.setDate(first.getDate() + direction * 7)
  else first.setMonth(first.getMonth() + direction)
  const nextStart = localDate(first)
  if (nextStart >= current.start) return current
  const last = new Date(first)
  if (preset === 'week') last.setDate(last.getDate() + 6)
  else last.setMonth(last.getMonth() + 1, 0)
  return { start: nextStart, end: localDate(last) }
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
