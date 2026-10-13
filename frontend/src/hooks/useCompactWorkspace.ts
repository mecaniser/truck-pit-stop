import { useSyncExternalStore } from 'react'

const query = '(max-width: 639px), (max-width: 959px) and (pointer: coarse)'
function subscribe(callback: () => void) {
  const media = window.matchMedia?.(query)
  media?.addEventListener('change', callback)
  return () => media?.removeEventListener('change', callback)
}
export function useCompactWorkspace() {
  return useSyncExternalStore(subscribe, () => window.matchMedia?.(query).matches ?? false, () => false)
}

