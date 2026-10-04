import { describe, it, expect, vi } from 'vitest'
import { routeMovementSummary, groupTripDays, loadTripOverview, summarizeTrips, tripDay } from '../tripAggregation'
import type { FleetTrip, FleetTripsResponse } from '../FleetTrips'
const trip = { id: '1', vehicle_id: 'a', started_at: '2026-10-02T03:00:00Z', distance_miles: 10.25, driving_seconds: 100 } as FleetTrip
const second = { ...trip, id: '2', vehicle_id: 'b', started_at: '2026-10-02T14:00:00Z', distance_miles: 20.5 }
const summary = { trip_count: 2, truck_count: 2, distance_miles: 30.75, driving_seconds: 200, coverage: 'partial' as const }
const page = { items: [trip], offset: 0, total: 2, summary } as FleetTripsResponse
describe('trip aggregation integrity', () => {
  it('groups short movement without losing mileage or hiding long-duration short trips', () => {
    const items = [trip, { ...trip, id: 'short', distance_miles: 1, driving_seconds: 900 }, { ...trip, id: 'long', distance_miles: 0.5, driving_seconds: 901 }]
    const result = routeMovementSummary(items)
    expect(result.short.map(t => t.id)).toEqual(['short'])
    expect(result.travel.map(t => t.id)).toEqual(['1', 'long'])
    expect(result.shortTotals.miles + result.travelTotals.miles).toBe(summarizeTrips(items).miles)
    expect(result.longest?.id).toBe('1')
    expect(routeMovementSummary([]).longest).toBeNull()
  })
  it('groups by local departure date, retaining overnight distance and seconds once', () => {
    expect(tripDay(trip.started_at, 'America/New_York')).toBe('2026-10-01')
    const days = groupTripDays([second, trip], 'America/New_York')
    expect(days.map(d => d.date)).toEqual(['2026-10-01', '2026-10-02'])
    expect(summarizeTrips(days.flatMap(d => d.trips))).toEqual({ count: 2, miles: 30.75, seconds: 200 })
  })
  it('handles DST and year boundaries', () => {
    expect(tripDay('2026-11-01T05:30:00Z', 'America/New_York')).toBe('2026-11-01')
    expect(tripDay('2026-11-01T06:30:00Z', 'America/New_York')).toBe('2026-11-01')
    expect(tripDay('2027-01-01T01:00:00Z', 'America/New_York')).toBe('2026-12-31')
  })
  it('reconciles complete pages', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(page).mockResolvedValueOnce({ ...page, offset: 1, items: [second] })
    expect((await loadTripOverview(fetch)).items).toHaveLength(2)
    expect(fetch).toHaveBeenLastCalledWith(1)
  })
  it.each(['duplicate', 'changed', 'empty', 'offset', 'sum'])('rejects %s pages instead of partial comparisons', async kind => {
    const next = { ...page, offset: 1, items: [second] }
    if (kind === 'duplicate') next.items = [trip]
    if (kind === 'changed') next.total = 3
    if (kind === 'empty') next.items = []
    if (kind === 'offset') next.offset = 0
    if (kind === 'sum') next.items = [{ ...second, distance_miles: 100 }]
    await expect(loadTripOverview(vi.fn().mockResolvedValueOnce(page).mockResolvedValueOnce(next))).rejects.toThrow()
  })
})

describe('relative activity ranking', () => {
  it('marks tied leaders, proportional differences and missing records honestly', async () => {
    const { activityRanking } = await import('../tripAggregation')
    const result = activityRanking([{id:'a',value:100,count:1},{id:'b',value:100,count:1},{id:'c',value:50,count:1},{id:'missing',value:0,count:0}])
    expect(result.get('a')).toEqual({rank:1,ratio:1,leader:true})
    expect(result.get('b')?.leader).toBe(true)
    expect(result.get('c')).toEqual({rank:3,ratio:.5,leader:false})
    expect(result.get('missing')).toBeNull()
    expect(activityRanking([{id:'zero',value:0,count:2}]).get('zero')).toBeNull()
  })
})

describe('diesel totals', () => {
  it('keeps measured totals separate from estimates and reports coverage', async () => {
    const { tripFuel } = await import('../tripAggregation')
    const measured = { ...trip, metrics: { fuel_used_gallons: 0 } } as FleetTrip
    const estimated = { ...second, metrics: { estimated_fuel_gallons: 8, estimate_baseline_mpg: 6, estimate_baseline_period: 'last_30_days' } } as FleetTrip
    expect(tripFuel([measured, estimated])).toEqual({ kind: 'Used', gallons: 0, count: 1, miles: measured.distance_miles })
    expect(tripFuel([trip, estimated])).toEqual({ kind: 'Est.', gallons: 8, count: 1, miles: estimated.distance_miles })
    expect(tripFuel([trip])).toBeNull()
  })
})
