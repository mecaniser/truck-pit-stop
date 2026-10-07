export interface Point { x: number; y: number }
export interface LeaderRect extends Point { width: number; height: number }

/** Exact segment/interior intersection. Boundary travel is allowed for visibility edges. */
export function crossesRect(a: Point, b: Point, rect: LeaderRect): boolean {
  let low = 0, high = 1
  for (const axis of ['x', 'y'] as const) {
    const half = (axis === 'x' ? rect.width : rect.height) / 2 - .01
    const delta = b[axis] - a[axis]
    if (Math.abs(delta) < .00001) {
      if (Math.abs(a[axis] - rect[axis]) >= half) return false
    } else {
      const first = (rect[axis] - half - a[axis]) / delta
      const second = (rect[axis] + half - a[axis]) / delta
      low = Math.max(low, Math.min(first, second))
      high = Math.min(high, Math.max(first, second))
      if (low >= high) return false
    }
  }
  return high > 0 && low < 1
}

/** Shortest visible polyline to a card edge, with 4px clearance around other cards. */
export function routeLeader(start: Point, target: LeaderRect, obstacles: LeaderRect[]): Point[] {
  const inflate = (rect: LeaderRect) => ({ ...rect, width: rect.width + 8, height: rect.height + 8 })
  const boxes = [...obstacles, target].map(inflate)
  const ports = [
    { x: target.x, y: target.y - target.height / 2 - 4 },
    { x: target.x + target.width / 2 + 4, y: target.y },
    { x: target.x, y: target.y + target.height / 2 + 4 },
    { x: target.x - target.width / 2 - 4, y: target.y },
  ]
  const edges = [
    { x: target.x, y: target.y - target.height / 2 },
    { x: target.x + target.width / 2, y: target.y },
    { x: target.x, y: target.y + target.height / 2 },
    { x: target.x - target.width / 2, y: target.y },
  ]
  // A fixed UI overlay can cover the true origin. Allow the first segment to exit it.
  const visible = (a: Point, b: Point) => !boxes.some(box => {
    if (a === start && Math.abs(start.x - box.x) < box.width / 2 && Math.abs(start.y - box.y) < box.height / 2) return false
    return crossesRect(a, b, box)
  })
  const points = [start, ...ports, ...boxes.flatMap(box => [
    { x: box.x - box.width / 2, y: box.y - box.height / 2 },
    { x: box.x + box.width / 2, y: box.y - box.height / 2 },
    { x: box.x + box.width / 2, y: box.y + box.height / 2 },
    { x: box.x - box.width / 2, y: box.y + box.height / 2 },
  ])]
  const distances = points.map(() => Infinity), previous = points.map(() => -1), visited = new Set<number>()
  distances[0] = 0
  while (visited.size < points.length) {
    let current = -1
    for (let i = 0; i < points.length; i++) if (!visited.has(i) && (current < 0 || distances[i] < distances[current])) current = i
    if (current < 0 || !Number.isFinite(distances[current])) break
    if (current >= 1 && current <= 4) {
      const result = [edges[current - 1]]
      for (let node = current; node !== -1; node = previous[node]) result.unshift(points[node])
      return result
    }
    visited.add(current)
    for (let next = 1; next < points.length; next++) {
      if (visited.has(next)) continue
      const cost = distances[current] + Math.hypot(points[next].x - points[current].x, points[next].y - points[current].y)
      if (cost < distances[next] && visible(points[current], points[next])) {
        distances[next] = cost; previous[next] = current
      }
    }
  }
  return [] // No misleading straight connector through a card when no corridor exists.
}
