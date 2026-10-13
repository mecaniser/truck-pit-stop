import { useEffect } from 'react'
import { useCompactWorkspace } from './useCompactWorkspace'

/** Phone keyboards can shrink only the visual viewport, leaving 100dvh unchanged.
 * Publish dimensions for the compact record frame and its portaled editor only.
 * Keep native pinch zoom: do not resize/reposition the layout while magnified. */
export function useWorkspaceViewport() {
  const compact = useCompactWorkspace()
  useEffect(() => {
    const viewport = window.visualViewport
    if (!compact || !viewport) return
    const style = document.documentElement.style
    const heightKey = '--db-workspace-viewport-height'
    const topKey = '--db-workspace-viewport-top'
    const previousHeight = style.getPropertyValue(heightKey)
    const previousTop = style.getPropertyValue(topKey)
    let frame = 0
    const restore = () => {
      if (previousHeight) style.setProperty(heightKey, previousHeight)
      else style.removeProperty(heightKey)
      if (previousTop) style.setProperty(topKey, previousTop)
      else style.removeProperty(topKey)
    }
    const update = () => {
      if (Math.abs(viewport.scale - 1) > 0.05 || viewport.height <= 0) {
        restore()
        return
      }
      style.setProperty(heightKey, `${viewport.height}px`)
      style.setProperty(topKey, `${Math.max(0, viewport.offsetTop)}px`)
    }
    const schedule = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(update)
    }
    update()
    viewport.addEventListener('resize', schedule)
    viewport.addEventListener('scroll', schedule)
    return () => {
      cancelAnimationFrame(frame)
      viewport.removeEventListener('resize', schedule)
      viewport.removeEventListener('scroll', schedule)
      restore()
    }
  }, [compact])
}
