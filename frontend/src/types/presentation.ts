export type PresentationVariant = 'legacy' | 'new'
export type PresentationSource = 'global_force_legacy' | 'user_override' | 'tenant_default' | 'product_default'
export type AccentColor = 'cyan' | 'indigo' | 'emerald' | 'rose' | 'amber'
export type FontFamily = 'geist' | 'dm-sans' | 'jakarta' | 'inter'
export type AppearanceFontSize = 'small' | 'default' | 'large'
export type AppearanceDensity = 'compact' | 'default' | 'comfortable' | 'large'
export type NotificationPosition = 'top_right' | 'bottom_right' | 'top_center'
export type AppearanceMode = 'light' | 'dark' | 'high_contrast'

export interface AppearancePreferences {
  accent: AccentColor
  font_family: FontFamily
  font_size: AppearanceFontSize
  density: AppearanceDensity
  notification_position: NotificationPosition
  mode: AppearanceMode
}

export interface PresentationBootstrap {
  schema_version: 1
  resolved_variant: PresentationVariant
  source: PresentationSource
  appearance: AppearancePreferences
  defaults: AppearancePreferences
  revision: number
  legacy_migration_status: 'pending' | 'complete'
  updated_at: string | null
}

export const DEFAULT_APPEARANCE: AppearancePreferences = Object.freeze({
  accent: 'cyan',
  font_family: 'geist',
  font_size: 'default',
  density: 'default',
  notification_position: 'bottom_right',
  mode: 'dark',
})

export function isAppearance(value: unknown): value is AppearancePreferences {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Record<string, unknown>
  return ['cyan', 'indigo', 'emerald', 'rose', 'amber'].includes(String(candidate.accent))
    && ['geist', 'dm-sans', 'jakarta', 'inter'].includes(String(candidate.font_family))
    && ['small', 'default', 'large'].includes(String(candidate.font_size))
    && ['compact', 'default', 'comfortable', 'large'].includes(String(candidate.density))
    && ['top_right', 'bottom_right', 'top_center'].includes(String(candidate.notification_position))
    && ['light', 'dark', 'high_contrast'].includes(String(candidate.mode))
}

export function isPresentationBootstrap(value: unknown): value is PresentationBootstrap {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Record<string, unknown>
  return candidate.schema_version === 1
    && ['legacy', 'new'].includes(String(candidate.resolved_variant))
    && ['global_force_legacy', 'user_override', 'tenant_default', 'product_default'].includes(String(candidate.source))
    && typeof candidate.revision === 'number'
    && candidate.revision >= 0
    && isAppearance(candidate.appearance)
    && isAppearance(candidate.defaults)
    && ['pending', 'complete'].includes(String(candidate.legacy_migration_status))
    && (candidate.updated_at === null || typeof candidate.updated_at === 'string')
}
