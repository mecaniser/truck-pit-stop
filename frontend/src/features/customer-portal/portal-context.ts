import api from '@/lib/api'
import type { Vehicle } from '@/types'

/** Reads every authorized page; incomplete/error responses must never imply an empty account. */
export async function getPortalItems<T>(url: string, params: Record<string, unknown> = {}, signal?: AbortSignal): Promise<T[]> {
  const all: T[] = []
  let skip = 0
  for (let page = 0; page < 1000; page += 1) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    const response = await api.get(url, { params: { ...params, paginated: true, skip, limit: 100 }, signal })
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    const payload = response.data
    if (Array.isArray(payload)) {
      if (page !== 0) throw new Error('List incomplete')
      return payload as T[]
    }
    if (!payload || !Array.isArray(payload.items) || typeof payload.has_more !== 'boolean') throw new Error('List unavailable')
    all.push(...payload.items)
    if (!payload.has_more) return all
    const next = Number(payload.skip) + Number(payload.limit)
    if (!payload.items.length || !Number.isFinite(next) || next <= skip) throw new Error('List incomplete')
    skip = next
  }
  throw new Error('List incomplete')
}
export function scopedPortalPath(path: string, vehicleId: string | null): string {
  const [pathname, search = ''] = path.split('?')
  const params = new URLSearchParams(search)
  if (vehicleId) params.set('vehicle_id', vehicleId)
  else params.delete('vehicle_id')
  return `${pathname}${params.size ? `?${params}` : ''}`
}
/** Display only, never a join key. Model/source labels remain unchanged in stored records. */
export function vehicleIdentity(vehicle: Vehicle): string {
  const unit = vehicle.unit_number ? `Unit #${vehicle.unit_number}` : null
  const name = [vehicle.year, vehicle.make].filter(Boolean).join(' ')
  return [unit, name || 'Vehicle', vehicle.license_plate].filter(Boolean).join(' · ')
}
export function vehicleIdentityCollisions(vehicles: Vehicle[]): Set<string> {
  const labels = new Map<string, string[]>()
  for (const vehicle of vehicles) {
    const key = vehicleIdentity(vehicle).toLowerCase()
    labels.set(key, [...(labels.get(key) || []), vehicle.id])
  }
  return new Set([...labels.values()].filter(ids => ids.length > 1).flat())
}
export function resolveVehicleScope(vehicles: Vehicle[], requested: string | null) {
  const vehicle = requested ? vehicles.find(item => item.id === requested) || null : vehicles.length === 1 ? vehicles[0] : null
  return { vehicleId: vehicle?.id || null, vehicle, invalid: Boolean(requested && !vehicle), ambiguous: Boolean(vehicle && vehicleIdentityCollisions(vehicles).has(vehicle.id)) }
}
