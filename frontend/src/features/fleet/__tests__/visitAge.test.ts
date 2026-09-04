/**
 * A visit's age is what says an order was never closed.
 *
 * The board and the shop's cockpit read one table, so an order left open keeps
 * a truck reading as "in the shop" on both. Nothing else on the board says how
 * long that has been true, which is why these thresholds are pinned.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { VISIT_STALE_AFTER_DAYS, visitAge, visitIsStale } from '../helpers'

const NOW = new Date('2026-09-04T12:00:00Z').getTime()
const daysAgo = (n: number) => new Date(NOW - n * 86_400_000).toISOString()

afterEach(() => vi.useRealTimers())

describe('visit age', () => {
  it('has no age when the projection has not carried one yet', () => {
    // Null until 133_fleet_board_opened_at runs; the card shows nothing rather
    // than guessing an age from a field it does not have.
    expect(visitAge(null)).toBeNull()
    expect(visitAge(undefined)).toBeNull()
    expect(visitIsStale(null)).toBe(false)
  })

  it('reads the age in the largest unit that fits', () => {
    vi.setSystemTime(NOW)
    expect(visitAge(daysAgo(44))!.label).toBe('44d')
    expect(visitAge(new Date(NOW - 3 * 3_600_000).toISOString())!.label).toBe('3h')
  })

  it('calls a visit stale only once it has outlived a plausible stop', () => {
    vi.setSystemTime(NOW)
    // A truck can sit over a weekend waiting on a part, so the line is 3 days.
    expect(visitIsStale(daysAgo(VISIT_STALE_AFTER_DAYS - 1))).toBe(false)
    expect(visitIsStale(daysAgo(VISIT_STALE_AFTER_DAYS))).toBe(true)
    expect(visitIsStale(daysAgo(44))).toBe(true)
  })

  it('treats a today visit as fresh', () => {
    vi.setSystemTime(NOW)
    expect(visitAge(daysAgo(0))!.days).toBe(0)
    expect(visitIsStale(daysAgo(0))).toBe(false)
  })
})
