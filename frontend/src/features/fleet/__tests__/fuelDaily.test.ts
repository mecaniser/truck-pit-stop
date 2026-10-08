import { describe, it, expect, vi } from 'vitest'
import { loadFuelRange, summarizeFuel, medianFuel, type FuelDaily, type FuelDailyResponse } from '../fuelDaily'
const row: FuelDaily = { vehicle_id: 'truck-a', report_date: '2026-08-15', driving_fuel_gallons: 10, idling_fuel_gallons: 2, reported_total_fuel_gallons: 12.1, source_distance_miles: 60, source_driving_seconds: 3600, source_idling_seconds: 600, timezone_status: 'unverified', source_timezone: null }
const page = (items: FuelDaily[], offset = 0, total = items.length): FuelDailyResponse => ({ items, total, offset, limit: 100, start_date: '2026-08-15', end_date: '2026-09-14', date_basis: 'source_report_date', coverage: 'partial' })
describe('Motive fuel history', () => {
  it('takes medians of truck totals, retains zero and excludes missing components and outside trucks', () => {
    const records = [row, { ...row, report_date: '2026-08-16', driving_fuel_gallons: 30 }, { ...row, vehicle_id: 'truck-b', driving_fuel_gallons: 10, idling_fuel_gallons: null }, { ...row, vehicle_id: 'truck-c', driving_fuel_gallons: 0, idling_fuel_gallons: 0 }, { ...row, vehicle_id: 'outside', driving_fuel_gallons: 999 }]
    expect(medianFuel(records, ['truck-a', 'truck-b', 'truck-c', 'missing', 'truck-a'])).toEqual({ driving: { value: 10, count: 3 }, idling: { value: 2, count: 2 } })
    expect(medianFuel([], ['missing'])).toEqual({ driving: { value: null, count: 0 }, idling: { value: null, count: 0 } })
  })
  it('uses non-overlapping 31 day windows and fetches all pages', async () => {
    const fetch = vi.fn(async (start: string, _end: string, offset: number) => start === '2026-08-15' ? page([{ ...row, vehicle_id: offset ? 'truck-b' : 'truck-a' }], offset, 2) : page([{ ...row, report_date: start }]))
    expect(await loadFuelRange('2026-08-15', '2026-10-04', fetch)).toHaveLength(3)
    expect(fetch.mock.calls).toEqual([['2026-08-15', '2026-09-14', 0], ['2026-08-15', '2026-09-14', 1], ['2026-09-15', '2026-10-04', 0]])
  })
  it('preserves provider total and null versus zero without creating missing days', () => {
    expect(summarizeFuel([])).toBeNull()
    expect(summarizeFuel([row], 'truck-b')).toBeNull()
    expect(summarizeFuel([row], undefined, '2026-08-16')).toBeNull()
    const summary = summarizeFuel([row, { ...row, report_date: '2026-08-16', driving_fuel_gallons: null, idling_fuel_gallons: 0, reported_total_fuel_gallons: null }])!
    expect(summary).toMatchObject({ driving: 10, idling: 2, total: 12.1, days: 2, drivingDays: 1, idlingDays: 2, timezone: null })
    expect(summarizeFuel([{ ...row, driving_fuel_gallons: null }])?.driving).toBeNull()
  })
  it('rejects duplicate records, broken pages and out-of-window rows', async () => {
    await expect(loadFuelRange('2026-08-15', '2026-08-16', async () => page([row, row]))).rejects.toThrow('Invalid fuel report row')
    await expect(loadFuelRange('2026-08-15', '2026-08-16', async () => page([], 0, 1))).rejects.toThrow('Incomplete fuel report')
    await expect(loadFuelRange('2026-08-16', '2026-08-17', async () => page([row]))).rejects.toThrow('Invalid fuel report row')
  })
})
