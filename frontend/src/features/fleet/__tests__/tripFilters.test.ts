import { describe, expect, it } from 'vitest'
import { adjacentTripPeriod, tripPreset } from '../tripFilters'

describe('calendar period navigation', () => {
  it('keeps Sunday in its current week and starts a fresh week on Monday', () => {
    expect(tripPreset('week', new Date(2026, 9, 4))).toEqual({ start: '2026-09-28', end: '2026-10-04' })
    expect(tripPreset('week', new Date(2026, 9, 5))).toEqual({ start: '2026-10-05', end: '2026-10-05' })
    expect(tripPreset('week', new Date(2026, 9, 7))).toEqual({ start: '2026-10-05', end: '2026-10-07' })
  })
  it('navigates complete past weeks and clamps next week to today', () => {
    const today = new Date(2026, 9, 7)
    expect(adjacentTripPeriod('week', '2026-10-05', -1, today)).toEqual({ start: '2026-09-28', end: '2026-10-04' })
    expect(adjacentTripPeriod('week', '2026-09-28', 1, today)).toEqual({ start: '2026-10-05', end: '2026-10-07' })
    expect(adjacentTripPeriod('week', '2026-10-05', 1, today)).toEqual({ start: '2026-10-05', end: '2026-10-07' })
  })
  it('handles full prior months, leap days and year rollover', () => {
    expect(adjacentTripPeriod('month', '2028-03-01', -1, new Date(2028, 2, 8))).toEqual({ start: '2028-02-01', end: '2028-02-29' })
    expect(adjacentTripPeriod('month', '2026-01-01', -1, new Date(2026, 0, 8))).toEqual({ start: '2025-12-01', end: '2025-12-31' })
    expect(adjacentTripPeriod('month', '2026-09-01', 1, new Date(2026, 9, 4))).toEqual({ start: '2026-10-01', end: '2026-10-04' })
    expect(adjacentTripPeriod('week', '2026-01-05', -1, new Date(2026, 0, 8))).toEqual({ start: '2025-12-29', end: '2026-01-04' })
  })
})
