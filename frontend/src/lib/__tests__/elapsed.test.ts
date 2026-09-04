import { describe, expect, it, vi } from 'vitest'

import { daysSince, elapsedSince, shortDuration } from '../elapsed'

const NOW = new Date('2026-09-04T12:00:00Z').getTime()

describe('elapsed', () => {
  it('returns null for input it cannot use', () => {
    expect(elapsedSince(null)).toBeNull()
    expect(elapsedSince(undefined)).toBeNull()
    expect(elapsedSince('not a date')).toBeNull()
    expect(daysSince(null)).toBeNull()
  })

  it('reports a signed elapsed time so callers decide about clock skew', () => {
    vi.setSystemTime(NOW)
    expect(elapsedSince('2026-09-04T11:00:00Z')).toBe(3_600_000)
    // A future timestamp stays negative rather than being flattened here: the
    // cockpit calls that "recently", the fleet board calls it fresh.
    expect(elapsedSince('2026-09-04T13:00:00Z')).toBeLessThan(0)
    vi.useRealTimers()
  })

  it('names one unit, the largest that fits', () => {
    expect(shortDuration(45 * 60_000)).toBe('45m')
    expect(shortDuration(6 * 3_600_000)).toBe('6h')
    expect(shortDuration(44 * 86_400_000)).toBe('44d')
    // 23h59m is still hours; the day boundary is not rounded up to.
    expect(shortDuration(23 * 3_600_000 + 59 * 60_000)).toBe('23h')
  })

  it('never renders a negative duration', () => {
    expect(shortDuration(-5_000)).toBe('0m')
    vi.setSystemTime(NOW)
    expect(daysSince('2026-09-05T12:00:00Z')).toBe(0)
    vi.useRealTimers()
  })

  it('counts whole days for thresholds', () => {
    vi.setSystemTime(NOW)
    expect(daysSince('2026-07-22T12:00:00Z')).toBe(44)
    expect(daysSince('2026-09-04T00:00:00Z')).toBe(0)
    vi.useRealTimers()
  })
})
