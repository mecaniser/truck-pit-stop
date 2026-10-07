interface Label { id: string; x: number; y: number; width: number; height: number; priority: number }
interface Rect { x: number; y: number; width: number; height: number }
const overlaps = (a: Rect, b: Rect) => Math.abs(a.x - b.x) < (a.width + b.width) / 2 + 6 && Math.abs(a.y - b.y) < (a.height + b.height) / 2 + 6

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
    const clearAnchors = (candidate: Rect) => !labels.some(anchor => Math.abs(candidate.x - anchor.x) < candidate.width / 2 + 8 && Math.abs(candidate.y - anchor.y) < candidate.height / 2 + 8)
    const safeCandidates = candidates.filter(clearAnchors)
    const choices = safeCandidates.length ? safeCandidates : candidates
    const best = choices.find(candidate => !placed.some(other => overlaps(candidate, other))) || choices[0]
    placed.push(best)
    return { id: label.id, dx: best.x - label.x, dy: best.y - label.y }
  })
}
