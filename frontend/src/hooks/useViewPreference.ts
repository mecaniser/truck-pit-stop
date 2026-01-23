import { useState, useEffect, useCallback } from 'react'

type ViewMode = 'list' | 'cards'

const STORAGE_KEY = 'tps_view_prefs'

function getStoredPrefs(): Record<string, ViewMode> {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    return stored ? JSON.parse(stored) : {}
  } catch {
    return {}
  }
}

function setStoredPref(pageKey: string, mode: ViewMode) {
  try {
    const prefs = getStoredPrefs()
    prefs[pageKey] = mode
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs))
  } catch {
    // localStorage unavailable
  }
}

export function useViewPreference(pageKey: string, defaultMode: ViewMode = 'list') {
  const [viewMode, setViewModeState] = useState<ViewMode>(() => {
    const prefs = getStoredPrefs()
    return prefs[pageKey] || defaultMode
  })

  const setViewMode = useCallback((mode: ViewMode) => {
    setViewModeState(mode)
    setStoredPref(pageKey, mode)
  }, [pageKey])

  return [viewMode, setViewMode] as const
}
