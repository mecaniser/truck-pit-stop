import { describe, expect, it } from 'vitest'
import { weeklyRevenueMedian } from '../weeklyRevenueMedian'

describe('weekly revenue median', () => {
  it('uses the middle displayed week for odd counts', () => {
    expect(weeklyRevenueMedian([40000, 20000, 30000])).toBe(30000)
  })

  it('averages the middle weeks and includes zero-revenue weeks', () => {
    expect(weeklyRevenueMedian([40000, 0, 20000, 10000])).toBe(15000)
  })

  it('omits the reference for an empty range', () => {
    expect(weeklyRevenueMedian([])).toBeNull()
  })
})
