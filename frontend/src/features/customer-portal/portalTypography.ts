import { useCallback, useMemo, useSyncExternalStore } from 'react'
import { useAuthStore } from '@/stores/authStore'

export const PORTAL_FONTS = [
  { id: 'sans', label: 'Sans serif', stack: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' },
  { id: 'serif', label: 'Serif', stack: 'Georgia, "Times New Roman", serif' },
  { id: 'mono', label: 'Monospace', stack: 'ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace' },
] as const
export const PORTAL_TEXT_SIZES = [
  { id: 'small', label: 'Small', px: 14 },
  { id: 'default', label: 'Default', px: 16 },
  { id: 'large', label: 'Large', px: 18 },
] as const
export interface PortalTypography {
  font: typeof PORTAL_FONTS[number]['id']
  size: typeof PORTAL_TEXT_SIZES[number]['id']
}
export const DEFAULT_PORTAL_TYPOGRAPHY: PortalTypography = { font: 'sans', size: 'default' }
const changedEvent = 'dieselbridge:customer-typography-changed'

export function parsePortalTypography(raw: string | null): PortalTypography {
  try {
    const value = JSON.parse(raw || 'null')
    if (value && PORTAL_FONTS.some(font => font.id === value.font) && PORTAL_TEXT_SIZES.some(size => size.id === value.size)) {
      return { font: value.font, size: value.size }
    }
  } catch { /* Ignore invalid or obsolete browser preferences. */ }
  return DEFAULT_PORTAL_TYPOGRAPHY
}

function subscribe(onChange: () => void) {
  window.addEventListener('storage', onChange)
  window.addEventListener(changedEvent, onChange)
  return () => {
    window.removeEventListener('storage', onChange)
    window.removeEventListener(changedEvent, onChange)
  }
}

/** Browser-only customer preferences never reuse or write the staff theme keys. */
export function usePortalTypography() {
  const { user } = useAuthStore()
  const key = user?.role === 'customer' && user.id && user.tenant_id
    ? `dieselbridge:customer-typography:v1:${user.tenant_id}:${user.id}` : null
  const read = useCallback(() => {
    try { return key ? localStorage.getItem(key) : null } catch { return null }
  }, [key])
  const raw = useSyncExternalStore(subscribe, read, () => null)
  const typography = useMemo(() => parsePortalTypography(raw), [raw])
  const update = useCallback((patch: Partial<PortalTypography>) => {
    if (!key) return false
    try {
      const next = { ...parsePortalTypography(localStorage.getItem(key)), ...patch }
      localStorage.setItem(key, JSON.stringify(next))
      window.dispatchEvent(new Event(changedEvent))
      return true
    } catch { return false }
  }, [key])
  return { typography, update }
}
