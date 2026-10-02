import type { TripFilters } from './FleetTrips'

export type TripPreset = 'day' | 'week' | 'month'
const localDate = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`

/** Calendar periods through today, in the same local timezone used by Trips. */
export function tripPreset(preset: TripPreset, today = new Date()): Pick<TripFilters, 'start' | 'end'> {
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  if (preset === 'week') start.setDate(start.getDate() - (start.getDay() + 6) % 7)
  if (preset === 'month') start.setDate(1)
  return { start: localDate(start), end: localDate(today) }
}

export function initialTripFilters(): TripFilters {
  return { vehicleId: '', ...tripPreset('week'), preset: 'week' }
}
