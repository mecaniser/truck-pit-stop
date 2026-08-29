/**
 * Scroll ownership moves as surfaces adopt the operating-surface pattern: the
 * shell scrolls below 1024px, an inner container scrolls above it. Hard-coding
 * `.db-staff-content` breaks silently the moment a surface owns its own
 * scroller, so resolve the owner from the node that actually changed.
 */
export function findScrollOwner(start: HTMLElement | null): HTMLElement | null {
  let node: HTMLElement | null = start
  while (node) {
    const { overflowY } = getComputedStyle(node)
    if ((overflowY === 'auto' || overflowY === 'scroll') && node.scrollHeight > node.clientHeight) return node
    node = node.parentElement
  }
  return null
}

export function scrollSurfaceToTop(start?: HTMLElement | null): void {
  const owner = findScrollOwner(start ?? null)
    ?? document.querySelector<HTMLElement>('.db-staff-content')
  owner?.scrollTo({ top: 0, behavior: 'auto' })
}
