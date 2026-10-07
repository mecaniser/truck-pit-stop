import { describe, expect, it } from 'vitest'
import { distanceColor } from '../distanceColor'
describe('relative home distance color', () => {
  it('runs green through amber to red by actual distance', () => {
    expect(distanceColor(10, 10, 90)).toBe('rgb(74, 222, 128)')
    expect(distanceColor(50, 10, 90)).toBe('rgb(251, 191, 36)')
    expect(distanceColor(90, 10, 90)).toBe('rgb(248, 113, 113)')
    expect(distanceColor(10.1, 10, 90)).toBe('rgb(74, 222, 128)')
  })
  it('keeps equal or single distances green and invalid distances neutral', () => {
    expect(distanceColor(0, 0, 0)).toBe('rgb(74, 222, 128)')
    expect(distanceColor(15, 15, 15)).toBe('rgb(74, 222, 128)')
    expect(distanceColor(NaN, 0, 90)).toBeUndefined()
    expect(distanceColor(-1, 0, 90)).toBeUndefined()
    expect(distanceColor(10, Infinity, -Infinity)).toBeUndefined()
  })
})
