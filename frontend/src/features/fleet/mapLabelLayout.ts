interface Label { id: string; x: number; y: number; width: number; height: number; priority: number }
interface Rect { x: number; y: number; width: number; height: number }
const overlaps = (a: Rect, b: Rect) => Math.abs(a.x - b.x) < (a.width + b.width) / 2 + 6 && Math.abs(a.y - b.y) < (a.height + b.height) / 2 + 6

const crosses = (from: Rect, to: Rect, obstacle: Rect) => {
  // Sample the short leader to avoid routing it through a previously placed tag.
  const steps = Math.ceil(Math.hypot(to.x - from.x, to.y - from.y) / 4)
  for (let i = 1; i < steps; i++) {
    const x = from.x + (to.x - from.x) * i / steps
    const y = from.y + (to.y - from.y) * i / steps
    if (Math.abs(x - obstacle.x) < obstacle.width / 2 + 2 && Math.abs(y - obstacle.y) < obstacle.height / 2 + 2) return true
  }
  return false
}

/** Offset labels only. Geographic anchors never move and no units are discarded. */
export function layoutTruckLabels(labels: Label[], width: number, height: number, obstacles: Rect[] = []) {
  const placed: Rect[] = [...obstacles]
  return [...labels].sort((a, b) => b.priority - a.priority || a.id.localeCompare(b.id)).map(label => {
    if (label.x < 0 || label.x > width || label.y < 0 || label.y > height) return { id: label.id, dx: 0, dy: -28 }
    const candidates: Rect[] = []
    const add = (x: number, y: number) => candidates.push({ ...label,
      x: Math.max(label.width / 2 + 8, Math.min(width - label.width / 2 - 8, x)),
      y: Math.max(label.height / 2 + 8, Math.min(height - label.height / 2 - 8, y)) })
    add(label.x, label.y - 28)
    for (let y = label.height / 2 + 8; y <= height - label.height / 2 - 8; y += label.height + 8) {
      for (let x = label.width / 2 + 8; x <= width - label.width / 2 - 8; x += label.width + 8) add(x, y)
    }
    candidates.sort((a, b) => Math.hypot(a.x - label.x, a.y - label.y + 28) - Math.hypot(b.x - label.x, b.y - label.y + 28))
    const best = candidates.find(candidate => !placed.some(other => overlaps(candidate, other) || crosses(label, candidate, other))) || candidates.find(candidate => !placed.some(other => overlaps(candidate, other))) || candidates[0]
    placed.push(best)
    return { id: label.id, dx: best.x - label.x, dy: best.y - label.y }
  })
}
