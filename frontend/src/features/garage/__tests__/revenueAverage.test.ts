import { describe, expect, it } from 'vitest'
import { revenueAverage } from '../revenueAverage'

describe('displayed revenue average', () => {
  it('uses the arithmetic mean rather than the middle value', () => {
    expect(revenueAverage([40000, 20000, 30000])).toBe(30000)
    expect(revenueAverage([1000, 1000, 10000])).toBe(4000)
  })

  it('includes zero-revenue periods', () => {
    expect(revenueAverage([40000, 0, 20000, 10000])).toBe(17500)
  })

  it('omits the reference for an empty range', () => {
    expect(revenueAverage([])).toBeNull()
  })
})
