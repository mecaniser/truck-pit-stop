import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Vehicle } from '@/types'
import { getPortalItems, resolveVehicleScope, scopedPortalPath, vehicleIdentity, vehicleIdentityCollisions } from '../portal-context'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get } }))

function vehicle(id: string, overrides: Partial<Vehicle> = {}): Vehicle {
  return {
    id, tenant_id: 'tenant-a', customer_id: 'customer-a', vin: 'VIN-' + id,
    unit_number: '12', make: 'Freightliner', model: 'Cascadia', year: 2020,
    license_plate: 'ABC123', color: null, mileage: null, notes: null,
    created_at: '2026-01-01', updated_at: '2026-01-01', ...overrides,
  }
}

describe('authorized portal pagination', () => {
  beforeEach(() => get.mockReset())

  it('loads every page and preserves the vehicle scope on subsequent requests', async () => {
    const controller = new AbortController()
    get.mockResolvedValueOnce({ data: { items: [{ id: 'first' }], has_more: true, skip: 0, limit: 100 } })
    get.mockResolvedValueOnce({ data: { items: [{ id: 'later' }], has_more: false, skip: 100, limit: 100 } })
    await expect(getPortalItems('/invoices', { vehicle_id: 'vehicle-a' }, controller.signal)).resolves.toEqual([{ id: 'first' }, { id: 'later' }])
    expect(get).toHaveBeenNthCalledWith(1, '/invoices', { params: { vehicle_id: 'vehicle-a', paginated: true, skip: 0, limit: 100 }, signal: controller.signal })
    expect(get).toHaveBeenNthCalledWith(2, '/invoices', { params: { vehicle_id: 'vehicle-a', paginated: true, skip: 100, limit: 100 }, signal: controller.signal })
  })

  it('makes no request when the query was already cancelled', async () => {
    const controller = new AbortController()
    controller.abort()
    await expect(getPortalItems('/invoices', {}, controller.signal)).rejects.toMatchObject({ name: 'AbortError' })
    expect(get).not.toHaveBeenCalled()
  })

  it.each([true, false])('discards a late response after cancellation and starts no next page (has_more=%s)', async (hasMore) => {
    const controller = new AbortController()
    let releasePage!: (response: unknown) => void
    get.mockImplementationOnce(() => new Promise(resolve => { releasePage = resolve }))
    const pending = getPortalItems('/invoices', {}, controller.signal)
    expect(get).toHaveBeenCalledTimes(1)
    controller.abort()
    releasePage({ data: { items: [{ id: 'previous-session' }], has_more: hasMore, skip: 0, limit: 100 } })
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
    expect(get).toHaveBeenCalledTimes(1)
  })

  it.each([
    { items: [], has_more: true, skip: 0, limit: 100 },
    { items: [{ id: 'a' }], has_more: true, skip: 0, limit: 0 },
    { items: [{ id: 'a' }], has_more: true, skip: 'invalid', limit: 100 },
    { items: [] },
    null,
  ])('rejects malformed or stalled pagination instead of reporting an empty account: %j', async (data) => {
    get.mockResolvedValueOnce({ data })
    await expect(getPortalItems('/invoices')).rejects.toThrow(/List (incomplete|unavailable)/)
    expect(get).toHaveBeenCalledTimes(1)
  })

  it('rejects a later read failure instead of presenting partial records as complete', async () => {
    get.mockResolvedValueOnce({ data: { items: [{ id: 'first' }], has_more: true, skip: 0, limit: 100 } })
    get.mockRejectedValueOnce(new Error('Unavailable'))
    await expect(getPortalItems('/invoices')).rejects.toThrow('Unavailable')
  })

  it('supports existing non-paginated authorized lists', async () => {
    get.mockResolvedValueOnce({ data: [{ id: 'legacy' }] })
    await expect(getPortalItems('/vehicles')).resolves.toEqual([{ id: 'legacy' }])
  })
})

describe('portal vehicle scope', () => {
  it('selects a sole authorized vehicle automatically, retaining its stable ID', () => {
    const only = vehicle('a')
    expect(resolveVehicleScope([only], null)).toEqual({ vehicleId: 'a', vehicle: only, invalid: false, ambiguous: false })
  })

  it('requires a selection for multiple vehicles and never falls back from an unknown ID', () => {
    const vehicles = [vehicle('a'), vehicle('b')]
    expect(resolveVehicleScope(vehicles, null)).toEqual({ vehicleId: null, vehicle: null, invalid: false, ambiguous: false })
    expect(resolveVehicleScope(vehicles, 'foreign-vehicle')).toEqual({ vehicleId: null, vehicle: null, invalid: true, ambiguous: false })
    expect(resolveVehicleScope([vehicles[0]], 'foreign-vehicle').vehicleId).toBeNull()
  })

  it('flags colliding display identities without merging records or using model labels as IDs', () => {
    const first = vehicle('a', { model: 'source model A' })
    const second = vehicle('b', { model: 'source model B', vin: 'DIFFERENT-VIN' })
    const third = vehicle('c', { unit_number: '13' })
    expect(vehicleIdentity(first)).toBe('Unit #12 · 2020 Freightliner · ABC123')
    expect(vehicleIdentityCollisions([first, second, third])).toEqual(new Set(['a', 'b']))
    expect(resolveVehicleScope([first, second, third], 'b')).toEqual({ vehicleId: 'b', vehicle: second, invalid: false, ambiguous: true })
    expect(first.model).toBe('source model A')
    expect(second.model).toBe('source model B')
  })

  it('preserves existing task query parameters when changing or clearing vehicle scope', () => {
    expect(scopedPortalPath('/portal/repairs?view=active&vehicle_id=old', 'new')).toBe('/portal/repairs?view=active&vehicle_id=new')
    expect(scopedPortalPath('/portal/repairs?view=active&vehicle_id=old', null)).toBe('/portal/repairs?view=active')
    expect(scopedPortalPath('/portal', null)).toBe('/portal')
  })
})
