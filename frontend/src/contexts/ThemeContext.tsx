import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { toast } from 'react-hot-toast'
import api from '../lib/api'
import { useAuthStore } from '../stores/authStore'
import {
  DEFAULT_APPEARANCE,
  isAppearance,
  isPresentationBootstrap,
  type AccentColor,
  type AppearanceDensity,
  type AppearanceMode,
  type AppearancePreferences,
  type FontFamily,
  type NotificationPosition as ServerNotificationPosition,
  type PresentationBootstrap,
  type PresentationVariant,
} from '../types/presentation'
import { accentRampFor, appearanceTokenRecord } from './appearanceTokens'
export { appearanceTokenRecord } from './appearanceTokens'

export type { AccentColor, FontFamily }
export type FontSize = 'compact' | 'default' | 'comfortable' | 'large'
export type NotificationPosition = 'top' | 'bottom' | 'center-top'

export const ACCENT_OPTIONS = [
  { id: 'cyan' as const, label: 'Cyan', colors: { 400: '#22d3ee', 500: '#06b6d4', 600: '#0891b2' } },
  { id: 'indigo' as const, label: 'Indigo', colors: { 400: '#818cf8', 500: '#6366f1', 600: '#4f46e5' } },
  { id: 'emerald' as const, label: 'Emerald', colors: { 400: '#34d399', 500: '#10b981', 600: '#059669' } },
  { id: 'rose' as const, label: 'Rose', colors: { 400: '#fb7185', 500: '#f43f5e', 600: '#e11d48' } },
  { id: 'amber' as const, label: 'Amber', colors: { 400: '#fbbf24', 500: '#f59e0b', 600: '#d97706' } },
]

export const FONT_FAMILY_OPTIONS = [
  { id: 'geist' as const, label: 'Geist', stack: "'Geist', ui-sans-serif, system-ui, sans-serif" },
  { id: 'dm-sans' as const, label: 'DM Sans', stack: "'DM Sans', ui-sans-serif, sans-serif" },
  { id: 'jakarta' as const, label: 'Jakarta', stack: "'Plus Jakarta Sans', ui-sans-serif, sans-serif" },
  { id: 'inter' as const, label: 'Inter', stack: "'Inter', ui-sans-serif, system-ui, sans-serif" },
]

export const FONT_SIZE_OPTIONS = [
  { id: 'compact' as const, label: 'Compact', previewPx: 14 },
  { id: 'default' as const, label: 'Default', previewPx: 16 },
  { id: 'comfortable' as const, label: 'Comfortable', previewPx: 18 },
  { id: 'large' as const, label: 'Large', previewPx: 18 },
]

export const NOTIFICATION_POSITION_OPTIONS = [
  { id: 'top' as const, label: 'Top right', description: 'Keep alerts near the workspace header.' },
  { id: 'bottom' as const, label: 'Bottom right', description: 'Keep alerts near the lower edge of the workspace.' },
  { id: 'center-top' as const, label: 'Top center', description: 'Center alerts above the active work area.' },
]

export const DENSITY_OPTIONS: Array<{ id: AppearanceDensity; label: string; description: string }> = [
  { id: 'compact', label: 'Compact', description: 'More records, with every control still at least 44px.' },
  { id: 'default', label: 'Default', description: 'Balanced density for daily shop work.' },
  { id: 'comfortable', label: 'Comfortable', description: 'More space between controls and records.' },
  { id: 'large', label: 'Large', description: 'Maximum spacing and 48px controls.' },
]

export const MODE_OPTIONS: Array<{ id: AppearanceMode; label: string; description: string }> = [
  { id: 'dark', label: 'Night shop', description: 'Deep navy operating surfaces.' },
  { id: 'light', label: 'Day shop', description: 'Road-white work surfaces with a navy shell.' },
  { id: 'high_contrast', label: 'High contrast', description: 'Opaque surfaces and stronger edges.' },
]

const LEGACY_KEYS = {
  accent: 'theme-accent',
  fontFamily: 'theme-font-family',
  fontSize: 'theme-font-size',
  notification: 'theme-notification-position',
} as const

const legacyFontSize = (appearance: AppearancePreferences): FontSize => {
  if (appearance.font_size === 'small') return 'compact'
  if (appearance.font_size === 'large') return 'large'
  return 'default'
}

const toServerPosition = (value: NotificationPosition): ServerNotificationPosition =>
  value === 'top' ? 'top_right' : value === 'center-top' ? 'top_center' : 'bottom_right'

const toLegacyPosition = (value: ServerNotificationPosition): NotificationPosition =>
  value === 'top_right' ? 'top' : value === 'top_center' ? 'center-top' : 'bottom'

function readLegacyAppearance(): AppearancePreferences | null {
  if (typeof window === 'undefined') return null
  const accent = localStorage.getItem(LEGACY_KEYS.accent)
  const fontFamily = localStorage.getItem(LEGACY_KEYS.fontFamily)
  const legacySize = localStorage.getItem(LEGACY_KEYS.fontSize)
  const legacyNotification = localStorage.getItem(LEGACY_KEYS.notification)
  const candidate: AppearancePreferences = {
    ...DEFAULT_APPEARANCE,
    accent: ['cyan', 'indigo', 'emerald', 'rose', 'amber'].includes(accent || '') ? accent as AccentColor : DEFAULT_APPEARANCE.accent,
    font_family: ['geist', 'dm-sans', 'jakarta', 'inter'].includes(fontFamily || '') ? fontFamily as FontFamily : DEFAULT_APPEARANCE.font_family,
    font_size: legacySize === 'compact' ? 'small' : legacySize === 'comfortable' || legacySize === 'large' ? 'large' : 'default',
    density: ['compact', 'default', 'comfortable', 'large'].includes(legacySize || '') ? legacySize as AppearanceDensity : 'default',
    notification_position: legacyNotification === 'top' ? 'top_right' : legacyNotification === 'center-top' ? 'top_center' : 'bottom_right',
  }
  return [accent, fontFamily, legacySize, legacyNotification].some(Boolean) ? candidate : null
}

function mirrorLegacyAppearance(value: AppearancePreferences) {
  localStorage.setItem(LEGACY_KEYS.accent, value.accent)
  localStorage.setItem(LEGACY_KEYS.fontFamily, value.font_family)
  localStorage.setItem(LEGACY_KEYS.fontSize, legacyFontSize(value))
  localStorage.setItem(LEGACY_KEYS.notification, toLegacyPosition(value.notification_position))
}

function applyTokens(value: AppearancePreferences, variant: PresentationVariant) {
  const root = document.querySelector<HTMLElement>('.db-staff-shell')
  if (!root) return
  const tokens = appearanceTokenRecord(value)
  root.dataset.presentation = variant
  root.dataset.appearanceMode = value.mode
  root.dataset.appearanceDensity = value.density
  root.dataset.appearanceFontSize = value.font_size
  Object.entries(tokens).forEach(([name, token]) => root.style.setProperty(name, token))
  root.style.setProperty('--accent-400', tokens['--personal-accent-400'])
  root.style.setProperty('--accent-500', tokens['--personal-accent-500'])
  root.style.setProperty('--accent-600', tokens['--personal-accent-600'])
  root.style.setProperty('--theme-font-family', tokens['--font-body'])
  root.style.setProperty('--theme-font-scale', value.font_size === 'small' ? '0.875' : value.font_size === 'large' ? '1.125' : '1')
}

function cacheKey(userId: string, tenantId: string) {
  return `dieselbridge:presentation:v1:${tenantId}:${userId}`
}

function readCachedPresentation(userId: string, tenantId: string): PresentationBootstrap | null {
  if (typeof window === 'undefined') return null
  try {
    const value = JSON.parse(localStorage.getItem(cacheKey(userId, tenantId)) || 'null') as unknown
    if (!value || typeof value !== 'object') return null
    const candidate = value as Record<string, unknown>
    if (candidate.schema_version !== 1 || typeof candidate.timestamp !== 'number') return null
    if (Date.now() - candidate.timestamp > 30 * 24 * 60 * 60 * 1000) return null
    if (!isAppearance(candidate.appearance) || typeof candidate.revision !== 'number' || !['legacy', 'new'].includes(String(candidate.resolved_variant))) return null
    return {
      schema_version: 1,
      resolved_variant: candidate.resolved_variant as PresentationVariant,
      source: 'product_default',
      appearance: candidate.appearance,
      defaults: DEFAULT_APPEARANCE,
      revision: candidate.revision,
      legacy_migration_status: 'complete',
      updated_at: null,
    }
  } catch {
    return null
  }
}

function clearAppliedPresentation() {
  const root = document.querySelector<HTMLElement>('.db-staff-shell')
  if (!root) return
  delete root.dataset.appearanceMode
  delete root.dataset.appearanceDensity
  delete root.dataset.appearanceFontSize
  const names = Object.keys(appearanceTokenRecord(DEFAULT_APPEARANCE))
  names.concat(['--accent-400', '--accent-500', '--accent-600', '--theme-font-family', '--theme-font-scale'])
    .forEach(name => root.style.removeProperty(name))
}

interface ThemeContextValue {
  accent: AccentColor
  fontFamily: FontFamily
  fontSize: FontSize
  notificationPosition: NotificationPosition
  accentColors: { 400: string; 500: string; 600: string }
  presentationVariant: PresentationVariant
  appearance: AppearancePreferences
  committedAppearance: AppearancePreferences
  defaults: AppearancePreferences
  density: AppearanceDensity
  mode: AppearanceMode
  hasUnappliedChanges: boolean
  saveStatus: 'idle' | 'saving' | 'saved' | 'error' | 'conflict'
  setAccent: (value: AccentColor) => void
  setFontFamily: (value: FontFamily) => void
  setFontSize: (value: FontSize) => void
  setNotificationPosition: (value: NotificationPosition) => void
  setDensity: (value: AppearanceDensity) => void
  setMode: (value: AppearanceMode) => void
  applyAppearance: () => Promise<void>
  cancelPreview: () => void
  previewDefaults: () => void
  resetToDefaults: () => Promise<void>
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { user, authSessionEpoch, isAuthenticated } = useAuthStore()
  const presentationWasReturned = user?.presentation !== undefined
  const bootstrap = isPresentationBootstrap(user?.presentation) ? user.presentation : null
  const eligibleStaff = Boolean(isAuthenticated && user?.tenant_id && !['customer', 'driver', 'fleet_manager', 'super_admin'].includes(user?.role || ''))
  const identity = eligibleStaff && user?.tenant_id ? `${authSessionEpoch}:${user.id}:${user.tenant_id}` : null
  const cached = eligibleStaff && user?.tenant_id ? readCachedPresentation(user.id, user.tenant_id) : null
  const [serverPresentation, setServerPresentation] = useState<PresentationBootstrap | null>(bootstrap ?? (presentationWasReturned ? null : cached))
  const variant = serverPresentation?.resolved_variant ?? 'legacy'
  const initial = serverPresentation?.appearance ?? readLegacyAppearance() ?? DEFAULT_APPEARANCE
  const [committed, setCommitted] = useState<AppearancePreferences>(initial)
  const [draft, setDraft] = useState<AppearancePreferences>(initial)
  const [revision, setRevision] = useState(bootstrap?.revision ?? 0)
  const [defaults, setDefaults] = useState<AppearancePreferences>(bootstrap?.defaults ?? DEFAULT_APPEARANCE)
  const [saveStatus, setSaveStatus] = useState<ThemeContextValue['saveStatus']>('idle')
  const previousIdentity = useRef<string | null>(null)
  const migrationAttempt = useRef<{ key: string; requestId: string } | null>(null)
  const draftRef = useRef(initial)
  const revisionRef = useRef(bootstrap?.revision ?? 0)
  const legacySaveTimer = useRef<number | null>(null)
  const legacySaveSequence = useRef(0)

  useEffect(() => { draftRef.current = draft }, [draft])
  useEffect(() => { revisionRef.current = revision }, [revision])
  useEffect(() => () => {
    if (legacySaveTimer.current !== null) window.clearTimeout(legacySaveTimer.current)
  }, [])

  useEffect(() => {
    if (previousIdentity.current && previousIdentity.current !== identity) {
      clearAppliedPresentation()
    }
    previousIdentity.current = identity
    const matchingCache = eligibleStaff && user?.tenant_id ? readCachedPresentation(user.id, user.tenant_id) : null
    // A server response that includes an invalid presentation record must fail closed.
    // Cached presentation is an offline fallback only when that field was unavailable.
    const nextPresentation = bootstrap ?? (presentationWasReturned ? null : matchingCache)
    setServerPresentation(nextPresentation)
    const next = nextPresentation?.appearance ?? readLegacyAppearance() ?? DEFAULT_APPEARANCE
    draftRef.current = next
    setCommitted(next)
    setDraft(next)
    setRevision(nextPresentation?.revision ?? 0)
    setDefaults(nextPresentation?.defaults ?? DEFAULT_APPEARANCE)
    setSaveStatus('idle')
    if (!eligibleStaff) clearAppliedPresentation()
  }, [identity, bootstrap, eligibleStaff, presentationWasReturned, user?.id, user?.tenant_id])

  useEffect(() => {
    if (!eligibleStaff) return
    applyTokens(draft, variant)
  }, [draft, eligibleStaff, identity, variant])

  useEffect(() => {
    if (!eligibleStaff || !user?.tenant_id || !serverPresentation) return
    const key = cacheKey(user.id, user.tenant_id)
    localStorage.setItem(key, JSON.stringify({
      schema_version: 1,
      appearance: committed,
      revision,
      resolved_variant: variant,
      timestamp: Date.now(),
    }))
  }, [committed, eligibleStaff, revision, serverPresentation, user?.id, user?.tenant_id, variant])

  useEffect(() => {
    if (!eligibleStaff) return
    let cancelled = false
    const refresh = async () => {
      try {
        const { data } = await api.get<PresentationBootstrap>('/auth/me/appearance')
        if (cancelled) return
        if (!isPresentationBootstrap(data)) {
          setServerPresentation(null)
          setCommitted(DEFAULT_APPEARANCE)
          draftRef.current = DEFAULT_APPEARANCE
          setDraft(DEFAULT_APPEARANCE)
          setRevision(0)
          setDefaults(DEFAULT_APPEARANCE)
          return
        }
        setServerPresentation(data)
        setCommitted(data.appearance)
        setDraft(current => {
          if (JSON.stringify(current) !== JSON.stringify(committed)) return current
          draftRef.current = data.appearance
          return data.appearance
        })
        setRevision(data.revision)
        setDefaults(data.defaults)
      } catch {
        // A verified identity-matched cache remains the offline presentation fallback.
      }
    }
    const interval = window.setInterval(refresh, 60_000)
    const onFocus = () => void refresh()
    window.addEventListener('focus', onFocus)
    return () => {
      cancelled = true
      window.clearInterval(interval)
      window.removeEventListener('focus', onFocus)
    }
  }, [committed, eligibleStaff, identity])

  useEffect(() => {
    if (!eligibleStaff || !identity || !serverPresentation || serverPresentation.legacy_migration_status !== 'pending') return
    const migrationKey = `${identity}:${serverPresentation.revision}`
    if (migrationAttempt.current?.key === migrationKey) return
    const requestId = crypto.randomUUID()
    migrationAttempt.current = { key: migrationKey, requestId }
    const legacy = readLegacyAppearance() ?? serverPresentation.defaults
    api.put<PresentationBootstrap>('/auth/me/appearance', {
      schema_version: 1,
      base_revision: serverPresentation.revision,
      appearance: legacy,
      migration_source: 'legacy_local_v1',
    }, { headers: { 'Idempotency-Key': requestId } }).then(({ data }) => {
      if (!isPresentationBootstrap(data)) return
      setServerPresentation(data)
      setCommitted(data.appearance)
      draftRef.current = data.appearance
      setDraft(data.appearance)
      setRevision(data.revision)
      setDefaults(data.defaults)
      mirrorLegacyAppearance(data.appearance)
    }).catch(() => undefined)
  }, [eligibleStaff, identity, serverPresentation])

  const persistLegacyChange = useCallback((next: AppearancePreferences) => {
    mirrorLegacyAppearance(next)
    if (!eligibleStaff) return
    legacySaveSequence.current += 1
    const sequence = legacySaveSequence.current
    if (legacySaveTimer.current !== null) window.clearTimeout(legacySaveTimer.current)
    legacySaveTimer.current = window.setTimeout(async () => {
      try {
        const { data } = await api.put<PresentationBootstrap>('/auth/me/appearance', {
          schema_version: 1,
          base_revision: revisionRef.current,
          appearance: next,
          migration_source: null,
        }, { headers: { 'Idempotency-Key': crypto.randomUUID() } })
        if (sequence !== legacySaveSequence.current || !isPresentationBootstrap(data)) return
        revisionRef.current = data.revision
        draftRef.current = data.appearance
        setServerPresentation(data)
        setCommitted(data.appearance)
        setDraft(data.appearance)
        setRevision(data.revision)
        setDefaults(data.defaults)
        mirrorLegacyAppearance(data.appearance)
      } catch {
        // Legacy mode remains locally compatible; the next explicit change retries.
      }
    }, 250)
  }, [eligibleStaff])

  const updatePreference = useCallback((patch: Partial<AppearancePreferences>) => {
    const next = { ...draftRef.current, ...patch }
    draftRef.current = next
    setDraft(next)
    setSaveStatus('idle')
    if (variant === 'legacy') {
      setCommitted(next)
      persistLegacyChange(next)
    }
  }, [persistLegacyChange, variant])

  const applyAppearance = useCallback(async () => {
    if (!eligibleStaff) return
    setSaveStatus('saving')
    try {
      const requestId = crypto.randomUUID()
      const { data } = await api.put<PresentationBootstrap>('/auth/me/appearance', {
        schema_version: 1,
        base_revision: revision,
        appearance: draft,
        migration_source: null,
      }, { headers: { 'Idempotency-Key': requestId } })
      if (!isPresentationBootstrap(data)) throw new Error('Appearance response was invalid')
      setServerPresentation(data)
      setCommitted(data.appearance)
      draftRef.current = data.appearance
      setDraft(data.appearance)
      setRevision(data.revision)
      setDefaults(data.defaults)
      mirrorLegacyAppearance(data.appearance)
      setSaveStatus('saved')
      toast.success('Appearance applied')
    } catch (error: unknown) {
      const status = typeof error === 'object' && error && 'response' in error
        ? (error as { response?: { status?: number } }).response?.status
        : undefined
      if (status === 409) {
        setSaveStatus('conflict')
        try {
          const { data } = await api.get<PresentationBootstrap>('/auth/me/appearance')
          if (isPresentationBootstrap(data)) {
            setServerPresentation(data)
            setCommitted(data.appearance)
            setRevision(data.revision)
            setDefaults(data.defaults)
            setSaveStatus('idle')
          }
        } catch {
          // Preserve the local draft; the next explicit Apply remains blocked by the stale revision.
        }
        toast.error('Appearance changed in another session. Refresh before applying again.')
      } else {
        setSaveStatus('error')
        toast.error('Appearance could not be saved. Your preview is still available here.')
      }
    }
  }, [draft, eligibleStaff, revision])

  const cancelPreview = useCallback(() => {
    draftRef.current = committed
    setDraft(committed)
    setSaveStatus('idle')
  }, [committed])

  const previewDefaults = useCallback(() => {
    draftRef.current = defaults
    setDraft(defaults)
    setSaveStatus('idle')
  }, [defaults])

  const resetToDefaults = useCallback(async () => {
    if (!eligibleStaff) return
    setSaveStatus('saving')
    try {
      const { data } = await api.delete<PresentationBootstrap>('/auth/me/appearance', {
        data: { schema_version: 1, base_revision: revision },
        headers: { 'Idempotency-Key': crypto.randomUUID() },
      })
      if (!isPresentationBootstrap(data)) throw new Error('Appearance response was invalid')
      setServerPresentation(data)
      setCommitted(data.appearance)
      draftRef.current = data.appearance
      setDraft(data.appearance)
      setRevision(data.revision)
      setDefaults(data.defaults)
      mirrorLegacyAppearance(data.appearance)
      setSaveStatus('saved')
      toast.success('Appearance reset')
    } catch {
      setDraft(committed)
      setSaveStatus('error')
      toast.error('Appearance could not be reset')
    }
  }, [committed, eligibleStaff, revision])

  const fontSize = legacyFontSize(draft)
  const notificationPosition = toLegacyPosition(draft.notification_position)
  const accentColors = accentRampFor(draft.accent, draft.mode)
  const value = useMemo<ThemeContextValue>(() => ({
    accent: draft.accent,
    fontFamily: draft.font_family,
    fontSize,
    notificationPosition,
    accentColors,
    presentationVariant: variant,
    appearance: draft,
    committedAppearance: committed,
    defaults,
    density: draft.density,
    mode: draft.mode,
    hasUnappliedChanges: JSON.stringify(draft) !== JSON.stringify(committed),
    saveStatus,
    setAccent: value => updatePreference({ accent: value }),
    setFontFamily: value => updatePreference({ font_family: value }),
    setFontSize: value => updatePreference({
      font_size: value === 'compact' ? 'small' : value === 'default' ? 'default' : 'large',
    }),
    setNotificationPosition: value => updatePreference({ notification_position: toServerPosition(value) }),
    setDensity: value => updatePreference({ density: value }),
    setMode: value => updatePreference({ mode: value }),
    applyAppearance,
    cancelPreview,
    previewDefaults,
    resetToDefaults,
  }), [accentColors, applyAppearance, cancelPreview, committed, defaults, draft, fontSize, notificationPosition, previewDefaults, resetToDefaults, saveStatus, updatePreference, variant])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const value = useContext(ThemeContext)
  if (!value) throw new Error('useTheme must be used within a ThemeProvider')
  return value
}
