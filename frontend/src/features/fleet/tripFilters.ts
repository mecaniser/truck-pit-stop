import type { TripFilters } from './FleetTrips'

export function initialTripFilters(): TripFilters {
  const today = new Date()
  const localDate = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
  const start = new Date(today); start.setDate(start.getDate() - 6)
  return { vehicleId: '', start: localDate(start), end: localDate(today) }
}
