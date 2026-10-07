import { expect, it } from 'vitest'
import { crossesRect, routeLeader } from '../mapLeaderRouting'
import { layoutTruckLabels } from '../mapLabelLayout'

it('ends at the card edge rather than its center', () => {
  const target = { x: 100, y: 100, width: 80, height: 28 }
  const points = routeLeader({ x: 100, y: 150 }, target, [])
  expect(points[0]).toEqual({ x: 100, y: 150 })
  expect(points.at(-1)).toEqual({ x: 100, y: 114 })
  for (let i = 1; i < points.length; i++) expect(crossesRect(points[i - 1], points[i], target)).toBe(false)
})
it('bends around a card placed between a dot and its label', () => {
  const obstacle = { x: 100, y: 100, width: 80, height: 28 }
  const points = routeLeader({ x: 100, y: 160 }, { x: 100, y: 40, width: 80, height: 28 }, [obstacle])
  expect(points.length).toBeGreaterThan(3)
  for (let i = 1; i < points.length; i++) expect(crossesRect(points[i - 1], points[i], obstacle)).toBe(false)
})
it.each([390, 900])('routes 21 coincident units around all final cards at %ipx', width => {
  const labels = Array.from({ length: 21 }, (_, i) => ({ id: String(i), x: width / 2, y: 300, width: 76, height: 28, priority: 0 }))
  const placements = layoutTruckLabels(labels, width, 650)
  const cards = placements.map(p => ({ ...labels.find(l => l.id === p.id)!, x: width / 2 + p.dx, y: 300 + p.dy }))
  cards.forEach(card => {
    const points = routeLeader({ x: width / 2, y: 300 }, card, cards.filter(other => other.id !== card.id))
    expect(points.length).toBeGreaterThan(1)
    cards.forEach(obstacle => {
      for (let i = 1; i < points.length; i++) expect(crossesRect(points[i - 1], points[i], obstacle)).toBe(false)
    })
  })
})
it('detects a thin obstacle between sampling intervals', () => {
  expect(crossesRect({ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 1.5, y: 0, width: .5, height: 10 })).toBe(true)
})
