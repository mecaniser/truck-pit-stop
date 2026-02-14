import { useCallback, useEffect, useState } from 'react'

const TIMER_PANEL_STORAGE_PREFIX = 'mechanic-timer-panel-expanded-v1'

export function useTimerPanelPersistence(userId: string | undefined) {
  const [isExpanded, setIsExpanded] = useState(true)

  useEffect(() => {
    const storageKey = `${TIMER_PANEL_STORAGE_PREFIX}:${userId || 'unknown'}`
    try {
      const saved = window.localStorage.getItem(storageKey)
      if (saved === null) {
        setIsExpanded(true)
        return
      }
      setIsExpanded(saved !== 'collapsed')
    } catch {
      setIsExpanded(true)
    }
  }, [userId])

  const toggleExpanded = useCallback(() => {
    setIsExpanded((prev) => {
      const next = !prev
      const storageKey = `${TIMER_PANEL_STORAGE_PREFIX}:${userId || 'unknown'}`
      try {
        window.localStorage.setItem(storageKey, next ? 'expanded' : 'collapsed')
      } catch {
        // Ignore storage errors; UI state still updates.
      }
      return next
    })
  }, [userId])

  return [isExpanded, toggleExpanded] as const
}
