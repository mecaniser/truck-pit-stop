import { DEFAULT_APPEARANCE, type AppearancePreferences, type PresentationBootstrap, type PresentationVariant } from '../../types/presentation'

export function deepFreeze<T>(value: T): Readonly<T> {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value)
    Object.values(value as Record<string, unknown>).forEach(item => deepFreeze(item))
  }
  return value
}

export const appearanceDefaults = deepFreeze({ ...DEFAULT_APPEARANCE })
export const appearanceLargeLight = deepFreeze<AppearancePreferences>({
  accent: 'amber', font_family: 'inter', font_size: 'large', density: 'large', notification_position: 'top_center', mode: 'light',
})
export const appearanceCompactContrast = deepFreeze<AppearancePreferences>({
  accent: 'indigo', font_family: 'geist', font_size: 'small', density: 'compact', notification_position: 'bottom_right', mode: 'high_contrast',
})

export function presentationFixture(variant: PresentationVariant = 'new', appearance: AppearancePreferences = appearanceDefaults): PresentationBootstrap {
  return deepFreeze({
    schema_version: 1,
    resolved_variant: variant,
    source: variant === 'new' ? 'user_override' : 'product_default',
    appearance: { ...appearance },
    defaults: { ...appearanceDefaults },
    revision: 4,
    legacy_migration_status: 'complete',
    updated_at: '2026-08-11T15:30:00Z',
  })
}

export const invalidLegacyAppearance = deepFreeze({ accent: 'url(javascript:bad)', font: 'unknown', size: '400%' })
export const missingLegacyAppearance = deepFreeze({ accent: null, font: null, size: null, notification: null })
