import { expect, it } from 'vitest'
import { layoutTruckLabels } from '../mapLabelLayout'
it.each([390, 900])('keeps 21 coincident labels distinct within a %ipx viewport', width => {
  const labels = Array.from({ length: 21 }, (_, i) => ({ id: String(i), x: width / 2, y: 300, width: 76, height: 36, priority: i === 9 ? 2 : 0 }))
  const result = layoutTruckLabels(labels, width, 650)
  expect(result).toHaveLength(21)
  expect(result[0].id).toBe('9')
  result.forEach((a, i) => {
    expect(a.dx + width / 2).toBeGreaterThanOrEqual(38)
    expect(a.dx + width / 2).toBeLessThanOrEqual(width - 38)
    expect(a.dy + 300).toBeGreaterThanOrEqual(18)
    expect(a.dy + 300).toBeLessThanOrEqual(632)
    result.slice(i + 1).forEach(b => expect(Math.abs(a.dx - b.dx) >= 82 || Math.abs(a.dy - b.dy) >= 42).toBe(true))
  })
  expect(layoutTruckLabels([...labels].reverse(), width, 650)).toEqual(result)
})
it('does not pull offscreen trucks into an edge pile', () => {
  expect(layoutTruckLabels([{ id: 'away', x: -100, y: 20, width: 70, height: 36, priority: 0 }], 390, 650)).toEqual([{ id: 'away', dx: 0, dy: -28 }])
})
